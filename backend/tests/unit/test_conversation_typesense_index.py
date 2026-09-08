"""First-party conversation Typesense projection — payload, gating, fail-open.

Covers the contract from SCA-452 (round 2):
- upsert payload shape matches the `conversations` collection schema the
  Firebase extension created and `utils.conversations.search` queries;
- ``transcript_segments`` / speaker fields can never reach Typesense;
- e2ee accounts are skipped by deleting any previously indexed document —
  and the kill switch disables upserts, never these privacy deletes;
- the Firestore document path is the index key (a stale stored ``id`` loses);
- a required purge fails loudly when Typesense is unconfigured;
- Typesense being down never raises out of any conversation write path;
- every durable write/delete choke point converges the index, including the
  AlreadyExists branch, the absent-owner processor result, failed-finalization
  discard, dead-letter bypasses, and empty-recording deletion.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
# No module-scope TYPESENSE env on purpose: it leaks process-wide and flips
# other suites' account-deletion wipes into real Typesense network attempts
# (round-2 regression). Each test sets the env it needs via `index_env`.

from database import conversations as conversations_db
from utils.conversations import lifecycle as conversations_lifecycle
from utils.conversations import typesense_index
from utils.conversations.typesense_index import (
    build_conversation_index_document,
    conversation_index_writes_enabled,
    delete_conversation_index_doc,
    purge_user_conversation_index,
    sync_conversation_index_after_write,
)

UID = "uid-conv-typesense"
CONVERSATION_ID = "conv-1"

ALLOWED_FIELDS = frozenset(
    {"id", "userId", "created_at", "discarded", "started_at", "finished_at", "structured", "geolocation"}
)


def _conversation_data() -> dict:
    return {
        "id": CONVERSATION_ID,
        "created_at": datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc),
        "started_at": datetime(2026, 9, 5, 11, 58, 30, tzinfo=timezone.utc),
        "finished_at": datetime(2026, 9, 5, 12, 4, 0, tzinfo=timezone.utc),
        "discarded": False,
        "structured": {"title": "Standup", "overview": "Daily sync", "events": [], "action_items": []},
        "geolocation": {"latitude": 37.7749, "longitude": -122.4194, "google_place_id": "place-x"},
        # Fields that must never reach Typesense.
        "transcript_segments": [
            {"text": "hello", "is_user": True, "person_id": "speaker-1"},
            {"text": "world", "is_user": False, "person_id": "speaker-2"},
        ],
        "photos": [{"base64": "zzz"}],
        "apps_results": [{"app_id": "a1", "content": "app output"}],
    }


def _fake_typesense() -> tuple[MagicMock, dict]:
    docs_store: dict = {}
    typesense_client = MagicMock()

    def _upsert(doc):
        docs_store[doc["id"]] = doc
        return doc

    def _delete_filter(params):
        filter_by = params.get("filter_by", "")
        quoted = [value for value in filter_by.split("`") if value and ":" not in value and "[" not in value]
        user_id = quoted[0] if quoted else None
        to_delete = [doc_id for doc_id, doc in docs_store.items() if doc.get("userId") == user_id]
        for doc_id in to_delete:
            docs_store.pop(doc_id, None)
        return {"num_deleted": len(to_delete)}

    documents = MagicMock()
    documents.upsert.side_effect = _upsert
    documents.delete.side_effect = _delete_filter
    documents.__getitem__.side_effect = lambda doc_id: MagicMock(delete=lambda: docs_store.pop(doc_id, None))

    collection = MagicMock()
    collection.documents = documents
    typesense_client.collections.__getitem__.return_value = collection
    return typesense_client, docs_store


def _policy_db(level: str = "enhanced") -> MagicMock:
    user_doc = MagicMock(exists=True, to_dict=lambda: {"data_protection_level": level})
    db_client = MagicMock()
    db_client.document.return_value = MagicMock(get=lambda: user_doc)
    return db_client


def _firestore_with_doc(doc: dict | None) -> MagicMock:
    snapshot = MagicMock()
    snapshot.exists = doc is not None
    snapshot.to_dict = lambda: dict(doc) if doc is not None else None
    client = MagicMock()
    client.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = (
        snapshot
    )
    return client


class _Snapshot:
    def __init__(self, data):
        self.exists = data is not None
        self._data = data

    def to_dict(self):
        return self._data


@pytest.fixture
def index_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TYPESENSE_HOST", "localhost")
    monkeypatch.setenv("TYPESENSE_API_KEY", "test-key-not-real")
    monkeypatch.delenv(typesense_index.CONVERSATION_INDEX_WRITES_ENV, raising=False)


@pytest.fixture
def mock_typesense(index_env):
    typesense_client, docs_store = _fake_typesense()
    with (
        patch.object(typesense_index, "_typesense_client", return_value=typesense_client),
        patch.object(typesense_index, "_resolve_default_db_client", return_value=_policy_db()),
    ):
        yield typesense_client, docs_store


class _Ref:
    def __init__(self, snapshot):
        self._snapshot = snapshot
        self.written = None

    def get(self, transaction=None, field_paths=None):
        return self._snapshot

    def update(self, data=None, **kwargs):
        self.written = data

    def create(self, data):
        if self.written == "EXISTS":
            from google.api_core.exceptions import AlreadyExists

            raise AlreadyExists("conflict")
        self.written = data

    def delete(self):
        self.written = "DELETED"

    def collections(self):
        return []


class _Transaction:
    def set(self, ref, data, merge=False):
        ref.written = data

    def update(self, ref, data):
        ref.written = data


class TestDocumentShape:
    def test_payload_carries_exactly_the_schema_fields(self):
        document = build_conversation_index_document(UID, _conversation_data())

        assert document is not None
        assert set(document) == ALLOWED_FIELDS
        assert document["id"] == CONVERSATION_ID
        assert document["userId"] == UID
        assert document["created_at"] == 1788609600  # 2026-09-05T12:00:00Z in unix seconds
        assert document["started_at"] == 1788609510
        assert document["finished_at"] == 1788609840
        assert document["discarded"] is False
        assert document["structured"]["title"] == "Standup"
        assert document["geolocation"] == [37.7749, -122.4194]

    def test_transcript_segments_and_speaker_fields_never_leave(self):
        document = build_conversation_index_document(UID, _conversation_data())

        dumped = str(document)
        assert "transcript_segments" not in dumped
        assert "speaker-1" not in dumped
        assert "speaker-2" not in dumped
        assert "is_user" not in dumped
        assert "zzz" not in dumped

    def test_epoch_numbers_pass_through(self):
        document = build_conversation_index_document(
            UID,
            {
                "id": "c2",
                "created_at": 1788609600,
                "started_at": 1788609510.25,
                "discarded": True,
            },
        )

        assert document is not None
        assert document["created_at"] == 1788609600
        assert document["started_at"] == 1788609510
        assert document["discarded"] is True

    def test_naive_datetime_is_treated_as_utc(self):
        document = build_conversation_index_document(UID, {"id": "c3", "created_at": datetime(2026, 9, 5, 12, 0, 0)})

        assert document is not None
        assert document["created_at"] == 1788609600

    def test_unparseable_geolocation_is_omitted_not_fatal(self):
        document = build_conversation_index_document(
            UID,
            {
                "id": "c4",
                "created_at": 1788609600,
                "geolocation": {"latitude": "north", "longitude": None},
            },
        )

        assert document is not None
        assert "geolocation" not in document

    def test_geopoint_object_maps_to_typesense_point(self):
        geopoint = MagicMock(latitude=52.52, longitude=13.405)

        document = build_conversation_index_document(
            UID, {"id": "c5", "created_at": 1788609600, "geolocation": geopoint}
        )

        assert document is not None
        assert document["geolocation"] == [52.52, 13.405]

    def test_missing_created_at_is_unindexable(self):
        assert build_conversation_index_document(UID, {"id": "c6"}) is None
        assert build_conversation_index_document(UID, {"id": "", "created_at": 1788609600}) is None


class TestWriteFlag:
    def test_default_on_when_typesense_env_present(self, index_env, monkeypatch):
        assert conversation_index_writes_enabled() is True

    @pytest.mark.parametrize("value", ["0", "false", "off", "no", "OFF"])
    def test_kill_switch_disables(self, index_env, monkeypatch, value):
        monkeypatch.setenv(typesense_index.CONVERSATION_INDEX_WRITES_ENV, value)
        assert conversation_index_writes_enabled() is False

    def test_missing_typesense_env_disables(self, monkeypatch):
        monkeypatch.delenv("TYPESENSE_HOST", raising=False)
        monkeypatch.delenv("TYPESENSE_API_KEY", raising=False)
        assert conversation_index_writes_enabled() is False


class TestSync:
    def test_sync_upserts_projected_document(self, index_env, mock_typesense):
        typesense_client, docs_store = mock_typesense
        firestore = _firestore_with_doc(_conversation_data())

        assert sync_conversation_index_after_write(UID, CONVERSATION_ID, firestore_client=firestore) is True

        assert set(docs_store) == {CONVERSATION_ID}
        assert set(docs_store[CONVERSATION_ID]) == ALLOWED_FIELDS
        typesense_client.collections.__getitem__.assert_called_with("conversations")

    def test_firestore_path_is_the_index_key_not_a_stale_stored_id(self, index_env, mock_typesense):
        _, docs_store = mock_typesense
        stale = _conversation_data()
        stale["id"] = "wrong-stale-id"
        firestore = _firestore_with_doc(stale)

        assert sync_conversation_index_after_write(UID, CONVERSATION_ID, firestore_client=firestore) is True

        assert set(docs_store) == {CONVERSATION_ID}
        assert docs_store[CONVERSATION_ID]["id"] == CONVERSATION_ID

    def test_unconfigured_typesense_skips_without_any_io(self, monkeypatch):
        """No shared Typesense env means no index exists: skip before any
        Firestore policy read or Typesense client construction (hermetic
        harnesses depend on this being zero-I/O)."""
        monkeypatch.delenv("TYPESENSE_HOST", raising=False)
        monkeypatch.delenv("TYPESENSE_API_KEY", raising=False)

        with (
            patch.object(typesense_index, "_resolve_default_db_client", side_effect=AssertionError("policy read")),
            patch.object(typesense_index, "_typesense_client", side_effect=AssertionError("client")),
        ):
            assert sync_conversation_index_after_write(UID, CONVERSATION_ID) is False

    def test_sync_skips_upserts_when_disabled(self, index_env, monkeypatch, mock_typesense):
        typesense_client, _ = mock_typesense
        monkeypatch.setenv(typesense_index.CONVERSATION_INDEX_WRITES_ENV, "0")
        firestore = _firestore_with_doc(_conversation_data())

        assert sync_conversation_index_after_write(UID, CONVERSATION_ID, firestore_client=firestore) is False

        typesense_client.collections.__getitem__.return_value.documents.upsert.assert_not_called()

    def test_kill_switch_still_runs_e2ee_delete(self, index_env, monkeypatch, mock_typesense):
        """Disabling upserts must not disable privacy cleanup (cubic P1)."""
        typesense_client, docs_store = mock_typesense
        monkeypatch.setenv(typesense_index.CONVERSATION_INDEX_WRITES_ENV, "0")
        docs_store[CONVERSATION_ID] = {"id": CONVERSATION_ID, "userId": UID}
        firestore = _firestore_with_doc(_conversation_data())

        with patch.object(typesense_index, "_resolve_default_db_client", return_value=_policy_db(level="e2ee")):
            assert sync_conversation_index_after_write(UID, CONVERSATION_ID, firestore_client=firestore) is True

        assert docs_store == {}
        typesense_client.collections.__getitem__.return_value.documents.upsert.assert_not_called()

    def test_e2ee_user_deletes_instead_of_upserting(self, index_env, mock_typesense):
        typesense_client, docs_store = mock_typesense
        docs_store[CONVERSATION_ID] = {"id": CONVERSATION_ID, "userId": UID}
        firestore = _firestore_with_doc(_conversation_data())

        with patch.object(typesense_index, "_resolve_default_db_client", return_value=_policy_db(level="e2ee")):
            assert sync_conversation_index_after_write(UID, CONVERSATION_ID, firestore_client=firestore) is True

        assert docs_store == {}
        typesense_client.collections.__getitem__.return_value.documents.upsert.assert_not_called()

    def test_missing_firestore_doc_converges_to_delete(self, index_env, mock_typesense):
        _, docs_store = mock_typesense
        docs_store[CONVERSATION_ID] = {"id": CONVERSATION_ID, "userId": UID}
        firestore = _firestore_with_doc(None)

        assert sync_conversation_index_after_write(UID, CONVERSATION_ID, firestore_client=firestore) is True

        assert docs_store == {}

    def test_typesense_down_does_not_raise(self, index_env, mock_typesense):
        typesense_client, _ = mock_typesense
        typesense_client.collections.__getitem__.return_value.documents.upsert.side_effect = Exception(
            "connection refused"
        )
        firestore = _firestore_with_doc(_conversation_data())

        assert sync_conversation_index_after_write(UID, CONVERSATION_ID, firestore_client=firestore) is False

    def test_projection_read_failure_does_not_raise(self, index_env, mock_typesense):
        firestore = _firestore_with_doc(_conversation_data())
        firestore.collection.return_value.document.return_value.collection.return_value.document.return_value.get.side_effect = Exception(
            "firestore unavailable"
        )

        assert sync_conversation_index_after_write(UID, CONVERSATION_ID, firestore_client=firestore) is False

    def test_internal_never_raise_contract(self, index_env, mock_typesense):
        firestore = _firestore_with_doc(_conversation_data())

        with patch.object(
            typesense_index,
            "_sync_conversation_index_after_write",
            side_effect=Exception("unexpected bug"),
        ):
            assert sync_conversation_index_after_write(UID, CONVERSATION_ID, firestore_client=firestore) is False


class TestDelete:
    def test_delete_removes_by_conversation_id(self, mock_typesense):
        _, docs_store = mock_typesense
        docs_store[CONVERSATION_ID] = {"id": CONVERSATION_ID, "userId": UID}

        assert delete_conversation_index_doc(UID, CONVERSATION_ID) is True
        assert docs_store == {}

    def test_delete_ignores_the_kill_switch(self, mock_typesense, monkeypatch):
        monkeypatch.setenv(typesense_index.CONVERSATION_INDEX_WRITES_ENV, "0")
        _, docs_store = mock_typesense
        docs_store[CONVERSATION_ID] = {"id": CONVERSATION_ID, "userId": UID}

        assert delete_conversation_index_doc(UID, CONVERSATION_ID) is True
        assert docs_store == {}

    def test_object_not_found_is_success(self, mock_typesense):
        typesense_client, _ = mock_typesense

        class ObjectNotFound(Exception):
            pass

        ObjectNotFound.__module__ = "typesense.exceptions"
        failing_doc = MagicMock()
        failing_doc.delete.side_effect = ObjectNotFound("not found")
        typesense_client.collections.__getitem__.return_value.documents.__getitem__.side_effect = (
            lambda doc_id: failing_doc
        )

        assert delete_conversation_index_doc(UID, "missing-conv") is True

    def test_typesense_down_does_not_raise_on_delete(self, mock_typesense):
        typesense_client, _ = mock_typesense
        failing_doc = MagicMock()
        failing_doc.delete.side_effect = Exception("timeout")
        typesense_client.collections.__getitem__.return_value.documents.__getitem__.side_effect = (
            lambda doc_id: failing_doc
        )

        assert delete_conversation_index_doc(UID, CONVERSATION_ID) is False

    def test_unconfigured_typesense_is_a_silent_noop(self, monkeypatch):
        monkeypatch.delenv("TYPESENSE_HOST", raising=False)
        monkeypatch.delenv("TYPESENSE_API_KEY", raising=False)

        with patch.object(typesense_index, "_typesense_client", side_effect=AssertionError("client constructed")):
            assert delete_conversation_index_doc(UID, CONVERSATION_ID) is False


class TestPurge:
    def test_purge_deletes_all_user_documents(self, mock_typesense):
        _, docs_store = mock_typesense
        docs_store.update(
            {
                "c1": {"id": "c1", "userId": UID},
                "c2": {"id": "c2", "userId": UID},
                "other": {"id": "other", "userId": "someone-else"},
            }
        )

        assert purge_user_conversation_index(UID) == 2
        assert set(docs_store) == {"other"}

    def test_purge_raises_when_required(self, mock_typesense):
        typesense_client, _ = mock_typesense
        typesense_client.collections.__getitem__.return_value.documents.delete.side_effect = Exception("typesense down")

        with pytest.raises(Exception, match="typesense down"):
            purge_user_conversation_index(UID, raise_on_failure=True)

    def test_required_purge_raises_when_typesense_unconfigured(self, monkeypatch):
        """A required purge must not report silent success (cubic P1)."""
        monkeypatch.delenv("TYPESENSE_HOST", raising=False)
        monkeypatch.delenv("TYPESENSE_API_KEY", raising=False)

        with pytest.raises(RuntimeError, match="not configured"):
            purge_user_conversation_index(UID, raise_on_failure=True)

    def test_purge_is_silent_noop_when_unconfigured(self, monkeypatch):
        monkeypatch.delenv("TYPESENSE_HOST", raising=False)
        monkeypatch.delenv("TYPESENSE_API_KEY", raising=False)

        assert purge_user_conversation_index(UID) == 0


class TestConversationWriteWiring:
    """Every durable write path must converge the index and must never leak a
    Typesense failure into the caller (SCA-452 fail-open requirement)."""

    @pytest.fixture
    def wired(self, monkeypatch: pytest.MonkeyPatch):
        """Patch the hook seam: the DB layer lazy-imports these functions from
        ``utils.conversations.typesense_index`` at call time, so patching the
        module attributes intercepts every hook."""
        # conversations_db is imported at module scope on purpose: binding the
        # real module object at collection time keeps this suite independent of
        # import-order games other test modules play with sys.modules.
        sync = MagicMock()
        delete = MagicMock()
        monkeypatch.setattr(typesense_index, "sync_conversation_index_after_write", sync)
        monkeypatch.setattr(typesense_index, "delete_conversation_index_doc", delete)

        conversation_ref = _Ref(_Snapshot({"data_protection_level": "standard"}))
        db = MagicMock()
        db.collection.return_value.document.return_value.collection.return_value.document.return_value = (
            conversation_ref
        )
        db.transaction.return_value = _Transaction()
        monkeypatch.setattr(conversations_db, "db", db)
        monkeypatch.setattr(conversations_db.firestore, "transactional", lambda fn: fn)
        return sync, delete, conversation_ref

    def test_discard_marks_and_syncs(self, wired):
        sync, _, _ = wired

        conversations_db.set_conversation_as_discarded(UID, CONVERSATION_ID)

        sync.assert_called_once_with(UID, CONVERSATION_ID)

    def test_restore_marks_and_syncs(self, wired):
        sync, _, _ = wired

        conversations_db.restore_conversation_from_discarded(UID, CONVERSATION_ID)

        sync.assert_called_once_with(UID, CONVERSATION_ID)

    def test_title_edit_syncs(self, wired):
        sync, _, _ = wired

        conversations_db.update_conversation_title(UID, CONVERSATION_ID, "Renamed")

        sync.assert_called_once_with(UID, CONVERSATION_ID)

    def test_summary_overview_edit_syncs(self, wired):
        sync, _, _ = wired

        assert conversations_db.update_conversation_summary(UID, CONVERSATION_ID, None, "New overview") == "ok"

        sync.assert_called_once_with(UID, CONVERSATION_ID)

    def test_summary_app_result_edit_does_not_sync(self, wired):
        sync, _, _ = wired

        result = conversations_db.update_conversation_summary(UID, CONVERSATION_ID, "missing-app", "content")

        assert result == "app_result_not_found"
        sync.assert_not_called()

    def test_finished_at_update_syncs(self, wired):
        sync, _, _ = wired

        conversations_db.update_conversation_finished_at(
            UID, CONVERSATION_ID, datetime(2026, 9, 5, 12, 5, 0, tzinfo=timezone.utc)
        )

        sync.assert_called_once_with(UID, CONVERSATION_ID)

    def test_delete_removes_from_index(self, wired):
        _, delete, _ = wired

        conversations_db.delete_conversation(UID, CONVERSATION_ID)

        delete.assert_called_once_with(UID, CONVERSATION_ID)

    def test_structured_update_syncs(self, wired):
        sync, _, _ = wired

        assert conversations_db.update_conversation(UID, CONVERSATION_ID, {"structured.title": "New"}) is True

        sync.assert_called_once_with(UID, CONVERSATION_ID)

    def test_non_search_update_does_not_sync(self, wired):
        sync, _, _ = wired

        assert conversations_db.update_conversation(UID, CONVERSATION_ID, {"starred": True}) is True

        sync.assert_not_called()

    def test_upsert_with_lifecycle_syncs(self, wired):
        sync, _, _ = wired

        conversations_db.upsert_conversation_with_lifecycle(UID, {"id": CONVERSATION_ID, "status": "in_progress"})

        sync.assert_called_once_with(UID, CONVERSATION_ID)

    def test_create_if_absent_syncs_on_create(self, wired):
        sync, _, _ = wired

        assert conversations_db.create_conversation_if_absent_with_lifecycle(UID, {"id": CONVERSATION_ID}) is True

        sync.assert_called_once_with(UID, CONVERSATION_ID)

    def test_create_if_absent_syncs_on_already_exists(self, wired):
        sync, _, ref = wired
        ref.written = "EXISTS"  # _Ref.create raises AlreadyExists

        assert conversations_db.create_conversation_if_absent_with_lifecycle(UID, {"id": CONVERSATION_ID}) is False

        sync.assert_called_once_with(UID, CONVERSATION_ID)

    def test_persist_processing_result_syncs_for_present_owner(self, wired):
        sync, _, _ = wired

        assert conversations_db.persist_processing_result_with_lifecycle(UID, {"id": CONVERSATION_ID}) is True

        sync.assert_called_once_with(UID, CONVERSATION_ID)

    def test_persist_processing_result_deletes_for_absent_owner(self, wired):
        sync, delete, ref = wired
        ref._snapshot = _Snapshot(None)

        assert conversations_db.persist_processing_result_with_lifecycle(UID, {"id": CONVERSATION_ID}) is False

        sync.assert_not_called()
        delete.assert_called_once_with(UID, CONVERSATION_ID)


class TestLifecycleWiring:
    """Paths that mutate conversations outside the conversations_db hooks."""

    @pytest.fixture
    def wired_lifecycle(self, monkeypatch: pytest.MonkeyPatch):
        sync = MagicMock()
        delete = MagicMock()
        monkeypatch.setattr(typesense_index, "sync_conversation_index_after_write", sync)
        monkeypatch.setattr(typesense_index, "delete_conversation_index_doc", delete)
        return sync, delete

    def test_fail_and_discard_processing_syncs_when_claimed(self, wired_lifecycle, monkeypatch):
        sync, _ = wired_lifecycle
        monkeypatch.setattr(
            conversations_lifecycle.conversations_db, "claim_conversation_status", MagicMock(return_value=True)
        )

        assert conversations_lifecycle.fail_and_discard_processing(UID, CONVERSATION_ID) is True

        sync.assert_called_once_with(UID, CONVERSATION_ID)

    def test_fail_and_discard_processing_skips_sync_when_fence_rejects(self, wired_lifecycle, monkeypatch):
        sync, _ = wired_lifecycle
        monkeypatch.setattr(
            conversations_lifecycle.conversations_db, "claim_conversation_status", MagicMock(return_value=False)
        )

        assert conversations_lifecycle.fail_and_discard_processing(UID, CONVERSATION_ID) is False

        sync.assert_not_called()

    def test_delete_empty_recording_conversation_deletes_index_before_photo_cleanup(self, wired_lifecycle, monkeypatch):
        _, delete = wired_lifecycle
        order: list[str] = []
        delete.side_effect = lambda uid, cid: order.append("index_delete")
        monkeypatch.setattr(
            conversations_lifecycle.recording_sessions_db,
            "tombstone_and_delete_empty_conversation",
            MagicMock(return_value=True),
        )
        photos = MagicMock(side_effect=lambda *a: order.append("photos"))
        monkeypatch.setattr(conversations_lifecycle.conversations_db, "delete_conversation_photos", photos)
        monkeypatch.setattr(
            conversations_lifecycle,
            "_discard_unreferenced_audio",
            MagicMock(side_effect=lambda *a: order.append("audio")),
        )

        assert conversations_lifecycle.delete_empty_recording_conversation(UID, CONVERSATION_ID, "session-1") is True

        delete.assert_called_once_with(UID, CONVERSATION_ID)
        assert order == ["index_delete", "photos", "audio"]

    def test_delete_empty_recording_conversation_noop_when_not_deleted(self, wired_lifecycle, monkeypatch):
        _, delete = wired_lifecycle
        monkeypatch.setattr(
            conversations_lifecycle.recording_sessions_db,
            "tombstone_and_delete_empty_conversation",
            MagicMock(return_value=False),
        )

        assert conversations_lifecycle.delete_empty_recording_conversation(UID, CONVERSATION_ID, "session-1") is False

        delete.assert_not_called()


class TestFailOpenWiring:
    def test_typesense_outage_does_not_raise_out_of_write_paths(self, monkeypatch: pytest.MonkeyPatch):
        """The real fail-open path: every Typesense call fails, and neither the
        discard update nor the delete may raise or skip its Firestore write."""
        conversation_ref = _Ref(_Snapshot({"data_protection_level": "standard"}))
        db = MagicMock()
        db.collection.return_value.document.return_value.collection.return_value.document.return_value = (
            conversation_ref
        )
        monkeypatch.setattr(conversations_db, "db", db)
        monkeypatch.setenv("TYPESENSE_HOST", "localhost")
        monkeypatch.setenv("TYPESENSE_API_KEY", "test-key-not-real")
        monkeypatch.delenv(typesense_index.CONVERSATION_INDEX_WRITES_ENV, raising=False)

        broken_client = MagicMock()
        broken_client.collections.__getitem__.return_value.documents.upsert.side_effect = Exception("typesense down")
        broken_client.collections.__getitem__.return_value.documents.__getitem__.side_effect = Exception(
            "typesense down"
        )
        monkeypatch.setattr(typesense_index, "_typesense_client", lambda: broken_client)
        monkeypatch.setattr(typesense_index, "_resolve_default_db_client", lambda: _policy_db())

        conversations_db.set_conversation_as_discarded(UID, CONVERSATION_ID)
        conversations_db.delete_conversation(UID, CONVERSATION_ID)

        # The Firestore writes themselves still landed.
        assert conversation_ref.written == "DELETED"

    def test_lazy_import_failure_does_not_raise_out_of_write_paths(self, monkeypatch: pytest.MonkeyPatch):
        """The round-one CI regression: a harness where utils.conversations is
        unavailable must not break the durable write paths."""
        import builtins

        conversation_ref = _Ref(_Snapshot({"data_protection_level": "standard"}))
        db = MagicMock()
        db.collection.return_value.document.return_value.collection.return_value.document.return_value = (
            conversation_ref
        )
        monkeypatch.setattr(conversations_db, "db", db)

        real_import = builtins.__import__

        def _blocked_import(name, *args, **kwargs):
            if name == "utils.conversations.typesense_index":
                raise ImportError("cannot import name 'typesense_index' from 'utils.conversations'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _blocked_import)

        conversations_db.set_conversation_as_discarded(UID, CONVERSATION_ID)
        conversations_db.delete_conversation(UID, CONVERSATION_ID)

        assert conversation_ref.written == "DELETED"
