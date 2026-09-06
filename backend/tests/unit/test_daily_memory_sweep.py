from datetime import date, datetime, timedelta, timezone
from io import StringIO
import sys
import threading
import time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from google.cloud import firestore
import pytest

from models.memory_apply import MemoryControlState, WriterMode
from models.memory_contracts import deterministic_contract_id
from services.users import data_export
from utils.memory.daily_memory_sweep import (
    DailySweepCandidate,
    DailySweepCohortAuthority,
    DailySweepCohortDecision,
    DailySweepCursor,
    DailySweepInput,
    DailySweepModelAuthority,
    MAX_CATCH_UP_DAYS,
    QA_SWEEP_MAX_CATCH_UP_DAYS,
    QA_SWEEP_MAX_SDK_RETRIES,
    QA_SWEEP_MAX_MEMORY_LOOKUPS,
    QA_SWEEP_MAX_MODEL_COST_USD,
    QA_SWEEP_MAX_SUMMARY_CONVERSATIONS,
    QA_SWEEP_MAX_SUMMARY_INPUT_CHARACTERS,
    QA_SWEEP_MAX_TRANSCRIPT_FETCHES,
    SweepAuthority,
    SweepAuthorityState,
    completed_local_day_window,
    timezone_transition_window,
    plan_daily_memory_sweep,
    run_daily_memory_sweep,
)
from utils.memory.daily_memory_sweep import (
    DailySweepRuntimeSources,
    _completed_day_row_eligibility,
    reconcile_daily_memory_sweep_timezone,
    _finish_onboarding_sources,
    _receipt_id,
    _cached_summary_eligibility_attested,
    _find_active_slot_or_subject,
    _load_or_stage_onboarding_candidates,
    _onboarding_staged_candidates_ref,
    _daily_summary_staged_candidates_ref,
    _onboarding_transcript_eligibility,
    _pending_completed_dates,
    _advance_cursor,
    close_daily_memory_sweep_cohort_clients,
    daily_memory_sweep_cohort_authority_from_environment,
    _POSTHOG_CLIENTS,
    MODEL_INVOCATION_PATH,
    MODEL_INVOCATION_FENCE_COLLECTION,
    MODEL_INVOCATION_SCHEMA_VERSION,
    _invoke_model_once,
    cleanup_expired_daily_memory_sweep_stages,
    read_daily_memory_sweep_cohort_assignment,
    run_daily_memory_sweep_scheduler,
    produce_completed_day_daily_summary_sources,
    firestore_daily_sweep_source_provider,
)
from models.product_memory import normalized_memory_content_key
from utils.llm.usage_tracker import get_current_context


def _candidate(**updates):
    value = {
        "candidate_id": "fact-alice-role",
        "kind": "fact",
        "operation": "add",
        "content": "Alice owns release review",
        "source_id": "conversation-1",
        "source_type": "conversation",
        "source_refs": ("conversation:conversation-1",),
        "slot": "release_role",
    }
    value.update(updates)
    return DailySweepCandidate.model_validate(value)


def _packet_kwargs(local_date, timezone_name="America/New_York"):
    window = completed_local_day_window(local_date, timezone_name)
    return {
        "timezone_name": timezone_name,
        "window_id": window.window_id,
        "window_start_utc": window.start_utc,
        "window_end_utc": window.end_utc,
        "complete": True,
    }


def test_plan_is_deterministic_and_direct_statement_wins_over_inference():
    inferred = _candidate(candidate_id="infer", source_id="summary-1")
    direct = _candidate(
        candidate_id="direct",
        source_id="statement-1",
        source_type="explicit_user_statement",
        authority=SweepAuthority.direct_user_statement,
    )

    first = plan_daily_memory_sweep(
        DailySweepInput(
            uid="user-1",
            local_date=date(2026, 8, 23),
            account_generation=4,
            source_generation=7,
            **_packet_kwargs(date(2026, 8, 23)),
            candidates=(inferred, direct),
        )
    )
    second = plan_daily_memory_sweep(
        DailySweepInput(
            uid="user-1",
            local_date=date(2026, 8, 23),
            account_generation=4,
            source_generation=7,
            **_packet_kwargs(date(2026, 8, 23)),
            candidates=(direct, inferred),
        )
    )

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert [item.candidate_id for item in first.candidates] == ["direct"]
    assert first.skipped[0].reason == "lower_authority"


def test_inference_cannot_invent_a_trigger_and_raw_pixels_are_rejected():
    with pytest.raises(ValueError, match="never invent"):
        _candidate(
            kind="trigger",
            operation="add",
            trigger_condition={"schema_version": "jit_trigger.v1", "keywords": ["release"]},
        )
    with pytest.raises(ValueError, match="raw image/pixel"):
        _candidate(source_id="screenshot_bytes:abc")
    with pytest.raises(ValueError, match="raw image/base64"):
        _candidate(
            kind="trigger",
            operation="repair",
            target_memory_id="trigger-1",
            trigger_condition={"keywords": ["release"], "nested": {"image": "data:image/png;base64,abc"}},
        )


def test_equal_authority_winner_is_order_independent_and_subject_scoped():
    left = _candidate(candidate_id="left", source_id="summary-left", content="Alice owns release review")
    right = _candidate(candidate_id="right", source_id="summary-right", content="Alice leads release review")
    first = plan_daily_memory_sweep(
        DailySweepInput(
            uid="user-1",
            local_date=date(2026, 8, 23),
            account_generation=1,
            source_generation=1,
            **_packet_kwargs(date(2026, 8, 23)),
            candidates=(left, right),
        )
    )
    second = plan_daily_memory_sweep(
        DailySweepInput(
            uid="user-1",
            local_date=date(2026, 8, 23),
            account_generation=1,
            source_generation=1,
            **_packet_kwargs(date(2026, 8, 23)),
            candidates=(right, left),
        )
    )
    assert first.model_dump(mode="json") == second.model_dump(mode="json")

    third_party = _candidate(
        candidate_id="third-party",
        source_id="summary-third-party",
        content="Alice owns release review",
        subject_scope="third_party",
        subject_entity_id="alice",
    )
    scoped = plan_daily_memory_sweep(
        DailySweepInput(
            uid="user-1",
            local_date=date(2026, 8, 23),
            account_generation=1,
            source_generation=1,
            **_packet_kwargs(date(2026, 8, 23)),
            candidates=(left, third_party),
        )
    )
    assert len(scoped.candidates) == 2


def test_completed_windows_preserve_dst_23_and_25_hour_days():
    spring = completed_local_day_window(date(2026, 3, 8), "America/New_York")
    fall = completed_local_day_window(date(2026, 11, 1), "America/New_York")
    assert (spring.end_utc - spring.start_utc).total_seconds() == 23 * 3600
    assert (fall.end_utc - fall.start_utc).total_seconds() == 25 * 3600
    assert spring.window_id != fall.window_id


def test_packet_requires_explicit_complete_exact_window_and_onboarding_is_direct():
    incomplete = _packet_kwargs(date(2026, 8, 23), timezone_name="UTC")
    incomplete["complete"] = False
    with pytest.raises(ValueError, match="complete exact local-day"):
        DailySweepInput(
            uid="user-1",
            local_date=date(2026, 8, 23),
            account_generation=1,
            source_generation=1,
            **incomplete,
            candidates=(),
        )
    onboarding = _candidate(
        candidate_id="seed",
        source_id="seed-1",
        source_type="onboarding",
        authority=SweepAuthority.direct_user_statement,
    )
    assert onboarding.authority.rank == SweepAuthority.direct_user_statement.rank


def test_completed_day_eligibility_proof_excludes_discarded_and_unfinished_rows():
    finished = {"status": "completed", "finished_at": datetime(2026, 8, 23, tzinfo=timezone.utc)}
    assert _completed_day_row_eligibility(finished) == "eligible"
    assert _completed_day_row_eligibility({**finished, "discarded": True}) == "discarded"
    assert (
        _completed_day_row_eligibility({"status": "processing", "finished_at": finished["finished_at"]}) == "unfinished"
    )
    assert _completed_day_row_eligibility({"status": "completed"}) == "unfinished"


def test_runtime_source_status_counts_auxiliary_candidates_and_zero_sources():
    source = DailySweepRuntimeSources.from_iterables(
        onboarding_cold_start=(_candidate(source_type="onboarding", authority=SweepAuthority.direct_user_statement),),
        onboarding_source_keys=("onboarding:conversation-1",),
        complete=True,
        source_status="complete_zero",
    )
    assert source.source_status == "complete"
    assert source.onboarding_source_keys == ("onboarding:conversation-1",)
    zero = DailySweepRuntimeSources.from_iterables(
        onboarding_source_keys=("onboarding:conversation-empty",),
        complete=True,
        source_status="complete_zero",
    )
    assert zero.candidates() == ()
    assert zero.onboarding_source_keys


def test_authority_is_closed_by_default():
    output = run_daily_memory_sweep(
        "user-1",
        "America/New_York",
        datetime(2026, 8, 24, 12, tzinfo=timezone.utc),
        {},
        db_client=object(),
    )
    assert output.status == "disabled"
    assert output.committed_count == 0


class _Snapshot:
    def __init__(self, value=None):
        self.value = value
        self.exists = value is not None

    def to_dict(self):
        return self.value


class _Ref:
    def __init__(self, store, path):
        self.store = store
        self.path = path

    def get(self, **_kwargs):
        return _Snapshot(self.store.get(self.path))

    def set(self, value, merge=False):
        if merge and self.path in self.store:
            current = dict(self.store[self.path])
            current.update(value)
            self.store[self.path] = current
        else:
            self.store[self.path] = dict(value)

    def create(self, value):
        if self.path in self.store:
            raise RuntimeError("already exists")
        self.store[self.path] = dict(value)


class _EmptyCollection:
    def where(self, *args, **kwargs):
        return self

    def limit(self, _count):
        return self

    def stream(self):
        return []


class _Transaction:
    def get(self, ref):
        return ref.get()

    def set(self, ref, value, merge=False):
        ref.set(value, merge=merge)


class _Db:
    def __init__(self):
        self.store = {}

    def document(self, path):
        return _Ref(self.store, path)

    def collection(self, _path):
        return _EmptyCollection()

    def transaction(self):
        return _Transaction()


