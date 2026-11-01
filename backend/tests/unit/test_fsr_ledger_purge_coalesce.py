"""Count real privacy-history walks and fence coalesced orchestrator failures."""

import importlib
from collections import Counter
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

UID = "uid-fsr-purge"
CONVERSATION = "conversation-fsr-purge"
HISTORY_COLLECTIONS = (
    "memory_operations",
    "memory_commits",
    "memory_outbox",
    "memory_ledger_reopens",
    "jit_trigger_feedback",
    "jit_proactivity_events",
    "jit_proactivity_daily_budgets",
)


@pytest.fixture
def harness(monkeypatch):
    # Use the existing fixture's import isolation at setup time, never at
    # collection time; all production orchestrators/ledger functions stay real.
    from tests.unit.test_memory_service_parity import _load_memory_service, _purge_stub_memory_modules

    monkeypatch.delenv("FIRESTORE_READ_LEVERS", raising=False)
    monkeypatch.setenv("MEMORY_ENABLED", "on")
    service_mod = _load_memory_service(monkeypatch)
    adapter = importlib.import_module("utils.memory.canonical_memory_adapter")
    ledger = importlib.import_module("database.memory_ledger")
    holds = importlib.import_module("database.legal_holds")
    keyword = importlib.import_module("utils.memory.atom_keyword_index")
    from models.memory_apply import MemoryControlState
    from tests.unit.fixtures.canonical_memory_fakes import (
        _FakeDb,
        _CollectionRef,
        _sample_memory_payload,
        _trusted_account_generation,
    )

    # Extend the established fake for the real review-queue query shape.
    original_matches = _CollectionRef._matches

    def matches(data, field, operator, expected):
        if operator == "array_contains_any":
            return bool(set(_CollectionRef._nested_value(data, field) or []).intersection(expected))
        return original_matches(data, field, operator, expected)

    monkeypatch.setattr(_CollectionRef, "_matches", staticmethod(matches))
    monkeypatch.setattr(adapter, "read_memory_v3_trusted_account_generation", lambda **_: _trusted_account_generation())
    events = []
    monkeypatch.setattr(
        adapter, "delete_canonical_memory_vector", lambda uid, mid: events.append(("vector", mid)) or True
    )
    monkeypatch.setattr(
        keyword, "delete_atom_keyword_doc", lambda uid, mid, **kw: events.append(("keyword", mid)) or True
    )
    monkeypatch.setattr(
        adapter.kg_db, "delete_memory_graph_assertion", lambda uid, mid, **kw: events.append(("graph", mid))
    )
    monkeypatch.setattr(
        adapter, "invalidate_kg_for_memory_retraction", lambda *a, **kw: events.append(("invalidate", a[1]))
    )
    monkeypatch.setattr(
        service_mod.HistoricalMemoryAdapter, "cleanup", lambda uid, mid, **kw: events.append(("historical", mid))
    )

    def make_db(count=3):
        db = _FakeDb(
            {
                f"users/{UID}/memory_state/apply_control": MemoryControlState(
                    uid=UID, head_commit_id="head0", account_generation=1, source_generation=1
                ).model_dump(mode="json")
            }
        )
        ids = []
        for index in range(count):
            payload = _sample_memory_payload(uid=UID, conversation_id=CONVERSATION, content=f"Private fact {index}")
            payload["evidence"][0]["evidence_id"] = f"evidence-{index}"
            adapter.write_canonical_extraction_memory(UID, payload, db_client=db)
            ids.append(payload["id"])
            db.docs[f"users/{UID}/memory_review_queue/review-{index}"] = {
                "fact_id": payload["id"],
                "referenced_memory_ids": [payload["id"]],
                "candidate": {"id": payload["id"], "content": payload["content"]},
            }
            db.docs[f"users/{UID}/memory_corrections/correction-{index}"] = {
                "legacy_mutations": [{"memory_id": payload["id"], "content": payload["content"]}]
            }
        # Unrelated history survives every walk, making the repeated read cost
        # observable even though the first purge deletes the target's history.
        for collection in HISTORY_COLLECTIONS:
            for index in range(3):
                db.docs[f"users/{UID}/{collection}/unrelated-{index}"] = {"memory_id": f"peer-{index}"}
        return db, ids

    def service_for(db, *, historical_ids=()):
        service = service_mod.MemoryService(db_client=db)
        service.history.all_live = MagicMock(
            return_value=[
                SimpleNamespace(memory=SimpleNamespace(id=mid, conversation_id=CONVERSATION, evidence=[]))
                for mid in historical_ids
            ]
        )
        return service

    try:
        yield SimpleNamespace(
            adapter=adapter,
            ledger=ledger,
            holds=holds,
            keyword=keyword,
            service_mod=service_mod,
            make_db=make_db,
            service_for=service_for,
            events=events,
        )
    finally:
        _purge_stub_memory_modules()


