"""Contract tests for hosted MCP request-level observability and key scoping.

Covers the 100% structured ``mcp_request`` log line (the PostHog-free request
envelope), deterministic per-uid ``MCP Tool Call`` sampling, the daily
``MCP Active`` Redis dedupe marker, the MCP-only ``POSTHOG_EVENTS_API_KEY``
capture path, and the HTTP 400 contract for header-caused protocol errors.
"""

import json
import math
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import utils.mcp_analytics as mcp_analytics
import utils.mcp_server.transport as mcp_transport
from routers import mcp_sse
from utils.mcp_scopes import MCP_FULL_ACCESS_SCOPES
from utils.mcp_server.auth import MCPAuthContext
from utils.mcp_server.versions import (
    META_PROTOCOL_VERSION,
    NEGOTIATED_FALLBACK_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
)

ALL_SCOPES = list(MCP_FULL_ACCESS_SCOPES)


def _full_auth(uid="uid-test", scopes=None, **kwargs):
    return MCPAuthContext(
        uid=uid,
        auth_type="oauth",
        scopes=list(scopes if scopes is not None else ALL_SCOPES),
        client_id="test-client",
        **kwargs,
    )


def _msg(method, msg_id=1, params=None):
    message = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        message["params"] = params
    return message


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(mcp_sse.router)
    return TestClient(app)


@pytest.fixture
def authed():
    """Authenticated POST seams: auth context, admission limiter, telemetry sinks."""
    with (
        patch.object(mcp_transport, "authenticate_mcp_request", return_value=_full_auth()),
        patch.object(mcp_transport, "check_rate_limit_inline") as admission,
        patch.object(mcp_transport, "check_rate_limit_context") as context_limit,
        patch.object(mcp_transport, "log_mcp_request") as request_log,
        patch.object(mcp_transport, "schedule_mcp_active") as active_event,
        patch.object(mcp_transport, "schedule_mcp_tool_call") as tool_event,
    ):
        yield SimpleNamespace(
            admission=admission,
            context_limit=context_limit,
            request_log=request_log,
            active_event=active_event,
            tool_event=tool_event,
        )


def _post(client, path, body, **headers):
    return client.post(path, json=body, headers={"Authorization": "Bearer tok", **headers})


def _tool_call(name, arguments=None, msg_id=7):
    return _msg("tools/call", msg_id=msg_id, params={"name": name, "arguments": arguments or {}})


class TestHeaderErrorStatusCodes:
    """2026-07-28 schema: header-caused ``HeaderMismatchError`` (-32020) and
    ``UnsupportedProtocolVersionError`` (-32022) answer HTTP 400 with a
    JSON-RPC error body. Body-level ``_meta`` version problems stay on 200."""

    def test_unsupported_header_version_returns_400(self, client, authed):
        response = _post(client, "/v1/mcp", _msg("tools/list"), **{"mcp-protocol-version": "1999-01-01"})
        assert response.status_code == 400
        error = response.json()["error"]
        assert error["code"] == -32022
        assert error["data"]["supported"] == list(SUPPORTED_PROTOCOL_VERSIONS)
        assert error["data"]["requested"] == "1999-01-01"
        authed.request_log.assert_called_once()
        assert authed.request_log.call_args.kwargs["http_status"] == 400

    def test_header_body_version_mismatch_returns_400(self, client, authed):
        message = _msg("tools/list")
        message["params"] = {"_meta": {META_PROTOCOL_VERSION: "2025-06-18"}}
        response = _post(client, "/v1/mcp", message, **{"mcp-protocol-version": "2025-03-26"})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == -32020

    def test_mcp_method_header_mismatch_returns_400(self, client, authed):
        response = _post(client, "/v1/mcp", _msg("ping"), **{"mcp-method": "tools/list"})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == -32020

    def test_body_meta_unsupported_version_stays_200(self, client, authed):
        message = _msg("tools/list")
        message["_meta"] = {META_PROTOCOL_VERSION: "1999-01-01"}
        response = _post(client, "/v1/mcp", message)
        assert response.status_code == 200
        assert response.json()["error"]["code"] == -32022


