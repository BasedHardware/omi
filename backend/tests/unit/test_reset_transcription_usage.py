"""Unit tests for the transcription- and chat-quota reset admin CLI pure logic.

Covers: month-key labelling, monthly aggregation, listening reset-plan,
chat nested/dotted/plan_usage shapes, dry-run vs apply shape, audit records.
No GCP — the helpers under test take plain dicts mirroring the Firestore
snapshot shape.
"""

from __future__ import annotations

from datetime import datetime, timezone

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from scripts.admin.reset_transcription_usage import (  # noqa: E402
    AccountView,
    MonthlyUsage,
    aggregate_monthly_usage,
    apply_chat_quota_reset_locally,
    build_audit_record,
    build_chat_quota_audit_record,
    build_chat_quota_reset_update,
    build_chat_reset_plan,
    build_parser,
    build_reset_plan,
    chat_questions_from_doc,
    listening_is_throttled,
    llm_usage_doc_id_in_utc_month,
    month_label,
    seconds_to_minutes,
    skip_unlimited_listening_reset,
    _print_usage,
    _sanitized_audit_payload,
)

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
# Chat-quota reset — nested / dotted / plan_usage shapes (SCA-393)
# ---------------------------------------------------------------------------


def _chat_doc(doc_id: str, data: dict) -> tuple[str, dict]:
    return (doc_id, data)


def test_llm_usage_doc_id_in_utc_month_filters_yyyy_mm_dd() -> None:
    assert llm_usage_doc_id_in_utc_month("2026-07-01", 2026, 7) is True
    assert llm_usage_doc_id_in_utc_month("2026-07-31", 2026, 7) is True
    assert llm_usage_doc_id_in_utc_month("2026-06-30", 2026, 7) is False
    assert llm_usage_doc_id_in_utc_month("2026-08-01", 2026, 7) is False
    assert llm_usage_doc_id_in_utc_month("2025-07-01", 2026, 7) is False
    assert llm_usage_doc_id_in_utc_month("hourly-not-a-day", 2026, 7) is False


def test_chat_questions_from_doc_counts_nested_quota_not_call_count() -> None:
    data = {
        "desktop_chat": {
            "call_count": 5,
            "quota_questions": 5,
            "cost_usd": 1.5,
        },
        "desktop_chat_realtime": {"call_count": 2, "quota_questions": 2},
        "chat.gpt-4.call_count": 4,
        "conv_apps.gpt-5.call_count": 100,
    }
    # Nested desktop quota_questions (5) + backend chat.* (4). Realtime has
    # quota_questions so its call_count is not a fallback. Proactive excluded.
    assert chat_questions_from_doc(data) == 9


def test_chat_questions_from_doc_falls_back_to_realtime_call_count() -> None:
    data = {
        "desktop_chat": {"call_count": 7, "cost_usd": 0.4},
        "desktop_chat_realtime": {"call_count": 7},
    }
    assert chat_questions_from_doc(data) == 7


def test_reset_nested_quota_questions_and_preserves_telemetry() -> None:
    data = {
        "desktop_chat": {
            "call_count": 5,
            "quota_questions": 5,
            "input_tokens": 100,
            "cost_usd": 1.5,
        },
        "backend_chat": {"quota_questions": 3, "call_count": 9},
        "desktop_chat_realtime": {"quota_questions": 2, "call_count": 2},
    }
    update = build_chat_quota_reset_update(data)
    after = apply_chat_quota_reset_locally(data, update)

    assert after["desktop_chat"]["quota_questions"] == 0
    assert after["backend_chat"]["quota_questions"] == 0
    assert after["desktop_chat_realtime"]["quota_questions"] == 0
    assert after["desktop_chat"]["call_count"] == 5
    assert after["backend_chat"]["call_count"] == 9
    assert after["desktop_chat_realtime"]["call_count"] == 2
    assert after["desktop_chat"]["cost_usd"] == 1.5
    assert after["desktop_chat"]["input_tokens"] == 100
    assert chat_questions_from_doc(after) == 0
    assert "call_count" not in update.get("desktop_chat", {})


def test_reset_dotted_quota_questions_keys() -> None:
    data = {
        "desktop_chat.quota_questions": 4,
        "backend_chat.quota_questions": 6,
        "desktop_chat_realtime.quota_questions": 1,
        "desktop_chat.call_count": 99,
    }
    update = build_chat_quota_reset_update(data)
    after = apply_chat_quota_reset_locally(data, update)

    assert after["desktop_chat.quota_questions"] == 0
    assert after["backend_chat.quota_questions"] == 0
    assert after["desktop_chat_realtime.quota_questions"] == 0
    assert after["desktop_chat.call_count"] == 99
    assert chat_questions_from_doc(after) == 0


