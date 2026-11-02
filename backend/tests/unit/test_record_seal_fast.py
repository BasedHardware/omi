"""Necessary-condition proof, metadata I/O and closed reason contracts."""

from datetime import datetime, timezone
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from utils.batch_pipeline import live, record_seal_repair as repair
from utils.batch_pipeline.record_barrier import validate_record_tail
from utils.batch_pipeline.record_seal_reasons import (
    PROOF_REASONS,
    TAIL_GAP_BUCKETS,
    proof_reason,
    proof_diagnostics,
    tail_gap_bucket,
)


def audio_client(pcm, metadata=None):
    reload = Mock()
    download = Mock(side_effect=lambda **kw: pcm)
    blob = SimpleNamespace(size=len(pcm), metadata=metadata or {}, reload=reload, download_as_bytes=download)
    return SimpleNamespace(bucket=lambda _: SimpleNamespace(blob=lambda *a, **kw: blob)), reload, download


@pytest.mark.parametrize('span', [None, {'sample_rate': 16000}])
def test_record_reader_reloads_once_and_preserves_metadata_and_rate(monkeypatch, span):
    monkeypatch.setattr(live, 'private_cloud_sync_bucket', 'synthetic')
    client, reload, download = audio_client(b'\x01\x00' * 8000, {'record_sample_rate': '8000', 'marker': 'kept'})
    chunk = {'path': 'chunks/synthetic/capture/a.pcm', 'generation': 7, 'timestamp': 100, 'span': span}
    units = list(live.retained_record_units('synthetic', 'capture', [chunk], client, b'x' * 32))
    reload.assert_called_once_with(if_generation_match=7, timeout=30, retry=None)
    download.assert_called_once_with(if_generation_match=7, timeout=60, retry=None)
    ref = units[0][2][0]
    assert ref['metadata']['marker'] == 'kept'
    assert ref['sample_rate'] == (16000 if span else 8000)
    assert units[0][1] == pytest.approx(0.5 if span else 15999 / 16000)


def chunks_for(starts, samples):
    return [
        {'path': f'chunks/synthetic/capture/{i}.pcm', 'generation': 1, 'timestamp': start, 'samples': size}
        for i, (start, size) in enumerate(zip(starts, samples))
    ]


@pytest.mark.parametrize(
    'starts,samples,finish',
    [
        ([100, 101], [16000, 16000], 103),  # short tail
        ([100, 101], [16000, 16000], 102),  # eligible still fully proven
        ([100, 100.5], [16000, 16000], 102),  # trimmed overlap, still short
        ([100, 100.5], [16000, 16000], 101.5),  # trimmed eligible
        ([100, 100.5], [16000, 8000], 101),  # fully trimmed final chunk
        ([100, 100.5], [16000, 4000], 101),  # contained short chunk conflicts
        ([100, 100.50002], [16000, 8000], 101.100021),  # rounding boundary: keep walk
        ([100, 100.49998], [16000, 8000], 101.1),
        ([100, 100.5, 100.75], [16000, 8000, 4000], 101),
        ([100, 140], [16000, 16000], 142),  # split unit
    ],
)
def test_precheck_never_refuses_a_full_walk_success(monkeypatch, starts, samples, finish):
    chunks = chunks_for(starts, samples)
    reads = []

    def read(_client, ref, *args, **kwargs):
        i = int(ref['path'].rsplit('/', 1)[1].split('.')[0])
        reads.append(i)
        return b'\x01\x00' * samples[i]

    monkeypatch.setattr(live, 'read_reference', read)
    row = {'finished_at': datetime.fromtimestamp(finish, timezone.utc)}
    job = {'record_snapshot': row}
    precheck_refused = False
    try:
        repair.precheck_record_tail('synthetic', 'capture', chunks, None, b'x' * 32, row, job)
    except ValueError:
        precheck_refused = True
    assert set(reads) == {len(chunks) - 1}
    try:
        units = list(live.retained_record_units('synthetic', 'capture', chunks, None, b'x' * 32))
        validate_record_tail(units, row['finished_at'], require_finish=True)
    except ValueError:
        full_refused = True
    else:
        full_refused = False
    assert not precheck_refused or full_refused
    if starts[-1] == 100.49998:
        assert not full_refused and not precheck_refused
        with pytest.raises(ValueError, match='tail not durable'):
            validate_record_tail([(starts[-1], samples[-1] / 16000, [])], row['finished_at'], require_finish=True)
    if finish == 103 or finish == 102 and starts[-1] == 100.5:
        # Singleton refusal is no longer sound for contained final objects.
        assert not precheck_refused


