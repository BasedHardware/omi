"""Hermetic unit tests for Limitless import macOS metadata exclusion.

Ensures that __MACOSX/ resource forks, ._<name> AppleDouble metadata files,
.DS_Store, and directory entries are skipped during Limitless ZIP import,
preventing false-positive import failures (fixes #21707).
"""

import io
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from zipfile import ZipFile

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _pkg(name: str):
    mod = sys.modules.get(name)
    if mod is None or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    return mod


def _mod(name: str):
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return mod


for p in ["google", "google.api_core", "google.cloud", "models", "database"]:
    _pkg(p)

_utils = _mod("utils")
_utils.__path__ = [str(BACKEND_DIR / "utils")]

_exc = _mod("google.api_core.exceptions")
for exc_name in ["Aborted", "NotFound", "InvalidArgument", "AlreadyExists", "Conflict"]:
    if not hasattr(_exc, exc_name):
        setattr(_exc, exc_name, type(exc_name, (Exception,), {}))
setattr(sys.modules["google.api_core"], "exceptions", _exc)

_fs = _mod("google.cloud.firestore")
for attr in ["Query", "FieldFilter", "Client", "transactional"]:
    if not hasattr(_fs, attr):
        setattr(_fs, attr, MagicMock())
setattr(sys.modules["google.cloud"], "firestore", _fs)

_fs_v1 = _mod("google.cloud.firestore_v1")
for attr in ["Query", "FieldFilter"]:
    if not hasattr(_fs_v1, attr):
        setattr(_fs_v1, attr, MagicMock())
setattr(sys.modules["google.cloud"], "firestore_v1", _fs_v1)

_models_conv = _mod("models.conversation")
_models_conv.AppResult = MagicMock()
class Conversation:
    def __init__(self, **kwargs):
        self._data = dict(kwargs)
    def model_dump(self):
        return dict(self._data)
_models_conv.Conversation = Conversation

_models_enums = _mod("models.conversation_enums")
class CategoryEnum:
    other = "other"
class ConversationSource:
    limitless = "limitless"
class ConversationStatus:
    completed = "completed"
_models_enums.CategoryEnum = CategoryEnum
_models_enums.ConversationSource = ConversationSource
_models_enums.ConversationStatus = ConversationStatus

_models_struct = _mod("models.structured")
_models_struct.Structured = MagicMock()

_models_ij = _mod("models.import_job")
class ImportJobStatus:
    processing = MagicMock(value="processing")
    completed = MagicMock(value="completed")
    failed = MagicMock(value="failed")
    cancelled = MagicMock(value="cancelled")
_models_ij.ImportJobStatus = ImportJobStatus
_models_ij.ImportJob = MagicMock()
_models_ij.ImportSourceType = MagicMock()

_models_ts = _mod("models.transcript_segment")
_models_ts.TranscriptSegment = MagicMock()

_notif = _mod("utils.notification_dispatch")
_notif.NotificationDispatchStatus = MagicMock()
_notif.NotificationIntent = MagicMock()
_notif.NotificationKind = MagicMock()
_notif.dispatch_notification = MagicMock()

_life = _mod("utils.conversations.lifecycle")
_life.persist_imported_conversation = MagicMock()
_proj = _mod("utils.conversations.projection_payload")
_proj.omit_null_processing_state = lambda x: x

_doc_ids = _mod("database.document_ids")
_doc_ids.document_id_from_seed = lambda seed: f"seed_{seed}"

_conv_db = _mod("database.conversations")
_ij_db = _mod("database.import_jobs")
_ij_db.update_import_job = MagicMock()

_psc = _mod("database.people_stats_cache")
_psc.invalidate_people_stats_cache = MagicMock()

from utils.imports import limitless


