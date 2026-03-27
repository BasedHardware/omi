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

_stub_module("utils.conversations")
_stub_module("utils.conversations.process_conversation")
sys.modules["utils.conversations.process_conversation"].process_conversation = MagicMock()

_stub_module("utils.conversations.location")
sys.modules["utils.conversations.location"].get_google_maps_location = MagicMock()

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
from routers.developer import _add_folder_names_to_conversations
from utils.webhooks import _add_folder_name_to_payload


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAddFolderNamesToConversations:
    """Tests for _add_folder_names_to_conversations in developer API."""

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
        _add_folder_names_to_conversations('uid1', conversations)

        assert conversations[0]['folder_name'] == 'Work'
        assert conversations[1]['folder_name'] == 'Personal'
        _mock_get_folders.assert_called_once_with('uid1')

    def test_conversations_without_folder_id_get_none(self):
        conversations = [
            {'id': 'conv1', 'folder_id': None},
            {'id': 'conv2'},
        ]
        _add_folder_names_to_conversations('uid1', conversations)

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
        _add_folder_names_to_conversations('uid1', conversations)

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
        _add_folder_names_to_conversations('uid1', conversations)

        assert conversations[0]['folder_name'] == 'Work'
        assert conversations[1]['folder_name'] is None
        assert conversations[2]['folder_name'] is None

    def test_empty_conversations_list(self):
        conversations = []
        _add_folder_names_to_conversations('uid1', conversations)

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
        _add_folder_names_to_conversations('uid1', conversations)

        assert _mock_get_folders.call_count == 1


class TestAddFolderNameToPayload:
    """Tests for _add_folder_name_to_payload in webhook."""

    def setup_method(self):
        _mock_get_folder.reset_mock()

    def test_payload_with_folder_id_gets_folder_name(self):
        _mock_get_folder.return_value = {'id': 'folder1', 'name': 'Work'}
        payload = {'folder_id': 'folder1'}

        _add_folder_name_to_payload('uid1', payload)

        assert payload['folder_name'] == 'Work'
        _mock_get_folder.assert_called_once_with('uid1', 'folder1')

    def test_payload_without_folder_id_gets_none(self):
        payload = {'folder_id': None}

        _add_folder_name_to_payload('uid1', payload)

        assert payload['folder_name'] is None
        _mock_get_folder.assert_not_called()

    def test_payload_missing_folder_id_key_gets_none(self):
        payload = {}

        _add_folder_name_to_payload('uid1', payload)

        assert payload['folder_name'] is None
        _mock_get_folder.assert_not_called()

    def test_folder_not_found_in_db_returns_none(self):
        _mock_get_folder.return_value = None
        payload = {'folder_id': 'deleted_folder'}

        _add_folder_name_to_payload('uid1', payload)

        assert payload['folder_name'] is None
