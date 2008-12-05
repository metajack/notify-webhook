# notify-webhook

notify-webhook is a [git](http://git.or.cz) post-receive hook script
that posts JSON data to a web hook capable server.

This implements the [GitHub](http://github.com) [Web hooks
API](http://github.com/guides/post-receive-hooks) as closely as
possible.  It allows arbitrary git repositories to use Web hook
capable services.

## License

This code is copyright (c) 2008 by Jack Moffitt <jack@metajack.im> and
is available under the [GPLv3](http://www.gnu.org/licenses/gpl.html).
See `LICENSE.txt` for details.

## Dependencies

* [simplejson](http://pypi.python.org/pypi/simplejson)

## Usage

To use notify-webhook, just copy `notify-webhook.py` to your
repository's `.git/hooks` dir and call it `post-receive`. Be sure to
set it executable with `chmod 755 post-receive` as well.

You'll need to edit the very top of the file where the constants are
defined.  

* `POST_URL` is the URL of the web hook server
* `REPO_URL` is the URL of your repository browser
* `COMMIT_URL` is the URL of a commit in your respository browser.
  '%s' in this string will be replaced with the SHA1 hash.
* `REPO_NAME` is the name of the repository
* `REPO_OWNER_NAME` is name of the repository owner
* `REPO_OWNER_EMAIL` is the repository owner's e-mail address
* `REPO_DESC` is the repository description
