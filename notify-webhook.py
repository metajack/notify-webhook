#!/usr/bin/env python

import sys

import simplejson as json


POST_URL = 'http://example.com'


def make_json(old, new, ref):
    pass


def post(url, data):
    print url
    print data


if __name__ == '__main__':
    for line in sys.stdin.xreadlines():
        old, new, ref = line.strip().split(' ')
        data = make_json(old, new, ref)
        post(POST_URL, data)
