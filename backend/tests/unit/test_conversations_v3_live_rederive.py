"""Per-owner live re-derive: fragmented live v3 windows replanned from their sources, and undone exactly.

Synthetic data only. The real loader, planner, commit transaction and undo transaction run against the
strict in-memory Firestore; only the outline model, speaker evidence and the started_at range read
(which the strict fixture does not model) are stood in for.
"""

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from database import conversations_v3 as store
from database import conversations_v3_backfill_runs as runs
from database import conversations_v3_leases as leases
from database import conversations_v3_rederive as rederive_store
from utils.conversations.v3 import backfill, service
from tests.unit.fixtures.strict_firestore_transaction import (
    StrictFirestoreCollection,
    StrictFirestoreDocument,
    StrictFirestoreSnapshot,
)
from tests.unit.test_conversations_v3_transactions import strict  # noqa: F401

UID = 'synthetic'
RUN = 'run-live-1'
AT = datetime(2026, 11, 19, 7, 50, tzinfo=timezone.utc)
SINCE, UNTIL = AT - timedelta(hours=1), AT + timedelta(hours=2)


def path(cid):
    return ('users', UID, 'conversations', cid)


def source(rid, start, seconds=60, words=10, **extra):
    """A sealed live recording: one segment, one audio file over its whole span."""
    return {
        'id': rid,
        'recording': True,
        'source': 'omi',
        'status': 'completed',
        'started_at': start,
        'finished_at': start + timedelta(seconds=seconds),
        'language': 'en',
        'transcript_segments': [
            {'id': rid + '-s', 'text': ' '.join(['word'] * words), 'start': 0.0, 'end': float(seconds), 'is_user': True}
        ],
        'audio_files': [{'id': 'f-' + rid, 'duration': float(seconds), 'started_at': start}],
        'claims': [],
        **extra,
    }


def fragment(cid, src, **extra):
    """A finished live v3 row that owns all of one source, as the pre-fix builder left it."""
    start, end = src['started_at'], src['finished_at']
    seconds = (end - start).total_seconds()
    src['claims'].append({'conversation_id': cid, 'start': start, 'end': end})
    return {
        'id': cid,
        'v3_derived': True,
        'source': 'omi',
        'status': 'completed',
        'tile_state': 'done',
        'kind': 'conversation',
        'outline_kind': 'conversation',
        'created_at': start,
        'started_at': start,
        'finished_at': end,
        'manual_end': True,
        'home_hidden': False,
        'home_hidden_reason': 'manual_end',
        'title_locked': True,
        'structured': {'title': 'Piece ' + cid, 'overview': 'Old notes'},
        'transcript_segments': [dict(s) for s in src['transcript_segments']],
        'v3_recording_ids': [src['id']],
        'recording_pieces': [
            {'recording_id': src['id'], 'audio_file_id': 'f-' + src['id'], 'start': 0.0, 'end': seconds}
        ],
        'audio_files': [],
        'v3_notes_written': True,
        **extra,
    }


def reply(*chapters):
    return json.dumps({'conversations': list(chapters)})


ONE_CHAPTER = reply({'first_line': 1, 'title': 'Lunch with the team', 'line': 'You ate.', 'kind': 'conversation'})


class RangeQuery:
    """The started_at range read the loader issues; the strict fixture models equality reads only."""

    def __init__(self, database, coll_path, filters=()):
        self.database, self.coll_path, self.filters = database, coll_path, filters

    def where(self, *, filter):
        return RangeQuery(self.database, self.coll_path, (*self.filters, filter))

    def order_by(self, *a, **kw):
        return self

    def limit(self, n):
        return self

    def stream(self):
        ops = {'>=': lambda a, b: a >= b, '<': lambda a, b: a < b}
        found = []
        for doc_path, row in self.database.rows.items():
            if doc_path[:-1] != self.coll_path:
                continue
            if all(
                row.get(f.field_path) is not None and ops[f.op_string](row[f.field_path], f.value) for f in self.filters
            ):
                snapshot = StrictFirestoreSnapshot(row)
                snapshot.reference = StrictFirestoreDocument(self.database, doc_path)
                found.append(snapshot)
        return iter(sorted(found, key=lambda s: s.to_dict()['started_at']))


