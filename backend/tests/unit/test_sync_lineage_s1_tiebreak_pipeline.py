"""End-to-end S1 tiebreak: an unstamped WAL segment ambiguous across live rows
binds to the canonical whose validated committed run covers/adjoins its frames.

The fixture replays the synthetic 2026-10-05 incident shape through the real
coordinator: a smart-merge survivor row covering 13:06:10-13:46:05 UTC (donor
redirect tombstone retained), five discarded non-deleted live rows inside its
interval, and a competing visible backdated row created 13:39:40 covering
13:25:03-13:46:05 — all strictly containing the segment, no phone stamp.
Without the frame evidence the plan stays pending and the speech is lost to a
retryable failure; with it the saved words land on the merged survivor that
provably captured the adjoining live frames, never on GEN-BACK or a hidden
row. All ids are synthetic.
"""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import tests.unit.test_wal_audio_coverage_pipeline as wal_pipeline_harness
from config.sync_live_dedupe import SYNC_LINEAGE_LIVE_DEDUPE_ENV
from tests.unit.test_sync_cross_job_assignment import intake
from tests.unit.test_sync_lineage_dedupe_replay import at, seeded_store
from tests.unit.test_sync_recording_lineage import ORIGIN
from utils.capture_evidence import SourcePositionMap
from utils.conversations import lifecycle
from utils.sync import recording_lineage

WAL_TS = datetime(2026, 10, 5, 13, 35, 0, tzinfo=timezone.utc).timestamp()
MERGED_START = datetime(2026, 10, 5, 13, 6, 10, tzinfo=timezone.utc).timestamp()
MERGED_END = datetime(2026, 10, 5, 13, 46, 5, tzinfo=timezone.utc).timestamp()
BACK_START = datetime(2026, 10, 5, 13, 25, 3, tzinfo=timezone.utc).timestamp()
BACK_CREATED = datetime(2026, 10, 5, 13, 39, 40, tzinfo=timezone.utc).timestamp()
DONOR_START = datetime(2026, 10, 5, 13, 40, 0, tzinfo=timezone.utc).timestamp()
MERGED_AT = MERGED_END
DISC_RANGES = [
    ('13:13:00', '13:17:00'),
    ('13:17:00', '13:21:00'),
    ('13:21:00', '13:27:00'),
    ('13:27:00', '13:33:00'),
    ('13:33:00', '13:40:00'),
]
INCIDENT_STEM = f'audio_pcm16_{int(WAL_TS)}'
INCIDENT_BIN = f'{INCIDENT_STEM}.bin'


@pytest.fixture(scope='module')
def real_pipeline():
    from utils.sync import pipeline

    return pipeline


def _hms(value):
    hour, minute, second = (int(part) for part in value.split(':'))
    return datetime(2026, 10, 5, hour, minute, second, tzinfo=timezone.utc)