def _open_control(monkeypatch):
    control = MemoryControlState(
        uid="user-1",
        head_commit_id="head0",
        account_generation=4,
        source_generation=7,
    )
    monkeypatch.setattr(
        "utils.memory.daily_memory_sweep.read_account_deletion_projection_fence",
        lambda _uid, db_client: type("Fence", (), {"blocks_projection_writes": False})(),
    )
    monkeypatch.setattr(
        "utils.memory.daily_memory_sweep.ensure_canonical_apply_control_state",
        lambda _uid, db_client: control,
    )
    monkeypatch.setattr(
        "utils.memory.daily_memory_sweep.firestore.transactional",
        lambda function: lambda transaction, *args: function(transaction, *args),
    )
    return control


def test_runner_uses_local_completed_days_and_cursor(monkeypatch):
    db = _Db()
    control = _open_control(monkeypatch)
    db.document("users/user-1/memory_state/apply_control").set(control.model_dump(mode="json"))
    written = []
    monkeypatch.setattr(
        "utils.memory.daily_memory_sweep._apply_candidate",
        lambda uid, local_date, candidate, **kwargs: (written.append(candidate.candidate_id) or "mem-1", None),
    )
    monkeypatch.setattr("utils.memory.daily_memory_sweep._finish_receipt", lambda *args, **kwargs: None)

    packet = DailySweepInput(
        uid="user-1",
        local_date=date(2026, 8, 23),
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        **_packet_kwargs(date(2026, 8, 23)),
        candidates=(_candidate(),),
    )
    first = run_daily_memory_sweep(
        "user-1",
        "America/New_York",
        datetime(2026, 8, 24, 12, tzinfo=timezone.utc),
        {packet.local_date: packet},
        db_client=db,
        authority=SweepAuthorityState(enabled=True),
    )
    second = run_daily_memory_sweep(
        "user-1",
        "America/New_York",
        datetime(2026, 8, 24, 13, tzinfo=timezone.utc),
        {packet.local_date: packet},
        db_client=db,
        authority=SweepAuthorityState(enabled=True),
    )

    assert first.status == "committed"
    assert first.completed_local_dates == (date(2026, 8, 23),)
    assert written == ["fact-alice-role"]
    assert second.status == "not_due"


def test_unknown_slot_fails_that_candidate_not_the_day(monkeypatch):
    db = _Db()
    control = _open_control(monkeypatch)
    db.document("users/user-1/memory_state/apply_control").set(control.model_dump(mode="json"))
    written = []

    def apply(_uid, _local_date, candidate, **_kwargs):
        if candidate.candidate_id == "fact-bad-slot":
            raise ValueError("unsupported knowledge ledger slot: mystery")
        written.append(candidate.candidate_id)
        return "mem-ok", None

    monkeypatch.setattr("utils.memory.daily_memory_sweep._apply_candidate", apply)
    monkeypatch.setattr("utils.memory.daily_memory_sweep._finish_receipt", lambda *args, **kwargs: None)

    packet = DailySweepInput(
        uid="user-1",
        local_date=date(2026, 8, 23),
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        **_packet_kwargs(date(2026, 8, 23)),
        candidates=(
            _candidate(candidate_id="fact-bad-slot", source_id="conversation-bad"),
            _candidate(candidate_id="fact-ok", source_id="conversation-ok", content="Alice ships Fridays", slot=None),
        ),
    )
    output = run_daily_memory_sweep(
        "user-1",
        "America/New_York",
        datetime(2026, 8, 24, 12, tzinfo=timezone.utc),
        {packet.local_date: packet},
        db_client=db,
        authority=SweepAuthorityState(enabled=True),
    )

    assert output.status == "committed"
    assert output.skipped_count == 1
    assert written == ["fact-ok"]


def test_runner_limits_missed_day_catch_up(monkeypatch):
    db = _Db()
    control = _open_control(monkeypatch)
    db.document("users/user-1/memory_state/apply_control").set(control.model_dump(mode="json"))
    db.document("users/user-1/memory_control/daily_memory_sweep").set(
        {
            "schema_version": "daily_memory_sweep_cursor.v1",
            "uid": "user-1",
            "account_generation": control.account_generation,
            "source_generation": control.source_generation,
            "generation": 0,
            "timezone_name": "America/New_York",
            "last_completed_local_date": "2026-08-19",
            "last_completed_window_id": "legacy-test-window",
            "last_completed_window_start_utc": datetime(2026, 8, 19, 4, tzinfo=timezone.utc),
            "last_completed_window_end_utc": datetime(2026, 8, 20, 4, tzinfo=timezone.utc),
            "updated_at": datetime(2026, 8, 20, tzinfo=timezone.utc),
        }
    )
    monkeypatch.setattr(
        "utils.memory.daily_memory_sweep._apply_candidate",
        lambda uid, local_date, candidate, **kwargs: ("mem-1", None),
    )
    monkeypatch.setattr("utils.memory.daily_memory_sweep._finish_receipt", lambda *args, **kwargs: None)
    packets = {
        day: DailySweepInput(
            uid="user-1",
            local_date=day,
            account_generation=control.account_generation,
            source_generation=control.source_generation,
            **_packet_kwargs(day),
            candidates=(),
        )
        for day in (date(2026, 8, 20), date(2026, 8, 21), date(2026, 8, 22), date(2026, 8, 23))
    }

    output = run_daily_memory_sweep(
        "user-1",
        "America/New_York",
        datetime(2026, 8, 24, 12, tzinfo=timezone.utc),
        packets,
        db_client=db,
        authority=SweepAuthorityState(enabled=True),
    )

    assert output.completed_local_dates == tuple(
        date(2026, 8, 20) + __import__("datetime").timedelta(days=index) for index in range(MAX_CATCH_UP_DAYS)
    )


def test_runner_blocks_generation_mismatch_before_writes(monkeypatch):
    db = _Db()
    control = _open_control(monkeypatch)
    packet = DailySweepInput(
        uid="user-1",
        local_date=date(2026, 8, 23),
        account_generation=control.account_generation,
        source_generation=control.source_generation + 1,
        **_packet_kwargs(date(2026, 8, 23)),
        candidates=(_candidate(),),
    )
    output = run_daily_memory_sweep(
        "user-1",
        "America/New_York",
        datetime(2026, 8, 24, 12, tzinfo=timezone.utc),
        {packet.local_date: packet},
        db_client=db,
        authority=SweepAuthorityState(enabled=True),
    )
    assert output.status == "blocked"
    assert output.blocked_reason == "input_generation_mismatch"
    assert not db.store


def test_timezone_reconcile_rolls_sweep_namespace_without_global_generation_or_anchor_reset(monkeypatch):
    db = _Db()
    control = _open_control(monkeypatch)
    db.document("users/user-1/memory_state/apply_control").set(control.model_dump(mode="json"))
    old_window = completed_local_day_window(date(2026, 8, 23), "America/New_York")
    db.document("users/user-1/memory_control/daily_memory_sweep").set(
        {
            "schema_version": "daily_memory_sweep_cursor.v1",
            "uid": "user-1",
            "account_generation": control.account_generation,
            "source_generation": control.source_generation,
            "generation": 1,
            "timezone_name": "America/New_York",
            "last_completed_local_date": "2026-08-23",
            "last_completed_window_id": old_window.window_id,
            "last_completed_window_start_utc": old_window.start_utc,
            "last_completed_window_end_utc": old_window.end_utc,
            "updated_at": datetime(2026, 8, 24, tzinfo=timezone.utc),
        }
    )
    assert reconcile_daily_memory_sweep_timezone(
        "user-1",
        "UTC",
        db_client=db,
        reconciliation_authorized=True,
    )
    updated_control = db.document("users/user-1/memory_state/apply_control").get().to_dict()
    updated_cursor = db.document("users/user-1/memory_control/daily_memory_sweep").get().to_dict()
    assert updated_control["source_generation"] == control.source_generation
    assert updated_cursor["source_generation"] == control.source_generation
    assert updated_cursor["sweep_generation"] == 2
    assert updated_cursor["timezone_name"] == "UTC"
    assert updated_cursor["last_completed_local_date"] == "2026-08-23"


def test_cohort_reader_is_backend_read_only_and_injectable(monkeypatch):
    calls = []

    class Reader:
        def get_feature_flag(self, flag, uid, **kwargs):
            calls.append((flag, uid, kwargs))
            return True

    assert read_daily_memory_sweep_cohort_assignment("user-1", "memory-sweep", resolver=Reader())
    assert calls == [("memory-sweep", "user-1", {"only_evaluate_locally": False, "send_feature_flag_events": False})]
    assert not read_daily_memory_sweep_cohort_assignment("user-1", "memory-sweep", resolver=lambda *_: "true")
    monkeypatch.delenv("POSTHOG_PROJECT_API_KEY", raising=False)
    assert not read_daily_memory_sweep_cohort_assignment("user-1", "memory-sweep")


def test_cohort_reader_distinguishes_false_from_posthog_outage(monkeypatch):
    assert (
        read_daily_memory_sweep_cohort_assignment("user-1", "memory-sweep", resolver=lambda *_: False)
        is DailySweepCohortDecision.disabled
    )
    assert (
        read_daily_memory_sweep_cohort_assignment(
            "user-1", "memory-sweep", resolver=lambda *_: (_ for _ in ()).throw(RuntimeError("posthog down"))
        )
        is DailySweepCohortDecision.unavailable
    )


def test_scheduler_requeues_posthog_outage_without_calling_source_provider():
    source_calls = []
    summary = run_daily_memory_sweep_scheduler(
        db_client=object(),
        now=datetime(2026, 8, 24, 12, tzinfo=timezone.utc),
        uid_inventory=("user-1",),
        source_provider=lambda *_args, **_kwargs: source_calls.append(True),
        timezone_resolver=lambda _uid: "UTC",
        authority=SweepAuthorityState(enabled=True),
        cohort_authority=DailySweepCohortAuthority(enabled=True, cohort_name="memory-sweep"),
        cohort_authorizer=lambda *_args: DailySweepCohortDecision.unavailable,
    )
    assert summary.failed_uids == ("user-1",)
    assert summary.completed_uids == ()
    assert source_calls == []


