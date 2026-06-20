"""Tests for Limitless import idempotency (deterministic conversation IDs).

Re-importing the same Limitless export must not create duplicate conversations,
and must not clobber edits a user made to a previously-imported conversation.
This is achieved by deriving each conversation's Firestore document ID
deterministically from (uid, lifelog start-time) and skipping lifelogs that are
already stored ("first import wins").

``database.*`` and ``utils.notifications`` are stubbed because they initialise
Firestore / FCM at import time. The Pydantic models are imported for real (no
external init), so this exercises the real ``process_limitless_import``. A small
in-memory store stands in for Firestore's atomic create-if-absent
(``document.create()``), so the tests assert real persistence behaviour (document
count, edit preservation), not just ID generation. True concurrency atomicity is a
property of Firestore ``create()`` itself and is not unit-tested here.
"""

import hashlib
import io
import os
import sys
import types
import uuid as uuid_lib
from zipfile import ZipFile

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from unittest.mock import MagicMock


def _stub_module(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# --- Pre-mock heavy deps (Firestore / FCM) before importing the module under test ---
if "database" not in sys.modules:
    _database_mod = _stub_module("database")
    _database_mod.__path__ = []
else:
    _database_mod = sys.modules["database"]

for _sub in ["_client", "import_jobs", "conversations"]:
    _full = f"database.{_sub}"
    if _full not in sys.modules:
        _m = _stub_module(_full)
        setattr(_database_mod, _sub, _m)


def _faithful_document_id_from_seed(seed: str) -> str:
    # Mirrors database._client.document_id_from_seed (kept in sync intentionally):
    # SHA-256 of the seed, first 16 bytes reinterpreted as a UUID. Deterministic.
    # NOTE: copied rather than imported because the real module initialises Firestore
    # at import time. A follow-up could move the primitive to a Firestore-free module
    # so tests import it directly and eliminate any drift risk.
    seed_hash = hashlib.sha256(seed.encode("utf-8")).digest()
    return str(uuid_lib.UUID(bytes=seed_hash[:16], version=4))


class _FakeConversationStore:
    """In-memory stand-in for Firestore's atomic create-if-absent (document.create())."""

    def __init__(self):
        self.docs = {}
        self.fail_ids = set()  # ids whose create() should raise (resilience testing)

    def reset(self):
        self.docs = {}
        self.fail_ids = set()

    def create_conversation_if_absent(self, uid, data):
        cid = data["id"]
        if cid in self.fail_ids:
            raise RuntimeError("simulated firestore error")
        if cid in self.docs:
            return False  # already exists -> skipped (mirrors AlreadyExists -> False)
        self.docs[cid] = data
        return True


_store = _FakeConversationStore()

sys.modules["database._client"].db = MagicMock()
sys.modules["database._client"].document_id_from_seed = _faithful_document_id_from_seed
sys.modules["database.conversations"].create_conversation_if_absent = _store.create_conversation_if_absent
sys.modules["database.import_jobs"].create_import_job = MagicMock()
sys.modules["database.import_jobs"].update_import_job = MagicMock()

# utils.notifications.send_notification pulls FCM/Firebase at import — stub just it.
# (utils / utils.imports stay real so the real limitless module is importable.)
sys.modules["utils.notifications"] = MagicMock()

import utils.imports.limitless as limitless  # noqa: E402

UID = "user-abc"
FN_A = "2025-10-08_07h00m25s_Morning-standup.md"
FN_B = "2025-10-09_09h15m00s_Design-review.md"


def _lifelog_md(first_line_text: str = "Hello team, let's begin.") -> str:
    return (
        "# Morning Standup\n\n"
        "## Summary\n\n"
        "### Key point\n\n"
        f"> [1](#startMs=1000&endMs=5000): {first_line_text}\n"
        "> [2](#startMs=5000&endMs=9000): Sounds good to me.\n"
    )


def _zip_bytes(files: dict) -> bytes:
    """files: {in_zip_path: markdown_content} -> ZIP bytes."""
    buf = io.BytesIO()
    with ZipFile(buf, "w") as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    return buf.getvalue()


def _run_import(tmp_path, zip_data: bytes, uid: str = UID, job_id: str = "job-1"):
    """Write the zip to disk and run the (real) import worker."""
    zip_path = tmp_path / "export.zip"
    zip_path.write_bytes(zip_data)
    limitless.process_limitless_import(job_id, uid, str(zip_path))


# --------------------------------------------------------------------------- #
# Helper-level behaviour
# --------------------------------------------------------------------------- #


def test_conversation_id_is_deterministic_and_timestamp_keyed():
    id1 = limitless.conversation_id_for_lifelog(UID, FN_A)
    id2 = limitless.conversation_id_for_lifelog(UID, FN_A)

    assert id1 == id2, "same (uid, filename) must yield the same ID"
    uuid_lib.UUID(id1)  # must be a valid UUID string

    # Same start-time, different title slug -> same ID (survives Limitless re-titling).
    retitled = "2025-10-08_07h00m25s_Completely-different-title.md"
    assert limitless.conversation_id_for_lifelog(UID, retitled) == id1

    # Different start-time -> different ID.
    assert limitless.conversation_id_for_lifelog(UID, FN_B) != id1
    # Different user -> different ID.
    assert limitless.conversation_id_for_lifelog("user-xyz", FN_A) != id1


def test_unparseable_filename_falls_back_to_full_name():
    a = limitless.conversation_id_for_lifelog(UID, "no-timestamp.md")
    b = limitless.conversation_id_for_lifelog(UID, "no-timestamp.md")
    c = limitless.conversation_id_for_lifelog(UID, "other-no-timestamp.md")
    assert a == b and a != c


# --------------------------------------------------------------------------- #
# End-to-end idempotency through process_limitless_import
# --------------------------------------------------------------------------- #


def test_reimport_same_export_creates_no_duplicates(tmp_path):
    _store.reset()
    zip_data = _zip_bytes({f"lifelogs/{FN_A}": _lifelog_md(), f"lifelogs/{FN_B}": _lifelog_md("Design review.")})

    _run_import(tmp_path, zip_data)
    after_first = dict(_store.docs)
    _run_import(tmp_path, zip_data)

    assert len(after_first) == 2, "both lifelogs imported on first run"
    assert set(_store.docs) == set(after_first), "re-import must not add or change document IDs"


def test_reimport_preserves_user_edits(tmp_path):
    """A re-import must skip an already-imported conversation, not overwrite edits."""
    _store.reset()
    zip_data = _zip_bytes({f"lifelogs/{FN_A}": _lifelog_md()})

    _run_import(tmp_path, zip_data)
    (conv_id,) = list(_store.docs)
    # Simulate the user editing the imported conversation inside Omi.
    _store.docs[conv_id]["structured"]["title"] = "My edited title"

    _run_import(tmp_path, zip_data)  # same export again

    assert len(_store.docs) == 1, "no duplicate created"
    assert _store.docs[conv_id]["structured"]["title"] == "My edited title", "edit must survive re-import"


def test_distinct_lifelogs_get_distinct_ids(tmp_path):
    _store.reset()
    zip_data = _zip_bytes({f"lifelogs/{FN_A}": _lifelog_md(), f"lifelogs/{FN_B}": _lifelog_md("Design review.")})

    _run_import(tmp_path, zip_data)

    assert len(_store.docs) == 2, "two different lifelogs must map to two different IDs"


def test_retitled_lifelog_is_deduped_across_imports(tmp_path):
    """Same lifelog re-exported with a different title slug must not duplicate."""
    _store.reset()
    original = "2025-10-08_07h00m25s_Morning-standup.md"
    retitled = "2025-10-08_07h00m25s_Daily-sync.md"

    _run_import(tmp_path, _zip_bytes({f"lifelogs/{original}": _lifelog_md()}))
    _run_import(tmp_path, _zip_bytes({f"lifelogs/{retitled}": _lifelog_md()}))

    assert len(_store.docs) == 1, "re-titled re-export of the same lifelog must dedupe"


def test_duplicate_basename_in_archive_does_not_overwrite(tmp_path):
    """Two entries that resolve to the same ID within one archive: first wins, no clobber."""
    _store.reset()
    zip_data = _zip_bytes(
        {
            f"a/lifelogs/{FN_A}": _lifelog_md("FIRST occurrence content."),
            f"b/lifelogs/{FN_A}": _lifelog_md("SECOND occurrence content."),
        }
    )

    _run_import(tmp_path, zip_data)

    assert len(_store.docs) == 1, "same-identity entries collapse to one conversation"
    (conv_id,) = list(_store.docs)
    assert _store.docs[conv_id]["transcript_segments"][0]["text"] == "FIRST occurrence content."


def test_persisted_id_is_deterministic_not_random(tmp_path):
    _store.reset()
    _run_import(tmp_path, _zip_bytes({f"lifelogs/{FN_A}": _lifelog_md()}))

    assert list(_store.docs) == [limitless.conversation_id_for_lifelog(UID, FN_A)]


def test_different_users_do_not_collide(tmp_path):
    _store.reset()
    _run_import(tmp_path, _zip_bytes({f"lifelogs/{FN_A}": _lifelog_md()}), uid="user-a", job_id="job-a")
    _run_import(tmp_path, _zip_bytes({f"lifelogs/{FN_A}": _lifelog_md()}), uid="user-b", job_id="job-b")

    assert len(_store.docs) == 2, "same export imported by two users must not share conversation IDs"


def test_create_error_is_isolated_per_file(tmp_path):
    """A create failure on one lifelog must not abort the rest of the import."""
    _store.reset()
    _store.fail_ids.add(limitless.conversation_id_for_lifelog(UID, FN_A))

    _run_import(tmp_path, _zip_bytes({f"lifelogs/{FN_A}": _lifelog_md(), f"lifelogs/{FN_B}": _lifelog_md("ok")}))

    # FN_A's create raised and was caught per-file; FN_B still imported.
    assert list(_store.docs) == [limitless.conversation_id_for_lifelog(UID, FN_B)]
