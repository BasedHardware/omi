"""SCA-3376 phase 2a: current app WAL names reach the duplicate shadow, and attest refusals are counted."""

import struct
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config.record_wal_duplicate import MAX_JOBS
from utils.batch_pipeline import record_wal_duplicate as duplicate
from utils.batch_pipeline import record_wal_sample as sampler
from utils.batch_pipeline import record_wal_source as source
from utils.batch_pipeline.artifact_reads import ArtifactReadBudget
from utils.other.raw_audio import WAL_FORMAT, filename_provenance

UNPARSED = {'format': 'as-captured-file-v1'}
TS = 1_700_000_000


def budget():
    return ArtifactReadBudget(time.monotonic() + 5, 0, 0)


def opus_fields(device='omi', frame=320, start=float(TS)):
    return {
        'device_model': device,
        'codec': 'opus',
        'sample_rate': 16000,
        'channels': 1,
        'frame_size': frame,
        'capture_start': start,
        'format': WAL_FORMAT,
    }


def write_wal(path, packets=10):
    # TOC 0xF8: one 20 ms CELT frame, 320 samples at 16 kHz.
    payloads = [bytes((0xF8, index)) for index in range(packets)]
    path.write_bytes(b''.join(struct.pack('<I', len(payload)) + payload for payload in payloads))
    return path


# --- (a) filename parser local to the shadow/sampler path -------------------


def test_old_shape_keeps_the_shared_parser_fields_exactly():
    name = f'audio_omi_opus_16000_1_fs160_{TS}.bin'
    assert sampler.staged_name_provenance(name) == filename_provenance(name) == opus_fields(frame=160)
    pcm = f'audio_omi_pcm16_16000_1_fs160_{TS}.bin'
    assert sampler.staged_name_provenance(pcm) == filename_provenance(pcm)
    assert sampler.staged_name_provenance(pcm)['format'] == 'omi-wal-uint32le-pcm-v1'


@pytest.mark.parametrize(
    ('name', 'expected'),
    [
        # bt_device.dart mapCodecToName(opusFS320) + wal.dart getFileNameByTimeStarts.
        (f'audio_omi_opus_fs320_16000_1_fs320_{TS}.bin', opus_fields()),
        (f'audio_omi_opus_fs320_16000_1_fs320_clke9f3a_{TS}.bin', opus_fields()),
        (f'audio_omi_opus_16000_1_fs320_clke9f3a_{TS}.bin', opus_fields()),
        (f'audio_omi_opus_fs160_16000_1_fs160_clkez0_{TS}.bin', opus_fields(frame=160)),
        # deviceClockCollisionPrefix puts the nonce before clke, never between clke and the time.
        (f'audio_omi_opus_fs320_16000_1_fs320_u3_clke9f3a_{TS}.bin', opus_fields()),
        (f'audio_omi_opus_fs320_16000_1_fs320_u3_{TS}.bin', opus_fields()),
        (f'audio_omi_opus_fs320_16000_1_fs320_clke9f3a_{TS}_u0.bin', opus_fields()),
        (f'audio_omi_opus_fs320_16000_1_fs320_{TS}.25.bin', opus_fields(start=TS + 0.25)),
        # flash_page_wal_sync.dart: millisecond timestamp, r<random>_<seq>, optional clke.
        (
            f'audio_limitless_opus_16000_1_fs320_r42_7_clkeab12_{TS}500.bin',
            opus_fields(device='limitless', start=TS + 0.5),
        ),
    ],
)
def test_current_app_names_yield_the_old_shape_fields(name, expected):
    assert filename_provenance(name) == UNPARSED, 'shared parser must stay unchanged'
    assert sampler.staged_name_provenance(name) == expected


def test_current_pcm_name_is_parsed_but_never_a_wal_descriptor():
    info = sampler.staged_name_provenance(f'audio_omi_pcm16_16000_1_fs160_clkeab_{TS}.bin')
    assert info['format'] == 'omi-wal-uint32le-pcm-v1' and info['codec'] == 'pcm16'


