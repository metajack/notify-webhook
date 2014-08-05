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
`easy_install simplejson || sudo easy_install simplejson`

## Usage

To use notify-webhook, just copy `notify-webhook.py` to your
repository's `.git/hooks` dir and call it `post-receive`. Be sure to
set it executable with `chmod 755 post-receive` as well.

### Configuration

Configuration is handled through `git config`. We use sensible defaults
where possible.

Here's an example:

    git config meta.url "http://example.com"
    git config hooks.webhookurl "http://example.net"

#### hooks.webhookurl
The URL to the webhook consumer - the commit details will be POSTed
here.

Defaults to `None` **which will echo the JSON data instead of sending
it**.

#### meta.ownername / meta.owneremail
Details about the repository owner.

Defaults to the first commit's author's details.

#### meta.reponame
The name of the repository.

Defaults to the repository name as determined by its path.

#### meta.url
The URL of your repository browser

Defaults to `None`

#### meta.commiturl
The URL of a commit in your repository browser. `%s` is replaced with
the SHA1 hash of the commit.  
Defaults to `meta.url+'/commit/%s'` or `None`

#### meta.description
Description of the repo.

Defaults to the contents of the "description" file.

#### hooks.authuser
Username to use for basic authentication.

#### hooks.authpass
Password to use for basic authentication.

## License

This code is copyright (c) 2008 by Jack Moffitt <jack@metajack.im> and
is available under the [GPLv3](http://www.gnu.org/licenses/gpl.html).
See `LICENSE.txt` for details.
