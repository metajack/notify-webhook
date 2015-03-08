#!/usr/bin/env python

import sys
import urllib, urllib2
import re
import os
import subprocess
from datetime import datetime
import simplejson as json

def git(args):
    args = ['git'] + args
    git = subprocess.Popen(args, stdout = subprocess.PIPE)
    details = git.stdout.read()
    details = details.strip()
    return details

def get_config(key, default=None):
    details = git(['config', '%s' % (key)])
    if len(details) > 0:
        return details
    else:
        return default

def get_repo_name():
    if git(['rev-parse','--is-bare-repository']) == 'true':
        name = os.path.basename(os.getcwd())
        if name.endswith('.git'):
            name = name[:-4]
        return name
    else:
        return os.path.basename(os.path.dirname(os.getcwd()))

POST_URL = get_config('hooks.webhookurl')
POST_USER = get_config('hooks.authuser')
POST_PASS = get_config('hooks.authpass')
POST_REALM = get_config('hooks.authrealm')
POST_CONTENTTYPE = get_config('hooks.webhook-contenttype', 'application/x-www-form-urlencoded')
REPO_URL = get_config('meta.url')
COMMIT_URL = get_config('meta.commiturl')
if COMMIT_URL == None and REPO_URL != None:
    COMMIT_URL = REPO_URL + r'/commit/%s'
REPO_NAME = get_repo_name()
REPO_DESC = ""
try:
    REPO_DESC = get_config('meta.description') or open('description', 'r').read()
except Exception:
    pass
REPO_OWNER_NAME = get_config('meta.ownername')
REPO_OWNER_EMAIL = get_config('meta.owneremail')
if REPO_OWNER_NAME is None:
    REPO_OWNER_NAME = git(['log','--reverse','--format=%an']).split("\n")[0]
if REPO_OWNER_EMAIL is None:
    REPO_OWNER_EMAIL = git(['log','--reverse','--format=%ae']).split("\n")[0]

EMAIL_RE = re.compile("^(.*) <(.*)>$")
DIFF_TREE_RE = re.compile("^:(?P<src_mode>[0-9]{6}) (?P<dst_mode>[0-9]{6}) (?P<src_hash>[0-9a-f]{7,40}) (?P<dst_hash>[0-9a-f]{7,40}) (?P<status>[ADMTUX]|[CR][0-9]{1,3})\s+(?P<file1>\S+)(?:\s+(?P<file2>\S+))?$", re.MULTILINE)

def get_revisions(old, new, head_commit=False):
    if re.match("^0+$", old):
        if not head_commit:
            return []

        commit_range = '%s~1..%s' % (new, new)
    else:
        commit_range = '%s..%s' % (old, new)
        
    git = subprocess.Popen(['git', 'rev-list', '--pretty=medium', '--reverse', commit_range], stdout=subprocess.PIPE)
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
            else:   # Covers U (file is unmerged)
                    # and X ("unknown" change type, usually an error)
                pass    # When we get X, we do not know what actually happened so
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

        if head_commit:
            return props

        revisions.append(props)
        s += 2

    return revisions

def get_base_ref(commit, ref):
    branches = git(['branch', '--contains', commit]).split('\n')
    CURR_BRANCH_RE = re.compile('^\* \w+$')
    curr_branch = None

    if len(branches) > 1:
        on_master = False
        for branch in branches:
            if CURR_BRANCH_RE.match(branch):
                curr_branch = branch.strip('* \n')
            elif branch.strip() == 'master':
                on_master = True

        if curr_branch is None and on_master:
            curr_branch = 'master'

    if curr_branch is None:
        curr_branch = branches[0].strip('* \n')

    base_ref = 'refs/heads/%s' % curr_branch

    if base_ref == ref:
        return None
    else:
        return base_ref

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
        url = None
        if COMMIT_URL != None:
            url = COMMIT_URL % r['id']
        commits.append({'id': r['id'],
                        'author': {'name': r['name'], 'email': r['email']},
                        'url': url,
                        'message': r['message'],
                        'timestamp': r['date'],
                        'added': r['added'],
                        'removed': r['removed'],
                        'modified': r['modified']
                        })
    data['commits'] = commits
    data['head_commit'] = get_revisions(old, new, True)

    base_ref = get_base_ref(new, ref)
    if base_ref:
        data['base_ref'] = base_ref

    return json.dumps(data)

def post(url, data):
    opener = urllib2.HTTPHandler
    if POST_CONTENTTYPE == 'application/json':
        request = urllib2.Request(url, data, {'Content-Type': 'application/json'})
    elif POST_CONTENTTYPE == 'application/x-www-form-urlencoded':
        request = urllib2.Request(url, urllib.urlencode({'payload': data}))
    if POST_USER is not None or POST_PASS is not None:
        password_mgr = urllib2.HTTPPasswordMgrWithDefaultRealm()
        password_mgr.add_password(POST_REALM, url, POST_USER, POST_PASS)
        handlerfunc = urllib2.HTTPBasicAuthHandler
        if POST_REALM is not None:
            handlerfunc = urllib2.HTTPDigestAuthHandler
        handler = handlerfunc(password_mgr)
        opener = urllib2.build_opener(handler)

    try:
        u = opener.open(request)
        u.read()
        u.close()
    except urllib2.HTTPError as error:
        print "POST to " + POST_URL + " returned error code " + str(error.code) + "."

if __name__ == '__main__':
    for line in sys.stdin.xreadlines():
        old, new, ref = line.strip().split(' ')
        data = make_json(old, new, ref)
        if POST_URL:
            post(POST_URL, data)
        else:
            print(data)