def test_scheduler_never_treats_disabled_cohort_as_unrestricted(monkeypatch):
    summary = run_daily_memory_sweep_scheduler(
        db_client=object(),
        now=datetime(2026, 8, 24, 12, tzinfo=timezone.utc),
        uid_inventory=("user-1",),
        source_provider=lambda *_args, **_kwargs: None,
        timezone_resolver=lambda _uid: "UTC",
        authority=SweepAuthorityState(enabled=True),
        cohort_authority=DailySweepCohortAuthority(enabled=False, cohort_name=""),
        cohort_authorizer=lambda *_args: True,
    )
    assert summary.attempted_users == 0
    assert summary.errors == ("cohort_disabled",)


@pytest.mark.parametrize(
    "authority, cohort",
    [
        (SweepAuthorityState(enabled=False), DailySweepCohortAuthority(enabled=False, cohort_name="")),
        (
            SweepAuthorityState(enabled=True, kill_switch_active=True),
            DailySweepCohortAuthority(enabled=True, cohort_name="sweep"),
        ),
    ],
)
def test_scheduler_cleanup_runs_even_when_rollout_is_closed(monkeypatch, authority, cohort):
    cleaned = []
    monkeypatch.setattr(
        "utils.memory.daily_memory_sweep.cleanup_expired_daily_memory_sweep_stages",
        lambda uid, **_kwargs: cleaned.append(uid),
    )
    summary = run_daily_memory_sweep_scheduler(
        db_client=object(),
        now=datetime(2026, 8, 24, 12, tzinfo=timezone.utc),
        uid_inventory=("user-1", "user-2"),
        source_provider=lambda *_args, **_kwargs: None,
        timezone_resolver=lambda _uid: "UTC",
        authority=authority,
        cohort_authority=cohort,
        cohort_authorizer=None,
    )
    assert cleaned == ["user-1", "user-2"]
    assert summary.attempted_users == 0


@pytest.mark.parametrize("decision", [DailySweepCohortDecision.disabled, DailySweepCohortDecision.unavailable])
def test_scheduler_cohort_gate_precedes_timezone_reconciliation_and_all_sweep_writes(decision):
    db = _Db()
    source_calls = []
    reconciliation_calls = []
    summary = run_daily_memory_sweep_scheduler(
        db_client=db,
        now=datetime(2026, 8, 24, 12, tzinfo=timezone.utc),
        uid_inventory=("user-1",),
        source_provider=lambda *_args, **_kwargs: source_calls.append(True),
        timezone_resolver=lambda _uid: "America/Los_Angeles",
        timezone_reconciler=lambda *_args: reconciliation_calls.append(True),
        authority=SweepAuthorityState(enabled=True),
        cohort_authority=DailySweepCohortAuthority(enabled=True, cohort_name="memory-sweep"),
        cohort_authorizer=lambda *_args: decision,
    )
    assert source_calls == []
    assert reconciliation_calls == []
    assert db.store == {}
    if decision is DailySweepCohortDecision.disabled:
        assert summary.completed_uids == ("user-1",)
    else:
        assert summary.failed_uids == ("user-1",)


def test_stale_overlapping_cursor_writer_cannot_move_cursor_backward(monkeypatch):
    db = _Db()
    control = _open_control(monkeypatch)
    db.document("users/user-1/memory_state/apply_control").set(control.model_dump(mode="json"))
    current_window = completed_local_day_window(date(2026, 8, 24), "UTC")
    current = DailySweepCursor(
        uid="user-1",
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        timezone_name="UTC",
        generation=2,
        last_completed_local_date=date(2026, 8, 24),
        last_completed_window_id=current_window.window_id,
        last_completed_window_start_utc=current_window.start_utc,
        last_completed_window_end_utc=current_window.end_utc,
    )
    cursor_ref = db.document("users/user-1/memory_control/daily_memory_sweep")
    cursor_ref.set(current.model_dump(mode="json"))
    stale_window = completed_local_day_window(date(2026, 8, 23), "UTC")
    stale = current.model_copy(
        update={
            "generation": 1,
            "last_completed_local_date": date(2026, 8, 23),
            "last_completed_window_id": stale_window.window_id,
            "last_completed_window_start_utc": stale_window.start_utc,
            "last_completed_window_end_utc": stale_window.end_utc,
        }
    )
    assert not _advance_cursor(
        db,
        "user-1",
        control,
        stale,
        date(2026, 8, 23),
        "UTC",
        stale_window.start_utc,
        stale_window.end_utc,
        stale_window.window_id,
    )
    assert cursor_ref.get().to_dict() == current.model_dump(mode="json")


def test_cohort_environment_requires_the_fixed_flag_binding(monkeypatch):
    monkeypatch.setenv("MEMORY_DAILY_MEMORY_SWEEP_COHORT_ENABLED", "true")
    monkeypatch.setenv("MEMORY_DAILY_MEMORY_SWEEP_COHORT_NAME", "legacy-alias")
    monkeypatch.delenv("MEMORY_DAILY_MEMORY_SWEEP_COHORT_FLAG", raising=False)
    authority = daily_memory_sweep_cohort_authority_from_environment()
    assert authority.enabled is True
    assert authority.cohort_name == ""


def test_cached_summary_requires_exact_completed_day_eligibility_attestation():
    window = completed_local_day_window(date(2026, 8, 23), "UTC")
    payload = {
        "complete": True,
        "source_status": "complete",
        "eligibility_proof": "completed_transcript_v1",
        "eligibility_attestation": {
            "schema_version": "completed_day_eligibility.v1",
            "local_date": "2026-08-23",
            "timezone_name": "UTC",
            "window_id": window.window_id,
            "window_start_utc": window.start_utc,
            "window_end_utc": window.end_utc,
            "eligible_count": 1,
            "discarded_count": 0,
            "processing_count": 0,
            "unfinished_count": 0,
        },
    }
    assert _cached_summary_eligibility_attested(payload, local_date=date(2026, 8, 23), window=window)
    payload["eligibility_attestation"]["processing_count"] = 1
    assert not _cached_summary_eligibility_attested(payload, local_date=date(2026, 8, 23), window=window)


def test_normalized_content_identity_is_casefolded_and_whitespace_stable():
    assert normalized_memory_content_key(" Alice   Owns Release Review ") == normalized_memory_content_key(
        "alice owns release review"
    )


def test_onboarding_source_receipt_consumes_multi_candidate_and_zero_sources(monkeypatch):
    db = _Db()
    control = _open_control(monkeypatch)
    db.document("users/user-1/memory_state/apply_control").set(control.model_dump(mode="json"))
    local_date = date(2026, 8, 23)
    window = completed_local_day_window(local_date, "America/New_York")
    first = _candidate(
        candidate_id="onboarding-a",
        source_id="onboarding:conversation-1",
        source_type="onboarding",
        authority=SweepAuthority.direct_user_statement,
    )
    second = first.model_copy(update={"candidate_id": "onboarding-b", "content": "Alice lives in NYC"})
    for candidate in (first, second):
        db.document(
            f"users/user-1/daily_memory_sweep_receipts/"
            f"{_receipt_id('user-1', local_date, candidate, account_generation=4, source_generation=7)}"
        ).set({"receipt_state": "committed"})
    assert _finish_onboarding_sources(
        db,
        "user-1",
        local_date,
        ("onboarding:conversation-1", "onboarding:conversation-empty"),
        (first, second),
        account_generation=4,
        source_generation=7,
        window=window,
    )
    consumed = db.document("users/user-1/memory_control/daily_memory_sweep_onboarding").get().to_dict()
    assert set(consumed["consumed_source_keys"]) == {
        "onboarding:conversation-1",
        "onboarding:conversation-empty",
    }


@pytest.mark.parametrize("new_timezone", ["America/Los_Angeles", "Europe/London"])
def test_timezone_transition_bridge_is_contiguous_and_bounded(new_timezone):
    prior = completed_local_day_window(date(2026, 8, 23), "America/New_York")
    bridge_date = prior.end_utc.astimezone(ZoneInfo(new_timezone)).date()
    bridge = timezone_transition_window(
        bridge_date,
        new_timezone,
        coverage_start_utc=prior.end_utc,
    )
    next_window = completed_local_day_window(bridge_date + timedelta(days=1), new_timezone)
    assert bridge.start_utc == prior.end_utc
    assert bridge.end_utc == next_window.start_utc
    cursor = DailySweepCursor(
        uid="user-1",
        account_generation=1,
        source_generation=1,
        timezone_name=new_timezone,
        last_completed_local_date=date(2026, 8, 23),
        last_completed_window_id=prior.window_id,
        last_completed_window_start_utc=prior.start_utc,
        last_completed_window_end_utc=prior.end_utc,
        pending_transition_local_date=bridge_date,
        pending_transition_window_id=bridge.window_id,
        pending_transition_start_utc=bridge.start_utc,
        pending_transition_end_utc=bridge.end_utc,
    )
    pending = _pending_completed_dates(
        cursor,
        timezone_name=new_timezone,
        now=datetime(2026, 8, 28, 12, tzinfo=timezone.utc),
    )
    assert pending[0] == bridge_date
    assert len(pending) == MAX_CATCH_UP_DAYS


def test_onboarding_receipts_are_exhaustive_beyond_32(monkeypatch):
    db = _Db()
    control = _open_control(monkeypatch)
    db.document("users/user-1/memory_state/apply_control").set(control.model_dump(mode="json"))
    window = completed_local_day_window(date(2026, 8, 23), "America/New_York")
    source_keys = tuple(f"onboarding:conversation-{index}" for index in range(33))
    assert _finish_onboarding_sources(
        db,
        "user-1",
        date(2026, 8, 23),
        source_keys[:32],
        (),
        account_generation=4,
        source_generation=7,
        window=window,
    )
    assert _finish_onboarding_sources(
        db,
        "user-1",
        date(2026, 8, 23),
        source_keys[32:],
        (),
        account_generation=4,
        source_generation=7,
        window=window,
    )
    consumed = db.document("users/user-1/memory_control/daily_memory_sweep_onboarding").get().to_dict()
    assert consumed["consumed_source_keys"] == sorted(source_keys)