class TestPrepareMessagesSseAccept:
    """``prepare_messages`` rejections are ordinary JSON-RPC errors and must
    honor ``Accept: text/event-stream`` like normal responses."""

    def test_batch_rejection_streams_as_sse(self, client, authed):
        response = _post(
            client,
            "/v1/mcp",
            [_msg("ping", 1)],
            accept="text/event-stream",
            **{"mcp-protocol-version": "2026-07-28"},
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        assert "event: message" in response.text
        assert '"code":-32600' in response.text or '"code": -32600' in response.text

    def test_batch_rejection_json_when_no_sse_accept(self, client, authed):
        response = _post(client, "/v1/mcp", [_msg("ping", 1)], **{"mcp-protocol-version": "2026-07-28"})
        assert response.status_code == 200
        assert response.json()["error"]["code"] == -32600


class TestRequestObservability:
    """The per-POST envelope is a 100% structured ``mcp_request`` log line plus
    a daily ``MCP Active`` marker — never a PostHog ``MCP Request`` event."""

    def _read_log_line(self, capsys):
        lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["message"] == mcp_analytics.MCP_REQUEST_LOG_MESSAGE == "mcp_request"
        return record

    def test_request_log_once_per_post(self, client, authed):
        _post(client, "/v1/mcp", _msg("tools/list"), **{"mcp-protocol-version": "2025-06-18"})
        authed.request_log.assert_called_once()
        kwargs = authed.request_log.call_args.kwargs
        assert kwargs["jsonrpc_methods"] == ["tools/list"]
        assert kwargs["http_status"] == 200
        assert kwargs["path"] == "canonical"
        assert kwargs["protocol_version"] == "2025-06-18"
        assert kwargs["is_handshake"] is False
        authed.active_event.assert_called_once()
        active_kwargs = authed.active_event.call_args.kwargs
        assert active_kwargs["uid"] == "uid-test"
        assert active_kwargs["protocol_version"] == "2025-06-18"

    def test_request_log_on_401(self, client):
        with (
            patch.object(mcp_transport, "authenticate_mcp_request", return_value=None),
            patch.object(mcp_transport, "log_mcp_request") as request_log,
            patch.object(mcp_transport, "schedule_mcp_active") as active_event,
        ):
            response = _post(client, "/v1/mcp", _msg("ping"))
        assert response.status_code == 401
        request_log.assert_called_once()
        assert request_log.call_args.kwargs["http_status"] == 401
        # The anonymous marker never reaches Redis/PostHog (schedule drops it).
        assert active_event.call_args.kwargs["uid"] == "mcp-anonymous"

    @pytest.mark.parametrize(("path", "label"), [("/v1/mcp", "canonical"), ("/v1/mcp/sse", "legacy_sse")])
    def test_request_log_on_auth_403(self, client, path, label):
        """A 403 raised inside authentication still emits exactly one
        structured log line per POST, labeled by path."""
        with (
            patch.object(
                mcp_transport,
                "authenticate_mcp_request",
                side_effect=HTTPException(status_code=403, detail="blocked"),
            ),
            patch.object(mcp_transport, "log_mcp_request") as request_log,
        ):
            response = _post(client, path, _msg("ping"))
        assert response.status_code == 403
        request_log.assert_called_once()
        kwargs = request_log.call_args.kwargs
        assert kwargs["http_status"] == 403
        assert kwargs["path"] == label

    def test_request_log_on_admission_403(self, client, authed):
        authed.admission.side_effect = HTTPException(status_code=403, detail="blocked")
        response = _post(client, "/v1/mcp", _msg("ping"))
        assert response.status_code == 403
        authed.request_log.assert_called_once()
        kwargs = authed.request_log.call_args.kwargs
        assert kwargs["http_status"] == 403
        assert kwargs["path"] == "canonical"

    def test_request_log_on_admission_429(self, client, authed):
        with patch.object(
            mcp_transport,
            "check_rate_limit_inline",
            side_effect=HTTPException(status_code=429, detail="Rate limit exceeded"),
        ):
            response = _post(client, "/v1/mcp", _msg("ping"))
        assert response.status_code == 429
        authed.request_log.assert_called_once()
        assert authed.request_log.call_args.kwargs["http_status"] == 429

    def test_request_log_fields_stay_low_cardinality(self, capsys):
        fields_allowed = {
            "message",
            "jsonrpc_methods",
            "message_count",
            "is_handshake",
            "protocol_version",
            "client_name",
            "auth_type",
            "http_status",
            "path",
            "duration_ms",
            "tool",
        }
        mcp_analytics.log_mcp_request(
            jsonrpc_methods=["tools/call", "custom_method_xyz"],
            message_count=2,
            is_handshake=False,
            protocol_version="2025-03-26",
            client_name="not-in-enum",
            auth_type="oauth",
            http_status=200,
            path="canonical",
            duration_ms=5.0,
            tool_name="get_memories",
        )
        record = self._read_log_line(capsys)
        assert set(record) <= fields_allowed
        assert record["jsonrpc_methods"] == ["tools/call", "unknown"]
        assert record["client_name"] == "unknown"
        assert record["auth_type"] == "hosted_oauth"

    def test_jsonrpc_methods_bounded_to_full_batch_cap(self, capsys):
        """The log line carries every method of an accepted 20-message batch
        and truncates only beyond the cap."""
        base = dict(
            message_count=20,
            is_handshake=False,
            protocol_version="2025-03-26",
            client_name="unknown",
            auth_type="oauth",
            http_status=200,
            path="canonical",
            duration_ms=1.0,
        )
        mcp_analytics.log_mcp_request(jsonrpc_methods=["tools/call"] * 20, **base)
        assert self._read_log_line(capsys)["jsonrpc_methods"] == ["tools/call"] * 20
        mcp_analytics.log_mcp_request(jsonrpc_methods=["ping"] * 25, **base)
        assert self._read_log_line(capsys)["jsonrpc_methods"] == ["ping"] * 20

    def test_no_mcp_request_posthog_event_exists(self):
        """There is deliberately no ``MCP Request`` PostHog event — request
        volume lives in the structured log only."""
        assert not hasattr(mcp_analytics, "MCP_REQUEST")
        assert not hasattr(mcp_analytics, "emit_mcp_request")
        assert not hasattr(mcp_analytics, "schedule_mcp_request")
        assert not hasattr(mcp_analytics, "MCP_REQUEST_EVENT_SAMPLE_RATE_ENV")


class TestToolCallUserSampling:
    """Deterministic per-uid sampling: a uid is fully in or fully out, decided
    by a salted SHA256 bucket — identical on every instance and deploy."""

    def _schedule(self, monkeypatch, env_value, uid="u1"):
        monkeypatch.setenv(mcp_analytics.MCP_TOOL_CALL_USER_SAMPLE_RATE_ENV, env_value)
        submit = MagicMock()
        monkeypatch.setattr(mcp_analytics, "submit_with_context", submit)
        mcp_analytics.schedule_mcp_tool_call(
            uid=uid,
            tool_name="get_memories",
            auth_type="oauth",
            client_id="c",
            outcome="success",
            authorization_outcome="allowed",
            error_category="none",
            duration_ms=1.0,
            result_count=0,
        )
        return submit

    def test_decision_matches_the_sha256_formula(self):
        import hashlib

        for uid in ("u-alpha", "u-beta", "uid-test-123"):
            bucket = int(
                hashlib.sha256((mcp_analytics.MCP_TOOL_CALL_USER_SAMPLE_SALT + uid).encode("utf-8")).hexdigest()[:8],
                16,
            )
            expected = bucket / 0xFFFFFFFF < 0.25
            assert mcp_analytics.user_in_tool_call_sample(uid, 0.25) == expected
            # Deterministic: repeated calls never flip the decision.
            assert mcp_analytics.user_in_tool_call_sample(uid, 0.25) == expected

    def test_rate_zero_never_samples(self, monkeypatch):
        for uid in ("a", "b", "uid-test-123"):
            assert not mcp_analytics.user_in_tool_call_sample(uid, 0.0)
        assert not self._schedule(monkeypatch, "0").called

    def test_rate_one_always_samples(self, monkeypatch):
        for uid in ("a", "b", "uid-test-123"):
            assert mcp_analytics.user_in_tool_call_sample(uid, 1.0)
        submit = self._schedule(monkeypatch, "1")
        submit.assert_called_once()
        assert submit.call_args.kwargs["user_sample_rate"] == 1.0

    def test_default_rate_is_quarter_and_env_clamps(self, monkeypatch):
        monkeypatch.delenv(mcp_analytics.MCP_TOOL_CALL_USER_SAMPLE_RATE_ENV, raising=False)
        assert mcp_analytics.tool_call_user_sample_rate() == 0.25
        monkeypatch.setenv(mcp_analytics.MCP_TOOL_CALL_USER_SAMPLE_RATE_ENV, "bogus")
        assert mcp_analytics.tool_call_user_sample_rate() == 0.25
        monkeypatch.setenv(mcp_analytics.MCP_TOOL_CALL_USER_SAMPLE_RATE_ENV, "2")
        assert mcp_analytics.tool_call_user_sample_rate() == 1.0
        monkeypatch.setenv(mcp_analytics.MCP_TOOL_CALL_USER_SAMPLE_RATE_ENV, "-1")
        assert mcp_analytics.tool_call_user_sample_rate() == 0.0

    @pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
    def test_nonfinite_rates_fall_back_to_default(self, monkeypatch, value):
        monkeypatch.setenv(mcp_analytics.MCP_TOOL_CALL_USER_SAMPLE_RATE_ENV, value)
        assert mcp_analytics.tool_call_user_sample_rate() == 0.25

    def test_sampled_fraction_matches_rate_over_population(self):
        """10k synthetic uids: the sampled fraction tracks the configured rate."""
        uids = [f"synthetic-uid-{i}" for i in range(10_000)]
        for rate, tolerance in ((0.25, 0.03), (0.5, 0.03), (0.05, 0.02)):
            fraction = sum(mcp_analytics.user_in_tool_call_sample(uid, rate) for uid in uids) / len(uids)
            assert abs(fraction - rate) < tolerance, (rate, fraction)

    def test_unsampled_user_sends_nothing_sampled_sends_everything(self, monkeypatch):
        rate = 0.25
        sampled = next(
            uid for uid in (f"u-{i}" for i in range(500)) if mcp_analytics.user_in_tool_call_sample(uid, rate)
        )
        unsampled = next(
            uid for uid in (f"u-{i}" for i in range(500)) if not mcp_analytics.user_in_tool_call_sample(uid, rate)
        )
        submit = self._schedule(monkeypatch, str(rate), uid=sampled)
        submit.assert_called_once()
        assert submit.call_args.kwargs["user_sample_rate"] == rate
        assert not self._schedule(monkeypatch, str(rate), uid=unsampled).called

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), 2.0, "bogus"])
    def test_emitted_user_sample_rate_is_finite_and_bounded(self, monkeypatch, value):
        emit = MagicMock()
        monkeypatch.setattr(mcp_analytics, "emit_mcp_posthog_event", emit)
        mcp_analytics.emit_mcp_tool_call(
            uid="u",
            tool_name="get_memories",
            auth_type="oauth",
            client_id="c",
            outcome="success",
            authorization_outcome="allowed",
            error_category="none",
            duration_ms=1.0,
            result_count=0,
            user_sample_rate=value,
        )
        rate = emit.call_args.args[2]["user_sample_rate"]
        assert 0.0 <= rate <= 1.0
        assert math.isfinite(rate)


