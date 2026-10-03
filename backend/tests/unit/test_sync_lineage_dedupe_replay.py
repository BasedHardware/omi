"""Bound safety-WAL uploads drop speech that provably repeats the live row.

Synthetic replay: one live generation row carries seven transcript lines; a WAL
upload stamped for it brings ten segments — seven lexical rewordings of the
live lines plus three genuinely new ones — under phone-clock skews of +40 s
and +1200 s. A drop requires independent source-frame capture proof: paired
``sync_vad`` receipts plus ``origin=live`` run coverage; without proof even
identical wording is legitimate repetition and appends. An upload that is
entirely proven repeats is acknowledged with no writes, no enrichment receipt
and no audio effects; the flag off, a mistyped value or a uid outside the
lineage allowlist restores the previous intake exactly. All ids and text are
synthetic.
"""

import json
import logging
import threading
from copy import deepcopy
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from config import sync_lineage
from config.sync_live_dedupe import SYNC_LINEAGE_LIVE_DEDUPE_ENV
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_cross_job_assignment import conversations, intake
from utils.firestore_document_size import estimate_firestore_document_bytes
from utils.sync import assignment
from utils.sync.capture_repeat_evidence import capture_covered_indices
from utils.sync.recording_lineage import select_segment_targets

T0 = 1_800_000_000.0
LIVE_ID = 'LIVE-ROW'
ORIGIN = 'REC-1'

LIVE = [f'the quarterly planning review meeting covered agenda item {n} in detail' for n in range(1, 8)]
NEW = [
    'a genuinely new remark about weekend hiking plans with close friends',
    'the dog barked twice at the delivery driver near the front gate',
    'dinner reservations moved to eight thirty at the corner bistro tonight',
]


def at(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc)


def reworded(text):
    words = [token for token in text.replace('the ', '').split(' ') if token]
    return 'Um, ' + ' '.join(words).capitalize() + '!'


def live_row(**extra):
    row = {
        'id': LIVE_ID,
        'started_at': at(T0),
        'finished_at': at(T0 + 70),
        'source': 'omi',
        'client_device_id': 'pendant',
        'is_locked': False,
        'discarded': False,
        'status': 'completed',
        'external_data': {'recording_session_id': ORIGIN, 'recording_origin_id': ORIGIN},
        'transcript_segments': [
            {
                'start': i * 10.0,
                'end': i * 10.0 + 10.0,
                'text': LIVE[i],
                'speaker': 'SPEAKER_00',
                'speaker_id': 0,
                'is_user': False,
            }
            for i in range(len(LIVE))
        ],
    }
    row.update(extra)
    return row


def wal(skew, texts, row_id='WAL-1'):
    start = T0 + skew
    return {
        'id': row_id,
        'started_at': at(start),
        'finished_at': at(start + 10 * len(texts)),
        'source': 'omi',
        'client_device_id': 'pendant',
        'discarded': False,
        'status': 'completed',
        'transcript_segments': [
            {'start': i * 10.0 + 0.7, 'end': i * 10.0 + 10.7, 'text': text, 'speaker_id': 0, 'is_user': False}
            for i, text in enumerate(texts)
        ],
    }


PROOF_ROOT = 'a1b2c3d4-1111-4222-8333-444455556666'
PROOF_EPOCH = 7
PROOF_RATE = 16000
PROOF_SPF = 160


def _receipt(segment_id, index):
    return {
        'segment_id': segment_id,
        'capture_root': PROOF_ROOT,
        'clock_epoch': PROOF_EPOCH,
        'channel': 'mono',
        'source_start_frame': index * 1000,
        'source_start_offset': 0,
        'source_end_frame': index * 1000 + 999,
        'source_end_offset': 0,
        'rate_hz': PROOF_RATE,
        'producer_revision': 'sync_vad_stt_v1',
    }


def sync_evidence(segment_ids):
    return {
        'version': 1,
        'capability': 'source_position',
        'coverage': 'mapped',
        'origin': 'sync_vad',
        'receipts': [_receipt(segment_id, i) for i, segment_id in enumerate(segment_ids)],
    }


def live_evidence(frame_count=100000, **over):
    evidence = {
        'version': 1,
        'capability': 'source_position',
        'coverage': 'mapped',
        'origin': 'live',
        'conflicts': 0,
        'runs': [
            {
                'capture_root': PROOF_ROOT,
                'clock_epoch': PROOF_EPOCH,
                'rate_hz': PROOF_RATE,
                'channel': 'mono',
                'source_frame_start': 0,
                'source_frame_end': frame_count,
                'decoded_sample_start': 0,
                'decoded_sample_end': frame_count * PROOF_SPF,
                'samples_per_frame': PROOF_SPF,
            }
        ],
    }
    evidence.update(over)
    return evidence


def prove(chunk, row, live_env=None):
    """Attach paired sync_vad receipts + live run coverage proving ``chunk`` repeats ``row``."""
    for i, segment in enumerate(chunk['transcript_segments']):
        segment.setdefault('id', f"{chunk['id']}-seg-{i}")
    chunk['capture_evidence'] = sync_evidence([s['id'] for s in chunk['transcript_segments']])
    row['capture_evidence'] = live_evidence() if live_env is None else live_env
    return chunk, row


def donor_chunk(donor_id='DONOR-1', start=T0 + 50, texts=None, duration=10.0):
    texts = texts or ['an unrelated remark about office furniture logistics']
    return {
        'id': donor_id,
        'started_at': at(start),
        'finished_at': at(start + duration * len(texts)),
        'source': 'omi',
        'client_device_id': 'pendant',
        'discarded': False,
        'status': 'completed',
        'transcript_segments': [
            {
                'start': i * duration,
                'end': (i + 1) * duration,
                'text': text,
                'speaker_id': 0,
                'is_user': False,
            }
            for i, text in enumerate(texts)
        ],
    }