@pytest.fixture
def owner(strict, monkeypatch):
    original_where = StrictFirestoreCollection.where

    def where(self, *args, filter=None):
        if filter is not None and filter.op_string in ('>=', '<'):
            return RangeQuery(self._database, self._path).where(filter=filter)
        return original_where(self, *args, filter=filter)

    monkeypatch.setattr(StrictFirestoreCollection, 'where', where)
    for module in (store, runs):
        monkeypatch.setattr(module, 'get_firestore_client', lambda: strict)
    monkeypatch.setattr(store, 'decrypt', lambda value, uid: value)
    monkeypatch.setattr(store, 'account_deletion_blocks_user_work', lambda *a, **kw: False)
    monkeypatch.setattr(
        store,
        'decode_row',
        lambda uid, snapshot: (
            {**snapshot.to_dict(), 'id': snapshot.id, '_v3_revision': snapshot.update_time} if snapshot.exists else None
        ),
    )

    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    for module in (service, backfill):
        monkeypatch.setattr(module, 'run_blocking', blocking)
    monkeypatch.setattr(service.context, 'outline_sources', lambda *a: ({}, [], []))
    monkeypatch.setattr(service, 'enqueue', lambda *a, **kw: pytest.fail('a re-derive never wakes the live queue'))

    def hydrate(uid, recordings, windows):
        for row in recordings.values():
            row['_v3_wearer_recognized'] = True

    monkeypatch.setattr(service.visibility, 'hydrate_recognition', hydrate)
    monkeypatch.setattr(service.models, 'outline', lambda *a: ONE_CHAPTER)

    def seed(*docs):
        for doc in docs:
            strict.rows[path(doc['id'])] = deepcopy(doc)

    return seed


def conversations(strict):
    return {p[-1]: deepcopy(row) for p, row in strict.rows.items() if p[:3] == ('users', UID, 'conversations')}


async def rederive(report=None):
    report = {} if report is None else report
    outcome = await service.reconcile(UID, derive=True, live=True, since=SINCE, until=UNTIL, run_id=RUN, report=report)
    return outcome, report


def lunch(count=6, words=10, gap=0):
    """Contiguous one-minute captures that the pre-fix builder cut into one manual card each."""
    sources = [source(f'r{i}', AT + timedelta(seconds=(60 + gap) * i), words=words) for i in range(count)]
    sources[-1]['v3_manual_end'] = True
    rows = [fragment(f'c{i}', src) for i, src in enumerate(sources)]
    return sources, rows


def claims_by_row(rows):
    found = {}
    for cid, row in rows.items():
        for claim in row.get('claims') or []:
            found.setdefault(claim['conversation_id'], []).append((cid, claim['start'], claim['end']))
    return found


# ---- replans ----------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fragmented_lunch_folds_into_one_card_that_keeps_the_earliest_id(owner, strict):
    sources, rows = lunch()
    owner(*sources, *rows)
    outcome, report = await rederive()
    assert outcome == 'committed'
    after = conversations(strict)
    card = after['c0']
    # One card, the earliest absorbed id, all six sources' speech, the manual close kept at its end.
    assert card['v3_recording_ids'] == [s['id'] for s in sources]
    assert len(card['transcript_segments']) == 6 and card['manual_end'] is True and card['home_hidden'] is False
    assert card['backfilled'] is True and card['v3_rederive_live_run'] == RUN
    # Notes on the backfill's own marker; no live notes obligation, so no derived effects or created fanout.
    assert card['v3_backfill_process_pending'] is True and not card.get('v3_process_pending')
    for cid in ('c1', 'c2', 'c3', 'c4', 'c5'):
        retired = after[cid]
        assert retired['deleted'] is True and retired['discarded'] is True
        assert retired['sync_merged_into'] == 'c0' and retired['v3_derived'] is False
    # Every source names exactly the surviving card; no claim points at a retired row.
    held = claims_by_row({rid: after[rid] for rid in (s['id'] for s in sources)})
    assert set(held) == {'c0'} and sorted(r for r, _a, _b in held['c0']) == [s['id'] for s in sources]
    # One audio piece per source file, none repeated.
    pieces = [(p['recording_id'], p['audio_file_id'], p['start'], p['end']) for p in card['recording_pieces']]
    assert len(pieces) == len(set(pieces)) == 6
    assert report['rows_eligible'] == 6 and report['windows_after'] == 1 and report['rows_retired'] == 5
    assert report['visible_before'] == 6 and report['visible_after'] == 1 and report['outline_calls'] == 1