@pytest.fixture(autouse=True)
def _reset_mcp_active_local_seen():
    """The process-local uid/day cache survives across tests in one process."""
    with mcp_analytics._mcp_active_seen_lock:
        mcp_analytics._mcp_active_seen_uids.clear()
        mcp_analytics._mcp_active_seen_day = None
    yield
    with mcp_analytics._mcp_active_seen_lock:
        mcp_analytics._mcp_active_seen_uids.clear()
        mcp_analytics._mcp_active_seen_day = None


class TestMcpActiveMarker:
    """``MCP Active`` fires at most once per uid per UTC day behind a Redis
    ``SET NX EX`` marker, and fails open when Redis is down."""

    def _properties(self):
        return dict(client_name="claude_ai", transport="oauth", protocol_version="2025-03-26", first_tool=None)

    def test_first_claim_of_day_emits(self, monkeypatch):
        redis = MagicMock()
        redis.r.set.return_value = True
        emit = MagicMock()
        monkeypatch.setattr(mcp_analytics, "redis_db", redis)
        monkeypatch.setattr(mcp_analytics, "emit_mcp_posthog_event", emit)
        mcp_analytics.emit_mcp_active(uid="u1", **self._properties())
        args, kwargs = redis.r.set.call_args
        assert args[0].startswith("mcp:active:")
        assert args[0].endswith(":u1")
        assert kwargs == {"nx": True, "ex": 172800}
        distinct_id, event, properties = emit.call_args.args
        assert distinct_id == "u1"
        assert event == "MCP Active"
        assert properties["first_tool"] == "none"
        assert properties["transport"] == "hosted_oauth"
        assert properties["$process_person_profile"] is False

    def test_second_claim_of_day_skips_event(self, monkeypatch):
        redis = MagicMock()
        redis.r.set.return_value = None  # NX: key already exists
        emit = MagicMock()
        monkeypatch.setattr(mcp_analytics, "redis_db", redis)
        monkeypatch.setattr(mcp_analytics, "emit_mcp_posthog_event", emit)
        mcp_analytics.emit_mcp_active(uid="u1", **self._properties())
        emit.assert_not_called()

    def test_redis_failure_fails_open(self, monkeypatch):
        redis = MagicMock()
        redis.r.set.side_effect = ConnectionError("redis down")
        emit = MagicMock()
        monkeypatch.setattr(mcp_analytics, "redis_db", redis)
        monkeypatch.setattr(mcp_analytics, "emit_mcp_posthog_event", emit)
        mcp_analytics.emit_mcp_active(uid="u1", **self._properties())
        emit.assert_not_called()

    def test_first_tool_normalized(self, monkeypatch):
        redis = MagicMock()
        redis.r.set.return_value = True
        emit = MagicMock()
        monkeypatch.setattr(mcp_analytics, "redis_db", redis)
        monkeypatch.setattr(mcp_analytics, "emit_mcp_posthog_event", emit)
        mcp_analytics.emit_mcp_active(
            uid="u1",
            client_name="other",
            transport="legacy_mcp_key",
            protocol_version="bogus",
            first_tool="get_memories",
        )
        properties = emit.call_args.args[2]
        assert properties["first_tool"] == "get_memories"
        assert properties["transport"] == "api_key"
        assert properties["protocol_version"] == "unknown"

    def test_schedule_skips_anonymous(self, monkeypatch):
        submit = MagicMock()
        monkeypatch.setattr(mcp_analytics, "submit_with_context", submit)
        mcp_analytics.schedule_mcp_active(uid="mcp-anonymous", **self._properties())
        mcp_analytics.schedule_mcp_active(uid=None, **self._properties())
        submit.assert_not_called()


