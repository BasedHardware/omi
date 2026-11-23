from collections import Counter
import hashlib
import json
import struct
import time
from types import SimpleNamespace
from unittest.mock import Mock

from google.api_core.exceptions import AlreadyExists
import pytest

from config import record_wal_sample as config
from database import record_wal_sample as state
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from utils.batch_pipeline import record_wal_sample as sampler
from utils.batch_pipeline.artifact_reads import ArtifactReadBudget, ArtifactReadLimit
from utils.batch_pipeline.record_wal_alignment import CLOCK_RATE, Packet
from utils.other.raw_audio import WAL_FORMAT


def budget():
    return ArtifactReadBudget(time.monotonic() + 20, sampler.MAX_MANIFEST_TOTAL, 14)


def test_sample_enabled_for_exact_service_window(monkeypatch):
    start = 1_800_000_000
    monkeypatch.setenv('RECORD_WAL_SAMPLE_START_EPOCH', str(start))
    monkeypatch.setenv('K_SERVICE', 'backend-integration')
    assert config.slot_at(start) is None
    monkeypatch.setenv('K_SERVICE', 'backend-sync')
    assert config.slot_at(start - 1) is None
    assert config.slot_at(start) == config.slot_at(start + 179)
    assert config.slot_at(start + 180) == config.slot_at(start) + 1
    assert config.slot_at(start + 86_399) is None
    assert config.slot_at(start + 86_400) is None
    assert len({config.slot_at(now) for now in range(start, start + 86_400, 180)}) == 480
    monkeypatch.setenv('RECORD_WAL_SAMPLE_START_EPOCH', str(start + 1))
    assert config.slot_at(start + 1) is None


def test_point_read_budget_refuses_before_the_eleventh_read():
    reads = sampler.SampleReads(budget())
    for _ in range(10):
        assert reads.timeout(1) == 1
    with pytest.raises(ArtifactReadLimit):
        reads.timeout(1)
    assert reads.issued == 10


def test_slot_contenders_share_one_create_without_retry(monkeypatch):
    ref = Mock()
    ref.create.side_effect = [None, AlreadyExists('claimed')]
    intake_reference = Mock(return_value=ref)
    monkeypatch.setattr(state.FirestoreTransaction, 'intake_reference', intake_reference)
    store1 = SimpleNamespace(client=object(), namespace='prod')
    store2 = SimpleNamespace(client=object(), namespace='other-revision')
    assert state.claim_slot(store1, 44, budget())
    assert not state.claim_slot(store2, 44, budget())
    assert intake_reference.call_args_list[0].args[1:] == intake_reference.call_args_list[1].args[1:]
    assert all(call.kwargs == {'timeout': 0.25, 'retry': None} for call in ref.create.call_args_list)
    ref.get.assert_not_called()


def _pack(tmp_path):
    path = tmp_path / 'audio_device_opus_16000_1_fs320_1700000000.bin'
    payloads = [bytes((0xF8, index)) for index in range(10)]
    path.write_bytes(b''.join(struct.pack('<I', len(payload)) + payload for payload in payloads))
    return path


def test_counts_encoded_packet_matches_and_clock_without_releasing_custody(tmp_path):
    path = _pack(tmp_path)
    files = sampler.read_staged_packets([path], budget())
    _, size, wal = files[0]
    live = [Packet(p.digest, p.ticks, p.start + 2 * CLOCK_RATE, p.size) for p in wal]
    measured, offsets = sampler._count(files, [live], {}, False, budget())
    assert measured == {('duplicate', 'bytes'): size, ('duplicate', 'ticks'): 9600}
    assert offsets == {'250ms_to_5s': 1}
    # An equally plausible placement on another run invalidates the match.
    measured, offsets = sampler._count(files, [live, live], {}, False, budget())
    assert measured == {('ambiguous', 'bytes'): size, ('ambiguous', 'ticks'): 9600}
    assert not offsets