def test_onboarding_requires_non_discarded_completed_finalized_transcript():
    finished = {"status": "completed", "finished_at": datetime(2026, 8, 23, tzinfo=timezone.utc)}
    assert _onboarding_transcript_eligibility({**finished, "finalization_status": "completed"}) == "eligible"
    assert _onboarding_transcript_eligibility({**finished, "finalization_status": "processing"}) == "unfinished"
    assert (
        _onboarding_transcript_eligibility({**finished, "finalization_status": "completed", "discarded": True})
        == "discarded"
    )


def test_posthog_cohort_client_is_reused_and_closed(monkeypatch):
    created = []
    closed = []

    class FakePosthog:
        def __init__(self, **_kwargs):
            created.append(self)

        def get_feature_flag(self, *_args, **_kwargs):
            return True

        def shutdown(self):
            closed.append(self)

    monkeypatch.setitem(sys.modules, "posthog", SimpleNamespace(Posthog=FakePosthog))
    monkeypatch.setenv("POSTHOG_PROJECT_API_KEY", "project-key")
    monkeypatch.setenv("POSTHOG_HOST", "https://posthog.test")
    _POSTHOG_CLIENTS.clear()
    assert read_daily_memory_sweep_cohort_assignment("user-1", "memory-sweep")
    assert read_daily_memory_sweep_cohort_assignment("user-2", "memory-sweep")
    assert len(created) == 1
    close_daily_memory_sweep_cohort_clients()
    assert closed == created


def test_onboarding_continuation_reuses_durable_candidate_page(monkeypatch):
    db = _Db()
    calls = []

    def extractor(_uid, _text):
        calls.append(True)
        return tuple(SimpleNamespace(content=f"fact-{index}") for index in range(20))

    first = _load_or_stage_onboarding_candidates(
        "user-1",
        "onboarding:conversation-1",
        "conversation-1",
        "stable transcript",
        db_client=db,
        extractor=extractor,
    )
    assert first is not None and len(first) == 20
    staged = next(payload for path, payload in db.store.items() if "onboarding_staged" in path)
    assert staged["candidate_count"] == 20

    def should_not_extract(_uid, _text):
        raise AssertionError("continuation reran nondeterministic extraction")

    second = _load_or_stage_onboarding_candidates(
        "user-1",
        "onboarding:conversation-1",
        "conversation-1",
        "stable transcript",
        db_client=db,
        extractor=should_not_extract,
    )
    assert second == first
    assert len(second[8:]) == 12
    assert len(calls) == 1


