"""S1 source-position matrix through listen controls, framed sync decode and VAD."""

import json
import struct
import wave
from pathlib import Path

import pytest

from utils.capture_evidence import (
    CaptureRoot,
    DeliveryVerdict,
    EvidenceUnit,
    SourcePositionMap,
    Span,
    Surface,
    Track,
    classify_delivery,
    coverage_union,
    digest,
    decoded_frame_map,
    merge_track_receipts,
    parse_live_frame,
    parse_sync_file_claims,
    source_coordinate,
    sync_segment_receipt,
)
from utils.sync.files import decode_files_to_wav
from utils.sync import pipeline

ROOT = '12345678-1234-4234-8234-123456789abc'
NAME = 'audio_phonemic_pcm16_16000_1_fs160_1710000000.bin'


def _claim(count=200, *, epoch=0, start=0, rate=16000):
    return {
        'name': NAME,
        'capture_root': ROOT,
        'clock_epoch': epoch,
        'source_frame_start': start,
        'frame_count': count,
        'rate_hz': rate,
        'codec': 'pcm16',
        'channel': 'mono',
    }


def _decode(tmp_path: Path, count=200, *, claimed=None, truncate=False):
    source = tmp_path / NAME
    frames = [bytes([i % 256, 0]) * 160 for i in range(count)]
    with source.open('wb') as stream:
        for frame in frames:
            stream.write(struct.pack('<I', len(frame)))
            stream.write(frame)
        if truncate:
            stream.write(struct.pack('<I', 320))
            stream.write(b'broken')
    wire = json.dumps({'version': 1, 'files': [claimed or _claim(count)]})
    claims = parse_sync_file_claims(wire, [NAME])
    samples = {}
    wav_path = decode_files_to_wav([str(source)], samples)[0]
    with wave.open(wav_path, 'rb') as wav:
        mapped = decoded_frame_map(
            claims[NAME], samples[wav_path], wav_rate_hz=wav.getframerate(), wav_channels=wav.getnchannels()
        )
    return frames, mapped, wav_path


def test_live_and_wal_different_batching_vad_and_retranscription(tmp_path, monkeypatch):
    frames, source_map, wav_path = _decode(tmp_path)
    assert source_map is not None
    live = SourcePositionMap()
    # One websocket packet per original frame; the WAL transports 200 in one file.
    for i, frame in enumerate(frames):
        control = {'version': 1, 'capture_root': ROOT, 'clock_epoch': 0, 'source_frame': i, 'byte_length': len(frame)}
        live.accept(
            parse_live_frame(control, len(frame)), sample_start=i * 160, sample_count=160, rate_hz=16000, payload=frame
        )
    assert live.snapshot()['runs'][0]['source_frame_end'] == 200
    assert source_coordinate(source_map, 32000) == (200, 0)
    assert live.snapshot()['coverage'] == 'mapped'
    track = Track(CaptureRoot('account-a', ROOT, Surface('phone-mic', 'install-1')), 'mono', '0', 16000, 'source_pcm')
    units = [
        EvidenceUnit(track, f'frame-{i}', 'audio', 'v1', Span(i * 160, (i + 1) * 160), digest(frame))
        for i, frame in enumerate(frames)
    ]
    assert coverage_union(unit.source_span for unit in units) == (Span(0, 32000),)
    assert classify_delivery(units[17], units)[0] == DeliveryVerdict.replay
    changed = EvidenceUnit(track, 'frame-17', 'audio', 'v1', units[17].source_span, digest(b'changed'))
    assert classify_delivery(changed, units)[0] == DeliveryVerdict.conflict

    monkeypatch.setattr(pipeline, 'vad_is_empty', lambda *_args, **_kwargs: [{'start': 0.2, 'end': 1.2}])
    derivatives = set()
    derivative_maps = {}
    pipeline.retrieve_vad_segments(wav_path, derivatives, [], source_map, derivative_maps)
    assert len(derivatives) == 1
    derivative = next(iter(derivatives))
    mapping, offset = derivative_maps[derivative]
    assert offset == 3200
    first = sync_segment_receipt(
        mapping, wav_sample_start=offset + 1600, wav_sample_end=offset + 8000, segment_id='transcript-v1'
    )
    revised = sync_segment_receipt(
        mapping, wav_sample_start=offset + 1600, wav_sample_end=offset + 8000, segment_id='transcript-v2'
    )
    assert (first['source_start_frame'], first['source_end_frame']) == (30, 70)
    assert revised['source_start_frame'] == first['source_start_frame']
    combined = merge_track_receipts([first], [revised])
    assert combined['coverage'] == 'mapped' and len(combined['receipts']) == 2


def test_truncated_tail_preserves_prefix_and_marks_incomplete(tmp_path):
    _, mapped, _ = _decode(tmp_path, count=8, claimed=_claim(10), truncate=True)
    assert mapped is not None and mapped['incomplete'] is True
    assert source_coordinate(mapped, 8 * 160) == (8, 0)
    assert source_coordinate(mapped, 9 * 160) is None


