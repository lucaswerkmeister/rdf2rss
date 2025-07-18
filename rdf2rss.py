#!/usr/bin/env python3
# -*- coding utf-8 -*-

import argparse
import datetime
import PyRSS2Gen  # type: ignore
import rdflib  # type: ignore
import re
from sys import stdout, stderr

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
parser.add_argument('-k',
                    '--keyword',
                    metavar='KEYWORD',
                    help='If set, only output items (blog posts) ' +
                    'with the given keyword (tag).')
parser.add_argument('-v',
                    '--verbose',
                    action='store_true',
                    help='print the RDF graph in Turtle format ' +
                    'to standard error')

args = parser.parse_args()

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
        description=value(posting, schema.description),
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

# sort by pubDate, moving items without one to the end
items.sort(key=lambda item: (item.pubDate is None, item.pubDate))

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
