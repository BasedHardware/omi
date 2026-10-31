"""Approved seal rules exercise the real proof, manifest reader and row CAS."""

from datetime import datetime, timezone
import io
import json
from types import SimpleNamespace
import wave

import pytest

from database.record_audio import mark_record_upload_failed, seal_record_audio
from utils.batch_pipeline import live, record_seal_repair as repair
from utils.batch_pipeline.record_barrier import validate_record_tail
from utils.batch_pipeline.source_audio import MAGIC, materialize
from tests.unit.test_record_seal_repair import source, PATH


def overlap_source(monkeypatch, starts=(100, 159), lengths=(60, 60)):
    chunks = [
        {'path': f'chunks/synthetic/capture/{i}.pcm', 'generation': 1, 'timestamp': start}
        for i, start in enumerate(starts)
    ]
    sources = {
        chunk['path']: bytes([i + 1, 0]) * (seconds * 16000) for i, (chunk, seconds) in enumerate(zip(chunks, lengths))
    }
    monkeypatch.setattr(live, 'read_reference', lambda client, ref, *a, **kw: sources[ref['path']])
    return chunks, sources


def test_divergent_partial_overlap_proof_and_reader_agree(monkeypatch):
    chunks, sources = overlap_source(monkeypatch)
    diagnostics = {}
    units = list(live.retained_record_units('synthetic', 'capture', chunks, None, b'', diagnostics=diagnostics))
    assert len(units) == 1
    start, duration, refs = units[0]
    assert (start, duration) == (100, 119)
    assert [(r['start_frame'], r['offset_frame'], r['frames']) for r in refs] == [
        (0, 0, 60 * 16000),
        (60 * 16000, 16000, 59 * 16000),
    ]
    item = SimpleNamespace(owner_id='synthetic', conversation_id='capture', capture_at=start, duration_seconds=duration)
    body = (
        MAGIC
        + json.dumps(
            {
                'owner_id': item.owner_id,
                'conversation_id': item.conversation_id,
                'capture_at': start,
                'references': refs,
                'context': {},
            }
        ).encode()
    )
    wav = materialize(body, item, lambda ref: sources[ref['path']])
    with wave.open(io.BytesIO(wav), 'rb') as stream:
        assert stream.readframes(stream.getnframes()) == sources[chunks[0]['path']] + sources[chunks[1]['path']][32000:]
    assert diagnostics == {'trimmed_divergent_overlaps': 1}
    validate_record_tail(units, datetime.fromtimestamp(219, timezone.utc), require_finish=True)
    with pytest.raises(ValueError, match='tail not durable'):
        validate_record_tail(units, datetime.fromtimestamp(220, timezone.utc), require_finish=True)
    # The actual repair proof consumes the identical walk and validates both
    # current and frozen finishes before granting eligibility.
    monkeypatch.setattr(repair, 'list_audio_chunks', lambda *a, **kw: chunks)
    artifacts = SimpleNamespace(authorize=lambda _: None, key_for_owner=lambda _: b'')
    row = {'finished_at': datetime.fromtimestamp(219, timezone.utc)}
    job = {
        'owner_id': 'synthetic',
        'conversation_id': 'capture',
        'segment_id': 'pending',
        'privacy_generation': 0,
        'record_snapshot': row,
    }
    proof_counts = {}
    assert repair.retained_tail_proof(job, row, None, artifacts, diagnostics=proof_counts) == repair.plan_digest(units)
    assert proof_counts == diagnostics


def test_wholly_covered_divergent_object_keeps_union_end_and_precheck_defers(monkeypatch):
    chunks, _ = overlap_source(monkeypatch, starts=(100, 159), lengths=(60, 0))
    # A shorter final object ends BEFORE the earlier object's union end.
    monkeypatch.setattr(
        live,
        'read_reference',
        lambda client, ref, *a, **kw: b'\x01\x00' * 960000 if ref['path'].endswith('0.pcm') else b'\x02\x00' * 8000,
    )
    diagnostics = {}
    units = list(live.retained_record_units('synthetic', 'capture', chunks, None, b'', diagnostics=diagnostics))
    assert units[0][:2] == (100, 60)
    assert len(units[0][2]) == 1
    row = {'finished_at': datetime.fromtimestamp(160, timezone.utc)}
    repair.precheck_record_tail('synthetic', 'capture', chunks, None, b'', row, {'record_snapshot': row})
    validate_record_tail(units, row['finished_at'], require_finish=True)
    assert diagnostics == {'trimmed_divergent_overlaps': 1}