@pytest.mark.asyncio
async def test_hidden_topic_pieces_of_one_stretch_become_one_visible_card(owner, strict, monkeypatch):
    # Eight 50-word captures over eight minutes; the pre-fix planner hid each topic piece (< 300 words).
    sources = [source(f'r{i}', AT + timedelta(minutes=i), words=50) for i in range(8)]
    rows = [
        fragment(f'c{i}', src, manual_end=False, home_hidden=True, home_hidden_reason='below_word_minimum')
        for i, src in enumerate(sources)
    ]
    owner(*sources, *rows)
    topics = reply(
        *({'first_line': line, 'title': f'Topic {line}', 'line': '', 'kind': 'conversation'} for line in (1, 3, 5, 7))
    )
    monkeypatch.setattr(service.models, 'outline', lambda *a: topics)
    outcome, report = await rederive()
    assert outcome == 'committed'
    after = conversations(strict)
    card = after['c0']
    assert card['home_hidden'] is False and card['home_hidden_reason'] == 'conversation'
    assert len(card['transcript_segments']) == 8
    # The short topics are sections of the one card, not cards of their own.
    assert len(card['structured']['sections']) >= 3
    assert all(after[f'c{i}']['sync_merged_into'] == 'c0' for i in range(1, 8))
    assert report['visible_before'] == 0 and report['visible_after'] == 1 and report['windows_after'] == 1


@pytest.mark.asyncio
async def test_a_second_pass_over_its_own_result_writes_nothing(owner, strict):
    sources, rows = lunch()
    owner(*sources, *rows)
    await rederive()
    # The run's notes finished.
    card = strict.rows[path('c0')]
    card.update(status='completed', tile_state='done', v3_backfill_process_pending=False)
    before = conversations(strict)
    writes = len(strict.transactions)
    outcome, report = await rederive()
    assert outcome == 'committed' and conversations(strict) == before
    assert report['rows_unchanged'] == 1 and report['rows_retired'] == 0 and report['priors_recorded'] == 0
    # Only the lease bookkeeping transaction ran, no row or source write.
    for tx in strict.transactions[writes:]:
        assert not any(p[2] == 'conversations' for p, _ in tx.sets + tx.updates) and not tx.deletes


# ---- what is never touched --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_open_windows_and_rows_over_until_are_untouched(owner, strict):
    sources, rows = lunch(count=4)
    # An open window on a recording the live builder still owes, and a closed row running past until.
    live = source('live', AT + timedelta(minutes=4), v3_pending=True, status='in_progress')
    late = source('late', UNTIL - timedelta(seconds=30), seconds=120)
    open_row = fragment('open', live, status='in_progress', tile_state='live', manual_end=False)
    late_row = fragment('late-row', late, manual_end=False)
    owner(*sources, *rows, live, late, open_row, late_row)
    before = conversations(strict)
    outcome, report = await rederive()
    assert outcome == 'committed'
    after = conversations(strict)
    for cid in ('open', 'late-row', 'live', 'late'):
        assert after[cid] == before[cid]
    assert after['c0']['v3_recording_ids'] == ['r0', 'r1', 'r2', 'r3']
    assert report['protected_open'] == 1 and report['protected_boundary'] == 1
    assert report['sources_blocked_unsealed'] == 1


