"""Current retrieval evidence and bounded attention deferral after main merge."""

from datetime import datetime, timedelta, timezone

import pytest

from config.dream_agent import Caps
from database import dream_store
from models.dream_agent import Edit
from tests.support.dream_firestore import DreamFirestore
from utils import dream_grounding, dream_reads
from utils.dream_context import EvidenceRecords


@pytest.mark.parametrize(
    'support',
    [
        {
            'structured': {
                'sections': [{'heading': 'Invented dish', 'body_markdown': 'Zuvrah is the confirmed spelling.'}]
            }
        },
        {'transcript_segments': [{'text': 'Zuvrah is the confirmed spelling.'}]},
        {'ocrText': 'Zuvrah is the confirmed spelling.'},
        {'ocr_text': 'Zuvrah is the confirmed spelling.'},
    ],
)
def test_admitted_context_can_ground_only_cited_independent_spelling(support):
    ref = 'screen/synthetic' if 'ocrText' in support or 'ocr_text' in support else 'conversations/neighbour'
    rows = EvidenceRecords(
        {'conversations/film': {'transcript_segments': [{'text': 'The invented name is Zuvra.'}]}, ref: support},
        targets={'conversations/film'},
    )
    edit = Edit(
        kind='spelling',
        target='conversations/film',
        before='Zuvra',
        after='Zuvrah',
        reason='Invented independent confirmation',
        evidence=list(rows),
    )
    assert dream_grounding.spelling_grounding_rejection(edit, rows) is None
    assert (
        dream_grounding.spelling_grounding_rejection(edit.model_copy(update={'evidence': ['conversations/film']}), rows)
        == 'ungrounded_spelling'
    )
    support['conversation_id'] = 'film'
    assert dream_grounding.spelling_grounding_rejection(edit, rows) == 'ungrounded_spelling'


def test_attention_deferral_does_not_restore_a_full_queue_settlement_scan(monkeypatch):
    uid = 'synthetic-bounded-deferral'
    now = datetime(2030, 1, 1, 23, 30, tzinfo=timezone.utc)
    lease = {
        'run_id': 'synthetic',
        'started_at': now,
        'day': '2030-01-01',
        'mode': 'on',
        'score': 1,
        'watermark': dream_store.EPOCH,
        'dirty_dropped': 0,
        'dirty_dropped_reported': 0,
    }
    db = DreamFirestore()
    db.rows[('dream_users', uid)] = {'lease': lease, 'score': 1}
    for i in range(500):
        db.rows[('dream_users', uid, 'dirty', dream_store.dirty_id('conversations', str(i)))] = {
            'collection': 'conversations',
            'id': str(i),
            'version': str(i),
            'last_changed_at': now,
        }
    queries = []
    original = dream_store.dirty_refs

    def query(*a, **kw):
        queries.append(kw)
        return original(*a, **kw)

    monkeypatch.setattr(dream_store, 'dirty_refs', query)
    monkeypatch.setattr(dream_store.firestore, 'transactional', lambda fn: fn)
    dream_store.finish(uid, lease, {}, success=True, deferred={'conversations/0'}, now=now, firestore_client=db)
    assert not queries
    dirty = {path: row for path, row in db.rows.items() if 'dirty' in path}
    assert len(dirty) == 500
    path = ('dream_users', uid, 'dirty', dream_store.dirty_id('conversations', '0'))
    assert dirty[path]['deferred_until'] == datetime(2030, 1, 2, tzinfo=timezone.utc)
    assert sum('deferred_until' in row for row in dirty.values()) == 1
    assert len(db.reads) < 6


def test_paused_ref_is_excluded_from_retrieval_without_hydration(monkeypatch):
    uid = 'synthetic-paused-context'
    now = datetime(2030, 1, 1, 23, 30, tzinfo=timezone.utc)
    db = DreamFirestore()
    for key in ('paused', 'healthy'):
        db.rows[('dream_users', uid, 'dirty', dream_store.dirty_id('conversations', key))] = {
            'collection': 'conversations',
            'id': key,
            'version': key,
            'last_changed_at': now - timedelta(seconds=2 if key == 'paused' else 1),
            **({'deferred_until': now + timedelta(hours=1)} if key == 'paused' else {}),
        }
    monkeypatch.setattr(dream_store, 'get_firestore_client', lambda: db)
    reads, excluded = [], []
    monkeypatch.setattr(dream_reads, 'read_record', lambda uid, ref, **kw: reads.append(ref) or {'name': 'Garden boat'})

    def candidates(*a, pending_refs, **kw):
        excluded.extend(pending_refs)
        return []

    monkeypatch.setattr(dream_reads, 'context_candidates', candidates)
    rows, consumed = dream_reads.read_changes(uid, {'started_at': now}, Caps())
    assert rows.targets == {'conversations/healthy'} and len(consumed) == 1
    assert reads == ['conversations/healthy']
    assert 'conversations/paused' in excluded