def seeded_store_with_donor(rows, donor=None):
    """Seed ``rows`` directly and the donor through intake so the index sees it."""
    store = seeded_store(rows)
    intake(store, donor or donor_chunk())
    return store


def seeded_store(rows):
    store = StrictFirestore()
    for row in rows:
        store.rows[('users', 'u', 'conversations', row['id'])] = deepcopy(row)
    return store


def texts_of(store, cid):
    return [segment['text'] for segment in store.rows[('users', 'u', 'conversations', cid)]['transcript_segments']]


@pytest.fixture(scope='module', autouse=True)
def load_dependencies():
    from database import conversations  # noqa: F401
    from models import transcript_segment  # noqa: F401
    from utils.conversations import lifecycle  # noqa: F401
    from utils.sync import pipeline  # noqa: F401


@pytest.fixture(autouse=True)
def default_flags(monkeypatch):
    monkeypatch.delenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, raising=False)
    monkeypatch.delenv(sync_lineage.SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST_ENV, raising=False)


@pytest.mark.parametrize('skew', [40, 1200])
def test_receipt_only_mixed_upload_appends_everything(skew):
    """Receipt-only envelopes prove nothing: even matching reworded speech appends."""
    row = live_row()
    texts = [reworded(text) for text in LIVE] + NEW
    chunk = wal(skew, texts)
    prove(chunk, row)
    store = seeded_store([row])
    assigned, created, survivors = intake(store, chunk, target_id=LIVE_ID)
    assert created is False and assigned['id'] == LIVE_ID
    assert len(survivors) == 10
    stats = assigned['_sync_lineage_dedupe']
    assert stats['appended_seconds'] == 100.0 and stats['dropped_as_repeat_seconds'] == 0.0
    assert stats['alignment_method'] == 'none' and stats['repeat_only'] is False
    stored = texts_of(store, LIVE_ID)
    assert sorted(stored) == sorted(LIVE + texts)
    row = store.rows[('users', 'u', 'conversations', LIVE_ID)]
    live_segments = {segment['text']: segment for segment in row['transcript_segments']}
    assert live_segments[LIVE[0]]['speaker'] == 'SPEAKER_00'
    assert live_segments[NEW[0]]['start'] == pytest.approx(skew + 7 * 10.0 + 0.7)
    assert {key for key in row if key.startswith('_sync_lineage')} == set()


@pytest.mark.parametrize('skew', [40, 1200])
def test_receipt_only_repeats_append_under_both_measured_skews(skew):
    row = live_row()
    texts = [reworded(text) for text in LIVE]
    chunk = wal(skew, texts)
    prove(chunk, row)
    store = seeded_store([row])
    assigned, created, survivors = intake(store, chunk, target_id=LIVE_ID)
    assert created is False and [s['text'] for s in survivors] == texts
    assert '_sync_lineage_repeat_only' not in assigned
    assert sorted(texts_of(store, LIVE_ID)) == sorted(LIVE + texts)


@pytest.mark.parametrize('skew', [40, 1200])
def test_unproven_identical_and_reworded_repeats_all_append(skew):
    """Absent capture proof the same wording is legitimate repetition, not a retry."""
    store = seeded_store([live_row()])
    chunk = wal(skew, list(LIVE) + [reworded(text) for text in LIVE])
    assigned, created, survivors = intake(store, chunk, target_id=LIVE_ID)
    assert created is False and len(survivors) == 14
    assert assigned['_sync_lineage_dedupe']['appended_seconds'] == 140.0
    stored = texts_of(store, LIVE_ID)
    assert len(stored) == len(LIVE) + 14


@pytest.mark.parametrize('speaker_id', [0, 3])
def test_unproven_same_range_repeat_is_legitimate_speech_for_any_speaker(speaker_id):
    store = seeded_store([live_row()])
    chunk = wal_at(T0, [LIVE[0]], 10.0)
    chunk['transcript_segments'][0]['speaker_id'] = speaker_id
    _, _, survivors = intake(store, chunk, target_id=LIVE_ID)
    assert [s['text'] for s in survivors] == [LIVE[0]]


def test_repeat_under_a_different_capture_root_is_legitimate_repetition():
    """Independent capture of the same words at the same absolute range is kept."""
    row = live_row()
    chunk = wal_at(T0, [LIVE[0]], 10.0)
    prove(chunk, row, live_env=live_evidence())
    for receipt in chunk['capture_evidence']['receipts']:
        receipt['capture_root'] = 'b2c3d4e5-2222-4333-8444-555566667777'
    store = seeded_store([row])
    _, _, survivors = intake(store, chunk, target_id=LIVE_ID)
    assert [s['text'] for s in survivors] == [LIVE[0]]


def test_same_wording_at_an_uncovered_frame_ordinal_is_legitimate_repetition():
    """A receipt claiming a later, uncovered capture ordinal proves nothing."""
    row = live_row()
    chunk = wal(40, [reworded(text) for text in LIVE])
    prove(chunk, row)
    for receipt in chunk['capture_evidence']['receipts']:
        receipt['source_start_frame'] += 100000
        receipt['source_end_frame'] += 100000
    store = seeded_store([row])
    _, _, survivors = intake(store, chunk, target_id=LIVE_ID)
    assert len(survivors) == len(LIVE)


