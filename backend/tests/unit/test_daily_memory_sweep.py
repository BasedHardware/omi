from datetime import date, datetime, timedelta, timezone
import sys
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from models.memory_apply import MemoryControlState
from utils.memory.daily_memory_sweep import (
    DailySweepCandidate,
    DailySweepCohortAuthority,
    DailySweepCohortDecision,
    DailySweepCursor,
    DailySweepInput,
    MAX_CATCH_UP_DAYS,
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
    _onboarding_transcript_eligibility,
    _pending_completed_dates,
    close_daily_memory_sweep_cohort_clients,
    daily_memory_sweep_cohort_authority_from_environment,
    _POSTHOG_CLIENTS,
    read_daily_memory_sweep_cohort_assignment,
    run_daily_memory_sweep_scheduler,
)
from models.product_memory import normalized_memory_content_key


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
