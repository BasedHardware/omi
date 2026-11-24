"""Per-owner live re-derive: fragmented live v3 windows replanned from their sources, and undone exactly.

Synthetic data only. The real loader, planner, commit transaction and undo transaction run against the
strict in-memory Firestore; only the outline model, speaker evidence and the started_at range read
(which the strict fixture does not model) are stood in for.
"""

import asyncio
import json
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import InvalidArgument

from database import action_items as tasks_db
from database import conversations as conversations_db
from database import conversations_v3 as store
from database import conversations_v3_backfill_runs as runs
from database import conversations_v3_leases as leases
from database import conversations_v3_rederive as rederive_store
from database.account_deletion_marker import account_deletion_document
from database.conversations_v3_undo_removals import removal_ref
from models.conversation import SetConversationEventsStateRequest
from routers import conversations as conversation_routes
from scripts import conversations_v3_backfill as script
from services import conversation_frame_evidence
from utils.conversations import merge_conversations
from utils.conversations.v3 import Conflict, backfill, service
from utils.other import lake_wipe
from utils.retrieval.tool_services import action_items as task_service
from utils.task_intelligence import task_source_validation
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
        'structured': {
            'title': 'Piece ' + cid,
            'overview': 'Old notes',
            'sections': [{'heading': 'Piece ' + cid, 'body_markdown': 'Old notes'}],
        },
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
    # The strict fixture models no ordered pages; the run's priors are read straight from its rows.
    monkeypatch.setattr(runs, 'list_priors', lambda uid, run_id, **kw: priors(strict, run_id))

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


@pytest.fixture
def edit_embedded_items(strict, monkeypatch):
    @store.firestore.transactional
    def write(tx, uid, cid, patch):
        tx.update(store.user_conversations(strict, uid).document(cid), patch)

    monkeypatch.setattr(conversations_db, 'update_conversation', lambda *args: write(strict.transaction(), *args))
    return conversations_db.update_conversation_action_items


@pytest.fixture
def set_event_created(strict, monkeypatch):
    @store.firestore.transactional
    def write(tx, ref, patch):
        tx.update(ref, patch)

    monkeypatch.setattr(
        StrictFirestoreDocument, 'update', lambda ref, patch: write(strict.transaction(), ref, patch), raising=False
    )
    monkeypatch.setattr(conversations_db, 'db', strict)
    monkeypatch.setattr(conversations_db, 'invalidate_people_stats_cache', lambda uid: None)
    monkeypatch.setattr(conversations_db, '_sync_conversation_search_index', lambda uid, cid: None)

    def read_card(uid, cid):
        # The synthetic projection only stubs audio, which this PATCH does not use.
        card = deepcopy(strict.rows[path(cid)])
        card['audio_files'] = []
        return card

    monkeypatch.setattr(conversation_routes, '_get_valid_conversation_by_id', read_card)

    def patch_event(cid, created):
        data = SetConversationEventsStateRequest(events_idx=[0], values=[created])
        assert conversation_routes.set_conversation_events_state(cid, data, uid=UID) == {'status': 'Ok'}

    return patch_event


def claims_by_row(rows):
    found = {}
    for cid, row in rows.items():
        for claim in row.get('claims') or []:
            found.setdefault(claim['conversation_id'], []).append((cid, claim['start'], claim['end']))
    return found


# ---- replans ----------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,hidden', [(None, False), ('off', True)])
async def test_manual_end_home_switch_reaches_the_planner_through_reconcile(owner, strict, monkeypatch, mode, hidden):
    if mode is None:
        monkeypatch.delenv('CONVERSATIONS_V3_MANUAL_END_HOME_VISIBLE', raising=False)
    else:
        monkeypatch.setenv('CONVERSATIONS_V3_MANUAL_END_HOME_VISIBLE', mode)
    media = reply({'first_line': 1, 'title': 'A podcast', 'line': 'Playback.', 'kind': 'media'})
    monkeypatch.setattr(service.models, 'outline', lambda uid, messages: media)
    sources, rows = lunch()
    owner(*sources, *rows)
    outcome, _ = await rederive()
    assert outcome == 'committed'
    card = conversations(strict)['c0']
    assert card['manual_end'] is True and card['kind'] == card['outline_kind'] == 'media'
    assert card['home_hidden'] is hidden and card['home_hidden_reason'] == 'media'


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
        # As a sync merge's absorbed row: claims transferred, and cached copies see a new revision.
        assert retired['v3_claims_transferred_to'] == 'c0' and retired['sync_content_revision'] == 1
        assert retired['summary_due_at'] is None
    # The survivor lists its bridges, so deleting it purges them (the sync merge contract).
    assert card['sync_merged_from'] == ['c1', 'c2', 'c3', 'c4', 'c5']
    # Every source names exactly the surviving card; no claim points at a retired row.
    held = claims_by_row({rid: after[rid] for rid in (s['id'] for s in sources)})
    assert set(held) == {'c0'} and sorted(r for r, _a, _b in held['c0']) == [s['id'] for s in sources]
    # One audio piece per source file, none repeated.
    pieces = [(p['recording_id'], p['audio_file_id'], p['start'], p['end']) for p in card['recording_pieces']]
    assert len(pieces) == len(set(pieces)) == 6
    assert report['rows_eligible'] == 6 and report['windows_after'] == 1 and report['rows_retired'] == 5
    assert report['visible_before'] == 6 and report['visible_after'] == 1 and report['outline_calls'] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('marked_deletion', [False, True], ids=['legacy-completed-item', 'marked-empty-list'])
async def test_rederive_preserves_cards_with_embedded_owner_items(owner, strict, edit_embedded_items, marked_deletion):
    sources, rows = lunch(count=3)
    rows[0]['structured']['action_items'] = [{'description': 'Owner revision', 'completed': True}]
    owner(*sources, *rows)
    if marked_deletion:
        edit_embedded_items(UID, 'c0', [])
    before = conversations(strict)

    _, report = await rederive()

    after = conversations(strict)
    assert after['c0'] == before['c0']
    assert after['r0']['claims'] == before['r0']['claims']
    reason = 'protected_edited' if marked_deletion else 'protected_action_items'
    assert report[reason] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('clear_confirmation', [False, True], ids=['unmarked-confirmation', 'marked-clear'])
async def test_rederive_preserves_cards_with_owner_events(owner, strict, set_event_created, clear_confirmation):
    sources, rows = lunch(count=3)
    rows[0]['structured']['events'] = [{'title': 'Team follow-up', 'start': AT, 'created': True}]
    owner(*sources, *rows)
    if clear_confirmation:
        set_event_created('c0', False)
        assert strict.rows[path('c0')][conversations_db.EVENTS_EDIT_REVISION]
    before = conversations(strict)

    _, report = await rederive()

    after = conversations(strict)
    assert after['c0'] == before['c0']
    assert after['r0']['claims'] == before['r0']['claims']
    reason = 'protected_edited' if clear_confirmation else 'protected_calendar_events'
    assert report[reason] == 1


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


def priors(strict, run_id=RUN):
    return [
        {**deepcopy(row), 'id': p[-1]}
        for p, row in strict.rows.items()
        if len(p) == 6 and p[:4] == ('users', UID, runs.COLLECTION, run_id) and p[4] == runs.PRIORS
    ]


@pytest.fixture
def ledger(strict, monkeypatch):
    book = Ledger()
    monkeypatch.setattr(runs, 'get_run', book.get)
    monkeypatch.setattr(runs, 'update_run', book.update)
    monkeypatch.setattr(runs, 'list_priors', lambda uid, run_id, **kw: priors(strict, run_id))
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
    # Restored exactly, the run keeps no copies of the owner's rows.
    assert not priors(strict)
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
@pytest.mark.parametrize('settled', [False, True], ids=['pending-baseline', 'recorded-baseline'])
@pytest.mark.parametrize(
    'edited_items', [[{'description': 'Owner revision', 'completed': True}], []], ids=['edit', 'delete']
)
async def test_embedded_item_changes_block_undo(owner, strict, ledger, edit_embedded_items, settled, edited_items):
    sources, rows = lunch(count=3)
    owner(*sources, *rows)
    await rederive()
    strict.rows[path('c0')]['structured']['action_items'] = [{'description': 'Generated', 'completed': False}]
    if settled:
        rederive_store.record_baselines(UID, RUN)

    edit_embedded_items(UID, 'c0', edited_items)
    after = conversations(strict)
    assert after['c0']['structured']['action_items'] == edited_items
    assert after['c0'][conversations_db.ACTION_ITEMS_EDIT_REVISION]
    refused = {'outcome': 'busy', 'reason': 'owner_edited_rebuilt_row'}
    assert backfill.undo_run(UID, RUN) == refused
    if not settled:
        rederive_store.record_baselines(UID, RUN)
        prior = next(entry for entry in priors(strict) if entry['id'] == 'c0')
        assert prior['baseline'] == rederive_store.CHANGED_BEFORE_SETTLE
        assert backfill.undo_run(UID, RUN) == refused
    assert conversations(strict) == after