def _incident_rows(merged_evidence=None):
    """The exact synthetic incident: merged survivor, donor tombstone, five
    discarded rows spanning 13:13-13:40, and the backdated competitor."""
    merged = {
        'id': 'GEN-MERGED',
        'created_at': at(MERGED_AT),
        'started_at': at(MERGED_START),
        'finished_at': at(MERGED_END),
        'source': 'omi',
        'client_device_id': 'pendant',
        'is_locked': False,
        'discarded': False,
        'status': 'completed',
        'external_data': {'recording_session_id': 'SESSION-MERGED', 'recording_origin_id': ORIGIN},
        'sync_merged_from': ['GEN-DONOR'],
        'smart_merge': {
            'role': 'survivor',
            'revision': 2,
            'refreshed_revision': 1,
            'fragments': [{'donor': 'GEN-DONOR'}],
            'last_merged_at': at(MERGED_AT),
        },
        'transcript_segments': [
            {'start': 0.0, 'end': 1.0, 'text': 'merged live speech', 'speaker_id': 0, 'is_user': False}
        ],
    }
    if merged_evidence is not None:
        merged['capture_evidence'] = merged_evidence
    donor = {
        'id': 'GEN-DONOR',
        'created_at': at(DONOR_START),
        'started_at': at(DONOR_START),
        'finished_at': at(MERGED_END),
        'source': 'omi',
        'client_device_id': 'pendant',
        'is_locked': False,
        'deleted': True,
        'discarded': True,
        'status': 'completed',
        'external_data': {'recording_session_id': 'SESSION-DONOR', 'recording_origin_id': ORIGIN},
        'sync_merged_into': 'GEN-MERGED',
        'smart_merge': {
            'role': 'donor',
            'survivor_id': 'GEN-MERGED',
            'survivor_revision': 2,
            'merged_at': at(MERGED_AT),
        },
        'transcript_segments': [
            {'start': 0.0, 'end': 1.0, 'text': 'donor live speech', 'speaker_id': 0, 'is_user': False}
        ],
    }
    back = {
        'id': 'GEN-BACK',
        'created_at': at(BACK_CREATED),
        'started_at': at(BACK_START),
        'finished_at': at(MERGED_END),
        'source': 'omi',
        'client_device_id': 'pendant',
        'is_locked': False,
        'discarded': False,
        'status': 'completed',
        'external_data': {'recording_session_id': 'SESSION-BACK', 'recording_origin_id': ORIGIN},
        'transcript_segments': [
            {'start': 0.0, 'end': 1.0, 'text': 'backdated live speech', 'speaker_id': 0, 'is_user': False}
        ],
    }
    rows = [merged, donor, back]
    for index, (start, end) in enumerate(DISC_RANGES):
        rows.append(
            {
                'id': f'GEN-DISC-{index}',
                'created_at': _hms(start),
                'started_at': _hms(start),
                'finished_at': _hms(end),
                'source': 'omi',
                'client_device_id': 'pendant',
                'is_locked': False,
                'discarded': True,
                'status': 'completed',
                'external_data': {
                    'recording_session_id': f'SESSION-DISC-{index}',
                    'recording_origin_id': ORIGIN,
                },
                'transcript_segments': [
                    {
                        'start': 0.0,
                        'end': 1.0,
                        'text': f'discarded live speech {index}',
                        'speaker_id': 0,
                        'is_user': False,
                    }
                ],
            }
        )
    return rows


def _merged_evidence(first, last, wall_first):
    """Real committed proof on the merged survivor: ordinals first..last-1 with
    receipt_wall anchors on the WAL's own phone clock (wall_first = wall at the
    first ordinal's frame start)."""
    source = SourcePositionMap(committed=True)
    cursor = 0
    for ordinal in range(first, last):
        source.accept(
            {
                'capture_root': wal_pipeline_harness.ROOT,
                'clock_epoch': wal_pipeline_harness.EPOCH,
                'source_frame': ordinal,
            },
            sample_start=cursor,
            sample_count=wal_pipeline_harness.FRAME_SAMPLES,
            rate_hz=wal_pipeline_harness.RATE,
            payload=wal_pipeline_harness._frame_bytes(ordinal % 7, 2048),
            receipt_wall_time=wall_first
            + (ordinal - first + 1) * wal_pipeline_harness.FRAME_SAMPLES / wal_pipeline_harness.RATE,
        )
        cursor += wal_pipeline_harness.FRAME_SAMPLES
    source.remember_transcripts([{'id': 'live-s0', '_capture_word_ranges': ((0, cursor),)}])
    return source.committed_snapshot(
        'GEN-MERGED',
        [SimpleNamespace(id='live-s0', text='merged live speech', start=0.0, end=1.0, audio_alignment=None)],
    )


def _claim(frame_start=40, frame_count=10):
    return {
        'capture_root': wal_pipeline_harness.ROOT,
        'clock_epoch': wal_pipeline_harness.EPOCH,
        'source_frame_start': frame_start,
        'frame_count': frame_count,
        'rate_hz': wal_pipeline_harness.RATE,
        'codec': 'pcm16',
        'channel': 'mono',
    }


