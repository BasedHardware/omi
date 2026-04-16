import os
import sys
import types
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _stub_module(name):
    if name not in sys.modules:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return sys.modules[name]


# ---------------------------------------------------------------------------
# Stub database package and submodules
# ---------------------------------------------------------------------------
database_mod = _stub_module("database")
if not hasattr(database_mod, '__path__'):
    database_mod.__path__ = []
for sub in [
    "_client",
    "redis_db",
    "memories",
    "conversations",
    "users",
    "folders",
    "action_items",
    "goals",
    "dev_api_key",
    "notifications",
    "chat",
    "daily_summaries",
    "apps",
    "llm_usage",
    "cache",
    "tasks",
    "trends",
    "calendar_meetings",
    "vector_db",
    "knowledge_graph",
    "mem_db",
]:
    mod = _stub_module(f"database.{sub}")
    setattr(database_mod, sub, mod)

# Stub database._client attributes
client_mod = sys.modules["database._client"]
client_mod.db = MagicMock()
client_mod.document_id_from_seed = MagicMock(return_value="mock-id")

# Stub redis_db attributes
redis_mod = sys.modules["database.redis_db"]
redis_mod.r = MagicMock()
for attr in [
    "get_user_webhook_db",
    "user_webhook_status_db",
    "disable_user_webhook_db",
    "enable_user_webhook_db",
    "set_user_webhook_db",
]:
    setattr(redis_mod, attr, MagicMock())

# Stub database.users
users_mod = sys.modules["database.users"]
users_mod.get_user_profile = MagicMock(return_value={"name": "TestUser"})
users_mod.get_people_by_ids = MagicMock(return_value=[])

# Stub database.folders with controllable mocks
folders_mod = sys.modules["database.folders"]
_mock_get_folders = MagicMock(return_value=[])
_mock_get_folder = MagicMock(return_value=None)
folders_mod.get_folders = _mock_get_folders
folders_mod.get_folder = _mock_get_folder

# ---------------------------------------------------------------------------
# Stub firebase_admin
# ---------------------------------------------------------------------------
_stub_module("firebase_admin")
_stub_module("firebase_admin.auth")
sys.modules["firebase_admin"].auth = sys.modules["firebase_admin.auth"]

# ---------------------------------------------------------------------------
# Stub utils modules that import heavy dependencies
# ---------------------------------------------------------------------------
_stub_module("utils.apps")
sys.modules["utils.apps"].update_personas_async = MagicMock()

_stub_module("utils.notifications")
sys.modules["utils.notifications"].send_notification = MagicMock()
sys.modules["utils.notifications"].send_action_item_data_message = MagicMock()

_stub_module("utils.scopes")
sys.modules["utils.scopes"].AVAILABLE_SCOPES = {}
sys.modules["utils.scopes"].validate_scopes = MagicMock()

# utils.conversations.render imports database.folders and database.users
# which are already stubbed above — no additional stubs needed.

_stub_module("utils.llm")
_stub_module("utils.llm.memories")
sys.modules["utils.llm.memories"].identify_category_for_memory = MagicMock()

_stub_module("dependencies")
sys.modules["dependencies"].get_uid_from_dev_api_key = MagicMock()
sys.modules["dependencies"].get_current_user_id = MagicMock()
sys.modules["dependencies"].get_uid_with_conversations_read = MagicMock()
sys.modules["dependencies"].get_uid_with_conversations_write = MagicMock()
sys.modules["dependencies"].get_uid_with_memories_read = MagicMock()
sys.modules["dependencies"].get_uid_with_memories_write = MagicMock()
sys.modules["dependencies"].get_uid_with_action_items_read = MagicMock()
sys.modules["dependencies"].get_uid_with_action_items_write = MagicMock()
sys.modules["dependencies"].get_uid_with_goals_read = MagicMock()
sys.modules["dependencies"].get_uid_with_goals_write = MagicMock()

# ---------------------------------------------------------------------------
# Now import the actual functions under test
# ---------------------------------------------------------------------------
from utils.conversations.render import populate_folder_names, populate_speaker_names

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAddFolderNamesToConversations:
    """Tests for populate_folder_names in developer API."""

    def setup_method(self):
        _mock_get_folders.reset_mock()

    def test_conversations_with_folder_id_get_folder_name(self):
        _mock_get_folders.return_value = [
            {'id': 'folder1', 'name': 'Work'},
            {'id': 'folder2', 'name': 'Personal'},
        ]
        conversations = [
            {'id': 'conv1', 'folder_id': 'folder1'},
            {'id': 'conv2', 'folder_id': 'folder2'},
        ]
        populate_folder_names('uid1', conversations)

        assert conversations[0]['folder_name'] == 'Work'
        assert conversations[1]['folder_name'] == 'Personal'
        _mock_get_folders.assert_called_once_with('uid1')

    def test_conversations_without_folder_id_get_none(self):
        conversations = [
            {'id': 'conv1', 'folder_id': None},
            {'id': 'conv2'},
        ]
        populate_folder_names('uid1', conversations)

        assert conversations[0]['folder_name'] is None
        assert conversations[1]['folder_name'] is None
        _mock_get_folders.assert_not_called()

    def test_folder_id_not_found_in_db_returns_none(self):
        _mock_get_folders.return_value = [
            {'id': 'folder1', 'name': 'Work'},
        ]
        conversations = [
            {'id': 'conv1', 'folder_id': 'deleted_folder'},
        ]
        populate_folder_names('uid1', conversations)

        assert conversations[0]['folder_name'] is None

    def test_mixed_conversations_with_and_without_folder_id(self):
        _mock_get_folders.return_value = [
            {'id': 'folder1', 'name': 'Work'},
        ]
        conversations = [
            {'id': 'conv1', 'folder_id': 'folder1'},
            {'id': 'conv2', 'folder_id': None},
            {'id': 'conv3'},
        ]
        populate_folder_names('uid1', conversations)

        assert conversations[0]['folder_name'] == 'Work'
        assert conversations[1]['folder_name'] is None
        assert conversations[2]['folder_name'] is None

    def test_empty_conversations_list(self):
        conversations = []
        populate_folder_names('uid1', conversations)

        assert conversations == []
        _mock_get_folders.assert_not_called()

    def test_batch_fetches_all_folders_once(self):
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
        populate_folder_names('uid1', conversations)

        assert _mock_get_folders.call_count == 1