def _enable(monkeypatch, enabled=True):
    monkeypatch.setenv("FIRESTORE_READ_LEVERS", '{"ledger_purge_coalesce":100}' if enabled else '{}')


def _count_walks(monkeypatch, harness):
    walks = Counter()
    reads = Counter()
    original = harness.ledger._iter_collection_documents

    def counted(collection):
        name = collection.path.rsplit("/", 1)[-1]
        walks[name] += 1
        for doc in original(collection):
            reads[name] += 1
            yield doc

    monkeypatch.setattr(harness.ledger, "_iter_collection_documents", counted)
    return walks, reads


@pytest.mark.parametrize("orchestrator,off_groups", [("canonical", 2), ("service", 4)])
@pytest.mark.parametrize("claim_gate", [False, True])
def test_real_deletion_reduces_fresh_history_walks(harness, monkeypatch, orchestrator, off_groups, claim_gate):
    walks, reads = _count_walks(monkeypatch, harness)
    measurements = []
    for enabled in (False, True):
        _enable(monkeypatch, enabled)
        db, ids = harness.make_db()
        walks.clear()
        reads.clear()
        if orchestrator == "canonical":
            result = harness.adapter.retract_conversation_sourced_memories(
                UID, CONVERSATION, db_client=db, claim_destructive_gate=claim_gate
            )
        else:
            result = harness.service_for(db).retract_conversation_memories(
                UID, CONVERSATION, claim_destructive_gate=claim_gate
            )
        assert set(result["retracted_memory_ids"]) == set(ids)
        assert all(f"users/{UID}/memory_items/{mid}" not in db.docs for mid in ids)
        assert not any("/memory_review_queue/" in path or "/memory_corrections/" in path for path in db.docs)
        for collection in HISTORY_COLLECTIONS:
            assert walks[collection] == (1 if enabled else off_groups)
            assert all(f"users/{UID}/{collection}/unrelated-{index}" in db.docs for index in range(3))
        measurements.append((sum(walks.values()), sum(reads.values())))
    receipt_walks = int(orchestrator == "service")
    assert [item[0] for item in measurements] == [7 * off_groups + receipt_walks, 7 + receipt_walks]
    assert measurements[0][1] - measurements[1][1] >= 7 * 3 * (off_groups - 1)


@pytest.mark.parametrize("orchestrator", ["canonical", "service"])
@pytest.mark.parametrize("claim_gate", [False, True])
def test_off_path_keeps_original_purge_order_and_arguments(harness, monkeypatch, orchestrator, claim_gate):
    monkeypatch.delenv("FIRESTORE_READ_LEVERS", raising=False)
    db, ids = harness.make_db()
    calls = []
    for module, name, label in (
        (harness.adapter, "purge_stale_review_conflicts_for_memories", "canonical-review"),
        (harness.ledger, "finalize_canonical_privacy_tombstones", "finalize"),
        (harness.service_mod, "purge_stale_review_conflicts_for_memories", "service-review"),
        (harness.service_mod, "purge_source_replacement_receipts_for_memories", "receipts"),
    ):
        original = getattr(module, name)

        def record(uid, target_ids, _fn=original, _label=label, **kwargs):
            calls.append((_label, uid, list(target_ids), kwargs.copy()))
            return _fn(uid, target_ids, **kwargs)

        monkeypatch.setattr(module, name, record)
    if orchestrator == "canonical":
        harness.adapter.retract_conversation_sourced_memories(
            UID, CONVERSATION, db_client=db, claim_destructive_gate=claim_gate
        )
        expected = ["canonical-review", "finalize"]
    else:
        harness.service_for(db).retract_conversation_memories(UID, CONVERSATION, claim_destructive_gate=claim_gate)
        expected = ["canonical-review", "finalize", "finalize", "service-review", "receipts"]
    assert [call[0] for call in calls] == expected
    for label, uid, target_ids, kwargs in calls:
        assert uid == UID and set(target_ids) == set(ids)
        assert kwargs["revalidate_gate"] is claim_gate
        assert kwargs.get("db_client", kwargs.get("firestore_client")) is db
        if label.endswith("review"):
            assert kwargs["include_legacy_commits"] is True
        if label != "receipts":
            assert kwargs["preserve_source_replacement_receipts"] is True


