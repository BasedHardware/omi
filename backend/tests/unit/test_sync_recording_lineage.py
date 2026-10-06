"""Safety-WAL uploads bind per segment to the live recording's rollover generations.

Synthetic replay of the live+sync duplicate: one phone recording (origin id
``REC-ORIGIN``) becomes one live row per silence rollover, while every WAL
carries the origin id. A batch stamped for generation L starts before L and
runs past its end; an unstamped batch straddles the next two generations. The
whole-batch resolver (kill switch off, today's behavior) finds only the first
generation, drops the stamp and creates a sync row. Per-segment lineage binding
appends every segment to the live row that owns its audio. All ids are
synthetic.
"""

import logging
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import tests.unit.test_listen_reconnect_continuity as continuity
import tests.unit.test_sync_v2 as sync_v2_harness
from config import sync_lineage
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_sync_cross_job_assignment import conversations, intake
from utils.sync import recording_lineage, recording_session_target
from utils.sync.assignment_errors import SyncAssignmentSuperseded
from utils.sync.recording_lineage import (
    lineage_resolution_requested,
    resolve_segment_targets,
    select_segment_targets,
)

ORIGIN = 'REC-ORIGIN'
T0 = 1_760_000_000
PERIOD = 360  # one rollover generation every six minutes
DURATION = 232  # live speech, then more than two minutes of silence
GENERATIONS = 50
L = 11  # the generation the phone stamped


@pytest.fixture(scope='module', autouse=True)
def dependencies():
    from database import conversations  # noqa: F401
    from utils.sync import pipeline

    return pipeline


@pytest.fixture(autouse=True)
def default_flag(monkeypatch):
    monkeypatch.delenv(sync_lineage.SYNC_LINEAGE_RESOLVE_ENV, raising=False)
    monkeypatch.delenv(sync_lineage.SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST_ENV, raising=False)


def at(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc)


def gen_id(k):
    return ORIGIN if k == 0 else f'LIVE-{k:02d}'


def gen_start(k):
    return T0 + PERIOD * k


def live_text(k, i):
    return f'live generation {k} line {i} about the quarterly planning review'


def generation(k, **extra):
    start = gen_start(k)
    row = {
        'id': gen_id(k),
        'started_at': at(start),
        'finished_at': at(start + DURATION),
        'source': 'omi',
        'client_device_id': 'pendant',
        'is_locked': False,
        'discarded': False,
        'status': 'completed',
        'external_data': {
            'recording_session_id': ORIGIN if k == 0 else f'SESSION-{k:02d}',
            'recording_origin_id': ORIGIN,
        },
        'transcript_segments': [
            {'start': 60.0 * i + 1, 'end': 60.0 * i + 9, 'text': live_text(k, i), 'speaker_id': 0, 'is_user': False}
            for i in range(4)
        ],
    }
    row.update(extra)
    return row


def sync_chunk(start, end, text):
    return {
        'id': f'SYNC-{start}',
        'started_at': at(start),
        'finished_at': at(end),
        'source': 'omi',
        'client_device_id': 'pendant',
        'discarded': False,
        'status': 'completed',
        'transcript_segments': [{'start': 0.0, 'end': end - start, 'text': text, 'speaker_id': 0, 'is_user': False}],
    }


def upload_stamped_for_l():
    """Six WAL-minutes stamped for L, 1 s phone clock skew: speech inside L, then after it ended."""
    s = gen_start(L) + 1
    return [
        sync_chunk(s + 1, s + 9, live_text(L, 0)),
        sync_chunk(s + 61, s + 69, live_text(L, 1)),
        sync_chunk(s + 121, s + 129, live_text(L, 2)),
        sync_chunk(s + 181, s + 189, live_text(L, 3)),
        sync_chunk(s + 236, s + 250, 'speech the live socket never received after the last line'),
        sync_chunk(s + 300, s + 340, 'a later remark in the silence before the next generation'),
    ]


def upload_straddling_next_two():
    """Unstamped five WAL-minutes that straddle generations L+1 and L+2."""
    s1, s2 = gen_start(L + 1) + 1, gen_start(L + 2) + 1
    return [
        sync_chunk(s1 + 121, s1 + 129, live_text(L + 1, 2)),
        sync_chunk(s1 + 181, s1 + 189, live_text(L + 1, 3)),
        sync_chunk(s2 + 1, s2 + 9, live_text(L + 2, 0)),
        sync_chunk(s2 + 61, s2 + 69, live_text(L + 2, 1)),
    ]


def spans(chunks):
    return {chunk['id']: (chunk['started_at'].timestamp(), chunk['finished_at'].timestamp()) for chunk in chunks}


def seeded_store(rows=None):
    store = StrictFirestore()
    for row in rows if rows is not None else [generation(k) for k in range(GENERATIONS)]:
        store.rows[('users', 'u', 'conversations', row['id'])] = deepcopy(row)
    return store


def lineage(store):
    return [deepcopy(row) for row in conversations(store) + deleted_rows(store) if row.get('external_data')]


def deleted_rows(store):
    return [value for key, value in store.rows.items() if key[2] == 'conversations' and value.get('deleted')]


def plan(store, chunks, stamp=None, **kwargs):
    return select_segment_targets(
        lineage(store),
        ORIGIN,
        spans(chunks),
        stamped_target=stamp,
        source='omi',
        client_device_id='pendant',
        is_locked=False,
        **kwargs,
    )


def replay(store, chunks, targets):
    return [intake(store, chunk, target_id=targets[chunk['id']]) for chunk in chunks]


def texts(store, cid):
    return [segment['text'] for segment in store.rows[('users', 'u', 'conversations', cid)]['transcript_segments']]


PROOF_ROOT = 'a1b2c3d4-1111-4222-8333-444455556666'
PROOF_FRAMES = 500000
PROOF_SPF = 160


def prove(chunk, store, row_id):
    """Pair sync_vad receipts for the chunk with live runs on its target row.

    The new dedupe drops only with independent source-frame capture proof, so
    replays that intentionally exercise suppression furnish the paired evidence
    explicitly; unproven wording is kept as legitimate repetition.
    """
    for i, segment in enumerate(chunk['transcript_segments']):
        segment.setdefault('id', f"{chunk['id']}-seg-{i}")
    chunk['capture_evidence'] = {
        'version': 1,
        'capability': 'source_position',
        'coverage': 'mapped',
        'origin': 'sync_vad',
        'receipts': [
            {
                'segment_id': segment['id'],
                'capture_root': PROOF_ROOT,
                'clock_epoch': 7,
                'channel': 'mono',
                'source_start_frame': i * 1000,
                'source_start_offset': 0,
                'source_end_frame': i * 1000 + 999,
                'source_end_offset': 0,
                'rate_hz': 16000,
                'producer_revision': 'sync_vad_stt_v1',
            }
            for i, segment in enumerate(chunk['transcript_segments'])
        ],
    }
    store.rows[('users', 'u', 'conversations', row_id)]['capture_evidence'] = {
        'version': 1,
        'capability': 'source_position',
        'coverage': 'mapped',
        'origin': 'live',
        'conflicts': 0,
        'runs': [
            {
                'capture_root': PROOF_ROOT,
                'clock_epoch': 7,
                'rate_hz': 16000,
                'channel': 'mono',
                'source_frame_start': 0,
                'source_frame_end': PROOF_FRAMES,
                'decoded_sample_start': 0,
                'decoded_sample_end': PROOF_FRAMES * PROOF_SPF,
                'samples_per_frame': PROOF_SPF,
            }
        ],
    }