@pytest.mark.asyncio
async def test_edited_and_locked_rows_are_skipped_and_their_speech_stays_with_them(owner, strict):
    sources, rows = lunch()
    rows[2]['user_title'] = 'My lunch title'
    rows[4]['is_locked'] = True
    owner(*sources, *rows)
    before = conversations(strict)
    outcome, report = await rederive()
    assert outcome == 'committed'
    after = conversations(strict)
    assert after['c2'] == before['c2'] and after['c4'] == before['c4']
    assert report['protected_edited'] == 1 and report['protected_locked'] == 1
    # Their sources still name only them; the rebuilt windows around them never repeat their speech.
    for rid, cid in (('r2', 'c2'), ('r4', 'c4')):
        assert {c['conversation_id'] for c in after[rid]['claims']} == {cid}
    rebuilt = [row for row in after.values() if row.get('v3_rederive_live_run') == RUN and not row.get('deleted')]
    assert rebuilt and all({'r2', 'r4'}.isdisjoint(row['v3_recording_ids']) for row in rebuilt)
    texts = [s['id'] for row in rebuilt for s in row['transcript_segments']]
    assert 'r2-s' not in texts and 'r4-s' not in texts and len(texts) == len(set(texts))


@pytest.mark.asyncio
async def test_speech_that_has_not_settled_refuses_before_any_paid_call(owner, strict, monkeypatch):
    now = datetime.now(timezone.utc)
    fresh = source('r0', now - timedelta(minutes=2))
    owner(fresh, fragment('c0', fresh))
    monkeypatch.setattr(service.models, 'outline', lambda *a: pytest.fail('paid for an open stretch'))
    report = {}
    outcome = await service.reconcile(
        UID, derive=True, live=True, since=now - timedelta(hours=1), until=now, run_id=RUN, report=report
    )
    assert outcome == 'blocked' and report['blocked_reason'] == 'rederive_live_open'


@pytest.mark.asyncio
async def test_speech_a_row_holds_that_its_sources_no_longer_produce_blocks_the_replan(owner, strict):
    sources, rows = lunch(count=3)
    rows[1]['transcript_segments'].append({'id': 'lost', 'text': 'only here', 'start': 5.0, 'end': 6.0})
    orphan = {**fragment('orphan', source('gone', AT + timedelta(minutes=20))), 'v3_recording_ids': []}
    owner(*sources, *rows, orphan)
    before = conversations(strict)
    outcome, report = await rederive()
    assert outcome == 'blocked' and report['blocked_reason'] == 'rederive_live_coverage'
    assert conversations(strict) == before and not priors(strict)
    # A row that names no source is never offered for a rebuild.
    assert report['protected_source_missing'] == 1


def test_protection_reasons():
    base = {
        'v3_derived': True,
        'status': 'completed',
        'started_at': AT,
        'finished_at': AT + timedelta(minutes=1),
    }
    window = {'since': SINCE, 'until': UNTIL}
    assert rederive_store.live_row_protection(base, **window) is None
    cases = {
        'deleted': {'deleted': True},
        'open': {'status': 'in_progress'},
        'boundary': {'finished_at': UNTIL + timedelta(seconds=1)},
        'backfilled': {'backfilled': True},
        'locked': {'is_locked': True},
        'private': {'data_protection_level': 'private'},
        'shared': {'visibility': 'shared'},
        'edited': {'starred': True},
        'discarded': {'discarded': True},
        'notes_pending': {'v3_process_pending': True},
    }
    for reason, patch in cases.items():
        assert rederive_store.live_row_protection({**base, **patch}, **window) == reason
    # A row an earlier live re-derive rebuilt is backfilled but may be rebuilt again.
    assert (
        rederive_store.live_row_protection({**base, 'backfilled': True, 'v3_rederive_live_run': 'old'}, **window)
        is None
    )
    # Its own run's notes marker does not protect a row from that run's resumed pass; another run's does.
    pending = {**base, 'backfilled': True, 'v3_rederive_live_run': RUN, 'v3_backfill_process_pending': True}
    assert rederive_store.live_row_protection(pending, **window, run_id=RUN) is None
    assert rederive_store.live_row_protection(pending, **window, run_id='other') == 'notes_pending'
    assert rederive_store.live_source_block({'recording': True, 'status': 'completed'}) is None
    assert (
        rederive_store.live_source_block({'recording': True, 'status': 'completed', 'v3_pending': True}) == 'unsealed'
    )
    assert rederive_store.live_source_block({'recording': True, 'status': 'completed', 'v3_backfill_run': 'r'}) == (
        'backfill_donor'
    )