def _projected(row, field_paths):
    """Server-side field projection on a stored row dict (dotted paths nest)."""
    projected = {}
    for path in field_paths:
        parts = path.split('.')
        value = row
        for part in parts:
            if not isinstance(value, dict) or part not in value:
                value = None
                break
            value = value[part]
        if value is None:
            continue
        target = projected
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = deepcopy(value)
    projected['id'] = row['id']
    return projected


def _wire_lineage_db(monkeypatch, rows):
    """Real ``_load_lineage`` against an in-memory seam honoring the query
    semantics and the field projection — exactly what production reads serve."""
    from database import sync_recording_lineage as lineage_db

    calls = []

    def fields(include_capture_evidence):
        return list(lineage_db.LINEAGE_FIELD_PATHS) + (['capture_evidence'] if include_capture_evidence else [])

    def get_recording_generations(
        uid,
        origin_id,
        *,
        started_before,
        finished_after=None,
        limit,
        include_capture_evidence=False,
        firestore_client=None,
    ):
        calls.append(include_capture_evidence)
        matching = [
            row
            for row in rows
            if (row.get('external_data') or {}).get('recording_origin_id') == origin_id
            and row['started_at'] <= started_before
            and (finished_after is None or row['finished_at'] >= finished_after)
        ]
        matching.sort(key=lambda row: (row['started_at'], row['id']), reverse=True)
        return [_projected(row, fields(include_capture_evidence)) for row in matching[: limit + 1]]

    def get_origin_generation(uid, origin_id, *, limit, include_capture_evidence=False, firestore_client=None):
        calls.append(include_capture_evidence)
        matching = [row for row in rows if (row.get('external_data') or {}).get('recording_session_id') == origin_id]
        return [_projected(row, fields(include_capture_evidence)) for row in matching[: limit + 1]]

    monkeypatch.setattr(lineage_db, 'get_recording_generations', get_recording_generations)
    monkeypatch.setattr(lineage_db, 'get_origin_generation', get_origin_generation)
    return calls


def _wire_incident(pipeline, monkeypatch, tmp_path, *, rows, word=None):
    """Real coordinator + real planner + real ``_load_lineage`` through the
    projection-faithful fake DB; ``_wire_real`` owns the rest of the stubs."""
    monkeypatch.setattr(wal_pipeline_harness, 'WAV_STEM', INCIDENT_STEM)
    monkeypatch.setattr(wal_pipeline_harness, 'BIN_NAME', INCIDENT_BIN)
    state = wal_pipeline_harness._wire_real(
        pipeline, monkeypatch, tmp_path, lineage_rows=rows, word=word or (lambda v: f'new-word-{v}')
    )
    monkeypatch.setattr(pipeline, 'lineage_resolution_requested', recording_lineage.lineage_resolution_requested)
    monkeypatch.setattr(recording_lineage, 'load_lineage', recording_lineage._load_lineage)
    state.projection_calls = _wire_lineage_db(monkeypatch, rows)
    plan_results = []
    real_plan = recording_lineage.plan_segment_targets

    def plan_spy(*args, **kwargs):
        result = real_plan(*args, **kwargs)
        plan_results.append((result, dict(kwargs.get('segment_source_maps') or {})))
        return result

    monkeypatch.setattr(pipeline, 'plan_segment_targets', plan_spy)
    state.plan_results = plan_results
    postprocess = pipeline.postprocess_words

    def with_segment_ids(words, offset):
        segments = postprocess(words, offset)
        for index, segment in enumerate(segments):
            segment.id = f'wal-seg-{index}'
        return segments

    monkeypatch.setattr(pipeline, 'postprocess_words', with_segment_ids)
    return state


async def _run_incident(pipeline, tmp_path, *, claims='default', target=None):
    await pipeline._run_full_pipeline_background_async(
        'job-tiebreak',
        'u',
        [f'/tmp/{INCIDENT_BIN}'],
        'omi',
        False,
        str(tmp_path / 'job'),
        target_conversation_id=target,
        client_device_id='pendant',
        recording_session_id=ORIGIN,
        audio_start_seconds=WAL_TS - 2000.0,
        audio_end_seconds=WAL_TS + 2000.0,
        task_mode=True,
        capture_evidence_claims={INCIDENT_BIN: _claim()} if claims == 'default' else claims,
    )