def replay_proven(store, chunks, targets):
    for chunk in chunks:
        prove(chunk, store, targets[chunk['id']])
    return replay(store, chunks, targets)


# --- Synthetic replay -------------------------------------------------------


def test_stamped_batch_straddling_generation_lands_on_its_live_row():
    store = seeded_store()
    before = {row['id'] for row in conversations(store)}
    chunks = upload_stamped_for_l()
    result = plan(store, chunks, stamp=gen_id(L))
    assert result.outcome == 'bound'
    # Speech that starts after L's last word never overlaps L, so it keeps the stamp.
    assert result.counts == {'bound': 4, 'stamp_overridden': 0, 'stamp_fallback': 2, 'unbound': 0}
    assert set(result.targets.values()) == {gen_id(L)}
    replay(store, chunks, result.targets)
    assert {row['id'] for row in conversations(store)} == before  # no sync row for live audio
    assert 'speech the live socket never received after the last line' in texts(store, gen_id(L))


def test_unstamped_batch_is_split_across_the_generations_that_own_its_audio():
    store = seeded_store()
    before = {row['id'] for row in conversations(store)}
    chunks = upload_straddling_next_two()
    result = plan(store, chunks)
    assert result.outcome == 'split_across_generations'
    assert [result.targets[chunk['id']] for chunk in chunks] == [gen_id(L + 1)] * 2 + [gen_id(L + 2)] * 2
    replay(store, chunks, result.targets)
    assert {row['id'] for row in conversations(store)} == before


def test_receipt_only_replay_appends_wording_matched_speech_to_live_rows():
    store = seeded_store()
    before = {row['id'] for row in conversations(store)}
    stamped, unstamped = upload_stamped_for_l(), upload_straddling_next_two()
    for chunks, stamp in ((stamped, gen_id(L)), (unstamped, None)):
        targets = plan(store, chunks, stamp=stamp).targets
        replay_proven(store, chunks, targets)
    assert {row['id'] for row in conversations(store)} == before
    expected = {
        gen_id(L): [live_text(L, i) for i in range(4)] + [c['transcript_segments'][0]['text'] for c in stamped],
        gen_id(L + 1): [live_text(L + 1, i) for i in range(4)]
        + [c['transcript_segments'][0]['text'] for c in unstamped[:2]],
        gen_id(L + 2): [live_text(L + 2, i) for i in range(4)]
        + [c['transcript_segments'][0]['text'] for c in unstamped[2:]],
    }
    for cid, want in expected.items():
        assert sorted(texts(store, cid)) == sorted(want)


def test_residual_differently_worded_overlap_still_repeats_on_the_live_row(monkeypatch):
    """Known residual: off the exact live timestamps, dedupe needs identical normalized text."""
    monkeypatch.setenv('SYNC_LINEAGE_LIVE_DEDUPE_ENABLED', 'off')
    store = seeded_store()
    s = gen_start(L) + 1  # one second of phone clock skew
    chunks = [
        sync_chunk(s + 1, s + 9, 'Live generation 11, line 0: about the quarterly planning review!'),
        sync_chunk(s + 61, s + 69, 'live generation eleven line one about quarterly planning reviews'),
    ]
    replay(store, chunks, plan(store, chunks, stamp=gen_id(L)).targets)
    assert len(texts(store, gen_id(L))) == 4 + 2  # both reworded repeats survive the text dedupe
    from utils.conversations.duration import conversation_duration_seconds
    from utils.conversations.meeting_treatment import deduplicated_transcribed_speech_seconds

    row = store.rows[('users', 'u', 'conversations', gen_id(L))]
    assert conversation_duration_seconds(row) == 189  # max end, not summed speech
    assert deduplicated_transcribed_speech_seconds(row['transcript_segments']) == 34  # originally 32; skew adds 2


def test_receipt_only_retry_binds_the_same_rows_and_reappends_its_speech():
    store = seeded_store()
    uploads = ((upload_stamped_for_l(), gen_id(L)), (upload_straddling_next_two(), None))
    first = [plan(store, chunks, stamp=stamp).targets for chunks, stamp in uploads]
    for (chunks, _), targets in zip(uploads, first):
        replay_proven(store, chunks, targets)
    before = {row['id'] for row in conversations(store)}
    again = [plan(store, chunks, stamp=stamp).targets for chunks, stamp in uploads]
    assert again == first
    for (chunks, _), targets in zip(uploads, again):
        for chunk, (_, created, survivors) in zip(chunks, replay_proven(store, chunks, targets)):
            assert not created and [s['text'] for s in survivors] == [s['text'] for s in chunk['transcript_segments']]
    assert {row['id'] for row in conversations(store)} == before


def test_exact_sync_scoped_retry_binds_the_same_rows_and_appends_nothing_new():
    store = seeded_store()
    uploads = ((upload_stamped_for_l(), gen_id(L)), (upload_straddling_next_two(), None))
    for chunks, _ in uploads:
        for chunk in chunks:
            for i, segment in enumerate(chunk['transcript_segments']):
                segment['id'] = f"{chunk['id']}-seg-{i}"
                segment['speaker_id_scope'] = f"sync:{chunk['id']}"
    first = [plan(store, chunks, stamp=stamp).targets for chunks, stamp in uploads]
    for (chunks, _), targets in zip(uploads, first):
        replay(store, chunks, targets)
    snapshot = deepcopy(store.rows)
    again = [plan(store, chunks, stamp=stamp).targets for chunks, stamp in uploads]
    assert again == first
    for (chunks, _), targets in zip(uploads, again):
        for _, created, survivors in replay(store, chunks, targets):
            assert not created and not survivors
    conversation_rows = lambda rows: {k: v for k, v in rows.items() if k[2] == 'conversations'}  # noqa: E731
    assert {k: v['transcript_segments'] for k, v in conversation_rows(store.rows).items()} == {
        k: v['transcript_segments'] for k, v in conversation_rows(snapshot).items()
    }


