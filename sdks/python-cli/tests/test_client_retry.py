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


def test_404_empty_body_raises_not_found(authed_profile, respx_mock) -> None:
    respx_mock.get("/v1/dev/user/conversations/missing").respond(404)
    with OmiClient(authed_profile) as client:
        with pytest.raises(NotFoundError):
            client.get("/v1/dev/user/conversations/missing")


def test_200_empty_body_returns_none(authed_profile, respx_mock) -> None:
    respx_mock.delete("/v1/dev/user/conversations/c1").respond(200)
    with OmiClient(authed_profile) as client:
        result = client.delete("/v1/dev/user/conversations/c1")
    assert result is None


def test_401_maps_to_auth_error(authed_profile, respx_mock) -> None:
    respx_mock.get("/v1/dev/user/memories").respond(401, json={"detail": "Invalid API Key"})
    with OmiClient(authed_profile) as client:
        with pytest.raises(AuthError):
            client.get("/v1/dev/user/memories")


@pytest.mark.parametrize("json_mode", [False, True])
def test_cli_auth_error_with_markup_preserves_exit_code(
    authed_profile, respx_mock, monkeypatch, capsys, json_mode
) -> None:
    import json

    from omi_cli.main import main

    detail = "Invalid key [/bold] :warning:"
    respx_mock.get("/v1/dev/user/memories").respond(401, json={"detail": detail})
    args = ["--json"] if json_mode else ["--no-color"]
    monkeypatch.setattr("sys.argv", ["omi", *args, "memory", "list"])
    with pytest.raises(SystemExit) as info:
        main()
    assert info.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    if json_mode:
        assert json.loads(captured.err)["detail"] == detail
    else:
        assert detail in captured.err


def test_empty_body_401_maps_to_auth_error(authed_profile, respx_mock) -> None:
    """An empty-body 401 must still raise, not be treated like an empty 204 success."""
    respx_mock.delete("/v1/dev/user/memories/abc").respond(401, content=b"")
    with OmiClient(authed_profile) as client:
        with pytest.raises(AuthError):
            client.delete("/v1/dev/user/memories/abc")


def test_empty_body_404_maps_to_not_found(authed_profile, respx_mock) -> None:
    respx_mock.delete("/v1/dev/user/memories/abc").respond(404, content=b"")
    with OmiClient(authed_profile) as client:
        with pytest.raises(NotFoundError):
            client.delete("/v1/dev/user/memories/abc")


def test_204_delete_still_returns_none(authed_profile, respx_mock) -> None:
    """Guard the success path the fix must not regress: empty 2xx bodies stay silent."""
    respx_mock.delete("/v1/dev/user/memories/abc").respond(204, content=b"")
    with OmiClient(authed_profile) as client:
        result = client.delete("/v1/dev/user/memories/abc")
    assert result is None


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


