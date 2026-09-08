"""Folder-name and speaker-name enrichment for conversations.

utils.conversations.render binds ``database.folders`` and ``database.users`` at import
(``import database.folders as folders_db``), and those database modules are not yet
import-pure (they pull google.cloud.firestore, database._client.db, etc.). So the fakes
must be active before render is exec'd. This is the sanctioned Tier-2 "fake must
precede import" case: see backend/docs/test_isolation.md and
testing/import_isolation.load_module_fresh.
"""

import os
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


# Shared controllable mocks — pure to construct at module scope; wired into the fakes
# by the ``render`` fixture below.
_mock_get_folders = MagicMock(return_value=[])
_mock_get_folder = MagicMock(return_value=None)
_mock_get_user_profile = MagicMock(return_value={"name": "TestUser"})
_mock_get_people_by_ids = MagicMock(return_value=[])


@pytest.fixture(scope="module")
def render():
    """Load a fresh utils.conversations.render against stubbed database.folders/users."""
    folders_mod = ModuleType("database.folders")
    folders_mod.get_folders = _mock_get_folders
    folders_mod.get_folder = _mock_get_folder

    users_mod = ModuleType("database.users")
    users_mod.get_user_profile = _mock_get_user_profile
    users_mod.get_people_by_ids = _mock_get_people_by_ids

    fakes = {
        "database.folders": folders_mod,
        "database.users": users_mod,
    }
    with stub_modules(fakes):
        module = load_module_fresh(
            "utils.conversations.render",
            os.path.join(BACKEND_DIR, "utils", "conversations", "render.py"),
        )
        yield module


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAddFolderNamesToConversations:
    """Tests for populate_folder_names in developer API."""

    def setup_method(self):
        _mock_get_folders.reset_mock()

    def test_conversations_with_folder_id_get_folder_name(self, render):
        _mock_get_folders.return_value = [
            {'id': 'folder1', 'name': 'Work'},
            {'id': 'folder2', 'name': 'Personal'},
        ]
        conversations = [
            {'id': 'conv1', 'folder_id': 'folder1'},
            {'id': 'conv2', 'folder_id': 'folder2'},
        ]
        render.populate_folder_names('uid1', conversations)

        assert conversations[0]['folder_name'] == 'Work'
        assert conversations[1]['folder_name'] == 'Personal'
        _mock_get_folders.assert_called_once_with('uid1')

    def test_conversations_without_folder_id_get_none(self, render):
        conversations = [
            {'id': 'conv1', 'folder_id': None},
            {'id': 'conv2'},
        ]
        render.populate_folder_names('uid1', conversations)

        assert conversations[0]['folder_name'] is None
        assert conversations[1]['folder_name'] is None
        _mock_get_folders.assert_not_called()

    def test_folder_id_not_found_in_db_returns_none(self, render):
        _mock_get_folders.return_value = [
            {'id': 'folder1', 'name': 'Work'},
        ]
        conversations = [
            {'id': 'conv1', 'folder_id': 'deleted_folder'},
        ]
        render.populate_folder_names('uid1', conversations)

        assert conversations[0]['folder_name'] is None

    def test_mixed_conversations_with_and_without_folder_id(self, render):
        _mock_get_folders.return_value = [
            {'id': 'folder1', 'name': 'Work'},
        ]
        conversations = [
            {'id': 'conv1', 'folder_id': 'folder1'},
            {'id': 'conv2', 'folder_id': None},
            {'id': 'conv3'},
        ]
        render.populate_folder_names('uid1', conversations)

        assert conversations[0]['folder_name'] == 'Work'
        assert conversations[1]['folder_name'] is None
        assert conversations[2]['folder_name'] is None

    def test_empty_conversations_list(self, render):
        conversations = []
        render.populate_folder_names('uid1', conversations)

        assert conversations == []
        _mock_get_folders.assert_not_called()

    def test_batch_fetches_all_folders_once(self, render):
        """Verify N+1 avoidance: get_folders is called only once regardless of conversation count."""
        _mock_get_folders.return_value = [
            {'id': 'f1', 'name': 'Work'},
            {'id': 'f2', 'name': 'Personal'},
        ]
        conversations = [
            {'id': 'conv1', 'folder_id': 'f1'},
            {'id': 'conv2', 'folder_id': 'f2'},
            {'id': 'conv3', 'folder_id': 'f1'},
        ]
        render.populate_folder_names('uid1', conversations)

        assert _mock_get_folders.call_count == 1


