from datetime import datetime, timezone

from database.v17_vector_repair_outbox_telemetry import (
    V17VectorRepairOutboxTelemetryConfig,
    emit_v17_vector_repair_outbox_worker_telemetry,
)
from database.v17_vector_repair_outbox_worker import (
    V17VectorRepairOutboxWorkerTickConfig,
    run_v17_vector_repair_outbox_worker_tick,
)
from tests.unit.test_v17_vector_repair_outbox_worker import _FakeFirestore, _record, _live_item


def _summary(**overrides):
    data = {
        "enabled": True,
        "worker_id": "worker-a",
        "uid": "user-secret",
        "leased_count": 3,
        "processed_count": 1,
        "skipped_count": 1,
        "failed_count": 1,
        "ack_failed_count": 1,
        "actions": [
            {"record_id": "rec-delete", "idempotency_key": "idem-delete", "action": "delete"},
            {"record_id": "rec-repair", "idempotency_key": "idem-repair", "action": "repair"},
        ],
        "errors": [
            {"stage": "ack", "record_id": "rec-secret", "error": "Pinecone timeout for vector vec-secret"},
            {"stage": "process", "error": "deadline exceeded"},
        ],
    }
    data.update(overrides)
    return data


def test_telemetry_emits_low_cardinality_metrics_and_events_without_identifiers():
    emitted = []

    result = emit_v17_vector_repair_outbox_worker_telemetry(
        tick_summary=_summary(),
        backlog={"pending_count": 12, "dead_letter_count": 2, "oldest_pending_age_seconds": 901},
        duration_ms=1234,
        emitter=lambda payload: emitted.append(payload),
        config=V17VectorRepairOutboxTelemetryConfig(enabled=True),
    )

    assert result == {"enabled": True, "emitted_count": len(emitted), "failed_count": 0, "errors": []}
    metric_names = {payload["name"] for payload in emitted if payload["kind"] == "metric"}
    assert {
        "v17_vector_repair_outbox_worker_records_total",
        "v17_vector_repair_outbox_worker_action_total",
        "v17_vector_repair_outbox_worker_retry_total",
        "v17_vector_repair_outbox_worker_dead_letter_total",
        "v17_vector_repair_outbox_worker_ack_failure_total",
        "v17_vector_repair_outbox_worker_backlog_count",
        "v17_vector_repair_outbox_worker_oldest_pending_age_seconds",
        "v17_vector_repair_outbox_worker_duration_ms",
    }.issubset(metric_names)
    event_names = {payload["name"] for payload in emitted if payload["kind"] == "event"}
    assert {"v17_vector_repair_outbox_worker_ack_failure", "v17_vector_repair_outbox_worker_dead_letter"}.issubset(
        event_names
    )

    forbidden_values = {
        "user-secret",
        "worker-a",
        "rec-delete",
        "rec-repair",
        "rec-secret",
        "idem-delete",
        "vec-secret",
    }
    rendered = repr(emitted)
    for forbidden in forbidden_values:
        assert forbidden not in rendered
    for payload in emitted:
        assert set(payload["labels"]).issubset({"worker_component", "status", "action", "reason", "event_type"})


def test_telemetry_disabled_is_noop_even_with_emitter():
    emitted = []

    result = emit_v17_vector_repair_outbox_worker_telemetry(
        tick_summary=_summary(),
        emitter=lambda payload: emitted.append(payload),
        config=V17VectorRepairOutboxTelemetryConfig(enabled=False),
    )

    assert result == {"enabled": False, "emitted_count": 0, "failed_count": 0, "errors": []}
    assert emitted == []


def test_telemetry_emitter_failures_are_recorded_without_raising():
    def failing_emitter(payload):
        raise RuntimeError(f"telemetry sink unavailable for {payload['name']}")

    result = emit_v17_vector_repair_outbox_worker_telemetry(
        tick_summary=_summary(),
        emitter=failing_emitter,
        config=V17VectorRepairOutboxTelemetryConfig(enabled=True),
    )

    assert result["enabled"] is True
    assert result["emitted_count"] == 0
    assert result["failed_count"] > 0
    assert result["errors"][0] == {
        "stage": "telemetry",
        "name": "v17_vector_repair_outbox_worker_records_total",
        "error": "telemetry sink unavailable for v17_vector_repair_outbox_worker_records_total",
    }


def test_worker_tick_telemetry_failure_does_not_mask_worker_cleanup_result():
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    db = _FakeFirestore(
        {
            "users/u1/memory_outbox/repair": _record(
                record_id="repair",
                idempotency_key="repair-key",
                outbox_path="users/u1/memory_outbox/repair",
                available_at=now.isoformat(),
            )
        }
    )

    result = run_v17_vector_repair_outbox_worker_tick(
        db_client=db,
        uid="u1",
        config=V17VectorRepairOutboxWorkerTickConfig(enabled=True, worker_id="worker-a", limit=10),
        authoritative_item_loader=lambda record: _live_item(memory_id=record["memory_id"]),
        vector_deleter=lambda record: None,
        vector_repairer=lambda record, item: None,
        now=now,
        telemetry_emitter=lambda payload: (_ for _ in ()).throw(RuntimeError("central metrics outage")),
        telemetry_config=V17VectorRepairOutboxTelemetryConfig(enabled=True),
    )

    assert db.store["users/u1/memory_outbox/repair"]["status"] == "completed"
    assert result["processed_count"] == 1
    assert result["failed_count"] == 0
    assert result["telemetry"]["failed_count"] > 0
    assert result["errors"] == []