@pytest.mark.asyncio
@pytest.mark.parametrize('settled', [False, True], ids=['pending-baseline', 'recorded-baseline'])
@pytest.mark.parametrize('edit', ['confirm', 'clear', 'legacy-confirmation'])
async def test_calendar_confirmation_blocks_undo(owner, strict, ledger, set_event_created, settled, edit):
    sources, rows = lunch(count=3)
    owner(*sources, *rows)
    await rederive()
    card = strict.rows[path('c0')]
    card['structured']['events'] = [{'title': 'Team follow-up', 'start': AT, 'created': edit == 'clear'}]
    if settled:
        rederive_store.record_baselines(UID, RUN)

    if edit == 'legacy-confirmation':
        card['structured']['events'][0]['created'] = True
    else:
        set_event_created('c0', edit == 'confirm')
        assert card[conversations_db.EVENTS_EDIT_REVISION]
    after = conversations(strict)
    assert after['c0']['structured']['events'][0]['created'] is (edit != 'clear')
    refused = {'outcome': 'busy', 'reason': 'owner_edited_rebuilt_row'}
    assert backfill.undo_run(UID, RUN) == refused
    if not settled:
        rederive_store.record_baselines(UID, RUN)
        assert next(entry for entry in priors(strict) if entry['id'] == 'c0')['baseline'] == (
            rederive_store.CHANGED_BEFORE_SETTLE
        )
        assert backfill.undo_run(UID, RUN) == refused
    assert conversations(strict) == after


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
async def test_an_owner_change_before_the_partition_settles_is_never_taken_as_the_baseline(owner, strict, ledger):
    sources, rows = lunch(count=3)
    owner(*sources, *rows)
    await rederive()
    # Starred while its notes were still running; the settle must not adopt the star as the baseline.
    strict.rows[path('c0')]['starred'] = True
    rederive_store.record_baselines(UID, RUN)
    after = conversations(strict)
    assert backfill.undo_run(UID, RUN) == {'outcome': 'busy', 'reason': 'owner_edited_rebuilt_row'}
    assert conversations(strict) == after


@pytest.mark.asyncio
async def test_an_undo_interrupted_before_erasing_a_created_row_finishes_on_rerun(owner, strict, ledger, monkeypatch):
    sources, rows = lunch()
    extra = source('r9', AT + timedelta(minutes=30), words=400)
    owner(*sources, *rows, extra)
    before = conversations(strict)
    await rederive()
    rederive_store.record_baselines(UID, RUN)
    erase = backfill.conversations_db.delete_conversation

    def failing(uid, cid):
        raise RuntimeError('child collection delete failed')

    monkeypatch.setattr(backfill.conversations_db, 'delete_conversation', failing)
    with pytest.raises(RuntimeError):
        backfill.undo_run(UID, RUN)
    # The groups are restored and the created row is hidden, waiting for its erasure.
    assert ledger.run['status'] == 'undoing'
    monkeypatch.setattr(backfill.conversations_db, 'delete_conversation', erase)
    result = backfill.undo_run(UID, RUN)
    assert result['outcome'] == 'undone' and result['rows_removed'] == 1
    assert conversations(strict) == before


@pytest.fixture
def task_writes(strict, monkeypatch):
    monkeypatch.setattr(tasks_db, 'db', strict)
    monkeypatch.setattr(tasks_db, 'fenced_action_item_commit', lambda uid: nullcontext())
    monkeypatch.setattr(tasks_db, 'bump_action_items_list_version', lambda uid: None)
    monkeypatch.setattr(conversations_db, 'get_conversation', lambda uid, cid: strict.rows.get(path(cid)))
    document = StrictFirestoreCollection.document
    task_ids = iter(['linked-task', 'standalone-task', 'batch-linked-task'])

    def allocate(self, name=None):
        if name is None:
            assert self.id == 'action_items'
            name = next(task_ids)
        return document(self, name)

    monkeypatch.setattr(StrictFirestoreCollection, 'document', allocate)


@pytest.fixture
def commit_refinement(owner, strict):
    sources, rows = lunch(count=2)
    owner(*sources, *rows)
    token = leases.acquire(UID, 'builder', firestore_client=strict)
    recordings = {row['id']: {**row, '_v3_revision': 1} for row in sources}
    existing = {row['id']: {**row, '_v3_revision': 1} for row in rows}
    survivor = {
        **rows[0],
        'finished_at': rows[1]['finished_at'],
        'v3_recording_ids': [row['id'] for row in sources],
        '_v3_absorbed': ['c1'],
        '_v3_claims': {row['id']: [{'start': row['started_at'], 'end': row['finished_at']}] for row in sources},
    }

    def commit(*other_rows):
        store.commit_projection(UID, token, recordings, existing, [survivor, *other_rows], [], firestore_client=strict)

    return commit


@pytest.fixture
async def undo_task_card(owner, strict, ledger, task_writes):
    sources, rows = lunch(count=3)
    extra = source('r9', AT + timedelta(minutes=30), words=400)
    owner(*sources, *rows, extra)
    before = conversations(strict)
    assert (await rederive())[0] == 'committed'
    rederive_store.record_baselines(UID, RUN)
    cid = next(entry['id'] for entry in priors(strict) if entry.get('created'))
    return cid, before


UNDO_TASK_BLOCK = {'outcome': 'busy', 'reason': 'undo_created_row_has_tasks'}


@pytest.mark.asyncio
@pytest.mark.parametrize('late', [False, True], ids=['later-group-at-preflight', 'committed-after-preflight'])
async def test_undo_refuses_to_remove_a_task_bearing_created_card(undo_task_card, strict, ledger, monkeypatch, late):
    cid, _ = undo_task_card
    groups = backfill._undo_groups(priors(strict))
    assert len(groups) > 1 and cid not in {entry['id'] for entry in groups[0]}
    before_undo = conversations(strict)

    def link_task():
        task_service.create_action_item(UID, {'description': 'Owner task', 'conversation_id': cid})

    if late:
        preflight = rederive_store.live_undo_blocker

        def create_after_preflight(*args, **kwargs):
            assert preflight(*args, **kwargs) is None
            link_task()

        monkeypatch.setattr(rederive_store, 'live_undo_blocker', create_after_preflight)
    else:
        link_task()
    assert backfill.undo_run(UID, RUN) == UNDO_TASK_BLOCK
    assert not ledger.erased and strict.rows[path(cid)] == before_undo[cid]
    assert strict.rows[path('r9')]['claims'] == before_undo['r9']['claims']
    assert strict.rows[('users', UID, 'action_items', 'linked-task')]['conversation_id'] == cid
    if not late:
        assert conversations(strict) == before_undo


@pytest.mark.asyncio
@pytest.mark.parametrize('late', [False, True], ids=['retry-preflight', 'retry-transaction'])
async def test_undo_retry_preserves_an_already_hidden_card_with_a_task(
    undo_task_card, strict, ledger, monkeypatch, late
):
    cid, _ = undo_task_card
    with monkeypatch.context() as patch:
        patch.setattr(conversations_db, 'delete_conversation', MagicMock(side_effect=RuntimeError('interrupted')))
        with pytest.raises(RuntimeError, match='interrupted'):
            backfill.undo_run(UID, RUN)
    hidden = deepcopy(strict.rows[path(cid)])
    assert hidden['deleted'] and hidden['v3_rederive_live_undone'] == RUN

    def add_legacy_task():
        strict.rows[('users', UID, 'action_items', 'legacy-task')] = {'conversation_id': cid}

    if late:
        preflight = rederive_store.live_undo_blocker

        def link_after_preflight(*args, **kwargs):
            assert preflight(*args, **kwargs) is None
            add_legacy_task()

        monkeypatch.setattr(rederive_store, 'live_undo_blocker', link_after_preflight)
    else:
        add_legacy_task()
    assert backfill.undo_run(UID, RUN) == UNDO_TASK_BLOCK
    assert strict.rows[path(cid)] == hidden and not ledger.erased


