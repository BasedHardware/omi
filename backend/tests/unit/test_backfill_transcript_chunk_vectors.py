"""scripts/backfill_transcript_chunk_vectors.py: what it indexes, and that readers can hydrate it."""

from datetime import datetime, timezone

from scripts.backfill_transcript_chunk_vectors import backfill_user, chunks_for
from utils.conversations.transcript_chunks import build_transcript_chunks

STARTED = datetime(2026, 3, 10, 15, 0, tzinfo=timezone.utc)


def _row(cid='c1', text='The invoice total was forty-seven dollars.', **fields):
    row = {
        'id': cid,
        'status': 'completed',
        'discarded': False,
        'started_at': STARTED,
        'created_at': datetime(2026, 3, 10, 16, 0, tzinfo=timezone.utc),
        'transcript_segments': [{'text': text, 'is_user': True, 'start': 0.0, 'end': 2.0}],
    }
    row.update(fields)
    return row


def test_chunks_match_what_search_readers_rebuild():
    """hydrate_chunk_texts rebuilds from started_at or created_at; indexed chunk_index must map to the same text."""
    row = _row()
    reader = {c['chunk_index']: c['text'] for c in build_transcript_chunks(row['transcript_segments'], STARTED)}
    written = chunks_for(row)
    assert written and all(reader[c['chunk_index']] == c['text'] for c in written)
    assert 'forty-seven dollars' in written[0]['text']


def test_ineligible_rows_are_skipped():
    for row in (
        _row(discarded=True),
        _row(deleted=True),
        _row(status='processing'),
        _row(text='   '),
        {**_row(), 'transcript_segments': None},
    ):
        assert chunks_for(row) == [], row


def test_dry_run_counts_without_writing():
    calls = []
    summary = backfill_user(
        'u1', [_row('a'), _row('b', discarded=True)], apply=False, upsert=lambda *a: calls.append(a) or 1
    )
    assert calls == []
    assert summary.as_dict() == {
        'apply': False,
        'scanned_conversations': 2,
        'conversations_with_chunks': 1,
        'chunks': 1,
        'upserted_vectors': 0,
        'failed_conversations': 0,
    }


def test_apply_upserts_each_eligible_conversation_and_survives_one_failure():
    calls = []

    def upsert(uid, conversation_id, chunks):
        calls.append((uid, conversation_id))
        if conversation_id == 'bad':
            raise RuntimeError('pinecone unavailable')
        return len(chunks)

    summary = backfill_user('u1', [_row('a'), _row('bad'), _row('c')], apply=True, upsert=upsert)
    assert calls == [('u1', 'a'), ('u1', 'bad'), ('u1', 'c')]
    assert (summary.upserted, summary.failed) == (2, 1)


def test_limit_bounds_indexed_conversations():
    calls = []
    summary = backfill_user(
        'u1',
        [_row('skip', discarded=True), _row('a'), _row('b'), _row('c')],
        apply=True,
        upsert=lambda uid, cid, chunks: calls.append(cid) or 1,
        limit=2,
    )
    assert calls == ['a', 'b']
    assert summary.eligible == 2
