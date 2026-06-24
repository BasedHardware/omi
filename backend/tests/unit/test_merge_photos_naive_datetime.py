"""Tests for ``utils.conversations.merge_conversations._collect_all_photos``.

Regression coverage for a ``TypeError: can't compare offset-naive and
offset-aware datetimes`` crash while merging conversations. ``_collect_all_photos``
sorts the merged photo list by ``created_at`` with a naive ``datetime.min``
fallback for photos missing the field. Firestore photo ``created_at`` values
are tz-aware, so as soon as one photo lacks ``created_at`` (uses the naive
fallback) and another has a tz-aware value, the sort comparison raises and the
entire merge fails for that user (caught by ``perform_merge_async``'s outer
``except`` -> merge silently aborts).

The fix coerces every sort key to a uniform tz-aware UTC ``datetime``
(``datetime.min.replace(tzinfo=timezone.utc)`` sentinel for the missing case,
plus ISO-string coercion), mirroring the ``_coerce_dt`` pattern already used
for conversation-level timestamps.

Stub harness mirrors ``test_merge_validation.py`` (same module, same heavy
import graph that initialises Firestore / GCS at module load).
"""

import os
import sys
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _ensure_stub(name):
    existing = sys.modules.get(name)
    if existing is not None and getattr(existing, "__file__", None):
        return existing
    if existing is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return sys.modules[name]


# Stub the database modules that merge_conversations imports — these init
# Firestore at module load. utils.other.storage is also pre-stubbed because it
# pulls google.cloud.storage + opuslib at import time.
_ensure_stub("database")
sys.modules["database"].__path__ = getattr(sys.modules["database"], "__path__", [])
for _sub in ["_client", "conversations", "vector_db", "redis_db", "users"]:
    _ensure_stub(f"database.{_sub}")
sys.modules["database._client"].db = MagicMock()
sys.modules["database.conversations"].get_conversation = MagicMock(return_value=None)
sys.modules["database.conversations"].get_conversation_photos = MagicMock(return_value=[])
sys.modules["database.vector_db"].delete_vector = MagicMock()

# Do NOT stub `utils` or `utils.other` — they are real packages on disk.
import utils  # noqa: F401, E402
import utils.other  # noqa: F401, E402

_fake_storage = types.ModuleType("utils.other.storage")
for _name in [
    "delete_conversation_audio_files",
    "list_audio_chunks",
    "storage_client",
    "private_cloud_sync_bucket",
    "_get_extension_for_path",
]:
    setattr(_fake_storage, _name, MagicMock())
sys.modules["utils.other.storage"] = _fake_storage

# Stub the models.* chain referenced by top-level imports / perform_merge_async.
_fake_models = types.ModuleType("models")
_fake_models.__path__ = []
sys.modules["models"] = _fake_models
for _modname, _attrs in [
    ("models.audio_file", ["AudioFile"]),
    ("models.conversation", ["Conversation"]),
    ("models.conversation_enums", ["ConversationStatus"]),
    ("models.structured", ["Structured"]),
]:
    _mod = types.ModuleType(_modname)
    for _attr in _attrs:
        setattr(_mod, _attr, MagicMock())
    sys.modules[_modname] = _mod

# Drop any earlier empty stub of the module so the real file is re-loaded.
for _modname in ["utils.conversations", "utils.conversations.merge_conversations"]:
    _existing = sys.modules.get(_modname)
    if _existing is not None and not getattr(_existing, "__file__", None):
        del sys.modules[_modname]

import database.conversations as conversations_db  # noqa: E402
from utils.conversations import merge_conversations as mod  # noqa: E402


def _photo(photo_id, created_at=...):
    p = {"id": photo_id, "data": f"img-{photo_id}"}
    if created_at is not ...:
        p["created_at"] = created_at
    return p


class TestCollectAllPhotosSortKey:
    def test_missing_created_at_with_tz_aware_does_not_raise(self):
        # The regression: one photo has no created_at (naive datetime.min
        # fallback pre-fix) while others are tz-aware -> sort comparison
        # raised TypeError and aborted the whole merge.
        photos = [
            _photo("p_aware", datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)),
            _photo("p_missing"),  # no created_at -> fallback sentinel
            _photo("p_aware2", datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc)),
        ]
        conversations_db.get_conversation_photos = MagicMock(return_value=photos)

        # Must not raise TypeError.
        result = mod._collect_all_photos("uid-1", [{"id": "c1"}])

        ids = [p["id"] for p in result]
        assert set(ids) == {"p_aware", "p_missing", "p_aware2"}
        # Missing-created_at photo sorts first (epoch sentinel), then the
        # tz-aware ones in ascending order.
        assert ids[0] == "p_missing"
        assert ids.index("p_aware2") < ids.index("p_aware")

    def test_string_created_at_coerced_and_sorted(self):
        # Older write paths persisted created_at as an ISO string; mixing a
        # string with tz-aware datetimes must also not raise and must order
        # correctly.
        photos = [
            _photo("p_str_late", "2026-05-30T15:00:00Z"),
            _photo("p_dt_early", datetime(2026, 5, 30, 9, 0, tzinfo=timezone.utc)),
        ]
        conversations_db.get_conversation_photos = MagicMock(return_value=photos)

        result = mod._collect_all_photos("uid-1", [{"id": "c1"}])
        ids = [p["id"] for p in result]
        assert ids == ["p_dt_early", "p_str_late"]

    def test_all_tz_aware_sorted_ascending(self):
        photos = [
            _photo("p3", datetime(2026, 5, 30, 14, 0, tzinfo=timezone.utc)),
            _photo("p1", datetime(2026, 5, 30, 8, 0, tzinfo=timezone.utc)),
            _photo("p2", datetime(2026, 5, 30, 11, 0, tzinfo=timezone.utc)),
        ]
        conversations_db.get_conversation_photos = MagicMock(return_value=photos)

        result = mod._collect_all_photos("uid-1", [{"id": "c1"}])
        assert [p["id"] for p in result] == ["p1", "p2", "p3"]

    def test_dedup_across_conversations(self):
        # Sanity: the dedup-by-id behaviour still holds with the new key.
        def _photos(uid, conv_id):
            if conv_id == "c1":
                return [_photo("dup", datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc))]
            return [
                _photo("dup", datetime(2026, 5, 30, 9, 0, tzinfo=timezone.utc)),
                _photo("only2"),
            ]

        conversations_db.get_conversation_photos = MagicMock(side_effect=_photos)
        result = mod._collect_all_photos("uid-1", [{"id": "c1"}, {"id": "c2"}])
        ids = [p["id"] for p in result]
        assert ids.count("dup") == 1
        assert "only2" in ids
