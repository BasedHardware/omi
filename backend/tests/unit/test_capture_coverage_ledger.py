"""Synthetic frame-only custody regressions; no provider or production I/O."""

import asyncio
from dataclasses import replace
from uuid import UUID
import wave

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from config import refactor_modes
from database import capture_coverage as store
from models.capture_coverage import CaptureKey, CoverageRecord, FrameRange
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.capture import coverage, sync_coverage, batch_coverage


@pytest.fixture
def identity():
    return str(UUID(int=11)), CaptureKey(capture_root=str(UUID(int=12)), channel='mono', clock_epoch='0')


@pytest.fixture
def ledger(monkeypatch):
    client = StrictFirestore()
    monkeypatch.setattr(store, '_client', lambda: client)
    monkeypatch.setenv(coverage.FLAG, 'serve')
    return client


def rec(cid='committed', origin='live', *spans):
    return CoverageRecord(conversation_id=cid, origin=origin, ranges=[FrameRange(start=a, end=b) for a, b in spans])


def test_merge_and_idempotence(ledger, identity):
    uid, key = identity
    coverage.record(uid, key, rec('committed', 'live', (10, 20), (20, 30)))
    coverage.record(uid, key, rec('committed', 'live', (10, 25)))
    rows = store.read(uid, key)
    assert rows == [rec('committed', 'live', (10, 30))]
    assert len([tx for tx in ledger.transactions if tx.sets]) == 1


def test_overlap_subtraction_and_multiple_conversation_owners(ledger, identity):
    uid, key = identity
    coverage.record(uid, key, rec('first', 'live', (10, 20)))
    coverage.record(uid, key, rec('second', 'sync', (30, 40)))
    result = coverage.admit(uid, key, [FrameRange(start=0, end=50)], origin='sync')
    assert result.uncovered == [FrameRange(start=a, end=b) for a, b in [(0, 10), (20, 30), (40, 50)]]
    assert result.covered == [FrameRange(start=10, end=20), FrameRange(start=30, end=40)]
    assert result.covering_conversation_id is None


def test_retry_does_not_reorder_multiple_records(ledger, identity):
    uid, key = identity
    coverage.record(uid, key, rec('first', 'live', (10, 20)))
    coverage.record(uid, key, rec('second', 'sync', (30, 40)))
    before = sum(len(tx.sets) for tx in ledger.transactions)
    coverage.record(uid, key, rec('first', 'live', (10, 20)))
    assert sum(len(tx.sets) for tx in ledger.transactions) == before


@pytest.mark.parametrize(
    'field,value',
    [
        ('capture_root', str(UUID(int=99))),
        ('channel', 'other'),
        ('clock_epoch', '1'),
        ('device_id', 'other'),
        ('recording_session_id', 'other'),
    ],
)
def test_keys_and_users_are_isolated(ledger, identity, field, value):
    uid, key = identity
    span = FrameRange(start=0, end=10)
    coverage.record(uid, key, rec('committed', 'live', (0, 10)))
    assert not coverage.query(uid, key.model_copy(update={field: value}), [span]).covered
    assert not coverage.query(str(UUID(int=13)), key, [span]).covered


@pytest.mark.parametrize('spans', [[(3, 3)], [(4, 2)], [(0, 360001)], [(i * 2, i * 2 + 1) for i in range(33)]])
def test_bad_or_unbounded_query_rejected(identity, spans):
    uid, key = identity
    with pytest.raises(ValueError):
        coverage.query(uid, key, [FrameRange(start=a, end=b) for a, b in spans])


def test_store_bound_never_fills_a_gap(monkeypatch, identity):
    _, key = identity
    monkeypatch.setattr(store, 'MAX_INTERVALS', 1)
    with pytest.raises(ValueError, match='capacity'):
        store.merge_record({}, key, rec('committed', 'live', (0, 10), (20, 30)))


def test_off_does_no_storage(monkeypatch, identity):
    uid, key = identity
    monkeypatch.setenv(coverage.FLAG, 'off')
    monkeypatch.setattr(store, '_client', lambda: pytest.fail('off must not access storage'))
    coverage.record(uid, key, rec('committed', 'live', (0, 10)))
    assert coverage.query(uid, key, [FrameRange(start=0, end=10)]).basis == 'unknown'


