"""Synthetic donor transfers use frozen live proof and emit only after commit."""

from copy import deepcopy
from datetime import timedelta
import logging

import pytest

from database import conversations as db
from database import smart_merge as smart_db
from tests.unit.test_committed_coverage import _envelope, ROOT, EPOCH, RATE
from utils.conversations.smart_merge_policy import absorb_payloads
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_cross_job_assignment import chunk
from utils.sync import bridge_observation as observation_module
from utils.sync import donor_dedupe
from utils.sync.assignment_index import AssignmentIndex
from utils.sync.intake_completion import log_sync_lineage_append
from utils.sync.live_speech_dedupe import speech_overlap_seconds
from utils.sync.donor_dedupe import DonorDedupe, dedupe_donor
from utils.conversations.smart_merge_policy import rebase_donor_segments

WORDS = 'we should deliver the revised project proposal before the next planning meeting'


@pytest.fixture(autouse=True)
def flags(monkeypatch):
    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_ENABLED', 'true')
    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST', 'u')
    monkeypatch.setenv('SYNC_LINEAGE_LIVE_DEDUPE_ENABLED', 'true')
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'off')
    monkeypatch.setattr(db, 'index_sync_assignment', lambda *a: None)
    monkeypatch.setattr(db, 'find_sync_live_overlap_candidates', lambda *a, **kw: ())


def rows(text=WORDS, *, donor_start=1002):
    live = dict(chunk('live', 1000, WORDS), data_protection_level='standard')
    donor = dict(chunk('donor', donor_start, text), sync_content_revision=1, data_protection_level='standard')
    return live, donor


def absolute(row):
    return [
        dict(segment, timestamp=row['started_at'].timestamp() + segment['start'])
        for segment in row['transcript_segments']
    ]


@pytest.mark.parametrize(
    'text,drop',
    [
        (WORDS, True),
        (WORDS + ' tomorrow', False),
        (WORDS.replace('next', '42'), False),
        (WORDS.replace('should', 'should not'), False),
        ('unrelated new speech occupies exactly the same time range', False),
    ],
)
def test_lexical_fallback_without_capture_context_preserves_novel_speech(text, drop):
    live, donor = rows(text, donor_start=1000)
    incoming = absolute(donor)
    before = deepcopy((live, donor, incoming))
    report = dedupe_donor(incoming, donor, live)
    assert report.kept == ([] if drop else incoming)
    assert report.lexical == int(drop)
    assert (live, donor, incoming) == before


def test_changed_segmentation_and_clock_offset_matches_adjacent_window():
    live, donor = rows(donor_start=1100)
    tokens = WORDS.split()
    live['transcript_segments'] = [
        dict(start=0, end=4, text=' '.join(tokens[:6])),
        dict(start=4, end=9.5, text=' '.join(tokens[6:])),
    ]
    assert not dedupe_donor(absolute(donor), donor, live).kept
    donor['started_at'] += timedelta(seconds=1800)
    assert dedupe_donor(absolute(donor), donor, live).kept


def test_exact_retry_requires_same_sync_scope():
    live, donor = rows('brief acknowledgement', donor_start=1000)
    live['transcript_segments'][0].update(text='brief acknowledgement', speaker_id_scope='sync:synthetic')
    donor['transcript_segments'][0]['speaker_id_scope'] = 'sync:synthetic'
    report = dedupe_donor(absolute(donor), donor, live)
    assert not report.kept and report.exact_retry == 1
    donor['transcript_segments'][0].pop('speaker_id_scope')
    assert dedupe_donor(absolute(donor), donor, live).kept


def test_capture_proof_path_uses_original_receipts_and_frozen_reference(monkeypatch):
    live, donor = rows()
    live['capture_evidence'] = {'origin': 'live'}
    donor['capture_evidence'] = {'origin': 'sync_vad'}
    seen = []
    monkeypatch.setattr(donor_dedupe, 'capture_covered_indices', lambda *a: frozenset())

    def proof(incoming, source, references):
        seen.append((source, references))
        return frozenset({0})

    monkeypatch.setattr(donor_dedupe, 'covered_indices', proof)
    report = dedupe_donor(absolute(donor), donor, live)
    assert not report.kept and report.capture == 1
    assert seen == [(donor, [live])]