@pytest.mark.parametrize(
    'name',
    [
        f'audio_omi_opus_fs320_16000_1_fs160_{TS}.bin',  # codec frame disagrees with fs<frame>
        f'audio_omi_opus_fs999_16000_1_fs999_{TS}.bin',  # unknown opus_fs codec
        f'audio_omi_lc3_fs1030_16000_1_fs1030_{TS}.bin',  # non-Opus codec with a frame suffix
        f'audio_omi_opus_fs320_16000_1_fs320_clkeAB_{TS}.bin',  # clke run is lowercase only
        f'audio_omi_opus_fs320_16000_1_fs320_clke9f3a_u3_{TS}.bin',  # nonce between clke and time
        f'audio_omi_opus_fs320_16000_1_fs320_{TS}_clke9f3a.bin',  # clke after the time
        f'audio_omi_opus_fs320_16000_1_fs320_clke9f3a.bin',  # no timestamp
        f'audio_omi_opus_fs320_16000_1_{TS}.bin',  # no fs<frame>
        f'audio_om-i_opus_fs320_16000_1_fs320_{TS}.bin',  # device token is alphanumeric
        f'audio_omi_opus_fs320_16000_1_fs320_wr{"a" * 32}_{TS}.bin',  # unrecognized producer token
        f'audio_omi_opus_fs320_16000_1_fs320_{TS}_extra.bin',
        'audio_omi_opus_fs320_16000_1_fs320_nan.bin',
        f'record_omi_opus_fs320_16000_1_fs320_{TS}.bin',
        'audio.bin',
    ],
)
def test_malformed_names_stay_refused(name):
    assert sampler.staged_name_provenance(name) == UNPARSED


@pytest.mark.parametrize('clock', ('', '_clke9f3a'))
def test_current_opus_fs320_file_produces_a_duplicate_descriptor(tmp_path, clock):
    path = write_wal(tmp_path / f'audio_omi_opus_fs320_16000_1_fs320{clock}_{TS}.bin')
    descriptors = {}
    files = sampler.read_staged_packets([str(path)], budget(), descriptors=descriptors)
    assert [(name, len(packets)) for name, _, packets in files] == [(path.name, 10)]
    entry = descriptors[path.name]
    assert {key: entry[key] for key in ('name', 'codec', 'sample_rate', 'channels', 'frame_size')} == {
        'name': path.name,
        'codec': 'opus',
        'sample_rate': 16000,
        'channels': 1,
        'frame_size': 320,
    }
    assert entry['capture_start'] == TS and entry['frame_count'] == 10 and entry['sample_count'] == 3200
    assert entry['size'] == path.stat().st_size


def test_malformed_name_produces_no_descriptor_and_unknown_duration(tmp_path):
    path = write_wal(tmp_path / f'audio_omi_opus_fs320_16000_1_fs160_{TS}.bin')
    descriptors = {}
    files = sampler.read_staged_packets([str(path)], budget(), descriptors=descriptors)
    assert files == [(path.name, path.stat().st_size, [])] and descriptors == {}