def test_reset_recurses_plan_usage_and_root_counters() -> None:
    data = {
        "desktop_chat": {"quota_questions": 5},
        "plan_usage": {
            "operator": {
                "desktop_chat": {"quota_questions": 2, "input_tokens": 10},
                "backend_chat": {"quota_questions": 1},
            }
        },
    }
    after = apply_chat_quota_reset_locally(data, build_chat_quota_reset_update(data))

    assert after["desktop_chat"]["quota_questions"] == 0
    assert after["plan_usage"]["operator"]["desktop_chat"]["quota_questions"] == 0
    assert after["plan_usage"]["operator"]["backend_chat"]["quota_questions"] == 0
    assert after["plan_usage"]["operator"]["desktop_chat"]["input_tokens"] == 10
    assert chat_questions_from_doc(after) == 0


def test_reset_introduces_backend_chat_quota_questions_instead_of_wiping_call_count() -> None:
    data = {"chat.gpt-4.call_count": 4, "chat.migrated.call_count": 3}
    update = build_chat_quota_reset_update(data)
    after = apply_chat_quota_reset_locally(data, update)

    assert after["chat.gpt-4.call_count"] == 4
    assert after["chat.migrated.call_count"] == 3
    assert after["backend_chat"]["quota_questions"] == 0
    # Introducing the key disables the legacy chat.*.call_count fallback.
    assert chat_questions_from_doc(data) == 7
    assert chat_questions_from_doc(after) == 0


def test_reset_does_not_zero_chat_call_count_when_backend_quota_questions_exists() -> None:
    data = {
        "backend_chat": {"quota_questions": 8},
        "chat.gpt-4.call_count": 4,
    }
    after = apply_chat_quota_reset_locally(data, build_chat_quota_reset_update(data))

    assert after["chat.gpt-4.call_count"] == 4
    assert after["backend_chat"]["quota_questions"] == 0
    assert chat_questions_from_doc(after) == 0


def test_reset_introduces_realtime_quota_questions_to_stop_call_count_fallback() -> None:
    data = {
        "desktop_chat": {"call_count": 7, "cost_usd": 0.4},
        "desktop_chat_realtime": {"call_count": 7},
    }
    after = apply_chat_quota_reset_locally(data, build_chat_quota_reset_update(data))

    assert after["desktop_chat"]["call_count"] == 7
    assert after["desktop_chat_realtime"]["call_count"] == 7
    assert after["desktop_chat_realtime"]["quota_questions"] == 0
    assert chat_questions_from_doc(after) == 0


def test_chat_reset_plan_skips_already_zero_docs() -> None:
    docs = [
        _chat_doc("2026-07-01", {"desktop_chat": {"quota_questions": 0, "call_count": 3}}),
        _chat_doc("2026-07-02", {"desktop_chat": {"quota_questions": 2}}),
    ]
    plan = build_chat_reset_plan(docs)

    assert plan.doc_ids == ("2026-07-02",)
    assert plan.touches == 1
    assert plan.updates[0][1] == {"desktop_chat": {"quota_questions": 0}}


def test_chat_reset_plan_dry_run_and_apply_share_shape() -> None:
    docs = [_chat_doc("2026-07-10", {"desktop_chat.quota_questions": 9})]
    plan = build_chat_reset_plan(docs)
    assert plan.touches == 1
    after = apply_chat_quota_reset_locally(docs[0][1], plan.updates[0][1])
    assert chat_questions_from_doc(after) == 0


def test_chat_quota_audit_record_includes_action_and_question_totals() -> None:
    record = build_chat_quota_audit_record(
        uid="abc123",
        email="user@example.com",
        plan="basic",
        month="2026-07",
        reason="goodwill: chat-quota burn",
        operator="david@",
        applied=True,
        before_questions=12,
        after_questions=0,
        docs_touched=3,
        now=NOW,
    )
    d = record.to_dict()
    assert d["action"] == "reset-chat-quota-month"
    assert d["before_questions"] == 12
    assert d["after_questions"] == 0
    assert d["docs_touched"] == 3
    assert d["at"] == "2026-07-27T13:30:00Z"