@pytest.mark.parametrize('live_env', [None, 'partial', 'conflict'])
def test_absent_partial_or_conflicting_live_evidence_keeps_everything(live_env):
    row = live_row()
    chunk = wal(40, [reworded(text) for text in LIVE])
    if live_env == 'partial':
        prove(chunk, row, live_env=live_evidence(frame_count=50))
    elif live_env == 'conflict':
        prove(chunk, row, live_env=live_evidence(conflicts=1))
    else:
        for i, segment in enumerate(chunk['transcript_segments']):
            segment.setdefault('id', f"{chunk['id']}-seg-{i}")
        chunk['capture_evidence'] = sync_evidence([s['id'] for s in chunk['transcript_segments']])
    store = seeded_store([row])
    _, _, survivors = intake(store, chunk, target_id=LIVE_ID)
    assert len(survivors) == 7


def test_receipt_only_upload_appends_and_reports_no_dropped_speech():
    row = live_row()
    texts = [reworded(text) for text in LIVE]
    chunk = wal(40, texts)
    prove(chunk, row)
    store = seeded_store([row])
    donorless = deepcopy(store.rows)
    assigned, created, survivors = intake(store, chunk, target_id=LIVE_ID)
    assert created is False and [s['text'] for s in survivors] == texts
    assert '_sync_lineage_repeat_only' not in assigned
    assert assigned['_sync_lineage_dedupe']['repeat_only'] is False
    assert assigned['_sync_lineage_dedupe']['dropped_as_repeat_seconds'] == 0.0
    assert assigned['sync_relevance'] == 'keep'
    assert store.rows != donorless
    assert sorted(texts_of(store, LIVE_ID)) == sorted(LIVE + texts)


@pytest.mark.parametrize('flag', ['off', 'disabled-typo'])
def test_flag_off_and_mistyped_restore_the_old_intake_exactly(monkeypatch, flag):
    monkeypatch.setenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, flag)
    store = seeded_store([live_row()])
    chunk = wal(40, [reworded(text) for text in LIVE] + NEW)
    assigned, created, survivors = intake(store, chunk, target_id=LIVE_ID)
    assert created is False and len(survivors) == 10
    assert '_sync_lineage_dedupe' not in assigned and '_sync_lineage_repeat_only' not in assigned
    assert len(texts_of(store, LIVE_ID)) == len(LIVE) + 10


def test_uid_outside_the_lineage_allowlist_uses_the_old_intake(monkeypatch):
    monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST_ENV, 'other-uid')
    store = seeded_store([live_row()])
    chunk = wal(40, [reworded(text) for text in LIVE])
    assigned, created, survivors = intake(store, chunk, target_id=LIVE_ID)
    assert len(survivors) == 7 and '_sync_lineage_dedupe' not in assigned


def test_receipt_only_repeats_on_capture_field_rows_report_no_alignment():
    segments = [
        dict(
            segment,
            audio_capture_start=T0 + segment['start'],
            audio_capture_end=T0 + segment['end'],
        )
        for segment in live_row()['transcript_segments']
    ]
    row = live_row(transcript_segments=segments)
    texts = [reworded(text) for text in LIVE]
    chunk = wal(40, texts)
    prove(chunk, row)
    store = seeded_store([row])
    assigned, _, survivors = intake(store, chunk, target_id=LIVE_ID)
    assert [s['text'] for s in survivors] == texts
    assert assigned['_sync_lineage_dedupe']['alignment_method'] == 'none'


def test_pinned_v2_origin_receipt_only_repeats_report_no_alignment():
    row = live_row(audio_timeline={'version': 2})
    texts = [reworded(text) for text in LIVE]
    chunk = wal(40, texts)
    prove(chunk, row)
    store = seeded_store([row])
    assigned, _, survivors = intake(store, chunk, target_id=LIVE_ID)
    assert [s['text'] for s in survivors] == texts
    assert assigned['_sync_lineage_dedupe']['alignment_method'] == 'none'


def test_non_live_sync_target_is_never_deduped():
    sync_row = live_row(id='SYNC-ROW', sync_content_revision=2)
    sync_row['transcript_segments'] = [
        dict(segment, speaker_id_scope='sync:earlier') for segment in sync_row['transcript_segments']
    ]
    store = seeded_store([sync_row])
    store.rows[('users', 'u', 'conversations', 'SYNC-ROW')]['sync_live_target'] = False
    assigned, _, survivors = intake(store, wal(40, [reworded(text) for text in LIVE]), target_id='SYNC-ROW')
    assert survivors and '_sync_lineage_dedupe' not in assigned


def test_append_to_live_row_with_no_segments_keeps_everything():
    store = seeded_store([live_row(transcript_segments=[])])
    _, _, survivors = intake(store, wal(40, NEW), target_id=LIVE_ID)
    assert len(survivors) == 3


def short_text_row():
    row = live_row()
    row['transcript_segments'][0] = {
        'start': 0.0,
        'end': 3.0,
        'text': 'okay see you',
        'speaker': 'SPEAKER_00',
        'speaker_id': 0,
        'is_user': False,
    }
    return row


def wal_at(abs_start, texts, duration):
    return {
        'id': 'WAL-1',
        'started_at': at(abs_start),
        'finished_at': at(abs_start + duration * len(texts)),
        'source': 'omi',
        'client_device_id': 'pendant',
        'discarded': False,
        'status': 'completed',
        'transcript_segments': [
            {'start': 0.0, 'end': duration, 'text': text, 'speaker_id': 0, 'is_user': False} for text in texts
        ],
    }


def test_unrelated_new_text_at_an_occupied_absolute_range_is_kept():
    store = seeded_store([live_row()])
    chunk = wal_at(T0, [NEW[0]], 10.0)
    assigned, created, survivors = intake(store, chunk, target_id=LIVE_ID)
    assert created is False and [s['text'] for s in survivors] == [NEW[0]]
    assert assigned['_sync_lineage_dedupe']['appended_seconds'] == 10.0
    assert NEW[0] in texts_of(store, LIVE_ID)


