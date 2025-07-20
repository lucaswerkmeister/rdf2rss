#!/usr/bin/env python3
# -*- coding utf-8 -*-

import argparse
import bs4
import datetime
import PyRSS2Gen  # type: ignore
import rdflib  # type: ignore
import re
import requests
from sys import stdout, stderr
from typing import Optional, cast
from urllib.parse import urljoin

rdflib.plugin.register('rdfa',
                       rdflib.parser.Parser,
                       'pyRdfa.rdflibparsers',
                       'RDFaParser')

parser = argparse.ArgumentParser(description='Generate an RSS feed file ' +
                                 'from the RDF description of a blog.')
parser.add_argument('root',
                    metavar='URL',
                    help='the URL of the blog')
parser.add_argument('out',
                    metavar='FILE',
                    type=argparse.FileType('w'),
                    default=stdout,
                    nargs='?',
                    help='the output file (default: standard output)')
parser.add_argument('-d',
                    '--description',
                    action='store_true',
                    help='if an item (blog post) has no RDFa description, ' +
                    'use its content as the RSS description')
parser.add_argument('-k',
                    '--keyword',
                    metavar='KEYWORD',
                    help='only output items (blog posts) ' +
                    'with the given keyword (tag)')
parser.add_argument('-v',
                    '--verbose',
                    action='store_true',
                    help='print the RDF graph in Turtle format ' +
                    'to standard error')

args = parser.parse_args()

our_user_agent = 'rdf2rss (https://github.com/lucaswerkmeister/rdf2rss)'
rdflib_default_user_agent = rdflib.parser.headers['User-agent']
rdflib.parser.headers['User-agent'] = \
    f'{our_user_agent} {rdflib_default_user_agent}'
requests_default_user_agent = requests.utils.default_user_agent
requests.utils.default_user_agent = lambda *args, **kwargs: \
    f'{our_user_agent} {requests_default_user_agent(*args, **kwargs)}'

root = rdflib.URIRef(args.root)
graph = rdflib.Graph()
schema = rdflib.Namespace('http://schema.org/')


def guess_format(url):
    if url.endswith('/'):
        url += 'index.html'
    return rdflib.util.guess_format(url)


def value(start, *predicates):
    current = start
    for predicate in predicates:
        current = graph.value(current, predicate, any=False)
        if current is None:
            return None
    return cleanup(current.toPython())


def values(subject, predicate):
    return [cleanup(value.toPython())
            for value in graph.objects(subject, predicate)]


def comma_separated_values(subject, predicate):
    return [value.strip()
            for item in values(subject, predicate)
            for value in item.split(',')]


def cleanup(value):
    if value is None:
        return None
    if type(value) is datetime.date:
        return datetime.datetime.combine(value, datetime.time())
    if type(value) is not str:
        return value
    return re.sub(r'\s+', ' ', value).strip()


def description(posting: rdflib.term.Node) -> Optional[str]:
    explicit_description = value(posting, schema.description)
    if explicit_description is not None:
        return explicit_description
    if not args.description:
        return None

    # get the HTML
    posting_uri = str(posting)
    response = requests.get(posting_uri)
    if not response.ok:
        return None
    html = response.text

    # parse it and find the content inside
    content = bs4.BeautifulSoup(html, 'html.parser')  # type: bs4.element.Tag
    if (about := content.find(resource=posting_uri)) is not None:
        content = cast(bs4.element.Tag, about)
    elif (article := content.article) is not None:
        content = article

    # clean it up
    for bad_tag_name in [
            'footer',
            'header',
            'link',
            'meta',
    ]:
        for bad_tag in content.find_all(bad_tag_name):
            bad_tag.decompose()
    for bad_attribute_name in [
            'property',
            'resource',
            'typeof',
    ]:
        for tag in content.find_all(attrs={bad_attribute_name: True}):
            tag = cast(bs4.element.Tag, tag)
            del tag[bad_attribute_name]
        # find_all() will not return content itself, so check that separately
        if bad_attribute_name in content.attrs:
            del content[bad_attribute_name]
    for a in content.find_all('a'):
        a = cast(bs4.element.Tag, a)
        if (href := a.get('href')) is not None:
            href = cast(str, href)
            a['href'] = urljoin(posting_uri, href)

    return str(content)


graph.parse(root,
            format=guess_format(root))

items = []

for posting in graph.subjects(rdflib.RDF.type, schema.BlogPosting):
    graph.parse(posting,  # type: ignore
                format=guess_format(posting))
    if args.keyword is not None:
        keywords = comma_separated_values(posting, schema.keywords)
        if args.keyword not in keywords:
            continue
    items.append(PyRSS2Gen.RSSItem(
        title=value(posting, schema.name),
        link=posting,
        description=description(posting),
        guid=PyRSS2Gen.Guid(posting),
        pubDate=value(posting, schema.datePublished),
        author=value(posting, schema.author, schema.email),
    ))

if args.verbose:
    # rdflib refuses to return an unencoded string,
    # so we have to decode the bytes object before print can encode it again
    encoded = graph.serialize(format='turtle',
                              encoding='utf-8')
    print(encoded.decode(encoding='utf-8'), file=stderr)

# sort by descending pubDate (reverse chronological order),
# moving items without schema:datePublished to the end
items.sort(
    key=lambda item: (item.pubDate is not None, item.pubDate),
    reverse=True,
)

title = value(root, schema.name)
if args.keyword is not None:
    title += ' (#' + args.keyword + ')'

rss = PyRSS2Gen.RSS2(
    title=title,
    link=root,
    description=value(root, schema.description),
    lastBuildDate=datetime.datetime.utcnow(),
    items=items,
)

rss.write_xml(args.out, encoding='utf-8')
args.out.write('\n')
