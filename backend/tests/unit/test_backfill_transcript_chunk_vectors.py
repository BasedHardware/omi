"""scripts/backfill_transcript_chunk_vectors.py: what it indexes, and that readers can hydrate it."""

from datetime import datetime, timezone

import database.vector_db as vector_db
from scripts import backfill_transcript_chunk_vectors as script
from scripts.backfill_transcript_chunk_vectors import backfill_user, chunks_for
from utils.conversations.transcript_chunks import build_transcript_chunks

STARTED = datetime(2026, 3, 10, 15, 0, tzinfo=timezone.utc)


def _always(uid, conversation_id):
    return True


def _never_delete(uid, conversation_id):
    raise AssertionError('a live conversation must keep its chunks')


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
        'u1',
        [_row('a'), _row('b', discarded=True)],
        apply=False,
        upsert=lambda *a: calls.append(a) or 1,
        exists=_always,
        delete=_never_delete,
    )
    assert calls == []
    assert summary.as_dict() == {
        'apply': False,
        'scanned_conversations': 2,
        'conversations_with_chunks': 1,
        'chunks': 1,
        'upserted_vectors': 0,
        'removed_after_delete': 0,
        'failed_conversations': 0,
    }


def test_apply_upserts_each_eligible_conversation_and_survives_one_failure():
    calls = []

    def upsert(uid, conversation_id, chunks):
        calls.append((uid, conversation_id))
        if conversation_id == 'bad':
            raise RuntimeError('pinecone unavailable')
        return len(chunks)

    summary = backfill_user(
        'u1', [_row('a'), _row('bad'), _row('c')], apply=True, upsert=upsert, exists=_always, delete=_never_delete
    )
    assert calls == [('u1', 'a'), ('u1', 'bad'), ('u1', 'c')]
    assert (summary.upserted, summary.failed) == (2, 1)


def test_limit_bounds_indexed_conversations():
    calls = []
    summary = backfill_user(
        'u1',
        [_row('skip', discarded=True), _row('a'), _row('b'), _row('c')],
        apply=True,
        upsert=lambda uid, cid, chunks: calls.append(cid) or 1,
        exists=_always,
        delete=_never_delete,
        limit=2,
    )
    assert calls == ['a', 'b']
    assert summary.eligible == 2


def test_a_zero_or_partial_upsert_is_a_failure_not_success():
    """The vector writer returns 0 when no index is configured; that must not read as success."""
    for written in (0, 1):
        two_chunks = _row('a', text='x')
        two_chunks['transcript_segments'] = [{'text': f'line {i}', 'is_user': True} for i in range(14)]
        expected = len(chunks_for(two_chunks))
        assert expected == 2
        summary = backfill_user(
            'u1',
            [two_chunks],
            apply=True,
            upsert=lambda uid, cid, chunks: written,
            exists=_always,
            delete=_never_delete,
        )
        assert (summary.upserted, summary.failed) == (written, 1), written


def test_a_conversation_deleted_during_indexing_loses_the_chunks_just_written():
    """Deletion removes the row, then its vectors; an upsert landing after that cleanup must be undone."""
    vectors = set()
    rows = {'gone', 'kept'}

    def upsert(uid, cid, chunks):
        if cid == 'gone':
            rows.discard('gone')  # user deletes the row, and its vector cleanup finds nothing yet
        vectors.update(f'{cid}-c{c["chunk_index"]}' for c in chunks)
        return len(chunks)

    deleted = []

    def delete(uid, cid):
        deleted.append(cid)
        vectors.difference_update({v for v in vectors if v.startswith(f'{cid}-')})

    summary = backfill_user(
        'u1',
        [_row('gone'), _row('kept')],
        apply=True,
        upsert=upsert,
        exists=lambda uid, cid: cid in rows,
        delete=delete,
    )
    assert deleted == ['gone']
    assert vectors == {'kept-c0'}
    assert (summary.removed_after_delete, summary.failed) == (1, 0)


def test_a_failed_cleanup_after_delete_is_a_failure():
    def delete(uid, cid):
        raise RuntimeError('pinecone unavailable')

    summary = backfill_user(
        'u1', [_row('gone')], apply=True, upsert=lambda *a: 1, exists=lambda *a: False, delete=delete
    )
    assert (summary.removed_after_delete, summary.failed) == (0, 1)


def test_apply_refuses_to_start_without_a_vector_index(monkeypatch, capsys):
    monkeypatch.setattr(vector_db, 'index', None)
    monkeypatch.setattr('sys.argv', ['backfill', '--uid', 'u1', '--apply'])
    assert script.main() == 2
    assert 'no vector index is configured' in capsys.readouterr().err
