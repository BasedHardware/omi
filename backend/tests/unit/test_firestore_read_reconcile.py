"""Focused tests for the cumulative Firestore ledger and daily reducer."""

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import firestore_read_reconcile as reconcile_module
import database.firestore_document_probe as probe

DAY = "2026-10-02"
END_SNAPSHOT = "2026-10-02T23:58:00+00:00"


def _set_ledger(monkeypatch):
    monkeypatch.setattr(probe, "_LEDGER_ENABLED", True)
    monkeypatch.setattr(probe, "_ledger_day", DAY)
    monkeypatch.setattr(probe, "_ledger_counts", {"lookup": 0, "not_found": 0, "query": 0})
    monkeypatch.setattr(probe, "_ledger_tier_counts", {})
    monkeypatch.setattr(probe, "_ledger_unscoped", 0)
    monkeypatch.setattr(probe, "_ledger_seq", 0)
    monkeypatch.setattr(probe, "_ledger_last_emit", 0.0)
    monkeypatch.setattr(
        probe.dt,
        "datetime",
        type(
            "FixedDateTime",
            (dt.datetime,),
            {"now": classmethod(lambda cls, tz=None: dt.datetime(2026, 10, 2, 23, 58, tzinfo=dt.timezone.utc))},
        ),
    )


def _client(project_marker="based-hardware"):
    return type("SDKObject", (), {"_client": type("Client", (), {"project": project_marker})()})()


def test_ledger_service_prefers_explicit_name_then_cloud_run_identity(monkeypatch):
    monkeypatch.setenv("FIRESTORE_READ_LEDGER_SERVICE", "backend")
    monkeypatch.setenv("K_SERVICE", "ignored")
    monkeypatch.setenv("CLOUD_RUN_JOB", "also-ignored")
    assert probe._ledger_service_name() == "backend"
    monkeypatch.delenv("FIRESTORE_READ_LEDGER_SERVICE")
    assert probe._ledger_service_name() == "ignored"
    monkeypatch.delenv("K_SERVICE")
    assert probe._ledger_service_name() == "also-ignored"
    monkeypatch.delenv("CLOUD_RUN_JOB")
    monkeypatch.setenv("DD_SERVICE", "backend-listen")
    assert probe._ledger_service_name() == "backend-listen"
    monkeypatch.setenv("DD_SERVICE", "Memory Job")
    assert probe._ledger_service_name() == "other"


def test_ledger_off_by_default(monkeypatch):
    monkeypatch.setattr(probe, "_LEDGER_ENABLED", False)
    probe._ledger_record(3, "query", "based-hardware")
    assert probe._ledger_counts == {"lookup": 0, "not_found": 0, "query": 0}


def test_ledger_scopes_projects_and_flags_unscoped(monkeypatch):
    _set_ledger(monkeypatch)
    lines = []
    monkeypatch.setattr(probe.logger, "info", lambda fmt, line: lines.append(json.loads(line)))
    probe._record((), True, amount=2, kind="lookup", sdk_object=_client())
    probe._record((), True, amount=7, kind="query", sdk_object=_client("another-project"))
    probe._record((), False, amount=3, kind="not_found", sdk_object=_client(None))
    probe._record((), True, amount=4, kind="query", sdk_object=object())
    assert probe._ledger_counts == {"lookup": 2, "not_found": 3, "query": 4}
    assert probe._ledger_unscoped == 1
    probe._ledger_atexit()
    assert lines[-1]["unscoped"] == 1


def test_snapshots_are_cumulative_rate_limited_and_private(monkeypatch):
    _set_ledger(monkeypatch)
    lines = []
    monkeypatch.setattr(probe.logger, "info", lambda fmt, line: lines.append(json.loads(line)))
    probe._ledger_record(2, "lookup", "based-hardware")
    probe._ledger_record(1, "query", "based-hardware")
    assert len(lines) == 1
    assert lines[0]["lookup"] == 2 and lines[0]["query"] == 0
    assert not any("uid" in key.lower() for key in lines[0])
    probe._ledger_last_emit = -100
    probe._ledger_record(3, "query", "based-hardware")
    assert lines[-1]["seq"] == lines[0]["seq"] + 1
    assert lines[-1]["query"] == 4