def wav(tmp_path, frames=10):
    path = str(tmp_path / 'audio_pcm16_16000_1_1760000000.0.wav')
    with wave.open(path, 'wb') as stream:
        stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        stream.writeframes(bytes(frames * 320 * 2))
    return path


def mapping(key, frames=10):
    return {
        'claim': {
            'capture_root': key.capture_root,
            'channel': key.channel,
            'clock_epoch': 0,
            'source_frame_start': 0,
            'frame_count': frames,
            'rate_hz': 16000,
            'codec': 'pcm16',
        },
        'offsets': [i * 320 for i in range(frames + 1)],
        'incomplete': False,
    }


@pytest.mark.parametrize('mode,expected', [('serve', 0), ('shadow', 1), ('off', 1), ('typo', 1)])
def test_same_live_audio_then_wal_one_transcription_only_in_serve(
    ledger, identity, tmp_path, monkeypatch, mode, expected
):
    uid, key = identity
    path = wav(tmp_path)
    # This is the live-flush contract. The WAL adapter runs before any STT.
    coverage.record(uid, key, rec('committed', 'live', (0, 10)))
    monkeypatch.setenv(coverage.FLAG, mode)
    paths, maps, _ = sync_coverage.trim_maps(uid, [path], {path: mapping(key)})
    assert len(paths) == expected
    if expected:
        assert paths == [path] and maps[path] == mapping(key)


def test_partial_wal_materialization_does_not_concatenate_a_gap(ledger, identity, tmp_path):
    uid, key = identity
    path = wav(tmp_path)
    coverage.record(uid, key, rec('committed', 'live', (3, 7)))
    paths, maps, generated = sync_coverage.trim_maps(uid, [path], {path: mapping(key)})
    assert len(paths) == len(generated) == 2
    assert [(maps[p]['claim']['source_frame_start'], maps[p]['claim']['frame_count']) for p in paths] == [
        (0, 3),
        (7, 3),
    ]
    assert [wave.open(p).getnframes() for p in paths] == [960, 960]


def test_successful_sync_records_full_frames_only(ledger, identity, tmp_path):
    uid, key = identity
    path = wav(tmp_path, 5)
    receipt = {
        'segment_id': 'span',
        'source_start_frame': 0,
        'source_start_offset': 160,
        'source_end_frame': 5,
        'source_end_offset': 160,
    }
    incoming = {'capture_evidence': {'receipts': [receipt]}, 'transcript_segments': [{'id': 'span'}]}
    sync_coverage.record_sync(uid, incoming, {'id': 'committed'}, (mapping(key, 10), 160), path)
    assert store.read(uid, key)[0].ranges == [FrameRange(start=1, end=5)]
    sync_coverage.record_sync(uid, incoming, {'id': 'committed'}, (mapping(key, 10), 160), path, survivors=[])
    assert len(store.read(uid, key)) == 1


def test_storage_error_keeps_audio(identity, tmp_path, monkeypatch):
    uid, key = identity
    path = wav(tmp_path)
    monkeypatch.setattr(coverage, 'admit', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('synthetic')))
    assert sync_coverage.trim_maps(uid, [path], {path: mapping(key)})[0] == [path]


def test_batch_packing_proof_ignores_partial_frame_edges(identity):
    _, key = identity
    runs = batch_coverage.piece_runs(mapping(key), 160, 1280, 100, {})
    assert [(r['start'], r['end'], r['sample_start']) for r in runs] == [(1, 4, 260)]
    incoming = {
        'started_at': __import__('datetime').datetime.fromtimestamp(1000, __import__('datetime').timezone.utc),
        'transcript_segments': [{'start': 260 / 16000, 'end': 1220 / 16000}],
    }
    claims = batch_coverage.claims_for_segments(incoming, {'capture_coverage_runs': runs}, capture_at=1000)
    assert claims[0][1] == FrameRange(start=1, end=4)


def test_endpoint_is_authenticated_bounded_and_read_only(ledger, identity, monkeypatch):
    from utils.capture import coverage_endpoint as endpoint

    uid, key = identity
    coverage.record(uid, key, rec('committed', 'live', (0, 10)))
    calls = []
    monkeypatch.setattr(endpoint, '_limit', lambda subject: calls.append(subject))
    app = FastAPI()
    app.include_router(endpoint.router)
    app.dependency_overrides[endpoint.auth.get_current_user_uid] = lambda: uid
    client = TestClient(app)
    params = {'capture_root': key.capture_root, 'channel': 'mono', 'clock_epoch': '0', 'start': 0, 'end': 10}
    assert client.get('/v2/capture-coverage', params=params).json()['uncovered'] == []
    assert calls == [uid]
    assert client.get('/v2/capture-coverage', params={**params, 'end': 360001}).status_code == 422
    assert len(store.read(uid, key)) == 1