class TestAddFolderNamesWebhookPayload:
    """Tests for populate_folder_names with single-item webhook payloads."""

    def setup_method(self):
        _mock_get_folders.reset_mock()

    def test_payload_with_folder_id_gets_folder_name(self):
        _mock_get_folders.return_value = [{'id': 'folder1', 'name': 'Work'}]
        payload = {'folder_id': 'folder1'}

        populate_folder_names('uid1', [payload])

        assert payload['folder_name'] == 'Work'
        _mock_get_folders.assert_called_once_with('uid1')

    def test_payload_without_folder_id_gets_none(self):
        payload = {'folder_id': None}

        populate_folder_names('uid1', [payload])

        assert payload['folder_name'] is None
        _mock_get_folders.assert_not_called()

    def test_payload_missing_folder_id_key_gets_none(self):
        payload = {}

        populate_folder_names('uid1', [payload])

        assert payload['folder_name'] is None
        _mock_get_folders.assert_not_called()

    def test_folder_not_found_in_db_returns_none(self):
        _mock_get_folders.return_value = []
        payload = {'folder_id': 'deleted_folder'}

        populate_folder_names('uid1', [payload])

        assert payload['folder_name'] is None


# ---------------------------------------------------------------------------
# Speaker name enrichment tests
# ---------------------------------------------------------------------------
_mock_get_user_profile = users_mod.get_user_profile
_mock_get_people_by_ids = users_mod.get_people_by_ids


class TestAddSpeakerNames:
    """Tests for populate_speaker_names enrichment."""

    def setup_method(self):
        _mock_get_user_profile.reset_mock()
        _mock_get_people_by_ids.reset_mock()
        _mock_get_user_profile.return_value = {"name": "TestUser"}
        _mock_get_people_by_ids.return_value = []

    def test_user_segments_get_user_name(self):
        conversations = [{'transcript_segments': [{'text': 'hi', 'is_user': True, 'speaker_id': 0}]}]
        populate_speaker_names('uid1', conversations)
        assert conversations[0]['transcript_segments'][0]['speaker_name'] == 'TestUser'

    def test_known_person_id_gets_person_name(self):
        _mock_get_people_by_ids.return_value = [{'id': 'p1', 'name': 'Alice'}]
        conversations = [
            {'transcript_segments': [{'text': 'hi', 'is_user': False, 'person_id': 'p1', 'speaker_id': 1}]}
        ]
        populate_speaker_names('uid1', conversations)
        assert conversations[0]['transcript_segments'][0]['speaker_name'] == 'Alice'

    def test_unknown_person_id_falls_back_to_speaker_id(self):
        _mock_get_people_by_ids.return_value = []
        conversations = [
            {'transcript_segments': [{'text': 'hi', 'is_user': False, 'person_id': 'unknown_p', 'speaker_id': 3}]}
        ]
        populate_speaker_names('uid1', conversations)
        assert conversations[0]['transcript_segments'][0]['speaker_name'] == 'Speaker 3'

    def test_no_person_id_no_is_user_falls_back_to_speaker_id(self):
        conversations = [{'transcript_segments': [{'text': 'hi', 'speaker_id': 2}]}]
        populate_speaker_names('uid1', conversations)
        assert conversations[0]['transcript_segments'][0]['speaker_name'] == 'Speaker 2'

    def test_missing_speaker_id_defaults_to_zero(self):
        conversations = [{'transcript_segments': [{'text': 'hi'}]}]
        populate_speaker_names('uid1', conversations)
        assert conversations[0]['transcript_segments'][0]['speaker_name'] == 'Speaker 0'

    def test_user_profile_missing_name_falls_back_to_user(self):
        _mock_get_user_profile.return_value = {"name": None}
        conversations = [{'transcript_segments': [{'text': 'hi', 'is_user': True, 'speaker_id': 0}]}]
        populate_speaker_names('uid1', conversations)
        assert conversations[0]['transcript_segments'][0]['speaker_name'] == 'User'

    def test_empty_conversations_list(self):
        populate_speaker_names('uid1', [])
        _mock_get_user_profile.assert_called_once_with('uid1')
        _mock_get_people_by_ids.assert_not_called()

    def test_no_transcript_segments_key(self):
        conversations = [{'id': 'conv1'}]
        populate_speaker_names('uid1', conversations)
        # Should not crash — no segments to enrich

    def test_batch_loads_people_once(self):
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
        populate_speaker_names('uid1', conversations)
        assert _mock_get_people_by_ids.call_count == 1
        assert conversations[0]['transcript_segments'][0]['speaker_name'] == 'Alice'
        assert conversations[1]['transcript_segments'][0]['speaker_name'] == 'Bob'
        assert conversations[1]['transcript_segments'][1]['speaker_name'] == 'Alice'
