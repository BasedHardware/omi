"""The OIDC adapter must percent-encode the uid it interpolates into an Admin API path.

`get_user`/`update_user_profile`/`delete_user` build `f"{admin_api}/users/{uid}"`. With the uid
inlined raw, a caller-supplied value containing `/` or `..` reshapes the request: httpx normalises
dot segments per RFC 3986, so `../groups` turns a user lookup into `GET /admin/realms/omi/groups`
carried by the admin client's bearer token. `POST /v1/apps/migrate-owner` reaches `get_user` with an
un-annotated query parameter (`old_id`) before its `source_uid != old_id` eligibility check runs, so
any authenticated caller can drive an arbitrary authenticated GET against the provider's Admin API.
The response never reaches the caller (a non-object JSON body becomes an AuthError, which the router
turns into 403), so it is a blind request-forgery primitive rather than a data leak — and it exists
only under OIDC: the Firebase SDK takes a uid, not a URL.

Encoding is done in the adapter rather than at the call site because the adapter is the boundary that
owns the URL; a validation added to one router would leave the other two verbs exposed.

Hermetic: httpx is imported lazily inside each method, so the transport is monkeypatched.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from utils.auth.adapters.oidc import OIDCAuthProvider

ADMIN_API = "http://keycloak:8080/admin/realms/omi"
TRAVERSAL_UID = "../groups"


def _provider(monkeypatch) -> OIDCAuthProvider:
    provider = OIDCAuthProvider()
    monkeypatch.setattr(provider, "_admin_token", lambda: "admin-token")
    monkeypatch.setattr(provider, "_admin_api", lambda: ADMIN_API)
    return provider


def _capture(monkeypatch, verb: str, *, json_body=None, status_code: int = 200) -> list[str]:
    """Record the URL the adapter asks httpx for, for one HTTP verb."""
    seen: list[str] = []

    def _fake(url, *_args, **_kwargs):
        seen.append(url)
        return SimpleNamespace(
            status_code=status_code,
            json=lambda: json_body if json_body is not None else {},
            text="",
        )

    monkeypatch.setattr(httpx, verb, _fake)
    return seen


def test_get_user_encodes_the_uid_into_a_single_path_segment(monkeypatch):
    provider = _provider(monkeypatch)
    seen = _capture(monkeypatch, "get", json_body={"id": TRAVERSAL_UID, "email": "u@example.com"})

    provider.get_user_profile(TRAVERSAL_UID)

    assert seen, 'the adapter made no request'
    assert seen[0] == f"{ADMIN_API}/users/..%2Fgroups", seen[0]
    assert "/groups" not in seen[0].removeprefix(ADMIN_API + "/users/"), seen[0]


def test_delete_user_encodes_the_uid(monkeypatch):
    provider = _provider(monkeypatch)
    seen = _capture(monkeypatch, "delete", status_code=204)

    provider.delete_user(TRAVERSAL_UID)

    assert seen[0] == f"{ADMIN_API}/users/..%2Fgroups", seen[0]


def test_update_user_profile_encodes_the_uid(monkeypatch):
    provider = _provider(monkeypatch)
    seen = _capture(monkeypatch, "put", status_code=204)

    provider.update_user_profile(TRAVERSAL_UID, display_name='x')

    assert seen[0] == f"{ADMIN_API}/users/..%2Fgroups", seen[0]


def test_an_ordinary_uid_is_unchanged(monkeypatch):
    """Encoding must not alter the normal case: Keycloak uids are UUIDs, which have no reserved chars."""
    provider = _provider(monkeypatch)
    seen = _capture(monkeypatch, "delete", status_code=204)

    provider.delete_user("3f2b9c14-6a7e-4f38-9c11-0d4a1b7e5c92")

    assert seen[0] == f"{ADMIN_API}/users/3f2b9c14-6a7e-4f38-9c11-0d4a1b7e5c92"