@pytest.mark.asyncio
@pytest.mark.parametrize('batch', [False, True], ids=['single', 'batch'])
@pytest.mark.parametrize('erase', [False, True], ids=['hidden', 'erased'])
@pytest.mark.parametrize('source_links', ['true', 'false'], ids=['validation-on', 'validation-off'])
async def test_task_create_validated_before_undo_cannot_commit_after_removal(
    undo_task_card, strict, ledger, monkeypatch, batch, erase, source_links
):
    monkeypatch.setenv(task_source_validation.SOURCE_LINKS_ENABLED_ENV, source_links)
    cid, before = undo_task_card
    # A task attached to a row that undo restores is outside its removal set.
    assert task_service.create_action_item(UID, {'description': 'Unrelated task', 'conversation_id': 'c0'})
    run = tasks_db.FirestoreActionItems._run_contention

    def undo_before_task_transaction(self, *args, **kwargs):
        if erase:
            assert backfill.undo_run(UID, RUN)['outcome'] == 'undone'
            assert ledger.erased == [cid]
        else:
            with monkeypatch.context() as patch:
                patch.setattr(
                    conversations_db, 'delete_conversation', MagicMock(side_effect=RuntimeError('interrupted'))
                )
                with pytest.raises(RuntimeError, match='interrupted'):
                    backfill.undo_run(UID, RUN)
            assert strict.rows[path(cid)]['v3_rederive_live_undone'] == RUN
        return run(self, *args, **kwargs)

    monkeypatch.setattr(tasks_db.FirestoreActionItems, '_run_contention', undo_before_task_transaction)
    payload = {'description': 'Task awaiting commit', 'conversation_id': cid}
    with pytest.raises(task_source_validation.TaskSourceValidationError):
        if batch:
            task_service.create_action_items_batch(UID, [{'description': 'Standalone'}, payload])
        else:
            task_service.create_action_item(UID, payload)
    after = conversations(strict)
    if not erase:
        assert after.pop(cid)['deleted']
    assert after == before
    assert [
        task['conversation_id'] for doc, task in strict.rows.items() if doc[:3] == ('users', UID, 'action_items')
    ] == ['c0']


@pytest.mark.asyncio
@pytest.mark.parametrize('batch', [False, True], ids=['single', 'batch'])
async def test_task_source_switch_off_preserves_missing_source_fallback(undo_task_card, strict, monkeypatch, batch):
    monkeypatch.setenv(task_source_validation.SOURCE_LINKS_ENABLED_ENV, 'false')
    missing = 'ordinary-missing-conversation'
    payload = {'description': 'Legacy link', 'conversation_id': missing}
    reads = []
    get = StrictFirestoreDocument.get

    def record_get(self, *args, **kwargs):
        if self.path[2:3] in {('conversations',), ('conversations_v3_undo_removals',)}:
            reads.append(self.path)
        return get(self, *args, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', record_get)
    if batch:
        ids = task_service.create_action_items_batch(UID, [payload, payload, {'description': 'Standalone'}])
        assert len(ids) == 3
    else:
        ids = [task_service.create_action_item(UID, payload)]
    for task_id in ids[:2]:
        assert strict.rows[('users', UID, 'action_items', task_id)]['conversation_id'] == missing
    assert len(reads) == 1 and reads[0][2] == 'conversations_v3_undo_removals'


@pytest.mark.asyncio
async def test_task_can_link_a_card_recreated_at_an_undo_removed_id(undo_task_card, strict, owner):
    cid, _ = undo_task_card
    assert backfill.undo_run(UID, RUN)['outcome'] == 'undone'
    assert (await rederive())[0] == 'committed'
    assert cid in conversations(strict)
    task_id = task_service.create_action_item(UID, {'description': 'New link', 'conversation_id': cid})
    assert strict.rows[('users', UID, 'action_items', task_id)]['conversation_id'] == cid


@pytest.mark.asyncio
async def test_undo_of_a_later_run_over_an_earlier_runs_rows_can_be_rerun(owner, strict, ledger):
    later = 'run-live-2'
    sources, rows = lunch()
    owner(*sources, *rows)
    before = conversations(strict)
    await rederive()
    # The first run's notes settled, then more speech landed on one of its sources.
    for row in strict.rows.values():
        row.pop('v3_backfill_process_pending', None)
    strict.rows[path('r2')]['transcript_segments'].append(
        {'id': 'r2-late', 'text': 'late words', 'start': 59.0, 'end': 60.0, 'is_user': True}
    )
    after_first = conversations(strict)
    report = {}
    outcome = await service.reconcile(
        UID, derive=True, live=True, since=SINCE, until=UNTIL, run_id=later, report=report
    )
    assert outcome == 'committed' and priors(strict, later)
    assert conversations(strict)['c0']['v3_rederive_live_run'] == later
    # The first attempt restores every group, then stops before finishing.
    drop = runs.drop_priors

    def interrupted(*args, **kwargs):
        raise RuntimeError('interrupted')

    runs.drop_priors = interrupted
    try:
        with pytest.raises(RuntimeError):
            backfill.undo_run(UID, later)
    finally:
        runs.drop_priors = drop
    assert conversations(strict) == after_first and priors(strict, later)
    # Rows the first attempt restored carry the earlier run's stamp; a rerun is not a newer run.
    assert backfill.undo_run(UID, later)['outcome'] == 'undone' and conversations(strict) == after_first
    expected = deepcopy(before)
    expected['r2']['transcript_segments'] = after_first['r2']['transcript_segments']
    assert backfill.undo_run(UID, RUN)['outcome'] == 'undone'
    restored = conversations(strict)
    for row in restored.values():
        row.pop('v3_backfill_process_pending', None)
    for row in expected.values():
        row.pop('v3_backfill_process_pending', None)
    assert restored == expected


@pytest.mark.asyncio
async def test_undo_refuses_once_the_owner_account_deletion_began(owner, strict, ledger):
    sources, rows = lunch(count=3)
    owner(*sources, *rows)
    await rederive()
    after = conversations(strict)
    strict.rows[account_deletion_document(UID, firestore_client=strict).path] = {'status': 'pending'}
    assert backfill.undo_run(UID, RUN) == {'outcome': 'busy', 'reason': 'account_deletion'}
    assert conversations(strict) == after


@pytest.mark.asyncio
async def test_undo_refuses_a_group_too_large_for_one_transaction_before_restoring_any(
    owner, strict, ledger, monkeypatch
):
    sources, rows = lunch(count=3)
    owner(*sources, *rows)
    await rederive()
    after = conversations(strict)
    monkeypatch.setattr(rederive_store, 'UNDO_GROUP_BYTES', 1)
    assert backfill.undo_run(UID, RUN) == {'outcome': 'busy', 'reason': 'undo_group_too_large'}
    assert conversations(strict) == after


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'reason, refusal', [('deleted', 'owner_deleted_rebuilt_row'), ('protection', 'owner_edited_rebuilt_row')]
)
async def test_a_deleted_or_reprotected_conversation_keeps_no_undo_copy(
    owner, strict, ledger, monkeypatch, reason, refusal
):
    sources, rows = lunch(count=3)
    owner(*sources, *rows)
    await rederive()
    after = conversations(strict)
    monkeypatch.setattr(runs, '_live_run_ids', lambda uid, **kw: [RUN, 'other-live-run'])
    assert {e['id'] for e in priors(strict)} == {'c0', 'c1', 'c2'}
    purged = runs.purge_conversation_priors(
        UID, ['c0', *after['c0']['sync_merged_from']], reason, firestore_client=strict
    )
    # Every copy is emptied (and none is invented in a run that never held one).
    assert purged == 3 and not priors(strict, 'other-live-run')
    assert all(set(e) == {'id', 'purged', 'recorded_at'} and e['purged'] == reason for e in priors(strict))
    # The run can no longer be undone exactly, so it is not undone at all.
    assert backfill.undo_run(UID, RUN) == {'outcome': 'busy', 'reason': refusal}
    assert conversations(strict) == after


@pytest.fixture
def migration_client(strict, monkeypatch):
    monkeypatch.setattr(
        strict, 'get_all', lambda refs, **kw: [SimpleNamespace(exists=True, id=r.id, reference=r) for r in refs]
    )
    monkeypatch.setattr(strict, 'batch', MagicMock, raising=False)
    monkeypatch.setattr(
        StrictFirestoreCollection, 'select', lambda *args: SimpleNamespace(stream=lambda: []), raising=False
    )
    monkeypatch.setattr(backfill.conversations_db, 'db', strict)


