"""Memory ledger unit tests.

``database.memory_ledger`` binds ``db`` from ``database._client`` and imports
``transactional`` from ``google.cloud.firestore_v1`` at import time, so a fake
``database._client`` + firestore chain must be active before the module is exec'd.
This is the sanctioned Tier-2 "fake must precede import" case (see
``backend/docs/test_isolation.md`` and ``testing/import_isolation.load_module_fresh``).
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from google.api_core.exceptions import Aborted
import pytest

from database import document_store, firestore_transaction_retry
from tests.store_fakes import FakeDocumentStore
from tests.unit.fake_firestore import FakeFirestore
from utils.memory.v3.account_generation_source import read_memory_v3_trusted_account_generation


@pytest.fixture(scope="module", autouse=True)
def _load_modules():
    """Bind the (now import-clean, WP2 port-backed) ledger + projection_repair as module globals.

    Both defer their store to a lazy ``get_document_store()``; tests inject a FakeDocumentStore via
    the ``store`` fixture below (the sanctioned ``_store`` seam), so no import-time fakery is needed.
    """
    import database.memory_ledger as memory_ledger
    import database.projection_repair as projection_repair

    globals()["memory_ledger"] = memory_ledger
    globals()["projection_repair"] = projection_repair
    yield


@pytest.fixture(autouse=True)
def _isolate_retry_logging_cost(monkeypatch):
    monkeypatch.setattr(firestore_transaction_retry, "logger", MagicMock())


class _StrictTx:
    """A neutral transaction that raises if a read lands after a write.

    Reproduces Firestore's read-before-write ordering contract (#9780) on the port seam, so the
    ledger's apply_control fallback read is still guarded even though the base fake is lenient.
    """

    def __init__(self, store):
        self._store = store
        self._wrote = False

    def get(self, path):
        if self._wrote:
            raise AssertionError(f"read after write in transaction: {path}")
        return self._store.get(path)

    def set(self, path, data, *, merge=False):
        self._wrote = True
        self._store.set(path, data, merge=merge)

    def update(self, path, data):
        self._wrote = True
        self._store.update(path, data)

    def delete(self, path):
        self._wrote = True
        self._store.delete(path)


class _StrictStore(FakeDocumentStore):
    def run_transaction(self, fn, *, attempts=3):
        return fn(_StrictTx(self))


@pytest.fixture
def store(monkeypatch):
    fake = FakeDocumentStore()
    monkeypatch.setattr(memory_ledger, "_store", lambda: fake)
    monkeypatch.setattr(projection_repair, "_store", lambda: fake)
    monkeypatch.setattr(document_store, "_store", lambda: fake)
    return fake


def _fact(fact_id, content, *, valid_from=None, valid_to=None):
    qualifiers = {}
    if valid_from:
        qualifiers["valid_from"] = valid_from
    if valid_to:
        qualifiers["valid_to"] = valid_to
    return {
        "id": fact_id,
        "content": content,
        "predicate": "resides_in",
        "arguments": {"location": content.removeprefix("Lives in ")},
        "subject_entity_id": "user",
        "qualifiers": qualifiers,
    }


def _seed_clobbered_state(store, uid):
    """State head lacks trusted canonical fields, so the write must fall back to reading
    memory_state/apply_control — the read that regressed to land after writes (issue #9780)."""
    store.set(f"users/{uid}/memory_state/head", {"current_head_commit_id": "legacy-head", "projection_version": 1})
    store.set(
        f"users/{uid}/memory_state/apply_control",
        {"uid": uid, "account_generation": 7, "head_commit_id": "canonical-head", "commit_sequence": 11},
    )


def test_fold_commits_replays_head_and_valid_time():
    january = datetime(2026, 1, 15, tzinfo=timezone.utc)
    february = datetime(2026, 2, 1, tzinfo=timezone.utc)
    learned = datetime(2026, 6, 1, tzinfo=timezone.utc)
    fact = _fact("m1", "Lives in NYC", valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc), valid_to=january)
    commit = memory_ledger.build_commit(None, [memory_ledger.add_fact(fact)], commit_time=learned)

    assert "m1" in memory_ledger.fold_commits([commit], valid_time=january)
    assert "m1" not in memory_ledger.fold_commits([commit], valid_time=february)


def test_add_fact_normalizes_legacy_valid_at_for_replay():
    valid_from = datetime(2026, 6, 1, tzinfo=timezone.utc)
    before_valid = datetime(2026, 5, 31, tzinfo=timezone.utc)
    fact = _fact("m1", "Lives in NYC")
    fact["valid_at"] = valid_from
    commit = memory_ledger.build_commit(None, [memory_ledger.add_fact(fact)], commit_time=valid_from)

    assert "m1" not in memory_ledger.fold_commits([commit], valid_time=before_valid)
    assert "m1" in memory_ledger.fold_commits([commit], valid_time=valid_from)
    assert commit["mutations"][0]["fact"]["qualifiers"]["valid_from"] == valid_from