def test_unrelated_new_text_at_an_occupied_range_drops_when_flag_off(monkeypatch):
    monkeypatch.setenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, 'off')
    store = seeded_store([live_row()])
    _, _, survivors = intake(store, wal_at(T0, [NEW[0]], 10.0), target_id=LIVE_ID)
    assert survivors == []


def test_identical_retry_of_a_short_line_reports_exact_retry_no_op():
    row = short_text_row()
    row['transcript_segments'][0]['speaker_id_scope'] = 'sync:wal-short'
    store = seeded_store([row])
    before = deepcopy(store.rows)
    chunk = wal_at(T0, ['okay see you'], 3.0)
    chunk['transcript_segments'][0]['speaker_id_scope'] = 'sync:wal-short'
    assigned, created, survivors = intake(store, chunk, target_id=LIVE_ID)
    assert created is False and survivors == []
    assert assigned['_sync_lineage_repeat_only'] is True
    stats = assigned['_sync_lineage_dedupe']
    assert stats['alignment_method'] == 'exact_retry' and stats['dropped_as_repeat_seconds'] == 3.0
    assert store.rows == before


def test_receipt_only_identical_text_and_range_is_kept():
    row = live_row()
    chunk = wal_at(T0, [LIVE[0]], 10.0)
    prove(chunk, row)
    store = seeded_store([row])
    assigned, _, survivors = intake(store, chunk, target_id=LIVE_ID)
    assert [s['text'] for s in survivors] == [LIVE[0]] and '_sync_lineage_repeat_only' not in assigned


def test_receipt_only_upload_appends_and_consolidates_an_overlapping_donor():
    row = live_row()
    texts = [reworded(text) for text in LIVE]
    chunk = wal(40, texts)
    prove(chunk, row)
    store = seeded_store_with_donor([row])
    assigned, created, survivors = intake(store, chunk, target_id=LIVE_ID)
    assert created is False and [s['text'] for s in survivors] == texts
    assert assigned['id'] == LIVE_ID and '_sync_lineage_repeat_only' not in assigned
    donor = store.rows[('users', 'u', 'conversations', 'DONOR-1')]
    assert donor['sync_merged_into'] == LIVE_ID and donor['deleted'] is True
    assert sorted(texts_of(store, LIVE_ID)) == sorted(LIVE + texts)


def test_receipt_only_append_past_an_oversized_donor_rolls_over_safely(monkeypatch, caplog):
    row = live_row()
    texts = [reworded(text) for text in LIVE]
    chunk = wal(40, texts)
    prove(chunk, row)
    store = seeded_store_with_donor([row])
    donor_stored = store.rows[('users', 'u', 'conversations', 'DONOR-1')]
    donor_stored['structured'] = {'title': '', 'overview': 'x' * 8192}
    donor_before = deepcopy(donor_stored)
    live_size = estimate_firestore_document_bytes(store.rows[('users', 'u', 'conversations', LIVE_ID)], None)
    monkeypatch.setattr(assignment, 'SYNC_CONVERSATION_BYTE_BUDGET', live_size + 64)
    with caplog.at_level(logging.WARNING):
        assigned, created, survivors = intake(store, chunk, target_id=LIVE_ID)
    assert created is True and [s['text'] for s in survivors] == texts
    assert assigned['id'] == chunk['id'] and '_sync_lineage_repeat_only' not in assigned
    assert store.rows[('users', 'u', 'conversations', 'DONOR-1')] == donor_before
    assert texts_of(store, LIVE_ID) == LIVE
    assert texts_of(store, chunk['id']) == texts


def test_donor_only_duplicate_text_is_appended_not_a_canonical_retry():
    store = seeded_store_with_donor([live_row()], donor=donor_chunk(texts=[NEW[0]]))
    chunk = wal_at(T0 + 50, [NEW[0]], 10.0)
    assigned, created, survivors = intake(store, chunk, target_id=LIVE_ID)
    assert created is False
    assert [s['text'] for s in survivors] == [NEW[0]]
    assert '_sync_lineage_repeat_only' not in assigned
    assert NEW[0] in texts_of(store, LIVE_ID)
    donor_stored = store.rows[('users', 'u', 'conversations', 'DONOR-1')]
    assert donor_stored['deleted'] is True and donor_stored['sync_merged_into'] == LIVE_ID


def test_new_speech_with_a_donor_consolidates_and_appends():
    row = live_row()
    chunk = wal(40, [reworded(text) for text in LIVE] + NEW)
    prove(chunk, row)
    store = seeded_store_with_donor([row])
    assigned, created, survivors = intake(store, chunk, target_id=LIVE_ID)
    assert created is False and len(survivors) == 10
    assert '_sync_lineage_repeat_only' not in assigned
    donor_stored = store.rows[('users', 'u', 'conversations', 'DONOR-1')]
    assert donor_stored['deleted'] is True and donor_stored['sync_merged_into'] == LIVE_ID
    assert set(texts_of(store, LIVE_ID)) >= set(NEW)


def test_negation_changes_keep_the_segment_at_intake():
    base = 'the quarterly planning review did not cover the budget numbers in detail'
    row = live_row()
    row['transcript_segments'][0]['text'] = base
    store = seeded_store([row])
    missing = wal_at(T0, [base.replace('did not', 'did')], 10.0)
    _, _, survivors = intake(store, missing, target_id=LIVE_ID)
    assert len(survivors) == 1
    store = seeded_store([row])
    contracted = wal_at(T0, [base.replace('did not', "didn't")], 10.0)
    _, _, survivors = intake(store, contracted, target_id=LIVE_ID)
    assert len(survivors) == 1