def test_a_protection_change_checks_priors_after_migrating(strict, monkeypatch, migration_client):
    conversations_db = backfill.conversations_db
    strict.rows[path('c0')] = {'id': 'c0', 'v3_rederive_live_run': RUN, 'data_protection_level': 'standard'}
    strict.rows[path('c1')] = {'id': 'c1', 'data_protection_level': 'standard'}
    strict.rows[path('c2')] = {'id': 'c2', 'v3_rederive_live_run': RUN, 'data_protection_level': 'enhanced'}
    calls = []

    def purge(uid, ids, reason, **kwargs):
        calls.append((uid, ids, reason, strict.rows[path(ids[0])]['data_protection_level']))

    monkeypatch.setattr(runs, 'purge_conversation_priors', purge)
    conversations_db.migrate_conversations_level_batch(UID, ['c0', 'c1', 'c2'], 'enhanced')
    assert calls == [(UID, ['c0', 'c1', 'c2'], 'protection', 'enhanced')]


@pytest.mark.parametrize('batch', [False, True], ids=['single', 'batch'])
def test_protection_migration_purges_retired_donor_priors(strict, monkeypatch, migration_client, batch):
    conversations_db = backfill.conversations_db
    strict.rows[path('survivor')] = {
        'v3_rederive_live_run': RUN,
        'sync_merged_from': ['donor'],
        'data_protection_level': 'standard',
    }
    strict.rows[path('donor')] = {
        'data_protection_level': 'standard',
    }
    runs.save_priors(
        UID,
        RUN,
        [{'id': cid, 'raw': {'data_protection_level': 'standard'}, 'claims': []} for cid in ('survivor', 'donor')],
        firestore_client=strict,
    )
    strict.rows[path('donor')].update(deleted=True, sync_merged_into='survivor', v3_rederive_live_run=RUN)
    monkeypatch.setattr(runs, '_live_run_ids', lambda uid, **kw: [RUN])

    ids = ['survivor', 'donor'] if batch else ['survivor']
    conversations_db.migrate_conversations_level_batch(UID, ids, 'enhanced')
    assert strict.rows[path('survivor')]['data_protection_level'] == 'enhanced'
    assert strict.rows[path('donor')]['deleted']
    assert {prior['id']: prior['purged'] for prior in priors(strict)} == {
        'survivor': 'protection',
        'donor': 'protection',
    }
    assert all('raw' not in prior for prior in priors(strict))


def test_a_protection_purge_keeps_copies_already_at_the_new_level(strict, monkeypatch):
    monkeypatch.setattr(runs, '_live_run_ids', lambda uid, **kw: [RUN])
    runs.save_priors(
        UID,
        RUN,
        [
            {'id': 'old', 'raw': {'id': 'old'}, 'claims': []},
            {'id': 'new', 'raw': {'id': 'new', 'data_protection_level': 'enhanced'}, 'claims': []},
            {'id': 'made', 'created': True, 'claims': []},
        ],
        firestore_client=strict,
    )
    ids = ['old', 'new', 'made']
    assert runs.purge_conversation_priors(UID, ids, 'protection', firestore_client=strict, keep_level='enhanced') == 1
    by_id = {e['id']: e for e in priors(strict)}
    assert by_id['old'].get('purged') == 'protection' and 'raw' in by_id['new'] and by_id['made'].get('created')


@pytest.mark.asyncio
async def test_undo_refuses_after_a_protection_change_before_baselines(owner, strict, ledger):
    sources, rows = lunch(count=3)
    owner(*sources, *rows)
    await rederive()
    strict.rows[path('c0')]['data_protection_level'] = 'enhanced'
    assert backfill.undo_run(UID, RUN) == {'outcome': 'busy', 'reason': 'owner_edited_rebuilt_row'}


def test_a_restored_row_is_recognised_despite_the_commit_hook_stamps():
    raw = {'id': 'c0', 'title': 'Kept', 'home_source_version': 'before'}
    restored = {'id': 'c0', 'title': 'Kept', 'home_source_version': 'stamped', 'home_content_invalidated': False}
    assert rederive_store.already_undone(restored, {'raw': raw}, RUN)
    assert not rederive_store.already_undone({**restored, 'title': 'Other'}, {'raw': raw}, RUN)


def test_the_dry_run_reports_a_window_that_would_cross_the_edge(owner, strict):
    sources, rows = lunch(count=3)
    owner(*sources, *rows, source('r9', UNTIL - timedelta(seconds=60), seconds=120, words=400))
    est = backfill.estimate_live_partition(
        UID, {'since': SINCE, 'until': UNTIL}, 'dry-run', now=UNTIL + timedelta(hours=1)
    )
    assert est['windows_crossing_edge'] == 1


def test_priors_are_never_written_for_a_conversation_the_owner_deleted(strict):
    strict.rows[('users', UID, 'deleted_conversations', 'c0')] = {'conversation_id': 'c0'}
    with pytest.raises(store.Conflict, match='target_deleted'):
        runs.save_priors(UID, RUN, [{'id': 'c0', 'raw': {'id': 'c0'}, 'claims': []}], firestore_client=strict)
    assert not priors(strict)


def test_the_dry_run_reports_live_speech_no_window_claimed(owner, strict):
    sources, rows = lunch()
    owner(*sources, *rows, source('r9', AT + timedelta(minutes=30), words=400))
    est = backfill.estimate_live_partition(UID, {'since': SINCE, 'until': UNTIL}, 'dry-run', now=UNTIL)
    assert est['sources_unclaimed'] == 1


@pytest.mark.asyncio
async def test_a_deleted_row_whose_claims_are_not_yet_released_still_fences_its_speech(owner, strict):
    sources, rows = lunch(count=3)
    gone_source = source('rd', AT + timedelta(minutes=40), words=400)
    gone = fragment('cd', gone_source, deleted=True, discarded=True)
    owner(*sources, *rows, gone_source, gone)
    outcome, report = await rederive()
    assert outcome == 'committed' and report['protected_deleted'] == 1
    after = conversations(strict)
    # No new card is made from the deleted conversation's speech, and it is left as it was.
    assert not any('rd' in (row.get('v3_recording_ids') or []) for cid, row in after.items() if cid != 'cd')
    assert after['cd'] == {**gone, 'id': 'cd'} or after['cd'] == gone


@pytest.mark.asyncio
async def test_the_run_ledger_counts_live_speech_no_window_claimed(owner, strict):
    sources, rows = lunch(count=3)
    owner(*sources, *rows, source('r9', AT + timedelta(minutes=30), words=400))
    outcome, report = await rederive()
    assert outcome == 'committed' and report['sources_unclaimed'] == 1


@pytest.mark.asyncio
async def test_a_failed_commit_keeps_no_copy_of_a_row_it_did_not_write(owner, strict, monkeypatch):
    sources, rows = lunch(count=3)
    owner(*sources, *rows)

    def commit(*args, **kwargs):
        # The owner deletes one row and re-protects another between the copies and the commit.
        strict.rows[('users', UID, 'deleted_conversations', 'c1')] = {'conversation_id': 'c1'}
        strict.rows[path('c2')]['data_protection_level'] = 'enhanced'
        raise store.Conflict('source_changed')

    monkeypatch.setattr(service, '_commit', commit)
    # A changed row is a retry, not a block; every copy the failed attempt recorded goes with it.
    with pytest.raises(store.Conflict, match='source_changed'):
        await rederive()
    assert not priors(strict)

    # Any other failure (here, Firestore unavailable) cleans up the same way.
    def unavailable(*args, **kwargs):
        raise RuntimeError('unavailable')

    monkeypatch.setattr(service, '_commit', unavailable)
    strict.rows.pop(('users', UID, 'deleted_conversations', 'c1'))
    strict.rows[path('c2')]['data_protection_level'] = 'standard'
    with pytest.raises(RuntimeError, match='unavailable'):
        await rederive()
    assert not priors(strict)


@pytest.fixture
async def stopped_attempt(owner, strict, monkeypatch):
    sources, rows = lunch(count=3)
    rows[1]['data_protection_level'] = 'standard'
    owner(*sources, *rows)

    class WorkerStopped(BaseException):
        pass

    def stop_before_stamp(*args, **kwargs):
        assert any(prior['id'] == 'c1' and 'raw' in prior for prior in priors(strict))
        raise WorkerStopped()

    monkeypatch.setattr(service, '_commit', stop_before_stamp)
    with pytest.raises(WorkerStopped):
        await rederive()
    assert not strict.rows[path('c1')].get('v3_rederive_live_run')
    monkeypatch.setattr(runs, '_live_run_ids', lambda uid, **kw: [RUN])


