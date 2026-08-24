from datetime import date, datetime, timezone

import pytest

from models.memory_apply import MemoryControlState
from utils.memory.daily_memory_sweep import (
    DailySweepCandidate,
    DailySweepInput,
    MAX_CATCH_UP_DAYS,
    SweepAuthority,
    SweepAuthorityState,
    completed_local_day_window,
    plan_daily_memory_sweep,
    run_daily_memory_sweep,
)
from utils.memory.daily_memory_sweep import (
    DailySweepRuntimeSources,
    _completed_day_row_eligibility,
    reconcile_daily_memory_sweep_timezone,
    _finish_onboarding_sources,
    _receipt_id,
)


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


def test_timezone_reconcile_rolls_source_generation_with_cursor_namespace(monkeypatch):
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
    assert updated_control["source_generation"] == control.source_generation + 1
    assert updated_cursor["source_generation"] == control.source_generation + 1
    assert updated_cursor["timezone_name"] == "UTC"
    assert updated_cursor["last_completed_local_date"] is None


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
