"""Hermetic regression: OAuth callback error pages must HTML-escape the
client-controlled `error` / `error_description` query parameters they
render. These params are set by the remote provider redirect, but the
values ultimately originate from the request the client controls, and
every other field on these pages is server-generated - so a crafted
callback URL is a reflected-XSS vector on an unauthenticated route.

Covers:
  plugins/omi-dropbox-app/main.py  auth_callback   <p>{error_description or error}</p>
  plugins/omi-ms365-app/main.py    auth_callback   <pre>{error}: {error_description}</pre>
  plugins/omi-notion-app/main.py   notion_callback <p>{error}</p>

Reuses the AST-driven loader from test_uid_reflection_remaining_apps.

Run: python3 plugins/test_oauth_error_params_escaped.py
"""

import asyncio
import ast
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

# standalone harness: AST-driven per-app import stubbing (same loader as
# test_uid_reflection_remaining_apps; kept inline so each manifest command
# is a self-contained script)
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
            f"{app_dir.replace('-', '_')}_oauth_error_under_test", main_path
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


HOSTILE = '<script>alert(1)</script> & "quoted"'


def test_dropbox_callback_escapes_error_params():
    module = load_app('omi-dropbox-app')
    html = asyncio.run(module.auth_callback(
        code=None, state=None, error='boom', error_description=HOSTILE))
    assert isinstance(html, str) and 'Authorization Failed' in html
    assert '<script>' not in html, 'dropbox: script reflected raw'
    assert '&lt;script&gt;' in html, 'dropbox: error_description not html-escaped'
    assert '&quot;quoted&quot;' in html, 'dropbox: quote not escaped'


def test_ms365_callback_escapes_error_params():
    module = load_app('omi-ms365-app')
    html = asyncio.run(module.auth_callback(code=None, state=None, error=HOSTILE))
    assert isinstance(html, str) and 'Authorization failed' in html
    assert '<script>' not in html, 'ms365: script reflected raw'
    assert '&lt;script&gt;' in html, 'ms365: error not html-escaped'
    assert '&amp;' in html, 'ms365: ampersand not escaped'


def test_notion_callback_escapes_error_param():
    module = load_app('omi-notion-app')
    html = asyncio.run(module.notion_callback(
        code=None, state=None, error=HOSTILE))
    assert isinstance(html, str) and 'Authorization Failed' in html
    assert '<script>' not in html, 'notion: script reflected raw'
    assert '&lt;script&gt;' in html, 'notion: error not html-escaped'


if __name__ == '__main__':
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
