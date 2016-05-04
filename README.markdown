# notify-webhook

notify-webhook is a [git](http://git.or.cz) post-receive hook script
that posts JSON data to a webhook capable server.

This implements the [GitHub](http://github.com) [Web hooks
API](http://github.com/guides/post-receive-hooks) as closely as
possible.  It allows arbitrary git repositories to use webhook
capable services.

As an example, this script works very well with
[commitbot](http://github.com/metajack/commitbot/tree/master) which
sends commit notifications to XMPP group chat rooms.

## Dependencies

* [simplejson](http://pypi.python.org/pypi/simplejson)

## Usage
### Installation & Configuration (manual)

To use notify-webhook, just copy `notify-webhook.py` to your
repository's `.git/hooks` dir and call it `post-receive`. Be sure to
set it executable with `chmod 755 post-receive` as well.

Configuration is handled through `git config`. We use sensible defaults
where possible.

Configuration example:

    git config meta.url "http://example.com"
    git config hooks.webhookurl "http://example.net"

### Installation & Configuration (Gitolite)
Please see the installation details at [Gitolite repo-specific hooks](http://gitolite.com/gitolite/non-core.html#rsh).

Configuration example:

    repo some-repo-in-gitolite
	  option hook.post-receive = notify-webhook
	  config meta.url "http://example.com"
      config hooks.webhookurl "http://example.net"

### Configuration Parameters

#### hooks.webhookurl
The URL to the webhook consumer - the commit details will be POSTed
here.

Defaults to `None` **which will echo the JSON data instead of sending
it** (unless the `hooks.webhookurls` configuration is set).

#### hooks.webhookurls

A list of URLs to different webhook consumers - the commit details will
be POSTed to each of them in the order they arrive (if hooks.webhookurl
is set, the commit details will be POSTed to that URL first).

The value is parsed like a csv file so each URL is separated by a comma
or a newline (or a combination of the two). URLs with a comma in them
can be wrapped in quotation marks.

An example of value with two URLS:

    git config hooks.webhookurls 'http://example.com/hook,"http://other.example.com/hook,with,comma"'

Defaults to `None` **which will echo the JSON data instead of sending
it** (unless the `hooks.webhookurl` configuration is set).

#### meta.ownername / meta.owneremail
Details about the repository owner.

Defaults the `gitweb.owner` variable, and falls back to author details on the
initial commit to the repository.

#### meta.reponame
The name of the repository.

Defaults to the repository name as determined by its path.

#### meta.description
Description of the repo.

Defaults to the `gitweb.description` config variable, and falls back to the contents of
the `description` file. This behavior is intended to be compatible with GitWeb.

#### meta.url
The URL of your repository browser

Defaults to `None`

#### meta.commiturl
The URL of a commit in your repository browser. `%s` is replaced with
the SHA1 hash of the commit.
Defaults to `meta.url+'/commit/%s'` or `None`

#### meta.compareurl
The URL of a diff in your repository browser. Must contain two `%s` elements.
Defaults to `meta.url+'/compare/%s..%s'` or `None`

#### hooks.authuser
Username to use for basic and digest authentication.

Defaults to `None`

#### hooks.authpass
Password to use for basic and digest authentication.
Note that it is stored in plaintext in git's config file!

Defaults to `None`

#### hooks.authrealm
Realm to use for digest authentication.

Defaults to `None`

#### hooks.secrettoken
Secret token to use for [GitHub-compatible X-Hub-Signature header](https://developer.github.com/webhooks/securing/).

Defaults to `None`

#### hooks.webhook-contenttype
[Payload Content Type](https://developer.github.com/webhooks/creating/#content-type) to
use for the body of the data. Supported values are:
* `application/x-www-form-urlencoded` (default).
* `application/json`

## License

This code is copyright (c) 2008-2015 by Jack Moffitt <jack@metajack.im> and
others; and is available under the [GPLv3](http://www.gnu.org/licenses/gpl.html).
See `LICENSE.txt` for details.
See `CONTRIBUTORS.markdown` for all authors.