class TestLimitlessMacOSXMetadata(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.uid = "test-user-123"
        self.job_id = "test-job-456"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_is_lifelog_path(self):
        # Valid lifelog markdown files
        self.assertTrue(limitless.is_lifelog_path("lifelogs/2025-10-08_07h00m25s_Title.md"))
        self.assertTrue(limitless.is_lifelog_path("export_folder/lifelogs/2025-10-08_07h00m25s_Title.md"))
        self.assertTrue(limitless.is_lifelog_path("lifelogs_export/2025-10-08_07h00m25s_Title.md"))

        # macOS __MACOSX / AppleDouble metadata files (Issue #21707)
        self.assertFalse(limitless.is_lifelog_path("__MACOSX/lifelogs/._2025-10-08_07h00m25s_Title.md"))
        self.assertFalse(limitless.is_lifelog_path("export/__MACOSX/lifelogs/._2025-10-08_07h00m25s_Title.md"))
        self.assertFalse(limitless.is_lifelog_path("lifelogs/._2025-10-08_07h00m25s_Title.md"))
        self.assertFalse(limitless.is_lifelog_path("lifelogs/._notes.md"))

        # Hidden dotfiles, directories, non-markdown
        self.assertFalse(limitless.is_lifelog_path("lifelogs/.DS_Store"))
        self.assertFalse(limitless.is_lifelog_path("lifelogs/.hidden.md"))
        self.assertFalse(limitless.is_lifelog_path("lifelogs/"))
        self.assertFalse(limitless.is_lifelog_path("__MACOSX/"))
        self.assertFalse(limitless.is_lifelog_path("lifelogs/info.txt"))
        self.assertFalse(limitless.is_lifelog_path(""))

    def test_process_limitless_import_skips_macosx_metadata(self):
        fn = "2025-10-08_07h00m25s_Morning-Standup.md"
        valid_md = (
            "# Morning Standup\n\n"
            "## Summary\n\n"
            "> [1](#startMs=1000&endMs=5000): Good morning everyone.\n"
        )
        files = {
            f"lifelogs/{fn}": valid_md.encode("utf-8"),
            f"__MACOSX/lifelogs/._" + fn: b"\x00\x05\x16\x07AppleDoubleBinaryBytes",
            f"lifelogs/._" + fn: b"\x00\x05\x16\x07AppleDoubleBinaryBytes",
            "lifelogs/.DS_Store": b"\x00\x00\x00\x01Bud1",
        }

        zip_path = self.temp_dir / "export.zip"
        with ZipFile(zip_path, "w") as zf:
            for path, data in files.items():
                zf.writestr(path, data)

        saved_docs = {}
        def mock_persist(uid, data):
            saved_docs[data["id"]] = data
            return True

        job_updates = []
        def mock_update(job_id, fields):
            job_updates.append(fields)

        orig_persist = getattr(limitless.lifecycle_service, "persist_imported_conversation", None)
        orig_find = getattr(limitless, "find_legacy_limitless_conversation_id", None)
        orig_update = getattr(limitless.import_jobs_db, "update_import_job", None)
        orig_get = getattr(limitless.import_jobs_db, "get_import_job", None)
        orig_notify = getattr(limitless, "dispatch_notification", None)

        try:
            limitless.lifecycle_service.persist_imported_conversation = mock_persist
            limitless.find_legacy_limitless_conversation_id = lambda u, s: None
            limitless.import_jobs_db.update_import_job = mock_update
            limitless.import_jobs_db.get_import_job = lambda jid: {"status": "processing"}
            limitless.dispatch_notification = MagicMock()

            limitless.process_limitless_import(self.job_id, self.uid, str(zip_path))

            # Only 1 file should be detected and counted
            total_files_updates = [u["total_files"] for u in job_updates if "total_files" in u]
            self.assertEqual(total_files_updates, [1])

            # The document should match the valid lifelog
            expected_cid = limitless.conversation_id_for_lifelog(self.uid, fn)
            self.assertEqual(list(saved_docs.keys()), [expected_cid])

            # Completed status should have no error
            completed_updates = [u for u in job_updates if u.get("status") == "completed"]
            self.assertEqual(len(completed_updates), 1)
            self.assertIsNone(completed_updates[0].get("error"))
        finally:
            if orig_persist:
                limitless.lifecycle_service.persist_imported_conversation = orig_persist
            if orig_find:
                limitless.find_legacy_limitless_conversation_id = orig_find
            if orig_update:
                limitless.import_jobs_db.update_import_job = orig_update
            if orig_get:
                limitless.import_jobs_db.get_import_job = orig_get
            if orig_notify:
                limitless.dispatch_notification = orig_notify


if __name__ == "__main__":
    unittest.main()
