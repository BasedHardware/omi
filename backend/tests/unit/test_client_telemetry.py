"""Collector, dedup, aggregate and admin-auth coverage for client telemetry."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config.client_telemetry import (
    TelemetryContractError,
    add_histogram,
    aggregate_visible,
    empty_histogram,
    histogram_public,
    migration_flags,
    validate_batch,
)
from database import client_telemetry as store
from database.client_telemetry import (
    DAYS,
    DEDUP,
    accept_batch,
    dedup_document_id,
    load_day_merged,
    merge_day_for_query,
    observation_visible,
    purge_expired_aggregates,
    query_is_stale,
    seal_day,
)
from routers import client_telemetry as telemetry_router
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.fixtures.telemetry_memory_firestore import TelemetryMemoryFirestore
from utils.other.endpoints import get_current_user_uid

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
OWNER = "owner-a"
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "client_telemetry"
E1 = "11111111-1111-4111-8111-111111111111"
E2 = "33333333-3333-4333-8333-333333333333"
E3 = "99999999-9999-4999-8999-999999999999"
ATTEMPT = "22222222-2222-4222-8222-222222222222"
BATCH = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def _day_view(db, day="2026-10-12"):
    """Merged day view (summary + shards) for tests asserting aggregate content."""
    summary, shards = load_day_merged(db, day)
    assert summary is not None, f"day {day} not committed"
    return merge_day_for_query(summary, shards)


def _upload(event_id: str, phase: str, attempt: str = ATTEMPT, **extra):
    attributes = {"attempt_id": attempt, "phase": phase, "source": "pendant"}
    attributes.update(extra)
    return {
        "event_id": event_id,
        "occurred_at": "2026-10-12T11:00:00Z",
        "platform": "macos",
        "channel": "production",
        "family": "upload",
        "attributes": attributes,
    }


def _batch(*observations, batch_id: str = BATCH):
    return {"schema_version": 1, "batch_id": batch_id, "observations": list(observations)}


def _accept(db, payload, owner=OWNER, now=NOW):
    return accept_batch(owner, payload, firestore_client=db, now=now)


def test_migration_flags_default_off(monkeypatch):
    monkeypatch.delenv("CLIENT_TELEMETRY_TRANSPORT", raising=False)
    monkeypatch.delenv("CLIENT_TELEMETRY_READER", raising=False)
    monkeypatch.delenv("CLIENT_TELEMETRY_RETIREMENT", raising=False)
    assert migration_flags() == {"transport_shadow": False, "reader": False, "retirement": False}


def test_invalid_payloads_reject_the_whole_batch():
    db = TelemetryMemoryFirestore()
    future = (NOW + timedelta(minutes=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
    stale = (NOW - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cases = [
        _batch({**_upload(E1, "started"), "owner": "smuggled"}),
        _batch(
            {
                **_upload(E1, "started"),
                "attributes": {"attempt_id": ATTEMPT, "phase": "started", "source": "pendant", "note": "x"},
            }
        ),
        _batch(_upload(E1, "started", latency_ms=-1)),
        _batch(_upload(E1, "started", latency_ms=float("nan"))),
        _batch({**_upload(E1, "started"), "occurred_at": future}),
        _batch({**_upload(E1, "started"), "occurred_at": stale}),
        _batch(_upload(E1, "nope")),
        {"schema_version": 2, "batch_id": BATCH, "observations": [_upload(E1, "started")]},
    ]
    for payload in cases:
        with pytest.raises(TelemetryContractError) as raised:
            _accept(db, payload)
        assert raised.value.status in {422, 409}
    assert db.read_committed((DAYS, "2026-10-12")) is None


def test_observation_over_4kib_and_over_100_reject():
    huge = _upload(E1, "started")
    huge["attributes"]["blob"] = "x" * 5000
    with pytest.raises(TelemetryContractError) as raised:
        validate_batch(_batch(huge), NOW)
    assert "4 KiB" in raised.value.message
    observations = [
        _upload("11111111-1111-4111-8111-%012d" % index, "started", attempt=ATTEMPT) for index in range(101)
    ]
    with pytest.raises(TelemetryContractError) as raised:
        validate_batch(_batch(*observations), NOW)
    assert raised.value.status == 422


def test_partial_batch_is_atomic_and_replay_counts_reconcile():
    db = TelemetryMemoryFirestore()
    good = _upload(E1, "started")
    bad = _upload(E2, "started", source="not-a-source")
    with pytest.raises(TelemetryContractError):
        _accept(db, _batch(good, bad))
    assert db.read_committed((DAYS, "2026-10-12")) is None

    first = _accept(db, _batch(good, _upload(E2, "accepted")))
    assert first["accepted_count"] == 2 and first["duplicate_count"] == 0
    second = _accept(db, _batch(good, _upload(E3, "failed", attempt="33333333-3333-4333-8333-333333333333")))
    assert second["accepted_count"] == 1 and second["duplicate_count"] == 1
    assert second["accepted_count"] + second["duplicate_count"] == 2
    replay = _accept(db, _batch(good))
    assert replay["accepted_count"] == 0 and replay["duplicate_count"] == 1
    day = _day_view(db)
    counters = []
    for series in day["series"].values():
        counters.append(series["counters"].get("observations_total", 0))
    assert sum(counters) == 3


def test_conflicting_payload_is_permanent_and_does_not_double_count():
    db = TelemetryMemoryFirestore()
    _accept(db, _batch(_upload(E1, "started")))
    conflict = _accept(db, _batch(_upload(E1, "started", source="phone")))
    assert conflict["status"] == 409
    day = _day_view(db)
    observations = sum(series["counters"]["observations_total"] for series in day["series"].values())
    assert observations == 1


def test_owner_isolation_and_voice_populations():
    db = TelemetryMemoryFirestore()
    payload = json.loads((FIXTURES / "payloads.json").read_text())["valid_mixed"]
    first = _accept(db, payload, owner="owner-a")
    second = _accept(db, payload, owner="owner-b")
    assert first["accepted_count"] == 5
    assert second["accepted_count"] == 5
    assert dedup_document_id("owner-a", E1) != dedup_document_id("owner-b", E1)
    seal_day("2026-10-12", firestore_client=db, now=NOW)
    response, stale = query_is_stale(
        days=1,
        channel="production",
        firestore_client=db,
        now=NOW,
        channel_by_actor={"owner-a": "production", "owner-b": "production"},
    )
    assert stale is False
    assert response["available"] is True
    assert response["partial"] is False
    populations = {row["population"] for row in response["voice_rows"]}
    assert populations == {"physical_shortcut", "floating_voice"}
    assert {row["actor_id"] for row in response["voice_rows"]} == {"owner-a", "owner-b"}
    started = sum(
        series["counters"].get("started_total", 0)
        for series in _day_view(db)["series"].values()
        if series["family"] == "upload"
    )
    completed = sum(series["counters"].get("request_completed_total", 0) for series in _day_view(db)["series"].values())
    assert started == 2 and completed == 2


def test_upload_conservation_and_histogram():
    db = TelemetryMemoryFirestore()
    attempts = [
        "22222222-2222-4222-8222-222222222221",
        "22222222-2222-4222-8222-222222222222",
        "22222222-2222-4222-8222-222222222223",
        "22222222-2222-4222-8222-222222222224",
        "22222222-2222-4222-8222-222222222225",
    ]
    events = ["11111111-1111-4111-8111-%012d" % index for index in range(1, 11)]
    observations = [
        _upload(events[0], "started", attempts[0]),
        _upload(events[1], "accepted", attempts[0]),
        _upload(events[2], "completed", attempts[0], latency_ms=1000),
        _upload(events[3], "started", attempts[1]),
        _upload(events[4], "completed", attempts[1], latency_ms=40),
        _upload(events[5], "started", attempts[2]),
        _upload(events[6], "failed", attempts[2], failure_class="timeout"),
        _upload(events[7], "started", attempts[3]),
        _upload(events[8], "deferred", attempts[3], failure_class="rate_limited"),
        _upload(events[9], "started", attempts[4]),
    ]
    result = _accept(db, _batch(*observations))
    assert result["accepted_count"] == 10
    day = _day_view(db)
    totals = {}
    latency = None
    for series in day["series"].values():
        for name, value in series["counters"].items():
            totals[name] = totals.get(name, 0) + value
        hist = series["durations"].get("latency_ms")
        if hist:
            latency = hist if latency is None else latency
            if latency is not hist:
                latency = {
                    "count": latency["count"] + hist["count"],
                    "sum_ms": latency["sum_ms"] + hist["sum_ms"],
                    "buckets": [a + b for a, b in zip(latency["buckets"], hist["buckets"])],
                    "session": False,
                }
    assert totals["started_total"] == 5
    assert totals["request_completed_total"] == 1
    assert totals["accepted_total"] == 1
    assert totals["accepted_completed_total"] == 1
    assert totals["pending_accepted_total"] == 0
    assert totals["failed_total"] == 1
    assert totals["deferred_total"] == 1
    unresolved = (
        totals["started_total"]
        - totals["request_completed_total"]
        - totals["accepted_total"]
        - totals["failed_total"]
        - totals["deferred_total"]
    )
    assert unresolved == 1
    public = histogram_public(latency)
    counts = [bucket["count"] for bucket in public["buckets"]]
    assert counts == sorted(counts)
    assert public["buckets"][-1]["le_seconds"] == "+Inf"
    assert public["buckets"][-1]["count"] == public["count"] == 2
    assert public["sum_ms"] == 1040
    assert all(bucket["count"] <= public["count"] for bucket in public["buckets"])


def test_histogram_ignores_absent_and_screen_stage_zero():
    hist = empty_histogram()
    add_histogram(hist, 40)
    before = hist["count"]
    assert before == 1
    screen = {
        "event_id": "12121212-1212-4212-8212-121212121212",
        "occurred_at": "2026-10-12T11:00:00Z",
        "platform": "macos",
        "channel": "production",
        "family": "screen_task",
        "attributes": {
            "operation_id": "13131313-1313-4313-8313-131313131313",
            "schema_version": 2,
            "pipeline": "screen_task_v2",
            "gate_outcome": "passed",
            "audit_sample": False,
            "extractor": "gemini_3_8",
            "outcome": "completed",
            "error_class": "none",
            "fallback_reason": "none",
            "eligible_frames": 1,
            "feature_enabled_at_start": True,
            "client_bypass": False,
            "invalid_items": 0,
            "gate_attempts": 1,
            "extraction_attempts": 1,
            "legacy_attempts": 0,
            "policy_rejected": 0,
            "outbox_saved": 1,
            "coalesced": 0,
            "pending_delivered": 0,
            "failed": 0,
            "ocr_ms": 0,
            "extraction_ms": 25,
        },
    }
    db = TelemetryMemoryFirestore()
    _accept(db, _batch(screen))
    day = _day_view(db)
    series = next(iter(day["series"].values()))
    assert "ocr_ms" not in series["durations"]
    assert series["durations"]["extraction_ms"]["count"] == 1
    assert series["counters"]["eligible_frames_total"] == 1
    assert series["counters"]["observations_total"] == 1


def test_capture_ingress_native_phases_pass_through_without_bucketing():
    for phase in ["inactive", "unverified", "flowing", "quiet", "repairing", "reconnecting", "action_required"]:
        observation = {
            "event_id": "14141414-1414-4414-8414-141414141414",
            "occurred_at": "2026-10-12T11:00:00Z",
            "platform": "ios",
            "channel": "production",
            "family": "capture_ingress",
            "attributes": {
                "operation_id": ATTEMPT,
                "phase": phase,
                "reason": "none",
                "subscription_confirmed": True,
                "recovery_outcome": "none",
                "recovery_spent": False,
                "reconnect_spent": False,
            },
        }
        _, normalized = validate_batch(_batch(observation), NOW)
        assert normalized[0]["dimensions"]["phase"] == phase


def test_aliases_bucket_unknown_without_rejecting_the_batch():
    observation = {
        "event_id": E1,
        "occurred_at": "2026-10-12T11:00:00Z",
        "platform": "ios",
        "channel": "beta",
        "family": "capture_ingress",
        "attributes": {
            "operation_id": ATTEMPT,
            "phase": "actionRequired",
            "reason": "capture_denied",
            "subscription_confirmed": False,
            "recovery_outcome": "fresh_subscription_confirmed",
            "recovery_spent": False,
            "reconnect_spent": False,
        },
    }
    _, normalized = validate_batch(_batch(observation), NOW)
    assert normalized[0]["dimensions"]["phase"] == "action_required"
    assert normalized[0]["dimensions"]["reason"] == "unknown"
    assert normalized[0]["dimensions"]["recovery_outcome"] == "unknown"
    wedge = {
        "event_id": E2,
        "occurred_at": "2026-10-12T11:00:00Z",
        "platform": "android",
        "channel": "production",
        "family": "capture_wedge",
        "attributes": {
            "operation_id": ATTEMPT,
            "phase": "detected",
            "trigger": "rapid_reconnects",
            "outcome": "pending",
        },
    }
    _, wedge_rows = validate_batch(_batch(wedge), NOW)
    assert wedge_rows[0]["dimensions"]["trigger"] == "rapid_reconnect"


def test_dedup_ttl_and_aggregate_retention_filter():
    db = TelemetryMemoryFirestore()
    _accept(db, _batch(_upload(E1, "started")))
    planted = db.read_committed((DEDUP, dedup_document_id(OWNER, E1)))
    planted["expires_at"] = "2026-10-12T11:00:00Z"
    db.plant(DEDUP, dedup_document_id(OWNER, E1), planted)
    again = _accept(db, _batch(_upload(E1, "started")))
    assert again["accepted_count"] == 1
    fresh = TelemetryMemoryFirestore()
    _accept(fresh, _batch(_upload(E1, "started")))
    recent = fresh.read_committed((DEDUP, dedup_document_id(OWNER, E1)))
    recent["expires_at"] = (NOW + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    fresh.plant(DEDUP, dedup_document_id(OWNER, E1), recent)
    replay = _accept(fresh, _batch(_upload(E1, "started")), now=NOW + timedelta(minutes=30))
    assert replay["duplicate_count"] == 1 and replay["accepted_count"] == 0
    assert aggregate_visible("2026-07-13", NOW) is False
    assert aggregate_visible("2026-10-12", NOW) is True
    old = {
        "schema_version": 1,
        "day": "2026-07-01",
        "rollup_sealed": True,
        "sealed_at": "2026-07-02T00:00:00Z",
        "accepted_observations": 4,
        "accepted_batches": 1,
        "last_accepted_at": "2026-07-01T00:00:00Z",
        "series": {},
        "voice": {},
    }
    db.plant(DAYS, "2026-07-01", old)
    removed = purge_expired_aggregates(firestore_client=db, now=NOW)
    assert "2026-07-01" in removed
    assert db.read_committed((DAYS, "2026-07-01")) is None
    hidden, _stale = query_is_stale(
        days=1, channel="all", firestore_client=db, now=datetime(2026, 10, 1, tzinfo=timezone.utc)
    )
    assert all(row["day"] != "2026-07-01" for row in hidden["rows"])
    assert observation_visible({"expires_at": "2026-09-01T00:00:00Z"}, NOW) is False


def test_rate_limit_and_concurrency():
    db = TelemetryMemoryFirestore()
    for index in range(10):
        event = "11111111-1111-4111-8111-%012d" % (index + 1)
        _accept(db, _batch(_upload(event, "started"), batch_id="bbbbbbbb-bbbb-4bbb-8bbb-%012d" % index))
    with pytest.raises(TelemetryContractError) as raised:
        _accept(db, _batch(_upload(E3, "started"), batch_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc"))
    assert raised.value.status == 429
    assert raised.value.retry_after is not None
    assert db.read_committed((DEDUP, dedup_document_id(OWNER, E3))) is None
    later = _accept(
        db,
        _batch(_upload(E3, "started"), batch_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc"),
        now=NOW + timedelta(seconds=61),
    )
    assert later["accepted_count"] == 1

    raced = TelemetryMemoryFirestore()
    payload = _batch(_upload(E1, "started"))

    def once():
        return _accept(raced, payload)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _index: once(), range(8)))
    accepted = [item for item in results if item.get("status") == 200 and item["accepted_count"] == 1]
    duplicates = [item for item in results if item.get("status") == 200 and item["duplicate_count"] == 1]
    assert len(accepted) == 1
    assert len(accepted) + len(duplicates) == 8
    day = _day_view(raced)
    assert sum(series["counters"]["observations_total"] for series in day["series"].values()) == 1

    conflicted = TelemetryMemoryFirestore()

    def left():
        return _accept(conflicted, _batch(_upload(E1, "started", source="pendant")))

    def right():
        return _accept(conflicted, _batch(_upload(E1, "started", source="phone")))

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [pool.submit(left).result(), pool.submit(right).result()]
    statuses = sorted(item["status"] for item in outcomes)
    assert statuses == [200, 409]
    day = _day_view(conflicted)
    assert sum(series["counters"]["observations_total"] for series in day["series"].values()) == 1


def test_strict_firestore_read_before_write_and_replay():
    db = StrictFirestore()
    first = _accept(db, _batch(_upload(E1, "started")))
    assert first["accepted_count"] == 1
    second = _accept(db, _batch(_upload(E1, "started")))
    assert second["duplicate_count"] == 1
    assert any(transaction.sets for transaction in db.transactions)


def test_coverage_unavailable_partial_and_truncation(monkeypatch):
    empty = TelemetryMemoryFirestore()
    unsealed, stale = query_is_stale(days=1, channel="all", firestore_client=empty, now=NOW)
    assert unsealed["available"] is False and unsealed["partial"] is True and unsealed["rows"] == []
    assert stale is False

    sealed_empty = TelemetryMemoryFirestore()
    seal_day("2026-10-12", firestore_client=sealed_empty, now=NOW)
    healthy, _stale = query_is_stale(days=1, channel="all", firestore_client=sealed_empty, now=NOW)
    assert healthy["available"] is True and healthy["partial"] is False and healthy["rows"] == []
    assert healthy["coverage_start"] == "2026-10-12"
    assert healthy["complete_through"] == "2026-10-12"

    mismatched = TelemetryMemoryFirestore()
    voice = {
        "event_id": E1,
        "occurred_at": "2026-10-12T11:00:00Z",
        "platform": "macos",
        "channel": "beta",
        "family": "voice_turn",
        "attributes": {
            "operation_id": ATTEMPT,
            "phase": "terminal",
            "population": "physical_shortcut",
            "route": "hub",
            "intent": "hold",
            "outcome": "success",
            "reason": "success",
            "latency_ms": 10,
        },
    }
    _accept(mismatched, _batch(voice))
    seal_day("2026-10-12", firestore_client=mismatched, now=NOW)
    excluded, _stale = query_is_stale(
        days=1,
        channel="all",
        firestore_client=mismatched,
        now=NOW,
        channel_by_actor={OWNER: "production"},
    )
    assert excluded["voice_rows"] == []
    assert excluded["partial"] is True

    class Broken:
        def collection(self, _name):
            raise RuntimeError("store down")

    with pytest.raises(TelemetryContractError) as raised:
        query_is_stale(days=1, channel="all", firestore_client=Broken(), now=NOW)
    assert raised.value.status == 503 and raised.value.code == "telemetry_unavailable"

    monkeypatch.setattr("config.client_telemetry.MAX_QUERY_ROWS", 0)
    seeded = TelemetryMemoryFirestore()
    _accept(seeded, _batch(_upload(E1, "started")))
    seal_day("2026-10-12", firestore_client=seeded, now=NOW)
    with pytest.raises(TelemetryContractError) as raised:
        query_is_stale(days=1, channel="all", firestore_client=seeded, now=NOW)
    assert raised.value.code == "telemetry_query_truncated"


def test_fixture_query_shape_is_stable():
    db = TelemetryMemoryFirestore()
    payload = json.loads((FIXTURES / "payloads.json").read_text())["valid_mixed"]
    _accept(db, payload)
    seal_day("2026-10-12", firestore_client=db, now=NOW)
    response, stale = query_is_stale(
        days=1,
        channel="production",
        firestore_client=db,
        now=NOW,
        channel_by_actor={OWNER: "production"},
    )
    assert stale is False
    golden_path = FIXTURES / "query_response.json"
    golden = json.loads(golden_path.read_text())
    assert response == golden


def _app(owner: str | None):
    app = FastAPI()
    app.include_router(telemetry_router.router)
    if owner is not None:
        app.dependency_overrides[get_current_user_uid] = lambda: owner
    return app


def test_http_auth_size_and_admin_gate(monkeypatch):
    db = TelemetryMemoryFirestore()
    monkeypatch.setattr(store, "get_firestore_client", lambda: db)
    monkeypatch.setenv("ADMIN_KEY", "test-admin-key-value-0123456789")
    authed = TestClient(_app(OWNER))
    # Route uses the real wall clock; stamp the fixture within MAX_EVENT_AGE.
    fresh = (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = _batch(_upload(E1, "started"))
    payload["observations"][0]["occurred_at"] = fresh
    created = authed.post("/v1/telemetry/client/batches", json=payload)
    assert created.status_code == 200
    body = created.json()
    assert body["accepted_count"] == 1 and body["duplicate_count"] == 0
    assert set(body) == {"schema_version", "batch_id", "accepted_count", "duplicate_count"}

    anonymous = TestClient(_app(None))
    assert anonymous.post("/v1/telemetry/client/batches", json=payload).status_code == 401

    oversized = authed.post("/v1/telemetry/client/batches", content=b"{" + b"x" * (128 * 1024))
    assert oversized.status_code == 413
    assert oversized.json()["detail"]["code"] == "telemetry_too_large"

    user = authed.get("/v1/telemetry/client/aggregates", params={"days": 1, "channel": "production"})
    assert user.status_code == 403
    admin = authed.get(
        "/v1/telemetry/client/aggregates",
        params={"days": 1, "channel": "production"},
        headers={"X-Admin-Key": "test-admin-key-value-0123456789"},
    )
    assert admin.status_code == 200
    assert admin.json()["available"] is False
    wrong = authed.get(
        "/v1/telemetry/client/aggregates",
        params={"days": 1, "channel": "production"},
        headers={"X-Admin-Key": "nope"},
    )
    assert wrong.status_code == 403


def test_router_is_registered_on_the_backend_app():
    # main.py mounts through the B8 role map; read its ROUTER_MOUNTS rows structurally (AST, not an
    # import: importing app_roles loads every router, too slow for a fast unit test).
    import ast

    role_map = ast.parse((Path(__file__).resolve().parents[2] / "app_roles.py").read_text())
    mounts = {
        (node.args[0].id, next((k.value.value for k in node.keywords if k.arg == "attr"), "router"))
        for node in ast.walk(role_map)
        if isinstance(node, ast.Call)
        and getattr(node.func, "id", None) == "Mount"
        and node.args
        and isinstance(node.args[0], ast.Name)
    }
    assert ("client_telemetry", "router") in mounts


def test_session_histogram_adds_the_week_bucket():
    hist = empty_histogram(session=True)
    add_histogram(hist, 100_000_000)
    public = histogram_public(hist)
    edges = [bucket["le_seconds"] for bucket in public["buckets"]]
    assert 604800.0 in edges
    assert public["buckets"][-1]["count"] == 1
    week = next(bucket for bucket in public["buckets"] if bucket["le_seconds"] == 604800.0)
    day = next(bucket for bucket in public["buckets"] if bucket["le_seconds"] == 86400.0)
    assert day["count"] == 0 and week["count"] == 1


def test_fallback_dimensions_bucket_to_registered_allowlists():
    """sol blocker: open-string fallback dimensions must bound to registered sets."""
    import datetime as _dt

    from config.client_telemetry import validate_batch

    moment = _dt.datetime(2026, 10, 13, tzinfo=_dt.timezone.utc)

    def _obs(event_hex, from_v, to_v, reason_v):
        return {
            "event_id": f"{event_hex}-1111-4111-8111-111111111111",
            "occurred_at": "2026-10-13T00:00:00Z",
            "platform": "macos",
            "channel": "production",
            "family": "fallback",
            "attributes": {
                "operation_id": f"{event_hex}-2222-4222-8222-222222222222",
                "area": "realtime_hub",
                "from": from_v,
                "to": to_v,
                "reason": reason_v,
                "outcome": "degraded",
            },
        }

    _, observations = validate_batch(
        {
            "schema_version": 1,
            "batch_id": "33333333-3333-4333-8333-333333333333",
            "observations": [
                _obs("44444444", "customer-123456", "gemini", "unique-error-789"),
                _obs("55555555", "hub", "deepgram", "gate_invalid_response"),
            ],
        },
        moment,
    )
    bad, good = observations[0], observations[1]
    assert bad["dimensions"]["from"] == "unknown"
    assert bad["dimensions"]["reason"] == "unknown"
    assert good["dimensions"]["from"] == "hub"
    assert good["dimensions"]["to"] == "deepgram"
    assert good["dimensions"]["reason"] == "gate_invalid_response"


def test_voice_actor_capacity_sharded_across_documents(monkeypatch):
    """sol blocker: 2,008 voice actors must not fill any single aggregate document.

    The legacy layout kept every voice row in one UTC-day document and its
    900KB guard rejected whole batches once ~2,008 actors contributed. Under
    the sharded layout each batch maps to bounded shards and the summary stays
    small; this test drives 2,200 single-observation voice batches and asserts
    every batch is accepted and no stored document approaches the guard.
    """
    import uuid as _uuid

    monkeypatch.setattr("config.client_telemetry.RATE_LIMIT_BATCHES", 10**9)
    db = TelemetryMemoryFirestore()

    def _voice_event(n: int) -> dict:
        return {
            "event_id": str(_uuid.UUID(int=n)),
            "occurred_at": "2026-10-12T11:00:00Z",
            "platform": "macos",
            "channel": "production",
            "family": "voice_turn",
            "attributes": {
                "operation_id": str(_uuid.UUID(int=n + 10_000)),
                "phase": "terminal",
                "population": "physical_shortcut",
                "route": "hub",
                "intent": "hold",
                "outcome": "success",
                "latency_ms": 1000 + n,
            },
        }

    # capacity property is per UTC day: keep every event on one day and lift
    # the per-owner batch rate limit for the duration of the test.
    for n in range(2200):
        result = _accept(db, _batch(_voice_event(n), batch_id=str(_uuid.UUID(int=n + 100_000))))
        assert result["status"] == 200, f"batch {n} rejected: {result}"

    summary, shards = load_day_merged(db, "2026-10-12")
    assert summary is not None
    assert len(shards) > 1, "expected the 2,200 actors to spread across multiple shards"
    for shard_id, shard in shards.items():
        size = len(repr(shard).encode("utf-8"))
        assert size < 900_000, f"shard {shard_id} too large: {size}"
    summary_size = len(repr(summary).encode("utf-8"))
    assert summary_size < 900_000, f"summary too large: {summary_size}"
    merged = _day_view(db)
    total_voice = sum(row["count"] for row in merged["voice"].values())
    assert total_voice == 2200
    # query path still returns every actor's row after the merge
    # (unclassified roster: raw rows returned, feed honestly partial)
    response, stale = query_is_stale(days=1, channel="production", firestore_client=db, now=NOW, channel_by_actor=None)
    assert stale is False
    assert sum(row["count"] for row in response["voice_rows"]) == 2200


def test_seal_settled_day_guardrails_and_roster_exclusion(monkeypatch):
    import pytest as _pytest

    from config.client_telemetry import TelemetryContractError
    from database.client_telemetry_ops import (
        channel_roster,
        enroll_channel,
        purge_expired_observations,
        seal_settled_day,
    )

    db = TelemetryMemoryFirestore()
    payload = json.loads((FIXTURES / "payloads.json").read_text())["valid_mixed"]
    _accept(db, payload)

    # refusal: unsettled day (today from NOW's perspective is 2026-10-12)
    with _pytest.raises(TelemetryContractError) as raised:
        seal_settled_day("2026-10-12", firestore_client=db, now=NOW)
    assert raised.value.code == "telemetry_invalid"

    # refusal: late arrival refreshes yesterday's day doc, then sealing within
    # STALE_AFTER conflicts. Late event: occurred Oct 12 23:30, accepted Oct 13 00:10.
    late_observations = json.loads((FIXTURES / "payloads.json").read_text())["valid_mixed"]["observations"]
    late_event = dict(late_observations[0])
    late_event["event_id"] = E3
    late_event["occurred_at"] = "2026-10-12T23:30:00Z"
    late_now = NOW + timedelta(hours=12, minutes=10)
    _accept(db, _batch(late_event, batch_id=E3.replace("9", "b")), now=late_now)
    with _pytest.raises(TelemetryContractError) as raised:
        seal_settled_day("2026-10-12", firestore_client=db, now=late_now + timedelta(minutes=2))
    assert raised.value.code == "telemetry_conflict"

    # idempotent success after writes settle, twice
    settled = NOW + timedelta(days=2)
    first = seal_settled_day("2026-10-12", firestore_client=db, now=settled)
    assert first["rollup_sealed"] is True
    second = seal_settled_day("2026-10-12", firestore_client=db, now=settled + timedelta(hours=4))
    assert second["rollup_sealed"] is True

    # roster: absent roster -> query stays partial; present roster -> unmatched actors excluded
    view = _day_view(db)
    actors = {row["actor_id"] for row in view.get("voice", {}).values()}
    assert actors, "fixture must produce voice rows"
    response, _ = query_is_stale(days=3, channel="all", firestore_client=db, now=settled, channel_by_actor=None)
    assert response["partial"] is True
    enroll_channel(sorted(actors)[0], "production", firestore_client=db, now=settled)
    db.plant("client_telemetry_channel_roster", "__anchor__", {"seeded": True})
    mapping = channel_roster(set(actors), firestore_client=db)
    assert sorted(actors)[0] in mapping
    response, _ = query_is_stale(days=3, channel="all", firestore_client=db, now=settled, channel_by_actor=mapping)
    returned_actors = {row["actor_id"] for row in response["voice_rows"]}
    assert sorted(actors)[0] in returned_actors or not actors
    unmatched = {a for a in actors if a not in mapping}
    assert returned_actors.isdisjoint(unmatched)

    # purge: expired observation docs are physically removed
    dead = dedup_document_id("owner-a", E1)
    doc = db.read_committed(("client_telemetry_observations", dead))
    if doc is not None:
        db.plant(
            "client_telemetry_observations",
            dead,
            {**doc, "expires_at": "2026-10-01T00:00:00Z"},
        )
        removed = purge_expired_observations(firestore_client=db, now=settled)
        assert sum(removed.values()) >= 1
        assert db.read_committed(("client_telemetry_observations", dead)) is None
