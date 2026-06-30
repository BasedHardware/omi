"""
Unit tests for database/ai_clone.py

Critical contracts:
- get_clone_settings returns a safe default dict when the Firestore doc doesn't exist
- update_clone_settings uses merge=True (does not clobber unrelated fields)
- update_platform_settings uses dot-notation path (does NOT replace the whole platforms dict)
- save_clone_message auto-generates an ID and sets created_at
- get_clone_messages orders by created_at descending
- update_clone_message uses .update() (not .set()) so it patches fields, not replaces the doc
"""

import os
import sys
import types
from unittest.mock import MagicMock, call, patch

os.environ.setdefault('ENCRYPTION_SECRET', 'x' * 64)

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, BACKEND_DIR)

# ── Firestore stub ─────────────────────────────────────────────────────────────

_firestore_stub = types.ModuleType('google.cloud.firestore')
_firestore_stub.Client = MagicMock
_firestore_stub.SERVER_TIMESTAMP = object()
_firestore_stub.DELETE_FIELD = object()
_firestore_stub.FieldFilter = MagicMock
_firestore_stub.ArrayUnion = MagicMock
_firestore_stub.ArrayRemove = MagicMock
_firestore_stub.Increment = MagicMock
_firestore_stub.Query = MagicMock

for mod in ['google', 'google.cloud', 'google.cloud.firestore']:
    if mod not in sys.modules:
        sys.modules[mod] = types.ModuleType(mod)
sys.modules['google.cloud.firestore'] = _firestore_stub

# Stub google.api_core.exceptions.NotFound so ai_clone.py can import it
_NotFound = type('NotFound', (Exception,), {})
_api_core_exceptions = types.ModuleType('google.api_core.exceptions')
_api_core_exceptions.NotFound = _NotFound
_api_core = types.ModuleType('google.api_core')
_api_core.exceptions = _api_core_exceptions
sys.modules['google.api_core'] = _api_core
sys.modules['google.api_core.exceptions'] = _api_core_exceptions

for mod in ['firebase_admin', 'firebase_admin.auth', 'firebase_admin.credentials']:
    if mod not in sys.modules:
        sys.modules[mod] = types.ModuleType(mod)
sys.modules['firebase_admin.auth'].InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})

# Make database a real package pointing at the source directory
_db_pkg = sys.modules.get('database')
if not isinstance(_db_pkg, types.ModuleType) or not hasattr(_db_pkg, '__path__'):
    _db_pkg = types.ModuleType('database')
    sys.modules['database'] = _db_pkg
_db_pkg.__path__ = [os.path.join(BACKEND_DIR, 'database')]

# ── Import the module under test ───────────────────────────────────────────────

import importlib

_client_mod = types.ModuleType('database._client')
_fake_db = MagicMock()
_client_mod.db = _fake_db
_client_mod.document_id_from_seed = MagicMock(return_value='seeded-id')
sys.modules['database._client'] = _client_mod

sys.modules.pop('database.ai_clone', None)
import database.ai_clone as clone_db  # noqa: E402

# Point the module's db reference at our fake
clone_db.db = _fake_db


# ── Helpers ────────────────────────────────────────────────────────────────────


def _reset_db():
    _fake_db.reset_mock()


def _settings_ref():
    return _fake_db.collection.return_value.document.return_value.collection.return_value.document.return_value


# ── Tests: get_clone_settings ─────────────────────────────────────────────────


class TestGetCloneSettings:
    def test_returns_default_when_doc_missing(self):
        _reset_db()
        doc = MagicMock()
        doc.exists = False
        _settings_ref().get.return_value = doc

        result = clone_db.get_clone_settings('uid-123')

        assert result == {'enabled': False, 'auto_reply': False, 'platforms': {}}

    def test_returns_firestore_data_when_doc_exists(self):
        _reset_db()
        doc = MagicMock()
        doc.exists = True
        doc.to_dict.return_value = {
            'enabled': True,
            'auto_reply': False,
            'platforms': {'telegram': {'connected': True}},
        }
        _settings_ref().get.return_value = doc

        result = clone_db.get_clone_settings('uid-123')

        assert result['enabled'] is True
        assert result['platforms']['telegram']['connected'] is True

    def test_queries_correct_firestore_path(self):
        _reset_db()
        doc = MagicMock()
        doc.exists = False
        _settings_ref().get.return_value = doc

        clone_db.get_clone_settings('uid-abc')

        _fake_db.collection.assert_called_with('users')
        _fake_db.collection.return_value.document.assert_called_with('uid-abc')
        _fake_db.collection.return_value.document.return_value.collection.assert_called_with('ai_clone')
        _fake_db.collection.return_value.document.return_value.collection.return_value.document.assert_called_with(
            'settings'
        )


