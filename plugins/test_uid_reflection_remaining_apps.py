"""Hermetic regression: the remaining plugin apps reflect the client-controlled
`uid` query parameter into HTML attributes and redirect URLs unencoded.

Precedent: PR #13658 encoded six apps; #14350 covered omi-twitter-app. This
suite pins the rest (issue class: FC-client-param-reflected-into-html-markup):

  app                site driven                        context
  omi-dropbox-app    GET / (both branches), GET /disconnect   form action, hrefs, redirect
  omi-google-calendar-app  GET / (unconnected), GET /disconnect, POST /update-calendar, callback error page
  omi-hive-app       POST /disconnect/hive                   redirect
  omi-ms365-app      GET /setup/microsoft                    redirect target
  omi-shipbob-app    GET /disconnect/shipbob                 redirect
  omi-shopify-app    GET /disconnect/shopify                 redirect
  omi-linear-app     GET /, GET /disconnect/linear           JSON oauth_url, redirect

A uid containing a double quote breaks out of an HTML attribute (reflected
XSS); a bare `&` or `#` corrupts the query handed to the next hop.

The loader AST-parses each app's imports and stubs every non-stdlib module
permissively (db seams return MagicMocks; tests patch the specific
dependency the driven handler reads). No network, no disk writes.

Run: python3 plugins/test_uid_reflection_remaining_apps.py
"""

import asyncio
import ast
import importlib.util
import sys
import types
from pathlib import Path
from unittest import mock

PLUGINS_DIR = Path(__file__).resolve().parent

STDLIB = {
    'os', 'sys', 'json', 're', 'base64', 'secrets', 'struct', 'wave', 'io',
    'datetime', 'typing', 'pathlib', 'collections', 'urllib', 'tempfile',
    'logging', 'traceback', 'time', 'hashlib', 'hmac', 'functools',
    'itertools', 'math', 'uuid', 'asyncio', 'contextlib', 'random',
    'textwrap', 'copy', 'enum', 'abc', 'email', 'stat', 'html', 'html.parser',
    'shutil', 'zipfile', 'csv', 'sqlite3', 'threading', 'subprocess', 'glob',
    'mimetypes', 'operator', 'weakref', 'types', 'string', 'numbers',
    'decimal', 'fractions', 'calendar', 'zoneinfo', 'ipaddress', 'socket',
    'ssl', 'http', 'xml', 'platform', 'getpass', 'signal', 'inspect',
    'dataclasses', 'warnings', 'errno', 'unicodedata',
}

HOSTILE_UID = 'x" onmouseover="alert(1)&admin=1'


def _decorator(*args, **kwargs):
    return lambda fn: fn


def _permissive(name):
    module = types.ModuleType(name)

    def _missing(attr):
        return mock.MagicMock(name=f"{name}.{attr}")

    module.__getattr__ = _missing
    return module


def _stub_modules_for(app_main: Path):
    """Parse the app's imports; return stub modules for every non-stdlib name."""
    tree = ast.parse(app_main.read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split('.')[0])
    stubs = {}

    def add(name):
        if name in stubs:
            return
        if name == 'urllib':
            # real urllib is fine; submodules resolve against it
            return
        if name in STDLIB:
            return
        stubs[name] = _permissive(name)

    for name in names:
        add(name)

    # framework + storage seams the apps all share
    fastapi = types.ModuleType('fastapi')

    class _FastAPI:
        def __init__(self, *a, **k):
            pass

        get = staticmethod(_decorator)
        post = staticmethod(_decorator)
        on_event = staticmethod(_decorator)
        websocket = staticmethod(_decorator)
        mount = staticmethod(lambda *a, **k: None)
        exception_handler = staticmethod(_decorator)
        middleware = staticmethod(_decorator)

    fastapi.FastAPI = _FastAPI
    fastapi.Request = object
    fastapi.Query = lambda default=None, **kw: default
    fastapi.Depends = lambda *a, **k: None
    fastapi.Form = lambda default=None, **kw: default
    fastapi.HTTPException = type('HTTPException', (Exception,), {'status_code': 500, 'detail': ''})
    responses = types.ModuleType('fastapi.responses')
    responses.HTMLResponse = lambda content=None, **kw: content
    responses.JSONResponse = lambda content=None, **kw: content
    responses.RedirectResponse = lambda url=None, **kw: types.SimpleNamespace(url=url, status_code=kw.get('status_code'))
    fastapi.responses = responses
    templating = types.ModuleType('fastapi.templating')
    templating.Jinja2Templates = lambda *a, **k: mock.MagicMock()
    staticfiles = types.ModuleType('fastapi.staticfiles')
    staticfiles.StaticFiles = lambda *a, **k: None
    stubs.update({
        'fastapi': fastapi,
        'fastapi.responses': responses,
        'fastapi.templating': templating,
        'fastapi.staticfiles': staticfiles,
        'dotenv': types.ModuleType('dotenv'),
        'urllib_parse': None,  # placeholder, never used
    })
    stubs.pop('urllib_parse')
    exceptions = types.ModuleType('fastapi.exceptions')
    exceptions.RequestValidationError = type('RequestValidationError', (Exception,), {})
    stubs['fastapi.exceptions'] = exceptions
    stubs['dotenv'].load_dotenv = lambda *a, **k: None
    return stubs


