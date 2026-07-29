"""mark_consolidated must no-op on an absent short-term doc instead of 500ing resolve.

Resolving a review conflict (POST /v3/memories/review-queue/{id}/resolve) calls mark_consolidated on
the conflict's source_short_term_id. Canonical cohorts write memory_items, not short_term, so that id
can point at an absent short_term doc. Firestore .update() raises NotFound on a missing doc (unlike
set), which surfaced as HTTP 500. It now checks existence first. database.short_term_memories is light.
"""

import os

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import database.short_term_memories as stm
from tests.store_fakes import FakeDocumentStore


def test_noop_when_doc_absent(monkeypatch):
    store = FakeDocumentStore()
    monkeypatch.setattr(stm, '_store', lambda: store)
    stm.mark_consolidated('u1', 'st1', 'commit-1')  # must not raise
    assert not store.exists('users/u1/short_term/st1')  # no doc created


def test_updates_when_doc_exists(monkeypatch):
    store = FakeDocumentStore()
    store.set('users/u1/short_term/st1', {'status': 'pending'})
    monkeypatch.setattr(stm, '_store', lambda: store)
    stm.mark_consolidated('u1', 'st1', 'commit-1')
    written = store.get('users/u1/short_term/st1').to_dict()
    assert written['status'] == 'consolidated' and written['consolidated_commit_id'] == 'commit-1'
