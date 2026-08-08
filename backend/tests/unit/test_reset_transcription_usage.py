"""Unit tests for the transcription-usage reset admin CLI pure logic.

Covers: month-key labelling, monthly aggregation, reset-plan construction
(dry-run vs apply shape), audit-record shape. No GCP — the helpers under test
take plain dicts mirroring the Firestore snapshot shape.
"""

from __future__ import annotations

from datetime import datetime, timezone

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from scripts.admin.reset_transcription_usage import (  # noqa: E402
    aggregate_monthly_usage,
    apply_reset,
    build_audit_record,
    build_reset_plan,
    fetch_monthly_hourly_docs,
    month_label,
    seconds_to_minutes,
    update_audit,
    write_audit,
    _sanitized_audit_payload,
)
from tests.store_fakes import FakeDocumentStore  # noqa: E402

NOW = datetime(2026, 7, 27, 13, 30, tzinfo=timezone.utc)


def _doc(doc_id: str, seconds: int, **extra) -> tuple[str, dict]:
    """One hourly_usage snapshot shape: (doc_id, data)."""
    data = {"transcription_seconds": seconds, "year": 2026, "month": 7}
    data.update(extra)
    return (doc_id, data)


def test_month_label_uses_utc_calendar_month() -> None:
    assert month_label(NOW) == "2026-07"


def test_aggregate_sums_transcription_seconds_and_counts_docs() -> None:
    docs = [_doc("2026-07-27-10", 120), _doc("2026-07-27-11", 60), _doc("2026-07-27-12", 0)]

    usage = aggregate_monthly_usage(docs)

    assert usage.used_seconds == 180
    assert usage.document_count == 3
    # zero-second buckets are dropped from the "top" view
    assert [b.doc_id for b in usage.top_buckets] == ["2026-07-27-10", "2026-07-27-11"]
    assert usage.top_buckets[0].seconds == 120


def test_aggregate_treats_missing_field_as_zero() -> None:
    # _aggregate_stats_with_count in database/user_usage does .get(..., 0); mirror it.
    docs = [("2026-07-27-10", {"year": 2026, "month": 7})]  # no transcription_seconds

    usage = aggregate_monthly_usage(docs)

    assert usage.used_seconds == 0
    assert usage.top_buckets == ()


def test_aggregate_handles_none_value_like_firestore_adapter() -> None:
    # Firestore snapshots can surface None for a field present-but-null.
    docs = [("2026-07-27-10", {"transcription_seconds": None})]

    usage = aggregate_monthly_usage(docs)

    assert usage.used_seconds == 0


def test_top_buckets_are_sorted_desc_and_capped() -> None:
    docs = [_doc(f"2026-07-27-{h:02d}", h * 10) for h in range(1, 8)]  # 7 buckets

    usage = aggregate_monthly_usage(docs, top_n=3)

    assert [b.seconds for b in usage.top_buckets] == [70, 60, 50]


def test_reset_plan_only_includes_nonzero_buckets_and_sums_before() -> None:
    docs = [_doc("2026-07-27-10", 120), _doc("2026-07-27-11", 60), _doc("2026-07-27-12", 0)]

    plan = build_reset_plan(docs)

    assert plan.doc_ids == ("2026-07-27-10", "2026-07-27-11")
    assert plan.before_total_seconds == 180
    assert plan.after_total_seconds == 0
    assert plan.touches == 2


def test_reset_plan_is_noop_on_fresh_user() -> None:
    plan = build_reset_plan([_doc("2026-07-27-10", 0), _doc("2026-07-27-11", 0)])

    assert plan.doc_ids == ()
    assert plan.before_total_seconds == 0
    assert plan.touches == 0


def test_reset_plan_after_total_is_always_zero_regardless_of_input() -> None:
    # The whole point of reset-month: zeroing lands the month at 0.
    docs = [_doc("2026-07-27-10", 9999)]

    plan = build_reset_plan(docs)

    assert plan.after_total_seconds == 0


def test_dry_run_vs_apply_share_the_same_plan_shape() -> None:
    # Whether --apply is set or not, the plan computed from the docs is identical;
    # only the write step differs (exercised in cmd_reset_month, not here).
    docs = [_doc("2026-07-27-10", 300)]

    plan = build_reset_plan(docs)

    assert plan.doc_ids == ("2026-07-27-10",)
    assert plan.before_total_seconds == 300
    # apply path would zero exactly these doc ids — the contract under test.
    assert plan.touches == 1