def test_changed_or_omitted_digit_tokens_keep_the_segment_at_intake():
    base = 'the quarterly planning review moved to room 204 for the budget talk'
    row = live_row()
    row['transcript_segments'][0]['text'] = base
    store = seeded_store([row])
    _, _, survivors = intake(store, wal_at(T0, [base.replace('204', '205')], 10.0), target_id=LIVE_ID)
    assert len(survivors) == 1
    store = seeded_store([row])
    _, _, survivors = intake(store, wal_at(T0, [base.replace('204 ', '')], 10.0), target_id=LIVE_ID)
    assert len(survivors) == 1


@pytest.fixture(scope='module')
def pipeline_module():
    from database import conversations  # noqa: F401
    from utils.sync import pipeline

    return pipeline


def _segments(texts):
    from models.transcript_segment import TranscriptSegment

    return [
        TranscriptSegment(
            text=text, start=i * 10.0 + 0.7, end=i * 10.0 + 10.7, speaker='SPEAKER_00', is_user=False, speaker_id=0
        )
        for i, text in enumerate(texts)
    ]


def _drive_process_segment(
    pipeline,
    monkeypatch,
    store,
    texts,
    *,
    target=LIVE_ID,
    response=None,
    finish_impl=None,
    wal_ts=T0 + 40,
    lineage_binding=None,
    prove=False,
    signed_url_impl=None,
    prerecorded_impl=None,
    turnstile=None,
    deferred_outcome=None,
    errors=None,
):
    from utils.conversations import lifecycle

    monkeypatch.setattr(pipeline, 'get_syncing_file_temporal_signed_url', signed_url_impl or (lambda _path: 'file://x'))
    monkeypatch.setattr(pipeline, 'schedule_syncing_temporal_file_deletion', lambda _path: None)
    monkeypatch.setattr(pipeline, 'get_prerecorded_service', lambda _lang: ('deepgram', 'cfg', 'nova-3'))
    monkeypatch.setattr(pipeline, 'prerecorded', prerecorded_impl or (lambda *args, **kwargs: (['w'], 'en')))
    monkeypatch.setattr(pipeline, 'postprocess_words', lambda *args, **kwargs: _segments(texts))
    monkeypatch.setattr(pipeline, 'get_timestamp_from_path', lambda _path: wal_ts)
    monkeypatch.setattr(pipeline, 'identify_speakers_for_segments', lambda *args, **kwargs: None)
    monkeypatch.setattr(pipeline.conversations_db, 'get_manual_speaker_receipt', lambda *args: {})
    monkeypatch.setattr(pipeline, 'capture_evidence_dark_write_enabled', lambda: False)
    if prove:

        def dark_write(incoming, _map, segments):
            incoming['capture_evidence'] = sync_evidence([str(segment.id) for segment in segments])

        monkeypatch.setattr(pipeline, 'apply_capture_evidence_dark_write', dark_write)
    monkeypatch.setattr(
        lifecycle,
        'ingest_sync_conversation',
        lambda uid, incoming, *, candidate_id=None, target_id=None: intake(
            store, incoming, candidate_id=candidate_id, target_id=target_id
        ),
    )
    finish = finish_impl or MagicMock()
    monkeypatch.setattr(pipeline, 'finish_sync_segment', finish)
    if response is None:
        response = {'new_memories': set(), 'updated_memories': set()}
    ok = pipeline.process_segment(
        '/tmp/wal.wav',
        'u',
        response,
        threading.Lock(),
        errors if errors is not None else [],
        target_conversation_id=target,
        turnstile=turnstile,
        client_device_id='pendant',
        deferred_outcome=deferred_outcome,
        lineage_binding=lineage_binding,
    )
    return ok, response, finish


def test_receipt_only_repeat_intake_writes_and_enrolls_enrichment(pipeline_module, monkeypatch, caplog):
    pipeline = pipeline_module
    store = seeded_store([live_row(capture_evidence=live_evidence())])
    texts = [reworded(text) for text in LIVE]
    with caplog.at_level(logging.INFO):
        ok, response, finish = _drive_process_segment(pipeline, monkeypatch, store, texts, prove=True)
    assert ok is True
    assert response['updated_memories'] == {LIVE_ID}
    assert response.get('_merged') == {LIVE_ID: 'en'}
    finish.assert_called_once()
    assert sorted(texts_of(store, LIVE_ID)) == sorted(LIVE + texts)
    lines = [r.getMessage() for r in caplog.records if 'event=sync_lineage_append' in r.getMessage()]
    assert len(lines) == 1 and len(lines[0]) <= 512
    assert 'repeat_only=False' in lines[0] and 'appended_seconds=70.00' in lines[0]
    for forbidden in (LIVE_ID, 'WAL-', 'u ', 'quarterly'):
        assert forbidden not in lines[0]


def test_receipt_only_append_preserves_existing_enrichment_debt(pipeline_module, monkeypatch):
    pipeline = pipeline_module
    store = seeded_store([live_row(capture_evidence=live_evidence())])
    texts = [reworded(text) for text in LIVE]
    response = {'new_memories': set(), 'updated_memories': set(), '_merged': {LIVE_ID: 'en'}}
    ok, response, _ = _drive_process_segment(pipeline, monkeypatch, store, texts, response=response, prove=True)
    assert ok is True
    assert response['_merged'] == {LIVE_ID: 'en'}
    assert response['updated_memories'] == {LIVE_ID}
    reprocess = MagicMock()
    monkeypatch.setattr(pipeline, '_reprocess_conversation_after_update', reprocess)
    pipeline._reprocess_merged_conversations('u', response)
    assert reprocess.call_count == 1
    assert reprocess.call_args.args[1] == LIVE_ID