def test_final_pass_sees_late_history_and_retains_deletion_receipts(harness, monkeypatch):
    _enable(monkeypatch)
    db, ids = harness.make_db()
    late_path = f"users/{UID}/memory_outbox/late-provider-write"
    original_review = harness.service_mod.purge_stale_review_conflicts_for_memories
    calls = []

    def late_write(uid, target_ids, **kwargs):
        assert kwargs["include_legacy_commits"] is False
        # Canonical cleanup has proved provider absence, but the tombstones
        # and retry receipt must still exist before the task-wide final purge.
        assert all(f"users/{UID}/memory_items/{mid}" in db.docs for mid in ids)
        assert any("/memory_source_replacements/" in path for path in db.docs)
        for mid in ids:
            assert ("vector", mid) in harness.events
            assert ("keyword", mid) in harness.events
            assert ("graph", mid) in harness.events
        calls.append(list(target_ids))
        original_review(uid, target_ids, **kwargs)
        db.docs[late_path] = {"memory_id": ids[0], "content": "late private content"}

    monkeypatch.setattr(harness.service_mod, "purge_stale_review_conflicts_for_memories", late_write)
    harness.service_for(db, historical_ids=["historical-only"]).retract_conversation_memories(UID, CONVERSATION)
    assert len(calls) == 1
    assert set(calls[0]) == set(ids + ["historical-only"])
    assert late_path not in db.docs
    assert ("historical", "historical-only") in harness.events
    assert not any("/memory_source_replacements/" in path for path in db.docs)
    from database.memory_apply_store import privacy_deletion_receipt_id

    for mid in ids:
        receipt = db.docs[f"users/{UID}/memory_deletion_receipts/{privacy_deletion_receipt_id(UID, mid)}"]
        assert receipt["schema_version"] == "memory_deletion_receipt.v2"
        assert mid not in repr(receipt)


@pytest.mark.parametrize("claim_gate", [False, True])
def test_canonical_final_pass_reads_history_written_after_review(harness, monkeypatch, claim_gate):
    _enable(monkeypatch)
    db, ids = harness.make_db()
    late_path = f"users/{UID}/memory_outbox/late-canonical-write"
    original_review = harness.adapter.purge_stale_review_conflicts_for_memories

    def late_write(uid, target_ids, **kwargs):
        assert kwargs["include_legacy_commits"] is False
        assert kwargs["revalidate_gate"] is claim_gate
        original_review(uid, target_ids, **kwargs)
        db.docs[late_path] = {"memory_id": ids[0], "content": "late private content"}

    monkeypatch.setattr(harness.adapter, "purge_stale_review_conflicts_for_memories", late_write)
    harness.adapter.retract_conversation_sourced_memories(
        UID, CONVERSATION, db_client=db, claim_destructive_gate=claim_gate
    )
    assert late_path not in db.docs
    assert all(f"users/{UID}/memory_items/{mid}" not in db.docs for mid in ids)


@pytest.mark.parametrize("provider", ["vector", "keyword", "graph"])
def test_provider_absence_failure_keeps_retry_inventory(harness, monkeypatch, provider):
    _enable(monkeypatch)
    db, ids = harness.make_db()
    if provider == "vector":
        monkeypatch.setattr(harness.adapter, "delete_canonical_memory_vector", lambda *a, **kw: False)
    elif provider == "keyword":
        monkeypatch.setattr(harness.keyword, "delete_atom_keyword_doc", lambda *a, **kw: False)
    else:

        def unavailable(*args, **kwargs):
            raise RuntimeError("graph privacy cleanup unavailable")

        monkeypatch.setattr(harness.adapter.kg_db, "delete_memory_graph_assertion", unavailable)
    with pytest.raises(RuntimeError, match="privacy cleanup unavailable"):
        harness.service_for(db).retract_conversation_memories(UID, CONVERSATION)
    assert all(f"users/{UID}/memory_items/{mid}" in db.docs for mid in ids)
    assert any("/memory_source_replacements/" in path for path in db.docs)
    assert harness.adapter._DEFERRED_CANONICAL_PRIVACY_FINALIZATION.get() is None


def test_final_pass_reproves_provider_absence_before_finalizing(harness, monkeypatch):
    _enable(monkeypatch)
    db, ids = harness.make_db()
    attempts = Counter()

    def provider(uid, mid):
        attempts[mid] += 1
        return attempts[mid] == 1

    monkeypatch.setattr(harness.adapter, "delete_canonical_memory_vector", provider)
    with pytest.raises(harness.service_mod.HTTPException) as error:
        harness.service_for(db).retract_conversation_memories(UID, CONVERSATION)
    assert error.value.status_code == 503
    assert sorted(attempts.values()) == [1, 1, 2]
    assert all(f"users/{UID}/memory_items/{mid}" in db.docs for mid in ids)
    assert any("/memory_source_replacements/" in path for path in db.docs)