@pytest.mark.asyncio
@pytest.mark.parametrize('missing_metadata', [False, True], ids=['normal', 'retry'])
async def test_app_delete_purges_a_stopped_attempt_prior(
    stopped_attempt, strict, ledger, monkeypatch, missing_metadata
):
    # The app records this tombstone before entering its frame/lake and conversation deletion service.
    strict.rows[('users', UID, 'deleted_conversations', 'c1')] = {'conversation_id': 'c1'}
    if missing_metadata:
        strict.rows.pop(path('c1'))
    monkeypatch.setattr(
        conversation_frame_evidence.conversations_db,
        'get_conversation_raw_snapshot',
        lambda uid, cid: strict.rows.get(path(cid)),
    )
    monkeypatch.setattr(conversation_frame_evidence.conversations_db, 'get_conversation_photos', lambda *a: [])
    for method in (
        'list_all_frame_request_storage_ids',
        'persist_conversation_frame_deletion_outbox',
        'delete_frame_requests_for_conversation',
    ):
        monkeypatch.setattr(conversation_frame_evidence.frame_requests_db, method, MagicMock(return_value=[]))
    monkeypatch.setattr(lake_wipe, 'purge_conversation_lake_objects', MagicMock())
    monkeypatch.setattr(merge_conversations, 'record_survivor_deleted', MagicMock())

    conversation_frame_evidence.delete_conversation_and_frame_evidence(UID, 'c1')
    by_id = {prior['id']: prior for prior in priors(strict)}
    assert by_id['c1']['purged'] == 'deleted' and 'raw' not in by_id['c1']
    assert 'raw' in by_id['c0']
    assert path('c1') not in strict.rows
    conversation_frame_evidence.delete_conversation_and_frame_evidence(UID, 'c1')
    assert {prior['id']: prior for prior in priors(strict)} == by_id


@pytest.mark.asyncio
@pytest.mark.parametrize('ids', [['c1'], ['c1', 'c2']], ids=['single', 'batch'])
@pytest.mark.parametrize('retry', [False, True], ids=['normal', 'same-target-retry'])
async def test_protection_migration_purges_stopped_attempt_priors(
    stopped_attempt, migration_client, strict, monkeypatch, ids, retry
):
    assert next(prior for prior in priors(strict) if prior['id'] == 'c1')['raw']['data_protection_level'] == 'standard'
    migrate = backfill.conversations_db.migrate_conversations_level_batch
    if retry:
        with monkeypatch.context() as patch:
            patch.setattr(runs, 'purge_conversation_priors', MagicMock(side_effect=RuntimeError('purge unavailable')))
            with pytest.raises(RuntimeError, match='purge unavailable'):
                migrate(UID, ids, 'enhanced')
        assert strict.rows[path('c1')]['data_protection_level'] == 'enhanced'
        assert 'raw' in next(prior for prior in priors(strict) if prior['id'] == 'c1')

    migrate(UID, ids, 'enhanced')
    by_id = {prior['id']: prior for prior in priors(strict)}
    for cid in ids:
        assert strict.rows[path(cid)]['data_protection_level'] == 'enhanced'
        assert not strict.rows[path(cid)].get('v3_rederive_live_run')
        assert by_id[cid]['purged'] == 'protection' and 'raw' not in by_id[cid]
    assert 'raw' in by_id['c0']


@pytest.mark.asyncio
@pytest.mark.parametrize('late', [False, True], ids=['already-present', 'before-commit'])
async def test_live_rederive_preserves_task_bearing_donor(owner, strict, monkeypatch, task_writes, late):
    sources, rows = lunch(count=3)
    owner(*sources, *rows)
    before = conversations(strict)
    task_path = ('users', UID, 'action_items', 'linked-task')
    checks = []
    query = store.merge_donors_have_tasks

    def has_tasks(uid, donor_ids, *, firestore_client=None, transaction=None):
        assert uid == UID and set(donor_ids) == {'c1', 'c2'}
        checks.append(transaction is not None)
        return query(uid, donor_ids, firestore_client=firestore_client, transaction=transaction)

    def create_task():
        task_service.create_action_item(UID, {'description': 'Donor task', 'conversation_id': 'c1'})

    monkeypatch.setattr(store, 'merge_donors_have_tasks', has_tasks)
    if late:
        commit = service._commit

        def add_task_and_commit(*args, **kwargs):
            create_task()
            return commit(*args, **kwargs)

        monkeypatch.setattr(service, '_commit', add_task_and_commit)
    else:
        create_task()

    outcome, report = await rederive()
    assert outcome == 'blocked' and report['blocked_reason'] == 'rederive_live_donor_tasks'
    assert checks == ([False, True] if late else [False])
    assert conversations(strict) == before and not priors(strict)
    assert strict.rows[task_path]['conversation_id'] == 'c1'
    assert not removal_ref(strict.document(f'users/{UID}'), 'c1').get().exists


@pytest.mark.asyncio
@pytest.mark.parametrize('batch', [False, True], ids=['single', 'batch'])
async def test_task_create_validated_before_retirement_cannot_commit(
    owner, strict, ledger, task_writes, monkeypatch, batch
):
    sources, rows = lunch(count=3)
    owner(*sources, *rows)
    monkeypatch.setenv(task_source_validation.SOURCE_LINKS_ENABLED_ENV, 'true')
    run = tasks_db.FirestoreActionItems._run_contention

    def retire_after_validation(self, *args, **kwargs):
        # The shared service has validated c1. Finish the repair before opening the task transaction.
        assert asyncio.run(rederive())[0] == 'committed'
        donor = strict.rows[path('c1')]
        assert donor['deleted'] and donor['sync_merged_into'] == 'c0'
        return run(self, *args, **kwargs)

    payload = {'description': 'Paused task', 'conversation_id': 'c1'}
    with monkeypatch.context() as patch:
        patch.setattr(tasks_db.FirestoreActionItems, '_run_contention', retire_after_validation)
        with pytest.raises(task_source_validation.TaskSourceValidationError):
            if batch:
                await asyncio.to_thread(
                    task_service.create_action_items_batch, UID, [{'description': 'Standalone'}, payload]
                )
            else:
                await asyncio.to_thread(task_service.create_action_item, UID, payload)
    assert not any(doc[:3] == ('users', UID, 'action_items') for doc in strict.rows)
    assert backfill.undo_run(UID, RUN)['outcome'] == 'undone'
    assert not strict.rows[path('c1')].get('deleted')
    assert task_service.create_action_item(UID, payload)


@pytest.mark.parametrize('batch', [False, True], ids=['single', 'batch'])
def test_task_create_validated_before_refinement_cannot_commit(
    commit_refinement, strict, task_writes, monkeypatch, batch
):
    monkeypatch.setenv(task_source_validation.SOURCE_LINKS_ENABLED_ENV, 'true')
    run = tasks_db.FirestoreActionItems._run_contention

    def absorb_after_validation(self, *args, **kwargs):
        # The shared create service has validated the active donor and is about to start its write.
        commit_refinement()
        donor = strict.rows[path('c1')]
        assert donor['deleted'] and donor['sync_merged_into'] == 'c0'
        return run(self, *args, **kwargs)

    monkeypatch.setattr(tasks_db.FirestoreActionItems, '_run_contention', absorb_after_validation)
    payload = {'description': 'Paused task', 'conversation_id': 'c1'}
    with pytest.raises(task_source_validation.TaskSourceValidationError):
        if batch:
            task_service.create_action_items_batch(UID, [{'description': 'Standalone'}, payload])
        else:
            task_service.create_action_item(UID, payload)
    assert not any(doc[:3] == ('users', UID, 'action_items') for doc in strict.rows)


def test_task_committed_first_blocks_refinement(commit_refinement, strict, task_writes):
    task = task_service.create_action_item(UID, {'description': 'Donor task', 'conversation_id': 'c1'})
    before = conversations(strict)
    with pytest.raises(store.Conflict, match='source_changed'):
        commit_refinement()
    assert conversations(strict) == before
    assert strict.rows[('users', UID, 'action_items', task)]['conversation_id'] == 'c1'
    assert not removal_ref(strict.document(f'users/{UID}'), 'c1').get().exists


def test_refinement_preflight_reserves_marker_write(commit_refinement, strict, monkeypatch):
    # Two recordings, the donor redirect and marker, the survivor and the lease.
    monkeypatch.setattr(store, 'BATCH_MAX_WRITES', 5)
    before = conversations(strict)
    tx_count = len(strict.transactions)
    with pytest.raises(store.Conflict, match='request_too_large'):
        commit_refinement()
    assert conversations(strict) == before and len(strict.transactions) == tx_count


