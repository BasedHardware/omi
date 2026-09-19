"""Hermetic regression: OAuth callback failure pages must HTML-escape the
dynamic strings they render — provider response bodies and exception
messages. These pages are HTMLResponses, so raw provider text or an
exception message that embeds a crafted URL executes in the browser;
the same class as the uid/error reflections fixed in #14350, #13658,
and the sibling suites.

Covers:
  omi-dropbox-app              token-exchange failure (response.text) + exception path
  omi-google-calendar-app      exception path
  omi-twitter-chat-tools-app   token-exchange failure (response.text) + exception path
  omi-whoop-app                exception path

Run: python3 plugins/test_callback_error_pages_escaped.py
"""

import asyncio
import ast
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

PLUGINS_DIR = Path(__file__).resolve().parent

STDLIB = {
    'os', 'sys', 'json', 're', 'base64', 'secrets', 'struct', 'wave', 'io',
    'datetime', 'typing', 'pathlib', 'collections', 'urllib', 'tempfile',
    'logging', 'traceback', 'time', 'hashlib', 'hmac', 'functools',
    'itertools', 'math', 'uuid', 'asyncio', 'contextlib', 'random',
    'textwrap', 'copy', 'enum', 'abc', 'email', 'stat', 'html', 'shutil',
    'zipfile', 'csv', 'sqlite3', 'threading', 'subprocess', 'types',
}

HOSTILE = '<script>alert(1)</script> & "quoted"'


def _decorator(*args, **kwargs):
    return lambda fn: fn


def _permissive(name):
    module = types.ModuleType(name)

    def _missing(attr):
        return mock.MagicMock(name=f"{name}.{attr}")

    module.__getattr__ = _missing
    return module


def _stub_modules_for(app_main: Path):
    tree = ast.parse(app_main.read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split('.')[0])
    stubs = {}
    for name in names:
        if name in STDLIB or name == 'urllib':
            continue
        stubs[name] = _permissive(name)

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
    exceptions = types.ModuleType('fastapi.exceptions')
    exceptions.RequestValidationError = type('RequestValidationError', (Exception,), {})
    stubs.update({
        'fastapi': fastapi,
        'fastapi.responses': responses,
        'fastapi.templating': templating,
        'fastapi.staticfiles': staticfiles,
        'fastapi.exceptions': exceptions,
        'dotenv': types.ModuleType('dotenv'),
    })
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
            f"{app_dir.replace('-', '_')}_error_strings_under_test", main_path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def fake_requests(status_code, text):
    response = SimpleNamespace(status_code=status_code, text=text)
    return SimpleNamespace(post=lambda *a, **k: response)


def assert_escaped(html, label):
    assert '<script>' not in html, f"{label}: raw script tag rendered"
    assert '&lt;script&gt;' in html, f"{label}: dynamic string not html-escaped"


def test_dropbox_token_exchange_failure_escapes_provider_body():
    module = load_app('omi-dropbox-app')
    module.get_oauth_state = lambda uid: 'u:tok'
    with mock.patch.object(module, 'requests', fake_requests(400, HOSTILE)):
        html = asyncio.run(module.auth_callback(
            code='c', state='u:tok', error=None, error_description=None))
    assert 'Token exchange failed' in html
    assert_escaped(html, 'dropbox token-exchange failure')


def test_dropbox_exception_path_escapes_message():
    module = load_app('omi-dropbox-app')
    module.get_oauth_state = lambda uid: 'u:tok'

    def boom(*a, **k):
        raise Exception(HOSTILE)

    with mock.patch.object(module, 'requests', SimpleNamespace(post=boom)):
        html = asyncio.run(module.auth_callback(
            code='c', state='u:tok', error=None, error_description=None))
    assert_escaped(html, 'dropbox exception path')


def test_gcal_exception_path_escapes_message():
    module = load_app('omi-google-calendar-app')
    module.get_oauth_state = lambda uid: 'u:tok'

    def boom(*a, **k):
        raise Exception(HOSTILE)

    with mock.patch.object(module, 'requests', SimpleNamespace(post=boom)):
        html = asyncio.run(module.google_callback(code='c', state='u:tok', error=None))
    assert_escaped(html, 'gcal exception path')


def test_twitter_chat_tools_token_exchange_failure_escapes_provider_body():
    module = load_app('omi-twitter-chat-tools-app')
    module.get_oauth_state = lambda uid: 'u:tok'
    with mock.patch.object(module, 'requests', fake_requests(400, HOSTILE)):
        html = asyncio.run(module.twitter_callback(code='c', state='u:tok', error=None))
    assert_escaped(html, 'twitter-chat-tools token-exchange failure')


def test_twitter_chat_tools_exception_path_escapes_message():
    module = load_app('omi-twitter-chat-tools-app')
    module.get_oauth_state = lambda uid: 'u:tok'

    def boom(*a, **k):
        raise Exception(HOSTILE)

    with mock.patch.object(module, 'requests', SimpleNamespace(post=boom)):
        html = asyncio.run(module.twitter_callback(code='c', state='u:tok', error=None))
    assert_escaped(html, 'twitter-chat-tools exception path')


def test_whoop_exception_path_escapes_message():
    module = load_app('omi-whoop-app')
    module.get_uid_from_oauth_state = lambda state: 'uid1'

    def boom(*a, **k):
        raise Exception(HOSTILE)

    with mock.patch.object(module, 'requests', SimpleNamespace(post=boom)):
        html = asyncio.run(module.whoop_callback(code='c', state='u:tok', error=None))
    assert_escaped(html, 'whoop exception path')


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