@pytest.mark.parametrize('flag', ['', 'off'])
def test_early_sync_append_preserves_a_pinned_live_clock(monkeypatch, flag):
    monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_ENV, flag)
    store = seeded_store([generation(L, audio_timeline={'version': 2})])
    origin = gen_start(L)
    chunk = sync_chunk(origin - 1, origin + 9, 'Synthetic buffered speech before live connected.')
    result, _, _ = intake(store, chunk, target_id=gen_id(L))
    # The live host continues to emit offsets against the pinned origin.
    # Moving it on sync intake shifts every later live line by one second.
    assert result['started_at'] == at(origin if flag == '' else origin - 1)
    live = next(s for s in result['transcript_segments'] if s['text'] == live_text(L, 0))
    assert result['started_at'].timestamp() + live['start'] == origin + 1
    incoming = next(s for s in result['transcript_segments'] if s['text'] == chunk['transcript_segments'][0]['text'])
    assert result['started_at'].timestamp() + incoming['start'] == origin - 1
    if flag == '':
        assert incoming['audio_alignment'] == 'unplaced'
    from database import conversations as db

    written = db.update_conversation_segments(
        'u',
        gen_id(L),
        [],
        firestore_client=store,
        live_segments=[
            {
                'id': 'LIVE-FRESH',
                'start': 20.0,
                'end': 21.0,
                'text': 'Synthetic later live speech.',
                'speaker': 'SPEAKER_04',
                'speaker_id': 4,
                'is_user': False,
            }
        ],
    )
    fresh = next(s for s in written.segments if s.get('id') == 'LIVE-FRESH')
    assert result['started_at'].timestamp() + fresh['start'] == origin + (20 if flag == '' else 19)


@pytest.mark.asyncio
async def test_kill_switch_off_reproduces_the_whole_batch_outcome(monkeypatch, dependencies):
    """Today's behavior: only the origin-id row is a candidate, so the batch loses its stamp."""
    pipeline = dependencies
    monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_ENV, 'off')
    store = seeded_store()
    candidates = [row for row in lineage(store) if row['external_data']['recording_session_id'] == ORIGIN]
    monkeypatch.setattr(recording_session_target, '_candidate_rows', lambda *_args, **_kwargs: candidates)

    async def run_inline(_executor, fn, *args):
        return fn(*args)

    monkeypatch.setattr(pipeline, 'run_blocking', run_inline)
    chunks = upload_stamped_for_l()
    start, end = chunks[0]['started_at'].timestamp() - 1, chunks[-1]['finished_at'].timestamp()
    assert not lineage_resolution_requested('u', ORIGIN, start, end)
    target = await pipeline._resolve_safety_wal_target(
        'u', gen_id(L), ORIGIN, pipeline.ConversationSource.omi, 'pendant', False, start, end
    )
    assert target is None
    before = {row['id'] for row in conversations(store)}
    replay(store, chunks, {chunk['id']: target for chunk in chunks})
    assert {row['id'] for row in conversations(store)} - before == {chunks[0]['id']}


def test_upload_without_recording_id_keeps_temporal_assignment():
    assert not lineage_resolution_requested('u', None, 1.0, 2.0)
    store = seeded_store()
    s = gen_start(L + 3)
    chunk = sync_chunk(s + 61, s + 69, 'an old client upload without recording proof')
    _, created, _ = intake(store, chunk)
    assert created  # temporal intake never adopts a live row, exactly as before


# --- Fallback and override --------------------------------------------------


def test_unique_generation_overrides_a_stale_stamp():
    store = seeded_store()
    chunks = upload_straddling_next_two()[:2]
    result = plan(store, chunks, stamp=gen_id(L))
    assert result.outcome == 'stamp_overridden'
    assert set(result.targets.values()) == {gen_id(L + 1)}


@pytest.mark.parametrize(
    ('rows', 'reason'),
    [([], 'no_rows'), ([generation(L)], 'interval_miss')],
)
def test_no_unique_generation_falls_back_to_the_stamp_or_stays_unbound(rows, reason):
    chunks = upload_straddling_next_two()
    stamped = select_segment_targets(
        rows, ORIGIN, spans(chunks), stamped_target='STAMP', source='omi', client_device_id='pendant', is_locked=False
    )
    assert stamped.outcome == 'stamp_fallback' and stamped.reason == reason
    assert set(stamped.targets.values()) == {'STAMP'}
    unstamped = select_segment_targets(
        rows, ORIGIN, spans(chunks), stamped_target=None, source='omi', client_device_id='pendant', is_locked=False
    )
    assert unstamped.outcome == reason and set(unstamped.targets.values()) == {None}


def test_adjacent_generations_inside_the_edge_allowance_are_ambiguous():
    end = gen_start(1) + DURATION
    rows = [generation(1), generation(2, started_at=at(end + 3))]
    chunk = sync_chunk(end - 1, end + 10, 'straddles the rollover')
    result = select_segment_targets(
        rows, ORIGIN, spans([chunk]), stamped_target=None, source='omi', client_device_id='pendant', is_locked=False
    )
    assert result.targets == {chunk['id']: None}
    assert result.binding_reasons == {chunk['id']: 'ambiguous_pending'} and result.reason == 'ambiguous_overlap'


def test_trailing_allowance_does_not_exceed_sixty_seconds():
    end = gen_start(L) + DURATION
    chunk = sync_chunk(end - 1, end + 61, 'Synthetic speech across the trailing limit.')
    result = select_segment_targets(
        [generation(L)],
        ORIGIN,
        spans([chunk]),
        stamped_target=None,
        source='omi',
        client_device_id='pendant',
        is_locked=False,
    )
    assert result.targets == {chunk['id']: None}


def test_overlapping_generations_bind_the_stamped_row_or_stay_pending():
    """A row whose interval grew over its successor (e.g. an earlier stamp append) overlaps it."""
    rows = [generation(1, finished_at=at(gen_start(2) + DURATION)), generation(2)]
    chunk = sync_chunk(gen_start(2) + 61, gen_start(2) + 69, live_text(2, 1))
    stamped = select_segment_targets(
        rows,
        ORIGIN,
        spans([chunk]),
        stamped_target=gen_id(2),
        source='omi',
        client_device_id='pendant',
        is_locked=False,
    )
    assert stamped.targets == {chunk['id']: gen_id(2)} and stamped.counts['bound'] == 1
    for stamp in (None, 'STAMP'):
        pending = select_segment_targets(
            rows,
            ORIGIN,
            spans([chunk]),
            stamped_target=stamp,
            source='omi',
            client_device_id='pendant',
            is_locked=False,
        )
        assert pending.targets == {chunk['id']: None}
        assert pending.binding_reasons == {chunk['id']: 'ambiguous_pending'}
        assert pending.reason == 'ambiguous_overlap' and pending.outcome == 'interval_miss'


@pytest.mark.parametrize(
    'mutation',
    [
        {'client_device_id': 'other-phone'},
        {'source': 'phone'},
        {'is_locked': True},
        {'external_data': {'recording_session_id': 'SESSION-X', 'recording_origin_id': 'OTHER-ORIGIN'}},
    ],
)
def test_other_partitions_and_recordings_never_bind(mutation):
    chunks = upload_straddling_next_two()[:1]
    result = select_segment_targets(
        [generation(L + 1, **mutation)],
        ORIGIN,
        spans(chunks),
        stamped_target=None,
        source='omi',
        client_device_id='pendant',
        is_locked=False,
    )
    assert result.targets == {chunks[0]['id']: None}