@pytest.mark.parametrize('count', [65, 4097])
def test_oversized_pools_abstain_without_truncation(count):
    live, donor = rows()
    if count == 65:
        donor['transcript_segments'] *= count
    else:
        live['transcript_segments'] *= count
    original = absolute(donor)
    report = dedupe_donor(original, donor, live)
    assert report.kept == original and report.incomplete_reason == 'segment_cap'


def setup_transfer(monkeypatch, text=WORDS):
    store = StrictFirestore()
    live, donor = rows(text)
    # First create the sync row independently. Its later live adoption is a
    # content transfer; no S1 attestation is needed on the triggering intake.
    db.assign_sync_conversation('u', donor, firestore_client=store)
    store.rows[('users', 'u', 'conversations', 'live')] = live
    return store, live, donor


def transfer(store):
    return db.assign_sync_conversation(
        'u',
        dict(
            chunk('fresh', 1010, 'This new update has its own distinct information.'), data_protection_level='standard'
        ),
        target_id='live',
        firestore_client=store,
    )


def bridge_lines(caplog):
    return [record.message for record in caplog.records if 'stage=bridge' in record.message]


@pytest.mark.parametrize(
    'text,outcome,kept', [(WORDS, 'bridge_clear', False), (WORDS + ' tomorrow', 'bridge_overlap', True)]
)
def test_assignment_dedupes_donor_and_observes_once_after_commit(monkeypatch, caplog, text, outcome, kept):
    store, live, donor = setup_transfer(monkeypatch, text)
    transaction = store.transaction()
    commit = transaction._commit

    def checked_commit():
        assert not bridge_lines(caplog)
        commit()

    monkeypatch.setattr(transaction, '_commit', checked_commit)
    monkeypatch.setattr(store, 'transaction', lambda: transaction)
    with caplog.at_level(logging.INFO):
        row, created, _ = transfer(store)
    assert not created
    assert (
        any(
            s['text'] == text and s.get('speaker_id_scope', '').startswith('legacy-conversation:')
            for s in row['transcript_segments']
        )
        is kept
    )
    assert len(bridge_lines(caplog)) == 1 and f'outcome={outcome}' in bridge_lines(caplog)[0]
    assert 'target_kind=live' in bridge_lines(caplog)[0] and 'donor_count_bucket=1' in bridge_lines(caplog)[0]
    assert WORDS not in bridge_lines(caplog)[0] and 'uid=' not in bridge_lines(caplog)[0]
    fields = dict(field.split('=', 1) for field in bridge_lines(caplog)[0].split())
    assert float(fields['donor_seconds_in']) == 9.5
    assert float(fields['donor_seconds_dropped']) == (0.0 if kept else 9.5)
    assert float(fields['donor_seconds_retained']) == (9.5 if kept else 0.0)
    assert float(fields['donor_seconds_retained_overlapping_live']) == (7.5 if kept else 0.0)
    assert not any('_sync_lineage_bridge' in value for value in store.rows.values())
    monkeypatch.setattr(store, 'transaction', lambda: StrictFirestore.transaction(store))
    with caplog.at_level(logging.INFO):
        transfer(store)
    assert len(bridge_lines(caplog)) == 1


@pytest.mark.parametrize('off', ['switch', 'cohort'])
def test_disabled_path_is_identical_to_legacy(monkeypatch, caplog, off):
    store, _, _ = setup_transfer(monkeypatch)
    if off == 'switch':
        monkeypatch.setenv('SYNC_LINEAGE_LIVE_DEDUPE_ENABLED', 'false')
    else:
        monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST', 'someone-else')
    with caplog.at_level(logging.INFO):
        row, _, _ = transfer(store)
    assert len(row['transcript_segments']) == 3
    assert not bridge_lines(caplog)


def test_donors_do_not_become_each_others_live_reference(monkeypatch):
    novel = 'we need fresh equipment for the upcoming remote training session tomorrow'
    store, _, _ = setup_transfer(monkeypatch, novel)
    another = dict(chunk('another', 1003, novel), sync_content_revision=1, data_protection_level='standard')
    store.rows[('users', 'u', 'conversations', 'another')] = another
    tx = store.transaction()
    index = AssignmentIndex(tx, store.collection('users').document('u'))
    index.read(another)
    index.write(another, {'another'})
    row, _, _ = transfer(store)
    assert sum(s['text'] == novel for s in row['transcript_segments']) == 2


