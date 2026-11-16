"""Synthetic two-lane transcripts: bounded dedupe and pinned recording bounds."""

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_cross_job_assignment import chunk, intake
from utils.sync import assignment
from utils.sync.donor_dedupe import dedupe_donor


def at(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc)


def paragraph(index, *, scope='final:batch:live'):
    return dict(
        id=f'{scope}-{index}',
        start=index * 4.0,
        end=index * 4.0 + 3,
        text=f'The revised project proposal for section{index} needs another detailed planning meeting',
        speaker_id=0,
        speaker_id_scope=scope,
        is_user=False,
    )


def recording(count=100):
    return dict(
        chunk('live', 1000),
        record_lane_owner='batch_live_v1',
        record_audio_closed=True,
        record_projection_revision=1,
        sync_live_target=True,
        sync_content_revision=1,
        finished_at=at(1000 + count * 4),
        transcript_segments=[paragraph(i) for i in range(count)],
    )


@pytest.fixture(autouse=True)
def gates(monkeypatch):
    monkeypatch.setattr(assignment, 'sync_live_dedupe_active_for', lambda _: True)
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'off')


def test_long_donor_uses_local_windows_without_losing_novel_negation_or_number():
    live = recording()
    donor = dict(chunk('donor', 1000), transcript_segments=[paragraph(i, scope='final:batch:sync') for i in range(100)])
    for index, extra in [(20, ' tomorrow'), (40, ' not'), (60, ' 42')]:
        donor['transcript_segments'][index]['text'] += extra
    incoming = [dict(s, timestamp=1000 + s['start']) for s in donor['transcript_segments']]
    before = deepcopy((donor, live, incoming))
    report = dedupe_donor(incoming, donor, live)
    assert [s['id'] for s in report.kept] == [f'final:batch:sync-{i}' for i in (20, 40, 60)]
    assert report.lexical == 97 and report.incomplete_reason == 'none'
    assert (donor, live, incoming) == before


def test_over_budget_donor_remains_intact():
    incoming = [dict(paragraph(i), timestamp=1000 + i * 4) for i in range(4097)]
    assert dedupe_donor(incoming, {}, recording(1)).kept == incoming


def test_long_donor_merge_keeps_one_copy_and_ancestry():
    store = StrictFirestore()
    live = recording()
    donor = dict(
        chunk('donor', 1000),
        finished_at=live['finished_at'],
        sync_content_revision=1,
        transcript_segments=[paragraph(i, scope='final:batch:sync') for i in range(100)],
    )
    store.rows[('users', 'u', 'conversations', 'live')] = deepcopy(live)
    store.rows[('users', 'u', 'conversations', 'donor')] = deepcopy(donor)
    assigned, created, _ = intake(store, donor, target_id='live')
    assert not created
    assert [s['id'] for s in assigned['transcript_segments']] == [s['id'] for s in live['transcript_segments']]
    assert assigned['sync_merged_from'] == ['donor']
    assert store.rows[('users', 'u', 'conversations', 'donor')]['sync_merged_into'] == 'live'


def test_late_sync_append_matches_final_batch_without_frame_receipts():
    store = StrictFirestore()
    live = recording()
    store.rows[('users', 'u', 'conversations', 'live')] = deepcopy(live)
    incoming = dict(chunk('fresh', 1000), transcript_segments=[paragraph(10, scope='final:batch:sync')])
    incoming['finished_at'] = at(1043)
    assigned, created, survivors = intake(store, incoming, target_id='live')
    assert not created and not survivors
    assert assigned['transcript_segments'] == live['transcript_segments']


@pytest.mark.parametrize('mode', ['on', 'off'])
@pytest.mark.parametrize('kind', ['earlier', 'later'])
def test_stamped_sync_outside_sealed_recording_stays_correctly_timed(monkeypatch, mode, kind):
    monkeypatch.setenv('LATE_AUDIO_SYNC_INTAKE_ENABLED', mode)
    store = StrictFirestore()
    live = recording(10)
    store.rows[('users', 'u', 'conversations', 'live')] = deepcopy(live)
    incoming = chunk('sync', 960 if kind == 'earlier' else 1050)
    assigned, created, survivors = intake(store, incoming, target_id='live')
    assert created and survivors and assigned['id'] == 'sync'
    assert assigned['started_at'] == incoming['started_at']
    assert assigned['transcript_segments'][0]['start'] == 0
    assert store.rows[('users', 'u', 'conversations', 'live')] == live


def test_gap_connected_earlier_donor_is_not_swept_into_short_live_row():
    store = StrictFirestore()
    live = recording(10)
    donor = dict(chunk('earlier', 900), finished_at=at(999), sync_content_revision=1)
    store.rows[('users', 'u', 'conversations', 'live')] = deepcopy(live)
    store.rows[('users', 'u', 'conversations', 'earlier')] = deepcopy(donor)
    assigned, _, _ = intake(store, chunk('fresh', 1020), candidate_id='earlier', target_id='live')
    assert assigned['id'] == 'live'
    assert 'earlier' not in assigned['sync_merged_from']
    assert all(s['start'] >= 0 for s in assigned['transcript_segments'])
    assert store.rows[('users', 'u', 'conversations', 'earlier')] == donor


def test_open_batch_target_still_accepts_later_speech():
    store = StrictFirestore()
    live = recording(1)
    live.update(record_audio_closed=False, status='in_progress')
    store.rows[('users', 'u', 'conversations', 'live')] = live
    assigned, created, survivors = intake(store, chunk('fresh', 1060), target_id='live')
    assert assigned['id'] == 'live' and not created and survivors


def test_existing_negative_offset_donor_cannot_hide_behind_later_envelope():
    store = StrictFirestore()
    live = recording(10)
    donor = dict(chunk('earlier', 1001), sync_content_revision=1)
    donor['transcript_segments'][0].update(start=-900, end=-890)
    store.rows[('users', 'u', 'conversations', 'live')] = deepcopy(live)
    store.rows[('users', 'u', 'conversations', 'earlier')] = deepcopy(donor)
    assigned, _, _ = intake(store, chunk('fresh', 1020), candidate_id='earlier', target_id='live')
    assert assigned['id'] == 'live' and 'earlier' not in assigned['sync_merged_from']
    assert store.rows[('users', 'u', 'conversations', 'earlier')] == donor


def test_temporal_discovery_chooses_containing_recording_over_later_overlap():
    from utils.sync.live_overlap import choose_live_overlap

    incoming = chunk('sync', 1005)
    covering = recording(10)
    covering.update(id='covering', has_content=True)
    later = deepcopy(covering)
    later.update(id='later', started_at=at(1006))
    assert choose_live_overlap([later, covering], incoming) == 'covering'