def _stored(store, row_id):
    return store.rows[('users', 'u', 'conversations', row_id)]


def _texts(store, row_id):
    return [s['text'] for s in _stored(store, row_id)['transcript_segments']]


def _row_ids(store):
    return {key[-1] for key in store.rows if key[2] == 'conversations'}


def _seed_and_intake(monkeypatch, rows):
    store = seeded_store(rows)
    monkeypatch.setattr(
        lifecycle,
        'ingest_sync_conversation',
        lambda uid, incoming, *, candidate_id=None, target_id=None: intake(
            store, incoming, candidate_id=candidate_id, target_id=target_id
        ),
    )
    return store


def _assert_incident_fixture(rows):
    """Exact incident dates, roles and merge metadata."""
    by_id = {row['id']: row for row in rows}
    merged = by_id['GEN-MERGED']
    assert merged['started_at'] == _hms('13:06:10')
    assert merged['finished_at'] == _hms('13:46:05')
    assert merged['smart_merge']['role'] == 'survivor'
    assert merged['sync_merged_from'] == ['GEN-DONOR']
    donor = by_id['GEN-DONOR']
    assert donor['deleted'] is True and donor['discarded'] is True
    assert donor['smart_merge']['role'] == 'donor'
    assert donor['sync_merged_into'] == 'GEN-MERGED'
    assert donor['started_at'] == _hms('13:40:00') and donor['finished_at'] == _hms('13:46:05')
    back = by_id['GEN-BACK']
    assert back['created_at'] == _hms('13:39:40')
    assert back['started_at'] == _hms('13:25:03') and back['finished_at'] == _hms('13:46:05')
    assert back['discarded'] is False
    for index, (start, end) in enumerate(DISC_RANGES):
        row = by_id[f'GEN-DISC-{index}']
        assert row['started_at'] == _hms(start) and row['finished_at'] == _hms(end)
        assert row['discarded'] is True and not row.get('deleted')


@pytest.mark.asyncio
async def test_adjoining_committed_run_binds_the_merged_survivor_and_saves_speech(real_pipeline, monkeypatch, tmp_path):
    """The WAL's frames (40..49) were never received live; the committed run
    20..40 on the merged survivor ends exactly at frame 40, so the segment
    binds there instead of staying pending and losing the speech — never to
    GEN-BACK or the hidden discarded rows."""
    pipeline = real_pipeline
    wal_pipeline_harness._coverage_env(monkeypatch)
    monkeypatch.setenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, 'true')
    monkeypatch.delenv('SYNC_LINEAGE_S1_REQUIRED', raising=False)
    rows = _incident_rows(merged_evidence=_merged_evidence(20, 40, WAL_TS - 10.0))
    _assert_incident_fixture(rows)
    store = _seed_and_intake(monkeypatch, rows)
    state = _wire_incident(pipeline, monkeypatch, tmp_path, rows=rows)
    await _run_incident(pipeline, tmp_path)
    merged = _stored(store, 'GEN-MERGED')
    assert merged.get('deleted') is not True
    assert merged['discarded'] is False
    texts = _texts(store, 'GEN-MERGED')
    assert 'merged live speech' in texts
    for i in range(10):
        assert texts.count(f'new-word-{i}') == 1
    assert _texts(store, 'GEN-BACK') == ['backdated live speech']
    assert _texts(store, 'GEN-DONOR') == ['donor live speech']
    for index in range(5):
        assert _texts(store, f'GEN-DISC-{index}') == [f'discarded live speech {index}']
    assert _row_ids(store) == {row['id'] for row in rows}
    assert state.outcomes[-1].value == 'success'
    assert state.prerecorded_calls
    assert state.projection_calls and all(flag is True for flag in state.projection_calls)
    assert state.finish.call_count == 1
    assert state.finish.call_args.args[1]['id'] == 'GEN-MERGED'