def test_audit_record_captures_who_when_why_before_after() -> None:
    record = build_audit_record(
        uid="abc123",
        email="user@example.com",
        plan="basic",
        month="2026-07",
        reason="goodwill: silent open-mic burn",
        operator="david@",
        applied=True,
        before_seconds=18000,
        after_seconds=0,
        docs_touched=42,
        now=NOW,
    )

    d = record.to_dict()
    assert d["uid"] == "abc123"
    assert d["email"] == "user@example.com"
    assert d["plan"] == "basic"
    assert d["month"] == "2026-07"
    assert d["reason"] == "goodwill: silent open-mic burn"
    assert d["operator"] == "david@"
    assert d["applied"] is True
    assert d["before_seconds"] == 18000
    assert d["after_seconds"] == 0
    assert d["docs_touched"] == 42
    assert d["at"] == "2026-07-27T13:30:00Z"


def test_audit_record_marks_dry_run_as_not_applied() -> None:
    record = build_audit_record(
        uid="abc",
        email=None,
        plan="basic",
        month="2026-07",
        reason="test",
        operator="ops",
        applied=False,
        before_seconds=10,
        after_seconds=0,
        docs_touched=1,
        now=NOW,
    )

    assert record.applied is False
    assert record.email is None


def test_seconds_to_minutes_rounds_to_one_decimal() -> None:
    assert seconds_to_minutes(0) == 0.0
    assert seconds_to_minutes(60) == 1.0
    assert seconds_to_minutes(90) == 1.5
    assert seconds_to_minutes(18000) == 300.0  # 300 min cap


def test_aggregation_trusts_caller_month_filter() -> None:
    # The fetch step filters hourly_usage by year/month; the aggregate must not
    # re-implement that filter. Guard against drift: docs from another month
    # passed in by mistake still get summed (caller owns the filter).
    assert month_label(NOW) == "2026-07"
    cross_month = [_doc("2026-06-30-23", 1000), _doc("2026-07-01-00", 500)]

    usage = aggregate_monthly_usage(cross_month)

    assert usage.used_seconds == 1500


# ---------------------------------------------------------------------------
# Audit sanitization (Thread 5)
# ---------------------------------------------------------------------------


def test_sanitized_audit_payload_masks_email() -> None:
    record = build_audit_record(
        uid="abc123",
        email="user@example.com",
        plan="basic",
        month="2026-07",
        reason="goodwill",
        operator="ops",
        applied=True,
        before_seconds=100,
        after_seconds=0,
        docs_touched=1,
        now=NOW,
    )

    payload = _sanitized_audit_payload(record)

    # Email local part is masked; domain preserved.
    assert "@" in payload["email"]
    assert payload["email"] != "user@example.com"
    assert "example.com" in payload["email"]


def test_sanitized_audit_payload_masks_reason_text() -> None:
    record = build_audit_record(
        uid="abc123",
        email=None,
        plan="basic",
        month="2026-07",
        reason="goodwill: user jane@example.com silent open-mic",
        operator="ops",
        applied=True,
        before_seconds=100,
        after_seconds=0,
        docs_touched=1,
        now=NOW,
    )

    payload = _sanitized_audit_payload(record)

    # The reason contained an email — it must be masked in the sanitized output.
    assert "jane@example.com" not in payload["reason"]


def test_sanitized_audit_payload_preserves_non_pii_fields() -> None:
    record = build_audit_record(
        uid="abc123",
        email=None,
        plan="basic",
        month="2026-07",
        reason="routine",
        operator="ops",
        applied=False,
        before_seconds=10,
        after_seconds=0,
        docs_touched=1,
        now=NOW,
    )

    payload = _sanitized_audit_payload(record)

    # Non-PII fields pass through unchanged.
    assert payload["uid"] == "abc123"
    assert payload["plan"] == "basic"
    assert payload["before_seconds"] == 10
    assert payload["applied"] is False


# ---------------------------------------------------------------------------
# Pending audit record uses sentinel before mutation outcome is known (Thread 4)
# ---------------------------------------------------------------------------


def test_pending_audit_record_marks_applied_false_and_sentinel_after() -> None:
    """A pending audit record is written before mutation with applied=False
    and a sentinel after_seconds=-1 so partial-failure leaves a recoverable trail."""
    pending = build_audit_record(
        uid="abc123",
        email=None,
        plan="basic",
        month="2026-07",
        reason="goodwill",
        operator="ops",
        applied=False,
        before_seconds=300,
        after_seconds=-1,  # sentinel: outcome not yet known
        docs_touched=2,
        now=NOW,
    )

    assert pending.applied is False
    assert pending.after_seconds == -1  # sentinel: not yet finalized


# ---------------------------------------------------------------------------
# I/O against the neutral document store (Firestore | Mongo), exercised with an
# in-memory FakeDocumentStore. Same behavior an on-prem operator gets on Mongo.
# ---------------------------------------------------------------------------