def test_inconsistent_timestamps_still_refuse(monkeypatch):
    chunks, _ = overlap_source(monkeypatch, starts=(100, 99), lengths=(1, 2))
    with pytest.raises(ValueError, match='conflicting retained audio overlap'):
        list(live.retained_record_units('synthetic', 'capture', chunks, None, b''))


@pytest.mark.parametrize('contained', [False, True])
def test_chained_overlap_keeps_full_previous_extent_and_earlier_bytes(monkeypatch, contained):
    chunks, sources = overlap_source(monkeypatch, starts=(100, 100 + 2 / 16000, 100 + 3 / 16000), lengths=(1, 1, 1))
    sources[chunks[0]['path']] = b'\x01\x00' * 4
    sources[chunks[1]['path']] = b'\x02\x00' * 3
    # Its overlap matches B's original bytes, but the first of those frames
    # belongs to A. The diagnostic must compare against accepted bytes too.
    sources[chunks[2]['path']] = b'\x02\x00' * 2 + b'\x03\x00'
    if contained:
        chunks.insert(
            2, {'path': 'chunks/synthetic/capture/contained.pcm', 'generation': 1, 'timestamp': 100 + 2 / 16000}
        )
        sources[chunks[2]['path']] = b'\x04\x00' * 2
    diagnostics = {}
    units = list(live.retained_record_units('synthetic', 'capture', chunks, None, b'', diagnostics=diagnostics))
    start, duration, refs = units[0]
    assert [(r['start_frame'], r['offset_frame'], r['frames']) for r in refs] == [(0, 0, 4), (4, 2, 1), (5, 2, 1)]
    item = SimpleNamespace(owner_id='synthetic', conversation_id='capture', capture_at=start, duration_seconds=duration)
    body = (
        MAGIC
        + json.dumps(
            {
                'owner_id': item.owner_id,
                'conversation_id': item.conversation_id,
                'capture_at': start,
                'references': refs,
                'context': {},
            }
        ).encode()
    )
    wav = materialize(body, item, lambda ref: sources[ref['path']])
    with wave.open(io.BytesIO(wav), 'rb') as stream:
        assert stream.readframes(stream.getnframes()) == b'\x01\x00' * 4 + b'\x02\x00' + b'\x03\x00'
    assert diagnostics == {'trimmed_divergent_overlaps': 3 if contained else 2}


def test_overlap_switch_off_restores_refusal(monkeypatch):
    monkeypatch.setenv('RECORD_SEAL_OVERLAP_TRIM_ENABLED', 'false')
    chunks, _ = overlap_source(monkeypatch)
    with pytest.raises(ValueError, match='conflicting retained audio overlap'):
        list(live.retained_record_units('synthetic', 'capture', chunks, None, b''))


def test_one_frame_divergent_overlap_is_trimmed_for_reader_agreement(monkeypatch):
    chunks, _ = overlap_source(monkeypatch, starts=(100, 101 - 1 / 16000), lengths=(1, 1))
    units = list(live.retained_record_units('synthetic', 'capture', chunks, None, b''))
    _, duration, refs = units[0]
    assert duration == pytest.approx(2 - 1 / 16000)
    assert refs[1]['start_frame'] == 16000
    assert refs[1]['offset_frame'] == 1
    assert refs[1]['frames'] == 15999