def test_receipt_only_append_reprocesses_the_live_row(pipeline_module, monkeypatch):
    pipeline = pipeline_module
    store = seeded_store([live_row(capture_evidence=live_evidence())])
    texts = [reworded(text) for text in LIVE]
    ok, response, _ = _drive_process_segment(pipeline, monkeypatch, store, texts, prove=True)
    assert ok is True and response['_merged'] == {LIVE_ID: 'en'}
    reprocess = MagicMock()
    monkeypatch.setattr(pipeline, '_reprocess_conversation_after_update', reprocess)
    pipeline._reprocess_merged_conversations('u', response)
    assert reprocess.call_count == 1
    assert reprocess.call_args.args[1] == LIVE_ID


def test_new_speech_enrolls_and_finishes_normally(pipeline_module, monkeypatch, caplog):
    pipeline = pipeline_module
    store = seeded_store([live_row(capture_evidence=live_evidence())])
    texts = [reworded(text) for text in LIVE] + NEW
    with caplog.at_level(logging.INFO):
        ok, response, finish = _drive_process_segment(pipeline, monkeypatch, store, texts, prove=True)
    assert ok is True
    assert response['updated_memories'] == {LIVE_ID}
    assert response.get('_merged') == {LIVE_ID: 'en'}
    finish.assert_called_once()
    lines = [r.getMessage() for r in caplog.records if 'event=sync_lineage_append' in r.getMessage()]
    assert len(lines) == 1
    assert 'appended_seconds=100.00' in lines[0] and 'repeat_only=False' in lines[0]


def test_receipt_only_process_segment_stores_all_speech(pipeline_module, monkeypatch):
    """The saved transcript is the contract: receipt-only proof drops nothing."""
    pipeline = pipeline_module
    store = seeded_store([live_row(capture_evidence=live_evidence())])
    texts = [reworded(text) for text in LIVE] + NEW
    ok, _, _ = _drive_process_segment(pipeline, monkeypatch, store, texts, prove=True)
    assert sorted(texts_of(store, LIVE_ID)) == sorted(LIVE + texts)
    assert ok is True


def test_sync_scoped_retry_after_a_failed_finish_completes_the_existing_debt(pipeline_module, monkeypatch, caplog):
    """A commit whose finish fails is completed by the identical re-upload.

    The second attempt's sync-scoped segments match stored ranges and text
    exactly, so the intake writes nothing again but still enrolls the owed
    enrichment debt and invokes finish.
    """
    pipeline = pipeline_module
    store = seeded_store([live_row()])
    texts = [reworded(text) for text in LIVE] + NEW

    def boom(*args, **kwargs):
        raise RuntimeError('finish failed')

    ok = _drive_process_segment(pipeline, monkeypatch, store, texts, finish_impl=boom)[0]
    assert ok is False
    committed = deepcopy(store.rows)

    finish = MagicMock()
    with caplog.at_level(logging.INFO):
        ok, response, finish = _drive_process_segment(
            pipeline, monkeypatch, store, texts, response=None, finish_impl=finish
        )
    assert ok is True
    assert response['new_memories'] == set() and response['updated_memories'] == set()
    assert response.get('_merged') == {LIVE_ID: 'en'}
    finish.assert_called_once()
    assert store.rows == committed
    lines = [r.getMessage() for r in caplog.records if 'event=sync_lineage_append' in r.getMessage()]
    assert len(lines) == 1 and len(lines[0]) <= 512
    assert 'repeat_only=True' in lines[0] and 'existing_completion=True' in lines[0]
    for forbidden in (LIVE_ID, 'WAL-', 'quarterly'):
        assert forbidden not in lines[0]


@pytest.mark.parametrize('skew', [40, 1200])
def test_correction_prefixed_transcript_reaches_the_live_row(pipeline_module, monkeypatch, skew):
    pipeline = pipeline_module
    store = seeded_store([live_row()])
    corrected = 'Actually ' + LIVE[0]
    ok, response, finish = _drive_process_segment(pipeline, monkeypatch, store, [corrected], wal_ts=T0 + skew)
    assert ok is True
    row = store.rows[('users', 'u', 'conversations', LIVE_ID)]
    assert corrected in [segment['text'] for segment in row['transcript_segments']]
    assert response['updated_memories'] == {LIVE_ID}
    assert response.get('_merged') == {LIVE_ID: 'en'}
    finish.assert_called_once()


def test_receipt_only_repeats_on_a_pristine_live_row_finish_normally(pipeline_module, monkeypatch):
    pipeline = pipeline_module
    store = seeded_store([live_row(capture_evidence=live_evidence())])
    texts = [reworded(text) for text in LIVE]
    finish = MagicMock()
    ok, response, _ = _drive_process_segment(pipeline, monkeypatch, store, texts, finish_impl=finish, prove=True)
    assert ok is True
    assert response.get('_merged') == {LIVE_ID: 'en'}
    finish.assert_called_once()


def test_receipt_only_repeat_on_a_row_with_merged_ancestry_finishes_normally(pipeline_module, monkeypatch):
    pipeline = pipeline_module
    store = seeded_store([live_row(sync_merged_from=['DONOR-1'], capture_evidence=live_evidence())])
    texts = [reworded(text) for text in LIVE]
    finish = MagicMock()
    ok, response, finish = _drive_process_segment(pipeline, monkeypatch, store, texts, finish_impl=finish, prove=True)
    assert ok is True
    assert response.get('_merged') == {LIVE_ID: 'en'}
    finish.assert_called_once()
    assert sorted(texts_of(store, LIVE_ID)) == sorted(LIVE + texts)