def test_chat_quota_audit_sanitizes_email_and_reason() -> None:
    record = build_chat_quota_audit_record(
        uid="abc123",
        email="user@example.com",
        plan="basic",
        month="2026-07",
        reason="goodwill: user jane@example.com",
        operator="ops",
        applied=False,
        before_questions=4,
        after_questions=0,
        docs_touched=1,
        now=NOW,
    )
    payload = _sanitized_audit_payload(record)
    assert payload["email"] != "user@example.com"
    assert "jane@example.com" not in payload["reason"]
    assert payload["action"] == "reset-chat-quota-month"
    assert payload["before_questions"] == 4


def test_reset_chat_month_parser_is_dry_run_by_default() -> None:
    parser = build_parser()
    args = parser.parse_args(["reset-chat-month", "--uid", "abc", "--reason", "goodwill"])
    assert args.apply is False
    assert args.func.__name__ == "cmd_reset_chat_month"


def test_show_parser_still_accepts_uid_and_email() -> None:
    parser = build_parser()
    args = parser.parse_args(["show", "--uid", "abc"])
    assert args.func.__name__ == "cmd_show"
    args = parser.parse_args(["show", "--email", "user@example.com"])
    assert args.email == "user@example.com"


def test_show_printout_includes_listening_and_chat(capsys) -> None:
    view = AccountView(
        plan_name="Free",
        status="active",
        listening_limit_seconds=18000,
        chat_questions_limit=30,
        chat_cost_usd_limit=None,
    )
    usage = MonthlyUsage(used_seconds=600, document_count=2, top_buckets=())
    _print_usage(
        "uid-123",
        "user@example.com",
        view,
        usage,
        "2026-07",
        chat_questions=12,
        fair_use_stage=None,
    )
    out = capsys.readouterr().out
    assert "plan:          Free" in out
    assert "status:        active" in out
    assert "listening used:" in out
    assert "chat used:      12 questions" in out
    assert "chat limit:     30 questions" in out
    assert "chat remaining: 18 questions" in out
    assert "listening throttled: no" in out
    assert "chat included exhausted: no" in out
    assert "GET /v1/admin/fair-use/user/uid-123" in out


def test_show_printout_prefers_fair_use_stage_when_present(capsys) -> None:
    view = AccountView(
        plan_name="Free",
        status="active",
        listening_limit_seconds=None,
        chat_questions_limit=None,
        chat_cost_usd_limit=None,
    )
    usage = MonthlyUsage(used_seconds=0, document_count=0, top_buckets=())
    _print_usage(
        "uid-123",
        None,
        view,
        usage,
        "2026-07",
        chat_questions=0,
        fair_use_stage="off",
    )
    out = capsys.readouterr().out
    assert "fair-use:       stage=off" in out
    assert "chat limit:     unlimited" in out
    assert "listening limit:     unlimited" in out
    assert "listening throttled: no" in out
    assert "listening reset: skip (unlimited; not throttled)" in out
    assert "chat included exhausted: n/a (unlimited)" in out


def test_listening_is_throttled_only_when_finite_cap_exhausted() -> None:
    assert listening_is_throttled(None, 1_000_000) is False
    assert listening_is_throttled(18000, 17999) is False
    assert listening_is_throttled(18000, 18000) is True
    assert listening_is_throttled(18000, 18001) is True


def test_skip_unlimited_listening_reset_requires_force() -> None:
    assert skip_unlimited_listening_reset(None, force=False) is True
    assert skip_unlimited_listening_reset(None, force=True) is False
    assert skip_unlimited_listening_reset(18000, force=False) is False


def test_reset_month_parser_accepts_force() -> None:
    parser = build_parser()
    args = parser.parse_args(["reset-month", "--uid", "abc", "--reason", "goodwill"])
    assert args.force is False
    args = parser.parse_args(["reset-month", "--uid", "abc", "--reason", "goodwill", "--force"])
    assert args.force is True


def test_show_printout_marks_exhausted_free_listening(capsys) -> None:
    view = AccountView(
        plan_name="Free",
        status="active",
        listening_limit_seconds=18000,
        chat_questions_limit=30,
        chat_cost_usd_limit=None,
    )
    usage = MonthlyUsage(used_seconds=18000, document_count=1, top_buckets=())
    _print_usage(
        "uid-123",
        None,
        view,
        usage,
        "2026-07",
        chat_questions=30,
        fair_use_stage=None,
    )
    out = capsys.readouterr().out
    assert "listening throttled: yes" in out
    assert "chat included exhausted: yes" in out
    assert "listening reset: skip" not in out