@pytest.mark.asyncio
async def test_single_visible_survivor_binds_when_discard_flag_survives_projection(
    real_pipeline, monkeypatch, tmp_path
):
    """Without the backdated competitor the lone visible canonical wins only
    because the projected `discarded` boolean reaches the planner."""
    pipeline = real_pipeline
    wal_pipeline_harness._coverage_env(monkeypatch)
    monkeypatch.setenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, 'true')
    monkeypatch.delenv('SYNC_LINEAGE_S1_REQUIRED', raising=False)
    rows = [row for row in _incident_rows() if row['id'] != 'GEN-BACK']
    store = _seed_and_intake(monkeypatch, rows)
    state = _wire_incident(pipeline, monkeypatch, tmp_path, rows=rows)
    await _run_incident(pipeline, tmp_path)
    texts = _texts(store, 'GEN-MERGED')
    for i in range(10):
        assert texts.count(f'new-word-{i}') == 1
    assert state.finish.call_args.args[1]['id'] == 'GEN-MERGED'
    assert state.outcomes[-1].value == 'success'


@pytest.mark.asyncio
async def test_coverage_trimmed_derivative_binds_the_merged_survivor(real_pipeline, monkeypatch, tmp_path):
    """Committed frames 40..45 on the survivor trim first; the derivative
    keeps only new frames 45..49 (values 5..9) and still binds GEN-MERGED."""
    pipeline = real_pipeline
    wal_pipeline_harness._coverage_env(monkeypatch)
    monkeypatch.setenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, 'true')
    monkeypatch.delenv('SYNC_LINEAGE_S1_REQUIRED', raising=False)
    rows = _incident_rows(merged_evidence=_merged_evidence(40, 45, WAL_TS))
    store = _seed_and_intake(monkeypatch, rows)
    state = _wire_incident(pipeline, monkeypatch, tmp_path, rows=rows)
    await _run_incident(pipeline, tmp_path)
    assert len(state.processed_paths) == 1
    derivative = state.processed_paths[0]
    assert '.coverage' in derivative
    assert wal_pipeline_harness._read_payload(derivative) == b''.join(
        wal_pipeline_harness._frame_bytes(v, wal_pipeline_harness.FRAME_SAMPLES) for v in range(5, 10)
    )
    texts = _texts(store, 'GEN-MERGED')
    for i in range(5, 10):
        assert texts.count(f'new-word-{i}') == 1
    assert all(not text.startswith('new-word-') for text in _texts(store, 'GEN-BACK'))
    assert all(not text.startswith('new-word-') for text in _texts(store, 'GEN-DONOR'))
    assert _row_ids(store) == {row['id'] for row in rows}
    assert state.finish.call_args.args[1]['id'] == 'GEN-MERGED'
    assert state.outcomes[-1].value == 'success'


@pytest.mark.asyncio
async def test_fully_committed_wal_skips_provider_writes_and_enrichment(real_pipeline, monkeypatch, tmp_path):
    """Committed proof over every WAL frame (40..50) suppresses the whole file:
    no STT call, no intake write, no enrichment — only a success ledger."""
    pipeline = real_pipeline
    wal_pipeline_harness._coverage_env(monkeypatch)
    monkeypatch.setenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, 'true')
    monkeypatch.delenv('SYNC_LINEAGE_S1_REQUIRED', raising=False)
    rows = _incident_rows(merged_evidence=_merged_evidence(40, 50, WAL_TS))
    store = _seed_and_intake(monkeypatch, rows)
    state = _wire_incident(pipeline, monkeypatch, tmp_path, rows=rows)
    await _run_incident(pipeline, tmp_path)
    assert state.prerecorded_calls == []
    assert state.processed_paths == []
    assert state.plan_results == []
    assert _texts(store, 'GEN-MERGED') == ['merged live speech']
    assert _row_ids(store) == {row['id'] for row in rows}
    assert state.outcomes[-1].value == 'success'