def test_generation_created_before_the_origin_stamp_binds_through_the_origin_row():
    legacy = generation(0, external_data={'recording_session_id': ORIGIN})
    chunk = sync_chunk(gen_start(0) + 61, gen_start(0) + 69, live_text(0, 1))
    result = select_segment_targets(
        [legacy], ORIGIN, spans([chunk]), stamped_target=None, source='omi', client_device_id='pendant', is_locked=False
    )
    assert result.targets == {chunk['id']: ORIGIN}


# --- Tombstones and user-managed live rows ----------------------------------


def smart_merged(store, survivor_k, donor_k):
    survivor = store.rows[('users', 'u', 'conversations', gen_id(survivor_k))]
    donor = store.rows[('users', 'u', 'conversations', gen_id(donor_k))]
    survivor.update(
        finished_at=donor['finished_at'],
        sync_content_revision=1,
        smart_merge={'role': 'survivor'},
        transcript_segments=survivor['transcript_segments']
        + [
            dict(segment, start=segment['start'] + PERIOD * (donor_k - survivor_k))
            for segment in donor['transcript_segments']
        ],
    )
    donor.update(deleted=True, discarded=True, sync_merged_into=gen_id(survivor_k), smart_merge={'role': 'donor'})


def test_donor_generation_resolves_to_its_survivor():
    store = seeded_store()
    smart_merged(store, L + 1, L + 2)
    chunks = upload_straddling_next_two()
    result = plan(store, chunks)
    assert result.outcome == 'bound'  # both generations are one conversation now
    assert set(result.targets.values()) == {gen_id(L + 1)}
    before = {row['id'] for row in conversations(store)}
    replay(store, chunks, result.targets)
    assert {row['id'] for row in conversations(store)} == before


def test_donor_whose_survivor_is_outside_the_lineage_redirects_in_intake():
    store = seeded_store()
    smart_merged(store, L + 1, L + 2)
    survivor_key = ('users', 'u', 'conversations', gen_id(L + 1))
    store.rows[survivor_key]['external_data'] = {'recording_session_id': 'OTHER', 'recording_origin_id': 'OTHER'}
    s = gen_start(L + 2)
    chunks = [sync_chunk(s + 100, s + 110, 'late repair audio for the folded generation')]
    result = plan(store, chunks)
    assert set(result.targets.values()) == {gen_id(L + 2)}  # the donor; intake follows its redirect
    replay(store, chunks, result.targets)
    assert 'late repair audio for the folded generation' in texts(store, gen_id(L + 1))


def test_deleted_survivor_supersedes_the_audio_instead_of_recreating_a_row():
    store = seeded_store()
    smart_merged(store, L + 1, L + 2)
    del store.rows[('users', 'u', 'conversations', gen_id(L + 1))]
    chunks = upload_straddling_next_two()[2:]
    result = plan(store, chunks)
    assert set(result.targets.values()) == {gen_id(L + 2)}
    before = {row['id'] for row in conversations(store)}
    with pytest.raises(SyncAssignmentSuperseded):
        intake(store, chunks[0], target_id=result.targets[chunks[0]['id']])
    assert {row['id'] for row in conversations(store)} == before


@pytest.mark.parametrize(
    'managed',
    [{'starred': True}, {'user_title': 'Planning'}, {'has_photos': True}, {'visibility': 'shared'}],
)
def test_user_managed_live_generation_keeps_its_identity_and_markers(managed):
    store = seeded_store([generation(L + 1, **managed)])
    chunks = upload_straddling_next_two()[:2]
    replay(store, chunks, plan(store, chunks).targets)
    row = store.rows[('users', 'u', 'conversations', gen_id(L + 1))]
    assert {row['id'] for row in conversations(store)} == {gen_id(L + 1)}
    assert all(row[key] == value for key, value in managed.items())


# --- Lookup, truncation, fail-open, telemetry --------------------------------


class _LineageDb:
    """In-memory stand-in for database.sync_recording_lineage with the real query semantics."""

    def __init__(self, rows):
        self.rows = rows
        self.failing: set[str] = set()
        self.calls = []

    def get_recording_generations(
        self, uid, origin_id, *, started_before, limit, finished_after=None, firestore_client=None
    ):
        self.calls.append('generations')
        if 'generations' in self.failing:
            raise TimeoutError('index not serving')
        matching = [
            row
            for row in self.rows
            if (row.get('external_data') or {}).get('recording_origin_id') == origin_id
            and row['started_at'] <= started_before
            and (finished_after is None or row['finished_at'] >= finished_after)
        ]
        matching.sort(key=lambda row: (row['started_at'], row['id']), reverse=True)
        return deepcopy(matching[: limit + 1])

    def get_origin_generation(self, uid, origin_id, *, limit, firestore_client=None):
        self.calls.append('origin')
        if 'origin' in self.failing:
            raise TimeoutError('deadline')
        matching = [
            row for row in self.rows if (row.get('external_data') or {}).get('recording_session_id') == origin_id
        ]
        return deepcopy(matching[: limit + 1])

    def get_recording_id_probe(self, uid, origin_id, *, firestore_client=None):
        self.calls.append('probe')
        if 'probe' in self.failing:
            raise TimeoutError('probe deadline')
        for row in self.rows:
            if row.get('id') == origin_id:
                return deepcopy(row)
        return None


@pytest.fixture
def lineage_db(monkeypatch):
    from database import sync_recording_lineage

    fake = _LineageDb([generation(k) for k in range(GENERATIONS)])
    for name in ('get_recording_generations', 'get_origin_generation', 'get_recording_id_probe'):
        monkeypatch.setattr(sync_recording_lineage, name, getattr(fake, name))
    return fake


def resolve(chunks, stamp=None):
    return resolve_segment_targets(
        'u',
        ORIGIN,
        spans(chunks),
        stamped_target=stamp,
        source='omi',
        client_device_id='pendant',
        is_locked=False,
        job_id='00000000-0000-4000-8000-000000000000',
    )


def test_long_recording_reads_one_bounded_window(lineage_db):
    chunks = upload_straddling_next_two()
    targets = resolve(chunks)
    assert [targets[chunk['id']] for chunk in chunks] == [gen_id(L + 1)] * 2 + [gen_id(L + 2)] * 2
    assert lineage_db.calls == ['generations', 'origin']  # legacy origin can have a late append


def test_audio_older_than_the_read_window_is_not_guessed(lineage_db):
    old = sync_chunk(gen_start(2) + 61, gen_start(2) + 69, live_text(2, 1))
    new = upload_straddling_next_two()[0]
    targets = resolve([old, new], stamp='STAMP')
    assert targets == {old['id']: 'STAMP', new['id']: 'STAMP'}  # incomplete overlap set proves neither target


def test_old_stamp_extended_into_a_later_generation_is_not_hidden_by_the_limit(lineage_db):
    old = lineage_db.rows[0]
    old['finished_at'] = at(gen_start(L + 1) + DURATION)
    chunk = upload_straddling_next_two()[0]
    # The origin row and LIVE-12 both contain the segment. The original
    # newest-eight query hides the extended origin and falsely overrides STAMP.
    reasons = {}
    targets = resolve_segment_targets(
        'u',
        ORIGIN,
        spans([chunk]),
        stamped_target='STAMP',
        source='omi',
        client_device_id='pendant',
        is_locked=False,
        binding_reasons=reasons,
    )
    assert targets == {chunk['id']: None}
    assert reasons == {chunk['id']: 'ambiguous_pending'}