def load_app(app_dir: str):
    main_path = PLUGINS_DIR / app_dir / 'main.py'
    stubs = _stub_modules_for(main_path)
    plugin_dir = str(PLUGINS_DIR / app_dir)
    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)
    with mock.patch.dict(sys.modules, stubs), \
            mock.patch('logging.basicConfig'), \
            mock.patch('logging.getLogger', return_value=mock.MagicMock()):
        spec = importlib.util.spec_from_file_location(
            f"{app_dir.replace('-', '_')}_reflection_under_test", main_path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def assert_encoded(value, label):
    """The reflected value must not survive raw: quotes broken out or &/# injected."""
    assert '" onmouseover=' not in value, f"{label}: attribute injection survived"
    assert '&admin=1' not in value, f"{label}: query param injection survived"
    assert '%22' in value, f"{label}: uid not percent-encoded"
    assert '%26' in value, f"{label}: ampersand not percent-encoded"


def test_dropbox_home_pages_encode_uid():
    module = load_app('omi-dropbox-app')
    hostile = HOSTILE_UID
    # connected branch renders the settings form action + disconnect href
    with mock.patch.object(module, 'get_dropbox_tokens', lambda uid: {'access_token': 't'}):
        html = asyncio.run(module.home(uid=hostile))
    assert_encoded(html, 'dropbox connected page')
    assert 'action="/settings?uid=' in html
    # unconnected branch renders the connect href
    with mock.patch.object(module, 'get_dropbox_tokens', lambda uid: None):
        html = asyncio.run(module.home(uid=hostile))
    assert_encoded(html, 'dropbox connect page')


def test_dropbox_disconnect_redirect_encodes_uid():
    module = load_app('omi-dropbox-app')
    deleted = []
    module.delete_dropbox_tokens = lambda uid: deleted.append(uid)
    response = asyncio.run(module.disconnect(uid=HOSTILE_UID))
    assert_encoded(response.url, 'dropbox disconnect redirect')


def test_gcal_pages_encode_uid():
    module = load_app('omi-google-calendar-app')
    with mock.patch.object(module, 'get_google_tokens', lambda uid: None):
        html = asyncio.run(module.root(uid=HOSTILE_UID))
    assert_encoded(html, 'gcal connect page')
    assert '/auth/google?uid=' in html

    module.delete_google_tokens = lambda uid: None
    response = asyncio.run(module.disconnect(uid=HOSTILE_UID))
    assert_encoded(response.url, 'gcal disconnect redirect')

    async def fake_form():
        return {'uid': HOSTILE_UID, 'calendar_id': 'cal-1'}

    response = asyncio.run(module.update_calendar(
        request=types.SimpleNamespace(form=fake_form)))
    assert_encoded(response.url, 'gcal update-calendar redirect')


def test_gcal_callback_error_page_escapes_error():
    module = load_app('omi-google-calendar-app')
    html = asyncio.run(module.google_callback(code=None, state=None, error='<b>oops</b> & things'))
    assert '<b>oops</b>' not in html, 'client-controlled error reflected raw'
    assert '&lt;b&gt;oops&lt;/b&gt;' in html, 'error not html-escaped'


def test_hive_disconnect_redirect_encodes_uid():
    module = load_app('omi-hive-app')
    module.delete_hive_api_key = lambda uid: True
    response = asyncio.run(module.disconnect_hive(uid=HOSTILE_UID))
    assert_encoded(response.url, 'hive disconnect redirect')


def test_ms365_setup_redirect_encodes_uid():
    module = load_app('omi-ms365-app')
    module.get_ms365_tokens = lambda uid: None
    html = asyncio.run(module.setup_page(uid=HOSTILE_UID))
    # the handler returns the HTML page directly; the connect link must
    # carry the encoded uid
    assert isinstance(html, str)
    assert_encoded(html, 'ms365 setup page')


def test_shipbob_disconnect_redirect_encodes_uid():
    module = load_app('omi-shipbob-app')
    module.delete_shipbob_tokens = lambda uid: True
    response = asyncio.run(module.disconnect_shipbob(uid=HOSTILE_UID))
    assert_encoded(response.url, 'shipbob disconnect redirect')


def test_shopify_disconnect_redirect_encodes_uid():
    module = load_app('omi-shopify-app')
    module.delete_shopify_tokens = lambda uid: True
    response = asyncio.run(module.disconnect_shopify(uid=HOSTILE_UID))
    assert_encoded(response.url, 'shopify disconnect redirect')


def test_linear_pages_encode_uid():
    module = load_app('omi-linear-app')

    captured = {}

    class FakeTemplates:
        def TemplateResponse(self, name, ctx):
            captured['context'] = ctx
            return types.SimpleNamespace(template=name, context=ctx)

    module.templates = FakeTemplates()

    async def fake_json():
        return {}

    asyncio.run(module.home(request=types.SimpleNamespace(json=fake_json), uid=HOSTILE_UID))
    oauth_url = captured['context']['oauth_url']
    assert_encoded(oauth_url, 'linear home oauth_url')

    module.delete_linear_tokens = lambda uid: True
    response = asyncio.run(module.disconnect_linear(uid=HOSTILE_UID))
    assert_encoded(response.url, 'linear disconnect redirect')


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
