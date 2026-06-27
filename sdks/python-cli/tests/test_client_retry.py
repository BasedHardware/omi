"""Tests for the HTTP client: auth headers, retry logic, error mapping, OAuth refresh."""

from __future__ import annotations

import time

import httpx
import pytest

from omi_cli import __version__
from omi_cli import config as cfg
from omi_cli.auth.store import store_oauth_tokens
from omi_cli.client import USER_AGENT, OmiClient
from omi_cli.errors import AuthError, CliError, NotFoundError, RateLimitError, ServerError


def test_user_agent_contains_version_and_repo() -> None:
    assert __version__ in USER_AGENT
    assert "omi-cli" in USER_AGENT


def test_oauth_pre_flight_refresh_when_token_expired(config_path, monkeypatch) -> None:
    """Constructing an OmiClient on an OAuth profile with an expired ID token
    must trigger a Firebase refresh before the bearer header is built."""
    # Seed the profile with an expired token.
    store_oauth_tokens(
        "default",
        id_token="stale_token",
        refresh_token="refr_x",
        expires_at=time.time() - 60,
        api_base="https://api.test.omi.local",
    )

    refreshed_calls: dict = {}

    def fake_refresh(profile_name: str) -> str:
        refreshed_calls["called"] = profile_name
        return "fresh_token_after_refresh"

    monkeypatch.setattr("omi_cli.auth.oauth.refresh_id_token", fake_refresh)

    profile = cfg.load().get_profile("default")
    with OmiClient(profile) as client:
        # Inspect the Authorization header the client computed.
        sent_token = client._http.headers["Authorization"]
    assert refreshed_calls.get("called") == "default"
    assert sent_token == "Bearer fresh_token_after_refresh"


def test_oauth_pre_flight_skipped_when_token_fresh(config_path, monkeypatch) -> None:
    """A still-valid OAuth ID token should NOT trigger a refresh — that would
    waste a Firebase round-trip on every CLI invocation."""
    store_oauth_tokens(
        "default",
        id_token="fresh_token",
        refresh_token="refr_x",
        expires_at=time.time() + 1800,  # 30 min remaining
        api_base="https://api.test.omi.local",
    )

    refresh_count = {"n": 0}

    def fake_refresh(profile_name: str) -> str:
        refresh_count["n"] += 1
        return "should_not_be_used"

    monkeypatch.setattr("omi_cli.auth.oauth.refresh_id_token", fake_refresh)

    profile = cfg.load().get_profile("default")
    with OmiClient(profile) as client:
        sent_token = client._http.headers["Authorization"]
    assert refresh_count["n"] == 0
    assert sent_token == "Bearer fresh_token"


def test_get_injects_bearer_and_returns_json(authed_profile, respx_mock) -> None:
    route = respx_mock.get("/v1/dev/user/memories").respond(json=[{"id": "m1", "content": "hi"}])
    with OmiClient(authed_profile) as client:
        result = client.get("/v1/dev/user/memories")
    assert result == [{"id": "m1", "content": "hi"}]
    request = route.calls.last.request
    assert request.headers["Authorization"].startswith("Bearer omi_dev_")
    assert request.headers["User-Agent"] == USER_AGENT


def test_unauthenticated_profile_raises(authed_profile) -> None:
    profile = authed_profile
    profile.api_key = None
    profile.auth_method = None
    with pytest.raises(CliError) as info:
        OmiClient(profile)
    assert info.value.exit_code == 2  # EXIT_AUTH


def test_404_maps_to_not_found(authed_profile, respx_mock) -> None:
    respx_mock.get("/v1/dev/user/memories").respond(404, json={"detail": "missing"})
    with OmiClient(authed_profile) as client:
        with pytest.raises(NotFoundError):
            client.get("/v1/dev/user/memories")


def test_401_maps_to_auth_error(authed_profile, respx_mock) -> None:
    respx_mock.get("/v1/dev/user/memories").respond(401, json={"detail": "Invalid API Key"})
    with OmiClient(authed_profile) as client:
        with pytest.raises(AuthError):
            client.get("/v1/dev/user/memories")


def test_403_maps_to_auth_error(authed_profile, respx_mock) -> None:
    respx_mock.post("/v1/dev/user/memories").respond(
        403, json={"detail": "Insufficient permissions. Required scope: memories:write"}
    )
    with OmiClient(authed_profile) as client:
        with pytest.raises(AuthError) as info:
            client.post("/v1/dev/user/memories", json_body={"content": "x"})
    assert "permission" in str(info.value).lower() or "scope" in str(info.value).lower()