def test_unread_smart_survivor_can_overlap_without_a_donor_in_the_window(lineage_db):
    old = lineage_db.rows[0]
    old.update(finished_at=at(gen_start(L + 1) + DURATION), smart_merge={'role': 'survivor'})
    # Donors need not be recent: the survivor can also have a late stamped
    # append while unrelated newer generations of the same recording exist.
    chunk = upload_straddling_next_two()[0]
    reasons = {}
    targets = resolve_segment_targets(
        'u',
        ORIGIN,
        spans([chunk]),
        stamped_target=None,
        source='omi',
        client_device_id='pendant',
        is_locked=False,
        binding_reasons=reasons,
    )
    assert targets == {chunk['id']: None}
    assert reasons == {chunk['id']: 'ambiguous_pending'}


@pytest.mark.parametrize('duration', [0, -1, float('nan'), float('inf')])
def test_invalid_audio_span_cannot_prove_a_generation(duration):
    start = gen_start(L) + 61
    result = select_segment_targets(
        [generation(L)],
        ORIGIN,
        {'bad': (start, start + duration)},
        stamped_target='STAMP',
        source='omi',
        client_device_id='pendant',
        is_locked=False,
    )
    assert result.targets == {'bad': 'STAMP'}


def test_recording_from_before_the_origin_stamp_reads_the_origin_row(lineage_db):
    lineage_db.rows = [generation(0, external_data={'recording_session_id': ORIGIN}), generation(1, external_data={})]
    chunk = sync_chunk(gen_start(0) + 61, gen_start(0) + 69, live_text(0, 1))
    assert resolve([chunk]) == {chunk['id']: ORIGIN}
    assert lineage_db.calls == ['generations', 'origin']


def test_unbuilt_lineage_index_degrades_to_the_origin_row(lineage_db, monkeypatch, caplog):
    lineage_db.failing = {'generations'}
    fallback = MagicMock()
    monkeypatch.setattr(recording_lineage, 'record_fallback', fallback)
    first = sync_chunk(gen_start(0) + 62, gen_start(0) + 70, live_text(0, 1))
    later = upload_straddling_next_two()[0]
    with caplog.at_level(logging.INFO, logger=recording_lineage.__name__):
        assert resolve([first, later], stamp='STAMP') == {first['id']: ORIGIN, later['id']: 'STAMP'}
    assert fallback.call_args.kwargs['to_mode'] == 'origin_row'
    assert 'window=origin_row_only' in caplog.text


def test_lookup_failure_fails_open_to_the_stamp(lineage_db, monkeypatch, caplog):
    lineage_db.failing = {'generations', 'origin'}
    fallback = MagicMock()
    monkeypatch.setattr(recording_lineage, 'record_fallback', fallback)
    chunks = upload_straddling_next_two()
    with caplog.at_level(logging.INFO, logger=recording_lineage.__name__):
        assert set(resolve(chunks, stamp='STAMP').values()) == {'STAMP'}
        assert set(resolve(chunks).values()) == {None}
    assert fallback.call_count == 2
    assert 'event=sync_lineage_resolve outcome=lookup_failed' in caplog.text


def test_planning_error_fails_open_and_never_raises(lineage_db, monkeypatch):
    def boom(*_args, **_kwargs):
        raise KeyError('bad row')

    monkeypatch.setattr(recording_lineage, 'select_segment_targets', boom)
    chunks = upload_straddling_next_two()
    assert set(resolve(chunks, stamp='STAMP').values()) == {'STAMP'}


def _drive_plan(monkeypatch, resolve):
    calls = []

    def fake(uid, origin_id, spans, **kwargs):
        calls.append(dict(spans))
        reasons = kwargs.get('binding_reasons')
        if reasons is not None:
            reasons.update(resolve(len(calls), spans))
        return {key: ('LIVE-12' if token in ('bound', 'stamp_overridden') else None) for key, token in reasons.items()}

    monkeypatch.setattr(recording_lineage, 'resolve_segment_targets', fake)
    reasons = {'stale': 'token'}
    targets = recording_lineage.plan_segment_targets(
        ['/tmp/seg.wav'],
        lambda _path: gen_start(L + 1) + 61,
        lambda _path: 8.0,
        'u',
        ORIGIN,
        'STAMP',
        'omi',
        'pendant',
        False,
        'job',
        reasons,
    )
    return calls, targets, reasons


def test_plan_reresolves_pending_segments_within_three_attempts(monkeypatch):
    calls, targets, reasons = _drive_plan(
        monkeypatch, lambda attempt, spans: {key: 'ambiguous_pending' if attempt < 3 else 'bound' for key in spans}
    )
    assert len(calls) == 3
    assert targets == {'/tmp/seg.wav': 'LIVE-12'}
    assert reasons == {'/tmp/seg.wav': 'bound'}


def test_plan_keeps_the_pending_token_after_three_attempts(monkeypatch):
    calls, targets, reasons = _drive_plan(
        monkeypatch, lambda _attempt, spans: {key: 'ambiguous_pending' for key in spans}
    )
    assert len(calls) == 3
    assert targets == {'/tmp/seg.wav': None}
    assert reasons == {'/tmp/seg.wav': 'ambiguous_pending'}


@pytest.mark.parametrize('later', ['lookup_failed', 'stamp_fallback', 'unbound', 'no_rows'])
def test_plan_pending_once_stays_pending_through_a_later_ordinary_miss(monkeypatch, later):
    calls, targets, reasons = _drive_plan(
        monkeypatch, lambda attempt, spans: {key: 'ambiguous_pending' if attempt == 1 else later for key in spans}
    )
    assert len(calls) == 2
    assert targets == {'/tmp/seg.wav': None}
    assert reasons == {'/tmp/seg.wav': 'ambiguous_pending'}


def test_plan_pending_clears_only_when_a_later_pass_binds(monkeypatch):
    calls, targets, reasons = _drive_plan(
        monkeypatch, lambda attempt, spans: {key: 'ambiguous_pending' if attempt == 1 else 'bound' for key in spans}
    )
    assert len(calls) == 2
    assert targets == {'/tmp/seg.wav': 'LIVE-12'}
    assert reasons == {'/tmp/seg.wav': 'bound'}


def test_plan_resolves_once_when_no_segment_is_pending(monkeypatch):
    calls, targets, reasons = _drive_plan(monkeypatch, lambda _attempt, spans: {key: 'bound' for key in spans})
    assert len(calls) == 1 and targets == {'/tmp/seg.wav': 'LIVE-12'}
    assert reasons == {'/tmp/seg.wav': 'bound'}


