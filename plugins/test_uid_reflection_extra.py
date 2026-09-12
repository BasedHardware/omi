"""Hermetic regression: client-controlled `uid`/`user_id` values were
interpolated raw into setup-page auth URLs, redirect Location headers, and an
outbound API query in three more plugins (linear, hive, manual-import). A `&`
or `#` in uid corrupted the query string (e.g. injecting an `error` param),
and the linear setup template rendered the raw value into href targets.

Run: python3 plugins/test_uid_reflection_extra.py
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from unittest import mock
from urllib.parse import quote

PLUGINS = Path(__file__).resolve().parent
HOSTILE_UID = 'x&error=injected#frag'
NORMAL_UID = "user_123"


def _decorator(*args, **kwargs):
    return lambda fn: fn


def _stub(name, **attrs):
    module = types.ModuleType(name)

    def _missing(attr):
        return mock.Mock(name=f"{name}.{attr}")

    module.__getattr__ = _missing
    module.__dict__.update(attrs)
    return module


class _Redirect:
    def __init__(self, url=None, status_code=None, **kw):
        self.url = url
        self.status_code = status_code


class _HTTPException(Exception):
    def __init__(self, status_code=None, detail=None, **kw):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _fastapi_stubs():
    """Stubs shared by the FastAPI plugins (linear, hive)."""
    fastapi = _stub(
        "fastapi",
        FastAPI=lambda *a, **k: mock.Mock(
            get=_decorator, post=_decorator, mount=lambda *a, **k: None,
            websocket=_decorator, on_event=lambda *a, **k: _decorator,
        ),
        HTTPException=_HTTPException,
        Request=object,
        Query=lambda default=None, **kw: default,
        Form=lambda default=None, **kw: default,
    )
    responses = _stub(
        "fastapi.responses",
        HTMLResponse=dict,
        RedirectResponse=_Redirect,
        JSONResponse=dict,
    )
    staticfiles = _stub("fastapi.staticfiles", StaticFiles=lambda *a, **k: None)
    templating = _stub(
        "fastapi.templating",
        Jinja2Templates=lambda *a, **k: types.SimpleNamespace(
            TemplateResponse=lambda template, ctx: types.SimpleNamespace(
                template=template, context=ctx
            )
        ),
    )
    return {
        "fastapi": fastapi,
        "fastapi.responses": responses,
        "fastapi.staticfiles": staticfiles,
        "fastapi.templating": templating,
        "dotenv": _stub("dotenv", load_dotenv=lambda *a, **k: None),
        "db": _stub("db"),
        "models": _stub("models", ChatToolResponse=dict),
        "requests": _stub("requests"),
    }


def _load(module_name, path, stubs):
    with mock.patch.dict(sys.modules, stubs):
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def _load_linear():
    return _load("linear_main_under_test", PLUGINS / "omi-linear-app" / "main.py", _fastapi_stubs())


def _load_hive():
    return _load("hive_main_under_test", PLUGINS / "omi-hive-app" / "main.py", _fastapi_stubs())


def _load_manual_import(recorded):
    """Stub flask/requests/openai so submit_memories runs its real path."""

    class _Flask:
        def __init__(self, *a, **k):
            pass

        route = staticmethod(_decorator)

    flask = _stub(
        "flask",
        Flask=_Flask,
        request=types.SimpleNamespace(json=None),
        jsonify=lambda obj=None, *a, **k: obj,
        send_from_directory=lambda *a, **k: None,
    )

    class _Resp:
        status_code = 200
        text = "ok"

        def json(self):
            return {}

    def _post(url, **kw):
        recorded.append(url)
        return _Resp()

    stubs = {
        "flask": flask,
        "requests": _stub("requests", post=_post),
        "openai": _stub("openai"),
        "httpx": _stub("httpx"),
        "dotenv": _stub("dotenv", load_dotenv=lambda *a, **k: None),
    }
    module = _load("manual_import_under_test", PLUGINS / "import" / "manual-import" / "app.py", stubs)
    return module, flask


def test_linear_setup_oauth_url_encodes_uid():
    module = _load_linear()
    with mock.patch.object(module, "get_linear_tokens", lambda uid: None):
        resp = asyncio.run(module.home(request=object(), uid=HOSTILE_UID))
    ctx = resp.context
    expected = f"/auth/linear?uid={quote(HOSTILE_UID, safe='')}"
    assert ctx["oauth_url"] == expected, ctx["oauth_url"]
    # the template must render the encoded value into the href targets
    template = (PLUGINS / "omi-linear-app" / "templates" / "setup.html").read_text()
    assert "uid={{ uid_q }}" in template
    assert "uid={{ uid }}" not in template


def test_linear_disconnect_redirect_encodes_uid():
    module = _load_linear()
    resp = asyncio.run(module.disconnect_linear(uid=HOSTILE_UID))
    assert resp.url == f"/?uid={quote(HOSTILE_UID, safe='')}", resp.url


def test_hive_redirects_encode_uid():
    module = _load_hive()
    with mock.patch.object(module, "verify_api_key", lambda key: None):
        resp = asyncio.run(module.connect_api_key(uid=HOSTILE_UID, api_key="bad"))
    assert resp.url.startswith(f"/?uid={quote(HOSTILE_UID, safe='')}&"), resp.url
    assert HOSTILE_UID not in resp.url

    resp = asyncio.run(module.disconnect_hive(uid=HOSTILE_UID))
    assert resp.url == f"/?uid={quote(HOSTILE_UID, safe='')}", resp.url


def test_manual_import_encodes_uid_in_api_query():
    recorded = []
    module, flask = _load_manual_import(recorded)
    flask.request.json = {
        "uid": HOSTILE_UID,
        "memories": ["a single memory that is well over twenty characters"],
        "use_ai": False,
    }
    module.submit_memories()
    assert recorded, "handler made no API call"
    for url in recorded:
        assert f"uid={quote(HOSTILE_UID, safe='')}" in url, url
        assert HOSTILE_UID not in url


def test_normal_uid_unchanged():
    module = _load_linear()
    resp = asyncio.run(module.disconnect_linear(uid=NORMAL_UID))
    assert resp.url == "/?uid=user_123", resp.url
    hive = _load_hive()
    resp = asyncio.run(hive.disconnect_hive(uid=NORMAL_UID))
    assert resp.url == "/?uid=user_123", resp.url


if __name__ == "__main__":
    tests = [
        test_linear_setup_oauth_url_encodes_uid,
        test_linear_disconnect_redirect_encodes_uid,
        test_hive_redirects_encode_uid,
        test_manual_import_encodes_uid_in_api_query,
        test_normal_uid_unchanged,
    ]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"{len(tests)}/{len(tests)} tests passed")