@pytest.mark.asyncio
async def test_committed_proof_reaches_intake_dedupe_but_abstains_without_wal_context(
    real_pipeline, monkeypatch, tmp_path
):
    """Coverage trimming off, committed proof on the survivor covering the
    WAL's frames: the intake dedupe consumer calls capture_covered_indices
    with the real sync_vad receipts and the chosen GEN-MERGED live envelope,
    and the existing proof contract abstains without observed WAL context —
    identical repeats are appended, never suppressed."""
    pipeline = real_pipeline
    wal_pipeline_harness._coverage_env(monkeypatch, coverage_flag='off')
    monkeypatch.setenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, 'true')
    monkeypatch.delenv('SYNC_LINEAGE_S1_REQUIRED', raising=False)
    live_texts = [f'the quiet river carried leaf {v} downstream past the mill' for v in range(7)]
    merged_evidence = _merged_evidence(40, 50, WAL_TS)
    rows = _incident_rows(merged_evidence=merged_evidence)
    merged = next(row for row in rows if row['id'] == 'GEN-MERGED')
    merged['transcript_segments'] = [
        {
            'start': 1730.0 + i * 0.5,
            'end': 1730.0 + i * 0.5 + 0.5,
            'text': live_texts[i],
            'speaker_id': 0,
            'is_user': False,
        }
        for i in range(7)
    ]
    store = _seed_and_intake(monkeypatch, rows)

    def word(value):
        return live_texts[value] if value < 7 else f'new-word-{value}'

    state = _wire_incident(pipeline, monkeypatch, tmp_path, rows=rows, word=word)
    from utils.sync import assignment

    covered_calls = []
    real_covered = assignment.capture_covered_indices

    def covered_spy(incoming_segments, incoming_evidence, live_evidence):
        covered_calls.append((incoming_segments, incoming_evidence, live_evidence))
        return real_covered(incoming_segments, incoming_evidence, live_evidence)

    monkeypatch.setattr(assignment, 'capture_covered_indices', covered_spy)
    await _run_incident(pipeline, tmp_path)
    assert covered_calls
    for _, incoming_evidence, live_evidence in covered_calls:
        assert incoming_evidence['origin'] == 'sync_vad'
        assert incoming_evidence['capability'] == 'source_position'
        assert len(incoming_evidence['receipts']) == 10
        assert all(r['source_start_frame'] >= 40 for r in incoming_evidence['receipts'])
        assert live_evidence == merged_evidence
    texts = _texts(store, 'GEN-MERGED')
    for i in range(7):
        assert texts.count(live_texts[i]) == 2
    for i in range(7, 10):
        assert texts.count(f'new-word-{i}') == 1
    assert state.finish.call_args.args[1]['id'] == 'GEN-MERGED'
    assert state.outcomes[-1].value == 'success'


@pytest.mark.asyncio
async def test_adjoining_only_proof_never_suppresses_identical_unreceived_speech(real_pipeline, monkeypatch, tmp_path):
    """The same incident with an adjoining (not covering) run: identical-looking
    words carry no positive frame coverage, so every repeat is still appended."""
    pipeline = real_pipeline
    wal_pipeline_harness._coverage_env(monkeypatch, coverage_flag='off')
    monkeypatch.setenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, 'true')
    monkeypatch.delenv('SYNC_LINEAGE_S1_REQUIRED', raising=False)
    live_texts = [f'the quarterly planning review covered agenda item {v} in detail' for v in range(10)]
    rows = _incident_rows(merged_evidence=_merged_evidence(20, 40, WAL_TS - 10.0))
    merged = next(row for row in rows if row['id'] == 'GEN-MERGED')
    merged['transcript_segments'] = [
        {
            'start': 1730.0 + i * 0.5,
            'end': 1730.0 + i * 0.5 + 0.5,
            'text': live_texts[i],
            'speaker_id': 0,
            'is_user': False,
        }
        for i in range(10)
    ]
    store = _seed_and_intake(monkeypatch, rows)
    state = _wire_incident(pipeline, monkeypatch, tmp_path, rows=rows, word=lambda v: live_texts[v])
    await _run_incident(pipeline, tmp_path)
    texts = _texts(store, 'GEN-MERGED')
    for i in range(10):
        assert texts.count(live_texts[i]) == 2
    assert state.finish.call_args.args[1]['id'] == 'GEN-MERGED'
    assert state.outcomes[-1].value == 'success'