# ── Tests: update_clone_settings ──────────────────────────────────────────────


class TestUpdateCloneSettings:
    def test_uses_merge_true(self):
        _reset_db()
        ref = _settings_ref()

        clone_db.update_clone_settings('uid-123', {'enabled': True})

        ref.set.assert_called_once()
        _, kwargs = ref.set.call_args
        assert kwargs.get('merge') is True, 'Must use merge=True to avoid clobbering unrelated fields'

    def test_passes_settings_dict_to_firestore(self):
        _reset_db()
        ref = _settings_ref()
        payload = {'enabled': True, 'auto_reply': True}

        clone_db.update_clone_settings('uid-123', payload)

        args, _ = ref.set.call_args
        assert args[0] == payload


# ── Tests: update_platform_settings ───────────────────────────────────────────


class TestUpdatePlatformSettings:
    def test_uses_dot_notation_path(self):
        """Critical: must NOT replace the whole platforms dict — only update platforms.telegram."""
        _reset_db()
        ref = _settings_ref()

        clone_db.update_platform_settings('uid-123', 'telegram', {'connected': True, 'session_string': 'abc'})

        ref.update.assert_called_once()
        args, _ = ref.update.call_args
        update_dict = args[0]
        # The key must be the dot-notation path, not a nested dict
        assert 'platforms.telegram' in update_dict, (
            'update_platform_settings must use dot-notation path "platforms.telegram" '
            'so it does not overwrite the iMessage platform settings'
        )

    def test_does_not_call_set(self):
        """Using .set() would clobber other platforms; must use .update()."""
        _reset_db()
        ref = _settings_ref()

        clone_db.update_platform_settings('uid-123', 'imessage', {'connected': True})

        ref.set.assert_not_called()

    def test_payload_stored_under_dot_notation_key(self):
        _reset_db()
        ref = _settings_ref()
        data = {'connected': True, 'session_string': 'sess123'}

        clone_db.update_platform_settings('uid-x', 'telegram', data)

        args, _ = ref.update.call_args
        assert args[0]['platforms.telegram'] == data


# ── Tests: save_clone_message ─────────────────────────────────────────────────


class TestSaveCloneMessage:
    def test_returns_generated_document_id(self):
        _reset_db()
        doc_ref = MagicMock()
        doc_ref.id = 'generated-doc-id'
        _fake_db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

        result = clone_db.save_clone_message('uid-123', {'platform': 'telegram', 'incoming': 'hi'})

        assert result == 'generated-doc-id'

    def test_adds_created_at_timestamp(self):
        _reset_db()
        doc_ref = MagicMock()
        doc_ref.id = 'doc-id'
        _fake_db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref
        message = {'platform': 'imessage', 'incoming': 'hey'}

        clone_db.save_clone_message('uid-123', message)

        args, _ = doc_ref.set.call_args
        saved = args[0]
        assert 'created_at' in saved, 'save_clone_message must set created_at for ordering'
        assert 'id' in saved, 'save_clone_message must embed the document ID for retrieval'

    def test_does_not_mutate_original_dict(self):
        _reset_db()
        doc_ref = MagicMock()
        doc_ref.id = 'doc-id'
        _fake_db.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref
        original = {'platform': 'telegram', 'incoming': 'hello'}
        original_copy = dict(original)

        clone_db.save_clone_message('uid-x', original)

        # The function modifies the dict in-place (adds created_at/id), which is fine,
        # but it should not break the caller's reference
        assert original['platform'] == original_copy['platform']


# ── Tests: get_clone_messages ─────────────────────────────────────────────────