@pytest.mark.parametrize(
    ("retry_after", "expected_wait"),
    [("3", 3.0), ("invalid", 0.25), (None, 0.25)],
)
def test_cli_503_uses_retry_after_or_backoff(
    authed_profile, respx_mock, monkeypatch, cli_runner, retry_after, expected_wait
) -> None:
    """RFC 9110 section 10.2.3 permits Retry-After on Service Unavailable."""
    import json

    from omi_cli import client as client_module
    from omi_cli.main import app

    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    monkeypatch.setattr(client_module, "_jittered_backoff", lambda _: 0.25)
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    route = respx_mock.get("/v1/dev/user/memories").mock(
        side_effect=[
            httpx.Response(503, headers=headers, json={"detail": "Temporarily unavailable"}),
            httpx.Response(200, json=[]),
        ]
    )

    result = cli_runner.invoke(app, ["--json", "memory", "list"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == []
    assert route.call_count == 2
    assert sleeps == [expected_wait]


def test_503_retry_after_exhaustion_preserves_server_error(authed_profile, respx_mock, monkeypatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    route = respx_mock.get("/v1/dev/user/goals").mock(
        side_effect=[httpx.Response(503, headers={"Retry-After": "3"}, json={"detail": "Maintenance"})] * 4
    )
    with OmiClient(authed_profile) as client:
        with pytest.raises(ServerError) as info:
            client.get("/v1/dev/user/goals")
    assert route.call_count == 4
    assert sleeps == [3.0, 3.0, 3.0]
    assert info.value.exit_code == 3
    assert info.value.detail == "Maintenance"


def test_503_retry_after_http_date(authed_profile, respx_mock, monkeypatch) -> None:
    from email.utils import formatdate

    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    future_date = formatdate(time.time() + 10.0, usegmt=True)
    route = respx_mock.get("/v1/dev/user/goals").mock(
        side_effect=[
            httpx.Response(503, headers={"Retry-After": future_date}, json={"detail": "Maintenance"}),
            httpx.Response(200, json=[]),
        ]
    )
    with OmiClient(authed_profile) as client:
        result = client.get("/v1/dev/user/goals")
    assert result == []
    assert len(sleeps) == 1
    assert 8.0 <= sleeps[0] <= 11.0


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


@pytest.mark.parametrize(
    ("method", "path", "status", "json_body", "error_type"),
    [
        ("GET", "/v1/dev/user/memories", 429, None, RateLimitError),
        ("GET", "/v1/dev/user/goals", 503, None, ServerError),
        ("POST", "/v1/dev/user/conversations", 429, {"text": "x"}, RateLimitError),
    ],
)
def test_long_retry_after_aborts_automatic_retries(
    authed_profile, respx_mock, monkeypatch, method, path, status, json_body, error_type
) -> None:
    """Retry-After values above MAX_RETRY_AFTER_SECONDS must not sleep or retry early."""
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    responses = [
        httpx.Response(status, headers={"Retry-After": "300"}, json={"detail": "synthetic cooldown"}),
        httpx.Response(200, json={"synthetic": True}),
    ]
    route = getattr(respx_mock, method.lower())(path).mock(side_effect=responses)
    with OmiClient(authed_profile) as client:
        with pytest.raises(error_type) as info:
            if method == "GET":
                client.get(path)
            else:
                client.post(path, json_body=json_body)
    assert route.call_count == 1
    assert sleeps == []
    if error_type is RateLimitError:
        assert info.value.retry_after_seconds == 300.0


def test_long_retry_after_http_date_aborts_automatic_retries(authed_profile, respx_mock, monkeypatch) -> None:
    from email.utils import formatdate

    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    future_date = formatdate(time.time() + 300.0, usegmt=True)
    route = respx_mock.get("/v1/dev/user/goals").mock(
        side_effect=[
            httpx.Response(503, headers={"Retry-After": future_date}, json={"detail": "Maintenance"}),
            httpx.Response(200, json=[]),
        ]
    )
    with OmiClient(authed_profile) as client:
        with pytest.raises(ServerError):
            client.get("/v1/dev/user/goals")
    assert route.call_count == 1
    assert sleeps == []


def test_retry_after_at_cap_still_retries(authed_profile, respx_mock, monkeypatch) -> None:
    """Retry-After exactly at MAX_RETRY_AFTER_SECONDS keeps the wait-then-retry path."""
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    from omi_cli import client as client_module

    route = respx_mock.get("/v1/dev/user/memories").mock(
        side_effect=[
            httpx.Response(
                429,
                headers={"Retry-After": str(int(client_module.MAX_RETRY_AFTER_SECONDS))},
                json={"detail": "slow down"},
            ),
            httpx.Response(200, json=[]),
        ]
    )
    with OmiClient(authed_profile) as client:
        result = client.get("/v1/dev/user/memories")
    assert result == []
    assert route.call_count == 2
    assert sleeps == [client_module.MAX_RETRY_AFTER_SECONDS]


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


def test_transport_connect_error_retries_and_surfaces_server_error(authed_profile, respx_mock, monkeypatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda _: None)
    route = respx_mock.get("/v1/dev/user/goals").mock(side_effect=[httpx.ConnectError("Connection refused")] * 4)
    with OmiClient(authed_profile) as client:
        with pytest.raises(ServerError) as info:
            client.get("/v1/dev/user/goals")
    assert route.call_count == 4
    err = info.value
    assert err.exit_code == 3
    assert err.message == "Connection failed"
    assert "Unable to reach the Omi API" in (err.detail or "")
    assert isinstance(err.__cause__, httpx.ConnectError)


def test_transport_read_timeout_surfaces_server_error(authed_profile, respx_mock, monkeypatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda _: None)
    respx_mock.get("/v1/dev/user/goals").mock(side_effect=[httpx.ReadTimeout("The read operation timed out")] * 4)
    with OmiClient(authed_profile) as client:
        with pytest.raises(ServerError) as info:
            client.get("/v1/dev/user/goals")
    err = info.value
    assert err.exit_code == 3
    assert err.message == "Connection failed"
    assert isinstance(err.__cause__, httpx.ReadTimeout)


def test_transport_protocol_error_surfaces_server_error(authed_profile, respx_mock, monkeypatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda _: None)
    respx_mock.get("/v1/dev/user/goals").mock(side_effect=[httpx.ProtocolError("protocol error")] * 4)
    with OmiClient(authed_profile) as client:
        with pytest.raises(ServerError) as info:
            client.get("/v1/dev/user/goals")
    err = info.value
    assert err.exit_code == 3
    assert err.message == "Connection failed"
    assert isinstance(err.__cause__, httpx.ProtocolError)


def test_transport_error_then_200_succeeds_after_retry(authed_profile, respx_mock) -> None:
    respx_mock.get("/v1/dev/user/goals").mock(
        side_effect=[
            httpx.ConnectError("Connection refused"),
            httpx.Response(200, json=[{"id": "g1"}]),
        ]
    )
    with OmiClient(authed_profile) as client:
        result = client.get("/v1/dev/user/goals")
    assert result == [{"id": "g1"}]


def test_main_cli_transport_error_plain_mode(authed_profile, respx_mock, monkeypatch, capsys) -> None:
    import sys

    from omi_cli.main import main

    monkeypatch.setattr(time, "sleep", lambda _: None)
    respx_mock.get("/v1/dev/user/memories").mock(side_effect=[httpx.ConnectError("Connection refused")] * 4)
    monkeypatch.setattr(sys, "argv", ["omi", "memory", "list"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Connection failed" in captured.err
    assert "Unable to reach the Omi API" in captured.err


def test_main_cli_transport_error_json_mode(authed_profile, respx_mock, monkeypatch, capsys) -> None:
    import json
    import sys

    from omi_cli.main import main

    monkeypatch.setattr(time, "sleep", lambda _: None)
    respx_mock.get("/v1/dev/user/memories").mock(side_effect=[httpx.ConnectError("Connection refused")] * 4)
    monkeypatch.setattr(sys, "argv", ["omi", "--json", "memory", "list"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["error"] == "Connection failed"
    assert "Unable to reach the Omi API" in payload["detail"]