@pytest.mark.asyncio
async def test_default_s1_admission_without_claims_keeps_whole_batch_resolution(real_pipeline, monkeypatch, tmp_path):
    """Default SYNC_LINEAGE_S1_REQUIRED refuses an upload with no claims before
    per-segment planning — the whole-batch resolver runs and no frame planner,
    projection or pending token appears."""
    pipeline = real_pipeline
    wal_pipeline_harness._coverage_env(monkeypatch)
    monkeypatch.setenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, 'true')
    monkeypatch.delenv('SYNC_LINEAGE_S1_REQUIRED', raising=False)
    rows = _incident_rows(merged_evidence=_merged_evidence(20, 40, WAL_TS - 10.0))
    store = _seed_and_intake(monkeypatch, rows)
    state = _wire_incident(pipeline, monkeypatch, tmp_path, rows=rows)
    whole_batch = AsyncMock(return_value='GEN-BACK')
    monkeypatch.setattr(pipeline, '_resolve_safety_wal_target', whole_batch)
    await _run_incident(pipeline, tmp_path, claims=None)
    assert whole_batch.await_count == 1
    assert state.plan_results == []
    assert state.projection_calls == [] or all(flag is not True for flag in state.projection_calls)
    texts = _texts(store, 'GEN-BACK')
    for i in range(10):
        assert texts.count(f'new-word-{i}') == 1
    assert all(not text.startswith('new-word-') for text in _texts(store, 'GEN-MERGED'))
    assert state.outcomes[-1].value == 'success'


@pytest.mark.asyncio
async def test_s1_gate_off_without_maps_leaves_two_visible_rows_pending(real_pipeline, monkeypatch, tmp_path):
    """SYNC_LINEAGE_S1_REQUIRED=off admits the claimless upload to per-segment
    binding, but with no decoded maps the two visible rows stay pending before
    STT and no new words are saved."""
    pipeline = real_pipeline
    wal_pipeline_harness._coverage_env(monkeypatch)
    monkeypatch.setenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, 'true')
    monkeypatch.setenv('SYNC_LINEAGE_S1_REQUIRED', 'off')
    rows = _incident_rows(merged_evidence=_merged_evidence(20, 40, WAL_TS - 10.0))
    store = _seed_and_intake(monkeypatch, rows)
    state = _wire_incident(pipeline, monkeypatch, tmp_path, rows=rows)
    await _run_incident(pipeline, tmp_path, claims=None)
    assert state.plan_results
    assert all(set(targets.values()) == {None} for targets, _maps in state.plan_results)
    assert all(not maps for _targets, maps in state.plan_results)
    assert state.prerecorded_calls == []
    assert _texts(store, 'GEN-MERGED') == ['merged live speech']
    assert _texts(store, 'GEN-BACK') == ['backdated live speech']


@pytest.mark.asyncio
async def test_compatible_visible_stamp_binds_ahead_of_frame_evidence(real_pipeline, monkeypatch, tmp_path):
    """A phone stamp naming the visible competitor still decides first: the
    segment binds GEN-BACK even though the committed run adjoins GEN-MERGED."""
    pipeline = real_pipeline
    wal_pipeline_harness._coverage_env(monkeypatch)
    monkeypatch.setenv(SYNC_LINEAGE_LIVE_DEDUPE_ENV, 'true')
    monkeypatch.delenv('SYNC_LINEAGE_S1_REQUIRED', raising=False)
    rows = _incident_rows(merged_evidence=_merged_evidence(20, 40, WAL_TS - 10.0))
    store = _seed_and_intake(monkeypatch, rows)
    state = _wire_incident(pipeline, monkeypatch, tmp_path, rows=rows)
    await _run_incident(pipeline, tmp_path, target='GEN-BACK')
    texts = _texts(store, 'GEN-BACK')
    assert 'backdated live speech' in texts
    for i in range(10):
        assert texts.count(f'new-word-{i}') == 1
    assert all(not text.startswith('new-word-') for text in _texts(store, 'GEN-MERGED'))
    assert state.finish.call_args.args[1]['id'] == 'GEN-BACK'
    assert state.outcomes[-1].value == 'success'