def test_endpoint_rate_limit_uses_authenticated_subject(monkeypatch, identity):
    from database import redis_db
    from utils.capture import coverage_endpoint as endpoint

    calls = []
    monkeypatch.setattr(redis_db, 'check_rate_limit', lambda *args: calls.append(args) or (False, 0, 5))
    with pytest.raises(Exception) as caught:
        endpoint._limit(identity[0])
    assert caught.value.status_code == 429
    assert calls == [(identity[0], 'capture_coverage:query', 60, 60)]


@pytest.mark.parametrize('mode,count', [('shadow', 1), ('serve', 0)])
def test_batch_projection_rechecks_coverage_and_keeps_shadow_output(ledger, identity, monkeypatch, mode, count):
    from datetime import datetime, timezone

    uid, key = identity
    coverage.record(uid, key, rec('committed', 'live', (0, 10)))
    monkeypatch.setenv(coverage.FLAG, mode)
    incoming = {
        'started_at': datetime.fromtimestamp(1760000000, timezone.utc),
        'capture_evidence': {'capability': 'unknown'},
        'transcript_segments': [{'id': 'positioned', 'start': 0.01, 'end': 0.19}],
    }
    runs = batch_coverage.piece_runs(mapping(key), 0, 3200, 0, {})
    batch_coverage.admit_projection(uid, incoming, {'capture_coverage_runs': runs}, capture_at=1760000000)
    assert len(incoming['transcript_segments']) == count
    if mode == 'shadow':
        assert incoming['capture_evidence'] == {'capability': 'unknown'}


def test_batch_partial_proof_keeps_segment(ledger, identity):
    from datetime import datetime, timezone

    uid, key = identity
    coverage.record(uid, key, rec('committed', 'live', (1, 9)))
    incoming = {
        'started_at': datetime.fromtimestamp(1760000000, timezone.utc),
        'transcript_segments': [{'id': 'positioned', 'start': 0.01, 'end': 0.19}],
    }
    runs = batch_coverage.piece_runs(mapping(key), 0, 3200, 0, {})
    batch_coverage.admit_projection(uid, incoming, {'capture_coverage_runs': runs}, capture_at=1760000000)
    assert len(incoming['transcript_segments']) == 1
    assert incoming['capture_evidence']['receipts'][0]['source_start_offset'] == 160


@pytest.mark.parametrize('mode,count', [('shadow', 1), ('serve', 0)])
def test_batch_decode_same_audio_uses_source_frames(ledger, identity, tmp_path, monkeypatch, mode, count):
    import struct
    from utils.batch_pipeline.capture_decode import decode_units

    uid, key = identity
    path = tmp_path / 'audio_omi_pcm16_16000_1760000000.bin'
    payload = bytes(640)
    path.write_bytes(b''.join(struct.pack('<I', len(payload)) + payload for _ in range(10)))
    claim = mapping(key)['claim']
    context = {'capture_evidence_claims': {path.name: claim}, 'uid': uid}
    coverage.record(uid, key, rec('committed', 'live', (0, 10)))
    monkeypatch.setenv(coverage.FLAG, mode)
    units = list(decode_units([str(path)], coverage_context=context))
    assert len(units) == count
    if units:
        assert units[0].coverage_runs[0]['start'] == 0
        assert units[0].coverage_runs[0]['end'] == 10
        assert units[0].duration_seconds == 0.2


def test_batch_record_uses_only_assignment_survivors(ledger, identity):
    from datetime import datetime, timezone

    uid, key = identity
    segment = {'id': 'positioned', 'start': 0, 'end': 0.2}
    incoming = {'started_at': datetime.fromtimestamp(1760000000, timezone.utc), 'transcript_segments': [segment]}
    runs = batch_coverage.piece_runs(mapping(key), 0, 3200, 0, {})
    manifest = {'capture_coverage_runs': runs}
    batch_coverage.record_projection(uid, incoming, {'id': 'committed'}, manifest, capture_at=1760000000, survivors=[])
    assert not store.read(uid, key)
    batch_coverage.record_projection(
        uid, incoming, {'id': 'committed'}, manifest, capture_at=1760000000, survivors=[segment]
    )
    assert store.read(uid, key) == [rec('committed', 'batch', (0, 10))]