class TestMcpActiveLocalCache:
    """The bounded process-local uid/day cache short-circuits the Redis NX
    claim at scheduling time and inside the worker; Redis stays authority."""

    def _properties(self):
        return dict(client_name="claude_ai", transport="oauth", protocol_version="2025-03-26", first_tool=None)

    def _redis(self, monkeypatch, set_return=True):
        redis = MagicMock()
        redis.r.set.return_value = set_return
        monkeypatch.setattr(mcp_analytics, "redis_db", redis)
        monkeypatch.setattr(mcp_analytics, "emit_mcp_posthog_event", MagicMock())
        return redis

    def test_repeated_uid_one_redis_set_and_one_schedule(self, monkeypatch):
        redis = self._redis(monkeypatch)
        submit = MagicMock(side_effect=lambda executor, fn, **kwargs: fn(**kwargs))
        monkeypatch.setattr(mcp_analytics, "submit_with_context", submit)
        for _ in range(3):
            mcp_analytics.schedule_mcp_active(uid="u1", **self._properties())
        assert submit.call_count == 1
        assert redis.r.set.call_count == 1
        mcp_analytics.emit_mcp_active(uid="u1", **self._properties())
        assert redis.r.set.call_count == 1

    def test_nx_miss_is_cached_and_skips_future_claims(self, monkeypatch):
        redis = self._redis(monkeypatch, set_return=None)
        emit = MagicMock()
        monkeypatch.setattr(mcp_analytics, "emit_mcp_posthog_event", emit)
        for _ in range(3):
            mcp_analytics.emit_mcp_active(uid="u1", **self._properties())
        assert redis.r.set.call_count == 1
        emit.assert_not_called()

    def test_redis_error_is_not_cached_and_retries(self, monkeypatch):
        redis = self._redis(monkeypatch)
        redis.r.set.side_effect = ConnectionError("redis down")
        emit = MagicMock()
        monkeypatch.setattr(mcp_analytics, "emit_mcp_posthog_event", emit)
        for _ in range(2):
            mcp_analytics.emit_mcp_active(uid="u1", **self._properties())
        assert redis.r.set.call_count == 2
        emit.assert_not_called()
        redis.r.set.side_effect = None
        redis.r.set.return_value = True
        mcp_analytics.emit_mcp_active(uid="u1", **self._properties())
        emit.assert_called_once()

    def test_utc_day_rollover_resets_cache(self, monkeypatch):
        redis = self._redis(monkeypatch)
        current = {"day": "20260728"}
        monkeypatch.setattr(mcp_analytics, "_utc_day", lambda now=None: current["day"])
        mcp_analytics.emit_mcp_active(uid="u1", **self._properties())
        mcp_analytics.emit_mcp_active(uid="u1", **self._properties())
        assert redis.r.set.call_count == 1
        current["day"] = "20260729"
        mcp_analytics.emit_mcp_active(uid="u1", **self._properties())
        assert redis.r.set.call_count == 2
        assert redis.r.set.call_args.args[0].endswith(":20260729:u1")

    def test_fifo_cap_evicts_oldest_entries(self, monkeypatch):
        redis = self._redis(monkeypatch)
        monkeypatch.setattr(mcp_analytics, "MCP_ACTIVE_LOCAL_SEEN_MAX", 2)
        for uid in ("u1", "u2", "u3"):
            mcp_analytics.emit_mcp_active(uid=uid, **self._properties())
        assert redis.r.set.call_count == 3
        mcp_analytics.emit_mcp_active(uid="u2", **self._properties())
        mcp_analytics.emit_mcp_active(uid="u3", **self._properties())
        assert redis.r.set.call_count == 3
        mcp_analytics.emit_mcp_active(uid="u1", **self._properties())
        assert redis.r.set.call_count == 4

    def test_rollover_mid_claim_marks_the_claimed_day(self, monkeypatch):
        """The worker captures its day once: if the UTC day rolls over while
        the Redis SET is awaited, the local mark lands on the claimed day, so
        the next day still performs its own claim."""
        instant = {"now": datetime(2026, 7, 28, 23, 59, 59, tzinfo=timezone.utc)}

        class _FrozenDateTime:
            @classmethod
            def now(cls, tz=None):
                return instant["now"]

        monkeypatch.setattr(mcp_analytics, "datetime", _FrozenDateTime)
        redis = self._redis(monkeypatch)

        def _set_then_roll(*args, **kwargs):
            instant["now"] = instant["now"] + timedelta(days=1)
            return True

        redis.r.set.side_effect = _set_then_roll
        mcp_analytics.emit_mcp_active(uid="u1", **self._properties())
        assert redis.r.set.call_args.args[0].endswith(":20260728:u1")
        assert mcp_analytics._mcp_active_seen_day == "20260728"
        mcp_analytics.emit_mcp_active(uid="u1", **self._properties())
        assert redis.r.set.call_count == 2
        assert redis.r.set.call_args.args[0].endswith(":20260729:u1")


