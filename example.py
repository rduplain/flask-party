from flask import Flask, url_for
from werkzeug.wsgi import DispatcherMiddleware
from wsgi_party import WSGIParty

from flask_party import Party


root = Flask(__name__)
one = Flask(__name__)
two = Flask(__name__)
three = Flask(__name__) # Add a non-partyline application.

party = Party()
party.init_app(root)
party.init_app(one)
party.init_app(two)

root.debug = True
one.debug = True
two.debug = True
three.debug = True

template = """
<html>
<head>
  <title>Demo: Cross-application URL building in Flask.</title>
</head>
<body>
  <p>You are in the root application.</p>
  <ul>
    <li><a href="%s">Go to application one</a></li>
    <li><a href="%s">Go to application two</a></li>
  </ul>
</body>
</html>
"""

@root.route('/', endpoint='index')
def root_index():
    return template % (url_for('one:index'), url_for('two:index'))

@one.route('/', endpoint='one:index')
def one_index():
    url = url_for('two:index')
    return 'This is app one. <a href="%s">Go to two.</a>' % url

@two.route('/', endpoint='two:index')
def two_index():
    url = url_for('one:index')
    return 'This is app two. <a href="%s">Go to one.</a>' % url

@three.route('/', endpoint='three:index')
def three_index():
    return 'I do not participate in parties.'


invite_path = party.invite_path
application = WSGIParty(DispatcherMiddleware(root, {
    '/one': one,
    '/two': two,
    '/three': three,
}), invites=(invite_path, '/one/'+invite_path, '/two/'+invite_path))


if __name__ == '__main__':
    import os
    from werkzeug.serving import run_simple
    # Bind to PORT if defined, otherwise default to 5000.
    port = int(os.environ.get('PORT', 5000))
    run_simple('0.0.0.0', port, application, use_reloader=True)