# ---- undo -------------------------------------------------------------------------------------


class Ledger:
    def __init__(self):
        self.run = {'run_id': RUN, 'status': 'committed', 'mode': backfill.LIVE_MODE}

    def get(self, uid, run_id, **kw):
        return deepcopy(self.run)

    def update(self, uid, run_id, *, status=None, partition=None, patch=None, expect=None, firestore_client=None):
        if status:
            self.run['status'] = status
        self.run.update(patch or {})
        return self.run


def priors(strict):
    return [
        {**deepcopy(row), 'id': p[-1]}
        for p, row in strict.rows.items()
        if len(p) == 6 and p[:4] == ('users', UID, runs.COLLECTION, RUN) and p[4] == runs.PRIORS
    ]


@pytest.fixture
def ledger(strict, monkeypatch):
    book = Ledger()
    monkeypatch.setattr(runs, 'get_run', book.get)
    monkeypatch.setattr(runs, 'update_run', book.update)
    monkeypatch.setattr(runs, 'list_priors', lambda uid, run_id, **kw: priors(strict))
    erased = []

    def delete_conversation(uid, cid):
        # The production helper also erases child collections; here the document is the whole row.
        erased.append(cid)
        strict.rows.pop(path(cid), None)

    monkeypatch.setattr(backfill.conversations_db, 'delete_conversation', delete_conversation)
    book.erased = erased
    return book


@pytest.mark.asyncio
async def test_undo_restores_every_row_and_claim_exactly(owner, strict, ledger):
    sources, rows = lunch()
    rows[3]['user_title'] = 'Kept'
    extra = source('r9', AT + timedelta(minutes=30), words=400)
    owner(*sources, *rows, extra)
    before = conversations(strict)
    await rederive()
    changed = conversations(strict)
    assert changed != before and any(row.get('sync_merged_into') for row in changed.values())
    assert not any('r9' in (row.get('v3_recording_ids') or []) for row in before.values())
    assert any(row.get('v3_recording_ids') == ['r9'] for row in changed.values())
    # The partition settled: baselines recorded, and nothing the owner did since, so undo proceeds.
    assert rederive_store.record_baselines(UID, RUN) == len(priors(strict))
    result = backfill.undo_run(UID, RUN)
    assert result['outcome'] == 'undone' and result['rows_removed'] == 1
    # The created row leaves through the conversation deletion helper (children included).
    assert len(ledger.erased) == 1 and ledger.erased[0] not in before
    assert conversations(strict) == before
    assert ledger.run['status'] == 'undone'
    # Rerunning an undo changes nothing.
    assert backfill.undo_run(UID, RUN)['outcome'] == 'undone' and conversations(strict) == before


@pytest.mark.asyncio
async def test_undo_refuses_after_the_owner_deleted_a_rebuilt_row(owner, strict, ledger):
    sources, rows = lunch(count=3)
    owner(*sources, *rows)
    await rederive()
    after = conversations(strict)
    strict.rows[('users', UID, 'deleted_conversations', 'c0')] = {'conversation_id': 'c0'}
    result = backfill.undo_run(UID, RUN)
    assert result == {'outcome': 'busy', 'reason': 'owner_deleted_rebuilt_row'}
    assert conversations(strict) == after and ledger.run['undo']['reason'] == 'owner_deleted_rebuilt_row'