def test_day_rollover_emits_previous_day(monkeypatch):
    _set_ledger(monkeypatch)
    lines = []
    monkeypatch.setattr(probe.logger, "info", lambda fmt, line: lines.append(json.loads(line)))
    probe._ledger_record(2, "lookup", "based-hardware")

    class Tomorrow(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return dt.datetime(2026, 10, 3, 0, 1, tzinfo=dt.timezone.utc)

    monkeypatch.setattr(probe.dt, "datetime", Tomorrow)
    probe._ledger_record(1, "query", "based-hardware")
    assert lines[0]["day"] == DAY and lines[0]["lookup"] == 2
    assert probe._ledger_day == "2026-10-03"
    assert probe._ledger_counts["query"] == 1


def _records(instrumented=97, timestamps=None, services=None, tier_counts=None):
    services = sorted(services or reconcile_module.REQUIRED_SERVICES)
    stamps = timestamps or {}
    result = []
    for index, service in enumerate(services):
        result.append(
            {
                "event": "firestore_read_ledger",
                "day": DAY,
                "service": service,
                "epoch": f"{index:016x}",
                "seq": 1,
                "lookup": instrumented if index == 0 else 0,
                "not_found": 0,
                "query": 0,
                "tier_counts": dict(tier_counts or {}) if index == 0 else {},
                "unscoped": 0,
                "emitted_at": stamps.get(service, END_SNAPSHOT),
            }
        )
    return result


def test_reconcile_deduplicates_duplicate_delivery():
    records = _records()
    records.extend([dict(records[0]), dict(records[0])])
    assert reconcile_module.reconcile(DAY, 100, records)["instrumented"] == 97


def test_reconcile_outcomes():
    missing = _records(instrumented=97, services=reconcile_module.REQUIRED_SERVICES - {"desktop-backend"})
    assert reconcile_module.reconcile(DAY, 100, missing)["outcome"] == "incomplete"
    assert reconcile_module.reconcile(DAY, 100, _records(instrumented=97))["outcome"] == "audit_required"
    assert reconcile_module.reconcile(DAY, 100, _records(instrumented=103))["outcome"] == "accounting_failure"
    stale = _records(instrumented=99, timestamps={"backend": "2026-10-02T20:00:00+00:00"})
    assert reconcile_module.reconcile(DAY, 100, stale)["outcome"] == "incomplete"
    fresh_records = _records(instrumented=99)
    fresh_records.append(
        {
            "event": "firestore_read_ledger",
            "day": DAY,
            "service": "memory-maintenance-job",
            "epoch": "cron",
            "seq": 4,
            "lookup": 0,
            "not_found": 0,
            "query": 0,
            "unscoped": 0,
            "emitted_at": "2026-10-02T15:00:00+00:00",
        }
    )
    fresh = reconcile_module.reconcile(DAY, 100, fresh_records)
    assert fresh["outcome"] == "healthy"
    assert fresh["completeness_excluded"] == ["pusher"]


def test_missing_pusher_snapshot_stays_quiet_and_present_rows_still_count():
    assert reconcile_module.COMPLETENESS_EXCLUDED == frozenset({"pusher"})
    assert "pusher" in reconcile_module.SHIPPED_SERVICES
    assert "pusher" not in reconcile_module.REQUIRED_SERVICES
    assert "pusher" not in reconcile_module.HOT_SERVICES
    quiet = reconcile_module.reconcile(DAY, 100, _records(instrumented=99))
    assert quiet["outcome"] == "healthy"
    assert quiet["completeness_excluded"] == ["pusher"]
    counted = _records(instrumented=90)
    counted.append(
        {
            "event": "firestore_read_ledger",
            "day": DAY,
            "service": "pusher",
            "epoch": "pusher",
            "seq": 2,
            "lookup": 9,
            "not_found": 0,
            "query": 0,
            "tier_counts": {"basic": 9},
            "unscoped": 0,
            "emitted_at": "2026-10-02T12:00:00+00:00",
        }
    )
    result = reconcile_module.reconcile(DAY, 100, counted)
    assert result["instrumented"] == 99
    assert result["outcome"] == "healthy"
    assert result["reads_by_tier"] == {"basic": 9}


def test_ledger_records_tier_breakdown_and_rollover_resets_it(monkeypatch):
    _set_ledger(monkeypatch)
    lines = []
    monkeypatch.setattr(probe.logger, "info", lambda fmt, line: lines.append(json.loads(line)))
    probe._ledger_record(2, "lookup", "based-hardware", "basic")
    assert lines[0]["tier_counts"] == {"basic": 2}
    probe._ledger_record(5, "query", "based-hardware", "unlimited")
    probe._ledger_last_emit = -100  # force the rate-limited snapshot
    probe._ledger_record(3, "query", "based-hardware")
    assert lines[-1]["tier_counts"] == {"basic": 2, "unattributed": 3, "unlimited": 5}
    assert lines[-1]["lookup"] == 2 and lines[-1]["query"] == 8
    assert lines[-1]["schema"] == 2

    class Tomorrow(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return dt.datetime(2026, 10, 3, 0, 1, tzinfo=dt.timezone.utc)

    monkeypatch.setattr(probe.dt, "datetime", Tomorrow)
    probe._ledger_record(1, "query", "based-hardware", "basic")
    assert probe._ledger_tier_counts == {"basic": 1}


def test_reconcile_sums_tier_counts_across_services_and_tolerates_schema1():
    records = _records(instrumented=97, tier_counts={"basic": 40, "unlimited": 57})
    records.append(
        {
            "event": "firestore_read_ledger",
            "day": DAY,
            "service": "backend",
            "epoch": "second-epoch-of-backend",
            "seq": 1,
            "lookup": 6,
            "not_found": 0,
            "query": 0,
            "tier_counts": {"unlimited": 6},
            "unscoped": 0,
            "emitted_at": END_SNAPSHOT,
        }
    )
    records.append(
        {
            "event": "firestore_read_ledger",
            "day": DAY,
            "service": "desktop-backend",
            "epoch": "legacy-schema1",
            "seq": 1,
            "lookup": 2,
            "not_found": 0,
            "query": 0,
            "unscoped": 0,
            "emitted_at": END_SNAPSHOT,
        }
    )
    result = reconcile_module.reconcile(DAY, 105, records)
    assert result["instrumented"] == 105
    assert result["reads_by_tier"] == {"basic": 40, "unlimited": 63}
    assert result["outcome"] == "healthy"


def test_reconcile_reduces_to_tier_shares_for_the_cut_list():
    records = _records(instrumented=97, tier_counts={"unattributed": 90, "basic": 5, "unlimited": 2})
    result = reconcile_module.reconcile(DAY, 100, records)
    assert result["reads_by_tier"] == {"basic": 5, "unattributed": 90, "unlimited": 2}
    assert sum(result["reads_by_tier"].values()) == result["instrumented"]


def test_missing_projection_pump_snapshot_makes_the_day_incomplete():
    """SCA-3120: the pump is a required ledger service before its flag turns on."""
    assert "backend-projection-pump" in reconcile_module.REQUIRED_SERVICES
    assert "backend-projection-pump" in reconcile_module.HOT_SERVICES
    day = "2026-11-23"  # after REQUIRED_FROM; earlier days do not require the pump

    def on_day(rows, stale_pump=False):
        for row in rows:
            row["day"] = day
            late = row["service"] == "backend-projection-pump" and stale_pump
            row["emitted_at"] = "2026-11-23T20:00:00+00:00" if late else "2026-11-23T23:58:00+00:00"
        return rows

    missing = on_day(
        _records(instrumented=99, services=reconcile_module.REQUIRED_SERVICES - {"backend-projection-pump"})
    )
    assert reconcile_module.reconcile(day, 100, missing)["outcome"] == "incomplete"
    # A pump that stopped reporting early in the day leaves later reads unaccounted.
    stale = on_day(_records(instrumented=99), stale_pump=True)
    assert reconcile_module.reconcile(day, 100, stale)["outcome"] == "incomplete"
    assert reconcile_module.reconcile(day, 100, on_day(_records(instrumented=99)))["outcome"] == "healthy"


def test_projection_pump_is_required_only_from_its_first_full_ledger_day():
    """#25966 panel F2: the D-2 cron must not score pre-pump days red."""
    assert reconcile_module.REQUIRED_FROM == {"backend-projection-pump": "2026-11-22"}
    before = "2026-11-20"
    others = reconcile_module.REQUIRED_SERVICES - {"backend-projection-pump"}
    rows = _records(instrumented=99, services=others)
    for row in rows:
        row["day"] = before
        row["emitted_at"] = "2026-11-20T23:59:00+00:00"
    assert reconcile_module.reconcile(before, 100, rows)["outcome"] == "healthy"
    after = "2026-11-22"
    for row in rows:
        row["day"] = after
        row["emitted_at"] = "2026-11-22T23:59:00+00:00"
    assert reconcile_module.reconcile(after, 100, rows)["outcome"] == "incomplete"
