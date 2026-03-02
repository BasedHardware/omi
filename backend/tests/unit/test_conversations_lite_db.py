"""
Tests for get_conversations_lite() in database/conversations.py.
Verifies that the lite function strips heavy fields and applies all filters.
Imports the REAL production function via importlib to avoid Firestore init.
"""

import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _ensure_mock_module(name: str):
    """Ensure a MagicMock module exists in sys.modules (supports 'from X import Y')."""
    if name not in sys.modules:
        mod = MagicMock()
        mod.__path__ = []
        mod.__name__ = name
        mod.__loader__ = None
        mod.__spec__ = None
        mod.__package__ = name if '.' not in name else name.rsplit('.', 1)[0]
        sys.modules[name] = mod
    return sys.modules[name]


# Stub _client with mock db BEFORE database.conversations can import it
mock_db = MagicMock()

_ensure_mock_module("database")
sys.modules["database"].__path__ = getattr(sys.modules["database"], '__path__', [])

client_stub = _ensure_mock_module("database._client")
client_stub.db = mock_db
client_stub.document_id_from_seed = MagicMock(return_value="doc-id")

# Stub database.users and database.helpers
_ensure_mock_module("database.users")


def _passthrough(*args, **kwargs):
    """No-op decorator factory: @decorator(...) returns identity decorator."""
    return lambda f: f


# Stub helpers with real passthrough decorators (database.conversations uses them at import time)
helpers_mod = types.ModuleType("database.helpers")
helpers_mod.set_data_protection_level = _passthrough
helpers_mod.prepare_for_write = _passthrough
helpers_mod.prepare_for_read = _passthrough
helpers_mod.with_photos = _passthrough
sys.modules["database.helpers"] = helpers_mod

# Stub utils modules (must be MagicMock to support 'from X import Y')
for name in [
    "utils",
    "utils.other",
    "utils.other.hume",
    "utils.other.storage",
    "utils.encryption",
]:
    _ensure_mock_module(name)

# Load the REAL database/conversations.py using importlib
_conv_path = os.path.join(os.path.dirname(__file__), '..', '..', 'database', 'conversations.py')
_conv_path = os.path.abspath(_conv_path)

# Remove any stale entry so we get the real module
if "database.conversations" in sys.modules:
    del sys.modules["database.conversations"]

spec = importlib.util.spec_from_file_location("database.conversations", _conv_path)
conv_module = importlib.util.module_from_spec(spec)
sys.modules["database.conversations"] = conv_module
spec.loader.exec_module(conv_module)

get_conversations_lite = conv_module.get_conversations_lite


def _make_fake_doc(data: dict):
    doc = MagicMock()
    doc.to_dict.return_value = data
    return doc


def _setup_mock_ref():
    mock_ref = MagicMock()
    mock_ref.where.return_value = mock_ref
    mock_ref.order_by.return_value = mock_ref
    mock_ref.limit.return_value = mock_ref
    mock_ref.offset.return_value = mock_ref
    mock_db.collection.return_value.document.return_value.collection.return_value = mock_ref
    return mock_ref


class TestGetConversationsLite:
    def test_strips_heavy_fields(self):
        """transcript_segments=[], photos=[], transcript_segments_compressed removed."""
        mock_ref = _setup_mock_ref()
        fake_data = {
            'id': 'conv_1',
            'structured': {'title': 'Test', 'overview': 'Overview', 'category': 'personal'},
            'transcript_segments': [{'text': 'secret data', 'speaker_id': 0, 'start': 0.0, 'end': 1.0}],
            'transcript_segments_compressed': b'\x00\x01\x02',
            'photos': [{'url': 'https://example.com/photo.jpg'}],
            'discarded': False,
            'status': 'completed',
            'created_at': None,
        }
        mock_ref.stream.return_value = [_make_fake_doc(dict(fake_data))]

        result = get_conversations_lite('uid_1', limit=10, offset=0)

        assert len(result) == 1
        conv = result[0]
        assert conv['transcript_segments'] == []
        assert conv['photos'] == []
        assert 'transcript_segments_compressed' not in conv
        assert conv['id'] == 'conv_1'
        assert conv['structured']['title'] == 'Test'

    def test_applies_all_filters(self):
        """All filter parameters are forwarded to Firestore queries."""
        from datetime import datetime

        mock_ref = _setup_mock_ref()
        mock_ref.stream.return_value = []

        start = datetime(2026, 1, 1)
        end = datetime(2026, 1, 31)

        get_conversations_lite(
            'uid_1',
            limit=25,
            offset=10,
            include_discarded=False,
            statuses=['completed'],
            start_date=start,
            end_date=end,
            categories=['personal'],
            folder_id='folder_abc',
            starred=True,
        )

        where_calls = mock_ref.where.call_args_list
        assert len(where_calls) == 7  # discarded + status + category + folder + starred + start + end
        mock_ref.order_by.assert_called_once()
        mock_ref.limit.assert_called_once_with(25)
        mock_ref.offset.assert_called_once_with(10)

    def test_include_discarded_true_skips_filter(self):
        """When include_discarded=True, the discarded filter is NOT applied."""
        mock_ref = _setup_mock_ref()
        mock_ref.stream.return_value = []

        get_conversations_lite('uid_1', include_discarded=True)

        assert mock_ref.where.call_count == 0