@pytest.mark.asyncio
@pytest.mark.parametrize('edit', [{'user_title': 'Renamed'}, {'starred': True}, {'has_photos': True}])
async def test_undo_refuses_after_the_owner_edited_a_rebuilt_or_created_row(owner, strict, ledger, edit):
    sources, rows = lunch(count=3)
    extra = source('r9', AT + timedelta(minutes=30), words=400)
    owner(*sources, *rows, extra)
    await rederive()
    created = next(cid for cid, row in conversations(strict).items() if row.get('v3_recording_ids') == ['r9'])
    for cid in ('c0', created):
        strict.rows[path(cid)].update(edit)
        after = conversations(strict)
        assert backfill.undo_run(UID, RUN) == {'outcome': 'busy', 'reason': 'owner_edited_rebuilt_row'}
        assert conversations(strict) == after and not ledger.erased
        for key in edit:
            strict.rows[path(cid)].pop(key)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'change',
    [
        {'structured': {'title': 'Lunch with the team', 'overview': 'Rewritten by the owner'}},
        {'deleted': True, 'discarded': True, 'sync_merged_into': 'merged-elsewhere'},
    ],
)
async def test_undo_refuses_after_a_summary_edit_or_merge_once_baselines_exist(owner, strict, ledger, change):
    sources, rows = lunch(count=3)
    owner(*sources, *rows)
    await rederive()
    rederive_store.record_baselines(UID, RUN)
    strict.rows[path('c0')].update(change)
    after = conversations(strict)
    assert backfill.undo_run(UID, RUN) == {'outcome': 'busy', 'reason': 'owner_edited_rebuilt_row'}
    assert conversations(strict) == after


@pytest.mark.asyncio
async def test_a_merge_of_a_rebuilt_row_before_baselines_also_refuses_undo(owner, strict, ledger):
    sources, rows = lunch(count=3)
    owner(*sources, *rows)
    await rederive()
    strict.rows[path('c0')].update(deleted=True, discarded=True, sync_merged_into='merged-elsewhere')
    assert backfill.undo_run(UID, RUN) == {'outcome': 'busy', 'reason': 'owner_edited_rebuilt_row'}


@pytest.mark.asyncio
async def test_a_window_crossing_until_blocks_and_writes_nothing(owner, strict):
    sources, rows = lunch(count=3)
    # Unclaimed speech that runs past until: its rebuilt window would cross the run's edge.
    crossing = source('r9', UNTIL - timedelta(seconds=60), seconds=120, words=400)
    owner(*sources, *rows, crossing)
    before = conversations(strict)
    outcome, report = await rederive()
    assert outcome == 'blocked' and report['blocked_reason'] == 'rederive_live_boundary'
    assert conversations(strict) == before and not priors(strict)


@pytest.mark.asyncio
async def test_a_prior_too_large_to_record_blocks_before_any_write(owner, strict):
    sources, rows = lunch(count=3)
    rows[1]['padding'] = 'x' * rederive_store.SOURCE_MAX_BYTES
    owner(*sources, *rows)
    before = conversations(strict)
    outcome, report = await rederive()
    assert outcome == 'blocked' and report['blocked_reason'] == 'document_too_large'
    assert conversations(strict) == before and not priors(strict)


@pytest.mark.asyncio
async def test_a_partition_over_the_transaction_write_cap_blocks(owner, strict, monkeypatch):
    sources, rows = lunch()
    owner(*sources, *rows)
    before = conversations(strict)
    monkeypatch.setattr(store, 'BATCH_MAX_WRITES', 8)
    outcome, report = await rederive()
    assert outcome == 'blocked' and report['blocked_reason'] == 'backfill_partition_budget'
    assert conversations(strict) == before and not priors(strict)


def padded(src, total):
    """A source whose stored document estimates at ``total`` bytes (the projection's size estimate)."""
    src = {**src, 'padding': ''}
    src['padding'] = 'x' * (total - rederive_store.stored_bytes(src))
    assert rederive_store.stored_bytes(src) == total
    return src


@pytest.mark.asyncio
async def test_a_source_at_the_document_limit_is_reported_up_front_and_left_alone(owner, strict):
    sources, rows = lunch(count=4)
    big = padded(sources[1], rederive_store.SOURCE_MAX_BYTES)
    sources[1] = big
    owner(*sources, *rows)
    est = backfill.estimate_live_partition(UID, {'since': SINCE, 'until': UNTIL}, 'dry-run', now=UNTIL)
    assert est['sources_blocked_size_limit'] == 1 and est['protected_source_blocked'] == 1
    before = conversations(strict)
    outcome, report = await rederive()
    assert outcome == 'committed' and report['sources_blocked_size_limit'] == 1
    after = conversations(strict)
    assert after['r1'] == before['r1'] and after['c1'] == before['c1']