def test_500_retries_and_then_surfaces_server_error(authed_profile, respx_mock) -> None:
    route = respx_mock.get("/v1/dev/user/goals").mock(side_effect=[httpx.Response(500, json={"detail": "boom"})] * 4)
    with OmiClient(authed_profile) as client:
        with pytest.raises(ServerError):
            client.get("/v1/dev/user/goals")
    # 4 attempts should have been made before giving up.
    assert route.call_count == 4


def test_500_then_200_succeeds_after_retry(authed_profile, respx_mock) -> None:
    respx_mock.get("/v1/dev/user/goals").mock(
        side_effect=[
            httpx.Response(500, json={"detail": "boom"}),
            httpx.Response(200, json=[]),
        ]
    )
    with OmiClient(authed_profile) as client:
        result = client.get("/v1/dev/user/goals")
    assert result == []


def test_429_surfaces_rate_limit_with_policy(authed_profile, respx_mock) -> None:
    respx_mock.post("/v1/dev/user/conversations").mock(
        side_effect=[
            httpx.Response(
                429,
                headers={"Retry-After": "12"},
                json={"detail": "Rate limit exceeded for policy dev:conversations"},
            ),
        ]
        * 4
    )
    with OmiClient(authed_profile) as client:
        with pytest.raises(RateLimitError) as info:
            client.post("/v1/dev/user/conversations", json_body={"text": "x"})
    err = info.value
    assert err.policy == "dev:conversations"
    assert err.retry_after_seconds == 12.0
    assert "12s" in (err.detail or "")


def test_204_returns_none(authed_profile, respx_mock) -> None:
    respx_mock.delete("/v1/dev/user/memories/abc").respond(204)
    with OmiClient(authed_profile) as client:
        result = client.delete("/v1/dev/user/memories/abc")
    assert result is None


def test_param_filtering_drops_none(authed_profile, respx_mock) -> None:
    route = respx_mock.get("/v1/dev/user/memories").respond(json=[])
    with OmiClient(authed_profile) as client:
        client.get("/v1/dev/user/memories", params={"limit": 25, "offset": 0, "categories": None})
    request = route.calls.last.request
    assert "categories" not in request.url.params
    assert request.url.params["limit"] == "25"


def test_429_with_retry_after_waits_at_least_that_long(authed_profile, respx_mock, monkeypatch) -> None:
    """Greptile P2: the retry wait must honor a server-supplied Retry-After
    header rather than blindly using exponential jitter."""
    import time

    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    # tenacity sleeps via time.sleep — capture and short-circuit.
    monkeypatch.setattr(time, "sleep", fake_sleep)

    respx_mock.get("/v1/dev/user/memories").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "3"}, json={"detail": "slow down"}),
            httpx.Response(200, json=[]),
        ]
    )
    with OmiClient(authed_profile) as client:
        result = client.get("/v1/dev/user/memories")
    assert result == []
    # Exactly one inter-attempt wait happened, and it honored the Retry-After
    # value (3 seconds), not the jitter window (which caps at ~0.5s on attempt 1).
    assert len(sleeps) == 1
    assert sleeps[0] == 3.0


def test_429_retry_after_is_capped(authed_profile, respx_mock, monkeypatch) -> None:
    """A pathologically large Retry-After value must be capped so the CLI
    doesn't pin for hours on a misbehaving upstream."""
    import time

    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))

    from omi_cli import client as client_module

    respx_mock.get("/v1/dev/user/memories").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "99999"}, json={"detail": "wait"}),
            httpx.Response(200, json=[]),
        ]
    )
    with OmiClient(authed_profile) as cli:
        cli.get("/v1/dev/user/memories")
    assert sleeps[0] == client_module.MAX_RETRY_AFTER_SECONDS


def test_validation_error_detail_string_is_formatted(authed_profile, respx_mock) -> None:
    respx_mock.post("/v1/dev/user/memories").respond(
        422,
        json={
            "detail": [
                {"loc": ["body", "content"], "msg": "field required"},
                {"loc": ["body", "tags"], "msg": "must be a list"},
            ]
        },
    )
    with OmiClient(authed_profile) as client:
        with pytest.raises(CliError) as info:
            client.post("/v1/dev/user/memories", json_body={})
    detail = info.value.detail or ""
    assert "body.content" in detail
    assert "body.tags" in detail