def test_refinement_batch_reserves_marker_with_donor(commit_refinement, strict, monkeypatch):
    cap = 6
    monkeypatch.setattr(store, 'BATCH_MAX_WRITES', cap)
    commit_refinement({'id': 'unrelated', 'status': 'completed', 'started_at': AT, 'finished_at': AT})

    batches = [tx for tx in strict.transactions if any('claims' in patch for _, patch in tx.updates)]
    assert len(batches) == 2
    survivor_batch, other_batch = batches
    marker = removal_ref(strict.document(f'users/{UID}'), 'c1').path
    assert {path('c0'), marker} <= {doc for doc, _ in survivor_batch.sets}
    assert any(doc == path('c1') and patch.get('deleted') for doc, patch in survivor_batch.updates)
    assert path('unrelated') in {doc for doc, _ in other_batch.sets}
    assert len(survivor_batch.sets) + len(survivor_batch.updates) <= cap


@pytest.mark.asyncio
async def test_a_row_the_owner_deletes_before_its_retirement_fails_the_commit(owner, strict, monkeypatch):
    sources, rows = lunch(count=3)
    owner(*sources, *rows)
    before = conversations(strict)
    record = runs.save_priors

    def save_then_delete(uid, run_id, entries, **kwargs):
        record(uid, run_id, entries, **kwargs)
        # The delete route records its tombstone first; c1 is about to be retired into c0.
        strict.rows[('users', UID, 'deleted_conversations', 'c1')] = {'conversation_id': 'c1'}

    monkeypatch.setattr(runs, 'save_priors', save_then_delete)
    outcome, report = await rederive()
    assert outcome == 'blocked' and report['blocked_reason'] == 'target_deleted'
    assert conversations(strict) == before and not priors(strict)


@pytest.mark.asyncio
async def test_a_card_with_app_results_is_left_alone(owner, strict):
    sources, rows = lunch(count=3)
    rows[2]['apps_results'] = [{'app_id': 'app', 'content': 'Result'}]
    owner(*sources, *rows)
    outcome, report = await rederive()
    assert outcome == 'committed' and report['protected_app_results'] == 1
    assert conversations(strict)['c2'] == rows[2]


@pytest.mark.asyncio
async def test_undo_reapplies_the_recurring_voice_fence_to_restored_rows(owner, strict, ledger, monkeypatch):
    sources, rows = lunch(count=3)
    owner(*sources, *rows)
    await rederive()

    def scrub(tx, user, data):
        data['voice_fence_applied'] = True

    monkeypatch.setattr(rederive_store, 'filter_processing_write', scrub)
    assert backfill.undo_run(UID, RUN)['outcome'] == 'undone'
    assert all(conversations(strict)[cid].get('voice_fence_applied') for cid in ('c0', 'c1', 'c2'))


@pytest.mark.asyncio
async def test_a_card_whose_summary_the_owner_rewrote_is_left_alone(owner, strict):
    sources, rows = lunch(count=3)
    # The summary edit endpoint replaces the overview and deletes the generated sections.
    rows[1]['structured'] = {'title': 'Piece c1', 'overview': 'My own words'}
    owner(*sources, *rows)
    outcome, report = await rederive()
    assert outcome == 'committed' and report['protected_edited'] == 1
    assert conversations(strict)['c1'] == rows[1]


@pytest.mark.asyncio
async def test_undo_refuses_after_a_summary_rewrite_before_baselines(owner, strict, ledger):
    sources, rows = lunch(count=3)
    owner(*sources, *rows)
    await rederive()
    strict.rows[path('c0')].update(v3_notes_written=True, structured={'title': 'Lunch', 'overview': 'Mine'})
    assert backfill.undo_run(UID, RUN) == {'outcome': 'busy', 'reason': 'owner_edited_rebuilt_row'}


@pytest.mark.asyncio
async def test_deleting_a_retired_bridge_releases_none_of_the_survivors_claims(owner, strict):
    sources, rows = lunch(count=3)
    owner(*sources, *rows)
    await rederive()
    before = conversations(strict)
    store.release_claims(UID, before['c1'], firestore_client=strict)
    after = conversations(strict)
    assert all(after[s['id']] == before[s['id']] for s in sources)
    assert not any(after[s['id']].get('v3_audio_purge_pending') for s in sources)


@pytest.mark.asyncio
async def test_undo_refuses_when_a_source_the_run_named_is_gone(owner, strict, ledger):
    sources, rows = lunch(count=3)
    owner(*sources, *rows)
    await rederive()
    strict.rows.pop(path('r1'))
    after = conversations(strict)
    assert backfill.undo_run(UID, RUN) == {'outcome': 'busy', 'reason': 'undo_source_missing'}
    assert conversations(strict) == after


@pytest.mark.asyncio
async def test_undo_checks_every_source_before_restoring_any_group(owner, strict, ledger):
    sources, rows = lunch(count=3)
    owner(*sources, *rows, source('r9', AT + timedelta(minutes=30), words=400))
    await rederive()
    assert len(backfill._undo_groups(priors(strict))) == 2
    # The created card's group sorts after the lunch group; its source is gone.
    strict.rows.pop(path('r9'))
    after = conversations(strict)
    assert backfill.undo_run(UID, RUN) == {'outcome': 'busy', 'reason': 'undo_source_missing'}
    assert conversations(strict) == after


def test_a_copy_is_never_recorded_at_a_protection_level_the_row_left(strict):
    strict.rows[path('c0')] = {'id': 'c0', 'data_protection_level': 'enhanced'}
    with pytest.raises(store.Conflict, match='source_changed'):
        runs.save_priors(UID, RUN, [{'id': 'c0', 'raw': {'id': 'c0'}, 'claims': []}], firestore_client=strict)
    assert not priors(strict)


@pytest.mark.asyncio
async def test_copies_left_by_a_stopped_attempt_are_dropped_by_resume_or_undo(owner, strict, ledger, monkeypatch):
    sources, rows = lunch(count=3)
    owner(*sources, *rows)
    stale = {'id': 'c1', 'raw': deepcopy(rows[1]), 'claims': []}
    # A process stopped after recording c1's copy and before stamping c1; the owner then deletes it.
    runs.save_priors(UID, RUN, [stale], firestore_client=strict)
    strict.rows[('users', UID, 'deleted_conversations', 'c1')] = {'conversation_id': 'c1'}
    ledger.run.update(status='blocked', partitions=[{'since': SINCE, 'until': UNTIL, 'status': 'blocked'}])
    monkeypatch.setattr(runs, 'mark_start', lambda *a, **kw: None)
    assert backfill.resume_run(UID, RUN)['outcome'] == 'resumed' and not priors(strict)
    # Undo drops them too before it looks for refusals.
    runs.save_priors(UID, 'other-run', [{'id': 'c2', 'raw': deepcopy(rows[2]), 'claims': []}], firestore_client=strict)
    ledger.run['run_id'] = 'other-run'
    assert backfill.undo_run(UID, 'other-run')['outcome'] == 'undone' and not priors(strict, 'other-run')
    assert conversations(strict)['c2'] == rows[2]


@pytest.mark.asyncio
async def test_a_partition_reads_only_its_own_copies(owner, strict, monkeypatch):
    sources, rows = lunch(count=3)
    owner(*sources, *rows)
    # Another partition's copy: neither the attempt nor its settle step lists the run's copies.
    runs.save_priors(UID, RUN, [{'id': 'elsewhere', 'raw': None, 'created': True}], firestore_client=strict)
    monkeypatch.setattr(runs, 'list_priors', lambda *a, **kw: pytest.fail('a partition lists every copy'))
    outcome, report = await rederive()
    assert outcome == 'committed' and report['prior_ids'] == ['c0', 'c1', 'c2']
    assert rederive_store.record_baselines(UID, RUN, report['prior_ids']) == 3
    held = {e['id']: e for e in priors(strict)}
    assert all(held[cid].get('baseline') for cid in report['prior_ids']) and 'baseline' not in held['elsewhere']


@pytest.mark.asyncio
async def test_a_range_too_large_for_one_pass_blocks_with_its_own_reason(owner, strict, monkeypatch):
    sources, rows = lunch(count=3)
    owner(*sources, *rows)
    before = conversations(strict)
    monkeypatch.setattr(rederive_store, 'REDERIVE_LIVE_LIMIT', 2)
    outcome, report = await rederive()
    assert outcome == 'blocked' and report['blocked_reason'] == 'rederive_live_range_overflow'
    assert conversations(strict) == before and not priors(strict)