def test_safe_overlap_off_never_enters_the_pending_recheck(monkeypatch, lineage_db):
    monkeypatch.setenv('SYNC_LINEAGE_LIVE_DEDUPE_ENABLED', 'off')
    loaded = []
    real = recording_lineage._load_lineage

    def counting(*args, **kwargs):
        loaded.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(recording_lineage, '_load_lineage', counting)
    old = lineage_db.rows[0]
    old['finished_at'] = at(gen_start(L + 1) + DURATION)
    chunk = upload_straddling_next_two()[0]
    targets = recording_lineage.plan_segment_targets(
        ['/tmp/seg.wav'],
        lambda _path: chunk['started_at'].timestamp(),
        lambda _path: (chunk['finished_at'] - chunk['started_at']).total_seconds(),
        'u',
        ORIGIN,
        'STAMP',
        'omi',
        'pendant',
        False,
        'job',
        {},
    )
    assert targets == {'/tmp/seg.wav': 'STAMP'}
    assert len(loaded) == 1


def test_resolver_excludes_unadmitted_cohorts_from_safe_overlap(monkeypatch, lineage_db):
    monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST_ENV, 'other-uid')
    seen = []
    real = recording_lineage.select_segment_targets

    def spy(*args, **kwargs):
        seen.append(kwargs.get('safe_overlap'))
        return real(*args, **kwargs)

    monkeypatch.setattr(recording_lineage, 'select_segment_targets', spy)
    resolve(upload_straddling_next_two())
    assert seen == [False]


@pytest.mark.parametrize('flag', ['', 'off'])
def test_decision_logging_cannot_fail_an_upload(lineage_db, monkeypatch, flag):
    monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_ENV, flag)

    def broken_handler(*_args, **_kwargs):
        raise RuntimeError('synthetic logging handler failure')

    monkeypatch.setattr(recording_lineage.logger, 'info', broken_handler)
    if flag == 'off':
        assert not lineage_resolution_requested('u', ORIGIN, 1.0, 2.0)
    else:
        chunks = upload_straddling_next_two()
        assert list(resolve(chunks).values()) == [gen_id(L + 1)] * 2 + [gen_id(L + 2)] * 2


def test_lookup_logging_failure_still_falls_back(lineage_db, monkeypatch):
    lineage_db.failing = {'generations', 'origin'}

    def broken_handler(*_args, **_kwargs):
        raise RuntimeError('synthetic logging handler failure')

    monkeypatch.setattr(recording_lineage.logger, 'warning', broken_handler)
    assert set(resolve(upload_straddling_next_two(), stamp='STAMP').values()) == {'STAMP'}


def test_decision_log_is_bounded_and_carries_no_ids(lineage_db, caplog):
    chunks = upload_straddling_next_two()
    with caplog.at_level(logging.INFO, logger=recording_lineage.__name__):
        resolve(chunks, stamp=gen_id(L))
    lines = [record.getMessage() for record in caplog.records if 'event=sync_lineage_resolve' in record.getMessage()]
    assert len(lines) == 1
    assert 'outcome=split_across_generations reason=none segments=4 bound=0 stamp_overridden=4' in lines[0]
    for forbidden in (ORIGIN, 'LIVE-', 'SYNC-', ' u ', 'quarterly'):
        assert forbidden not in lines[0]


class _FakeQuery:
    def __init__(self, docs):
        self.docs = docs
        self.ops = []

    def collection(self, name):
        self.ops.append(('collection', name))
        return self

    def document(self, name):
        self.ops.append(('document', name))
        return self

    def where(self, *, filter):
        self.ops.append(('where', filter.field_path, filter.op_string, filter.value))
        return self

    def order_by(self, field_path, direction):
        self.ops.append(('order_by', field_path, direction))
        return self

    def select(self, field_paths):
        self.ops.append(('select', tuple(field_paths)))
        self.field_paths = tuple(field_paths)
        return self

    def limit(self, count):
        self.ops.append(('limit', count))
        return self

    def stream(self):
        return iter(self.projected_docs())

    def projected_docs(self):
        """Each doc's dict narrowed to the selected field paths, as the real
        backend serves a ``select`` projection (dotted paths nest)."""
        if getattr(self, 'field_paths', None) is None:
            return self.docs
        projected = []
        for doc in self.docs:
            data = doc.to_dict()
            out = {}
            for path in self.field_paths:
                parts = path.split('.')
                value = data
                for part in parts:
                    if not isinstance(value, dict) or part not in value:
                        value = None
                        break
                    value = value[part]
                if value is None:
                    continue
                target = out
                for part in parts[:-1]:
                    target = target.setdefault(part, {})
                target[parts[-1]] = deepcopy(value)
            projected.append(SimpleNamespace(id=doc.id, to_dict=lambda out=out: deepcopy(out)))
        return projected


def test_lineage_reads_are_bounded_indexed_and_transcript_free(monkeypatch):
    from database import sync_recording_lineage as lineage_db

    reads = []
    monkeypatch.setattr(lineage_db, 'record_firestore_read', lambda *args: reads.append(args))
    doc = SimpleNamespace(id='LIVE-01', to_dict=lambda: {'started_at': at(T0)})
    before = at(T0 + 600)
    query = _FakeQuery([doc])
    rows = lineage_db.get_recording_generations(
        'u', ORIGIN, started_before=before, finished_after=at(T0), limit=8, firestore_client=query
    )
    assert rows == [{'started_at': at(T0), 'id': 'LIVE-01'}]
    assert query.ops[:3] == [('collection', 'users'), ('document', 'u'), ('collection', 'conversations')]
    assert query.ops[3:8] == [
        ('where', 'external_data.recording_origin_id', '==', ORIGIN),
        ('where', 'started_at', '<=', before),
        ('where', 'finished_at', '>=', at(T0)),
        ('order_by', 'started_at', 'DESCENDING'),
        ('order_by', 'finished_at', 'DESCENDING'),
    ]
    selected = query.ops[8][1]
    assert query.ops[9] == ('limit', 9)
    assert not any(field.startswith(('transcript', 'photos', 'structured')) for field in selected)
    origin = _FakeQuery([])
    assert lineage_db.get_origin_generation('u', ORIGIN, limit=5, firestore_client=origin) == []
    assert ('where', 'external_data.recording_session_id', '==', ORIGIN) in origin.ops and ('limit', 6) in origin.ops
    assert [(family.value, mode.value, count) for family, mode, count in reads] == [
        ('sync_recording_lineage', 'bounded', 1),
        ('sync_recording_lineage', 'bounded', 0),
    ]


