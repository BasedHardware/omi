"""A live overlap hint holds standalone visibility until proof, keep or expiry."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config.sync_bridge_containment import (
    CONTAINMENT_TOLERANCE_SECONDS,
    ENV,
    MODE_OFF,
    MODE_ON,
    MODE_SHADOW,
    contained_donor_merge_enabled,
    contained_donor_merge_mode,
)
from database import conversations as db
from tests.unit.test_sync_live_overlap import assign, live_row, seeded
from tests.unit.test_sync_cross_job_assignment import chunk
from tests.unit.test_sync_donor_tombstone_visibility import _install_listing, _rows_from_store
from utils.capture.shadow import SHADOW
from utils.conversations.recorded_time import conversation_span, segment_span
from utils.metrics import OMI_SYNC_BRIDGE_CONTAINED_DONOR_SHADOW_TOTAL
from utils.sync import bridge, bridge_pending
from utils.sync.assignment_errors import SyncAssignmentConflict, SyncAssignmentConflictReason
from utils.sync.intake_completion import complete_sync_intake
from utils.sync.live_overlap import span_contained

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def pending(monkeypatch):
    # The live owner exists but has not yet persisted speech proof. Its wall
    # envelope may hold intake, but cannot authorize transcript transfer.
    live = live_row('in_progress')
    live.update(has_content=False, transcript_segments=[])
    store = seeded(live)
    incoming = dict(
        chunk('wal', 1002),
        data_protection_level='standard',
        structured={'title': 'Retained speech', 'title_provenance': 'server_minimum'},
    )
    row, created, survivors = assign(store, incoming)
    assert created and row['id'] == 'wal' and bridge_pending.hidden(row)
    assert not row['discarded']
    monkeypatch.setattr(
        bridge,
        'read_metadata',
        lambda _, uid, cid, **kw: deepcopy(store.rows.get(('users', uid, 'conversations', cid))),
    )
    monkeypatch.setattr(
        db, 'get_conversation', lambda uid, cid, **kw: deepcopy(store.rows.get(('users', uid, 'conversations', cid)))
    )
    monkeypatch.setattr(db, 'assign_sync_conversation', lambda uid, row, **kw: assign(store, row, **kw))
    monkeypatch.setattr(bridge, 'transfer_donor', lambda *a: None)
    monkeypatch.setattr(bridge, 'retract_sync_bridge_source', lambda *a: None)
    monkeypatch.setattr(bridge, 'mark_sync_bridge_cleaned', lambda *a: True)
    return store, row, created, survivors


def test_default_list_and_count_hide_pending_but_expiry_or_keep_releases_it(monkeypatch, pending):
    store, row, _, _ = pending
    _install_listing(monkeypatch, _rows_from_store(store))
    assert db.get_conversations_without_photos('u', statuses=['completed']) == []
    assert db.get_conversations_count('u', statuses=['completed']) == 0
    assert [
        r['id'] for r in db.get_conversations_without_photos('u', statuses=['completed'], include_discarded=True)
    ] == ['wal']
    saved = store.rows[('users', 'u', 'conversations', 'wal')]
    deadline = saved[bridge_pending.FIELD]['expires_at']
    monkeypatch.setattr(bridge_pending, 'current_time', lambda: deadline)
    _install_listing(monkeypatch, _rows_from_store(store))
    assert [r['id'] for r in db.get_conversations_without_photos('u', statuses=['completed'])] == ['wal']
    assert db.get_conversations_count('u', statuses=['completed']) == 1
    assert db.is_visible_conversation(dict(row, sync_relevance_user_kept=True))


def test_pending_deadline_is_not_extended_by_more_intake(pending):
    store, row, _, _ = pending
    again, _, _ = assign(
        store, dict(chunk('more', 1003, text='Another retained observation.'), data_protection_level='standard')
    )
    assert again[bridge_pending.FIELD] == row[bridge_pending.FIELD]


@pytest.mark.parametrize('finished_status', ['processing', 'completed'])
@pytest.mark.parametrize('expired', [False, True])
def test_live_target_is_bridged_after_capture_finishes(monkeypatch, pending, finished_status, expired):
    from utils.enrichment import callback
    from utils.conversations.summary_delivery import PROCESS_CONTEXT

    store, row, _, _ = pending
    if expired:
        deadline = row[bridge_pending.FIELD]['expires_at']
        monkeypatch.setattr(bridge_pending, 'current_time', lambda: deadline + 1)
    context = {}
    token = PROCESS_CONTEXT.set(context)
    try:
        callback.enrich_conversation('u', 'wal', 'en')
        assert context['defer_reason'] == 'pending_live_bridge'
        if expired:
            assert context['defer_until'] > row[bridge_pending.FIELD]['expires_at']
        else:
            assert context['defer_until'] <= row[bridge_pending.FIELD]['expires_at']
        store.rows[('users', 'u', 'conversations', 'live')].update(live_row(finished_status))
        context.clear()
        callback.enrich_conversation('u', 'wal', 'en')
        assert context == {'redirect_to': 'live'}
    finally:
        PROCESS_CONTEXT.reset(token)
    donor = store.rows[('users', 'u', 'conversations', 'wal')]
    assert donor['deleted'] and donor['sync_merged_into'] == 'live'
    canonical = store.rows[('users', 'u', 'conversations', 'live')]
    assert 'wal' in canonical['sync_merged_from']
    assert not bridge_pending.hidden(canonical)
    assert bridge.finish_sync_bridges('u', 'wal') == 'live'
    _install_listing(monkeypatch, _rows_from_store(store))
    assert [r['id'] for r in db.get_conversations_without_photos('u')] == ['live']


def test_pending_review_intake_enrolls_bridge_even_without_audio(monkeypatch, pending):
    _, row, created, survivors = pending
    row['sync_relevance'] = 'review'
    response = {'new_memories': set(), 'updated_memories': set()}
    finish = MagicMock()
    complete_sync_intake(
        uid='u',
        assigned=row,
        created=created,
        survivors=survivors,
        response=response,
        lock=threading.Lock(),
        language='en',
        audio_enabled=False,
        store_audio=lambda _: None,
        finish=finish,
        mark_finalize=lambda: None,
        acknowledge=lambda: None,
    )
    assert response['_merged'] == {'wal': 'en'}
    finish.assert_called_once()


@pytest.mark.parametrize('indexed', [False, True])
def test_default_home_http_list_hides_pending_row(monkeypatch, pending, indexed):
    from routers import conversations as routes
    from utils.other import endpoints as auth
    from tests.unit.test_sync_donor_tombstone_visibility import _ListingCollection, _ListingDoc, _ListingQuery

    def select(collection, fields):
        return _ListingQuery(
            [
                _ListingDoc(doc.id, {key: value for key, value in doc.to_dict().items() if key in fields})
                for doc in collection._query._docs
            ]
        )

    monkeypatch.setattr(_ListingCollection, 'select', select, raising=False)
    monkeypatch.setattr(db, 'indexed_list_reads_enabled', lambda: indexed)
    store, _, _, _ = pending
    _install_listing(monkeypatch, _rows_from_store(store))
    monkeypatch.setattr(routes, '_heal_locked_conversations_if_eligible', lambda *a: None)
    monkeypatch.setattr(
        routes.ListVersionCheck, 'start', lambda *a: SimpleNamespace(not_modified=None, finish=lambda *a, **kw: None)
    )
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: 'u'
    with TestClient(app) as client:
        response = client.get('/v1/conversations')
        assert response.status_code == 200
        assert response.json() == []
        assert client.get('/v1/conversations/wal').status_code == 404
        store.rows[('users', 'u', 'conversations', 'wal')]['sync_relevance_user_kept'] = True
        _install_listing(monkeypatch, _rows_from_store(store))
        response = client.get('/v1/conversations')
        assert response.status_code == 200
        assert [row['id'] for row in response.json()] == ['wal']


def test_pending_bridge_preserves_an_independently_enriched_donor(pending):
    store, _, _, _ = pending
    source = store.rows[('users', 'u', 'conversations', 'wal')]
    source['structured'] = {'title': 'Generated notes', 'overview': 'Existing protected notes.'}
    store.rows[('users', 'u', 'conversations', 'live')].update(live_row('completed'))
    assert bridge.finish_sync_bridges('u', 'wal') == 'wal'
    assert not source.get('deleted')
    assert not store.rows[('users', 'u', 'conversations', 'live')].get('sync_content_revision')


def _mark_processed(store, conversation_id='wal'):
    source = store.rows[('users', 'u', 'conversations', conversation_id)]
    source['summary_completed_at'] = source['started_at'] + timedelta(seconds=1)
    source['structured'] = {'title': 'Generated notes', 'overview': 'Existing protected notes.'}
    return source


def _finish_target(store, *, end_seconds):
    target = store.rows[('users', 'u', 'conversations', 'live')]
    target.update(live_row('completed'))
    target['transcript_segments'] = [
        {'start': 0.0, 'end': end_seconds, 'text': 'Live capture.', 'speaker_id': 0, 'is_user': False}
    ]
    return target


def test_contained_processed_donor_merges_in_on_mode(monkeypatch, pending):
    monkeypatch.setenv(ENV, 'on')
    store, _, _, _ = pending
    _mark_processed(store)
    # Donor span is 1002..1011.5; the target covers 1000..1020.
    _finish_target(store, end_seconds=20.0)
    assert bridge.finish_sync_bridges('u', 'wal') == 'live'
    donor = store.rows[('users', 'u', 'conversations', 'wal')]
    assert donor['deleted'] and donor['sync_merged_into'] == 'live'
    assert 'wal' in store.rows[('users', 'u', 'conversations', 'live')]['sync_merged_from']


def test_partial_overlap_processed_donor_is_refused_in_on_mode(monkeypatch, pending):
    monkeypatch.setenv(ENV, 'on')
    store, _, _, _ = pending
    source = _mark_processed(store)
    # Donor span is 1002..1011.5; the target covers only 1000..1009.5.
    _finish_target(store, end_seconds=9.5)
    assert bridge.finish_sync_bridges('u', 'wal') == 'wal'
    assert not source.get('deleted')
    assert not source.get('sync_merged_into')


def test_open_target_processed_donor_is_refused_in_on_mode(monkeypatch, pending):
    monkeypatch.setenv(ENV, 'on')
    store, _, _, _ = pending
    source = _mark_processed(store)
    # The target's recorded span covers the whole donor, but its capture is still
    # open, so no merge is due yet. Without the open-target fence this would merge.
    target = _finish_target(store, end_seconds=20.0)
    target['status'] = 'in_progress'
    assert bridge.finish_sync_bridges('u', 'wal') == 'wal'
    assert not source.get('deleted')
    assert not source.get('sync_merged_into')


def test_contained_donor_growing_past_target_refuses_whole_assignment(monkeypatch, pending):
    monkeypatch.setenv(ENV, 'on')
    store, _, _, _ = pending
    _mark_processed(store)
    _finish_target(store, end_seconds=20.0)
    refused = []
    assign_after_bridge_read = db.assign_sync_conversation

    def grow_then_assign(uid, row, **kw):
        # The bridge already proved containment on its own read. Grow the donor
        # past the target before the assignment transaction reads it again.
        grown = store.rows[('users', 'u', 'conversations', 'wal')]
        grown['transcript_segments'] = [
            {'start': 0.0, 'end': 30.0, 'text': 'Donor speech.', 'speaker_id': 0, 'is_user': False}
        ]
        grown['recorded_end'] = grown['started_at'] + timedelta(seconds=30)
        try:
            return assign_after_bridge_read(uid, row, **kw)
        except SyncAssignmentConflict as error:
            refused.append(error.subtype)
            raise

    monkeypatch.setattr(db, 'assign_sync_conversation', grow_then_assign)
    assert bridge.finish_sync_bridges('u', 'wal') == 'wal'
    # The transaction re-proof refuses the assignment whole, not just the donor.
    assert refused == [SyncAssignmentConflictReason.CONTAINED_DONOR_NOT_CONTAINED]
    donor = store.rows[('users', 'u', 'conversations', 'wal')]
    assert not donor.get('deleted') and not donor.get('sync_merged_into')
    assert 'wal' not in store.rows[('users', 'u', 'conversations', 'live')].get('sync_merged_from', [])
    # Nothing dead-letters the row: it is still pending and visible after expiry.
    assert bridge_pending.hidden(donor, now=donor[bridge_pending.FIELD]['expires_at'] + 1) is False


def test_off_refuses_contained_processed_donor_before_any_target_read(monkeypatch, pending):
    monkeypatch.setenv(ENV, 'off')
    store, _, _, _ = pending
    source = _mark_processed(store)
    _finish_target(store, end_seconds=20.0)
    reads = []
    original_get = db.get_conversation

    def record_get(uid, cid, **kw):
        reads.append(cid)
        return original_get(uid, cid, **kw)

    assign = MagicMock()
    monkeypatch.setattr(db, 'get_conversation', record_get)
    monkeypatch.setattr(db, 'assign_sync_conversation', assign)
    assert bridge.finish_sync_bridges('u', 'wal') == 'wal'
    # The pre-change refusal returns before the target is read or any assignment
    # is attempted, so the contained_donor_not_contained race path is unreachable.
    assert 'live' not in reads
    assign.assert_not_called()
    assert not source.get('deleted') and not source.get('sync_merged_into')


def test_shadow_does_not_emit_capture_coverage_comparisons(monkeypatch, caplog, pending):

    monkeypatch.setenv(ENV, 'shadow')
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    store, _, _, _ = pending
    _mark_processed(store)
    _finish_target(store, end_seconds=20.0)

    def live_bind_samples() -> float:
        return sum(
            sample.value
            for metric in SHADOW.collect()
            for sample in metric.samples
            if sample.labels.get('path') == 'live_bind'
        )

    before = live_bind_samples()
    with caplog.at_level('INFO'):
        assert bridge.finish_sync_bridges('u', 'wal') == 'wal'
    # The shadow pass must not inject live_bind disagreement samples into the
    # capture-coverage rollout's own evidence.
    assert live_bind_samples() == before
    assert not [record for record in caplog.records if 'check=live_bind' in record.getMessage()]


def test_shadow_target_read_failure_still_refuses(monkeypatch, caplog, pending):

    monkeypatch.setenv(ENV, 'shadow')
    store, _, _, _ = pending
    source = _mark_processed(store)
    _finish_target(store, end_seconds=20.0)
    original_get = db.get_conversation

    def fail_target_read(uid, conversation_id, **kwargs):
        if conversation_id == 'live':
            raise RuntimeError('transcript segments failed to decode')
        return original_get(uid, conversation_id, **kwargs)

    monkeypatch.setattr(db, 'get_conversation', fail_target_read)
    before = OMI_SYNC_BRIDGE_CONTAINED_DONOR_SHADOW_TOTAL.labels(outcome='error')._value.get()
    with caplog.at_level('INFO', logger='utils.sync.bridge'):
        # A raising target read must refuse like ``off``, never propagate.
        assert bridge.finish_sync_bridges('u', 'wal') == 'wal'
    after = OMI_SYNC_BRIDGE_CONTAINED_DONOR_SHADOW_TOTAL.labels(outcome='error')._value.get()
    assert after == before + 1
    assert 'outcome=error' in caplog.text
    assert not source.get('deleted') and not source.get('sync_merged_into')


def test_off_is_byte_identical_to_the_pre_change_refusal(monkeypatch, pending):
    monkeypatch.setenv(ENV, 'off')
    store, _, _, _ = pending
    source = _mark_processed(store)
    _finish_target(store, end_seconds=20.0)
    before = deepcopy(store.rows)
    assert bridge.finish_sync_bridges('u', 'wal') == 'wal'
    # No stored state changes: the donor is not tombstoned, the target is not
    # touched, and the pending marker is unchanged.
    assert store.rows == before
    assert not source.get('deleted') and not source.get('sync_merged_into')


def test_shadow_counts_and_never_merges(monkeypatch, caplog, pending):

    monkeypatch.setenv(ENV, 'shadow')
    store, _, _, _ = pending
    source = _mark_processed(store)
    _finish_target(store, end_seconds=20.0)
    assign_calls = []
    retract = MagicMock()
    transfer = MagicMock()
    cleaned = MagicMock()
    monkeypatch.setattr(db, 'assign_sync_conversation', lambda *a, **kw: assign_calls.append(kw))
    monkeypatch.setattr(bridge, 'retract_sync_bridge_source', retract)
    monkeypatch.setattr(bridge, 'transfer_donor', transfer)
    monkeypatch.setattr(bridge, 'mark_sync_bridge_cleaned', cleaned)
    before = OMI_SYNC_BRIDGE_CONTAINED_DONOR_SHADOW_TOTAL.labels(outcome='would_absorb')._value.get()
    with caplog.at_level('INFO', logger='utils.sync.bridge'):
        assert bridge.finish_sync_bridges('u', 'wal') == 'wal'
    after = OMI_SYNC_BRIDGE_CONTAINED_DONOR_SHADOW_TOTAL.labels(outcome='would_absorb')._value.get()
    assert after == before + 1
    # Shadow never assigns, tombstones, retracts notes/memories or copies audio.
    assert assign_calls == []
    retract.assert_not_called()
    transfer.assert_not_called()
    cleaned.assert_not_called()
    assert not source.get('deleted') and not source.get('sync_merged_into')
    assert not store.rows[('users', 'u', 'conversations', 'live')].get('sync_merged_from')
    # The one log line carries only the bounded outcome token.
    shadow_lines = [record.getMessage() for record in caplog.records if 'contained_donor_shadow' in record.getMessage()]
    assert shadow_lines == ['event=sync_bridge_contained_donor_shadow outcome=would_absorb']
    for line in shadow_lines:
        assert 'wal' not in line and 'live' not in line
        assert 'Generated notes' not in line and 'Existing protected notes' not in line


@pytest.mark.parametrize(
    'end_seconds, expected',
    [
        (9.5, 'partial_overlap'),
        (20.0, 'would_absorb'),
    ],
)
def test_shadow_outcome_distinguishes_partial_overlap(monkeypatch, caplog, pending, end_seconds, expected):
    monkeypatch.setenv(ENV, 'shadow')
    store, _, _, _ = pending
    _mark_processed(store)
    _finish_target(store, end_seconds=end_seconds)
    with caplog.at_level('INFO', logger='utils.sync.bridge'):
        assert bridge.finish_sync_bridges('u', 'wal') == 'wal'
    assert f'outcome={expected}' in caplog.text


def test_shadow_outcome_marks_a_wall_clock_only_span(monkeypatch, caplog, pending):
    monkeypatch.setenv(ENV, 'shadow')
    store, _, _, _ = pending
    source = _mark_processed(store)
    _finish_target(store, end_seconds=20.0)
    # Legacy donor: its only span is the finished_at envelope, fully inside the
    # target's, but no placed segment proves it.
    source['transcript_segments'] = []
    for field in ('recorded_start', 'recorded_end', 'sync_live_target', 'audio_timeline'):
        source.pop(field, None)
    if (source.get('capture_evidence') or {}).get('origin') == 'live':
        source.pop('capture_evidence')
    with caplog.at_level('INFO', logger='utils.sync.bridge'):
        assert bridge.finish_sync_bridges('u', 'wal') == 'wal'
    assert 'outcome=no_segment_span' in caplog.text


def test_shadow_outcome_marks_a_user_managed_donor_ineligible(monkeypatch, caplog, pending):
    monkeypatch.setenv(ENV, 'shadow')
    store, _, _, _ = pending
    source = _mark_processed(store)
    # A manual speaker receipt makes the transaction refuse the anchor before
    # planning the merge, so shadow must not count it as would_absorb.
    source['manual_speaker_assignments'] = {'0': 'person-1'}
    _finish_target(store, end_seconds=20.0)
    with caplog.at_level('INFO', logger='utils.sync.bridge'):
        assert bridge.finish_sync_bridges('u', 'wal') == 'wal'
    assert 'outcome=donor_ineligible' in caplog.text


def test_shadow_outcome_marks_unplaced_donor_speech(monkeypatch, caplog, pending):
    monkeypatch.setenv(ENV, 'shadow')
    store, _, _, _ = pending
    source = _mark_processed(store)
    source['transcript_segments'] = [
        {'start': 0.0, 'end': 9.5, 'text': 'Placed.', 'speaker_id': 0, 'is_user': False},
        {
            'start': 90.0,
            'end': 95.0,
            'text': 'Unplaced.',
            'speaker_id': 0,
            'is_user': False,
            'audio_alignment': 'unplaced',
        },
    ]
    _finish_target(store, end_seconds=20.0)
    with caplog.at_level('INFO', logger='utils.sync.bridge'):
        assert bridge.finish_sync_bridges('u', 'wal') == 'wal'
    assert 'outcome=unplaced_donor' in caplog.text


@pytest.mark.parametrize('recorded_segments', [True, False])
def test_contained_donor_requires_a_segment_span_on_both_sides(monkeypatch, pending, recorded_segments):

    monkeypatch.setenv(ENV, 'on')
    store, _, _, _ = pending
    source = _mark_processed(store)
    target = _finish_target(store, end_seconds=20.0)
    if recorded_segments:
        assert span_contained(source, target, tolerance_seconds=CONTAINMENT_TOLERANCE_SECONDS)
        assert bridge.finish_sync_bridges('u', 'wal') == 'live'
        donor = store.rows[('users', 'u', 'conversations', 'wal')]
        assert donor['deleted'] and donor['sync_merged_into'] == 'live'
        return
    # Legacy donor: its only span is the finished_at envelope 1002..1011.5,
    # fully inside the target's 1000..1020, but no placed segment proves it.
    source['transcript_segments'] = []
    for field in ('recorded_start', 'recorded_end', 'sync_live_target', 'audio_timeline'):
        source.pop(field, None)
    if (source.get('capture_evidence') or {}).get('origin') == 'live':
        source.pop('capture_evidence')
    envelope = conversation_span(source)
    assert envelope is not None and envelope.recorded_end == source['finished_at']
    assert segment_span(source) is None
    assert not span_contained(source, target, tolerance_seconds=CONTAINMENT_TOLERANCE_SECONDS)
    assert bridge.finish_sync_bridges('u', 'wal') == 'wal'
    donor = store.rows[('users', 'u', 'conversations', 'wal')]
    assert not donor.get('deleted') and not donor.get('sync_merged_into')
    assert not store.rows[('users', 'u', 'conversations', 'live')].get('sync_merged_from')


def test_contained_donor_with_a_tenth_second_overhang_is_refused_in_on_mode(monkeypatch, pending):
    monkeypatch.setenv(ENV, 'on')
    store, _, _, _ = pending
    source = _mark_processed(store)
    # Donor span is 1002..1011.5; the target covers 1000..1011.4, so the donor
    # holds 0.1 s of speech the target never captured. Inward-only containment
    # refuses it; an outward tolerance would have absorbed and lost that speech.
    _finish_target(store, end_seconds=11.4)
    assert bridge.finish_sync_bridges('u', 'wal') == 'wal'
    assert not source.get('deleted') and not source.get('sync_merged_into')
    assert not store.rows[('users', 'u', 'conversations', 'live')].get('sync_merged_from')


def test_contained_donor_strictly_inside_merges_in_on_mode(monkeypatch, pending):
    monkeypatch.setenv(ENV, 'on')
    store, _, _, _ = pending
    _mark_processed(store)
    # Donor span 1002..1011.5 sits strictly inside the target's 1000..1011.6.
    _finish_target(store, end_seconds=11.6)
    assert bridge.finish_sync_bridges('u', 'wal') == 'live'
    donor = store.rows[('users', 'u', 'conversations', 'wal')]
    assert donor['deleted'] and donor['sync_merged_into'] == 'live'


def test_repeat_only_contained_donor_still_commits_the_redirect_in_on_mode(monkeypatch, pending):
    monkeypatch.setenv(ENV, 'on')
    monkeypatch.setenv('SYNC_LINEAGE_LIVE_DEDUPE_ENABLED', 'true')
    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_ENABLED', 'true')
    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST', 'u')
    store, _, _, _ = pending
    source = _mark_processed(store)
    # The donor repeats the target's speech exactly, so live dedupe drops every
    # incoming line. The repeat-only shortcut must not skip the donor redirect
    # this call explicitly requested.
    source['transcript_segments'][0]['speaker_id_scope'] = 'sync:wal'
    target = _finish_target(store, end_seconds=9.5)
    target['started_at'] = source['started_at']
    target['transcript_segments'][0]['text'] = source['transcript_segments'][0]['text']
    target['transcript_segments'][0]['speaker_id_scope'] = 'sync:wal'
    assert bridge.finish_sync_bridges('u', 'wal') == 'live'
    donor = store.rows[('users', 'u', 'conversations', 'wal')]
    assert donor['deleted'] and donor['sync_merged_into'] == 'live'
    assert 'wal' in store.rows[('users', 'u', 'conversations', 'live')]['sync_merged_from']


def test_identical_boundary_donor_passes_the_configured_tolerance():
    origin = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    donor = {'started_at': origin, 'transcript_segments': [{'start': 0.0, 'end': 9.5}]}
    target = {'started_at': origin, 'transcript_segments': [{'start': 0.0, 'end': 9.5}]}
    # The common duplicate shape is an identical re-upload. The configured
    # tolerance is deliberately 0.0 so exact containment passes; any positive
    # inward tolerance would refuse this shape forever.
    assert CONTAINMENT_TOLERANCE_SECONDS == 0.0
    assert span_contained(donor, target, tolerance_seconds=CONTAINMENT_TOLERANCE_SECONDS)
    assert not span_contained(donor, target, tolerance_seconds=0.5)


def test_unplaced_donor_speech_is_refused_in_on_mode(monkeypatch, pending):
    monkeypatch.setenv(ENV, 'on')
    store, _, _, _ = pending
    source = _mark_processed(store)
    # Placed speech inside the target plus an unplaced segment elsewhere: the
    # donor's extent covers only part of its speech, so absorbing it would lose
    # the unplaced remainder. The predicate refuses the whole donor.
    source['transcript_segments'] = [
        {'start': 0.0, 'end': 9.5, 'text': 'Placed.', 'speaker_id': 0, 'is_user': False},
        {
            'start': 90.0,
            'end': 95.0,
            'text': 'Unplaced.',
            'speaker_id': 0,
            'is_user': False,
            'audio_alignment': 'unplaced',
        },
    ]
    _finish_target(store, end_seconds=20.0)
    assert bridge.finish_sync_bridges('u', 'wal') == 'wal'
    assert not source.get('deleted') and not source.get('sync_merged_into')
    assert not store.rows[('users', 'u', 'conversations', 'live')].get('sync_merged_from')


@pytest.mark.parametrize('raw', [None, '', ' ', '1', '0', 'ture', 'TRUE ', 'True', 'off', 'false', 'no', 'disabled'])
def test_mode_parser_resolves_off_for_absent_blank_unknown_and_numeric(monkeypatch, raw):
    if raw is None:
        monkeypatch.delenv(ENV, raising=False)
    else:
        monkeypatch.setenv(ENV, raw)
    assert contained_donor_merge_mode() == MODE_OFF
    assert contained_donor_merge_enabled() is False


@pytest.mark.parametrize('raw', ['on', 'true', 'yes', 'enabled'])
def test_mode_parser_selects_on_for_documented_words(monkeypatch, raw):
    monkeypatch.setenv(ENV, raw)
    assert contained_donor_merge_mode() == MODE_ON
    assert contained_donor_merge_enabled() is True


def test_mode_parser_selects_shadow(monkeypatch):
    monkeypatch.setenv(ENV, 'shadow')
    assert contained_donor_merge_mode() == MODE_SHADOW
    assert contained_donor_merge_enabled() is False


_MODE_DECL = re.compile(rf'^{ENV}:\s*$')
_MODE_OFF_VALUE = re.compile(r"^\s*value:\s*['\"]?off['\"]?\s*$")


def _declared_off_values(path: Path) -> int:
    """Count ``ENV:`` block declarations that carry ``value: 'off'`` on the next line.

    Line-scanning instead of ``yaml.safe_load``: both deploy manifests are ~5k
    lines, and parsing them whole costs more call-phase CPU than the fast-unit
    duration guard allows for a single test.
    """
    lines = path.read_text(encoding='utf-8').splitlines()
    count = 0
    for index, line in enumerate(lines):
        if not _MODE_DECL.match(line.strip()):
            continue
        following = lines[index + 1] if index + 1 < len(lines) else ''
        assert _MODE_OFF_VALUE.match(following), f'{path}: {ENV} at line {index + 1} does not declare value off'
        count += 1
    return count


def test_mode_surfaces_agree_on_off_and_the_three_values():
    assert _declared_off_values(REPO_ROOT / 'backend/deploy/runtime_env/_base.yaml') == 5
    assert _declared_off_values(REPO_ROOT / 'backend/deploy/runtime_env.yaml') == 10

    for chart in ('dev', 'prod'):
        text = (REPO_ROOT / f'backend/charts/backend-listen/{chart}_omi_backend_listen_values.yaml').read_text(
            encoding='utf-8'
        )
        assert f'- name: {ENV}\n    value: "off"' in text

    registry_lines = (REPO_ROOT / 'config/feature-flags.yaml').read_text(encoding='utf-8').splitlines()
    entry_line = next(line for line in registry_lines if f'"key":"{ENV}"' in line)
    entry = json.loads(entry_line.strip().removeprefix('- ').strip())
    assert entry['fail'] == 'closed'
    assert entry['lifecycle'] == 'config_switch'
    for word in ('off', 'shadow', 'on'):
        assert word in entry['summary']

    classification = json.loads((REPO_ROOT / 'config/deployment-setting-classification.json').read_text())
    assert ENV in classification['kinds']['config']
    assert ENV not in classification['kinds']['secret']

    doc = (REPO_ROOT / 'backend/docs/feature-flag-registry.md').read_text(encoding='utf-8')
    row = next(line for line in doc.splitlines() if f'`{ENV}`' in line)
    assert '| closed |' in row
    assert 'off' in row and 'shadow' in row and 'on' in row


def test_sync_enrichment_yields_to_a_bound_processing_finalizer(monkeypatch, pending):
    from utils.enrichment import callback
    from utils.conversations.summary_delivery import PROCESS_CONTEXT

    store, _, _, _ = pending
    store.rows[('users', 'u', 'conversations', 'live')].update(
        live_row('processing'), sync_live_target=True, finalization_job_id='job'
    )
    process = MagicMock()
    monkeypatch.setattr(callback, 'process_conversation', process)
    context = {}
    token = PROCESS_CONTEXT.set(context)
    try:
        callback.enrich_conversation('u', 'live', 'en')
    finally:
        PROCESS_CONTEXT.reset(token)
    assert context == {'defer_reason': 'open_live_target'}
    process.assert_not_called()


def test_flags_off_preserve_standalone_intake_and_skip_target_recovery(monkeypatch):
    monkeypatch.setenv('SYNC_LIVE_OVERLAP_ENABLED', 'false')
    monkeypatch.setenv('SYNC_FINALIZE_TARGET_RECOVERY_ENABLED', 'false')
    live = live_row('in_progress')
    live.update(has_content=False, transcript_segments=[])
    store = seeded(live)
    original = deepcopy(store.rows)
    row, created, _ = assign(store, dict(chunk('wal', 1002), data_protection_level='standard'))
    assert created and row['id'] == 'wal'
    assert not row.get(bridge_pending.FIELD)
    assert db.is_visible_conversation(row)
    assert store.rows[('users', 'u', 'conversations', 'live')] == original[('users', 'u', 'conversations', 'live')]
    monkeypatch.setattr(bridge, 'read_metadata', lambda *a, **kw: deepcopy(row))
    recover = MagicMock(side_effect=AssertionError('flag-off must not recover a target'))
    monkeypatch.setattr(bridge, '_finish_pending_live_bridge', recover)
    assert bridge.finish_sync_bridges('u', 'wal') == 'wal'
    recover.assert_not_called()