@pytest.mark.asyncio
async def test_a_claims_update_that_would_grow_a_source_past_the_limit_blocks_before_any_write(
    owner, strict, monkeypatch
):
    sources, rows = lunch(count=3)
    # Unclaimed speech on a source the loader admits (no claim headroom): its new claim crosses the limit.
    monkeypatch.setattr(rederive_store, 'CLAIM_BYTES', 0)
    extra = padded(source('r9', AT + timedelta(minutes=30), words=400), rederive_store.SOURCE_MAX_BYTES - 20)
    owner(*sources, *rows, extra)
    before = conversations(strict)
    outcome, report = await rederive()
    assert outcome == 'blocked' and report['blocked_reason'] == 'document_too_large'
    assert conversations(strict) == before and not priors(strict)


@pytest.mark.asyncio
async def test_a_commit_that_fails_midway_resumes_and_undoes_exactly(owner, strict, ledger, monkeypatch):
    from google.api_core.exceptions import InvalidArgument

    sources, rows = lunch()
    extra = source('r9', AT + timedelta(minutes=30), words=400)
    owner(*sources, *rows, extra)
    before = conversations(strict)
    # One row per commit batch, and the second batch's transaction fails at Firestore's size limit.
    monkeypatch.setattr(store, 'BATCH_ROW_BYTES', 1)
    run_transaction = store.firestore.transactional
    commits = []

    def transactional(body):
        inner = run_transaction(body)

        def run(tx, *args, **kwargs):
            if body.__name__ == 'commit':
                commits.append(1)
                if len(commits) == 2:
                    raise InvalidArgument('Document exceeds the maximum allowed size')
            return inner(tx, *args, **kwargs)

        return run

    monkeypatch.setattr(store.firestore, 'transactional', transactional)
    outcome, report = await rederive()
    assert outcome == 'blocked' and report['blocked_reason'] == 'document_too_large'
    partial = conversations(strict)
    assert partial != before and partial['c0']['v3_rederive_live_run'] == RUN
    # Retirement happens only in the final batch, which failed: the absorbed rows are untouched so far.
    assert all(partial[f'c{i}'] == before[f'c{i}'] for i in range(1, 6))
    # Undo from the partial state is exact.
    assert backfill.undo_run(UID, RUN)['outcome'] == 'undone'
    assert conversations(strict) == before
    # The same partial failure, then a resume that finishes, is still undone exactly.
    commits.clear()
    ledger.run['status'] = 'committed'
    assert (await rederive())[0] == 'blocked'
    monkeypatch.setattr(store.firestore, 'transactional', run_transaction)
    outcome, report = await rederive()
    assert outcome == 'committed' and conversations(strict)['c1']['sync_merged_into'] == 'c0'
    assert backfill.undo_run(UID, RUN)['outcome'] == 'undone'
    assert conversations(strict) == before


@pytest.mark.asyncio
async def test_undo_waits_for_a_newer_run_over_the_same_rows(owner, strict, ledger):
    sources, rows = lunch(count=3)
    owner(*sources, *rows)
    await rederive()
    strict.rows[path('c0')]['v3_rederive_live_run'] = 'newer-run'
    assert backfill.undo_run(UID, RUN) == {'outcome': 'busy', 'reason': 'undo_newer_run_first'}


def test_undo_groups_restore_rows_sharing_a_source_together():
    entries = [
        {'id': 'a', 'claims': [{'recording_id': 's1'}], 'sources': ['s1']},
        {'id': 'b', 'claims': [{'recording_id': 's2'}], 'sources': ['s1', 's2']},
        {'id': 'c', 'claims': [{'recording_id': 's3'}], 'sources': ['s3']},
    ]
    groups = sorted(sorted(e['id'] for e in group) for group in backfill._undo_groups(entries))
    assert groups == [['a', 'b'], ['c']]


# ---- dry-run and operator -----------------------------------------------------------------------