def test_lineage_projection_always_carries_deleted_and_discarded(monkeypatch):
    from database import sync_recording_lineage as lineage_db

    monkeypatch.setattr(lineage_db, 'record_firestore_read', lambda *args: None)
    full = {
        'created_at': at(T0),
        'started_at': at(T0),
        'finished_at': at(T0 + 60),
        'source': 'omi',
        'client_device_id': 'pendant',
        'is_locked': False,
        'deleted': False,
        'discarded': True,
        'sync_merged_into': 'GEN-MERGED',
        'smart_merge': {'role': 'donor', 'survivor_id': 'GEN-MERGED'},
        'external_data': {'recording_session_id': 'SESSION-X', 'recording_origin_id': ORIGIN},
        'capture_evidence': {'version': 1, 'origin': 'live'},
        'transcript_segments': [{'text': 'hidden'}],
        'structured': {'title': 'hidden'},
    }
    doc = SimpleNamespace(id='GEN-DONOR', to_dict=lambda: deepcopy(full))
    for include in (False, True):
        query = _FakeQuery([doc])
        rows = lineage_db.get_recording_generations(
            'u',
            ORIGIN,
            started_before=at(T0 + 600),
            finished_after=at(T0),
            limit=8,
            include_capture_evidence=include,
            firestore_client=query,
        )
        selected = next(op[1] for op in query.ops if op[0] == 'select')
        assert 'deleted' in selected and 'discarded' in selected
        assert ('capture_evidence' in selected) is include
        assert rows[0]['discarded'] is True and rows[0]['deleted'] is False
        assert 'transcript_segments' not in rows[0] and 'structured' not in rows[0]
        assert ('capture_evidence' in rows[0]) is include
        origin = _FakeQuery([doc])
        rows = lineage_db.get_origin_generation(
            'u', ORIGIN, limit=5, include_capture_evidence=include, firestore_client=origin
        )
        selected = next(op[1] for op in origin.ops if op[0] == 'select')
        assert 'deleted' in selected and 'discarded' in selected
        assert ('capture_evidence' in selected) is include
        assert rows[0]['discarded'] is True and ('capture_evidence' in rows[0]) is include


def test_projected_discard_flag_reaches_the_planner(monkeypatch):
    """Real query + projection: a discarded covering row cannot compete with a
    visible one, so the single visible canonical wins instead of pending."""
    from database import sync_recording_lineage as lineage_db

    monkeypatch.setenv('SYNC_LINEAGE_LIVE_DEDUPE_ENABLED', 'true')
    monkeypatch.setattr(lineage_db, 'record_firestore_read', lambda *args: None)
    base = {
        'created_at': at(gen_start(1)),
        'started_at': at(gen_start(1)),
        'finished_at': at(gen_start(1) + DURATION),
        'source': 'omi',
        'client_device_id': 'pendant',
        'is_locked': False,
        'deleted': False,
        'external_data': {'recording_session_id': ORIGIN, 'recording_origin_id': ORIGIN},
        'transcript_segments': [{'text': 'hidden'}],
    }
    visible = dict(base, discarded=False)
    hidden = dict(base, discarded=True)
    query = _FakeQuery(
        [
            SimpleNamespace(id='LIVE-V', to_dict=lambda: deepcopy(visible)),
            SimpleNamespace(id='LIVE-D', to_dict=lambda: deepcopy(hidden)),
        ]
    )
    start = gen_start(1) + 30.0
    reasons = {}
    targets = resolve_segment_targets(
        'u',
        ORIGIN,
        {'seg.wav': (start, start + 10.0)},
        stamped_target=None,
        source='omi',
        client_device_id='pendant',
        is_locked=False,
        firestore_client=query,
        binding_reasons=reasons,
    )
    assert targets == {'seg.wav': 'LIVE-V'}
    assert reasons == {'seg.wav': 'bound'}


# --- Kill switch --------------------------------------------------------------


@pytest.mark.parametrize(('value', 'enabled'), [('', True), ('true', True), ('on', True), ('1', True)])
def test_unset_or_on_values_keep_the_feature_on(monkeypatch, value, enabled):
    monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_ENV, value)
    assert sync_lineage.sync_lineage_resolve_enabled() is enabled


@pytest.mark.parametrize('value', ['off', 'false', '0', 'no', 'of', 'disabled-typo'])
def test_off_and_unrecognized_values_disable_it(monkeypatch, value, caplog):
    monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_ENV, value)
    assert not sync_lineage.sync_lineage_resolve_enabled()
    with caplog.at_level(logging.INFO, logger=recording_lineage.__name__):
        assert not lineage_resolution_requested('u', ORIGIN, 1.0, 2.0)
    assert 'event=sync_lineage_resolve outcome=disabled' in caplog.text


# --- Coordinator call site ----------------------------------------------------


@pytest.fixture
def coordinator():
    """The routers.sync behavioral harness; import-heavy, so built outside the call budget."""
    module, stubs = sync_v2_harness.TestAsyncCoordinatorBehavioral._load_sync_module()
    try:
        yield module, stubs
    finally:
        sync_v2_harness.TestAsyncCoordinatorBehavioral._cleanup(stubs['saved_modules'])


def _drive(module, stubs, chunks, monkeypatch, *, stamp, s1_claims=None):
    pipeline = stubs['pipeline']
    paths = {f"/tmp/job-lineage/seg_{chunk['started_at'].timestamp():.0f}.wav": chunk for chunk in chunks}
    wav_path = '/tmp/job-lineage/w.wav'

    def decode(raw_paths, decoded_frames=None):
        if decoded_frames is not None:
            decoded_frames[wav_path] = [16000]
        return [wav_path]

    pipeline.decode_files_to_wav = MagicMock(side_effect=decode)
    pipeline._cleanup_files = MagicMock()
    pipeline.retrieve_vad_segments = lambda _path, segmented, _errors, **_kwargs: segmented.update(paths)
    pipeline.get_timestamp_from_path = lambda path: paths[path]['started_at'].timestamp()
    pipeline.get_wav_duration = lambda path: (paths[path]['finished_at'] - paths[path]['started_at']).total_seconds()
    pipeline.users_db = MagicMock()
    pipeline.users_db.get_user_transcription_preferences = MagicMock(return_value={})
    pipeline.build_person_embeddings_cache = MagicMock(return_value={})
    pipeline.record_usage = MagicMock()
    captured = {}

    def capture(path, uid, response, lock, errors, source, is_locked, prefs, cache, target, *args, **kwargs):
        captured[paths[path]['id']] = target
        response['updated_memories'].add(target or 'sync-row')
        return True

    pipeline.process_segment = capture
    if hasattr(pipeline, 'plan_segment_targets'):
        # Also supports replaying the coordinator against origin/main's
        # pipeline, which has no lineage call. Its observed targets must still
        # satisfy the assertion below; absence is not the failure criterion.
        monkeypatch.setattr(
            sys.modules[pipeline.plan_segment_targets.__module__],
            '_load_lineage',
            lambda *_args, **_kwargs: ([generation(k) for k in range(GENERATIONS)], None, False),
        )
    candidates = [generation(0)]
    monkeypatch.setattr(
        sys.modules[pipeline.resolve_recording_session_sync_target.__module__],
        '_candidate_rows',
        lambda *_args, **_kwargs: candidates,
    )
    if s1_claims:
        mapping = {'claim': next(iter(s1_claims.values())), 'offsets': [0, 16000], 'incomplete': False}

        async def observed_maps(_uid, _source, _lock, _device, _session, _claims, wav_paths, _frames, **_kwargs):
            return wav_paths, {path: dict(mapping) for path in wav_paths}, False

        monkeypatch.setattr(pipeline, 'apply_sync_wal_audio_coverage', observed_maps)
    return captured, SimpleNamespace(
        target_conversation_id=stamp,
        client_device_id='pendant',
        recording_session_id=ORIGIN,
        audio_start_seconds=chunks[0]['started_at'].timestamp() - 8,
        audio_end_seconds=chunks[-1]['finished_at'].timestamp(),
        capture_evidence_claims=s1_claims,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('flag', ['', 'off'])
async def test_coordinator_forwards_each_segment_its_generation(coordinator, monkeypatch, flag):
    module, stubs = coordinator
    monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_ENV, flag)
    monkeypatch.setenv('SYNC_LINEAGE_S1_REQUIRED', 'off')
    chunks = upload_straddling_next_two()
    captured, kwargs = _drive(module, stubs, chunks, monkeypatch, stamp=gen_id(L))
    await module._run_full_pipeline_background_async(
        'job-lineage', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job-lineage', **vars(kwargs)
    )
    expected = [gen_id(L + 1)] * 2 + [gen_id(L + 2)] * 2 if flag == '' else [None] * 4
    assert [captured[chunk['id']] for chunk in chunks] == expected


