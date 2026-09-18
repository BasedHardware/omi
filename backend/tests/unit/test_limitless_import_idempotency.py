"""Tests for Limitless import idempotency (deterministic conversation IDs).

Re-importing the same Limitless export must not create duplicate conversations,
and must not clobber edits a user made to a previously-imported conversation.
This is achieved by deriving each conversation's Firestore document ID
deterministically from (uid, lifelog start-time) and skipping lifelogs that are
already stored ("first import wins").
"""

import io
import uuid as uuid_lib
from datetime import datetime, timezone
from zipfile import ZipFile
from unittest.mock import MagicMock

import pytest

from database.document_ids import document_id_from_seed
from utils.imports import limitless

UID = "user-abc"
FN_A = "2025-10-08_07h00m25s_Morning-standup.md"
FN_B = "2025-10-09_09h15m00s_Design-review.md"


class _FakeConversationStore:
    """In-memory stand-in for Firestore's atomic create-if-absent (document.create())."""

    def __init__(self):
        self.docs = {}
        self.owners = {}
        self.fail_ids = set()

    def reset(self):
        self.docs = {}
        self.owners = {}
        self.fail_ids = set()

    def persist_imported_conversation(self, uid, data):
        cid = data["id"]
        if cid in self.fail_ids:
            raise RuntimeError("simulated firestore error")
        if cid in self.docs:
            return False
        self.docs[cid] = data
        self.owners[cid] = uid
        return True

    def find_legacy_limitless_conversation_id(self, uid, started_at):
        for cid, data in self.docs.items():
            if self.owners.get(cid) != uid:
                continue
            if data.get("source") in ("limitless",) and data.get("started_at") == started_at:
                return cid
        return None


@pytest.fixture
def store(monkeypatch):
    fake = _FakeConversationStore()
    monkeypatch.setattr(
        limitless.lifecycle_service,
        "persist_imported_conversation",
        fake.persist_imported_conversation,
    )
    monkeypatch.setattr(
        limitless,
        "find_legacy_limitless_conversation_id",
        fake.find_legacy_limitless_conversation_id,
    )
    monkeypatch.setattr(limitless.import_jobs_db, "create_import_job", MagicMock())
    monkeypatch.setattr(limitless.import_jobs_db, "update_import_job", MagicMock())
    monkeypatch.setattr(limitless.import_jobs_db, "get_import_job", MagicMock(return_value={'status': 'processing'}))
    monkeypatch.setattr(limitless, "send_notification", MagicMock())
    return fake


def _lifelog_md(first_line_text: str = "Hello team, let's begin.", start_ms: int = 1000) -> str:
    return (
        "# Morning Standup\n\n"
        "## Summary\n\n"
        "### Key point\n\n"
        f"> [1](#startMs={start_ms}&endMs={start_ms + 4000}): {first_line_text}\n"
        f"> [2](#startMs={start_ms + 4000}&endMs={start_ms + 8000}): Sounds good to me.\n"
    )


def _zip_bytes(files: dict) -> bytes:
    buf = io.BytesIO()
    with ZipFile(buf, "w") as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    return buf.getvalue()


def _run_import(tmp_path, zip_data: bytes, uid: str = UID, job_id: str = "job-1"):
    zip_path = tmp_path / "export.zip"
    zip_path.write_bytes(zip_data)
    limitless.process_limitless_import(job_id, uid, str(zip_path))


def test_conversation_id_is_deterministic_and_timestamp_keyed():
    id1 = limitless.conversation_id_for_lifelog(UID, FN_A)
    id2 = limitless.conversation_id_for_lifelog(UID, FN_A)

    assert id1 == id2, "same (uid, filename) must yield the same ID"
    uuid_lib.UUID(id1)

    retitled = "2025-10-08_07h00m25s_Completely-different-title.md"
    assert limitless.conversation_id_for_lifelog(UID, retitled) == id1

    assert limitless.conversation_id_for_lifelog(UID, FN_B) != id1
    assert limitless.conversation_id_for_lifelog("user-xyz", FN_A) != id1

    started_at, _slug = limitless.parse_lifelog_filename(FN_A)
    assert started_at is not None
    assert id1 == document_id_from_seed(f"{limitless.LIMITLESS_IMPORT_ID_NAMESPACE}:{UID}:{started_at.isoformat()}")


def test_unparseable_filename_falls_back_to_full_path():
    a = limitless.conversation_id_for_lifelog(UID, "no-timestamp.md")
    b = limitless.conversation_id_for_lifelog(UID, "no-timestamp.md")
    c = limitless.conversation_id_for_lifelog(UID, "other-no-timestamp.md")
    assert a == b and a != c
    d = limitless.conversation_id_for_lifelog(UID, "a/lifelogs/note.md")
    e = limitless.conversation_id_for_lifelog(UID, "b/lifelogs/note.md")
    assert d != e


