#!/usr/bin/env python3
# -*- coding utf-8 -*-

import argparse
import datetime
import PyRSS2Gen  # type: ignore
import rdflib  # type: ignore
import re
from sys import stdout, stderr

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
parser.add_argument('-v',
                    '--verbose',
                    action='store_true',
                    help='print the RDF graph in Turtle format ' +
                    'to standard error')

args = parser.parse_args()

root = rdflib.URIRef(args.root)
graph = rdflib.Graph()
schema = rdflib.Namespace('http://schema.org/')


def value(start, *predicates):
    current = start
    for predicate in predicates:
        current = graph.value(current, predicate, any=False)
        if current is None:
            return None
    return cleanup(current.toPython())


def cleanup(value):
    if value is None:
        return None
    if type(value) is datetime.date:
        return datetime.datetime.combine(value, datetime.time())
    if type(value) is not str:
        return value
    return re.sub(r'\s+', ' ', value).strip()


graph.parse(root)

items = []

for posting in graph.subjects(rdflib.RDF.type, schema.BlogPosting):
    graph.parse(posting)
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

rss = PyRSS2Gen.RSS2(
    title=value(root, schema.name),
    link=root,
    description=value(root, schema.description),
    lastBuildDate=datetime.datetime.utcnow(),
    items=items,
)

rss.write_xml(args.out, encoding='utf-8')
args.out.write('\n')
