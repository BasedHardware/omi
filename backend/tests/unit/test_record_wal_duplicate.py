"""Synthetic packet placement and admission-switch custody checks."""

from types import SimpleNamespace
import time

import pytest

from config.record_wal_duplicate import mode
from utils.batch_pipeline import record_wal_duplicate as duplicate
from utils.batch_pipeline.artifact_reads import ArtifactReadBudget
from utils.batch_pipeline.record_wal_alignment import Packet
from utils.batch_pipeline.record_wal_source import attest
from utils.other.raw_audio import WAL_FORMAT


def frames(*values, root='device-root', first=0, begin=48000):
    return [Packet(str(value), 960, begin + 960 * i, 4, (root, 7, first + i)) for i, value in enumerate(values)]


def prove(runs, wal=None, covered=None, claims=None, capture_sessions=None):
    wal = wal if wal is not None else frames(1, 2, 3, 4)
    claims = (
        claims
        if claims is not None
        else {
            'a': {
                'capture_root': 'device-root',
                'clock_epoch': 7,
                'source_frame_start': 0,
                'rate_hz': 16000,
                'frame_count': len(wal),
                'codec': 'opus',
                'channel': 'mono',
            }
        }
    )
    all_positions = {(r, p) for r, run in enumerate(runs) for p, _ in enumerate(run)}
    return duplicate._placements(
        [('a', 32, wal)],
        {'a': {'sample_rate': 16000}},
        claims,
        duplicate.Inventory(
            runs,
            all_positions if covered is None else covered,
            [],
            capture_sessions or ('archive-session',) * len(runs),
        ),
        ArtifactReadBudget(time.monotonic() + 2, 0, 0),
        True,
    )


def test_requires_every_frame_and_both_algorithms_agree():
    proof, disagreement = prove([frames(1, 2, 3, 4)])
    assert proof[0]
    assert not disagreement
    proof, _ = prove([frames(1, 2, 3, 4)], covered={(0, n) for n in range(3)})
    assert proof == [None]
    proof, _ = prove([frames(1, 2, 3, 4)], wal=frames(1, 2, 3, 4, 5))
    assert proof == [None]


@pytest.mark.parametrize(
    'runs',
    (
        [frames(1, 2, 3, 4), frames(1, 2, 3, 4, first=4, begin=52000)],
        [frames(1, 2, 3, 4), frames(9, 9, 9, 9, first=0, begin=52000)],
        [frames(1, 2, 3, 4, first=4)],
        [[Packet(str(i), 960, 48000 + 960 * i, 4) for i in range(1, 5)]],
        [frames(1, 2, 9, 4)],
    ),
)
def test_ambiguous_unpositioned_conflicting_and_unmatched_sources_hold(runs):
    assert prove(runs)[0] == [None]


def test_native_intake_attests_only_its_exact_retained_slices():
    ref = {
        'path': 'raw-live/owner/record/original.bin',
        'bucket': 'private',
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
    args = ('private', 'owner', 'record', {'record_audio_closed': True}, {'record_upload_revision': 4})
    units, items = [(0, 1, [ref])], [SimpleNamespace(segment_id='seg')]
    attestation = attest(*args, units, items)
    assert attestation['revision'] == 4
    assert attestation['slices'] == [{'unit': 'seg', 'path': ref['path'], 'generation': 3, 'first': 160, 'count': 480}]
    assert attest(*args, [(0, 1, [{**ref, 'path': 'chunks/owner/record/other.wav'}])], items) is None


def test_independent_shadow_and_settlement_controls_fail_closed(monkeypatch):
    assert mode('owner', 1080) == ('off', None)
    monkeypatch.setenv('K_SERVICE', 'backend-sync')
    monkeypatch.setenv('RECORD_WAL_DUPLICATE_SOURCE_FENCE_VERIFIED', 'true')
    monkeypatch.setenv('RECORD_WAL_DUPLICATE_SHADOW_EPOCH', '1080')
    assert mode('owner', 1080) == ('shadow', 6)
    assert mode('owner', 1080 + 86400) == ('off', None)
    monkeypatch.setenv('RECORD_WAL_DUPLICATE_PERCENT', '100')
    assert mode('owner', 1080) == ('off', None)
    monkeypatch.delenv('RECORD_WAL_DUPLICATE_SHADOW_EPOCH')
    assert mode('owner', 1080) == ('settle', None)
    monkeypatch.setenv('RECORD_WAL_HANDOFF_ENABLED', 'true')
    assert mode('owner', 1080) == ('off', None)


@pytest.mark.asyncio
async def test_shadow_offload_failure_cannot_change_existing_reply(monkeypatch):
    async def unavailable(*args, **kwargs):
        raise RuntimeError('executor unavailable')

    monkeypatch.setattr(duplicate, 'run_blocking', unavailable)
    assert await duplicate.evaluate(None, 'u', 'c', 'omi', 'd', 'id', None, ['synthetic'], {}, 'shadow', 1) is None


def test_spanning_packs_requires_one_archive_session():
    first = frames(1, 2, 3, 4)
    second = frames(5, 6, 7, 8, first=4, begin=48000 + 4 * 960)
    assert prove([first, second], wal=first + second)[0][0]
    assert prove([first, second], wal=first + second, capture_sessions=('first', 'second'))[0] == [None]
    assert prove([first], wal=first, capture_sessions=(None,))[0] == [None]


def test_lifecycle_rpc_records_termination_at_the_sync_boundary():
    from google.api_core.exceptions import Cancelled, DeadlineExceeded
    from database.batch_pipeline_reads import observe_rpc

    observed = []
    for failure, expected in [(Cancelled('cancelled'), 'cancelled'), (DeadlineExceeded('deadline'), 'deadline')]:
        with pytest.raises(type(failure)), observe_rpc(lambda *event: observed.append(event), 'begin'):
            raise failure
        assert observed[-2:] == [('begin', 'attempt'), ('begin', expected)]