def _claims(name):
    return {
        name: {
            'capture_root': 'root',
            'clock_epoch': 1,
            'source_frame_start': 0,
            'rate_hz': 16000,
            'frame_count': 10,
            'codec': 'opus',
            'channel': 'mono',
        }
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('name', 'reaches'),
    [
        (f'audio_omi_opus_fs320_16000_1_fs320_{TS}.bin', True),
        (f'audio_omi_opus_fs320_16000_1_fs320_clke9f3a_{TS}.bin', True),
        (f'audio_omi_opus_fs320_16000_1_fs160_{TS}.bin', False),
    ],
)
async def test_shadow_reaches_the_ledger_for_current_app_names(monkeypatch, tmp_path, name, reaches):
    path = write_wal(tmp_path / name)

    async def inline(executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    reconcile = Mock(return_value=None)
    monkeypatch.setattr(duplicate, 'run_blocking', inline)
    monkeypatch.setattr(duplicate, '_claim_process', lambda slot: True)
    monkeypatch.setattr(duplicate, 'claim_slot', lambda *args, **kwargs: True)
    monkeypatch.setattr(duplicate.ledger, 'reconcile', reconcile)
    result = await duplicate.evaluate(None, 'u', 'c', 'omi', 'd', 'id', None, [str(path)], _claims(name), 'shadow', 1)
    assert result is None
    assert reconcile.called is reaches
    if reaches:
        (entry,) = reconcile.call_args.kwargs['files']
        assert entry['name'] == name and entry['frame_size'] == 320 and entry['codec'] == 'opus'


# --- (b) attest refusal counter ---------------------------------------------

BUCKET, UID, CID = 'private', 'owner', 'record'
REF = {
    'path': f'raw-live/{UID}/{CID}/original.bin',
    'bucket': BUCKET,
    'generation': 3,
    'offset_frame': 160,
    'frames': 480,
    'metadata': {
        'format': WAL_FORMAT,
        'custody_schema': 'audio_custody_v1',
        'clock_source': 'server_projected',
        'source_layout': 'mono',
        'sample_rate': '16000',
    },
}
ROW = {'record_audio_closed': True}
ITEM = SimpleNamespace(segment_id='seg')


def _ref(**changes):
    metadata = {**REF['metadata'], **changes.pop('metadata', {})}
    return {**REF, **changes, 'metadata': metadata}


REFUSALS = [
    ('not_closed', {'row': {}}),
    ('not_closed', {'row': {'record_audio_closed': 'true'}}),
    ('partial', {'row': {**ROW, 'record_audio_partial': True}}),
    ('upload_failed', {'row': {**ROW, 'record_upload_failed': True}}),
    ('handoff_present', {'row': {**ROW, 'record_wal_handoff_present': True}}),
    ('unit_count', {'units': [], 'items': []}),
    ('unit_count', {'items': [ITEM, ITEM]}),
    ('unit_count', {'units': [(0, 1, [REF])] * (MAX_JOBS + 1), 'items': [ITEM] * (MAX_JOBS + 1)}),
    ('slice_count', {'units': [(0, 1, [])]}),
    ('slice_count', {'units': [(0, 1, [REF] * (source.MAX_SLICES + 1))]}),
    ('bucket', {'units': [(0, 1, [_ref(bucket='other')])]}),
    ('path', {'units': [(0, 1, [_ref(path=f'chunks/{UID}/{CID}/other.wav')])]}),
    ('path', {'units': [(0, 1, [_ref(path=f'raw-live/{UID}/{CID}/' + 'x' * 512)])]}),
    ('format', {'units': [(0, 1, [_ref(metadata={'format': 'omi-wal-uint32le-pcm-v1'})])]}),
    ('format', {'units': [(0, 1, [_ref(metadata={'custody_schema': 'legacy'})])]}),
    ('clock_source', {'units': [(0, 1, [_ref(metadata={'clock_source': 'device_estimated'})])]}),
    ('geometry', {'units': [(0, 1, [_ref(metadata={'source_layout': 'stereo'})])]}),
    ('geometry', {'units': [(0, 1, [_ref(metadata={'sample_rate': '48000'})])]}),
    ('generation', {'units': [(0, 1, [_ref(generation='3')])]}),
    ('generation', {'units': [(0, 1, [_ref(generation=0)])]}),
]


def _counts():
    return {reason: source.refusals.labels(reason)._value.get() for reason in source.REFUSAL_REASONS}


def _attest(row=ROW, units=None, items=None):
    units = [(0, 1, [REF])] if units is None else units
    items = [ITEM] if items is None else items
    return source.attest(BUCKET, UID, CID, row, {'record_upload_revision': 4}, units, items)


def test_refusal_vocabulary_is_fixed_and_exported_at_zero():
    assert len(source.REFUSAL_REASONS) == len(set(source.REFUSAL_REASONS)) == 12
    family = next(m for m in source.refusals.collect() if m.name == 'omi_record_wal_handoff_source_attest_refusals')
    labels = {sample.labels['reason'] for sample in family.samples if sample.name.endswith('_total')}
    assert labels == set(source.REFUSAL_REASONS)
    assert {key for sample in family.samples for key in sample.labels} == {'reason'}


def test_admitted_attestation_is_unchanged_and_counts_nothing():
    before = _counts()
    attestation = _attest()
    assert attestation == {
        'bucket': BUCKET,
        'revision': 4,
        'units': ['seg'],
        'slices': [{'unit': 'seg', 'path': REF['path'], 'generation': 3, 'first': 160, 'count': 480}],
    }
    assert _counts() == before


@pytest.mark.parametrize(('reason', 'case'), REFUSALS)
def test_each_refusal_returns_none_and_counts_its_one_reason(reason, case):
    before = _counts()
    assert _attest(**case) is None
    after = _counts()
    assert after[reason] == before[reason] + 1
    assert {key: value for key, value in after.items() if key != reason} == {
        key: value for key, value in before.items() if key != reason
    }


def test_first_failing_check_wins_one_increment_per_call():
    before = _counts()
    bad = _ref(bucket='other', generation=0)
    assert _attest(row={'record_audio_partial': True}, units=[(0, 1, [bad])]) is None
    assert _attest(units=[(0, 1, [REF, bad, bad])]) is None
    after = _counts()
    assert after['not_closed'] - before['not_closed'] == 1
    assert after['bucket'] - before['bucket'] == 1
    assert sum(after.values()) - sum(before.values()) == 2