@pytest.mark.parametrize('text,expected', [(WORDS, 1), (WORDS + ' tomorrow', 2)])
def test_smart_rebase_uses_same_policy_and_keeps_attribution(text, expected):
    live, donor = rows(text)
    observations = []
    merged = rebase_donor_segments(
        live, live['transcript_segments'], donor, donor['transcript_segments'], uid='u', observations=observations
    )
    assert len(merged) == expected
    assert len(observations) == 1
    if expected == 2:
        assert merged[1]['speaker_id_scope'].startswith('legacy-conversation:')
        assert merged[1]['start'] == 2


def test_observation_unknown_and_overlap_precedence_and_fail_open(monkeypatch):
    live, donor = rows()
    incoming = absolute(donor)
    observation = observation_module.bridge_observation(
        live,
        [(incoming, DonorDedupe(incoming, incomplete_reason='segment_cap'))],
        operation='assignment',
        target_kind='live',
    )
    assert observation['outcome'] == 'bridge_overlap'
    incoming[0]['timestamp'] = float('nan')
    observation = observation_module.bridge_observation(
        live, [(incoming, DonorDedupe(incoming))], operation='assignment', target_kind='live'
    )
    assert observation['outcome'] == 'bridge_unknown'
    monkeypatch.setattr(observation_module.logger, 'info', lambda *a: (_ for _ in ()).throw(RuntimeError('synthetic')))
    observation_module.log_bridge_observation(observation)
    store, _, _ = setup_transfer(monkeypatch)
    transfer(store)  # Logging failure cannot turn a committed write into failure.


@pytest.mark.parametrize(
    'live_text,donor_text,drop',
    [
        (WORDS, WORDS, True),
        (WORDS, 'brief phrase', False),
        (WORDS, WORDS + ' tomorrow', False),
        (WORDS + ' in 41 days', WORDS + ' in 42 days', False),
        (WORDS, WORDS.replace('should', 'should not'), False),
        (WORDS, 'actually ' + WORDS, False),
        (WORDS + ' in 41 days', WORDS, False),
        ('never ' + WORDS, WORDS, False),
        ('correction ' + WORDS, WORDS, False),
        (WORDS, WORDS.replace('proposal', 'proposal proposal'), False),
    ],
)
def test_real_committed_frame_receipts_still_require_lexical_safety(live_text, donor_text, drop):
    live, donor = rows(donor_text)
    live['transcript_segments'][0]['text'] = live_text
    live['capture_evidence'] = _envelope(range(8))
    donor['transcript_segments'][0]['id'] = 'synthetic-segment'
    donor['capture_evidence'] = dict(
        version=1,
        capability='source_position',
        coverage='mapped',
        origin='sync_vad',
        receipts=[
            dict(
                segment_id='synthetic-segment',
                capture_root=ROOT,
                clock_epoch=EPOCH,
                rate_hz=RATE,
                channel='mono',
                source_start_frame=1,
                source_end_frame=4,
                source_start_offset=0,
                source_end_offset=0,
            )
        ],
    )
    incoming = absolute(donor)
    before = deepcopy((live, donor, incoming))
    # Real source-frame proof qualifies even the novel/corrective cases.
    assert donor_dedupe.covered_indices(incoming, donor, [live]) == frozenset({0})
    report = dedupe_donor(incoming, donor, live)
    assert report.kept == ([] if drop else incoming)
    assert report.capture == int(drop)
    assert report.lexical == 0 and report.exact_retry == 0
    assert (live, donor, incoming) == before
    # Partial/conflicting coverage cannot delete a short, lexically unproven line.
    donor['transcript_segments'][0]['text'] = 'brief phrase'
    live['capture_evidence'] = _envelope(range(2))
    assert dedupe_donor(absolute(donor), donor, live).kept
    live['capture_evidence'] = _envelope(range(8))
    live['capture_evidence']['conflicts'] = 1
    assert dedupe_donor(absolute(donor), donor, live).kept