class TestPostHogKeyScoping:
    """``POSTHOG_EVENTS_API_KEY`` is scoped to MCP events only: generic capture
    keeps the project/legacy key resolution and rollout decisions never touch
    the events key."""

    def _reset(self, monkeypatch):
        import utils.integration_telemetry as it

        monkeypatch.setattr(it, "_posthog_client", None)
        monkeypatch.setattr(it, "_posthog_disabled", False)
        monkeypatch.setattr(mcp_analytics, "_mcp_events_client", None)
        monkeypatch.setattr(mcp_analytics, "_mcp_events_client_disabled", False)
        for name in ("POSTHOG_EVENTS_API_KEY", "POSTHOG_PROJECT_API_KEY", "POSTHOG_API_KEY"):
            monkeypatch.delenv(name, raising=False)
        return it

    def test_generic_capture_prefers_project_key(self, monkeypatch):
        it = self._reset(monkeypatch)
        monkeypatch.setenv("POSTHOG_EVENTS_API_KEY", "events-key")
        monkeypatch.setenv("POSTHOG_PROJECT_API_KEY", "project-key")
        build = MagicMock(side_effect=lambda key: f"client:{key}")
        monkeypatch.setattr(it, "_build_posthog_client", build)
        assert it._get_posthog_client() == "client:project-key"

    def test_generic_capture_falls_back_to_legacy_key(self, monkeypatch):
        it = self._reset(monkeypatch)
        monkeypatch.setenv("POSTHOG_API_KEY", "legacy-key")
        build = MagicMock(side_effect=lambda key: f"client:{key}")
        monkeypatch.setattr(it, "_build_posthog_client", build)
        assert it._get_posthog_client() == "client:legacy-key"

    def test_generic_capture_ignores_events_key(self, monkeypatch):
        """A non-MCP event never captures through the events key."""
        it = self._reset(monkeypatch)
        monkeypatch.setenv("POSTHOG_EVENTS_API_KEY", "events-key")
        build = MagicMock(side_effect=lambda key: f"client:{key}")
        monkeypatch.setattr(it, "_build_posthog_client", build)
        assert it._get_posthog_client() is None
        build.assert_not_called()

    def test_mcp_capture_uses_events_key(self, monkeypatch):
        self._reset(monkeypatch)
        monkeypatch.setenv("POSTHOG_EVENTS_API_KEY", "events-key")
        monkeypatch.setenv("POSTHOG_PROJECT_API_KEY", "project-key")
        fake = MagicMock()
        build = MagicMock(return_value=fake)
        monkeypatch.setattr(mcp_analytics, "_build_mcp_events_client", build)
        mcp_analytics.emit_mcp_posthog_event("u", "MCP Tool Call", {"tool": "get_memories"})
        build.assert_called_once_with("events-key")
        fake.capture.assert_called_once_with(
            distinct_id="u", event="MCP Tool Call", properties={"tool": "get_memories"}
        )

    def test_mcp_capture_falls_back_to_generic_emit(self, monkeypatch):
        """Without the events key, MCP events route through generic capture."""
        self._reset(monkeypatch)
        monkeypatch.setenv("POSTHOG_PROJECT_API_KEY", "project-key")
        generic = MagicMock()
        monkeypatch.setattr(mcp_analytics, "emit_posthog_event", generic)
        mcp_analytics.emit_mcp_posthog_event("u", "MCP Active", {"client_name": "other"})
        generic.assert_called_once_with("u", "MCP Active", {"client_name": "other"})

    def test_decision_code_is_project_key_only(self, monkeypatch):
        """The dead decisions helper is gone; jit_rollout builds its own client
        from POSTHOG_PROJECT_API_KEY and never reads the events key."""
        import utils.integration_telemetry as it
        import utils.jit_rollout as jr

        assert not hasattr(it, "get_posthog_client_for_decisions")
        self._reset(monkeypatch)
        monkeypatch.setenv("POSTHOG_EVENTS_API_KEY", "events-key")
        provider = jr.PostHogJITFlagProvider.__new__(jr.PostHogJITFlagProvider)
        provider._timeout_seconds = 1
        # Only the events key is present: no decision client may be built.
        assert provider._build_client() is None


