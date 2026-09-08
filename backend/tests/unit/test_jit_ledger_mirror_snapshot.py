from datetime import datetime, timezone

import pytest

from models.memory_evidence import (
    ArtifactPreservationState,
    MemoryEvidence,
    ProvenanceVisibility,
    RedactionStatus,
    SourceState,
    SourceStateReason,
)
from models.product_memory import (
    LedgerWriteReason,
    MemoryItem,
    MemoryItemStatus,
    MemoryKind,
    MemoryLayer,
    MemorySubjectScope,
    ProcessingState,
)
from utils.memory import jit_ledger_mirror_snapshot as mirror

NOW = datetime(2026, 8, 24, tzinfo=timezone.utc)
SECRET = b"unit-test-jit-ledger-mirror-cursor-secret"


@pytest.fixture(autouse=True)
def _cursor_secret(monkeypatch):
    monkeypatch.setenv("MEMORY_V3_CURSOR_SECRET", SECRET.decode())


class _Snapshot:
    def __init__(self, item):
        self.id = item.memory_id
        self._payload = item.model_dump(mode="python")

    def to_dict(self):
        return self._payload


class _Ref:
    def __init__(self, identifier):
        self.id = identifier


class _Query:
    def __init__(self, rows, after=None, limit_count=None):
        self.rows = rows
        self.after = after
        self.limit_count = limit_count

    def order_by(self, *_args, **_kwargs):
        return self

    def start_after(self, cursor):
        return _Query(self.rows, after=cursor["__name__"].id, limit_count=self.limit_count)

    def limit(self, count):
        return _Query(self.rows, after=self.after, limit_count=count)

    def stream(self):
        rows = sorted(self.rows, key=lambda row: row.id)
        if self.after is not None:
            rows = [row for row in rows if row.id > self.after]
        return iter(rows[: self.limit_count])


class _Collection(_Query):
    def document(self, identifier):
        return _Ref(identifier)


class _Client:
    def __init__(self, items):
        self.rows = [_Snapshot(item) for item in items]

    def collection(self, _path):
        return _Collection(self.rows)


def _fence(head="head-7"):
    return mirror.LedgerMirrorFence(
        owner_id="owner",
        account_generation=3,
        source_generation=4,
        writer_epoch=2,
        head_commit_id=head,
        commit_sequence=7,
    )


def _item(identifier, **updates):
    data = {
        "memory_id": identifier,
        "uid": "owner",
        "version": 1,
        "tier": MemoryLayer.long_term,
        "status": MemoryItemStatus.active,
        "processing_state": ProcessingState.processed,
        "content": f"Memory {identifier}",
        "evidence": [],
        "source_state": SourceState.active,
        "sensitivity_labels": [],
        "visibility": "private",
        "user_asserted": True,
        "captured_at": NOW,
        "updated_at": NOW,
        "ledger_commit_id": "head-7",
        "ledger_sequence": 7,
        "account_generation": 3,
        "ledger_schema_version": "knowledge_ledger.v1",
        "kind": MemoryKind.fact,
        "subject_scope": MemorySubjectScope.primary_user,
        "slot": "home_city",
        "intent_backed": True,
        "write_reason": LedgerWriteReason.direct_user_statement,
    }
    data.update(updates)
    return MemoryItem(**data)


def test_cursor_chain_is_stable_and_final_page_includes_closed_history_and_alias(monkeypatch):
    monkeypatch.setattr(mirror, "_read_fence", lambda *_args, **_kwargs: _fence())
    first = _item("a")
    closed = _item(
        "b",
        status=MemoryItemStatus.superseded,
        valid_to=NOW,
        canonical_memory_id="c",
        superseded_by="c",
    )
    client = _Client([closed, first])

    page_one = mirror.read_authoritative_ledger_mirror_page("owner", page_size=1, firestore_client=client)
    page_two = mirror.read_authoritative_ledger_mirror_page(
        "owner", cursor=page_one.next_cursor, page_size=1, firestore_client=client
    )

    assert page_one.final_page is False
    assert [row.memory_id for row in page_one.rows] == ["a"]
    assert page_two.final_page is True
    assert [row.memory_id for row in page_two.rows] == ["b"]
    assert page_two.rows[0].status == "superseded"
    assert {(alias.alias_memory_id, alias.canonical_memory_id) for alias in page_two.aliases} == {("b", "c")}
    assert len(page_one.page_revision) == len(page_two.page_revision) == 64