def test_a_resumed_attempt_keeps_the_first_copy_of_a_row(strict):
    first = {'id': 'c0', 'raw': {'id': 'c0', 'title': 'before'}, 'claims': [{'recording_id': 'r0', 'index': 0}]}
    later = {'id': 'c0', 'raw': {'id': 'c0', 'title': 'later'}, 'claims': [{'recording_id': 'r0', 'index': 3}]}
    runs.save_priors(UID, RUN, [first], firestore_client=strict)
    runs.save_priors(UID, RUN, [later], firestore_client=strict)
    (kept,) = priors(strict)
    assert kept['raw'] == first['raw'] and kept['claims'] == first['claims']


def test_priors_are_never_written_once_the_owner_account_deletion_began(strict, monkeypatch):
    strict.rows[account_deletion_document(UID, firestore_client=strict).path] = {'status': 'pending'}
    with pytest.raises(store.Conflict, match='account_deletion'):
        runs.save_priors(UID, RUN, [{'id': 'c0', 'raw': {'id': 'c0'}, 'claims': []}], firestore_client=strict)
    assert not priors(strict)


def test_the_window_classifier_counts_each_kind_once():
    meta = [
        {'recording': True},
        {'recording': True, 'deleted': True},
        {'v3_derived': True},
        {'v3_derived': True, 'home_hidden': True},
        {'v3_derived': True, 'backfilled': True},
        {'v3_derived': True, 'backfilled': True, 'v3_rederive_live_run': RUN},
        {'v3_derived': True, 'sync_merged_into': 'c0'},
        {'structured': {}},
    ]
    assert backfill.classify_live_window(meta) == {
        'documents': 8,
        'live_sources': 1,
        'live_rows': 3,
        'live_rows_visible': 2,
        'backfilled_rows': 1,
        'legacy_rows': 1,
        'deleted': 2,
    }


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


@pytest.mark.asyncio
async def test_partition_write_budget_includes_donor_markers(owner, strict, monkeypatch):
    sources, rows = lunch(count=3)
    owner(*sources, *rows)
    before = conversations(strict)
    # Three sources, two donors and their markers, one lineage patch, one row and the lease.
    monkeypatch.setattr(store, 'BATCH_MAX_WRITES', 9)
    outcome, report = await rederive()
    assert outcome == 'blocked' and report['blocked_reason'] == 'backfill_partition_budget'
    assert conversations(strict) == before and not priors(strict)


@pytest.mark.asyncio
async def test_final_batch_reserves_donor_marker_writes(owner, strict, monkeypatch):
    sources, rows = lunch(count=3)
    owner(*sources, *rows, source('r9', AT + timedelta(minutes=30), words=400))
    cap = 11
    monkeypatch.setattr(store, 'BATCH_MAX_WRITES', cap)
    assert (await rederive())[0] == 'committed'

    batches = [tx for tx in strict.transactions if any('claims' in patch for _, patch in tx.updates)]
    assert len(batches) == 2
    first, final = batches
    marker_paths = {removal_ref(strict.document(f'users/{UID}'), cid).path for cid in ('c1', 'c2')}
    assert not marker_paths.intersection(doc for doc, _ in first.sets)
    assert marker_paths <= {doc for doc, _ in final.sets}
    assert {path('c1'), path('c2')} <= {doc for doc, patch in final.updates if patch.get('deleted')}
    assert len(final.sets) + len(final.updates) + len(final.deletes) <= cap


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
    # Retirement happens only in the final batch, which failed: the absorbed rows are untouched so far,
    # and the survivor does not list them yet, so deleting it now cannot take live rows with it.
    assert all(partial[f'c{i}'] == before[f'c{i}'] for i in range(1, 6))
    assert 'sync_merged_from' not in partial['c0']
    # Copies are kept only for rows the failed attempt wrote; a resume records the rest again.
    assert priors(strict) and all(partial[e['id']]['v3_rederive_live_run'] == RUN for e in priors(strict))
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
    # Its settle step baselines the rows the failed attempt already wrote, too.
    assert rederive_store.record_baselines(UID, RUN, report['prior_ids']) == len(priors(strict))
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


def test_historical_partition_refuses_a_short_silence_gap():
    first = source('first', AT)
    second = source('second', first['finished_at'] + timedelta(seconds=899))
    parts = backfill.plan_partitions([first, second], SINCE, UNTIL, max_rows=1)
    assert len(parts) == 2 and not parts[0]['forced_cut']
    with pytest.raises(Conflict, match='rederive_live_boundary'):
        backfill.plan_partitions([first, second], SINCE, UNTIL, max_rows=1, historical_sitdown=True)
    second = source('second', first['finished_at'] + timedelta(seconds=900))
    parts = backfill.plan_partitions([first, second], SINCE, UNTIL, max_rows=1, historical_sitdown=True)
    assert parts[0]['until'] == parts[1]['since'] == second['started_at']
    assert not any(part['forced_cut'] for part in parts)


def test_historical_estimate_uses_the_landing_clock_and_checks_speech_at_seam(owner, strict):
    landed = AT + timedelta(hours=1)
    first = source('first', AT, v3_speech_landed_at=landed)
    owner(first)
    partition = {'since': SINCE, 'until': first['finished_at'] + timedelta(seconds=900)}
    options = {'historical_sitdown': True, 'internal_end': True}
    with pytest.raises(Conflict, match='rederive_live_open'):
        backfill.estimate_live_partition(UID, partition, 'dry-run', now=landed + timedelta(seconds=3599), **options)
    settled = landed + timedelta(seconds=3600)
    estimate = backfill.estimate_live_partition(UID, partition, 'dry-run', now=settled, **options)
    assert estimate['stretches'] == 1 and estimate['open_stretches'] == 0
    first['transcript_segments'][0]['end'] += 1
    owner(first)
    with pytest.raises(Conflict, match='rederive_live_boundary'):
        backfill.estimate_live_partition(UID, partition, 'dry-run', now=settled, **options)
    del first['v3_speech_landed_at']
    owner(first)
    with pytest.raises(Conflict, match='rederive_live_landing_unknown'):
        backfill.estimate_live_partition(UID, partition, 'dry-run', now=settled, **options)
    assert not strict.transactions


@pytest.mark.asyncio
@pytest.mark.parametrize('historical', [False, True])
async def test_live_rederive_timing_reaches_the_outline_and_planner(owner, strict, monkeypatch, historical):
    monkeypatch.setenv('CONVERSATIONS_V3_SILENCE_GAP_SECONDS', '900')
    monkeypatch.setenv('CONVERSATIONS_V3_LOCK_SECONDS', '3600')
    monkeypatch.setenv('CONVERSATIONS_V3_STRETCH_COHESION', 'on')
    first = source('first', AT, words=310, v3_speech_landed_at=AT + timedelta(minutes=1))
    second = source('second', AT + timedelta(minutes=11), words=310, v3_speech_landed_at=AT + timedelta(minutes=12))
    owner(first, second, fragment('c1', first), fragment('c2', second))
    outlined = []

    def fixed_outline(uid, messages):
        outlined.append(messages)
        if not historical:
            return ONE_CHAPTER
        return reply(
            {'first_line': 1, 'title': 'First subject', 'kind': 'conversation', 'people': ['A']},
            {'first_line': 2, 'title': 'Second subject', 'kind': 'conversation', 'people': ['A']},
        )

    monkeypatch.setattr(service.models, 'outline', fixed_outline)
    report = {}
    outcome = await service.reconcile(
        UID,
        derive=True,
        live=True,
        since=SINCE,
        until=UNTIL,
        run_id=RUN,
        report=report,
        historical_timing=[900, 3600] if historical else None,
    )
    assert outcome == 'committed'
    if historical:
        assert len(outlined) == 1
        assert 'Find the sit-downs first' in outlined[0][0][1]
        assert '10 min without speech' in outlined[0][1][1]
        assert report['windows_after'] == 1 and report['rows_retired'] == 1
        assert conversations(strict)['c2']['sync_merged_into'] == 'c1'
    else:
        assert len(outlined) == 2
        assert report['windows_after'] == 2 and report['rows_retired'] == 0