@pytest.mark.parametrize('start_frame', [0.4999, 0.5, 0.5001, 1.4999, 1.5, 1.5001])
def test_half_frame_quantization_uses_same_boundary_for_proof_and_reader(monkeypatch, start_frame):
    chunks, sources = overlap_source(monkeypatch, starts=(100, 100 + start_frame / 16000), lengths=(1, 1))
    # Small real sources make the banker's-rounding boundary explicit.
    sources[chunks[0]['path']] = b'\x01\x00'
    sources[chunks[1]['path']] = b'\x02\x00' * 3
    units = list(live.retained_record_units('synthetic', 'capture', chunks, None, b''))
    start, duration, refs = units[0]
    item = SimpleNamespace(owner_id='synthetic', conversation_id='capture', capture_at=start, duration_seconds=duration)
    body = (
        MAGIC
        + json.dumps(
            {
                'owner_id': item.owner_id,
                'conversation_id': item.conversation_id,
                'capture_at': start,
                'references': refs,
                'context': {},
            }
        ).encode()
    )
    wav = materialize(body, item, lambda ref: sources[ref['path']])
    with wave.open(io.BytesIO(wav), 'rb') as stream:
        frames = stream.readframes(stream.getnframes())
    assert frames[:2] == b'\x01\x00'
    assert refs[1]['start_frame'] >= refs[0]['frames']


def failed_plan(source):
    store, client, artifacts = source
    client.rows[PATH]['record_upload_failed'] = True
    return repair.plan_seals(store, ['pending'], None, artifacts, repair_upload_failed=True)


def test_upload_failed_clear_requires_explicit_repair_and_full_proof(source):
    store, client, artifacts = source
    plan = failed_plan(source)
    assert plan['entries'][0]['disposition'] == 'eligible'
    assert repair.plan_seals(store, ['pending'], None, artifacts)['entries'][0]['disposition'] == 'upload_failed'
    assert seal_record_audio('synthetic', 'record', firestore_client=client) == 'upload_failed'
    assert repair.apply_seals(store, plan, plan['plan_sha256']) == {'upload_failed_cleared': 1}
    assert client.rows[PATH]['record_audio_closed']
    assert client.rows[PATH]['record_upload_failed'] is False
    assert client.transactions[-1].updates == [(PATH, {'record_audio_closed': True, 'record_upload_failed': False})]


@pytest.mark.parametrize(
    'change',
    [
        {'finished_at': datetime.fromtimestamp(103, timezone.utc)},
        {'finished_at': None},
        {'record_upload_sessions': {'unproven': True}},
        {'private_cloud_sync_enabled': False},
    ],
)
def test_failed_full_proof_keeps_failure_flag(source, change):
    store, client, _ = source
    client.rows[PATH].update(change)
    plan = failed_plan(source)
    assert plan['entries'][0]['disposition'] != 'eligible'
    repair.apply_seals(store, plan, plan['plan_sha256'])
    assert client.rows[PATH]['record_upload_failed']
    assert not client.rows[PATH].get('record_audio_closed')
    assert all(not tx.updates for tx in client.transactions)


def test_fresh_repeated_failure_after_plan_is_fenced(source):
    store, client, _ = source
    plan = failed_plan(source)
    for revision in (1, 2):
        assert mark_record_upload_failed('synthetic', 'record', firestore_client=client)
        assert client.rows[PATH]['record_upload_revision'] == revision
    assert repair.apply_seals(store, plan, plan['plan_sha256']) == {'state_changed': 1}
    assert client.rows[PATH]['record_upload_failed']
    assert not client.rows[PATH]['record_audio_closed']


def test_upload_failed_switch_off_at_plan_or_apply_restores_refusal(source, monkeypatch):
    store, client, _ = source
    approved = failed_plan(source)
    monkeypatch.setenv('RECORD_SEAL_UPLOAD_FAILED_REPAIR_ENABLED', 'false')
    assert failed_plan(source)['entries'][0]['disposition'] == 'upload_failed'
    assert repair.apply_seals(store, approved, approved['plan_sha256']) == {'upload_failed': 1}
    assert client.rows[PATH]['record_upload_failed']
    assert all(not tx.updates for tx in client.transactions)


def test_overlap_switch_off_invalidates_existing_plan(source, monkeypatch):
    store, _, artifacts = source
    plan = repair.plan_seals(store, ['pending'], None, artifacts)
    monkeypatch.setenv('RECORD_SEAL_OVERLAP_TRIM_ENABLED', 'false')
    assert repair.apply_seals(store, plan, plan['plan_sha256']) == {'state_changed': 1}
