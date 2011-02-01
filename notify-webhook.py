#!/usr/bin/env python

import sys
import urllib, urllib2
import re
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


EMAIL_RE = re.compile("^(.*) <(.*)>$")
DIFF_TREE_RE = re.compile("^:(?P<src_mode>[0-9]{6}) (?P<dst_mode>[0-9]{6}) (?P<src_hash>[0-9a-f]{7,40}) (?P<dst_hash>[0-9a-f]{7,40}) (?P<status>[ADMTUX]|[CR][0-9]{1,3})\s+(?P<file1>\S+)(?:\s+(?P<file2>\S+))?$", re.MULTILINE)

def get_revisions(old, new):
    git = subprocess.Popen(['git', 'rev-list', '--pretty=medium', '%s..%s' % (old, new)], stdout=subprocess.PIPE)
    sections = git.stdout.read().split('\n\n')[:-1]
    
    revisions = []
    s = 0
    while s < len(sections):
        lines = sections[s].split('\n')
        
        # first line is 'commit HASH\n'
        props = {'id': lines[0].strip().split(' ')[1], 'added': [], 'removed': [], 'modified': []}
        
        # call git diff-tree and get the file changes
        git_difftree = subprocess.Popen(['git', 'diff-tree', '-r', '-C', '%s' % props['id']], stdout=subprocess.PIPE)
        output = git_difftree.stdout.read()
        
        # sort the changes into the added/modified/removed lists
        for i in DIFF_TREE_RE.finditer(output):
            item = i.groupdict()
            if item['status'] == 'A':      # addition of a file
                props['added'].append(item['file1'])
            elif item['status'][0] == 'C': # copy of a file into a new one
                props['added'].append(item['file2'])
            elif item['status'] == 'D':    # deletion of a file
                props['removed'].append(item['file1'])
            elif item['status'] == 'M':    # modification of the contents or mode of a file
                props['modified'].append(item['file1'])
            elif item['status'][0] == 'R': # renaming of a file
                props['removed'].append(item['file1'])
                props['added'].append(item['file2'])
            elif item['status'] == 'T':    # change in the type of the file
                props['modified'].append(item['file1'])
            else: # Covers U (file is unmerged)
                  #    and X ("unknown" change type, usually an error)
                pass # When we get X, we do not know what actually happened so
                     # it's safest just to ignore it. We shouldn't be seeing U
                     # anyway, so we can ignore that too.
        
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
        m = EMAIL_RE.match(props['author'])
        if m:
            props['name'] = m.group(1)
            props['email'] = m.group(2)
        else:
            props['name'] = 'unknown'
            props['email'] = 'unknown'
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
                        'timestamp': r['date'],
                        'added': r['added'],
                        'removed': r['removed'],
                        'modified': r['modified']
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
