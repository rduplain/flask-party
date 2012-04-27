import sys
import types

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
        patch_create_url_adapter(app)


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


def reraise_error(error):
    exc_type, exc_value, tb = sys.exc_info()
    if exc_value is error:
        # exception is current, raise in context of original traceback.
        raise exc_type, exc_value, tb
    else:
        raise error


def patch_create_url_adapter(app):
    original_create = app.create_url_adapter
    def create_partyline_url_adapter(self, request):
        adapter = original_create(request)
        if adapter is None:
            return None
        original_build = adapter.build
        def build_with_partyline(self, endpoint, values, method, force_external):
            partyline = app.extensions.get('party').partyline
            error = None
            method = values.pop('_method', method)
            force_external = values.pop('_external', force_external)
            try:
                urls = [original_build(endpoint, values, method=method, force_external=force_external)]
            except BuildError, e:
                urls = []
                error = e
            if not getattr(_request_ctx_stack.top, 'use_partyline', True):
                if error is not None:
                    reraise_error(error)
                else:
                    return urls[0]
            values['_method'] = method
            values['_external'] = force_external
            for url in partyline.ask_around('url', (endpoint, values)):
                urls.append(url)
            # Add a sort hook here.
            if not urls:
                reraise_error(error)
            return urls[0]
        adapter.build = types.MethodType(build_with_partyline, adapter)
        return adapter
    app.create_url_adapter = types.MethodType(create_partyline_url_adapter, app)