class TestAddFolderNamesWebhookPayload:
    """Tests for populate_folder_names with single-item webhook payloads."""

    def setup_method(self):
        _mock_get_folders.reset_mock()

    def test_payload_with_folder_id_gets_folder_name(self, render):
        _mock_get_folders.return_value = [{'id': 'folder1', 'name': 'Work'}]
        payload = {'folder_id': 'folder1'}

        render.populate_folder_names('uid1', [payload])

        assert payload['folder_name'] == 'Work'
        _mock_get_folders.assert_called_once_with('uid1')

    def test_payload_without_folder_id_gets_none(self, render):
        payload = {'folder_id': None}

        render.populate_folder_names('uid1', [payload])

        assert payload['folder_name'] is None
        _mock_get_folders.assert_not_called()

    def test_payload_missing_folder_id_key_gets_none(self, render):
        payload = {}

        render.populate_folder_names('uid1', [payload])

        assert payload['folder_name'] is None
        _mock_get_folders.assert_not_called()

    def test_folder_not_found_in_db_returns_none(self, render):
        _mock_get_folders.return_value = []
        payload = {'folder_id': 'deleted_folder'}

        render.populate_folder_names('uid1', [payload])

        assert payload['folder_name'] is None


# ---------------------------------------------------------------------------
# Speaker name enrichment tests
# ---------------------------------------------------------------------------


class TestAddSpeakerNames:
    """Tests for populate_speaker_names enrichment."""

    def setup_method(self):
        _mock_get_user_profile.reset_mock()
        _mock_get_people_by_ids.reset_mock()
        _mock_get_user_profile.return_value = {"name": "TestUser"}
        _mock_get_people_by_ids.return_value = []

    def test_user_segments_get_user_name(self, render):
        conversations = [{'transcript_segments': [{'text': 'hi', 'is_user': True, 'speaker_id': 0}]}]
        render.populate_speaker_names('uid1', conversations)
        assert conversations[0]['transcript_segments'][0]['speaker_name'] == 'TestUser'

    def test_known_person_id_gets_person_name(self, render):
        _mock_get_people_by_ids.return_value = [{'id': 'p1', 'name': 'Alice'}]
        conversations = [
            {'transcript_segments': [{'text': 'hi', 'is_user': False, 'person_id': 'p1', 'speaker_id': 1}]}
        ]
        render.populate_speaker_names('uid1', conversations)
        assert conversations[0]['transcript_segments'][0]['speaker_name'] == 'Alice'

    def test_unknown_person_id_falls_back_to_speaker_id(self, render):
        _mock_get_people_by_ids.return_value = []
        conversations = [
            {'transcript_segments': [{'text': 'hi', 'is_user': False, 'person_id': 'unknown_p', 'speaker_id': 3}]}
        ]
        render.populate_speaker_names('uid1', conversations)
        assert conversations[0]['transcript_segments'][0]['speaker_name'] == 'Speaker 3'

    def test_no_person_id_no_is_user_falls_back_to_speaker_id(self, render):
        conversations = [{'transcript_segments': [{'text': 'hi', 'speaker_id': 2}]}]
        render.populate_speaker_names('uid1', conversations)
        assert conversations[0]['transcript_segments'][0]['speaker_name'] == 'Speaker 2'

    def test_missing_speaker_id_defaults_to_zero(self, render):
        conversations = [{'transcript_segments': [{'text': 'hi'}]}]
        render.populate_speaker_names('uid1', conversations)
        assert conversations[0]['transcript_segments'][0]['speaker_name'] == 'Speaker 0'

    def test_user_profile_missing_name_falls_back_to_user(self, render):
        _mock_get_user_profile.return_value = {"name": None}
        conversations = [{'transcript_segments': [{'text': 'hi', 'is_user': True, 'speaker_id': 0}]}]
        render.populate_speaker_names('uid1', conversations)
        assert conversations[0]['transcript_segments'][0]['speaker_name'] == 'User'

    def test_empty_conversations_list(self, render):
        render.populate_speaker_names('uid1', [])
        _mock_get_user_profile.assert_called_once_with('uid1')
        _mock_get_people_by_ids.assert_not_called()

    def test_no_transcript_segments_key(self, render):
        conversations = [{'id': 'conv1'}]
        render.populate_speaker_names('uid1', conversations)
        # Should not crash — no segments to enrich

    def test_batch_loads_people_once(self, render):
        _mock_get_people_by_ids.return_value = [
            {'id': 'p1', 'name': 'Alice'},
            {'id': 'p2', 'name': 'Bob'},
        ]
        conversations = [
            {
                'transcript_segments': [
                    {'text': 'hi', 'is_user': False, 'person_id': 'p1', 'speaker_id': 1},
                ]
            },
            {
                'transcript_segments': [
                    {'text': 'hey', 'is_user': False, 'person_id': 'p2', 'speaker_id': 2},
                    {'text': 'yo', 'is_user': False, 'person_id': 'p1', 'speaker_id': 1},
                ]
            },
        ]
        render.populate_speaker_names('uid1', conversations)
        assert _mock_get_people_by_ids.call_count == 1
        assert conversations[0]['transcript_segments'][0]['speaker_name'] == 'Alice'
        assert conversations[1]['transcript_segments'][0]['speaker_name'] == 'Bob'
        assert conversations[1]['transcript_segments'][1]['speaker_name'] == 'Alice'