def test_bracketed_hole_remains_ambiguous_with_unverified_upload_ordinals(tmp_path):
    path = _pack(tmp_path)
    files = sampler.read_staged_packets([path], budget())
    _, _, wal = files[0]
    live = [
        Packet(p.digest, p.ticks, p.start, p.size, ('track', 0, index))
        for index, p in enumerate(wal)
        if index not in {4, 5}
    ]
    claims = {
        path.name: {
            'codec': 'opus',
            'frame_count': 10,
            'capture_root': 'track',
            'clock_epoch': 0,
            'source_frame_start': 0,
        }
    }
    counted, _ = sampler._count(files, [live], claims, True, budget())
    assert counted['ambiguous_bracketed', 'ticks'] == 1920
    assert ('gap', 'ticks') not in counted
    counted, _ = sampler._count(files, [live], claims, False, budget())
    assert not counted['ambiguous_bracketed', 'ticks']
    assert counted['ambiguous', 'ticks'] == 1920
    counted, _ = sampler._count(files, [live], {}, True, budget())
    assert not counted['ambiguous_bracketed', 'ticks']
    assert counted['ambiguous', 'ticks'] == 1920


def test_manifest_body_only_with_both_preconditions(monkeypatch):
    media = SimpleNamespace(
        name='raw-live/owner/record/pack/hash.bin',
        generation=123,
        size=6,
        metadata={
            'format': WAL_FORMAT,
            'codec': 'opus',
            'source_layout': 'mono',
            'conversation_id': 'record',
            'clock_source': 'server_projected',
            'consent_state': 'private_cloud_sync_enabled',
            'custody_schema': 'audio_custody_v1',
            'channels': '1',
            'sample_rate': '16000',
            'sha256': 'b' * 64,
            'encrypted': 'false',
        },
    )
    payload = json.dumps(
        {
            'schema': 'audio_custody_v1',
            'media': {'bucket': 'private', 'path': media.name, 'generation': '123', 'sha256': 'b' * 64},
            'capture': {'sample_rate': 16000, 'format': WAL_FORMAT, 'channels': 1},
            'frames': [
                {
                    'sequence': 0,
                    'byte_offset': 0,
                    'bytes': 6,
                    'start': 1_700_000_000,
                    'gap_before': False,
                    'samples': 320,
                    'sha256': 'a' * 64,
                }
            ],
        }
    ).encode()
    listed = SimpleNamespace(
        name='audio-outbox/owner/record/pack/hash.bin',
        size=len(payload),
        generation=456,
        metageneration=5,
        metadata={
            'format': 'audio-custody-manifest-v1',
            'conversation_id': 'record',
            'encrypted': 'false',
            'sha256': hashlib.sha256(payload).hexdigest(),
        },
    )
    blob = Mock()
    blob.download_as_bytes.return_value = payload
    bucket = SimpleNamespace(name='private', blob=Mock(return_value=blob))
    spent = budget()
    assert sampler._manifest(bucket, 'owner', 'record', media, listed, spent)[0].ticks == 960
    bucket.blob.assert_called_once_with(listed.name)
    assert blob.download_as_bytes.call_args.kwargs['if_generation_match'] == 456
    assert blob.download_as_bytes.call_args.kwargs['if_metageneration_match'] == 5
    assert blob.download_as_bytes.call_args.kwargs['retry'] is None
    assert blob.download_as_bytes.call_args.kwargs['raw_download'] is True
    assert spent.received_bytes == len(payload)
    media.generation += 1
    with pytest.raises(ValueError):
        sampler._manifest(bucket, 'owner', 'record', media, listed, spent)


def test_continuation_is_ambiguous_and_never_paginated():
    bucket = Mock()
    iterator = bucket.list_blobs.return_value
    iterator.pages = iter([[object()]])
    iterator.next_page_token = 'more-results'
    spent = budget()
    with pytest.raises(ArtifactReadLimit):
        sampler._page(bucket, 'bounded/', 6, spent)
    assert spent.objects == 1
    assert bucket.list_blobs.call_args.kwargs['retry'] is None