def test_dry_run_preview_counts_before_and_after_and_writes_nothing(owner, strict):
    sources, rows = lunch()
    owner(*sources, *rows)
    before = deepcopy(strict.rows)
    est = backfill.estimate_live_partition(UID, {'since': SINCE, 'until': UNTIL}, 'dry-run', now=UNTIL)
    assert strict.rows == before and not strict.transactions
    assert est['rows_eligible'] == 6 and est['visible_before'] == 6
    assert est['windows_after'] == 1 and est['visible_after'] == 1 and est['rows_retired_est'] == 5
    assert est['outline_calls'] == 1 and est['usd'] > 0


def test_operator_dry_run_prints_the_preview_without_uids(tmp_path, monkeypatch, capsys):
    from scripts import conversations_v3_backfill as script

    secret_uid = 'synthetic-owner-uid-123'
    owners = tmp_path / 'owners.txt'
    owners.write_text(secret_uid + '\n')
    meta = [{'id': 'r0', 'recording': True, 'started_at': AT, 'finished_at': AT + timedelta(minutes=1)}]
    monkeypatch.setattr(store, 'backfill_window_metadata', lambda *a: meta)
    monkeypatch.setattr(
        backfill,
        'estimate_live_partition',
        lambda *a, **kw: {
            'rows_eligible': 18,
            'visible_before': 18,
            'windows_after': 1,
            'visible_after': 1,
            'rows_retired_est': 17,
            'outline_calls': 1,
            'notes_calls': 1,
            'short_task_calls': 0,
            'usd': 0.01,
        },
    )
    monkeypatch.setattr(runs, 'list_runs', lambda uid: [])
    monkeypatch.setattr(backfill, 'create_run', lambda *a, **kw: pytest.fail('dry-run wrote a run'))
    args = ['run', '--owners-file', str(owners), '--mode', 'rederive-live', '--dry-run']
    assert script.main([*args, '--since', SINCE.isoformat(), '--until', UNTIL.isoformat()]) == 0
    out = capsys.readouterr().out
    assert secret_uid not in out
    assert 'windows=18->1' in out and 'visible=18->1' in out and 'rows_retired_est=17' in out and 'llm_calls=2' in out
    # The live edge is the live builder's.
    with pytest.raises(SystemExit):
        script.main([*args, '--days', '1'])


@pytest.mark.asyncio
async def test_a_live_run_step_replans_with_the_live_loader(monkeypatch):
    calls = []

    async def reconcile(uid, **kw):
        calls.append(kw)
        return 'committed'

    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    run = {
        'run_id': RUN,
        'status': 'planned',
        'mode': backfill.LIVE_MODE,
        'partitions': [{'since': SINCE, 'until': UNTIL, 'status': 'pending'}],
    }
    monkeypatch.setattr(backfill, 'run_blocking', blocking)
    monkeypatch.setattr(runs, 'get_run', lambda *a, **kw: deepcopy(run))
    monkeypatch.setattr(runs, 'update_run', lambda *a, **kw: run)
    monkeypatch.setattr(service, 'reconcile', reconcile)
    baselines = []
    monkeypatch.setattr(backfill.rederive_store, 'record_baselines', lambda uid, run_id: baselines.append(run_id))
    monkeypatch.setattr(
        service, 'drain_backfill', lambda *a, **kw: _done({'processed': 0, 'failed': 0, 'remaining': 0})
    )
    await backfill.run_step(UID, RUN, 0, 'derive')
    assert calls[0]['live'] is True and calls[0]['derive'] is True and calls[0]['rederive'] is False
    # The settled partition records the owner-surface baselines undo compares against.
    assert baselines == [RUN]


async def _done(value):
    return value


def test_undo_takes_the_backfill_lease_before_anything_else(monkeypatch):
    seen = []
    monkeypatch.setattr(runs, 'update_run', lambda *a, **kw: {})
    monkeypatch.setattr(leases, 'acquire', lambda uid, key, **kw: seen.append(key) or None)
    assert backfill.undo_live_run(UID, RUN) == {'outcome': 'busy', 'reason': 'backfill_pass_in_flight'}
    assert seen == [store.BACKFILL_LEASE]
