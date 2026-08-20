"""Tests for Limitless import idempotency (deterministic conversation IDs).

Re-importing the same Limitless export must not create duplicate conversations,
and must not clobber edits a user made to a previously-imported conversation.
This is achieved by deriving each conversation's Firestore document ID
deterministically from (uid, lifelog start-time) and skipping lifelogs that are
already stored ("first import wins").
"""

import io
import uuid as uuid_lib
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
        self.fail_ids = set()

    def reset(self):
        self.docs = {}
        self.fail_ids = set()

    def persist_imported_conversation(self, uid, data):
        del uid
        cid = data["id"]
        if cid in self.fail_ids:
            raise RuntimeError("simulated firestore error")
        if cid in self.docs:
            return False
        self.docs[cid] = data
        return True


@pytest.fixture
def store(monkeypatch):
    fake = _FakeConversationStore()
    monkeypatch.setattr(
        limitless.lifecycle_service,
        "persist_imported_conversation",
        fake.persist_imported_conversation,
    )
    monkeypatch.setattr(limitless.import_jobs_db, "create_import_job", MagicMock())
    monkeypatch.setattr(limitless.import_jobs_db, "update_import_job", MagicMock())
    monkeypatch.setattr(limitless.import_jobs_db, "get_import_job", MagicMock(return_value={'status': 'processing'}))
    monkeypatch.setattr(limitless, "send_notification", MagicMock())
    return fake


def _lifelog_md(first_line_text: str = "Hello team, let's begin.") -> str:
    return (
        "# Morning Standup\n\n"
        "## Summary\n\n"
        "### Key point\n\n"
        f"> [1](#startMs=1000&endMs=5000): {first_line_text}\n"
        "> [2](#startMs=5000&endMs=9000): Sounds good to me.\n"
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


def test_reimport_same_export_creates_no_duplicates(tmp_path, store):
    zip_data = _zip_bytes({f"lifelogs/{FN_A}": _lifelog_md(), f"lifelogs/{FN_B}": _lifelog_md("Design review.")})

    _run_import(tmp_path, zip_data)
    after_first = dict(store.docs)
    _run_import(tmp_path, zip_data)

    assert len(after_first) == 2, "both lifelogs imported on first run"
    assert set(store.docs) == set(after_first), "re-import must not add or change document IDs"


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
            "a/lifelogs/note.md": _lifelog_md("Folder A content."),
            "b/lifelogs/note.md": _lifelog_md("Folder B content."),
        }
    )

    _run_import(tmp_path, zip_data)

    assert len(store.docs) == 2, "same basename in different folders must not be deduped when unparseable"


def test_persisted_id_is_deterministic_not_random(tmp_path, store):
    _run_import(tmp_path, _zip_bytes({f"lifelogs/{FN_A}": _lifelog_md()}))

    assert list(store.docs) == [limitless.conversation_id_for_lifelog(UID, FN_A)]


def test_different_users_do_not_collide(tmp_path, store):
    _run_import(tmp_path, _zip_bytes({f"lifelogs/{FN_A}": _lifelog_md()}), uid="user-a", job_id="job-a")
    _run_import(tmp_path, _zip_bytes({f"lifelogs/{FN_A}": _lifelog_md()}), uid="user-b", job_id="job-b")

    assert len(store.docs) == 2, "same export imported by two users must not share conversation IDs"


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
