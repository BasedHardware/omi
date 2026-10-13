"""Unavailable speech, pendant fragments and accented lexical retrieval."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
import unicodedata

import pytest

from config.dream_agent import Caps
from database.dream_context_reads import temporal_neighbours
from tests.support.firestore_shape_recorder import RecordingFirestore
from utils import dream_context, dream_reads
from utils.conversations import search


@pytest.mark.parametrize('direction', [-1, 1])
def test_temporal_filters_unavailable_fragments_before_nearest_four(direction):
    now = datetime(2030, 1, 1, 12, tzinfo=timezone.utc)
    db = RecordingFirestore()
    unavailable = [
        db.snapshot(
            f'users/synthetic/conversations/fragment-{i}',
            {'created_at': now + timedelta(minutes=direction * (i + 1)), **flags},
        )
        for i, flags in enumerate([{'discarded': True}, {'deleted': True}, {'is_locked': True}, {'discarded': True}])
    ]
    healthy = [
        db.snapshot(
            f'users/synthetic/conversations/context-{i}',
            # Healthy legacy documents may omit every availability flag.
            {'created_at': now + timedelta(minutes=direction * (i + 5))},
        )
        for i in range(4)
    ]
    db.queue_results(unavailable + healthy if direction < 0 else [])
    db.queue_results(unavailable + healthy if direction > 0 else [])
    rows = temporal_neighbours(
        'synthetic', 'conversations', now - timedelta(days=1), now, now + timedelta(days=1), firestore_client=db
    )
    assert [row['id'] for row in rows] == [f'context-{i}' for i in range(4)]
    assert len(db.shapes) == 2
    assert all(shape.limit == 12 for shape in db.shapes)
    assert all(set(shape.projection) == {'created_at', 'discarded', 'deleted', 'is_locked'} for shape in db.shapes)


@pytest.mark.parametrize('function_words', ['không của này kia là và với', 'khong cua nay kia la va voi'])
def test_vietnamese_stopwords_cannot_displace_content_anchors(function_words):
    terms = dream_context.query_terms({'content': function_words + ' bún bò Huế garden boat'})
    assert terms[:3] == ['bún', 'bò', 'huế']
    assert not set(terms) & {'không', 'của', 'này', 'khong', 'cua', 'nay'}
    assert dream_context.query_terms({'content': function_words}) == []


@pytest.mark.parametrize('normalization', ['NFC', 'NFD'])
def test_accented_terms_reach_the_typesense_query_unchanged(monkeypatch, normalization):
    query = ' '.join(
        dream_context.query_terms({'content': unicodedata.normalize(normalization, 'Không của này bún bò Huế')})
    )
    provider = Mock(return_value={'hits': [], 'found': 0})
    monkeypatch.setattr(
        search,
        '_typesense_client',
        SimpleNamespace(collections={'conversations': SimpleNamespace(documents=SimpleNamespace(search=provider))}),
    )
    assert search.keyword_search_conversation_ids('synthetic', query, raise_on_error=True) == []
    params = provider.call_args.args[0]
    assert params['q'] == 'bún bò huế'
    assert params['filter_by'] == 'userId:=synthetic && discarded:=false'


def test_bad_transcript_does_not_block_the_next_dirty_target(monkeypatch):
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    items = [
        {'collection': 'conversations', 'id': key, 'version': key, 'last_changed_at': now} for key in ('bad', 'healthy')
    ]
    snapshots = [SimpleNamespace(to_dict=lambda item=item: item) for item in items]
    dirty = Mock(return_value=snapshots)
    monkeypatch.setattr(dream_reads.dream_store, 'dirty_refs', dirty)
    monkeypatch.setattr(dream_reads, 'context_candidates', lambda *a, **k: [])

    def read(uid, ref, **kwargs):
        if ref.endswith('/bad'):
            raise dream_reads.DreamTranscriptReadError('Invented unreadable speech')
        return {'transcript_segments': [{'text': 'Garden boat'}]}

    monkeypatch.setattr(dream_reads, 'read_record', read)
    report, unavailable = {}, []
    records, consumed = dream_reads.read_changes(
        'synthetic', {'started_at': now}, Caps(), diagnostics=report, unavailable=unavailable
    )
    assert records.targets == {'conversations/healthy'}
    assert consumed == [items[1]]
    assert unavailable == [{**items[0], 'transient': True}]
    assert report['dirty_counts']['failed'] == report['dirty_counts']['transient'] == 1
    dirty.assert_called_once_with('synthetic', limit=32, newest=False)
