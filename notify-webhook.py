#!/usr/bin/env python

import sys
import urllib, urllib2
import subprocess
from datetime import datetime
import simplejson as json


POST_URL = 'http://example.com'
REPO_URL = 'http://example.com'
COMMIT_URL = r'http://example.com/commit/%s'
REPO_NAME = 'gitrepo'
REPO_OWNER_NAME = 'Git U. Some'
REPO_OWNER_EMAIL = 'git@example.com'
REPO_DESC = ''


def get_revisions(old, new):
    git = subprocess.Popen(['git-rev-list', '--pretty=medium', '%s..%s' % (old, new)], stdout=subprocess.PIPE)
    sections = git.stdout.read().split('\n\n')[:-1]

    revisions = []
    s = 0
    while s < len(sections):
	lines = sections[s].split('\n')
	    
	# first line is 'commit HASH\n'
	props = {'id': lines[0].strip().split(' ')[1]}
	    
	# read the header
	for l in lines[1:]:
	    key, val = l.split(' ', 1)
	    props[key[:-1].lower()] = val.strip()

	# read the commit message
	props['message'] = sections[s+1]

	# use github time format
	basetime = datetime.strptime(props['date'][:-6], "%a %b %d %H:%M:%S %Y")
	tzstr = props['date'][-5:]
	props['date'] = basetime.strftime('%Y-%m-%dT%H:%M:%S') + tzstr

	# split up author
	parts = props['author'].split(' ')
	props['name'] = ' '.join(parts[:2])
	props['email'] = parts[2][1:-1]
	del props['author']
	
	revisions.append(props)
	s += 2
	
    return revisions

def make_json(old, new, ref):
    data = {
	'before': old,
	'after': new,
	'ref': ref,
	'repository': {
	    'url': REPO_URL,
	    'name': REPO_NAME,
	    'description': REPO_DESC,
	    'owner': {
		'name': REPO_OWNER_NAME,
		'email': REPO_OWNER_EMAIL
		}
	    }
	}

    revisions = get_revisions(old, new)
    commits = []
    for r in revisions:
	commits.append({'id': r['id'],
			'author': {'name': r['name'], 'email': r['email']},
			'url': COMMIT_URL % r['id'],
			'message': r['message'],
			'timestamp': r['date']
			})
    data['commits'] = commits

    return json.dumps(data)


def post(url, data):
    u = urllib2.urlopen(POST_URL, urllib.urlencode({'payload': data}))
    u.read()
    u.close()


if __name__ == '__main__':
    for line in sys.stdin.xreadlines():
        old, new, ref = line.strip().split(' ')
        data = make_json(old, new, ref)
        post(POST_URL, data)