def test_supersede_commit_flips_materialized_head_like_invalidate():
    first = memory_ledger.build_commit(
        None,
        [memory_ledger.add_fact(_fact("m1", "Lives in NYC"))],
        commit_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    second = memory_ledger.build_commit(
        first["commit_id"],
        [memory_ledger.supersede_fact("m1", by="m2", kind="contradict")],
        commit_time=datetime(2026, 6, 2, tzinfo=timezone.utc),
    )

    head = memory_ledger.fold_commits([first, second])

    assert "m1" not in head


def test_valid_time_query_can_return_superseded_fact_for_past_window():
    june_1 = datetime(2026, 6, 1, tzinfo=timezone.utc)
    june_2 = datetime(2026, 6, 2, tzinfo=timezone.utc)
    old_fact = _fact("m1", "Lives in NYC", valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc))
    first = memory_ledger.build_commit(None, [memory_ledger.add_fact(old_fact)], commit_time=june_1)
    second = memory_ledger.build_commit(
        first["commit_id"],
        [memory_ledger.supersede_fact("m1", by="m2", kind="contradict", valid_interval={"valid_to": june_2})],
        commit_time=june_2,
    )

    past_truth = memory_ledger.fold_commits([first, second], valid_time=datetime(2026, 5, 1, tzinfo=timezone.utc))
    current_head = memory_ledger.fold_commits([first, second])

    assert "m1" in past_truth
    assert "m1" not in current_head


def test_retract_payload_tombstones_historical_checkout():
    june_1 = datetime(2026, 6, 1, tzinfo=timezone.utc)
    june_2 = datetime(2026, 6, 2, tzinfo=timezone.utc)
    first = memory_ledger.build_commit(None, [memory_ledger.add_fact(_fact("m1", "Lives in NYC"))], commit_time=june_1)
    second = memory_ledger.build_commit(
        first["commit_id"],
        [memory_ledger.retract_fact("m1", reason="source_tombstoned")],
        commit_time=june_2,
    )

    facts = {}
    for commit in [first, second]:
        for mutation in commit["mutations"]:
            memory_ledger._apply_mutation(facts, mutation, commit["commit_time"])

    assert facts["m1"]["content"] is None
    assert facts["m1"]["arguments"] == {}
    assert facts["m1"]["redaction_status"] == "payload_tombstoned"


def test_tombstone_evidence_marks_evidence_without_removing_it():
    june_1 = datetime(2026, 6, 1, tzinfo=timezone.utc)
    june_2 = datetime(2026, 6, 2, tzinfo=timezone.utc)
    fact = _fact("m1", "Lives in NYC")
    fact["evidence"] = [{"evidence_id": "ev1", "source_id": "conv1"}]
    first = memory_ledger.build_commit(None, [memory_ledger.add_fact(fact)], commit_time=june_1)
    second = memory_ledger.build_commit(
        first["commit_id"],
        [memory_ledger.tombstone_evidence("m1", "ev1", june_2)],
        commit_time=june_2,
    )

    head = memory_ledger.fold_commits([first, second])

    assert head["m1"]["evidence"][0]["evidence_id"] == "ev1"
    assert head["m1"]["evidence"][0]["redaction_status"] == "tombstoned"


def test_tombstone_evidence_recomputes_replayed_veracity_from_active_evidence():
    june_1 = datetime(2026, 6, 1, tzinfo=timezone.utc)
    june_2 = datetime(2026, 6, 2, tzinfo=timezone.utc)
    fact = _fact("m1", "Lives in NYC")
    fact["capture_confidence"] = 0.8
    fact["veracity"] = 0.67
    fact["evidence"] = [
        {
            "evidence_id": "ev-conv",
            "source_id": "conv1",
            "independence_group": "conv1",
            "capture_confidence": 0.65,
        },
        {
            "evidence_id": "ev-calendar",
            "source_id": "calendar1",
            "independence_group": "calendar1",
            "capture_confidence": 0.8,
        },
    ]
    first = memory_ledger.build_commit(None, [memory_ledger.add_fact(fact)], commit_time=june_1)
    second = memory_ledger.build_commit(
        first["commit_id"],
        [memory_ledger.tombstone_evidence("m1", "ev-conv", june_2)],
        commit_time=june_2,
    )

    head = memory_ledger.fold_commits([first, second])

    assert head["m1"]["evidence"][0]["redaction_status"] == "tombstoned"
    assert head["m1"]["veracity"] == 0.45
    assert head["m1"]["uncertainty_reasons"] == ["single_source"]