def test_ledger_target_is_only_a_serve_binding_hint(ledger, identity, tmp_path, monkeypatch):
    uid, key = identity
    coverage.record(uid, key, rec('committed', 'live', (0, 3)))
    path = wav(tmp_path)
    assert sync_coverage.covering_target(uid, (mapping(key), 0), path) == 'committed'
    monkeypatch.setenv(coverage.FLAG, 'shadow')
    assert sync_coverage.covering_target(uid, (mapping(key), 0), path) is None


@pytest.mark.parametrize('mode,expected', [('shadow', 1), ('serve', 0)])
def test_cap_held_segment_rechecks_before_paid_recovery(ledger, identity, tmp_path, monkeypatch, mode, expected):
    uid, key = identity
    coverage.record(uid, key, rec('committed', 'live', (0, 10)))
    path = wav(tmp_path)
    monkeypatch.setenv(coverage.FLAG, mode)
    paths, _, _, _ = sync_coverage.held_segment(uid, path, {'source_position_map': [mapping(key), 0]})
    assert len(paths) == expected


def test_provider_manifest_does_not_change_shadow_targeting(identity, monkeypatch):
    from datetime import datetime, timezone
    from unittest.mock import Mock
    from utils.batch_pipeline import projection, context, audio
    from utils.batch_pipeline.contracts import WorkItem, ProjectionBinding, Priority
    from config.policy import ProjectionPolicy

    uid, _ = identity
    monkeypatch.setenv(coverage.FLAG, 'shadow')
    item = WorkItem('piece', uid, 1760000000, 'gs://synthetic/audio', 1, Priority.DEEP)
    binding = ProjectionBinding(uid, 'job', 'content', ('piece',))
    payload = {
        'words': [{'word': str(UUID(int=90)), 'timestamp': [0, 1]}],
        'audio_seconds': 1,
        'speech_seconds': 1,
        'diarization': {'turns': []},
    }
    frozen = audio.with_context(audio.audio_unit(item.capture_at, bytes(32000)).wav, {'capture_coverage_runs': []})
    projector = projection.Projector(Mock(), Mock(return_value=payload), fetch_audio=lambda _: frozen)
    projector.store = Mock()
    incoming = {
        'started_at': datetime.fromtimestamp(item.capture_at, timezone.utc),
        'finished_at': datetime.fromtimestamp(item.capture_at + 1, timezone.utc),
        'transcript_segments': [{'id': 'segment', 'speaker_id_scope': 'scope', 'start': 0, 'end': 1}],
    }
    monkeypatch.setattr(projection, 'build_incoming', lambda *a, **k: incoming)
    monkeypatch.setattr(
        context, 'resolve_context', lambda *a, **k: pytest.fail('provider shadow must keep legacy targeting')
    )
    monkeypatch.setattr(projection.conversations_db, 'get_closest_conversation_to_timestamps', lambda *a: None)

    def commit(*args, after_assign, **kwargs):
        result = ({'id': 'committed'}, False, [])
        after_assign(None, result)
        return result

    monkeypatch.setattr(projection.conversations_db, 'assign_sync_conversation', commit)
    projector.assign_parts(
        item, {'result': {'result_uri': 'fixture'}}, binding, finish=False, policy=ProjectionPolicy()
    )
    projector.store.session.return_value.persist.assert_called_once()


@pytest.mark.parametrize('mode', ['off', 'shadow', 'serve', 'invalid'])
def test_optional_sync_identity_preserves_unpositioned_legacy_payload(monkeypatch, mode):
    monkeypatch.setenv(coverage.FLAG, mode)
    incoming = {'id': 'unpositioned'}
    sync_coverage.annotate_identity(incoming)
    assert incoming == {'id': 'unpositioned'}
    positioned = {'capture_evidence': {'capability': 'source_position'}}
    sync_coverage.annotate_identity(positioned)
    assert positioned == {'capture_evidence': {'capability': 'source_position'}}