@pytest.mark.asyncio
async def test_historical_worker_blocks_on_timing_drift(owner, strict, monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_SILENCE_GAP_SECONDS', '900')
    monkeypatch.setenv('CONVERSATIONS_V3_LOCK_SECONDS', '300')
    monkeypatch.setattr(service.models, 'outline', lambda *a: pytest.fail('outlined with mismatched timing'))
    report = {}
    outcome = await service.reconcile(
        UID,
        derive=True,
        live=True,
        since=SINCE,
        until=UNTIL,
        run_id=RUN,
        report=report,
        historical_timing=[900, 3600],
    )
    assert outcome == 'blocked' and report['blocked_reason'] == 'rederive_live_timing'
    assert not conversations(strict)


def test_dry_run_preview_counts_before_and_after_and_writes_nothing(owner, strict):
    sources, rows = lunch()
    owner(*sources, *rows)
    before = deepcopy(strict.rows)
    est = backfill.estimate_live_partition(UID, {'since': SINCE, 'until': UNTIL}, 'dry-run', now=UNTIL)
    assert strict.rows == before and not strict.transactions
    assert est['rows_eligible'] == 6 and est['visible_before'] == 6
    assert est['windows_after'] == 1 and est['visible_after'] == 1 and est['rows_retired_est'] == 5
    assert est['outline_calls'] == 1 and est['usd'] > 0


@pytest.mark.parametrize('historical', [False, True])
def test_operator_dry_run_prints_the_preview_without_uids(tmp_path, monkeypatch, capsys, historical):
    secret_uid = 'synthetic-owner-uid-123'
    owners = tmp_path / 'owners.txt'
    owners.write_text(secret_uid + '\n')
    meta = [{'id': 'r0', 'recording': True, 'started_at': AT, 'finished_at': AT + timedelta(minutes=1)}]
    monkeypatch.setattr(store, 'backfill_window_metadata', lambda *a: meta)

    def estimate(*args, historical_sitdown, **kwargs):
        assert historical_sitdown == historical
        return {
            'rows_eligible': 18,
            'visible_before': 18,
            'windows_after': 1,
            'visible_after': 1,
            'rows_retired_est': 17,
            'outline_calls': 1,
            'notes_calls': 1,
            'short_task_calls': 0,
            'usd': 0.01,
        }

    monkeypatch.setattr(backfill, 'estimate_live_partition', estimate)
    monkeypatch.setattr(runs, 'list_runs', lambda uid: [])
    monkeypatch.setattr(backfill, 'create_run', lambda *a, **kw: pytest.fail('dry-run wrote a run'))
    args = ['run', '--owners-file', str(owners), '--mode', 'rederive-live', '--dry-run']
    if historical:
        args.append('--historical-sitdown')
    assert script.main([*args, '--since', SINCE.isoformat(), '--until', UNTIL.isoformat()]) == 0
    out = capsys.readouterr().out
    assert secret_uid not in out
    assert ('silence_seconds=900 landing_lock_seconds=3600' in out) == historical
    assert 'windows=18->1' in out and 'visible=18->1' in out and 'rows_retired_est=17' in out and 'llm_calls=2' in out
    # The live edge is the live builder's.
    with pytest.raises(SystemExit):
        script.main([*args, '--days', '1'])


@pytest.mark.asyncio
@pytest.mark.parametrize('historical_timing', [None, [900, 3600]])
async def test_a_live_run_step_replans_with_the_live_loader(monkeypatch, historical_timing):
    calls = []

    async def reconcile(uid, **kw):
        calls.append(kw)
        kw['report']['prior_ids'] = ['c0']
        return 'committed'

    async def blocking(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    run = {
        'run_id': RUN,
        'status': 'planned',
        'mode': backfill.LIVE_MODE,
        'partitions': [{'since': SINCE, 'until': UNTIL, 'status': 'pending'}],
    }
    if historical_timing is not None:
        run['historical_timing'] = historical_timing
    monkeypatch.setattr(backfill, 'run_blocking', blocking)
    monkeypatch.setattr(runs, 'get_run', lambda *a, **kw: deepcopy(run))
    monkeypatch.setattr(runs, 'update_run', lambda *a, **kw: run)
    monkeypatch.setattr(service, 'reconcile', reconcile)
    baselines = []
    monkeypatch.setattr(
        backfill.rederive_store, 'record_baselines', lambda uid, run_id, ids=None: baselines.append((run_id, ids))
    )
    monkeypatch.setattr(
        service, 'drain_backfill', lambda *a, **kw: _done({'processed': 0, 'failed': 0, 'remaining': 0})
    )
    await backfill.run_step(UID, RUN, 0, 'derive')
    assert calls[0]['live'] is True and calls[0]['derive'] is True and calls[0]['rederive'] is False
    assert calls[0]['historical_timing'] == historical_timing
    # The settled partition records the owner-surface baselines undo compares against, for its own copies.
    assert baselines == [(RUN, ['c0'])]


async def _done(value):
    return value


def test_undo_takes_the_backfill_lease_before_anything_else(monkeypatch):
    seen = []
    monkeypatch.setattr(runs, 'update_run', lambda *a, **kw: {})
    monkeypatch.setattr(leases, 'acquire', lambda uid, key, **kw: seen.append(key) or None)
    assert backfill.undo_live_run(UID, RUN) == {'outcome': 'busy', 'reason': 'backfill_pass_in_flight'}
    assert seen == [store.BACKFILL_LEASE]


@pytest.mark.asyncio
@pytest.mark.parametrize('lost_lease', [None, 'builder', store.BACKFILL_LEASE])
async def test_undo_renews_both_leases_during_long_preflight(owner, strict, ledger, monkeypatch, lost_lease):
    sources, rows = lunch(count=3)
    owner(*sources, *rows)
    original = conversations(strict)
    assert (await rederive())[0] == 'committed'
    before_undo = conversations(strict)

    class Clock:
        now_value = datetime.now(timezone.utc)

        @classmethod
        def now(cls, tz):
            return cls.now_value.astimezone(tz)

    monkeypatch.setattr(leases, 'datetime', Clock)
    monkeypatch.setattr(rederive_store, 'datetime', Clock)
    active = {}

    @contextmanager
    def keepalive(uid, key, token, *, firestore_client, max_seconds):
        assert firestore_client is strict and max_seconds is None
        active[key] = token
        try:
            yield
        finally:
            del active[key]

    monkeypatch.setattr(leases, 'keepalive', keepalive)
    original_blocker = rederive_store.live_undo_blocker

    def slow_preflight(uid, run_id, entries, *, firestore_client):
        # Tick the enrolled heartbeats on a fake clock, then finish beyond the initial TTL.
        for _ in range(4):
            Clock.now_value += timedelta(seconds=leases.LEASE_SECONDS / 3)
            for key, token in active.items():
                leases.renew(uid, key, token, firestore_client=firestore_client)
        if lost_lease:
            strict.rows[leases.lease_ref(strict, uid, lost_lease).path]['token'] = 'new-owner'
        return original_blocker(uid, run_id, entries, firestore_client=firestore_client)

    monkeypatch.setattr(rederive_store, 'live_undo_blocker', slow_preflight)
    if lost_lease:
        monkeypatch.setattr(rederive_store, 'undo_live_rederive', lambda *a, **kw: pytest.fail('restoration started'))
        assert backfill.undo_run(UID, RUN, firestore_client=strict) == {'outcome': 'busy', 'reason': 'lease_lost'}
        assert conversations(strict) == before_undo
        assert priors(strict)
        assert strict.rows[leases.lease_ref(strict, UID, lost_lease).path]['token'] == 'new-owner'
    else:
        assert backfill.undo_run(UID, RUN, firestore_client=strict)['outcome'] == 'undone'
        assert conversations(strict) == original
    assert not active


@pytest.mark.asyncio
@pytest.mark.parametrize('lost_lease', ['builder', store.BACKFILL_LEASE])
async def test_undo_transaction_checks_both_builder_tokens(owner, strict, ledger, monkeypatch, lost_lease):
    sources, rows = lunch(count=3)
    owner(*sources, *rows)
    assert (await rederive())[0] == 'committed'
    before_undo = conversations(strict)
    restore = rederive_store.undo_live_rederive

    def lose_lease_before_transaction(uid, held_leases, run_id, entries, *, firestore_client):
        strict.rows[leases.lease_ref(strict, uid, lost_lease).path]['token'] = 'new-owner'
        return restore(uid, held_leases, run_id, entries, firestore_client=firestore_client)

    monkeypatch.setattr(rederive_store, 'undo_live_rederive', lose_lease_before_transaction)
    assert backfill.undo_run(UID, RUN, firestore_client=strict) == {'outcome': 'busy', 'reason': 'lease_lost'}
    assert conversations(strict) == before_undo
    assert priors(strict)