def test_unparseable_filename_uses_recovered_startms_before_path():
    started_at = datetime.fromtimestamp(1.0, tz=timezone.utc)
    wrapped = limitless.conversation_id_for_lifelog(UID, "export/lifelogs/note.md", started_at=started_at)
    nested = limitless.conversation_id_for_lifelog(UID, "lifelogs/note.md", started_at=started_at)
    path_only = limitless.conversation_id_for_lifelog(UID, "lifelogs/note.md")

    assert wrapped == nested
    assert wrapped != path_only
    assert wrapped == document_id_from_seed(f"{limitless.LIMITLESS_IMPORT_ID_NAMESPACE}:{UID}:{started_at.isoformat()}")


def test_reimport_same_export_creates_no_duplicates(tmp_path, store):
    zip_data = _zip_bytes({f"lifelogs/{FN_A}": _lifelog_md(), f"lifelogs/{FN_B}": _lifelog_md("Design review.")})

    _run_import(tmp_path, zip_data)
    after_first = dict(store.docs)
    _run_import(tmp_path, zip_data)

    assert len(after_first) == 2, "both lifelogs imported on first run"
    assert set(store.docs) == set(after_first), "re-import must not add or change document IDs"


def test_skipped_lifelog_log_does_not_include_title_slug(tmp_path, store, caplog):
    zip_data = _zip_bytes({f"lifelogs/{FN_A}": _lifelog_md()})
    _run_import(tmp_path, zip_data)
    with caplog.at_level("INFO"):
        _run_import(tmp_path, zip_data)

    skip_logs = [rec.message for rec in caplog.records if "Skipped already-imported" in rec.message]
    assert skip_logs, "re-import should log that the lifelog was skipped"
    assert all("Morning-standup" not in message and FN_A not in message for message in skip_logs)


def test_reimport_preserves_user_edits(tmp_path, store):
    zip_data = _zip_bytes({f"lifelogs/{FN_A}": _lifelog_md()})

    _run_import(tmp_path, zip_data)
    (conv_id,) = list(store.docs)
    store.docs[conv_id]["structured"]["title"] = "My edited title"

    _run_import(tmp_path, zip_data)

    assert len(store.docs) == 1, "no duplicate created"
    assert store.docs[conv_id]["structured"]["title"] == "My edited title", "edit must survive re-import"


def test_distinct_lifelogs_get_distinct_ids(tmp_path, store):
    zip_data = _zip_bytes({f"lifelogs/{FN_A}": _lifelog_md(), f"lifelogs/{FN_B}": _lifelog_md("Design review.")})

    _run_import(tmp_path, zip_data)

    assert len(store.docs) == 2, "two different lifelogs must map to two different IDs"


def test_retitled_lifelog_is_deduped_across_imports(tmp_path, store):
    original = "2025-10-08_07h00m25s_Morning-standup.md"
    retitled = "2025-10-08_07h00m25s_Daily-sync.md"

    _run_import(tmp_path, _zip_bytes({f"lifelogs/{original}": _lifelog_md()}))
    _run_import(tmp_path, _zip_bytes({f"lifelogs/{retitled}": _lifelog_md()}))

    assert len(store.docs) == 1, "re-titled re-export of the same lifelog must dedupe"


def test_duplicate_basename_in_archive_does_not_overwrite(tmp_path, store):
    zip_data = _zip_bytes(
        {
            f"a/lifelogs/{FN_A}": _lifelog_md("FIRST occurrence content."),
            f"b/lifelogs/{FN_A}": _lifelog_md("SECOND occurrence content."),
        }
    )

    _run_import(tmp_path, zip_data)

    assert len(store.docs) == 1, "same-identity entries collapse to one conversation"
    (conv_id,) = list(store.docs)
    assert store.docs[conv_id]["transcript_segments"][0]["text"] == "FIRST occurrence content."


def test_nested_unparseable_basenames_do_not_collide(tmp_path, store):
    zip_data = _zip_bytes(
        {
            "a/lifelogs/note.md": _lifelog_md("Folder A content.", start_ms=1000),
            "b/lifelogs/note.md": _lifelog_md("Folder B content.", start_ms=2000),
        }
    )

    _run_import(tmp_path, zip_data)

    assert len(store.docs) == 2, "same basename in different folders must not be deduped when startMs differs"


