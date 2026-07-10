from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import NotFound

import database.memories as memories_module


class _FakeDb:
    def __init__(self, memory_ref):
        self.memory_ref = memory_ref

    def collection(self, _name):
        return self

    def document(self, _name):
        return self

    def update(self, payload):
        return self.memory_ref.update(payload)

    def batch(self):
        return MagicMock()


class _FakeTransaction:
    def update(self, ref, payload):
        return ref.update(payload)


def _append_commit_with_projection(**kwargs):
    projection_writer = kwargs.get('projection_writer')
    if projection_writer:
        projection_writer(_FakeTransaction())
    return None


@pytest.fixture
def patch_memories(monkeypatch):
    """Wire ``database.memories`` to a fake db rooted at ``memory_ref`` and mock the ledger.

    ``database.memories`` imports cleanly now (``db`` is a lazy proxy, no import-time
    side effects), so the sanctioned seam is ``monkeypatch.setattr`` on the module
    attributes rather than ``sys.modules`` mutation. See backend/docs/test_isolation.md.
    """

    def _configure(memory_ref):
        fake_db = _FakeDb(memory_ref)
        monkeypatch.setattr(memories_module, 'get_firestore_client', lambda: fake_db)
        monkeypatch.setattr(
            memories_module.memory_ledger,
            'append_commit',
            MagicMock(side_effect=lambda *args, **kwargs: _append_commit_with_projection(**kwargs)),
        )
        return memories_module

    return _configure


def test_set_memory_kg_extracted_missing_doc_is_idempotent(caplog, patch_memories):
    memory_ref = MagicMock()
    memory_ref.update.side_effect = NotFound('No document to update: users/u/memories/m')
    memories = patch_memories(memory_ref)

    assert memories.set_memory_kg_extracted('uid-abc', 'memory-1') is None

    memory_ref.update.assert_called_once_with({'kg_extracted': True})
    assert 'memory-1' not in caplog.text
    assert 'No document to update' not in caplog.text


def test_invalidate_memory_missing_doc_is_idempotent(caplog, patch_memories):
    memory_ref = MagicMock()
    memory_ref.update.side_effect = NotFound('No document to update: users/u/memories/m')
    memories = patch_memories(memory_ref)

    assert memories.invalidate_memory('uid-abc', 'memory-1', superseded_by='memory-2') is None

    payload = memory_ref.update.call_args.args[0]
    assert 'invalid_at' in payload
    assert payload['superseded_by'] == 'memory-2'
    assert 'memory-1' not in caplog.text
    assert 'memory-2' not in caplog.text
    assert 'No document to update' not in caplog.text
