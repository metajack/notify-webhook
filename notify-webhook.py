#!/usr/bin/env python3

import sys
import urllib.request, urllib.parse, urllib.error
import re
import os
import subprocess
import csv
import io
from datetime import datetime
import simplejson as json
from itertools import chain, repeat
from collections import OrderedDict

EMAIL_RE = re.compile("^\"?(.*)\"? <(.*)>$")
DIFF_TREE_RE = re.compile("^:(?P<src_mode>[0-9]{6}) (?P<dst_mode>[0-9]{6}) (?P<src_hash>[0-9a-f]{7,40}) (?P<dst_hash>[0-9a-f]{7,40}) (?P<status>[ADMTUX]|[CR][0-9]{1,3})\s+(?P<file1>\S+)(?:\s+(?P<file2>\S+))?$", re.MULTILINE)
EMPTY_TREE_HASH = '4b825dc642cb6eb9a060e54bf8d69288fbee4904'

def git(args):
    args = ['git'] + args
    git = subprocess.Popen(args, stdout = subprocess.PIPE)
    details = git.stdout.read()
    details = details.decode('utf-8', 'replace').strip()
    return details

def _git_config():
    raw_config = git(['config', '-l', '-z'])
    items = raw_config.split("\0")
    # remove empty items
    items = filter(lambda i: len(i) > 0, items)
    # split into key/value based on FIRST \n; allow embedded \n in values
    items = [item.partition("\n")[0:3:2] for item in items]
    return OrderedDict(items)

GIT_CONFIG = _git_config()

def get_config(key, default=None):
    return GIT_CONFIG.get(key, default)

def get_repo_name():
    if get_config('core.bare', 'false') == 'true':
        name = os.path.basename(os.getcwd())
        if name.endswith('.git'):
            name = name[:-4]
        return name
    else:
        return os.path.basename(os.path.dirname(os.getcwd()))

def extract_name_email(s):
    p = re.compile(EMAIL_RE)
    _ = p.search(s.strip())
    if _ is None:
        return (None, None)
    name = _.group(1)
    if name is not None:
        name = name.strip()
        if len(name) <= 0:
            name = None
    email = _.group(2)
    if email is not None:
        email = email.strip()
        if len(email) <= 0:
            email = None
    return (name, email)

POST_URL = get_config('hooks.webhookurl')
POST_URLS = get_config('hooks.webhookurls')
POST_USER = get_config('hooks.authuser')
POST_PASS = get_config('hooks.authpass')
POST_REALM = get_config('hooks.authrealm')
POST_SECRET_TOKEN = get_config('hooks.secrettoken')
POST_CONTENTTYPE = get_config('hooks.webhook-contenttype', 'application/x-www-form-urlencoded')
POST_TIMEOUT = get_config('hooks.timeout')
DEBUG = get_config('hooks.webhook-debug')
REPO_URL = get_config('meta.url')
COMMIT_URL = get_config('meta.commiturl')
COMPARE_URL = get_config('meta.compareurl')
if COMMIT_URL is None and REPO_URL is not None:
    COMMIT_URL = REPO_URL + r'/commit/%s'
if COMPARE_URL is None and REPO_URL is not None:
    COMPARE_URL = REPO_URL + r'/compare/%s..%s'
REPO_NAME = get_repo_name()
REPO_DESC = ""
try:
    REPO_DESC = get_config('meta.description') or get_config('gitweb.description') or open('description', 'r').read()
except Exception:
    pass

# Explicit keys
REPO_OWNER_NAME = get_config('meta.ownername')
REPO_OWNER_EMAIL = get_config('meta.owneremail')
# Fallback to gitweb
gitweb_owner = get_config('gitweb.owner')
if gitweb_owner is not None and REPO_OWNER_NAME is None and REPO_OWNER_EMAIL is None:
    (name, email) = extract_name_email(gitweb_owner)
    if name is not None:
        REPO_OWNER_NAME = name
    if email is not None:
        REPO_OWNER_EMAIL = email
# Fallback to the repo
if REPO_OWNER_NAME is None or REPO_OWNER_EMAIL is None:
    # You cannot include -n1 because it is processed before --reverse
    logmsg = git(['log','--reverse','--format=%an%x09%ae']).split("\n")[0]
    # These will never be null
    (name, email) = logmsg.split("\t")
    if REPO_OWNER_NAME is None:
        REPO_OWNER_NAME = name
    if REPO_OWNER_EMAIL is None:
        REPO_OWNER_EMAIL = email