def test_receipt_only_append_with_a_donor_finishes_and_reprocesses(pipeline_module, monkeypatch):
    pipeline = pipeline_module
    store = seeded_store_with_donor([live_row(capture_evidence=live_evidence())])
    texts = [reworded(text) for text in LIVE]
    finish = MagicMock()
    ok, response, finish = _drive_process_segment(pipeline, monkeypatch, store, texts, finish_impl=finish, prove=True)
    assert ok is True
    assert response.get('_merged') == {LIVE_ID: 'en'}
    finish.assert_called_once()
    donor = store.rows[('users', 'u', 'conversations', 'DONOR-1')]
    assert donor['sync_merged_into'] == LIVE_ID and donor['deleted'] is True
    assert sorted(texts_of(store, LIVE_ID)) == sorted(LIVE + texts)
    reprocess = MagicMock()
    monkeypatch.setattr(pipeline, '_reprocess_conversation_after_update', reprocess)
    pipeline._reprocess_merged_conversations('u', response)
    assert reprocess.call_count == 1
    assert reprocess.call_args.args[1] == LIVE_ID


def test_committed_append_logs_telemetry_before_a_failing_finish(pipeline_module, monkeypatch, caplog):
    pipeline = pipeline_module
    store = seeded_store([live_row(capture_evidence=live_evidence())])
    texts = [reworded(text) for text in LIVE] + NEW

    def boom(*args, **kwargs):
        raise RuntimeError('finish failed')

    with caplog.at_level(logging.INFO):
        ok = _drive_process_segment(pipeline, monkeypatch, store, texts, finish_impl=boom, prove=True)[0]
    assert ok is False
    lines = [r.getMessage() for r in caplog.records if 'event=sync_lineage_append' in r.getMessage()]
    assert len(lines) == 1 and len(lines[0]) <= 512
    assert 'appended_seconds=100.00' in lines[0] and 'repeat_only=False' in lines[0]
    for forbidden in (LIVE_ID, 'WAL-', 'quarterly'):
        assert forbidden not in lines[0]


def test_ambiguous_pending_defers_before_stt_and_a_bound_retry_lands(pipeline_module, monkeypatch):
    """An undecidable generation overlap defers the segment instead of guessing a row."""
    pipeline = pipeline_module
    store = seeded_store([live_row(capture_evidence=live_evidence())])
    before = deepcopy(store.rows)
    response = {'new_memories': set(), 'updated_memories': set()}
    errors, deferred = [], {}
    signed_url, prerecorded_call, turnstile = MagicMock(), MagicMock(), MagicMock()
    ok, response, finish = _drive_process_segment(
        pipeline,
        monkeypatch,
        store,
        NEW,
        response=response,
        errors=errors,
        deferred_outcome=deferred,
        signed_url_impl=signed_url,
        prerecorded_impl=prerecorded_call,
        turnstile=turnstile,
        lineage_binding='ambiguous_pending',
    )
    assert ok is False and errors == ['sync_persistence_failed']
    assert deferred['retryable'] is True
    signed_url.assert_not_called()
    prerecorded_call.assert_not_called()
    turnstile.complete.assert_called_once_with('/tmp/wal.wav')
    finish.assert_not_called()
    assert store.rows == before
    assert response == {'new_memories': set(), 'updated_memories': set()}
    ok, response, finish = _drive_process_segment(
        pipeline, monkeypatch, store, NEW, response=response, lineage_binding='bound', prove=True
    )
    assert ok is True
    assert len(conversations(store)) == 1
    assert set(texts_of(store, LIVE_ID)) >= set(NEW)


def test_pending_plan_output_defers_through_real_process_segment(pipeline_module, monkeypatch):
    pipeline = pipeline_module
    rows = [
        live_row(id='GEN-A', finished_at=at(T0 + 120)),
        live_row(
            id='GEN-B',
            started_at=at(T0 + 60),
            finished_at=at(T0 + 180),
            external_data={'recording_session_id': 'S-B', 'recording_origin_id': ORIGIN},
        ),
    ]
    store = seeded_store(rows)
    before = deepcopy(store.rows)
    segment_plan = select_segment_targets(
        rows,
        ORIGIN,
        {'wal': (T0 + 80, T0 + 90)},
        stamped_target='STAMP',
        source='omi',
        client_device_id='pendant',
        is_locked=False,
    )
    signed_url, prerecorded_call = MagicMock(), MagicMock()
    ok, _, finish = _drive_process_segment(
        pipeline,
        monkeypatch,
        store,
        NEW,
        target=segment_plan.targets['wal'],
        lineage_binding=segment_plan.binding_reasons['wal'],
        signed_url_impl=signed_url,
        prerecorded_impl=prerecorded_call,
    )
    assert ok is False
    signed_url.assert_not_called()
    prerecorded_call.assert_not_called()
    finish.assert_not_called()
    assert store.rows == before


@pytest.mark.parametrize('stamp', [None, 'UNRELATED'])
def test_tolerant_pending_plan_output_defers_through_real_process_segment(pipeline_module, monkeypatch, stamp):
    """A straddling segment that only tolerantly overlaps two generations defers whole."""
    pipeline = pipeline_module
    rows = [
        live_row(id='GEN-A', started_at=at(43200), finished_at=at(44400)),
        live_row(id='GEN-B', started_at=at(44403), finished_at=at(45000)),
    ]
    store = seeded_store(rows)
    before = deepcopy(store.rows)
    segment_plan = select_segment_targets(
        rows,
        ORIGIN,
        {'wal': (44399, 44410)},
        stamped_target=stamp,
        source='omi',
        client_device_id='pendant',
        is_locked=False,
    )
    assert segment_plan.targets == {'wal': None}
    assert segment_plan.binding_reasons == {'wal': 'ambiguous_pending'}
    errors, deferred = [], {}
    response = {'new_memories': set(), 'updated_memories': set()}
    signed_url, prerecorded_call, turnstile = MagicMock(), MagicMock(), MagicMock()
    ok, response, finish = _drive_process_segment(
        pipeline,
        monkeypatch,
        store,
        NEW,
        target=segment_plan.targets['wal'],
        lineage_binding=segment_plan.binding_reasons['wal'],
        response=response,
        errors=errors,
        deferred_outcome=deferred,
        signed_url_impl=signed_url,
        prerecorded_impl=prerecorded_call,
        turnstile=turnstile,
    )
    assert ok is False and errors == ['sync_persistence_failed']
    assert deferred['retryable'] is True
    signed_url.assert_not_called()
    prerecorded_call.assert_not_called()
    turnstile.complete.assert_called_once_with('/tmp/wal.wav')
    finish.assert_not_called()
    assert store.rows == before
    assert response == {'new_memories': set(), 'updated_memories': set()}


