"""Hermetic regression: the Shopify `shop` param becomes a URL host on both
/auth/shopify and /auth/shopify/callback. Without validation, a callback with
shop=evil.com POSTs client_id/client_secret/code to the attacker, and
shop=evil.com# on /auth/shopify produces an open-redirect authorization URL.

Run: python3 plugins/omi-shopify-app/test_shop_host.py
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from unittest import mock

MAIN_PATH = Path(__file__).resolve().parent / "main.py"


class _HTTPException(Exception):
    def __init__(self, status_code=None, detail=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _decorator(*args, **kwargs):
    return lambda fn: fn


def _stub(name, **attrs):
    module = types.ModuleType(name)

    def _missing(attr):
        return mock.Mock(name=f"{name}.{attr}")

    module.__getattr__ = _missing
    module.__dict__.update(attrs)
    return module


def _install_stubs():
    fastapi = _stub(
        "fastapi",
        FastAPI=lambda *a, **k: mock.Mock(get=_decorator, post=_decorator, mount=lambda *a, **k: None),
        HTTPException=_HTTPException,
        Request=object,
        Query=lambda default=None, **kw: default,
        Form=lambda default=None, **kw: default,
    )
    responses = _stub(
        "fastapi.responses",
        HTMLResponse=mock.Mock(name="HTMLResponse"),
        RedirectResponse=lambda url=None, **kw: types.SimpleNamespace(url=url),
        JSONResponse=mock.Mock(name="JSONResponse"),
    )
    staticfiles = _stub("fastapi.staticfiles", StaticFiles=lambda *a, **k: None)
    templating = _stub(
        "fastapi.templating",
        Jinja2Templates=lambda *a, **k: mock.Mock(
            TemplateResponse=lambda template, ctx: types.SimpleNamespace(template=template, context=ctx)
        ),
    )
    dotenv = _stub("dotenv", load_dotenv=lambda *a, **k: None)
    db = _stub("db")
    models = _stub("models")

    stubs = {
        "fastapi": fastapi,
        "fastapi.responses": responses,
        "fastapi.staticfiles": staticfiles,
        "fastapi.templating": templating,
        "dotenv": dotenv,
        "db": db,
        "models": models,
        "requests": _stub("requests"),
    }
    return stubs


def _load_main():
    stubs = _install_stubs()
    with mock.patch.dict(sys.modules, stubs):
        spec = importlib.util.spec_from_file_location("shopify_main_under_test", MAIN_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def _callback(module, shop):
    posts = []
    get_urls = []

    class _Resp:
        status_code = 400

        def json(self):
            return {}

    fake_requests = types.SimpleNamespace(
        post=lambda url, **kw: (posts.append(url), _Resp())[1],
        get=lambda url, **kw: (get_urls.append(url), _Resp())[1],
    )
    with mock.patch.object(module, "requests", fake_requests):
        result = asyncio.run(
            module.shopify_callback(
                request=mock.Mock(), code="authcode", state="uid1", shop=shop, hmac="x"
            )
        )
    return result, posts, get_urls


def test_callback_rejects_attacker_host_before_token_exchange():
    module = _load_main()
    _, posts, gets = _callback(module, "evil.com")
    assert not posts, f"token exchange sent to attacker host: {posts}"
    assert not gets


def test_callback_rejects_fragment_and_path_smuggling():
    module = _load_main()
    for shop in ["evil.com#.myshopify.com", "evil.com/x.myshopify.com", "evil.com?.myshopify.com"]:
        _, posts, _ = _callback(module, shop)
        assert not posts, f"host smuggled via {shop!r}: {posts}"


def test_callback_accepts_real_shop_domain():
    module = _load_main()
    _, posts, _ = _callback(module, "mystore.myshopify.com")
    assert posts == ["https://mystore.myshopify.com/admin/oauth/access_token"]


def test_auth_flow_rejects_non_shopify_host():
    module = _load_main()
    for shop in ["evil.com#", "evil.com/x", "@evil.com"]:
        try:
            asyncio.run(module.shopify_auth(uid="u1", shop=shop))
            raise AssertionError(f"shop={shop!r} was not rejected")
        except _HTTPException as e:
            assert e.status_code == 400


def test_auth_flow_normalizes_bare_store_name():
    module = _load_main()
    resp = asyncio.run(module.shopify_auth(uid="u1", shop="mystore"))
    assert resp.url.startswith("https://mystore.myshopify.com/admin/oauth/authorize?"), resp.url
    resp = asyncio.run(module.shopify_auth(uid="u1", shop="mystore.myshopify.com"))
    assert resp.url.startswith("https://mystore.myshopify.com/admin/oauth/authorize?"), resp.url


def test_auth_flow_rejects_malformed_dns_label():
    module = _load_main()
    for shop in ["foo-.myshopify.com", "-foo.myshopify.com", "a" * 64 + ".myshopify.com"]:
        try:
            asyncio.run(module.shopify_auth(uid="u1", shop=shop))
            raise AssertionError(f"shop={shop!r} was not rejected")
        except _HTTPException as e:
            assert e.status_code == 400


if __name__ == "__main__":
    tests = [
        test_callback_rejects_attacker_host_before_token_exchange,
        test_callback_rejects_fragment_and_path_smuggling,
        test_callback_accepts_real_shop_domain,
        test_auth_flow_rejects_non_shopify_host,
        test_auth_flow_normalizes_bare_store_name,
        test_auth_flow_rejects_malformed_dns_label,
    ]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"{len(tests)}/{len(tests)} tests passed")