def test_live_evidence_survives_donor_and_incoming_receipt_union(monkeypatch):
    store, live, _ = setup_transfer(monkeypatch)
    live['capture_evidence'] = _envelope(range(8))
    store.rows[('users', 'u', 'conversations', 'live')] = deepcopy(live)
    incoming = dict(
        chunk('fresh', 1010),
        data_protection_level='standard',
        capture_evidence={
            'version': 1,
            'capability': 'source_position',
            'coverage': 'incomplete',
            'origin': 'sync_vad',
            'receipts': [],
        },
    )
    row, _, _ = db.assign_sync_conversation('u', incoming, target_id='live', firestore_client=store)
    assert row['capture_evidence'] == live['capture_evidence']
    assert store.rows[('users', 'u', 'conversations', 'live')]['capture_evidence'] == live['capture_evidence']


def test_smart_absorb_persists_deduped_transcript_and_keeps_original_donor(monkeypatch, caplog):
    store = StrictFirestore()
    live, donor = rows()
    live['created_at'] = live['started_at']
    donor['created_at'] = donor['started_at']
    for row in (live, donor):
        store.rows[('users', 'u', 'conversations', row['id'])] = deepcopy(row)
    monkeypatch.setattr(smart_db, 'has_intervening_discarded', lambda *a, **kw: False)
    monkeypatch.setattr(smart_db, 'invalidate_people_stats_cache', lambda *a: None)
    monkeypatch.setattr(db, '_sync_conversation_search_index', lambda *a: None)
    monkeypatch.setattr(db, '_delete_conversation_search_index', lambda *a: None)

    def plan(survivor, survivor_segments, source, source_segments, *args):
        updates = absorb_payloads(
            survivor, survivor_segments, source, source_segments, merged_at=donor['finished_at'], decision={}
        )
        return None, *updates, {}

    with caplog.at_level(logging.INFO):
        result = smart_db.absorb_conversation(
            'u', 'live', 'donor', expected_revision=0, plan=plan, firestore_client=store
        )
    assert result.outcome == 'absorbed'
    payload = store.rows[('users', 'u', 'conversations', 'live')]
    assert (
        len(
            db.decode_transcript_segments_verified(
                'u', payload['transcript_segments'], payload.get('transcript_segments_compressed', False)
            )
        )
        == 1
    )
    tombstone = store.rows[('users', 'u', 'conversations', 'donor')]
    assert tombstone['transcript_segments'] == donor['transcript_segments']
    assert tombstone['sync_merged_into'] == 'live'
    assert len(bridge_lines(caplog)) == 1 and 'outcome=bridge_clear' in bridge_lines(caplog)[0]


def test_receipt_overflow_abstains_and_sync_target_is_unknown():
    live, donor = rows()
    donor['capture_evidence'] = {'receipts': [{}] * 65}
    incoming = absolute(donor)
    report = dedupe_donor(incoming, donor, live)
    assert report.kept == incoming and report.incomplete_reason == 'receipt_cap'
    measured = observation_module.bridge_observation(
        live, [(incoming, report)], operation='assignment', target_kind='sync'
    )
    assert measured['outcome'] == 'bridge_unknown' and measured['target_kind'] == 'sync'


def test_observation_failure_is_unknown(monkeypatch):
    live, donor = rows()
    incoming = absolute(donor)
    monkeypatch.setattr(
        observation_module, 'live_speech_union', lambda *a: (_ for _ in ()).throw(RuntimeError('synthetic'))
    )
    measured = observation_module.bridge_observation(
        live, [(incoming, DonorDedupe(incoming))], operation='assignment', target_kind='live'
    )
    assert measured['outcome'] == 'bridge_unknown' and measured['incomplete_reason'] == 'observation_error'


def test_sync_smart_survivor_does_not_certify_a_live_transfer(monkeypatch, caplog):
    store, _, _ = setup_transfer(monkeypatch)
    store.rows[('users', 'u', 'conversations', 'live')].update(
        sync_content_revision=2,
        smart_merge={'role': 'survivor', 'revision': 1, 'fragments': []},
    )
    with caplog.at_level(logging.INFO):
        transfer(store)
    assert len(bridge_lines(caplog)) == 1
    assert 'target_kind=sync' in bridge_lines(caplog)[0]
    assert 'outcome=bridge_unknown' in bridge_lines(caplog)[0]