def test_pending_token_is_inert_when_safe_overlap_is_off(pipeline_module, monkeypatch):
    monkeypatch.setenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, 'off')
    pipeline = pipeline_module
    store = seeded_store([live_row()])
    ok, _, finish = _drive_process_segment(pipeline, monkeypatch, store, NEW, lineage_binding='ambiguous_pending')
    assert ok is True
    finish.assert_called_once()


def test_flag_off_logs_nothing_and_enrolls_normally(pipeline_module, monkeypatch, caplog):
    monkeypatch.setenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, 'off')
    pipeline = pipeline_module
    store = seeded_store([live_row()])
    texts = [reworded(text) for text in LIVE]
    with caplog.at_level(logging.INFO):
        ok, response, finish = _drive_process_segment(pipeline, monkeypatch, store, texts)
    assert ok is True
    assert response['updated_memories'] == {LIVE_ID}
    finish.assert_called_once()
    assert not any('sync_lineage_append' in r.getMessage() for r in caplog.records)


_BASELINE_FIXTURE = Path(__file__).parent / 'fixtures' / 'sync_lineage_dedupe_baseline.json'


def _baseline_cases():
    expected = json.loads(_BASELINE_FIXTURE.read_text())
    return {
        'mixed40': (live_row(), wal(40, [reworded(text) for text in LIVE] + NEW)),
        'mixed1200': (live_row(), wal(1200, [reworded(text) for text in LIVE] + NEW)),
        'all_reworded': (live_row(), wal(40, [reworded(text) for text in LIVE])),
        'short_retry': (short_text_row(), wal_at(T0, ['okay see you'], 3.0)),
    }, expected


def _snapshot(store, assigned, created, survivors):
    row = store.rows[('users', 'u', 'conversations', LIVE_ID)]
    return {
        'created': created,
        'survivor_texts': [segment['text'] for segment in survivors],
        'survivor_starts': [round(segment['start'], 4) for segment in survivors],
        'assigned_marker_keys': sorted(key for key in assigned if key.startswith('_sync_lineage')),
        'row_texts': [segment['text'] for segment in row['transcript_segments']],
        'row_speakers': [segment.get('speaker_id') for segment in row['transcript_segments']],
        'revision': row.get('sync_content_revision'),
    }


@pytest.mark.parametrize('gate', ['off', 'disabled-typo', 'nonallowlisted'])
def test_flag_off_parity_with_the_pre_dedupe_baseline(monkeypatch, gate):
    cases, expected = _baseline_cases()
    if gate == 'nonallowlisted':
        monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST_ENV, 'other-uid')
    else:
        monkeypatch.setenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, gate)
    for name, (row, chunk) in cases.items():
        store = seeded_store([row])
        assigned, created, survivors = intake(store, chunk, target_id=LIVE_ID)
        assert _snapshot(store, assigned, created, survivors) == expected[name], name


def test_config_parser_unset_blank_and_on_tokens(monkeypatch):
    from config.sync_live_dedupe import sync_live_dedupe_enabled

    for value in (None, '', '   ', '1', 'true', 'on', 'yes', 'enabled', 'TRUE', ' On '):
        if value is None:
            monkeypatch.delenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, raising=False)
        else:
            monkeypatch.setenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, value)
        assert sync_live_dedupe_enabled() is True, repr(value)
    for value in ('0', 'false', 'off', 'disabled', 'treu', '1x', 'enabledd', 'offf'):
        monkeypatch.setenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, value)
        assert sync_live_dedupe_enabled() is False, repr(value)


def test_config_parser_active_for_requires_the_allowlist(monkeypatch):
    from config.sync_live_dedupe import sync_live_dedupe_active_for

    monkeypatch.delenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, raising=False)
    monkeypatch.delenv(sync_lineage.SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST_ENV, raising=False)
    assert sync_live_dedupe_active_for('u') is True
    monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST_ENV, 'other-uid')
    assert sync_live_dedupe_active_for('u') is False


def test_receipt_only_evidence_never_proves_and_enrichment_is_not_skipped(pipeline_module, monkeypatch):
    """Valid receipt-only envelopes yield no capture proof: matching and reworded
    speech appends through intake and the live row's enrichment still enrolls."""
    row = live_row()
    texts = [reworded(text) for text in LIVE]
    chunk = wal(40, texts)
    prove(chunk, row)
    assert (
        capture_covered_indices(chunk['transcript_segments'], chunk['capture_evidence'], row['capture_evidence'])
        == frozenset()
    )
    store = seeded_store([row])
    assigned, created, survivors = intake(store, chunk, target_id=LIVE_ID)
    assert created is False and [s['text'] for s in survivors] == texts
    assert '_sync_lineage_repeat_only' not in assigned
    assert sorted(texts_of(store, LIVE_ID)) == sorted(LIVE + texts)

    pipeline = pipeline_module
    store = seeded_store([live_row(capture_evidence=live_evidence())])
    ok, response, finish = _drive_process_segment(pipeline, monkeypatch, store, texts, prove=True)
    assert ok is True
    assert response['updated_memories'] == {LIVE_ID}
    assert response.get('_merged') == {LIVE_ID: 'en'}
    finish.assert_called_once()
    assert sorted(texts_of(store, LIVE_ID)) == sorted(LIVE + texts)
