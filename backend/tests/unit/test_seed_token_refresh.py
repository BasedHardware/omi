"""The MELD seed reacquires its Keycloak access token on a 401.

deploy/onprem/seed/seed_meld_users.py mints one user access token per user, then reuses it across the
whole per-user pass (profile conversation + N dialogues, each polled up to ~60s). That pass can outlive
the realm's access-token lifespan (Keycloak default 5 min), so a long run died mid-way with a 401 on an
expired bearer (cubic PR 10887 seed_meld_users.py:357). _KcToken + _api re-mint once on a 401 and retry.

Hermetic: the seed is stdlib-only, loaded by path; _http is replaced with a fake KC/API so no network."""

import importlib.util
import os

import pytest

SEED_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "deploy", "onprem", "seed", "seed_meld_users.py",
)


def _load_seed():
    spec = importlib.util.spec_from_file_location("_seed_meld_users", SEED_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_api_reacquires_token_on_401():
    mod = _load_seed()
    calls = {"mints": 0, "api": 0}

    def fake_http(method, url, *, headers=None, data=None, form=None, expect=(200, 201, 204, 409)):
        if url.endswith("/protocol/openid-connect/token"):
            calls["mints"] += 1
            return 200, {"access_token": f"tok{calls['mints']}"}
        calls["api"] += 1
        if calls["api"] == 1:
            raise RuntimeError(f"{method} {url} -> 401: expired token")
        # the retry must carry the freshly-minted bearer, not the stale one
        assert headers["Authorization"] == "Bearer tok2"
        return 200, {"id": "c1"}

    mod._http = fake_http

    token = mod._KcToken("http://kc", "realm", "cli", "user", "pass")
    assert calls["mints"] == 1  # initial mint

    status, res = mod._api("POST", "http://api/v1/x", token, data={"k": 1})
    assert (status, res) == (200, {"id": "c1"})
    assert calls["mints"] == 2  # re-minted exactly once on the 401
    assert calls["api"] == 2    # original attempt + one retry


def test_api_propagates_non_401_without_refresh():
    mod = _load_seed()
    calls = {"mints": 0, "api": 0}

    def fake_http(method, url, *, headers=None, data=None, form=None, expect=(200, 201, 204, 409)):
        if url.endswith("/protocol/openid-connect/token"):
            calls["mints"] += 1
            return 200, {"access_token": f"tok{calls['mints']}"}
        calls["api"] += 1
        raise RuntimeError(f"{method} {url} -> 500: server error")

    mod._http = fake_http

    token = mod._KcToken("http://kc", "realm", "cli", "user", "pass")
    with pytest.raises(RuntimeError, match="-> 500"):
        mod._api("GET", "http://api/v1/x", token, expect=(200,))
    assert calls["mints"] == 1  # a 500 is not an auth problem: no re-mint
    assert calls["api"] == 1    # and no retry