@pytest.mark.asyncio
async def test_coordinator_lineage_exception_keeps_stamp_and_processes_siblings(coordinator, monkeypatch, caplog):
    module, stubs = coordinator
    monkeypatch.setenv('SYNC_LINEAGE_S1_REQUIRED', 'off')
    chunks = upload_straddling_next_two()
    captured, kwargs = _drive(module, stubs, chunks, monkeypatch, stamp='STAMP')

    def failed(*_args, **_kwargs):
        raise RuntimeError('synthetic planner failure')

    monkeypatch.setattr(stubs['pipeline'], 'plan_segment_targets', failed)
    metrics = MagicMock()
    lineage_module = sys.modules[stubs['pipeline'].fallback_segment_targets.__module__]
    monkeypatch.setattr(lineage_module, 'OMI_SYNC_LINEAGE_RESOLVE_TOTAL', metrics)
    caplog.set_level(logging.INFO, logger=lineage_module.__name__)
    await module._run_full_pipeline_background_async(
        'job-lineage', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job-lineage', **vars(kwargs)
    )
    assert captured == {chunk['id']: 'STAMP' for chunk in chunks}
    metrics.labels.assert_called_once_with(outcome='lookup_failed')
    metrics.labels.return_value.inc.assert_called_once()
    assert sum('event=sync_lineage_resolve' in r.getMessage() for r in caplog.records) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('flag', ['', 'off'])
async def test_retry_after_append_before_enrichment_reprocesses_the_landed_row(coordinator, monkeypatch, flag):
    module, stubs = coordinator
    monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_ENV, flag)
    monkeypatch.setenv('SYNC_LINEAGE_S1_REQUIRED', 'off')
    chunks = upload_straddling_next_two()[:1]
    captured, kwargs = _drive(module, stubs, chunks, monkeypatch, stamp=gen_id(L))
    pipeline = stubs['pipeline']
    pipeline.get_sync_job = MagicMock(
        return_value={
            'partial_result': {'updated_memories': [gen_id(L + 1), 'FENCED'], 'fenced_conversation_ids': ['FENCED']}
        }
    )
    pipeline.get_processed_segments = MagicMock(
        return_value={f"/tmp/job-lineage/seg_{chunk['started_at'].timestamp():.0f}.wav" for chunk in chunks}
    )
    enriched = []

    def reprocess(_uid, response, *_args, **_kwargs):
        enriched.append(dict(response.pop('_merged', {})))

    pipeline._reprocess_merged_conversations = reprocess
    await module._run_full_pipeline_background_async(
        'job-lineage', 'uid', ['/tmp/f.opus'], 'omi', False, '/tmp/job-lineage', task_mode=True, **vars(kwargs)
    )
    assert captured == {}  # landed audio never returns to STT or assignment
    assert enriched == ([{gen_id(L + 1): pipeline._LINEAGE_RETRY_LANGUAGE}] if flag == '' else [{}])


def test_sync_reprocess_does_not_complete_an_open_live_recording(dependencies, monkeypatch):
    pipeline = dependencies
    row = generation(
        L,
        status='in_progress',
        sync_live_target=True,
        sync_content_revision=1,
        created_at=at(gen_start(L)),
        structured={'title': 'Synthetic review'},
    )
    monkeypatch.setattr(pipeline.conversations_db, 'get_conversation', lambda *_args: row)
    process = MagicMock()
    monkeypatch.setattr(pipeline, 'process_conversation', process)
    pipeline._reprocess_conversation_after_update('u', row['id'], 'en')
    process.assert_not_called()


@pytest.mark.parametrize(('status', 'flag'), [('completed', ''), ('processing', ''), ('in_progress', 'off')])
def test_finalized_and_processing_targets_and_off_keep_reprocessing(dependencies, monkeypatch, status, flag):
    pipeline = dependencies
    monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_ENV, flag)
    row = generation(
        L,
        status=status,
        sync_live_target=True,
        sync_content_revision=1,
        created_at=at(gen_start(L)),
        structured={'title': 'Synthetic review'},
    )
    monkeypatch.setattr(pipeline.conversations_db, 'get_conversation', lambda *_args: row)
    process = MagicMock()
    monkeypatch.setattr(pipeline, 'process_conversation', process)
    pipeline._reprocess_conversation_after_update('u', row['id'], 'en')
    assert len(process.call_args_list) == (0 if status == 'in_progress' else 1)


@pytest.mark.parametrize('flag', ['', 'off'])
def test_resumed_enrichment_uses_stored_language(dependencies, monkeypatch, flag):
    pipeline = dependencies
    monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_ENV, flag)
    row = generation(L, created_at=at(gen_start(L)), structured={'title': 'Synthetic review'}, language='es')
    monkeypatch.setattr(pipeline.conversations_db, 'get_conversation', lambda *_args: row)
    process = MagicMock()
    monkeypatch.setattr(pipeline, 'process_conversation', process)
    language = pipeline._LINEAGE_RETRY_LANGUAGE if flag == '' else ''
    pipeline._reprocess_conversation_after_update('u', row['id'], language)
    assert process.call_args.kwargs['language_code'] == ('es' if flag == '' else 'en')


# --- Live origin stamp ----------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize('flag', ['', 'off'])
async def test_every_live_generation_names_its_origin_recording(monkeypatch, flag):
    monkeypatch.setenv(sync_lineage.SYNC_LINEAGE_RESOLVE_ENV, flag)
    harness = continuity.CaptureHarness(monkeypatch)
    first = harness.connect(client_id='fresh')
    await first.prepare()
    assert first.host.state.current_conversation_id == 'fresh'
    harness.now = harness.rows['original']['finished_at'] + timedelta(seconds=300)
    rollover = harness.connect()
    await rollover.prepare()
    generation_id = rollover.host.state.current_conversation_id
    assert generation_id != 'original'
    assert harness.rows[generation_id]['external_data']['recording_session_id'] != 'original'
    origins = [harness.rows[cid]['external_data'].get('recording_origin_id') for cid in ('fresh', generation_id)]
    assert origins == (['fresh', 'original'] if flag == '' else [None, None])