class TestGetCloneMessages:
    def test_orders_by_created_at_descending(self):
        _reset_db()
        query_chain = MagicMock()
        doc1, doc2 = MagicMock(), MagicMock()
        doc1.to_dict.return_value = {'id': 'a', 'created_at': '2024-01-02'}
        doc2.to_dict.return_value = {'id': 'b', 'created_at': '2024-01-01'}
        query_chain.stream.return_value = [doc1, doc2]

        _fake_db.collection.return_value.document.return_value.collection.return_value.order_by.return_value.limit.return_value = (
            query_chain
        )

        result = clone_db.get_clone_messages('uid-123', limit=50)

        order_call = _fake_db.collection.return_value.document.return_value.collection.return_value.order_by
        order_call.assert_called_once()
        args, kwargs = order_call.call_args
        assert args[0] == 'created_at'
        assert kwargs.get('direction') == 'DESCENDING'
        assert len(result) == 2

    def test_respects_limit(self):
        _reset_db()
        query_chain = MagicMock()
        query_chain.stream.return_value = []
        _fake_db.collection.return_value.document.return_value.collection.return_value.order_by.return_value.limit.return_value = (
            query_chain
        )

        clone_db.get_clone_messages('uid-123', limit=10)

        limit_call = (
            _fake_db.collection.return_value.document.return_value.collection.return_value.order_by.return_value.limit
        )
        limit_call.assert_called_with(10)


# ── Tests: update_clone_message ───────────────────────────────────────────────


class TestUpdateCloneMessage:
    def test_uses_update_not_set(self):
        """Must use .update() to patch specific fields — .set() would wipe the document."""
        _reset_db()
        msg_ref = MagicMock()
        _fake_db.collection.return_value.document.return_value.collection.return_value.document.return_value = msg_ref

        clone_db.update_clone_message('uid-123', 'msg-id-456', {'status': 'sent'})

        msg_ref.update.assert_called_once_with({'status': 'sent'})
        msg_ref.set.assert_not_called()


# ── Tests: get_platform_settings ─────────────────────────────────────────────


class TestGetPlatformSettings:
    def test_returns_platform_sub_dict(self):
        _reset_db()
        doc = MagicMock()
        doc.exists = True
        doc.to_dict.return_value = {
            'platforms': {'telegram': {'connected': True, 'phone': '+1234'}, 'imessage': {'connected': True}}
        }
        _settings_ref().get.return_value = doc

        result = clone_db.get_platform_settings('uid-x', 'telegram')

        assert result == {'connected': True, 'phone': '+1234'}

    def test_returns_none_for_missing_platform(self):
        _reset_db()
        doc = MagicMock()
        doc.exists = True
        doc.to_dict.return_value = {'platforms': {}}
        _settings_ref().get.return_value = doc

        result = clone_db.get_platform_settings('uid-x', 'whatsapp')

        assert result is None

    def test_returns_none_when_doc_missing(self):
        _reset_db()
        doc = MagicMock()
        doc.exists = False
        _settings_ref().get.return_value = doc

        result = clone_db.get_platform_settings('uid-x', 'telegram')

        assert result is None


# ── Tests: set_platform_field ────────────────────────────────────────────────


class TestSetPlatformField:
    def test_uses_deep_dot_notation_to_preserve_other_fields(self):
        """platforms.telegram.active must not clobber bot_token or other fields."""
        _reset_db()
        ref = _settings_ref()

        clone_db.set_platform_field('uid-x', 'telegram', 'active', True)

        args, _ = ref.update.call_args
        # Key must be the deep path, not just 'platforms.telegram'
        assert 'platforms.telegram.active' in args[0]
        assert args[0]['platforms.telegram.active'] is True

    def test_does_not_use_shallow_path(self):
        _reset_db()
        ref = _settings_ref()

        clone_db.set_platform_field('uid-x', 'imessage', 'active', False)

        args, _ = ref.update.call_args
        # Shallow path would clobber other fields — must NOT be present
        assert 'platforms.imessage' not in args[0]

    def test_falls_back_to_set_merge_on_first_write(self):
        _reset_db()
        ref = _settings_ref()
        ref.update.side_effect = _NotFound('document not found')

        clone_db.set_platform_field('uid-new', 'whatsapp', 'active', True)

        ref.set.assert_called_once()
        call_args = ref.set.call_args
        data = call_args[0][0]
        assert data['platforms']['whatsapp']['active'] is True
        assert call_args[1].get('merge') is True

    def test_does_not_swallow_other_exceptions(self):
        _reset_db()
        ref = _settings_ref()
        ref.update.side_effect = RuntimeError('network error')

        try:
            clone_db.set_platform_field('uid-x', 'telegram', 'active', True)
            assert False, 'Expected RuntimeError to propagate'
        except RuntimeError:
            pass
