import sys

from flask import abort, current_app, request, url_for
from flask import _request_ctx_stack
from werkzeug.routing import BuildError
from wsgi_party import WSGIParty, HighAndDry


class Party(object):
    invite_path = '/__invite__/'

    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        partyline_proxy = PartylineProxy(app)
        app.extensions['party'] = partyline_proxy
        app.add_url_rule(self.invite_path, endpoint='partyline',
                         view_func=partyline_proxy.join_party)
        if not hasattr(app, 'build_error_handler'):
            raise RuntimeError('Requires Flask>=0.9 for build_error_handler.')
        app.build_error_handler = build_error_handler


class PartylineProxy(object):
    def __init__(self, app):
        self.app = app
        self.partyline = None
        self.connected = False

    def join_party(self, request=request):
        # Bootstrap, turn the view function into a 404 after registering.
        if self.connected:
            # This route does not exist at the HTTP level.
            abort(404)
        self.invitation_context = _request_ctx_stack.top
        self.invitation_context.use_partyline = False
        self.partyline = request.environ.get(WSGIParty.partyline_key)
        self.partyline.connect('ping', lambda x: 'pong')
        self.partyline.connect('url', self.handle_url)
        self.connected = True
        return 'ok'

    def handle_url(self, payload):
        endpoint, values = payload
        try:
            return self.my_url_for(endpoint, **values)
        except BuildError:
            raise HighAndDry()

    def my_url_for(self, endpoint, **values):
        try:
            # RequestContext.push() causes wrong context to be popped when app
            # preserves context on exception, the default for app.debug=True.
            # Instead, push/pop directly on the LocalStack.
            _request_ctx_stack.push(self.invitation_context)
            return url_for(endpoint, **values)
        finally:
            _request_ctx_stack.pop()


def build_error_handler(error, endpoint, **values):
    # Bootstrap. Prevent recursion into partyline when called from partyline.
    if not getattr(_request_ctx_stack.top, 'use_partyline', True):
        reraise_error(error)

    partyline_proxy = current_app.extensions.get('party')
    assert partyline_proxy is not None, 'Where did Flask-Party go?'

    for url in partyline_proxy.partyline.ask_around('url', (endpoint, values)):
        # First response wins.
        return url

    # Partyline does not have a URL for these arguments.
    reraise_error(error)


def reraise_error(error):
    exc_type, exc_value, tb = sys.exc_info()
    if exc_value is error:
        # exception is current, raise in context of original traceback.
        raise exc_type, exc_value, tb
    else:
        raise error