def test_epoch_change_rejects_prior_cursor_without_querying_rows(monkeypatch):
    monkeypatch.setattr(mirror, "_read_fence", lambda *_args, **_kwargs: _fence("head-8"))
    old_cursor = mirror._encode_cursor(
        uid="owner",
        epoch_id=_fence("head-7").epoch_id,
        last_memory_id="a",
        chain_revision="a" * 64,
        scanned_count=1,
        projected_count=1,
        secret=SECRET,
    )

    page = mirror.read_authoritative_ledger_mirror_page(
        "owner", cursor=old_cursor, page_size=1, firestore_client=_Client([_item("b")])
    )

    assert page.failure_reason == "epoch_changed"
    assert page.rows == ()
    assert page.final_page is False


def test_deleted_row_must_be_content_purged_before_it_can_revoke_local_membership(monkeypatch):
    monkeypatch.setattr(mirror, "_read_fence", lambda *_args, **_kwargs: _fence())
    unsafe = _item(
        "deleted",
        status=MemoryItemStatus.tombstoned,
        source_state=SourceState.purged,
    )

    page = mirror.read_authoritative_ledger_mirror_page("owner", page_size=10, firestore_client=_Client([unsafe]))

    assert page.failure_reason == "row_invalid"
    assert page.rows == ()


def test_content_free_tombstone_is_an_explicit_deletion_marker(monkeypatch):
    monkeypatch.setattr(mirror, "_read_fence", lambda *_args, **_kwargs: _fence())
    tombstone = _item(
        "deleted",
        status=MemoryItemStatus.tombstoned,
        source_state=SourceState.purged,
        content=None,
        ledger_schema_version=None,
        kind=MemoryKind.fact,
        intent_backed=False,
        write_reason=None,
        arguments={},
        trigger_condition={},
        evidence=[
            MemoryEvidence(
                evidence_id="deleted-evidence",
                source_type="chat_turn",
                source_id="turn-1",
                source_version="v1",
                artifact_preservation=ArtifactPreservationState.deleted_by_user,
                source_state=SourceState.tombstoned,
                source_state_reason=SourceStateReason.deleted_by_user,
                provenance_visibility=ProvenanceVisibility.hidden,
                redaction_status=RedactionStatus.tombstoned,
                encryption_or_redaction_status=RedactionStatus.tombstoned,
            )
        ],
    )

    page = mirror.read_authoritative_ledger_mirror_page("owner", page_size=10, firestore_client=_Client([tombstone]))

    assert page.failure_reason is None
    assert page.final_page is True
    assert page.rows[0].content_purged is True
    assert page.rows[0].memory is None


def test_forged_cursor_cannot_skip_rows_or_certify_a_final_page(monkeypatch):
    monkeypatch.setattr(mirror, "_read_fence", lambda *_args, **_kwargs: _fence())
    client = _Client([_item("a"), _item("b"), _item("c")])
    first = mirror.read_authoritative_ledger_mirror_page("owner", page_size=1, firestore_client=client)
    assert first.next_cursor is not None
    prefix, payload, signature = first.next_cursor.split(".")
    forged_payload = payload[:-1] + ("A" if payload[-1] != "A" else "B")

    forged = mirror.read_authoritative_ledger_mirror_page(
        "owner",
        cursor=f"{prefix}.{forged_payload}.{signature}",
        page_size=1,
        firestore_client=client,
    )

    assert forged.failure_reason == "invalid_cursor"
    assert forged.final_page is False
    assert forged.rows == ()


def test_final_page_carries_cumulative_chain_counts(monkeypatch):
    monkeypatch.setattr(mirror, "_read_fence", lambda *_args, **_kwargs: _fence())
    client = _Client([_item("a"), _item("b")])
    first = mirror.read_authoritative_ledger_mirror_page("owner", page_size=1, firestore_client=client)
    final = mirror.read_authoritative_ledger_mirror_page(
        "owner", cursor=first.next_cursor, page_size=1, firestore_client=client
    )

    assert first.scanned_count == first.projected_count == 1
    assert final.scanned_count == final.projected_count == 2
    assert len(final.chain_revision) == 64


def test_head_flip_after_page_read_discards_every_row(monkeypatch):
    fences = iter([_fence("head-7"), _fence("head-8")])
    monkeypatch.setattr(mirror, "_read_fence", lambda *_args, **_kwargs: next(fences))

    page = mirror.read_authoritative_ledger_mirror_page("owner", page_size=10, firestore_client=_Client([_item("a")]))

    assert page.failure_reason == "authority_changed"
    assert page.rows == ()
    assert page.page_revision == ""