def test_wrapper_prefixed_unparseable_lifelogs_share_recovered_startms(tmp_path, store):
    _run_import(tmp_path, _zip_bytes({"lifelogs/note.md": _lifelog_md()}), job_id="job-1")
    _run_import(tmp_path, _zip_bytes({"export/lifelogs/note.md": _lifelog_md()}), job_id="job-2")

    assert len(store.docs) == 1, "same recovered startMs must dedupe across ZIP wrapper prefixes"


def test_persisted_id_is_deterministic_not_random(tmp_path, store):
    _run_import(tmp_path, _zip_bytes({f"lifelogs/{FN_A}": _lifelog_md()}))

    assert list(store.docs) == [limitless.conversation_id_for_lifelog(UID, FN_A)]


def test_different_users_do_not_collide(tmp_path, store):
    _run_import(tmp_path, _zip_bytes({f"lifelogs/{FN_A}": _lifelog_md()}), uid="user-a", job_id="job-a")
    _run_import(tmp_path, _zip_bytes({f"lifelogs/{FN_A}": _lifelog_md()}), uid="user-b", job_id="job-b")

    assert len(store.docs) == 2, "same export imported by two users must not share conversation IDs"


def test_find_legacy_limitless_matches_source_and_started_at(monkeypatch):
    started_at = datetime(2025, 10, 8, 7, 0, 25, tzinfo=timezone.utc)
    captured = {}

    def fake_get_conversations(uid, **kwargs):
        captured.update(kwargs)
        captured["uid"] = uid
        return [
            {"id": "omi-row", "source": "omi", "started_at": started_at},
            {"id": "legacy-uuid", "source": "limitless", "started_at": started_at},
        ]

    monkeypatch.setattr(limitless.conversations_db, "get_conversations", fake_get_conversations)

    assert limitless.find_legacy_limitless_conversation_id(UID, started_at) == "legacy-uuid"
    assert captured["uid"] == UID
    assert captured["date_field"] == "started_at"
    assert captured["start_date"] == started_at
    assert captured["end_date"] == started_at
    assert captured["include_discarded"] is True


def test_reimport_skips_legacy_uuid_row_with_same_started_at(tmp_path, store):
    started_at, _slug = limitless.parse_lifelog_filename(FN_A)
    legacy_id = str(uuid_lib.uuid4())
    store.docs[legacy_id] = {
        "id": legacy_id,
        "started_at": started_at,
        "source": "limitless",
        "structured": {"title": "legacy import"},
    }
    store.owners[legacy_id] = UID

    _run_import(tmp_path, _zip_bytes({f"lifelogs/{FN_A}": _lifelog_md()}))

    deterministic_id = limitless.conversation_id_for_lifelog(UID, FN_A)
    assert list(store.docs) == [legacy_id]
    assert deterministic_id not in store.docs
    assert store.docs[legacy_id]["structured"]["title"] == "legacy import"


def test_legacy_row_with_different_started_at_does_not_block_import(tmp_path, store):
    other_id = str(uuid_lib.uuid4())
    store.docs[other_id] = {
        "id": other_id,
        "started_at": datetime(2000, 1, 1, tzinfo=timezone.utc),
        "source": "limitless",
    }
    store.owners[other_id] = UID

    _run_import(tmp_path, _zip_bytes({f"lifelogs/{FN_A}": _lifelog_md()}))

    assert limitless.conversation_id_for_lifelog(UID, FN_A) in store.docs
    assert len(store.docs) == 2


def test_create_error_is_isolated_per_file(tmp_path, store):
    store.fail_ids.add(limitless.conversation_id_for_lifelog(UID, FN_A))

    _run_import(tmp_path, _zip_bytes({f"lifelogs/{FN_A}": _lifelog_md(), f"lifelogs/{FN_B}": _lifelog_md("ok")}))

    assert list(store.docs) == [limitless.conversation_id_for_lifelog(UID, FN_B)]


def test_retry_after_partial_failure_creates_only_missing(tmp_path, store):
    store.fail_ids.add(limitless.conversation_id_for_lifelog(UID, FN_A))
    zip_data = _zip_bytes({f"lifelogs/{FN_A}": _lifelog_md(), f"lifelogs/{FN_B}": _lifelog_md("ok")})

    _run_import(tmp_path, zip_data)
    assert list(store.docs) == [limitless.conversation_id_for_lifelog(UID, FN_B)]

    store.fail_ids.clear()
    _run_import(tmp_path, zip_data)

    assert set(store.docs) == {
        limitless.conversation_id_for_lifelog(UID, FN_A),
        limitless.conversation_id_for_lifelog(UID, FN_B),
    }
    assert store.docs[limitless.conversation_id_for_lifelog(UID, FN_B)]["transcript_segments"][0]["text"] == "ok"