class TestInitializeNegotiatedAnalytics:
    """With no header/_meta declaration, the analytics version follows the
    negotiated initialize result; request log and MCP Active stay in lockstep."""

    def test_initialize_requested_version_drives_analytics(self, client, authed):
        response = _post(client, "/v1/mcp", _msg("initialize", params={"protocolVersion": "2025-11-25"}))
        assert response.status_code == 200
        assert response.json()["result"]["protocolVersion"] == "2025-11-25"
        assert authed.request_log.call_args.kwargs["protocol_version"] == "2025-11-25"
        assert authed.active_event.call_args.kwargs["protocol_version"] == "2025-11-25"

    def test_unsupported_initialize_logs_negotiated_fallback(self, client, authed):
        _post(client, "/v1/mcp", _msg("initialize", params={"protocolVersion": "1999-01-01"}))
        assert authed.request_log.call_args.kwargs["protocol_version"] == NEGOTIATED_FALLBACK_VERSION
        assert authed.active_event.call_args.kwargs["protocol_version"] == NEGOTIATED_FALLBACK_VERSION

    def test_legacy_batch_initialize_logs_its_version(self, client, authed):
        _post(
            client,
            "/v1/mcp",
            [_msg("initialize", 1, params={"protocolVersion": "2025-03-26"}), _msg("ping", 2)],
        )
        assert authed.request_log.call_args.kwargs["protocol_version"] == "2025-03-26"
        assert authed.active_event.call_args.kwargs["protocol_version"] == "2025-03-26"

    def test_initialize_negotiated_result_beats_disagreeing_header(self, client, authed):
        response = _post(
            client,
            "/v1/mcp",
            _msg("initialize", params={"protocolVersion": "2025-11-25"}),
            **{"mcp-protocol-version": "2024-11-05"},
        )
        assert response.status_code == 200
        assert response.json()["result"]["protocolVersion"] == "2025-11-25"
        assert authed.request_log.call_args.kwargs["protocol_version"] == "2025-11-25"

    def test_explicit_meta_beats_initialize_request(self, client, authed):
        message = _msg(
            "initialize",
            params={
                "protocolVersion": "2025-03-26",
                "_meta": {META_PROTOCOL_VERSION: "2025-11-25"},
            },
        )
        _post(client, "/v1/mcp", message)
        assert authed.request_log.call_args.kwargs["protocol_version"] == "2025-11-25"