def test_restart_replay_conflict_reset_and_clock_jump():
    frame = bytes([1, 2]) * 160
    claim = {'version': 1, 'capture_root': ROOT, 'clock_epoch': 0, 'source_frame': 7, 'byte_length': len(frame)}
    before, after = SourcePositionMap(), SourcePositionMap()
    for mapper in (before, after):
        mapper.accept(
            parse_live_frame(claim, len(frame)), sample_start=0, sample_count=160, rate_hz=16000, payload=frame
        )
    assert before.snapshot()['runs'][0]['source_frame_start'] == after.snapshot()['runs'][0]['source_frame_start']
    after.accept(parse_live_frame(claim, len(frame)), sample_start=160, sample_count=160, rate_hz=16000, payload=frame)
    assert after.snapshot()['coverage'] == 'mapped'
    assert after.snapshot()['runs'][-1]['replay'] is True
    after.accept(
        parse_live_frame(claim, len(frame)), sample_start=320, sample_count=160, rate_hz=16000, payload=b'changed'
    )
    assert after.snapshot()['conflicts'] == 1
    assert after.snapshot()['coverage'] == 'incomplete'
    reset = {**claim, 'clock_epoch': 1, 'source_frame': 0}
    after.accept(parse_live_frame(reset, len(frame)), sample_start=480, sample_count=160, rate_hz=16000, payload=frame)
    assert after.snapshot()['runs'][-1]['clock_epoch'] == 1
    # No wall clock participates in the wire key.
    assert 'wall_time' not in claim


def test_live_conversation_roll_slices_only_owned_source_frames():
    mapper = SourcePositionMap()
    frame = b'\x01\x00' * 160
    for ordinal in range(4):
        mapper.accept(
            {'capture_root': ROOT, 'clock_epoch': 0, 'source_frame': ordinal},
            sample_start=ordinal * 160,
            sample_count=160,
            rate_hz=16000,
            payload=frame,
        )
    first = mapper.snapshot([(0, 320)])
    second = mapper.snapshot([(320, 640)])
    assert first['runs'][0]['source_frame_start'] == 0
    assert first['runs'][0]['source_frame_end'] == 2
    assert second['runs'][0]['source_frame_start'] == 2
    assert second['runs'][0]['source_frame_end'] == 4


def test_rate_account_and_stereo_are_not_admitted_as_exact_mono(tmp_path):
    _, mapped, _ = _decode(tmp_path, count=2, claimed=_claim(2, rate=48000))
    assert mapped is None
    assert decoded_frame_map(_claim(2), [160, 160], wav_rate_hz=16000, wav_channels=2) is None
    assert parse_sync_file_claims(json.dumps({'version': 1, 'files': [_claim(2)]}), [NAME, 'other.bin']) == {}
    assert (
        parse_live_frame(
            {'version': 1, 'capture_root': 'foreign', 'clock_epoch': 0, 'source_frame': 0, 'byte_length': 320}, 320
        )
        is None
    )
    original = EvidenceUnit(
        Track(CaptureRoot('account-a', ROOT, Surface('phone-mic', 'install-1')), 'mono', '0', 16000, 'source_pcm'),
        'frame-0',
        'audio',
        'v1',
        Span(0, 160),
        digest(b'frame'),
    )
    switched = EvidenceUnit(
        Track(CaptureRoot('account-b', ROOT, Surface('phone-mic', 'install-1')), 'mono', '0', 16000, 'source_pcm'),
        'frame-0',
        'audio',
        'v1',
        Span(0, 160),
        digest(b'frame'),
    )
    assert classify_delivery(switched, [original])[0] == DeliveryVerdict.novel
    assert (
        parse_live_frame(
            {'version': True, 'capture_root': ROOT, 'clock_epoch': 0, 'source_frame': 0, 'byte_length': 320}, 320
        )
        is None
    )
    assert parse_sync_file_claims(json.dumps({'version': True, 'files': [_claim(2)]}), [NAME]) == {}


def test_bounded_receipt_overflow_and_changed_assignment_are_explicit():
    receipt = sync_segment_receipt(
        decoded_frame_map(_claim(1), [160], wav_rate_hz=16000, wav_channels=1),
        wav_sample_start=0,
        wav_sample_end=160,
        segment_id='same',
    )
    conflicting = {**receipt, 'source_end_offset': 10}
    assert merge_track_receipts([receipt], [conflicting])['capability'] == 'unknown'
    many = [{**receipt, 'segment_id': str(i)} for i in range(100)]
    assert merge_track_receipts([], many)['coverage'] == 'incomplete'


@pytest.mark.asyncio
async def test_listen_receiver_pairs_control_with_actual_binary_frame(monkeypatch):
    from tests.unit.test_listen_audio_timeline_stack import _Stack, _run_receiver_frames, _disconnect_frame

    monkeypatch.setenv('CAPTURE_EVIDENCE_V1_DARK_WRITE', 'true')
    stack = _Stack(monkeypatch, v2=False, conversation_id='capture-test')
    frame = b'\x01\x00' * 160
    control = {
        'type': 'capture_evidence_frame',
        'version': 1,
        'capture_root': ROOT,
        'clock_epoch': 0,
        'source_frame': 9,
        'byte_length': len(frame),
    }
    try:
        await _run_receiver_frames(stack, [{'text': json.dumps(control)}, {'bytes': frame}, _disconnect_frame()])
        snapshot = stack.host.state.source_position_map.snapshot()
        assert snapshot['capability'] == 'source_position'
        assert snapshot['runs'][0]['source_frame_start'] == 9
        assert snapshot['runs'][0]['decoded_sample_end'] == 160
    finally:
        stack.restore()
