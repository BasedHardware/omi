"""A stale memory update on a missing projection doc must be idempotent, not a 500.

set_memory_kg_extracted / invalidate_memory can target a memory whose projection document no longer
exists (deleted, or a canonical cohort that never wrote the legacy projection). The port's tx.update
on a missing doc is adapter-defined (ADR-0021), so these guard with exists() and no-op the projection
write; invalidate_memory still records the ledger commit. This exercises the real port seam via
FakeDocumentStore (mongomock has no transactions).
"""

import os

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import pytest  # noqa: E402

import database.memories as memories_module  # noqa: E402
from database import memory_ledger, projection_repair  # noqa: E402
from tests.store_fakes import FakeDocumentStore  # noqa: E402


@pytest.fixture
def store(monkeypatch):
    fake = FakeDocumentStore()
    # memories + the ledger + repair enqueue all resolve the same backing store.
    monkeypatch.setattr(memories_module, '_store', lambda: fake)
    monkeypatch.setattr(memory_ledger, '_store', lambda: fake)
    monkeypatch.setattr(projection_repair, '_store', lambda: fake)
    return fake


def test_set_memory_kg_extracted_missing_doc_is_idempotent(caplog, store):
    # No memory doc seeded — the update must no-op rather than raise.
    assert memories_module.set_memory_kg_extracted('uid-abc', 'memory-1') is None

    assert not store.exists('users/uid-abc/memories/memory-1')  # not created
    assert 'No document to update' not in caplog.text


def test_invalidate_memory_missing_doc_is_idempotent(store):
    # No projection doc — the write is skipped, but the ledger still records the invalidation.
    result = memories_module.invalidate_memory('uid-abc', 'memory-1', superseded_by='memory-2')

    assert not store.exists('users/uid-abc/memories/memory-1')  # projection not resurrected
    assert result is not None and result.get('applied') is True  # ledger commit recorded