def test_precheck_short_tail_avoids_prefix_but_eligible_keeps_full_proof(monkeypatch):
    chunks = chunks_for([100, 101], [16000, 16000])
    monkeypatch.setattr(repair, 'list_audio_chunks', lambda *a, **k: chunks)
    reads = []

    def read(_client, ref, *args, **kwargs):
        reads.append(ref['path'].rsplit('/', 1)[1])
        return b'\x01\x00' * 16000

    monkeypatch.setattr(live, 'read_reference', read)
    artifacts = SimpleNamespace(authorize=lambda _: None, key_for_owner=lambda _: b'x' * 32)
    job = {'owner_id': 'synthetic', 'conversation_id': 'capture', 'segment_id': 'pending', 'privacy_generation': 0}
    row = {'finished_at': datetime.fromtimestamp(103, timezone.utc)}
    job['record_snapshot'] = row
    with pytest.raises(ValueError, match='tail not durable') as refusal:
        repair.retained_tail_proof(job, row, None, artifacts)
    assert proof_diagnostics(refusal.value) == {'proof_reason': 'tail_lagging', 'tail_gap_bucket': '1_to_5s'}
    assert reads == ['1.pcm', '0.pcm', '1.pcm']
    reads.clear()
    row['finished_at'] = datetime.fromtimestamp(102, timezone.utc)
    assert repair.retained_tail_proof(job, row, None, artifacts)
    assert reads == ['1.pcm', '0.pcm', '1.pcm']


@pytest.mark.parametrize(
    'message,reason',
    [
        ('retained capture tail not durable yet', 'tail_lagging'),
        ('retained capture not durable yet', 'tail_lost_or_unproven'),
        ('conflicting retained audio overlap', 'overlap_conflict'),
        ('retained capture checksum mismatch', 'decode_or_checksum'),
        ('retained capture reference budget exceeded', 'budget_limit'),
        ('retained capture finish missing', 'finish_missing'),
        ('registration refused', 'registration_refused'),
    ],
)
def test_reason_mapping_is_exact_and_closed(message, reason):
    assert proof_reason(ValueError(message)) == reason
    for private in ('A' * 28, 'private@example.invalid', 'users/private/conversations/private'):
        assert proof_reason(ValueError(message + private)) == 'other'
        assert private not in json.dumps({'proof_reason': proof_reason(ValueError(private))})
    assert reason in PROOF_REASONS


@pytest.mark.parametrize(
    'gap,bucket',
    [
        (-1, 'negative_or_unknown'),
        (0, 'under_1s'),
        (0.999999, 'under_1s'),
        (1, '1_to_5s'),
        (4.999999, '1_to_5s'),
        (5, '5_to_30s'),
        (29.999999, '5_to_30s'),
        (30, '30_to_120s'),
        (120, '30_to_120s'),
        (120.000001, 'over_120s'),
    ],
)
def test_tail_gap_boundaries(gap, bucket):
    assert tail_gap_bucket(datetime.fromtimestamp(200 + gap, timezone.utc), 200) == bucket
    assert bucket in TAIL_GAP_BUCKETS


@pytest.mark.parametrize('end', [float('nan'), float('inf'), float('-inf'), None])
def test_unknown_gap_stays_closed(end):
    assert tail_gap_bucket(datetime.fromtimestamp(200, timezone.utc), end) == 'negative_or_unknown'
    assert tail_gap_bucket(None, 200) == 'negative_or_unknown'


def test_full_walk_tail_diagnostic_uses_validated_finish():
    units = [(100, 2, [])]
    for finish, bucket in ((102.5, 'under_1s'), (107, '5_to_30s'), (300, 'over_120s')):
        with pytest.raises(ValueError, match='tail not durable') as refusal:
            repair.validate_repair_tail(units, datetime.fromtimestamp(finish, timezone.utc))
        assert proof_diagnostics(refusal.value) == {'proof_reason': 'tail_lagging', 'tail_gap_bucket': bucket}
    # Existing tolerance and missing-finish refusal remain unchanged.
    repair.validate_repair_tail(units, datetime.fromtimestamp(102.1, timezone.utc))
    with pytest.raises(ValueError, match='finish missing') as refusal:
        repair.validate_repair_tail(units, None)
    assert proof_diagnostics(refusal.value) == {'proof_reason': 'finish_missing'}