def get_revisions(old, new, head_commit=False):
    if re.match("^0+$", old):
        if not head_commit:
            return []

        commit_range = '%s..%s' % (EMPTY_TREE_HASH, new)
    else:
        commit_range = '%s..%s' % (old, new)

    revs = git(['rev-list', '--pretty=medium', '--reverse', commit_range])
    sections = revs.split('\n\n')

    revisions = []
    s = 0
    while s < len(sections):
        lines = sections[s].split('\n')

        # first line is 'commit HASH\n'
        props = {'id': lines[0].strip().split(' ')[1], 'added': [], 'removed': [], 'modified': []}

        # call git diff-tree and get the file changes
        output = git(['diff-tree', '-r', '-C', '%s' % props['id']])

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
        # Strip leading tabs/4-spaces on the message
        props['message'] = re.sub(r'^(\t| {4})', '', sections[s+1], 0, re.MULTILINE)

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

# http://stackoverflow.com/a/20559031
def purify(o):
    if hasattr(o, 'items'):
        oo = type(o)()
        for k in o:
            if k != None and o[k] != None:
                oo[k] = purify(o[k])
    elif hasattr(o, '__iter__'):
        oo = []
        for it in o:
            if it != None:
                oo.append(purify(it))
    else: return o
    return type(o)(oo)

def make_json(old, new, ref):
    # Lots more fields could be added
    # https://developer.github.com/v3/activity/events/types/#pushevent
    compareurl = None
    if COMPARE_URL is not None: compareurl = COMPARE_URL % (old, new)

    data = {
        'before': old,
        'after': new,
        'ref': ref,
        'compare': compareurl,
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
        if COMMIT_URL is not None:
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
    data['size'] = len(commits)
    data['head_commit'] = get_revisions(old, new, True)

    base_ref = get_base_ref(new, ref)
    if base_ref:
        data['base_ref'] = base_ref

    return json.dumps(data)

def post(url, data):
    headers = {
        'Content-Type': POST_CONTENTTYPE,
        'X-GitHub-Event': 'push',
    }
    if POST_CONTENTTYPE == 'application/json':
        postdata = data.encode('UTF-8')
    elif POST_CONTENTTYPE == 'application/x-www-form-urlencoded':
        postdata = urllib.parse.urlencode({'payload': data}).encode('UTF-8')
    if POST_SECRET_TOKEN is not None:
        import hmac
        import hashlib
        hmacobj = hmac.new(POST_SECRET_TOKEN, postdata, hashlib.sha1)
        signature = 'sha1=' + hmacobj.hexdigest()
        headers['X-Hub-Signature'] = signature

    request = urllib.request.Request(url, postdata, headers)

    # Default handler
    handler = urllib.request.HTTPHandler
    # Override handler for passwords
    if POST_USER is not None or POST_PASS is not None:
        password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        password_mgr.add_password(POST_REALM, url, POST_USER, POST_PASS)
        handlerfunc = urllib.request.HTTPBasicAuthHandler
        if POST_REALM is not None:
            handlerfunc = urllib.request.HTTPDigestAuthHandler
        handler = handlerfunc(password_mgr)

    opener = urllib.request.build_opener(handler)

    try:
        if POST_TIMEOUT is not None:
            u = opener.open(request, None, float(POST_TIMEOUT))
        else:
            u = opener.open(request)
        u.read()
        u.close()
    except urllib.error.HTTPError as error:
        errmsg = "POST to %s returned error code %s." % (url, str(error.code))
        print(errmsg, file=sys.stderr)

def main(lines):
    for line in lines:
        old, new, ref = line.strip().split(' ')
        data = make_json(old, new, ref)
        if DEBUG:
            print(data)
        urls = []
        if POST_URL:
            urls.append(POST_URL)
        if POST_URLS:
            urls = io.StringIO(POST_URLS)
            urls.extend(csv.reader(urls))
        if urls:
            for url in urls:
                post(url.strip(), data)

if __name__ == '__main__':
    main(sys.stdin)