def _seed_month(fake: FakeDocumentStore, uid: str, buckets: dict[str, int], *, year=2026, month=7) -> None:
    for doc_id, seconds in buckets.items():
        fake.set(
            f"users/{uid}/hourly_usage/{doc_id}",
            {"transcription_seconds": seconds, "year": year, "month": month},
        )


def test_fetch_monthly_hourly_docs_filters_by_year_and_month() -> None:
    fake = FakeDocumentStore()
    _seed_month(fake, "u1", {"2026-07-27-10": 120, "2026-07-27-11": 60})
    # A doc from another month must be excluded by the year/month filter.
    fake.set("users/u1/hourly_usage/2026-06-30-23", {"transcription_seconds": 999, "year": 2026, "month": 6})
    # A doc for a different user must not leak into u1's collection scope.
    fake.set("users/u2/hourly_usage/2026-07-27-10", {"transcription_seconds": 5, "year": 2026, "month": 7})

    docs = fetch_monthly_hourly_docs(fake, "u1", 2026, 7)

    got = {doc_id: data["transcription_seconds"] for doc_id, data in docs}
    assert got == {"2026-07-27-10": 120, "2026-07-27-11": 60}
    # aggregate on the fetched docs matches the seeded month total
    assert aggregate_monthly_usage(docs).used_seconds == 180


def test_apply_reset_zeroes_only_planned_docs_and_merges() -> None:
    fake = FakeDocumentStore()
    _seed_month(fake, "u1", {"2026-07-27-10": 120, "2026-07-27-11": 60, "2026-07-27-12": 0})

    docs = fetch_monthly_hourly_docs(fake, "u1", 2026, 7)
    plan = build_reset_plan(docs)
    apply_reset(fake, "u1", plan)

    # Touched docs land at zero, and the merge preserves the sibling year/month fields.
    for doc_id in ("2026-07-27-10", "2026-07-27-11"):
        data = fake.get(f"users/u1/hourly_usage/{doc_id}").to_dict()
        assert data["transcription_seconds"] == 0
        assert data["year"] == 2026 and data["month"] == 7
    # The already-zero bucket was never in the plan, so it is untouched.
    assert "2026-07-27-12" not in plan.doc_ids

    # Re-fetch: the whole month now aggregates to zero.
    assert aggregate_monthly_usage(fetch_monthly_hourly_docs(fake, "u1", 2026, 7)).used_seconds == 0


def test_apply_reset_noop_when_plan_empty() -> None:
    fake = FakeDocumentStore()
    _seed_month(fake, "u1", {"2026-07-27-10": 0})

    plan = build_reset_plan(fetch_monthly_hourly_docs(fake, "u1", 2026, 7))
    apply_reset(fake, "u1", plan)  # must not raise, must not write

    assert plan.doc_ids == ()
    assert fake.get("users/u1/hourly_usage/2026-07-27-10").to_dict()["transcription_seconds"] == 0


def test_write_audit_persists_record_and_returns_id() -> None:
    fake = FakeDocumentStore()
    record = build_audit_record(
        uid="abc123",
        email="user@example.com",
        plan="basic",
        month="2026-07",
        reason="goodwill",
        operator="ops",
        applied=False,
        before_seconds=300,
        after_seconds=-1,  # pending sentinel
        docs_touched=2,
        now=NOW,
    )

    audit_id = write_audit(fake, record)

    assert audit_id  # a non-empty generated id
    stored = fake.get(f"admin_audit_log/{audit_id}").to_dict()
    assert stored == record.to_dict()
    assert stored["applied"] is False
    assert stored["after_seconds"] == -1


def test_update_audit_finalizes_the_same_document() -> None:
    fake = FakeDocumentStore()
    pending = build_audit_record(
        uid="abc123",
        email=None,
        plan="basic",
        month="2026-07",
        reason="goodwill",
        operator="ops",
        applied=False,
        before_seconds=300,
        after_seconds=-1,
        docs_touched=2,
        now=NOW,
    )
    audit_id = write_audit(fake, pending)

    final = build_audit_record(
        uid="abc123",
        email=None,
        plan="basic",
        month="2026-07",
        reason="goodwill",
        operator="ops",
        applied=True,
        before_seconds=300,
        after_seconds=0,
        docs_touched=2,
        now=NOW,
    )
    update_audit(fake, audit_id, final)

    # Same doc id is overwritten with the finalized outcome (no orphan record).
    stored = fake.get(f"admin_audit_log/{audit_id}").to_dict()
    assert stored["applied"] is True
    assert stored["after_seconds"] == 0
    assert len(fake.list_ids("admin_audit_log")) == 1
