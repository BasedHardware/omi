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


def test_review_reproduction_later_utterance_in_long_donor_is_not_a_repeat():
    live = recording(65)
    donor = dict(chunk('donor', 1000), transcript_segments=[paragraph(i, scope='final:batch:sync') for i in range(65)])
    for index, segment in enumerate(donor['transcript_segments']):
        segment.update(start=1000 + index * 4, end=1003 + index * 4, text=f'Novel donor speech for detail{index}')
    donor['transcript_segments'][0].update(start=60, end=63, text=live['transcript_segments'][0]['text'])
    incoming = [dict(segment, timestamp=1000 + segment['start']) for segment in donor['transcript_segments']]
    report = dedupe_donor(incoming, donor, live)
    assert report.kept == incoming
    assert report.capture == report.lexical == report.exact_retry == 0


@pytest.mark.parametrize('skew', [-26.4, 26.4])
def test_long_donor_true_copies_with_realistic_clock_skew_have_ordered_neighbours(skew):
    live = recording(65)
    incoming = [dict(paragraph(i, scope='final:batch:sync'), timestamp=1000 + i * 4 + skew) for i in range(65)]
    before = deepcopy((incoming, live))
    report = dedupe_donor(incoming, {}, live)
    assert not report.kept and report.lexical == 65 and report.capture == 0
    assert (incoming, live) == before


@pytest.mark.parametrize('repeat_in', ['incoming', 'live', 'live_duration_mismatch'])
def test_repeated_phrase_within_discovery_window_abstains_even_at_nearest_time(repeat_in):
    live = recording(65)
    incoming = [dict(paragraph(i, scope='final:batch:sync'), timestamp=1000 + i * 4) for i in range(65)]
    repeated = incoming[10]['text']
    if repeat_in == 'incoming':
        incoming[25]['text'] = repeated
    else:
        live['transcript_segments'][25]['text'] = repeated
        if repeat_in == 'live_duration_mismatch':
            live['transcript_segments'][25]['end'] = 200
    report = dedupe_donor(incoming, {}, live)
    assert incoming[10] in report.kept
    if repeat_in == 'incoming':
        assert incoming[25] in report.kept


def test_shifted_isolated_or_reordered_matches_cannot_establish_an_occurrence():
    live = recording(65)
    incoming = [dict(paragraph(i, scope='final:batch:sync'), timestamp=1000 + i * 4 + 26.4) for i in (1, 0, 2)]
    assert dedupe_donor(incoming, {}, live).kept == incoming
    assert dedupe_donor(incoming[:1], {}, live).kept == incoming[:1]
    incoming[0]['timestamp'] = 1000 + incoming[0]['start'] + 1
    assert dedupe_donor(incoming[:1], {}, live).kept == incoming[:1]


def test_neighbour_offsets_must_agree_and_cannot_explain_a_sixty_second_repeat():
    live = recording(65)
    for offsets in ([26.4, 27, 30.4], [60, 60, 60]):
        incoming = [
            dict(paragraph(i, scope='final:batch:sync'), timestamp=1000 + i * 4 + skew)
            for i, skew in enumerate(offsets)
        ]
        assert dedupe_donor(incoming, {}, live).kept == incoming


def test_reworded_incoming_occurrences_cannot_share_one_reference_occurrence():
    live = recording(65)
    incoming = [dict(paragraph(i, scope='final:batch:sync'), timestamp=1000 + i * 4) for i in range(65)]
    incoming[11]['text'] = 'Well ' + incoming[10]['text']
    report = dedupe_donor(incoming, {}, live)
    assert incoming[10] in report.kept and incoming[11] in report.kept


def test_frame_proof_still_certifies_a_later_match_without_lexical_clock_inference(monkeypatch):
    from utils.sync import donor_dedupe

    live = recording(65)
    incoming = [dict(paragraph(0, scope='final:batch:sync'), timestamp=1060)]
    monkeypatch.setattr(donor_dedupe, 'capture_covered_indices', lambda *a: frozenset({0}))
    monkeypatch.setattr(donor_dedupe, 'covered_indices', lambda *a: frozenset())
    report = dedupe_donor(incoming, {}, live)
    assert not report.kept and report.capture == 1 and report.lexical == 0


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