class TestRequestToolDimension:
    """``mcp_request.tool`` is populated only when the POST carries exactly one
    ``tools/call`` message; any other count would misattribute it."""

    def test_mixed_tool_batch_logs_unknown(self, client, authed):
        with patch.object(mcp_transport, "execute_tool", return_value={}):
            response = _post(
                client,
                "/v1/mcp",
                [_tool_call("get_memories", msg_id=1), _tool_call("get_people", msg_id=2)],
                **{"mcp-protocol-version": "2025-03-26"},
            )
        assert response.status_code == 200
        assert authed.request_log.call_args.kwargs["tool_name"] is None

    def test_single_tool_name_preserved(self, client, authed):
        with patch.object(mcp_transport, "execute_tool", return_value={}):
            _post(client, "/v1/mcp", _tool_call("get_people"))
        assert authed.request_log.call_args.kwargs["tool_name"] == "get_people"

    def test_tool_plus_ping_keeps_tool_name(self, client, authed):
        with patch.object(mcp_transport, "execute_tool", return_value={}):
            _post(
                client,
                "/v1/mcp",
                [_tool_call("get_people", msg_id=1), _msg("ping", 2)],
                **{"mcp-protocol-version": "2025-03-26"},
            )
        assert authed.request_log.call_args.kwargs["tool_name"] == "get_people"

    def test_same_tool_called_twice_logs_unknown(self, client, authed):
        with patch.object(mcp_transport, "execute_tool", return_value={}):
            response = _post(
                client,
                "/v1/mcp",
                [_tool_call("get_people", msg_id=1), _tool_call("get_people", msg_id=2)],
                **{"mcp-protocol-version": "2025-03-26"},
            )
        assert response.status_code == 200
        assert authed.request_log.call_args.kwargs["tool_name"] is None
