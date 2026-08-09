"""Tests for scheduled canonical Short-term maintenance orchestration."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from models.memory_recurrence import CanonicalRecurrenceSignal
from models.product_memory import MemoryItem
from utils.memory import canonical_short_term_maintenance_cron as cron
from utils.memory.canonical_consolidation import ConsolidationReport
from utils.memory.canonical_required_processing import RequiredMemoryProcessingReport
from utils.memory.short_term_promotion import (
    CanonicalShortTermMaintenanceReport as MaintenanceReport,
)

NOW = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
CANONICAL_A = "uid-canonical-a"
CANONICAL_B = "uid-canonical-b"


def _enable_for(monkeypatch, *uids: str) -> None:
    monkeypatch.setenv(cron.MEMORY_CANONICAL_MAINTENANCE_ENABLED_ENV, "true")
    monkeypatch.setattr(cron, "list_canonical_cohort_uids", lambda: list(uids))
    monkeypatch.setattr(
        cron,
        "run_canonical_cohort_lifecycle",
        lambda **_kwargs: SimpleNamespace(
            write_enrolled_uids=(),
            backfill=SimpleNamespace(summary=SimpleNamespace(read_ready_count=0)),
            backfill_ready_uids=tuple(uids),
            generation_reconciled_uids=(),
            generation_reconcile_errors=(),
        ),
    )


def test_disabled_cohort_runner_returns_empty_summary_without_running_maintenance(
    monkeypatch,
):
    monkeypatch.setenv(cron.MEMORY_CANONICAL_MAINTENANCE_ENABLED_ENV, "false")
    list_uids = MagicMock(return_value=[CANONICAL_A])
    run_maintenance = MagicMock()
    monkeypatch.setattr(cron, "list_canonical_cohort_uids", list_uids)
    monkeypatch.setattr(cron, "run_canonical_short_term_maintenance", run_maintenance)

    summary = cron.run_canonical_short_term_maintenance_for_cohort(
        db_client=object(),
        now=NOW,
        run_id="cron-disabled",
    )

    assert summary == cron.CanonicalShortTermMaintenanceCronSummary(run_id="cron-disabled")
    list_uids.assert_not_called()
    run_maintenance.assert_not_called()


def test_enabled_cohort_runs_lifecycle_before_maintenance(monkeypatch):
    _enable_for(monkeypatch, CANONICAL_A)
    lifecycle_report = SimpleNamespace(
        write_enrolled_uids=(CANONICAL_A,),
        backfill=SimpleNamespace(summary=SimpleNamespace(read_ready_count=1)),
        backfill_ready_uids=(CANONICAL_A,),
        generation_reconciled_uids=(CANONICAL_A,),
        generation_reconcile_errors=(),
    )
    lifecycle_calls = []
    monkeypatch.setattr(
        cron,
        "run_canonical_cohort_lifecycle",
        lambda **kwargs: lifecycle_calls.append(kwargs) or lifecycle_report,
    )
    monkeypatch.setattr(
        cron,
        "run_canonical_short_term_maintenance",
        lambda uid, **_kwargs: MaintenanceReport(uid=uid),
    )
    client = object()

    summary = cron.run_canonical_short_term_maintenance_for_cohort(
        db_client=client,
        now=NOW,
        run_id="cron-lifecycle",
    )

    assert lifecycle_calls == [{"db_client": client}]
    assert summary.lifecycle_write_enrolled_total == 1
    assert summary.lifecycle_backfill_read_ready_total == 1
    assert summary.lifecycle_generation_reconciled_total == 1


def test_lifecycle_failure_blocks_graph_staging_but_not_per_user_maintenance(monkeypatch):
    _enable_for(monkeypatch, CANONICAL_A)
    maintenance = MagicMock(side_effect=lambda uid, **_kwargs: MaintenanceReport(uid=uid))
    monkeypatch.setattr(cron, "run_canonical_cohort_lifecycle", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError()))
    monkeypatch.setattr(cron, "run_canonical_short_term_maintenance", maintenance)

    summary = cron.run_canonical_short_term_maintenance_for_cohort(now=NOW, run_id="cron-lifecycle-failure")

    assert summary.errors == ["canonical_cohort_lifecycle:RuntimeError"]
    maintenance.assert_called_once()


def test_enabled_cohort_graph_backfill_uses_the_fenced_bounded_runner(monkeypatch):
    _enable_for(monkeypatch, CANONICAL_A)
    monkeypatch.setenv(cron.MEMORY_CANONICAL_GRAPH_BACKFILL_ENABLED_ENV, "true")
    client = object()
    monkeypatch.setattr(
        cron,
        "run_canonical_short_term_maintenance",
        lambda uid, **_kwargs: MaintenanceReport(uid=uid),
    )
    graph_calls: list[dict[str, object]] = []

    def run_graph_enrichment(**kwargs: object) -> dict[str, object]:
        graph_calls.append(kwargs)
        return {"outcomes": {"committed": 3}}

    monkeypatch.setattr(cron, "run_enrichment", run_graph_enrichment)

    summary = cron.run_canonical_short_term_maintenance_for_cohort(
        db_client=client,
        now=NOW,
        run_id="cron-graph-backfill",
    )

    assert summary.graph_enriched_total == 3
    assert summary.graph_enrichment_blocked_total == 0
    assert len(graph_calls) == 1
    assert graph_calls[0]["uid"] == CANONICAL_A
    assert graph_calls[0]["db_client"] is client
    assert graph_calls[0]["apply"] is True
    assert graph_calls[0]["confirm_uid"] == CANONICAL_A
    assert graph_calls[0]["limit"] == cron.DEFAULT_GRAPH_BACKFILL_PAGE_SIZE
    assert graph_calls[0]["apply_limit"] == cron.DEFAULT_GRAPH_BACKFILL_PAGE_SIZE
    assert graph_calls[0]["scan_limit"] == cron.DEFAULT_GRAPH_BACKFILL_SCAN_SIZE


def test_graph_backfill_uses_per_item_fences_while_lifecycle_staging_is_incomplete(monkeypatch):
    _enable_for(monkeypatch, CANONICAL_A)
    monkeypatch.setenv(cron.MEMORY_CANONICAL_GRAPH_BACKFILL_ENABLED_ENV, "true")
    monkeypatch.setattr(
        cron,
        "run_canonical_cohort_lifecycle",
        lambda **_kwargs: SimpleNamespace(
            write_enrolled_uids=(),
            backfill=SimpleNamespace(summary=SimpleNamespace(read_ready_count=0)),
            backfill_ready_uids=(),
            generation_reconciled_uids=(),
            generation_reconcile_errors=(),
        ),
    )
    monkeypatch.setattr(
        cron,
        "run_canonical_short_term_maintenance",
        lambda uid, **_kwargs: MaintenanceReport(uid=uid),
    )
    graph_calls = []
    monkeypatch.setattr(cron, "run_enrichment", lambda **kwargs: graph_calls.append(kwargs) or {"outcomes": {}})

    summary = cron.run_canonical_short_term_maintenance_for_cohort(db_client=object(), now=NOW, run_id="cron-not-ready")

    assert len(graph_calls) == 1
    assert summary.graph_enriched_total == 0


def test_graph_backfill_scan_size_is_bounded_to_the_current_page_multiple(monkeypatch):
    assert cron.DEFAULT_GRAPH_BACKFILL_SCAN_SIZE == 25
    assert cron.canonical_graph_backfill_scan_size(page_size=5) == 25

    monkeypatch.setenv(cron.MEMORY_CANONICAL_GRAPH_BACKFILL_SCAN_SIZE_ENV, "0")
    assert cron.canonical_graph_backfill_scan_size(page_size=5) == 5

    monkeypatch.setenv(cron.MEMORY_CANONICAL_GRAPH_BACKFILL_SCAN_SIZE_ENV, "not-an-integer")
    assert cron.canonical_graph_backfill_scan_size(page_size=5) == cron.DEFAULT_GRAPH_BACKFILL_SCAN_SIZE

    monkeypatch.setenv(cron.MEMORY_CANONICAL_GRAPH_BACKFILL_SCAN_SIZE_ENV, "999999")
    assert cron.canonical_graph_backfill_scan_size(page_size=5) == 25
    assert cron.canonical_graph_backfill_scan_size(page_size=cron.MAX_PAGE_SIZE) == 125
    assert cron.canonical_graph_backfill_scan_size(page_size=cron.MAX_PAGE_SIZE) <= cron.MAX_STRUCTURED_SCAN_SIZE


def test_graph_backfill_uses_one_page_budget_for_apply_and_safe_scan(monkeypatch):
    _enable_for(monkeypatch, CANONICAL_A)
    monkeypatch.setenv(cron.MEMORY_CANONICAL_GRAPH_BACKFILL_ENABLED_ENV, "true")
    monkeypatch.setenv(cron.MEMORY_CANONICAL_GRAPH_BACKFILL_PAGE_SIZE_ENV, "10")
    monkeypatch.setenv(cron.MEMORY_CANONICAL_GRAPH_BACKFILL_SCAN_SIZE_ENV, "999999")
    monkeypatch.setattr(
        cron,
        "run_canonical_short_term_maintenance",
        lambda uid, **_kwargs: MaintenanceReport(uid=uid),
    )
    graph_calls: list[dict[str, object]] = []
    monkeypatch.setattr(cron, "run_enrichment", lambda **kwargs: graph_calls.append(kwargs) or {"outcomes": {}})

    cron.run_canonical_short_term_maintenance_for_cohort(db_client=object(), now=NOW, run_id="cron-page-budget")

    assert graph_calls[0]["limit"] == 10
    assert graph_calls[0]["apply_limit"] == 10
    assert graph_calls[0]["scan_limit"] == 50


def test_cohort_summary_uses_consolidation_routes_and_promotions(monkeypatch):
    _enable_for(monkeypatch, CANONICAL_A, CANONICAL_B)
    client = object()
    recurrence_sink = MagicMock()
    calls: list[tuple[str, dict[str, Any]]] = []
    reports = {
        CANONICAL_A: MaintenanceReport(
            uid=CANONICAL_A,
            consolidation=ConsolidationReport(
                uid=CANONICAL_A,
                trigger_reason="first_pending",
                batched_memory_ids=["mem-a1", "mem-a2"],
                promoted_memory_ids=["mem-a1"],
                archived_memory_ids=["mem-a2"],
            ),
        ),
        CANONICAL_B: MaintenanceReport(
            uid=CANONICAL_B,
            consolidation=ConsolidationReport(
                uid=CANONICAL_B,
                trigger_reason="first_pending",
                batched_memory_ids=["mem-b1"],
                promoted_memory_ids=["mem-b1"],
            ),
        ),
    }

    def run_maintenance(uid: str, **kwargs: Any) -> MaintenanceReport:
        calls.append((uid, kwargs))
        return reports[uid]

    monkeypatch.setattr(cron, "run_canonical_short_term_maintenance", run_maintenance)

    summary = cron.run_canonical_short_term_maintenance_for_cohort(
        db_client=client,
        now=NOW,
        run_id="cron-routes",
        recurrence_signal_persister=recurrence_sink,
    )

    assert summary.user_count == 2
    assert summary.routed_total == 3
    assert summary.promoted_total == 2
    assert summary.skipped_users == 0
    assert summary.errors == []
    assert [uid for uid, _kwargs in calls] == [CANONICAL_A, CANONICAL_B]
    for _uid, kwargs in calls:
        assert kwargs["db_client"] is client
        assert kwargs["now"] == NOW
        assert kwargs["run_id"] == "cron-routes"
        assert kwargs["recurrence_signal_sink"] is recurrence_sink
        assert callable(kwargs["required_processor"])
        assert set(kwargs) == {
            "db_client",
            "now",
            "run_id",
            "recurrence_signal_sink",
            "required_processor",
        }


def test_consolidation_skipped_reason_is_logged_and_counted(monkeypatch, caplog):
    consolidation = MaintenanceReport(
        uid=CANONICAL_A,
        consolidation=ConsolidationReport(
            uid=CANONICAL_A,
            skipped_reason="consolidation_not_due",
        ),
    )

    _enable_for(monkeypatch, CANONICAL_A)
    monkeypatch.setattr(
        cron,
        "run_canonical_short_term_maintenance",
        lambda *_args, **_kwargs: consolidation,
    )
    caplog.set_level("INFO", logger=cron.__name__)

    summary = cron.run_canonical_short_term_maintenance_for_cohort(now=NOW, run_id="cron-skipped")

    assert summary.routed_total == 0
    assert summary.promoted_total == 0
    assert summary.skipped_users == 1
    assert "skipped_reason=consolidation_not_due" in caplog.text


def test_one_user_failure_does_not_block_remaining_cohort(monkeypatch):
    _enable_for(monkeypatch, CANONICAL_A, CANONICAL_B)
    invoked: list[str] = []

    def run_maintenance(uid: str, **_kwargs: Any) -> MaintenanceReport:
        invoked.append(uid)
        if uid == CANONICAL_A:
            raise RuntimeError("broken user state")
        return MaintenanceReport(
            uid=uid,
            consolidation=ConsolidationReport(
                uid=uid,
                batched_memory_ids=["mem-b"],
                promoted_memory_ids=["mem-b"],
            ),
        )

    monkeypatch.setattr(cron, "run_canonical_short_term_maintenance", run_maintenance)

    summary = cron.run_canonical_short_term_maintenance_for_cohort(now=NOW, run_id="cron-isolated")

    assert invoked == [CANONICAL_A, CANONICAL_B]
    assert summary.user_count == 2
    assert summary.routed_total == 1
    assert summary.promoted_total == 1
    assert summary.skipped_users == 0
    assert summary.errors == [f"uid={CANONICAL_A}: RuntimeError"]


def test_malformed_memory_error_does_not_log_raw_payload(monkeypatch, caplog):
    _enable_for(monkeypatch, CANONICAL_A)
    private_text = "private-diagnosis-sentinel"

    def run_maintenance(_uid: str, **_kwargs: Any) -> MaintenanceReport:
        MemoryItem.model_validate(
            {
                "memory_id": "malformed",
                "uid": CANONICAL_A,
                "content": private_text,
            }
        )
        raise AssertionError("validation should fail")

    monkeypatch.setattr(cron, "run_canonical_short_term_maintenance", run_maintenance)
    caplog.set_level("WARNING", logger=cron.__name__)

    summary = cron.run_canonical_short_term_maintenance_for_cohort(now=NOW, run_id="cron-malformed")

    assert len(summary.errors) == 1
    assert "ValidationError" in summary.errors[0]
    assert "input_value" not in summary.errors[0]
    assert private_text not in summary.errors[0]
    assert private_text not in caplog.text


def test_nonempty_outbox_errors_fail_cron_even_when_failure_counters_are_zero(
    monkeypatch,
):
    _enable_for(monkeypatch, CANONICAL_A)
    report = MaintenanceReport(
        uid=CANONICAL_A,
        outbox={
            "delivered_count": 0,
            "retryable_failure_count": 0,
            "dead_letter_count": 0,
            "ack_failed_count": 0,
            "errors": [{"stage": "lease", "code": "lease_query_failed"}],
        },
    )
    monkeypatch.setattr(cron, "run_canonical_short_term_maintenance", lambda *_args, **_kwargs: report)

    summary = cron.run_canonical_short_term_maintenance_for_cohort(
        db_client=object(),
        now=NOW,
        run_id="cron-outbox-error",
    )

    assert summary.outbox_retryable_failures_total == 0
    assert summary.outbox_dead_letters_total == 0
    assert summary.outbox_ack_failures_total == 0
    assert summary.errors == [f"uid={CANONICAL_A}: outbox_delivery_failed:retryable=0:dead_letter=0:ack=0:errors=1"]


def test_blocked_consolidation_is_a_cohort_error_that_fails_the_job_contract(
    monkeypatch,
):
    _enable_for(monkeypatch, CANONICAL_A)
    report = MaintenanceReport(
        uid=CANONICAL_A,
        consolidation=ConsolidationReport(
            uid=CANONICAL_A,
            watermark_blocked=True,
            retryable_memory_ids=["mem-retry"],
            quarantined_memory_ids=["mem-quarantined"],
            errors=["output_invalid:partition_mismatch"],
        ),
    )
    monkeypatch.setattr(cron, "run_canonical_short_term_maintenance", lambda *_args, **_kwargs: report)

    summary = cron.run_canonical_short_term_maintenance_for_cohort(
        db_client=object(),
        now=NOW,
        run_id="cron-consolidation-error",
    )

    assert summary.errors == [f"uid={CANONICAL_A}: consolidation_failed:blocked=1:retryable=1:quarantined=1:errors=1"]


def test_required_processing_failures_are_cohort_errors_that_fail_the_job_contract(
    monkeypatch,
):
    _enable_for(monkeypatch, CANONICAL_A)
    report = MaintenanceReport(
        uid=CANONICAL_A,
        required_processing=RequiredMemoryProcessingReport(
            uid=CANONICAL_A,
            failed_memory_ids=["mem-retry", "mem-quarantined"],
            retryable_memory_ids=["mem-retry"],
            quarantined_memory_ids=["mem-quarantined"],
        ),
    )
    monkeypatch.setattr(cron, "run_canonical_short_term_maintenance", lambda *_args, **_kwargs: report)

    summary = cron.run_canonical_short_term_maintenance_for_cohort(
        db_client=object(),
        now=NOW,
        run_id="cron-required-processing-error",
    )

    assert summary.errors == [f"uid={CANONICAL_A}: required_processing_failed:failed=2:retryable=1:quarantined=1"]


def test_recurrence_consumer_failure_is_degraded_and_does_not_abort_user(monkeypatch):
    _enable_for(monkeypatch, CANONICAL_A)
    client = object()
    signal = cast(CanonicalRecurrenceSignal, object())
    recurrence_sink = MagicMock()
    consumer = MagicMock(side_effect=RuntimeError("candidate store unavailable"))
    fallback = MagicMock()
    maintenance_kwargs: dict[str, Any] = {}

    def run_maintenance(uid: str, **kwargs: Any) -> MaintenanceReport:
        maintenance_kwargs.update(kwargs)
        return MaintenanceReport(
            uid=uid,
            consolidation=ConsolidationReport(
                uid=uid,
                batched_memory_ids=["mem-a"],
                recurrence_signals=[signal],
            ),
        )

    monkeypatch.setattr(cron, "run_canonical_short_term_maintenance", run_maintenance)
    monkeypatch.setattr(cron, "record_fallback", fallback)

    summary = cron.run_canonical_short_term_maintenance_for_cohort(
        db_client=client,
        now=NOW,
        run_id="cron-recurrence",
        recurrence_signal_persister=recurrence_sink,
        recurrence_signal_consumer=consumer,
    )

    assert maintenance_kwargs["recurrence_signal_sink"] is recurrence_sink
    consumer.assert_called_once_with(
        CANONICAL_A,
        [signal],
        firestore_client=client,
    )
    fallback.assert_called_once_with(
        component="other",
        from_mode="recurrence_maintenance",
        to_mode="recurrence_inbox_retry",
        reason="other",
        outcome="degraded",
    )
    assert summary.routed_total == 1
    assert summary.promoted_total == 0
    assert summary.skipped_users == 0
    assert summary.recurrence_candidates_total == 0
    assert summary.errors == [f"uid={CANONICAL_A}: recurrence_consumer:RuntimeError"]


def test_async_entrypoint_offloads_sync_cohort_runner_to_db_executor(monkeypatch):
    client = object()
    executor = object()
    recurrence_sink = MagicMock()
    recurrence_consumer = MagicMock()
    expected = cron.CanonicalShortTermMaintenanceCronSummary(
        run_id="cron-async",
        user_count=1,
        routed_total=2,
        promoted_total=1,
    )
    calls: list[tuple[Any, Any, tuple[Any, ...], dict[str, Any]]] = []

    async def run_blocking(executor_arg: Any, function: Any, *args: Any, **kwargs: Any):
        calls.append((executor_arg, function, args, kwargs))
        return expected

    monkeypatch.setattr(cron, "db_executor", executor)
    monkeypatch.setattr(cron, "run_blocking", run_blocking)

    result = asyncio.run(
        cron.run_canonical_short_term_maintenance_cron(
            db_client=client,
            now=NOW,
            run_id="cron-async",
            recurrence_signal_persister=recurrence_sink,
            recurrence_signal_consumer=recurrence_consumer,
        )
    )

    assert result is expected
    assert calls == [
        (
            executor,
            cron.run_canonical_short_term_maintenance_for_cohort,
            (),
            {
                "db_client": client,
                "now": NOW,
                "run_id": "cron-async",
                "recurrence_signal_persister": recurrence_sink,
                "recurrence_signal_consumer": recurrence_consumer,
            },
        )
    ]
