"""migrate_conversations_level_batch must not abort when a photo doc has no base64 payload.

The photo migration loop decrypted each photo with _prepare_photo_for_read and then read
plain_photo_data['base64'] unconditionally. A photo doc missing the base64 field (legacy or a partial
write) makes _prepare_photo_for_read return None (empty doc) or a dict without 'base64', so the bracket
access raised KeyError/TypeError and aborted the whole multi-conversation migration batch partway through
(after some batches had already been committed).

database/conversations.py initializes the Firestore client at import time, so we load it from source with
its heavy dependencies stubbed, then patch the conversation-prep helpers (not under test) and drive the
real photo loop with a mocked Firestore.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

# Stub every heavy dependency database/conversations.py pulls in at import time. We load the module from
# source (it inits Firestore at import), so a meta-path finder satisfies its imports with auto-mocks while
# the module's own functions stay real.
_STUB = ('database', 'utils', 'models', 'google', 'firebase_admin', 'pinecone', 'opuslib', 'pydub', 'redis')


def _is_stubbed_name(name):
    return any(name == p or name.startswith(p + '.') for p in _STUB)


class _AutoMock(types.ModuleType):
    __path__ = []

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        m = MagicMock()
        setattr(self, name, m)
        return m


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        if _is_stubbed_name(name):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        pass


_finder = _Finder()
_saved = {name: mod for name, mod in sys.modules.items() if _is_stubbed_name(name)}
for name in list(sys.modules):
    if _is_stubbed_name(name):
        sys.modules.pop(name, None)
sys.meta_path.insert(0, _finder)
try:
    _spec = importlib.util.spec_from_file_location(
        'database.conversations', str(_BACKEND_DIR / 'database' / 'conversations.py')
    )
    conv_db = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(conv_db)
finally:
    sys.meta_path.remove(_finder)
    for name in list(sys.modules):
        if _is_stubbed_name(name) and name not in _saved:
            sys.modules.pop(name, None)
    sys.modules.update(_saved)


def _make_snapshot(doc_id, data, reference):
    snap = MagicMock()
    snap.exists = True
    snap.id = doc_id
    snap.to_dict.return_value = data
    snap.reference = reference
    return snap


def _make_photo_doc(data):
    doc = MagicMock()
    doc.to_dict.return_value = data
    doc.reference = MagicMock()
    return doc


def _run_migration(photo_docs, target_level='enhanced'):
    """Drive migrate_conversations_level_batch for one standard conversation with the given photo docs."""
    batch = MagicMock()
    db = MagicMock()
    db.batch.return_value = batch

    conv_ref = MagicMock()
    conv_ref.collection.return_value.select.return_value.stream.return_value = iter(photo_docs)
    conv_snapshot = _make_snapshot('c1', {'data_protection_level': 'standard'}, conv_ref)
    db.get_all.return_value = [conv_snapshot]

    with patch.object(conv_db, 'db', db), patch.object(
        conv_db, '_prepare_conversation_for_read', lambda data, uid: data
    ), patch.object(conv_db, '_prepare_conversation_for_write', lambda payload, uid, level: {}):
        conv_db.migrate_conversations_level_batch('uid1', ['c1'], target_level)
    return batch


def test_photo_missing_base64_does_not_abort_migration():
    # A photo doc with no base64 field (and an empty one) must be skipped, not crash the whole batch.
    photos = [_make_photo_doc({'data_protection_level': 'standard'}), _make_photo_doc({})]
    batch = _run_migration(photos)  # must not raise
    photo_payloads = [
        c.args[1] for c in batch.update.call_args_list if isinstance(c.args[1], dict) and 'base64' in c.args[1]
    ]
    assert photo_payloads == []  # neither bad photo produced a base64 update


def test_valid_photo_still_migrated():
    # A photo that does have base64 must still be migrated (regression guard for over-skipping).
    photos = [_make_photo_doc({'data_protection_level': 'standard', 'base64': 'abc'})]
    batch = _run_migration(photos)
    photo_payloads = [
        c.args[1] for c in batch.update.call_args_list if isinstance(c.args[1], dict) and 'base64' in c.args[1]
    ]
    assert len(photo_payloads) == 1