@pytest.mark.parametrize("claim_gate", [False, True])
@pytest.mark.parametrize("enabled", [False, True])
def test_active_legal_hold_blocks_coalesced_retraction(harness, monkeypatch, claim_gate, enabled):
    _enable(monkeypatch, enabled)
    db, ids = harness.make_db()
    db.docs[f"legal_holds/{UID}"] = {"schema_version": "legal_hold.v1", "issuer": "admin", "active": True}
    with pytest.raises(harness.holds.LegalHoldActive):
        harness.service_for(db).retract_conversation_memories(UID, CONVERSATION, claim_destructive_gate=claim_gate)
    assert all(f"users/{UID}/memory_items/{mid}" in db.docs for mid in ids)
    assert harness.events == []


@pytest.mark.parametrize("failure", ["review", "final-history", "suppression", "historical"])
def test_failed_task_can_retry_from_durable_receipt(harness, monkeypatch, failure):
    _enable(monkeypatch)
    db, ids = harness.make_db()
    service = harness.service_for(db, historical_ids=["legacy"])
    target, name = {
        "review": (harness.service_mod, "purge_stale_review_conflicts_for_memories"),
        "final-history": (harness.ledger, "purge_canonical_privacy_history_for_memories"),
        "suppression": (service, "_write_historical_overrides"),
        "historical": (harness.service_mod.HistoricalMemoryAdapter, "cleanup"),
    }[failure]
    original = getattr(target, name)

    def unavailable(*args, **kwargs):
        raise RuntimeError("injected cleanup outage")

    monkeypatch.setattr(target, name, unavailable)
    with pytest.raises((RuntimeError, harness.service_mod.HTTPException)):
        service.retract_conversation_memories(UID, CONVERSATION)
    assert any("/memory_source_replacements/" in path for path in db.docs)
    if failure != "historical":
        assert all(f"users/{UID}/memory_items/{mid}" in db.docs for mid in ids)
    monkeypatch.setattr(target, name, original)
    result = service.retract_conversation_memories(UID, CONVERSATION)
    assert set(result["retracted_memory_ids"]) == set(ids)
    assert all(f"users/{UID}/memory_items/{mid}" not in db.docs for mid in ids)
    assert not any("/memory_source_replacements/" in path for path in db.docs)


@pytest.mark.parametrize("phase", ["before-final", "during-final"])
def test_takeover_stops_coalesced_deletes_and_keeps_receipt(harness, monkeypatch, phase):
    _enable(monkeypatch)
    db, ids = harness.make_db()
    if phase == "before-final":
        original_review = harness.service_mod.purge_stale_review_conflicts_for_memories

        def take_over(*args, **kwargs):
            original_review(*args, **kwargs)
            db.docs[f"legal_hold_deletion_gates/{UID}"]["token"] = "peer-token"

        monkeypatch.setattr(harness.service_mod, "purge_stale_review_conflicts_for_memories", take_over)
    else:
        original_check = harness.ledger.assert_destructive_gate_still_ours
        deletes = []

        def take_over(uid, kind, **kwargs):
            deletes.append(kind)
            if len(deletes) == 2:
                db.docs[f"legal_hold_deletion_gates/{UID}"]["token"] = "peer-token"
            return original_check(uid, kind, **kwargs)

        monkeypatch.setattr(harness.ledger, "assert_destructive_gate_still_ours", take_over)
    with pytest.raises(harness.service_mod.HTTPException) as error:
        harness.service_for(db).retract_conversation_memories(UID, CONVERSATION)
    assert error.value.status_code == 409
    assert all(f"users/{UID}/memory_items/{mid}" in db.docs for mid in ids)
    assert any("/memory_source_replacements/" in path for path in db.docs)


def test_deferral_is_user_and_client_scoped(harness, monkeypatch):
    _enable(monkeypatch)
    first_db, first_ids = harness.make_db(1)
    second_db, second_ids = harness.make_db(1)
    finalize = MagicMock()
    monkeypatch.setattr(harness.ledger, "finalize_canonical_privacy_tombstones", finalize)
    with harness.adapter.defer_conversation_privacy_finalization(UID, db_client=first_db) as deferred:
        for uid, db, ids in ((UID, second_db, second_ids), ("other-user", first_db, first_ids)):
            harness.adapter.purge_canonical_memory_projections(
                uid, ids, db_client=db, reason="scope-test", preserve_source_replacement_receipts=True
            )
        assert deferred == []
    assert finalize.call_count == 2
    assert harness.adapter._DEFERRED_CANONICAL_PRIVACY_FINALIZATION.get() is None