def test_capture_exact_retry_preserves_original_indices_after_lexical_drop(monkeypatch):
    live, donor = rows(donor_start=1000)
    live['transcript_segments'].append(dict(start=20, end=22, text='brief phrase'))
    donor['transcript_segments'].extend(
        [
            dict(start=20, end=22, text='brief phrase'),
            dict(start=25, end=27, text='brief phrase'),
        ]
    )
    monkeypatch.setattr(donor_dedupe, 'capture_covered_indices', lambda *a: frozenset({0, 1}))
    monkeypatch.setattr(donor_dedupe, 'covered_indices', lambda *a: frozenset())
    incoming = absolute(donor)
    report = dedupe_donor(incoming, donor, live)
    assert report.kept == [incoming[2]]
    assert report.capture == 1 and report.exact_retry == 1 and report.lexical == 0


def test_numeric_observation_measures_retained_partial_overlap_and_rounds(caplog):
    live, _ = rows()
    live['transcript_segments'] = [
        dict(start=0, end=6, text=WORDS),
        dict(start=4, end=10, text=WORDS),
        # Stored sync text must not enlarge the original-live union.
        dict(start=10, end=30, text=WORDS, speaker_id_scope='sync:previous'),
    ]
    original = [
        dict(timestamp=1002.04, start=0, end=10, text='retained'),
        dict(timestamp=1040, start=0, end=2.26, text='dropped'),
        dict(timestamp=1020, start=0, end=4.12, text='retained outside live'),
    ]
    observation = observation_module.bridge_observation(
        live,
        [(original, DonorDedupe([original[0], original[2]]))],
        operation='assignment',
        target_kind='live',
    )
    assert observation['donor_seconds_in'] == 16.4
    assert observation['donor_seconds_dropped'] == 2.3
    assert observation['donor_seconds_retained'] == 14.1
    assert observation['donor_seconds_retained_overlapping_live'] == 8.0
    assert speech_overlap_seconds(
        [original[0], original[2]], live['transcript_segments'], live_origin=1000, live_pinned=False
    ) == pytest.approx(7.96)
    with caplog.at_level(logging.INFO):
        observation_module.log_bridge_observation(observation)
    assert 'donor_seconds_retained_overlapping_live=8.0' in bridge_lines(caplog)[0]
    assert 'donor_seconds_in=16.4' in bridge_lines(caplog)[0]


def test_fresh_append_overlap_is_measurable_from_append_line(monkeypatch, caplog):
    monkeypatch.setenv('SYNC_SAFETY_WAL_DEDUPE_ENABLED', 'false')
    store = StrictFirestore()
    live, _ = rows()
    store.rows[('users', 'u', 'conversations', 'live')] = live
    incoming = dict(
        chunk('fresh', 1007, 'New words survive though they overlap live speech.'), data_protection_level='standard'
    )
    row, _, _ = db.assign_sync_conversation('u', incoming, target_id='live', firestore_client=store)
    stats = row['_sync_lineage_dedupe']
    assert stats['appended_seconds'] == 9.5
    assert stats['appended_seconds_overlapping_live'] == 2.5
    with caplog.at_level(logging.INFO):
        log_sync_lineage_append(stats)
    assert any('appended_seconds_overlapping_live=2.5' in record.message for record in caplog.records)


def test_append_line_marks_absent_overlap_measurement_unknown(caplog):
    with caplog.at_level(logging.INFO):
        log_sync_lineage_append(
            dict(appended_seconds=2.0, dropped_as_repeat_seconds=0.0, alignment_method='none', repeat_only=False)
        )
    assert any('appended_seconds_overlapping_live=unknown' in record.message for record in caplog.records)


@pytest.mark.parametrize('invalid', ['live', 'incoming', 'denominator_cap', 'malformed'])
def test_fresh_overlap_measurement_abstains_on_incomplete_timing(invalid):
    live, donor = rows()
    incoming = absolute(donor)
    if invalid == 'live':
        live['transcript_segments'][0]['end'] = float('nan')
    elif invalid == 'incoming':
        incoming[0]['timestamp'] = float('inf')
    elif invalid == 'denominator_cap':
        incoming[0]['end'] = 86401
    else:
        live['transcript_segments'] = [None]
    assert speech_overlap_seconds(incoming, live['transcript_segments'], live_origin=1000, live_pinned=False) is None