@pytest.mark.asyncio
async def test_privacy_race_drops_the_sample_before_any_measurement_publishes(monkeypatch, tmp_path):
    slot = 5001
    monkeypatch.setattr(sampler, 'slot_at', lambda now: slot)
    monkeypatch.setattr(sampler, '_latest_attempted', -1)
    monkeypatch.setattr(state, 'claim_slot', Mock(return_value=True))
    monkeypatch.setattr(
        state, 'authority', Mock(side_effect=[(1, {}), BatchPrivacyBlocked('privacy_generation_changed')])
    )
    monkeypatch.setattr(sampler, 'read_manifest_inventory', Mock(return_value=([], False)))
    counted = Mock(return_value=(Counter(), Counter()))
    monkeypatch.setattr(sampler, '_count', counted)
    attempts = Mock()
    monkeypatch.setattr(sampler, 'attempts', attempts)

    async def direct(executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(sampler, 'run_blocking', direct)
    content = next(
        str(i) for i in range(10000) if int(hashlib.sha256(str(i).encode()).hexdigest()[:12], 16) % 1000 == 0
    )
    await sampler.observe(
        store=object(),
        uid='owner',
        cid='record',
        source='device',
        device='model',
        paths=[str(_pack(tmp_path))],
        content_id=content,
        claims={},
        status_code=503,
        has_jobs=True,
    )
    counted.assert_not_called()
    attempts.labels.assert_any_call('authority_refused')
    assert state.authority.call_args.kwargs['expected_generation'] == 1


def test_alternate_chunks_suppress_gaps_without_discarding_positive_evidence(monkeypatch, tmp_path):
    path = _pack(tmp_path)
    files = sampler.read_staged_packets([path], budget())
    _, size, wal = files[0]
    media = SimpleNamespace(name='raw-live/owner/record/pack/hash.bin')
    listed = SimpleNamespace(name='audio-outbox/owner/record/pack/hash.bin')
    root = Mock()
    root.list_blobs.side_effect = [
        SimpleNamespace(pages=iter([[media]]), next_page_token=None),
        SimpleNamespace(pages=iter([[listed]]), next_page_token=None),
        SimpleNamespace(pages=iter([[object()]]), next_page_token='another-chunk'),
    ]
    monkeypatch.setattr(sampler, 'get_private_cloud_sync_bucket', lambda: root)
    monkeypatch.setattr(sampler, '_manifest', lambda *_: wal)
    inventory_budget = budget()
    runs, no_alternate = sampler.read_manifest_inventory('owner', 'record', True, inventory_budget)
    measured, _ = sampler._count(files, runs, {}, no_alternate, budget())
    assert not no_alternate
    assert measured['duplicate', 'bytes'] == size
    assert inventory_budget.objects == 3
    assert root.list_blobs.call_args.kwargs['page_size'] == 1


def test_staged_durations_come_from_headers_and_bad_sibling_keeps_its_byte_count(tmp_path):
    variable = _pack(tmp_path)
    short, nominal = bytes((0xF0, 1)), bytes((0xF8, 2))
    variable.write_bytes(struct.pack('<I', len(short)) + short + struct.pack('<I', len(nominal)) + nominal)
    bad = variable.with_name(variable.name.replace('1700000000', '1700000010'))
    bad.write_bytes(struct.pack('<I', 100) + short)
    files = sampler.read_staged_packets([str(variable), str(bad)], budget())
    measured, _ = sampler._count(files, [], {}, False, budget())
    assert measured['ambiguous', 'ticks'] == 480 + 960
    assert measured['ambiguous', 'bytes'] == variable.stat().st_size + bad.stat().st_size
    assert measured['ambiguous', 'unknown_duration_files'] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(('status', 'dispatch'), [(503, 'refused'), (200, 'accepted'), (202, 'accepted')])
async def test_observe_publishes_counted_duplicate_bytes_under_the_existing_reply(
    monkeypatch, tmp_path, status, dispatch
):
    path = _pack(tmp_path)
    _, size, wal = sampler.read_staged_packets([str(path)], budget())[0]
    monkeypatch.setattr(sampler, 'slot_at', lambda now: 5002)
    monkeypatch.setattr(sampler, '_latest_attempted', -1)
    monkeypatch.setattr(state, 'claim_slot', Mock(return_value=True))
    monkeypatch.setattr(state, 'authority', Mock(return_value=(1, {})))
    monkeypatch.setattr(sampler, 'read_manifest_inventory', Mock(return_value=([wal], False)))
    observed = Mock()
    monkeypatch.setattr(sampler, 'totals', observed)

    async def direct(executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(sampler, 'run_blocking', direct)
    content = next(
        str(i) for i in range(10000) if int(hashlib.sha256(str(i).encode()).hexdigest()[:12], 16) % 1000 == 0
    )
    await sampler.observe(
        store=object(),
        uid='owner',
        cid='record',
        source='device',
        device='model',
        paths=[str(path)],
        content_id=content,
        claims={},
        status_code=status,
        has_jobs=True,
    )
    assert [call.args for call in observed.labels.call_args_list] == [
        (dispatch, 'duplicate', 'bytes'),
        (dispatch, 'duplicate', 'ticks'),
    ]
    assert [call.args for call in observed.labels.return_value.inc.call_args_list] == [(size,), (9600,)]