def test_model_invocation_fence_is_at_most_once_under_overlapping_threads():
    db = _Db()
    calls = []
    results = []

    def builder():
        calls.append(True)
        # Give the second worker a chance to contend at the durable boundary.
        time.sleep(0.01)
        return ({"candidate_id": "candidate-1"},)

    workers = [
        threading.Thread(
            target=lambda: results.append(_invoke_model_once(db, "user-1", "overlap", candidate_builder=builder))
        )
        for _ in range(2)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert len(calls) == 1
    assert results == [({"candidate_id": "candidate-1"},)] * 2
    invocation = db.document(f"users/user-1/{MODEL_INVOCATION_PATH}/overlap").get().to_dict()
    assert invocation["schema_version"] == MODEL_INVOCATION_SCHEMA_VERSION
    assert invocation["state"] == "returned"


def test_fenced_invocation_survives_wipe_race_without_recreating_user_state(monkeypatch):
    db = _Db()
    control = _open_control(monkeypatch)
    db.document("users/user-1/memory_state/apply_control").set(control.model_dump(mode="json"))
    claimed = threading.Event()
    release_provider = threading.Event()
    paid_call_count = 0
    provider_results = []

    def provider():
        nonlocal paid_call_count
        paid_call_count += 1
        claimed.set()
        assert release_provider.wait(timeout=2)
        return ({"candidate_id": "after-wipe"},)

    first = threading.Thread(
        target=lambda: provider_results.append(
            _invoke_model_once(
                db,
                "user-1",
                "wipe-race-generation-4-source-7-window-a",
                candidate_builder=provider,
                account_generation=control.account_generation,
                source_generation=control.source_generation,
                sweep_generation=1,
                window_id="window-a",
            )
        )
    )
    first.start()
    assert claimed.wait(timeout=2)

    # Simulate the account deletion transaction winning after claim: it
    # removes every user subtree, but deliberately leaves the top-level
    # content-free invocation fence behind.
    db.document("account_deletions/user-1").set({"wipe_status": "running"})
    for path in list(db.store):
        if path.startswith("users/user-1/"):
            db.store.pop(path)
    second = threading.Thread(
        target=lambda: provider_results.append(
            _invoke_model_once(
                db,
                "user-1",
                "wipe-race-generation-4-source-7-window-a",
                candidate_builder=lambda: (_ for _ in ()).throw(AssertionError("paid twice")),
                account_generation=control.account_generation,
                source_generation=control.source_generation,
                sweep_generation=1,
                window_id="window-a",
            )
        )
    )
    second.start()
    release_provider.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert paid_call_count == 1
    assert provider_results == [None, None]
    assert db.store.keys() == {
        "account_deletions/user-1",
        f"{MODEL_INVOCATION_FENCE_COLLECTION}/wipe-race-generation-4-source-7-window-a",
    }
    fence = db.store[f"{MODEL_INVOCATION_FENCE_COLLECTION}/wipe-race-generation-4-source-7-window-a"]
    assert fence["state"] == "indeterminate"
    assert all(not path.startswith("users/user-1/") for path in db.store)


def test_generation_roll_does_not_reuse_old_returned_payload(monkeypatch):
    db = _Db()
    control = _open_control(monkeypatch)
    db.document("users/user-1/memory_state/apply_control").set(control.model_dump(mode="json"))
    old_id = "generation-4-source-7-window-a"
    assert _invoke_model_once(
        db,
        "user-1",
        old_id,
        candidate_builder=lambda: ({"candidate_id": "old"},),
        account_generation=4,
        source_generation=7,
        sweep_generation=1,
        window_id="window-a",
    ) == ({"candidate_id": "old"},)
    # A generation-fenced logical ID cannot consume the previous returned
    # payload, even if a caller accidentally supplies the same source text.
    assert (
        _invoke_model_once(
            db,
            "user-1",
            old_id,
            candidate_builder=lambda: (_ for _ in ()).throw(AssertionError("old payload reused")),
            account_generation=5,
            source_generation=7,
            sweep_generation=1,
            window_id="window-a",
        )
        is None
    )


def test_model_return_is_reused_after_stage_gap_and_pending_is_fail_closed():
    db = _Db()
    calls = []

    def builder():
        calls.append(True)
        return ({"candidate_id": "candidate-after-provider-return"},)

    first = _invoke_model_once(db, "user-1", "stage-gap", candidate_builder=builder)
    # The candidate stage can be absent after a worker crash, but the durable
    # invocation receipt still makes a retry free and deterministic.
    second = _invoke_model_once(
        db,
        "user-1",
        "stage-gap",
        candidate_builder=lambda: (_ for _ in ()).throw(AssertionError("provider charged twice")),
    )
    assert first == second
    assert len(calls) == 1

    pending_ref = db.document(f"users/user-1/{MODEL_INVOCATION_PATH}/pending-crash")
    pending_ref.set(
        {
            "schema_version": MODEL_INVOCATION_SCHEMA_VERSION,
            "uid": "user-1",
            "invocation_id": "pending-crash",
            "state": "pending",
            "lease_expires_at": datetime.now(timezone.utc) - timedelta(minutes=1),
        }
    )
    assert (
        _invoke_model_once(
            db,
            "user-1",
            "pending-crash",
            candidate_builder=lambda: (_ for _ in ()).throw(AssertionError("indeterminate call retried")),
        )
        is None
    )


class _CleanupRow:
    def __init__(self, path, payload, store):
        self.id = path.rsplit("/", 1)[-1]
        self._store = store
        self._path = path
        self.reference = self
        self._payload = payload

    def to_dict(self):
        return self._payload

    def delete(self):
        self._store.pop(self._path, None)

    def set(self, value, merge=False):
        current = dict(self._store.get(self._path, {})) if merge else {}
        for key, item in value.items():
            if item is firestore.DELETE_FIELD:
                current.pop(key, None)
            else:
                current[key] = item
        self._store[self._path] = current
        self._payload.clear()
        self._payload.update(current)


class _CleanupCollection:
    def __init__(self, rows):
        self.rows = rows

    def limit(self, _count):
        return self

    def stream(self):
        return iter(self.rows)


class _CleanupDb(_Db):
    def collection(self, path):
        rows = [
            _CleanupRow(row_path, payload, self.store)
            for row_path, payload in list(self.store.items())
            if row_path.startswith(path + "/")
        ]
        return _CleanupCollection(rows)


class _ExpiryQuery(_CleanupCollection):
    def __init__(self, rows):
        super().__init__(rows)
        self._limit = None

    def where(self, *args, **kwargs):
        predicate = kwargs.get("filter")
        if predicate is None and len(args) == 3:
            field, operator, value = args
        else:
            field = getattr(predicate, "field_path", "")
            operator = getattr(predicate, "op_string", "")
            value = getattr(predicate, "value", None)
        assert field == "expires_at" and operator == "<="
        return _ExpiryQuery(
            [
                row
                for row in self.rows
                if isinstance(row.to_dict().get("expires_at"), datetime) and row.to_dict()["expires_at"] <= value
            ]
        )

    def order_by(self, _field):
        self.rows = sorted(self.rows, key=lambda row: row.to_dict().get("expires_at"))
        return self

    def limit(self, count):
        self._limit = count
        return self

    def start_after(self, row):
        try:
            index = self.rows.index(row)
        except ValueError:
            return self
        result = _ExpiryQuery(self.rows[index + 1 :])
        result._limit = self._limit
        return result

    def stream(self):
        return iter(self.rows if self._limit is None else self.rows[: self._limit])


class _ExpiryCleanupDb(_CleanupDb):
    def collection(self, path):
        rows = [
            _CleanupRow(row_path, payload, self.store)
            for row_path, payload in list(self.store.items())
            if row_path.startswith(path + "/")
        ]
        return _ExpiryQuery(rows)


def test_expired_candidate_stages_are_bounded_but_indeterminate_claims_remain_closed():
    db = _CleanupDb()
    expired = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.store["users/user-1/daily_memory_sweep_daily_summary_staged/summary"] = {"expires_at": expired}
    db.store["users/user-1/daily_memory_sweep_onboarding_staged/onboarding"] = {"expires_at": expired}
    db.store["users/user-1/daily_memory_sweep_model_invocations/returned"] = {
        "invocation_id": "returned",
        "state": "returned",
        "expires_at": expired,
        "candidate_page": [{"content": "private fact"}],
        "candidate_digest": "digest",
    }
    db.store["users/user-1/daily_memory_sweep_model_invocations/pending"] = {
        "invocation_id": "pending",
        "state": "pending",
        "lease_expires_at": expired,
    }
    db.store["users/user-1/daily_memory_sweep_model_invocations/indeterminate"] = {
        "invocation_id": "indeterminate",
        "state": "indeterminate",
        "lease_expires_at": expired,
    }

    assert cleanup_expired_daily_memory_sweep_stages("user-1", db_client=db) == 3
    assert not any("staged" in path for path in db.store)
    returned = db.store["users/user-1/daily_memory_sweep_model_invocations/returned"]
    assert returned["state"] == "payload_expired"
    assert returned["at_most_once_tombstone"] is True
    assert "candidate_page" not in returned
    assert "candidate_digest" not in returned
    assert "users/user-1/daily_memory_sweep_model_invocations/pending" in db.store
    assert "users/user-1/daily_memory_sweep_model_invocations/indeterminate" in db.store


def test_expiry_query_skips_more_than_one_page_of_permanent_tombstones():
    db = _ExpiryCleanupDb()
    expired = datetime.now(timezone.utc) - timedelta(minutes=1)
    for index in range(140):
        db.store[f"users/user-1/{MODEL_INVOCATION_PATH}/tombstone-{index}"] = {
            "invocation_id": f"tombstone-{index}",
            "state": "indeterminate",
            "at_most_once_tombstone": True,
        }
    db.store[f"users/user-1/{MODEL_INVOCATION_PATH}/returned-after-tombstones"] = {
        "invocation_id": "returned-after-tombstones",
        "state": "returned",
        "expires_at": expired,
        "candidate_page": [{"content": "private"}],
    }

    assert cleanup_expired_daily_memory_sweep_stages("user-1", db_client=db, limit=128) == 1
    assert "candidate_page" not in db.store[f"users/user-1/{MODEL_INVOCATION_PATH}/returned-after-tombstones"]
    assert all(f"users/user-1/{MODEL_INVOCATION_PATH}/tombstone-{index}" in db.store for index in range(140))


def test_indeterminate_tombstone_survives_expired_lease_and_blocks_second_paid_call():
    db = _CleanupDb()
    paid_call_count = 0

    def provider_exception():
        nonlocal paid_call_count
        paid_call_count += 1
        raise RuntimeError("provider response was indeterminate")

    assert (
        _invoke_model_once(
            db,
            "user-1",
            "indeterminate-paid-call",
            candidate_builder=provider_exception,
        )
        is None
    )
    assert paid_call_count == 1

    # The provider exception leaves the original lease expired. Cleanup must
    # retain the identity fence rather than treating expiry as a free retry.
    invocation_path = "users/user-1/daily_memory_sweep_model_invocations/indeterminate-paid-call"
    db.store[invocation_path]["lease_expires_at"] = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert cleanup_expired_daily_memory_sweep_stages("user-1", db_client=db) == 0
    assert (
        _invoke_model_once(
            db,
            "user-1",
            "indeterminate-paid-call",
            candidate_builder=lambda: (_ for _ in ()).throw(AssertionError("charged twice")),
        )
        is None
    )
    assert paid_call_count == 1


def test_returned_payload_expiry_keeps_content_free_tombstone_and_blocks_replay():
    db = _CleanupDb()
    paid_call_count = 0

    def provider_return():
        nonlocal paid_call_count
        paid_call_count += 1
        return ({"candidate_id": "crashed-before-stage"},)

    assert _invoke_model_once(
        db,
        "user-1",
        "returned-before-stage",
        candidate_builder=provider_return,
    ) == ({"candidate_id": "crashed-before-stage"},)
    assert paid_call_count == 1

    # Simulate the source worker crashing before writing its candidate stage,
    # then let the bounded returned payload expire.
    invocation_path = "users/user-1/daily_memory_sweep_model_invocations/returned-before-stage"
    db.store[invocation_path]["expires_at"] = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert cleanup_expired_daily_memory_sweep_stages("user-1", db_client=db) == 1
    tombstone = db.store[invocation_path]
    assert tombstone["state"] == "payload_expired"
    assert "candidate_page" not in tombstone
    assert (
        _invoke_model_once(
            db,
            "user-1",
            "returned-before-stage",
            candidate_builder=lambda: (_ for _ in ()).throw(AssertionError("charged twice")),
        )
        is None
    )
    assert paid_call_count == 1


def test_user_export_includes_both_candidate_stages_and_model_receipts(monkeypatch):
    monkeypatch.setattr(data_export, "get_user_profile", lambda _uid: {})
    monkeypatch.setattr(data_export.conversations_db, "iter_all_conversations", lambda *_args, **_kwargs: ())
    monkeypatch.setattr(data_export.conversations_db, "iter_all_conversation_photos", lambda *_args, **_kwargs: ())
    monkeypatch.setattr(data_export, "get_people", lambda _uid: ())
    monkeypatch.setattr(data_export, "get_standalone_action_items", lambda *_args, **_kwargs: ())
    monkeypatch.setattr(data_export.chat_db, "iter_all_messages", lambda *_args, **_kwargs: ())

    def user_rows(_uid, collection):
        if collection in {
            "daily_memory_sweep_sources",
            "daily_memory_sweep_daily_summary_staged",
            "daily_memory_sweep_onboarding_staged",
            "daily_memory_sweep_model_invocations",
        }:
            yield {"id": f"{collection}-row", "candidate_page": [{"content": "private fact"}]}

    monkeypatch.setattr(data_export, "_iter_user_subcollection", user_rows)
    monkeypatch.setattr(data_export, "_iter_user_nested_subcollection", lambda *_args, **_kwargs: iter(()))

    payload = "".join(data_export._iter_user_data_export_from_spool("user-1", StringIO("[\n]")))
    export = __import__("json").loads(payload)

    assert {
        "daily_memory_sweep_sources",
        "daily_memory_sweep_daily_summary_staged",
        "daily_memory_sweep_onboarding_staged",
        "daily_memory_sweep_model_invocations",
    } <= set(export["task_data"])
    assert export["task_data"]["daily_memory_sweep_onboarding_staged"][0]["candidate_page"]


def test_onboarding_malformed_stage_fails_closed_without_reextracting(monkeypatch):
    db = _Db()
    _onboarding_staged_candidates_ref(db, "user-1", "onboarding:conversation-1").set(
        {
            "schema_version": "daily_memory_sweep_onboarding_stage.v1",
            "uid": "user-1",
            "source_key": "onboarding:conversation-1",
            "transcript_digest": "tampered",
            "candidate_digest": "tampered",
            "candidate_page": [],
        }
    )

    def should_not_extract(_uid, _text):
        raise AssertionError("malformed durable stage must not rerun extraction")

    assert (
        _load_or_stage_onboarding_candidates(
            "user-1",
            "onboarding:conversation-1",
            "conversation-1",
            "stable transcript",
            db_client=db,
            extractor=should_not_extract,
        )
        is None
    )


def _day_source(conversation_id, summary, transcript="", needs_folder=False):
    from utils.memory.daily_memory_sweep import CompletedDayConversationSource

    return CompletedDayConversationSource(
        conversation_id=conversation_id,
        summary_text=summary,
        transcript_text=transcript,
        needs_folder=needs_folder,
    )


def _agent_output(memories=(), folder_assignments=()):
    return SimpleNamespace(
        memories=list(memories),
        transcript_requests=[],
        folder_assignments=list(folder_assignments),
    )


def test_completed_day_model_candidates_are_staged_before_apply_and_reused(monkeypatch):
    db = _Db()
    control = _open_control(monkeypatch)
    db.document("users/user-1/memory_state/apply_control").set(control.model_dump(mode="json"))
    local_date = date(2026, 8, 23)
    window = completed_local_day_window(local_date, "UTC")
    monkeypatch.setattr(
        "utils.memory.daily_memory_sweep._read_completed_day_conversation_sources",
        lambda *_args, **_kwargs: ((_day_source("conversation-1", "stable summary"),), "complete"),
    )
    model = DailySweepModelAuthority(enabled=True, model_name="test", max_candidates=8, max_cost_usd=1.0)
    calls = []

    def agent(_uid, summary_rows, transcript_lookup, **_kwargs):
        calls.append(summary_rows)
        return _agent_output(
            memories=[SimpleNamespace(content="fact from first pass", conversation_ids=["conversation-1"])]
        )

    first = produce_completed_day_daily_summary_sources(
        "user-1",
        local_date,
        "UTC",
        control,
        db_client=db,
        model_authority=model,
        agent_runner=agent,
        window_override=window,
    )
    assert first.source_status == "complete"
    assert len(first.daily_summary) == 1
    assert first.daily_summary[0].source_refs == ("conversation:conversation-1",)
    assert len(calls) == 1

    assert calls[0] == (("conversation-1", "stable summary"),)
    staged = next(payload for path, payload in db.store.items() if "daily_summary_staged" in path)
    assert staged["candidate_count"] == 1
    assert staged["folder_assignments"] == []
    assert staged["candidate_digest"] == deterministic_contract_id(
        "daily-sweep-daily-summary-candidate-page",
        {"digests": [first.daily_summary[0].digest()], "folder_assignments": []},
    )

    def should_not_run(_uid, _rows, _lookup, **_kwargs):
        raise AssertionError("completed-day continuation reran the nondeterministic agent")

    second = produce_completed_day_daily_summary_sources(
        "user-1",
        local_date,
        "UTC",
        control,
        db_client=db,
        model_authority=model,
        agent_runner=should_not_run,
        window_override=window,
    )
    assert second.daily_summary == first.daily_summary
    assert len(calls) == 1


def test_qa_completed_day_rejects_a_stage_from_another_run(monkeypatch):
    db = _Db()
    control = _open_control(monkeypatch)
    db.document("users/user-1/memory_state/apply_control").set(control.model_dump(mode="json"))
    local_date = date(2026, 8, 23)
    window = completed_local_day_window(local_date, "UTC")
    monkeypatch.setattr(
        "utils.memory.daily_memory_sweep._read_completed_day_conversation_sources",
        lambda *_args, **_kwargs: ((_day_source("conversation-1", "stable summary"),), "complete"),
    )
    model = DailySweepModelAuthority(enabled=True, model_name="test", max_candidates=8, max_cost_usd=1.0)

    def agent(_uid, _rows, _lookup, **_kwargs):
        return _agent_output(
            memories=[SimpleNamespace(content="fact from prior run", conversation_ids=["conversation-1"])]
        )

    first = produce_completed_day_daily_summary_sources(
        "user-1",
        local_date,
        "UTC",
        control,
        db_client=db,
        model_authority=model,
        agent_runner=agent,
        window_override=window,
    )
    assert first.source_status == "complete"
    second = produce_completed_day_daily_summary_sources(
        "user-1",
        local_date,
        "UTC",
        control,
        db_client=db,
        model_authority=model,
        agent_runner=agent,
        window_override=window,
        qa_run_id="qa-run-1",
    )
    assert second.source_status == "incomplete"


def test_qa_source_provider_rejects_a_preexisting_packet(monkeypatch):
    db = _Db()
    control = _open_control(monkeypatch)
    db.document("users/user-1/memory_state/apply_control").set(control.model_dump(mode="json"))
    local_date = date(2026, 8, 23)
    db.document(f"users/user-1/daily_memory_sweep_sources/{local_date.isoformat()}").set(
        {"schema_version": "daily_memory_sweep.v1", "uid": "user-1", "complete": True}
    )
    with pytest.raises(ValueError, match="pre-existing source packet"):
        firestore_daily_sweep_source_provider(
            "user-1",
            local_date,
            control,
            db_client=db,
            timezone_name="UTC",
            qa_run_id="qa-run-1",
        )


def test_qa_completed_day_uses_tight_real_input_and_provider_envelope(monkeypatch):
    db = _Db()
    control = _open_control(monkeypatch)
    db.document("users/user-1/memory_state/apply_control").set(control.model_dump(mode="json"))
    local_date = date(2026, 8, 23)
    window = completed_local_day_window(local_date, "UTC")
    monkeypatch.setattr(
        "utils.memory.daily_memory_sweep._read_completed_day_conversation_sources",
        lambda *_args, **kwargs: (
            (_day_source("conversation-1", "stable summary"),),
            "complete",
        ),
    )
    model = DailySweepModelAuthority(
        enabled=True,
        model_name="test",
        max_candidates=1,
        max_cost_usd=QA_SWEEP_MAX_MODEL_COST_USD,
    )
    seen = {}

    def agent(_uid, _rows, _lookup, **kwargs):
        seen.update(kwargs)
        seen["usage_context"] = get_current_context()
        return _agent_output(
            memories=[SimpleNamespace(content="fact from QA pass", conversation_ids=["conversation-1"])]
        )

    result = produce_completed_day_daily_summary_sources(
        "user-1",
        local_date,
        "UTC",
        control,
        db_client=db,
        model_authority=model,
        agent_runner=agent,
        window_override=window,
        qa_run_id="qa-run-1",
    )
    assert result.source_status == "complete"
    assert result.model_cost_usd <= QA_SWEEP_MAX_MODEL_COST_USD
    # The QA receipt prices the checked-in Luna input/output envelope, rather
    # than only the short source spine; this stays below the 5-cent cap.
    assert result.model_cost_usd >= 0.0027
    assert seen["max_candidates"] == 1
    assert seen["max_transcript_fetches"] == QA_SWEEP_MAX_TRANSCRIPT_FETCHES
    assert seen["max_memory_lookups"] == QA_SWEEP_MAX_MEMORY_LOOKUPS
    assert seen["max_provider_retries"] == QA_SWEEP_MAX_SDK_RETRIES
    assert seen["usage_context"].uid == "user-1"
    assert seen["usage_context"].feature == "memories"
    assert get_current_context() is None
    assert QA_SWEEP_MAX_CATCH_UP_DAYS == 1
    assert QA_SWEEP_MAX_SUMMARY_CONVERSATIONS == 1
    assert QA_SWEEP_MAX_SUMMARY_INPUT_CHARACTERS == 2_000


def test_completed_day_agent_assigns_folders_for_unopened_conversations(monkeypatch):
    db = _Db()
    control = _open_control(monkeypatch)
    refreshes = []
    monkeypatch.setattr(
        "database.folders.update_folder_conversation_count",
        lambda uid, folder_id: refreshes.append((uid, folder_id)),
    )
    db.document("users/user-1/memory_state/apply_control").set(control.model_dump(mode="json"))
    local_date = date(2026, 8, 23)
    window = completed_local_day_window(local_date, "UTC")
    db.document("users/user-1/conversations/conversation-1").set(
        {"jit_first_open": {"state": "pending"}, "discarded": False}
    )
    monkeypatch.setattr(
        "utils.memory.daily_memory_sweep._read_completed_day_conversation_sources",
        lambda *_args, **_kwargs: (
            (
                _day_source("conversation-1", "planning summary", needs_folder=True),
                _day_source("conversation-2", "second summary"),
            ),
            "complete",
        ),
    )
    monkeypatch.setattr(
        "utils.memory.daily_memory_sweep._read_daily_sweep_folder_options",
        lambda _uid, db_client: (("folder-1", "Planning"),),
    )
    model = DailySweepModelAuthority(enabled=True, model_name="test", max_candidates=8, max_cost_usd=1.0)
    seen_kwargs = {}

    def agent(_uid, _rows, _lookup, **kwargs):
        seen_kwargs.update(kwargs)
        return _agent_output(
            memories=[SimpleNamespace(content="cross-day fact", conversation_ids=["conversation-1", "conversation-2"])],
            folder_assignments=[SimpleNamespace(conversation_id="conversation-1", folder_id="folder-1")],
        )

    result = produce_completed_day_daily_summary_sources(
        "user-1",
        local_date,
        "UTC",
        control,
        db_client=db,
        model_authority=model,
        agent_runner=agent,
        window_override=window,
    )
    assert result.source_status == "complete"
    assert seen_kwargs["folder_options"] == (("folder-1", "Planning"),)
    assert seen_kwargs["needs_folder_ids"] == ("conversation-1",)
    assert result.daily_summary[0].source_refs == (
        "conversation:conversation-1",
        "conversation:conversation-2",
    )
    staged = next(payload for path, payload in db.store.items() if "daily_summary_staged" in path)
    assert staged["folder_assignments"] == [{"conversation_id": "conversation-1", "folder_id": "folder-1"}]
    assert db.store["users/user-1/conversations/conversation-1"]["folder_id"] == "folder-1"
    assert refreshes == [("user-1", "folder-1")]


def test_folder_backstop_never_overwrites_and_requires_obligation(monkeypatch):
    from utils.memory.daily_memory_sweep import _apply_daily_sweep_folder_assignments

    refreshes = []
    monkeypatch.setattr(
        "database.folders.update_folder_conversation_count",
        lambda uid, folder_id: refreshes.append((uid, folder_id)),
    )
    monkeypatch.setattr(
        "utils.memory.daily_memory_sweep.firestore.transactional",
        lambda function: lambda transaction, *args: function(transaction, *args),
    )
    db = _Db()
    db.document("users/user-1/conversations/filed").set(
        {"jit_first_open": {"state": "pending"}, "folder_id": "existing", "discarded": False}
    )
    db.document("users/user-1/conversations/eager").set({"discarded": False})
    db.document("users/user-1/conversations/open-pending").set(
        {"jit_first_open": {"state": "pending"}, "discarded": False}
    )
    applied = _apply_daily_sweep_folder_assignments(
        "user-1",
        [
            {"conversation_id": "filed", "folder_id": "folder-1"},
            {"conversation_id": "eager", "folder_id": "folder-1"},
            {"conversation_id": "open-pending", "folder_id": "folder-1"},
            {"conversation_id": "open-pending", "folder_id": "not-a-folder"},
        ],
        db_client=db,
        valid_folder_ids={"folder-1"},
    )
    assert applied == 1
    assert db.store["users/user-1/conversations/filed"]["folder_id"] == "existing"
    assert "folder_id" not in db.store["users/user-1/conversations/eager"]
    assert db.store["users/user-1/conversations/open-pending"]["folder_id"] == "folder-1"
    assert refreshes == [("user-1", "folder-1")]


def test_completed_day_memory_without_valid_citation_is_dropped(monkeypatch):
    db = _Db()
    control = _open_control(monkeypatch)
    db.document("users/user-1/memory_state/apply_control").set(control.model_dump(mode="json"))
    local_date = date(2026, 8, 23)
    window = completed_local_day_window(local_date, "UTC")
    monkeypatch.setattr(
        "utils.memory.daily_memory_sweep._read_completed_day_conversation_sources",
        lambda *_args, **_kwargs: ((_day_source("conversation-1", "stable summary"),), "complete"),
    )
    model = DailySweepModelAuthority(enabled=True, model_name="test", max_candidates=8, max_cost_usd=1.0)

    def agent(_uid, _rows, _lookup, **_kwargs):
        return _agent_output(
            memories=[SimpleNamespace(content="fabricated provenance", conversation_ids=["not-in-day"])]
        )

    result = produce_completed_day_daily_summary_sources(
        "user-1",
        local_date,
        "UTC",
        control,
        db_client=db,
        model_authority=model,
        agent_runner=agent,
        window_override=window,
    )
    assert result.source_status == "complete_zero"
    assert result.daily_summary == ()


def test_completed_day_malformed_stage_fails_closed_without_reextracting(monkeypatch):
    db = _Db()
    control = _open_control(monkeypatch)
    db.document("users/user-1/memory_state/apply_control").set(control.model_dump(mode="json"))
    local_date = date(2026, 8, 23)
    window = completed_local_day_window(local_date, "UTC")
    ref = _daily_summary_staged_candidates_ref(
        db,
        "user-1",
        local_date,
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        window_id=window.window_id,
    )
    ref.set(
        {
            "schema_version": "daily_memory_sweep_daily_summary_stage.v2",
            "uid": "user-1",
            "local_date": local_date.isoformat(),
            "timezone_name": "UTC",
            "account_generation": control.account_generation,
            "source_generation": control.source_generation,
            "window_id": window.window_id,
            "window_start_utc": window.start_utc,
            "window_end_utc": window.end_utc,
            "transcript_digest": "tampered",
            "candidate_digest": "tampered",
            "candidate_page": [],
            "candidate_count": 0,
            "folder_assignments": [],
        }
    )
    monkeypatch.setattr(
        "utils.memory.daily_memory_sweep._read_completed_day_conversation_sources",
        lambda *_args, **_kwargs: ((_day_source("conversation-1", "stable summary"),), "complete"),
    )
    model = DailySweepModelAuthority(enabled=True, model_name="test", max_candidates=8, max_cost_usd=1.0)

    def should_not_run(_uid, _rows, _lookup, **_kwargs):
        raise AssertionError("malformed completed-day stage must not rerun the agent")

    result = produce_completed_day_daily_summary_sources(
        "user-1",
        local_date,
        "UTC",
        control,
        db_client=db,
        model_authority=model,
        agent_runner=should_not_run,
        window_override=window,
    )
    assert result.source_status == "incomplete"


def test_legacy_compatibility_proof_allows_more_than_two_unslotted_facts():
    from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState
    from models.memory_evidence import SourceState

    now = datetime(2026, 8, 24, tzinfo=timezone.utc)
    rows = []
    writes = []

    class Snapshot:
        def __init__(self, payload, row_id):
            self.payload = payload
            self.id = row_id
            self.reference = SimpleNamespace(set=lambda value, merge=False: writes.append((row_id, value, merge)))

        def to_dict(self):
            return self.payload

    for index in range(3):
        rows.append(
            Snapshot(
                {
                    "memory_id": f"memory-{index}",
                    "uid": "user-1",
                    "version": 1,
                    "tier": MemoryTier.long_term.value,
                    "status": MemoryItemStatus.active.value,
                    "processing_state": ProcessingState.processed.value,
                    "content": "Alice owns release review" if index == 1 else f"legacy fact {index}",
                    "source_state": SourceState.active.value,
                    "sensitivity_labels": [],
                    "visibility": "private",
                    "user_asserted": True,
                    "captured_at": now,
                    "updated_at": now,
                    "ledger_commit_id": f"commit-{index}",
                    "ledger_sequence": index + 1,
                },
                f"memory-{index}",
            )
        )

    class Query:
        def __init__(self, normalized=False):
            self.normalized = normalized

        def where(self, *, filter):
            return Query(self.normalized or filter.field_path == "normalized_content_key")

        def limit(self, _count):
            return self

        def stream(self):
            return [] if self.normalized else rows

    class Collection:
        def where(self, *, filter):
            return Query(filter.field_path == "normalized_content_key")

    db = SimpleNamespace(collection=lambda _path: Collection())
    occupant = _find_active_slot_or_subject("user-1", _candidate(slot=None), db_client=db)
    assert occupant is not None and occupant.memory_id == "memory-1"
    # Compatibility reads must not lazily write a child row: an unfenced
    # backfill can recreate data after account deletion. Identity is derived
    # in memory for this bounded proof instead.
    assert writes == []


def test_completed_day_agent_slot_reaches_the_candidate(monkeypatch):
    db = _Db()
    control = _open_control(monkeypatch)
    db.document("users/user-1/memory_state/apply_control").set(control.model_dump(mode="json"))
    local_date = date(2026, 8, 23)
    window = completed_local_day_window(local_date, "UTC")
    monkeypatch.setattr(
        "utils.memory.daily_memory_sweep._read_completed_day_conversation_sources",
        lambda *_args, **_kwargs: ((_day_source("conversation-1", "stable summary"),), "complete"),
    )
    model = DailySweepModelAuthority(enabled=True, model_name="test", max_candidates=8, max_cost_usd=1.0)

    def agent(_uid, _rows, _lookup, **_kwargs):
        return _agent_output(
            memories=[
                SimpleNamespace(
                    content="David lives in New York",
                    conversation_ids=["conversation-1"],
                    slot="Current City",
                )
            ]
        )

    result = produce_completed_day_daily_summary_sources(
        "user-1",
        local_date,
        "UTC",
        control,
        db_client=db,
        model_authority=model,
        agent_runner=agent,
        window_override=window,
    )
    assert result.source_status == "complete"
    # The candidate validator normalizes slot names to snake_case.
    assert result.daily_summary[0].slot == "current_city"


def test_completed_day_stale_schema_stage_attests_empty_and_advances(monkeypatch):
    """A stage written by an older deployment must not stall the cursor forever."""

    db = _Db()
    control = _open_control(monkeypatch)
    db.document("users/user-1/memory_state/apply_control").set(control.model_dump(mode="json"))
    local_date = date(2026, 8, 23)
    window = completed_local_day_window(local_date, "UTC")
    ref = _daily_summary_staged_candidates_ref(
        db,
        "user-1",
        local_date,
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        window_id=window.window_id,
    )
    ref.set(
        {
            "schema_version": "daily_memory_sweep_daily_summary_stage.v1",
            "uid": "user-1",
            "local_date": local_date.isoformat(),
            "candidate_page": [{"legacy": "shape"}],
            "candidate_count": 1,
        }
    )
    monkeypatch.setattr(
        "utils.memory.daily_memory_sweep._read_completed_day_conversation_sources",
        lambda *_args, **_kwargs: ((_day_source("conversation-1", "stable summary"),), "complete"),
    )
    model = DailySweepModelAuthority(enabled=True, model_name="test", max_candidates=8, max_cost_usd=1.0)

    def should_not_run(_uid, _rows, _lookup, **_kwargs):
        raise AssertionError("a stale-schema stage must not rerun the agent")

    result = produce_completed_day_daily_summary_sources(
        "user-1",
        local_date,
        "UTC",
        control,
        db_client=db,
        model_authority=model,
        agent_runner=should_not_run,
        window_override=window,
    )
    # The older deployment owned this window's invocation and apply; the day
    # completes empty instead of blocking every later day.
    assert result.source_status == "complete_zero"
    assert result.daily_summary == ()


def test_sweep_slot_refresh_amends_sweep_occupant_but_never_user_statements(monkeypatch):
    """A sweep-authored slot occupant is refreshed by an equal-rank slot
    candidate (profile maintenance); user statements and subject-only matches
    keep the strict rank rule."""

    from models.product_memory import MemoryItemStatus, MemoryKind
    from utils.memory.daily_memory_sweep import LedgerWriteReason, _apply_candidate

    def occupant(reason):
        return SimpleNamespace(
            memory_id="memory-existing",
            status=MemoryItemStatus.active,
            kind=MemoryKind.fact,
            write_reason=reason,
        )

    amended = []
    monkeypatch.setattr("utils.memory.daily_memory_sweep._target_for_candidate", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "utils.memory.daily_memory_sweep.amend_fact",
        lambda uid, memory_id, content, **kwargs: amended.append((memory_id, content)) or "memory-amended",
    )

    # Sweep-authored occupant + slot candidate: refresh via amend.
    monkeypatch.setattr(
        "utils.memory.daily_memory_sweep._find_active_slot_or_subject",
        lambda *_a, **_k: occupant(LedgerWriteReason.daily_reconciliation),
    )
    memory_id, skip = _apply_candidate(
        "user-1", date(2026, 8, 23), _candidate(content="David now lives in Austin"), db_client=_Db()
    )
    assert (memory_id, skip) == ("memory-amended", None)
    assert amended == [("memory-existing", "David now lives in Austin")]

    # A direct user statement is never overwritten by sweep inference.
    monkeypatch.setattr(
        "utils.memory.daily_memory_sweep._find_active_slot_or_subject",
        lambda *_a, **_k: occupant(LedgerWriteReason.direct_user_statement),
    )
    memory_id, skip = _apply_candidate("user-1", date(2026, 8, 23), _candidate(), db_client=_Db())
    assert (memory_id, skip) == ("memory-existing", "existing_active_slot")

    # Subject-only matches (no slot) stay duplicates, not updates.
    monkeypatch.setattr(
        "utils.memory.daily_memory_sweep._find_active_slot_or_subject",
        lambda *_a, **_k: occupant(LedgerWriteReason.daily_reconciliation),
    )
    memory_id, skip = _apply_candidate("user-1", date(2026, 8, 23), _candidate(slot=None), db_client=_Db())
    assert (memory_id, skip) == ("memory-existing", "existing_active_subject")
    assert len(amended) == 1


def test_unstructured_fallback_marker_matches_the_prompt_rule():
    """The producer's raw-transcript marker and the prompt rule that gates
    slots on it must stay the same literal string, or the gate silently
    stops firing."""

    from utils import prompts
    from utils.memory.daily_memory_sweep import UNSTRUCTURED_SUMMARY_MARKER

    assert UNSTRUCTURED_SUMMARY_MARKER in prompts._DAILY_SWEEP_SHARED_RULES
    rule = next(line for line in prompts._DAILY_SWEEP_SHARED_RULES.splitlines() if UNSTRUCTURED_SUMMARY_MARKER in line)
    assert "NEVER set a slot" in rule


def _legacy_row_payload(index: int, content: str):
    from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState
    from models.memory_evidence import SourceState

    now = datetime(2026, 8, 24, tzinfo=timezone.utc)
    return {
        "memory_id": f"memory-{index:05d}",
        "uid": "user-1",
        "version": 1,
        "tier": MemoryTier.long_term.value,
        "status": MemoryItemStatus.active.value,
        "processing_state": ProcessingState.processed.value,
        "content": content,
        "source_state": SourceState.active.value,
        "sensitivity_labels": [],
        "visibility": "private",
        "user_asserted": True,
        "captured_at": now,
        "updated_at": now,
        "ledger_commit_id": f"commit-{index}",
        "ledger_sequence": index + 1,
    }


class _PaginatedLegacyDb:
    """A fake whose legacy query obeys limit + start_after over sorted rows."""

    def __init__(self, rows):
        self._rows = sorted(rows, key=lambda snapshot: snapshot.id)

    def collection(self, _path):
        rows = self._rows

        class Query:
            def __init__(self, normalized=False, after_id=None, count=None):
                self.normalized = normalized
                self.after_id = after_id
                self.count = count

            def where(self, *, filter):
                return Query(
                    self.normalized or filter.field_path == "normalized_content_key", self.after_id, self.count
                )

            def limit(self, count):
                return Query(self.normalized, self.after_id, count)

            def start_after(self, snapshot):
                return Query(self.normalized, snapshot.id, self.count)

            def stream(self):
                if self.normalized:
                    return []
                selected = [row for row in rows if self.after_id is None or row.id > self.after_id]
                return selected[: self.count] if self.count is not None else selected

        class Collection:
            def where(self, *, filter):
                return Query(filter.field_path == "normalized_content_key")

        return Collection()


class _LegacySnapshot:
    def __init__(self, payload, row_id):
        self._payload = payload
        self.id = row_id

    def to_dict(self):
        return self._payload


def test_legacy_compatibility_proof_survives_a_real_accounts_cohort():
    """Regression: dev sweep stuck since 2026-08-30 (canonical_occupant_query_unavailable).

    The compatibility occupant proof capped the whole cohort at one 64-row
    page, so an account with more active unslotted facts than that — the
    owner's dogfood account holds ~196 — could never complete a sweep day:
    every hourly run failed closed with "exceeded proof budget". Completeness
    now comes from draining the cursor; the duplicate is still found even
    when it sits past the old cap.
    """

    rows = [_legacy_row_payload(index, f"legacy fact {index}") for index in range(700)]
    rows[650]["content"] = "Alice owns release review"
    db = _PaginatedLegacyDb([_LegacySnapshot(payload, payload["memory_id"]) for payload in rows])

    occupant = _find_active_slot_or_subject("user-1", _candidate(slot=None), db_client=db)

    assert occupant is not None and occupant.memory_id == "memory-00650"


def test_legacy_compatibility_proof_completes_with_no_duplicate_past_the_old_cap():
    rows = [_legacy_row_payload(index, f"legacy fact {index}") for index in range(100)]
    db = _PaginatedLegacyDb([_LegacySnapshot(payload, payload["memory_id"]) for payload in rows])

    occupant = _find_active_slot_or_subject("user-1", _candidate(slot=None), db_client=db)

    assert occupant is None


def test_legacy_compatibility_proof_still_fails_closed_above_the_scan_ceiling():
    from utils.memory.daily_memory_sweep import MAX_LEGACY_COMPAT_OCCUPANT_SCAN, SweepAuthoritativeQueryUnavailable

    total = MAX_LEGACY_COMPAT_OCCUPANT_SCAN + 1
    rows = [_legacy_row_payload(index, f"legacy fact {index}") for index in range(total)]
    db = _PaginatedLegacyDb([_LegacySnapshot(payload, payload["memory_id"]) for payload in rows])

    with pytest.raises(SweepAuthoritativeQueryUnavailable):
        _find_active_slot_or_subject("user-1", _candidate(slot=None), db_client=db)


def test_scheduler_skips_predrain_accounts_without_error_or_claims(monkeypatch):
    """Regression: enrolled-but-undrained accounts failed the job hourly.

    Every beta account starts in ``compatibility`` writer mode until the
    maintenance drain publishes its ledger cutover, and ordinary ledger writes
    are refused there (``require_writer_admitted``). The scheduler used to
    claim the day anyway: the write died with WriterAdmissionError, the burned
    receipt lease shadowed the retries as ``source_idempotency_conflict``, and
    the hourly job exited 1 — observed continuously in dev on the dogfood
    account (still compatibility at epoch 0). Pre-drain is an expected rollout
    state: skip quietly, advance the fair page, and leave the account's day
    cursor untouched so pending days catch up after the drain.
    """

    from models.memory_apply import MemoryControlState

    control = MemoryControlState(
        uid="user-1",
        head_commit_id="head0",
        account_generation=4,
        source_generation=7,
    )
    assert control.writer_mode is not WriterMode.ledger
    monkeypatch.setattr(
        "utils.memory.daily_memory_sweep.ensure_canonical_apply_control_state",
        lambda _uid, db_client: control,
    )
    db = _Db()
    source_calls = []

    summary = run_daily_memory_sweep_scheduler(
        db_client=db,
        now=datetime(2026, 8, 24, 12, tzinfo=timezone.utc),
        uid_inventory=("user-1",),
        source_provider=lambda *_args, **_kwargs: source_calls.append(True),
        timezone_resolver=lambda _uid: "UTC",
        authority=SweepAuthorityState(enabled=True),
        cohort_authority=DailySweepCohortAuthority(enabled=True, cohort_name="memory-sweep"),
        cohort_authorizer=lambda *_args: True,
    )

    assert summary.errors == ()
    assert summary.completed_uids == ("user-1",)
    assert summary.failed_uids == ()
    assert summary.blocked_users == 1
    assert source_calls == []
    # No receipt claim, cursor write, or any other document was touched.
    assert db.store == {}


def test_scheduler_proceeds_for_ledger_mode_accounts(monkeypatch):
    from models.memory_apply import MemoryControlState

    control = MemoryControlState(
        uid="user-1",
        head_commit_id="head0",
        account_generation=4,
        source_generation=7,
        writer_mode=WriterMode.ledger,
        writer_epoch=1,
    )
    monkeypatch.setattr(
        "utils.memory.daily_memory_sweep.ensure_canonical_apply_control_state",
        lambda _uid, db_client: control,
    )
    db = _Db()
    source_calls = []

    run_daily_memory_sweep_scheduler(
        db_client=db,
        now=datetime(2026, 8, 24, 12, tzinfo=timezone.utc),
        uid_inventory=("user-1",),
        source_provider=lambda *_args, **_kwargs: source_calls.append(True) or None,
        timezone_resolver=lambda _uid: "UTC",
        authority=SweepAuthorityState(enabled=True),
        cohort_authority=DailySweepCohortAuthority(enabled=True, cohort_name="memory-sweep"),
        cohort_authorizer=lambda *_args: True,
    )

    # The gate is passed: the scheduler advanced beyond writer-mode admission
    # into ordinary day planning for this account (which asks the source
    # provider for the pending day's packet).
    assert source_calls != []


# --- S5 (§1.8): a basic account is not admitted to the sweep -----------------


def _ledger_control(monkeypatch):
    """An account that has completed ledger cutover, so the writer-mode skip
    above the plan gate does not fire and the plan gate is what is under test."""
    control = MemoryControlState(
        uid="user-1",
        head_commit_id="head0",
        account_generation=4,
        source_generation=7,
        writer_mode=WriterMode.ledger,
    )
    monkeypatch.setattr(
        "utils.memory.daily_memory_sweep.read_account_deletion_projection_fence",
        lambda _uid, db_client: type("Fence", (), {"blocks_projection_writes": False})(),
    )
    monkeypatch.setattr(
        "utils.memory.daily_memory_sweep.ensure_canonical_apply_control_state",
        lambda _uid, db_client: control,
    )
    monkeypatch.setattr(
        "utils.memory.daily_memory_sweep.firestore.transactional",
        lambda function: lambda transaction, *args: function(transaction, *args),
    )
    return control


def _plan_decision(*, allowed: bool, reason: str):
    from config.plan_catalog import PlanType
    from utils.managed_compute import Decision

    return Decision(
        allowed=allowed,
        reason=reason,
        feature="memories",
        funding_owner="omi",
        plan=PlanType.basic if not allowed else PlanType.unlimited,
        plan_resolved=True,
    )


def _run_sweep_for_plan(monkeypatch, *, suppression_on: bool, allowed: bool, reason: str):
    db = _Db()
    _ledger_control(monkeypatch)
    source_calls = []
    monkeypatch.setattr(
        "utils.memory.daily_memory_sweep.free_tier_memory_suppression_enabled",
        lambda: suppression_on,
    )
    monkeypatch.setattr(
        "utils.memory.daily_memory_sweep.authorize_managed_compute",
        lambda *_args, **_kwargs: _plan_decision(allowed=allowed, reason=reason),
    )
    summary = run_daily_memory_sweep_scheduler(
        db_client=db,
        now=datetime(2026, 8, 24, 12, tzinfo=timezone.utc),
        uid_inventory=("user-1",),
        source_provider=lambda *_args, **_kwargs: source_calls.append(True),
        timezone_resolver=lambda _uid: "UTC",
        timezone_reconciler=lambda *_args: True,
        authority=SweepAuthorityState(enabled=True),
        cohort_authority=DailySweepCohortAuthority(enabled=True, cohort_name="memory-sweep"),
        cohort_authorizer=lambda *_args: DailySweepCohortDecision.enabled,
    )
    return summary, source_calls, db


# red-proof: delete the `if free_tier_memory_suppression_enabled():` block in the scheduler
def test_basic_account_is_not_admitted_by_the_sweep_producer(monkeypatch):
    """Named proof (b). Acked, not rejected: a definite plan answer is a
    successful bounded decision, so the fair page cursor may advance. A reject
    would burn receipt leases and strand the tail behind an account that is
    never going to be swept."""
    summary, source_calls, db = _run_sweep_for_plan(
        monkeypatch, suppression_on=True, allowed=False, reason="basic_not_entitled"
    )
    assert source_calls == [], "a basic account must not reach the candidate producer"
    assert summary.completed_uids == ("user-1",)
    assert summary.failed_uids == ()
    assert summary.blocked_users == 1
    assert db.store == {}, "a suppressed account must not write cursor or receipt state"


def test_paid_account_is_still_swept_with_the_flag_on(monkeypatch):
    _summary, source_calls, _db = _run_sweep_for_plan(
        monkeypatch, suppression_on=True, allowed=True, reason="plan_paid"
    )
    assert source_calls != [], "a paid account must still reach the candidate producer"


def test_flag_off_admits_a_basic_account_exactly_as_today(monkeypatch):
    """Dark rollout: with the flag off the plan is not consulted at all."""
    _summary, source_calls, _db = _run_sweep_for_plan(
        monkeypatch, suppression_on=False, allowed=False, reason="basic_not_entitled"
    )
    assert source_calls != []
