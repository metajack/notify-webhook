#!/usr/bin/env python3

import os
import re
import subprocess
import sys
import hmac
import hashlib
from datetime import datetime
from collections import OrderedDict

import urllib.error
import urllib.parse
import urllib.request
import simplejson as json

EMAIL_RE = re.compile(r"^(\"?)(?P<name>.*)\1\s+<(?P<email>.*)>$")

# see git-diff-tree 'RAW OUTPUT FORMAT'
# https://git-scm.com/docs/git-diff-tree#_raw_output_format
DIFF_TREE_RE = re.compile(r" \
        ^: \
          (?P<src_mode>[0-9]{6}) \
          \s+ \
          (?P<dst_mode>[0-9]{6}) \
          \s+ \
          (?P<src_hash>[0-9a-f]{7,40}) \
          \s+ \
          (?P<dst_hash>[0-9a-f]{7,40}) \
          \s+ \
          (?P<status>[ADTUX]|[CR][0-9]{1,3}|M[0-9]{0,3}) \
          \s+ \
          (?P<file1>\S+) \
          (?:\s+ \
            (?P<file2>\S+) \
          )? \
        $", re.MULTILINE | re.VERBOSE)

EMPTY_TREE_HASH = '4b825dc642cb6eb9a060e54bf8d69288fbee4904'

def git(args):
    args = ['git'] + args
    cmd = subprocess.Popen(args, stdout=subprocess.PIPE)
    details = cmd.stdout.read()
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

    # Fallback:
    return os.path.basename(os.getcwd())

def get_repo_description():
    description = get_config('meta.description')
    if description:
        return description

    description = get_config('gitweb.description')
    if description:
        return description

    if os.path.exists('description'):
        with open('description', 'r') as fp:
            return fp.read()

    return ''


def extract_name_email(s):
    p = EMAIL_RE
    _ = p.search(s.strip())
    if not _:
        return (None, None)
    name = (_.group('name') or '').strip()
    email = (_.group('email') or '').strip()
    return (name, email)

def get_repo_owner():
    # Explicit keys
    repo_owner_name = get_config('meta.ownername')
    repo_owner_email = get_config('meta.owneremail')
    # Fallback to gitweb
    gitweb_owner = get_config('gitweb.owner')
    if gitweb_owner is not None and repo_owner_name is None and repo_owner_email is None:
        (name, email) = extract_name_email(gitweb_owner)
        if name is not None:
            repo_owner_name = name
        if email is not None:
            repo_owner_email = email
    # Fallback to the repo
    if repo_owner_name is None or repo_owner_email is None:
        # You cannot include -n1 because it is processed before --reverse
        logmsg = git(['log', '--reverse', '--format=%an%x09%ae']).split("\n")[0]
        # These will never be null
        (name, email) = logmsg.split("\t")
        if repo_owner_name is None:
            repo_owner_name = name
        if repo_owner_email is None:
            repo_owner_email = email

    return (repo_owner_name, repo_owner_email)

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
REPO_DESC = get_repo_description()
(REPO_OWNER_NAME, REPO_OWNER_EMAIL) = get_repo_owner()

def get_revisions(old, new, head_commit=False):
    if re.match(r"^0+$", old):
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
    CURR_BRANCH_RE = re.compile(r'^\* \w+$')
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

    # Fallback
    return base_ref

# http://stackoverflow.com/a/20559031
def purify(obj):
    if hasattr(obj, 'items'):
        newobj = type(obj)()
        for k in obj:
            if k is not None and obj[k] is not None:
                newobj[k] = purify(obj[k])
    elif hasattr(obj, '__iter__'):
        newobj = []
        for k in obj:
            if k is not None:
                newobj.append(purify(k))
    else:
        return obj
    return type(obj)(newobj)

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

def post_encode_data(contenttype, rawdata):
    if contenttype == 'application/json':
        return rawdata.encode('UTF-8')
    if contenttype == 'application/x-www-form-urlencoded':
        return urllib.parse.urlencode({'payload': rawdata}).encode('UTF-8')

    assert False, "Unsupported data encoding"
    return None

def post(url, data):
    headers = {
        'Content-Type': POST_CONTENTTYPE,
        'X-GitHub-Event': 'push',
    }
    postdata = post_encode_data(POST_CONTENTTYPE, data)

    if POST_SECRET_TOKEN is not None:
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
            urls.extend(re.split(r',\s*', POST_URLS))
        for url in urls:
            post(url.strip(), data)

if __name__ == '__main__':
    main(sys.stdin)
