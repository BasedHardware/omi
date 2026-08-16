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

from unittest.mock import MagicMock

import database.short_term_memories as stm


def _fake_db(doc_ref):
    fake = MagicMock()
    fake.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref
    return fake


def test_noop_when_doc_absent(monkeypatch):
    doc_ref = MagicMock()
    doc_ref.get.return_value.exists = False
    monkeypatch.setattr(stm, 'db', _fake_db(doc_ref))
    stm.mark_consolidated('u1', 'st1', 'commit-1')  # must not raise
    doc_ref.update.assert_not_called()


def test_updates_when_doc_exists(monkeypatch):
    doc_ref = MagicMock()
    doc_ref.get.return_value.exists = True
    monkeypatch.setattr(stm, 'db', _fake_db(doc_ref))
    stm.mark_consolidated('u1', 'st1', 'commit-1')
    doc_ref.update.assert_called_once()
    written = doc_ref.update.call_args.args[0]
    assert written['status'] == 'consolidated' and written['consolidated_commit_id'] == 'commit-1'
