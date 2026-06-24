"""Regression test for populate_speaker_names KeyError on people docs missing 'name'.

get_people_by_ids backfills 'id' but not 'name' (legacy docs may lack it), so the
people_map comprehension {p['id']: p['name'] ...} raised KeyError for such a doc and
took down the whole list/render path. The fix uses p.get('name') or '' so a missing
name degrades to a blank speaker name instead of crashing.
"""

import os
import sys
import types
from unittest.mock import patch, MagicMock

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


# Stub database chain so render.py can import at module level without Firestore
_ensure_stub("database")
sys.modules["database"].__path__ = getattr(sys.modules["database"], "__path__", [])
for _sub in ["_client", "redis_db", "users", "folders"]:
    _ensure_stub(f"database.{_sub}")
sys.modules["database._client"].db = MagicMock()
sys.modules["database.users"].get_user_profile = MagicMock(return_value={"name": "TestUser"})
sys.modules["database.users"].get_people_by_ids = MagicMock(return_value=[])
sys.modules["database.folders"].get_folders = MagicMock(return_value=[])

# Stub-cleanup preamble: force-reimport real modules if earlier test files
# left empty ModuleType stubs in sys.modules.
for _mod in [
    "models",
    "models.conversation",
    "models.conversation_enums",
    "models.structured",
    "utils",
    "utils.conversations",
    "utils.conversations.render",
]:
    _existing = sys.modules.get(_mod)
    if _existing is not None and not getattr(_existing, "__file__", None):
        del sys.modules[_mod]

from utils.conversations import render


class TestPopulateSpeakerNamesMissingName:
    def test_person_doc_missing_name_does_not_raise(self):
        """A person doc with an 'id' but no 'name' must not KeyError; blank name instead."""
        conversations = [
            {
                "transcript_segments": [
                    {"person_id": "a", "speaker_id": 1},
                    {"person_id": "b", "speaker_id": 2},
                ]
            }
        ]
        # 'a' has a name, 'b' (legacy doc) is missing it.
        people = [{"id": "a", "name": "Alice"}, {"id": "b"}]

        with patch.object(render.users_db, "get_user_profile", return_value={"name": "Zach"}), patch.object(
            render.users_db, "get_people_by_ids", return_value=people
        ):
            # Before the fix this raises KeyError('name').
            render.populate_speaker_names("uid-1", conversations)

        segs = conversations[0]["transcript_segments"]
        assert segs[0]["speaker_name"] == "Alice"
        # Missing-name person degrades to an empty speaker name, not a crash.
        assert segs[1]["speaker_name"] == ""

    def test_present_names_still_assigned(self):
        """Sanity: when every person has a name, mapping is unchanged by the fix."""
        conversations = [{"transcript_segments": [{"person_id": "p1", "speaker_id": 0}]}]
        people = [{"id": "p1", "name": "Bob"}]

        with patch.object(render.users_db, "get_user_profile", return_value={"name": "Zach"}), patch.object(
            render.users_db, "get_people_by_ids", return_value=people
        ):
            render.populate_speaker_names("uid-1", conversations)

        assert conversations[0]["transcript_segments"][0]["speaker_name"] == "Bob"