def test_diff_returns_typed_mutations_between_parent_child():
    first = memory_ledger.build_commit(
        None,
        [memory_ledger.add_fact(_fact("m1", "Lives in NYC"))],
        commit_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    mutation = memory_ledger.supersede_fact("m1", by="m2", kind="contradict")
    second = memory_ledger.build_commit(
        first["commit_id"],
        [mutation],
        commit_time=datetime(2026, 6, 2, tzinfo=timezone.utc),
    )

    assert memory_ledger.diff(first, second) == [mutation]


def test_append_commit_to_history_is_idempotent_for_same_commit():
    state = {"current_head_commit_id": None}
    commits = {}
    mutations = [memory_ledger.add_fact(_fact("m1", "Lives in NYC"))]

    first = memory_ledger.append_commit_to_history(state, commits, None, mutations)
    second = memory_ledger.append_commit_to_history(state, commits, first["commit"]["parent_commit_id"], mutations)

    assert first["applied"] is True
    assert second["applied"] is False
    assert len(commits) == 1


def test_append_commit_to_history_rejects_sibling_heads():
    state = {"current_head_commit_id": None}
    commits = {}
    parent = None

    first = memory_ledger.append_commit_to_history(
        state,
        commits,
        parent,
        [memory_ledger.add_fact(_fact("m1", "Lives in NYC"))],
    )

    try:
        memory_ledger.append_commit_to_history(
            state,
            commits,
            parent,
            [memory_ledger.add_fact(_fact("m2", "Lives in SF"))],
        )
    except memory_ledger.HeadConflict as exc:
        assert exc.expected_parent == parent
        assert exc.current_head == first["commit"]["commit_id"]
    else:
        raise AssertionError("Expected same-parent sibling append to fail")


def test_ledger_append_repairs_clobbered_trusted_state_head_from_canonical_apply_control(store):
    uid = "u1"
    _seed_clobbered_state(store, uid)

    result = store.run_transaction(
        lambda tx: memory_ledger._append_commit_transaction(
            tx,
            uid,
            "legacy-head",
            [memory_ledger.add_fact(_fact("m1", "Lives in NYC"))],
            None,
            datetime(2026, 7, 14, tzinfo=timezone.utc),
            None,
            False,
        )
    )

    state_head = store.get(f"users/{uid}/memory_state/head").to_dict()
    assert state_head["current_head_commit_id"] == result["commit"]["commit_id"]
    assert state_head["head_commit_id"] == "canonical-head"
    assert state_head["commit_sequence"] == 11

    trusted = read_memory_v3_trusted_account_generation(
        uid=uid,
    )
    assert trusted.read_error_reason is None
    assert trusted.account_generation == 7


def test_ledger_append_reads_apply_control_before_any_write(monkeypatch):
    """Regression for #9780: the apply_control fallback read must precede writes.

    The strict store's transaction raises if a get() lands after a set(), reproducing Firestore's
    ordering contract on the neutral port seam (the base fake is lenient). The dual-backend contract
    additionally exercises the ordering against the real Firestore adapter.
    """
    uid = "u1"
    store = _StrictStore()
    monkeypatch.setattr(memory_ledger, "_store", lambda: store)
    monkeypatch.setattr(projection_repair, "_store", lambda: store)
    _seed_clobbered_state(store, uid)

    result = store.run_transaction(
        lambda tx: memory_ledger._append_commit_transaction(
            tx,
            uid,
            "legacy-head",
            [memory_ledger.add_fact(_fact("m1", "Lives in NYC"))],
            None,
            datetime(2026, 7, 14, tzinfo=timezone.utc),
            lambda _tx: None,
            False,
        )
    )

    state_head = store.get(f"users/{uid}/memory_state/head").to_dict()
    assert state_head["current_head_commit_id"] == result["commit"]["commit_id"]
    assert state_head["head_commit_id"] == "canonical-head"
    assert state_head["commit_sequence"] == 11


def test_ledger_builder_append_reads_apply_control_before_any_write(monkeypatch):
    """Regression for #9780 on the builder append path (strict read-before-write store)."""
    uid = "u1"
    store = _StrictStore()
    monkeypatch.setattr(memory_ledger, "_store", lambda: store)
    monkeypatch.setattr(projection_repair, "_store", lambda: store)
    _seed_clobbered_state(store, uid)

    result = store.run_transaction(
        lambda tx: memory_ledger._append_commit_with_builder_transaction(
            tx,
            uid,
            "legacy-head",
            lambda _tx: {"mutations": [memory_ledger.add_fact(_fact("m1", "Lives in NYC"))]},
            None,
            datetime(2026, 7, 14, tzinfo=timezone.utc),
            False,
        )
    )

    state_head = store.get(f"users/{uid}/memory_state/head").to_dict()
    assert state_head["current_head_commit_id"] == result["commit"]["commit_id"]
    assert state_head["head_commit_id"] == "canonical-head"
    assert state_head["commit_sequence"] == 11


def test_ledger_builder_append_preserves_existing_trusted_state_head_without_control_fallback(store):
    uid = "u1"
    store.set(
        f"users/{uid}/memory_state/head",
        {
            "current_head_commit_id": "legacy-head",
            "projection_version": 1,
            "schema_version": 1,
            "uid": uid,
            "source": "memory_state_head",
            "account_generation": 7,
            "head_commit_id": "canonical-head",
            "commit_sequence": 11,
        },
    )

    result = store.run_transaction(
        lambda tx: memory_ledger._append_commit_with_builder_transaction(
            tx,
            uid,
            "legacy-head",
            lambda _tx: {"mutations": [memory_ledger.add_fact(_fact("m1", "Lives in NYC"))]},
            None,
            datetime(2026, 7, 14, tzinfo=timezone.utc),
            False,
        )
    )

    state_head = store.get(f"users/{uid}/memory_state/head").to_dict()
    assert state_head["current_head_commit_id"] == result["commit"]["commit_id"]
    assert state_head["head_commit_id"] == "canonical-head"
    assert state_head["commit_sequence"] == 11


def test_contention_retry_uses_fresh_transactions_and_equal_jitter():
    transactions = []
    sleeps = []
    calls = []

    def transaction_factory():
        transaction = object()
        transactions.append(transaction)
        return transaction

    def operation(transaction):
        calls.append(transaction)
        if len(calls) < 3:
            raise Aborted("read contention")
        return "committed"

    result = firestore_transaction_retry.run_with_transaction_contention_retry(
        transaction_factory,
        operation,
        operation_name="test_operation",
        sleep=sleeps.append,
        random_value=lambda: 0.0,
    )

    assert result == "committed"
    assert calls == transactions
    assert len({id(transaction) for transaction in transactions}) == 3
    assert sleeps == [0.1, 0.2]


def test_contention_retry_accepts_sdk_exhaustion_wrapper_with_explicit_aborted_cause():
    calls = 0

    def operation(_transaction):
        nonlocal calls
        calls += 1
        if calls == 1:
            try:
                raise Aborted("commit contention")
            except Aborted as error:
                raise ValueError("transaction failed after SDK attempts") from error
        return "committed"

    result = firestore_transaction_retry.run_with_transaction_contention_retry(
        object,
        operation,
        operation_name="test_operation",
        sleep=lambda _delay: None,
    )

    assert result == "committed"
    assert calls == 2


def test_contention_retry_does_not_replay_non_contention_error():
    calls = 0

    def operation(_transaction):
        nonlocal calls
        calls += 1
        raise RuntimeError("not retryable")

    with pytest.raises(RuntimeError, match="not retryable"):
        firestore_transaction_retry.run_with_transaction_contention_retry(
            object,
            operation,
            operation_name="test_operation",
            sleep=lambda _delay: None,
        )

    assert calls == 1


def test_aborted_implicit_context_does_not_make_replacement_error_retryable():
    calls = 0

    def operation(_transaction):
        nonlocal calls
        calls += 1
        try:
            raise Aborted("handled contention")
        except Aborted:
            raise RuntimeError("replacement failure")

    with pytest.raises(RuntimeError, match="replacement failure"):
        firestore_transaction_retry.run_with_transaction_contention_retry(
            object,
            operation,
            operation_name="test_operation",
            sleep=lambda _delay: None,
        )

    assert calls == 1


def test_contention_retry_exhaustion_is_bounded_and_preserves_cause():
    sleeps = []

    def operation(_transaction):
        raise Aborted("persistent contention")

    with pytest.raises(firestore_transaction_retry.FirestoreContentionExhausted) as raised:
        firestore_transaction_retry.run_with_transaction_contention_retry(
            object,
            operation,
            operation_name="test_operation",
            max_attempts=3,
            sleep=sleeps.append,
            random_value=lambda: 1.0,
        )

    assert isinstance(raised.value.__cause__, Aborted)
    assert sleeps == [0.2, 0.4]


def test_contention_retry_rejects_invalid_attempt_count_before_transaction():
    opened = False

    def transaction_factory():
        nonlocal opened
        opened = True
        return object()

    with pytest.raises(ValueError, match="max_attempts must be positive"):
        firestore_transaction_retry.run_with_transaction_contention_retry(
            transaction_factory,
            lambda _transaction: None,
            operation_name="test_operation",
            max_attempts=0,
        )

    assert opened is False


def test_projection_repair_extracts_affected_fact_ids_and_metadata():
    mutations = [
        memory_ledger.add_fact({"id": "m1", "subject_entity_id": "user", "object_entity_ids": ["project"]}),
        memory_ledger.supersede_fact("m2", by="m1"),
    ]

    assert projection_repair.affected_fact_ids(mutations) == ["m1", "m2"]
    assert projection_repair.projection_metadata_for_fact(
        {
            "id": "m1",
            "subject_entity_id": "user",
            "object_entity_ids": ["project"],
            "qualifiers": {"scope": "work", "valid_from": "2026-06-01"},
            "status": "pending_review",
            "redaction_status": "active",
        },
        source_commit_id="commit1",
    ) == {
        "fact_id": "m1",
        "memory_id": "m1",
        "source_commit_id": "commit1",
        "projection_version": projection_repair.PROJECTION_VERSION,
        "entity_ids": ["user", "project"],
        "valid_time": "2026-06-01",
        "scope": "work",
        "epistemic_status": "pending_review",
        "source_tombstone_state": "active",
    }


def test_reconcile_projection_detects_and_repairs_drift_to_zero():
    facts = [
        {"id": "active", "content": "Active"},
        {"id": "retracted", "content": None, "invalid_at": datetime(2026, 6, 1, tzinfo=timezone.utc)},
    ]

    drift = projection_repair.reconcile_memory_projection("uid-1", facts, ["retracted"])
    repaired = projection_repair.reconcile_memory_projection("uid-1", facts, ["active"])

    assert drift["missing_upserts"] == ["active"]
    assert drift["stale_deletes"] == ["retracted"]
    assert drift["projection_fail_count"] == 2
    assert repaired["drift_count"] == 0
    assert repaired["projection_fail_count"] == 0


def test_append_commit_enqueues_projection_repairs(monkeypatch, store):
    queued = []
    commit = memory_ledger.build_commit(None, [memory_ledger.add_fact({"id": "m1"})])

    monkeypatch.setattr(
        memory_ledger,
        "_append_commit_transaction",
        lambda *args, **kwargs: {"commit": commit, "applied": True},
    )
    monkeypatch.setattr(
        memory_ledger.projection_repair,
        "enqueue_projection_repairs",
        lambda uid, item, **_kwargs: queued.append((uid, item)) or ["repair"],
    )

    result = memory_ledger.append_commit("uid-1", None, commit["mutations"])

    assert result["applied"] is True
    assert queued == [("uid-1", commit)]


# NOTE: the ledger no longer owns outer contention retry — that moved into the port's
# run_transaction (ADR-0021), covered by the adapters' dual-backend contract. The
# run_with_transaction_contention_retry helper is still unit-tested directly below.


def test_process_projection_repairs_applies_queued_vector_repairs(store):
    store.set(
        "users/uid-1/projection_repairs/repair1",
        {"repair_id": "repair1", "fact_id": "m1", "status": "queued"},
    )

    result = projection_repair.process_projection_repairs(
        "uid-1",
        fact_loader=lambda fact_id: {"id": fact_id, "invalid_at": datetime(2026, 6, 1, tzinfo=timezone.utc)},
        repair_func=lambda uid, fact: "delete" if fact and fact.get("invalid_at") else "upsert",
    )

    assert result == {"repaired": ["repair1"], "failed": [], "processed": 1}
    stored = store.get("users/uid-1/projection_repairs/repair1").to_dict()
    assert stored["status"] == "repaired"
    assert stored["repair_action"] == "delete"


def test_process_projection_repairs_dead_letters_after_max_attempts(store):
    store.set(
        "users/uid-1/projection_repairs/repair1",
        {"repair_id": "repair1", "fact_id": "m1", "status": "failed", "attempt_count": 1},
    )

    def _failing_repair(uid, fact):
        raise RuntimeError("repair failed")

    result = projection_repair.process_projection_repairs(
        "uid-1",
        fact_loader=lambda fact_id: {"id": fact_id},
        repair_func=_failing_repair,
        max_attempts=2,
    )

    assert result == {"repaired": [], "failed": ["repair1"], "processed": 1}
    stored = store.get("users/uid-1/projection_repairs/repair1").to_dict()
    assert stored["status"] == "dead_letter"
    assert stored["attempt_count"] == 2
