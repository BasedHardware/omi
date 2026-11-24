"""Synthetic packet placement and admission-switch custody checks."""

import time
from types import SimpleNamespace
from unittest.mock import Mock

from google.api_core.exceptions import Cancelled, DeadlineExceeded, ServiceUnavailable
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from config.record_wal_duplicate import mode
from database.batch_pipeline_reads import read_snapshot, write_snapshot
from utils.batch_pipeline import record_wal_duplicate as duplicate
from utils.batch_pipeline.artifact_reads import ArtifactReadBudget, ArtifactReadLimit
from utils.batch_pipeline.record_wal_alignment import Packet
from utils.batch_pipeline.record_wal_source import attest
from utils.other.raw_audio import WAL_FORMAT


def frames(*values, root='device-root', first=0, begin=48000):
    return [Packet(str(value), 960, begin + 960 * i, 4, (root, 7, first + i)) for i, value in enumerate(values)]


def prove(runs, wal=None, covered=None, claims=None, capture_sessions=None, *, shadow=True):
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
        shadow,
    )


def test_requires_every_frame_and_both_algorithms_agree():
    proof, disagreement = prove([frames(1, 2, 3, 4)])
    assert proof[0]
    assert not disagreement
    proof, _ = prove([frames(1, 2, 3, 4)], covered={(0, n) for n in range(3)})
    assert proof == [None]
    proof, _ = prove([frames(1, 2, 3, 4)], wal=frames(1, 2, 3, 4, 5))
    assert proof == [None]


def test_active_proof_uses_anchored_decision_without_shadow_oracle(monkeypatch):
    oracle = Mock(side_effect=AssertionError('shadow oracle ran on active settlement'))
    monkeypatch.setattr(duplicate, '_oracle', oracle)
    proof, disagreement = prove([frames(1, 2, 3, 4)], shadow=False)
    assert proof[0] and not disagreement
    oracle.assert_not_called()


def test_active_holds_repeated_sequence_split_across_archive_packs():
    first = frames(1, 2, 3, 4)
    repeated = frames(1, 2, 3, 4, first=4, begin=first[-1].start + 960)
    assert prove([first, repeated[:2], repeated[2:]], shadow=False)[0] == [None]


@pytest.mark.asyncio
async def test_shadow_holds_and_counts_disagreement_on_packet_placement(monkeypatch):
    first = frames(1, 2, 3, 4)
    repeated = frames(1, 2, 3, 4, first=4, begin=first[-1].start + 960)
    broken = frames(3, 4, first=6, begin=repeated[2].start + 960)
    runs = [first, repeated[:2], broken]
    placements, disagree = prove(runs)
    assert placements[0] and disagree

    claims = {
        'a': {
            'capture_root': 'device-root',
            'clock_epoch': 7,
            'source_frame_start': 0,
            'rate_hz': 16000,
            'frame_count': len(first),
            'codec': 'opus',
            'channel': 'mono',
        }
    }

    def staged(paths, budget, *, descriptors):
        descriptors['a'] = {'sample_rate': 16000}
        return [('a', 32, first)]

    async def inline(executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    snapshot = Mock(return_value=SimpleNamespace(prior=False, scope=SimpleNamespace(source={})))
    covered = {(r, p) for r, run in enumerate(runs) for p in range(len(run))}
    inventory = duplicate.Inventory(runs, covered, [], ('archive-session',) * len(runs))
    monkeypatch.setattr(duplicate, 'run_blocking', inline)
    monkeypatch.setattr(duplicate, '_claim_process', lambda slot: True)
    monkeypatch.setattr(duplicate, 'claim_slot', lambda *args, **kwargs: True)
    monkeypatch.setattr(duplicate.sample, 'read_staged_packets', staged)
    monkeypatch.setattr(duplicate.ledger, 'reconcile', snapshot)
    monkeypatch.setattr(duplicate, '_inventory', lambda *args: inventory)
    disagreement = duplicate.shadow_checks.labels('disagree')._value
    hold = duplicate.decisions.labels('shadow', 'hold')._value
    before_disagreement, before_hold = disagreement.get(), hold.get()
    assert await duplicate.evaluate(None, 'u', 'c', 'omi', 'd', 'id', None, ['a'], claims, 'shadow', 1) is None
    assert disagreement.get() == before_disagreement + 1
    assert hold.get() == before_hold + 1
    snapshot.assert_called_once()


@pytest.mark.parametrize(
    ('mode', 'prepare_limit', 'finish_limit'),
    [('settle', 52, 53), ('shadow', 52, 52), ('replay', 56, 52)],
)
def test_proof_read_ceilings_are_fixed(mode, prepare_limit, finish_limit):
    prepare, finish = duplicate._views(duplicate._budget(), mode)
    for reads, limit in ((prepare, prepare_limit), (finish, finish_limit)):
        for _ in range(limit):
            reads.point(2)
        assert reads.issued == limit
        with pytest.raises(ArtifactReadLimit, match='point-read limit'):
            reads.point(2)


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
    claims = {'synthetic': {}}
    assert await duplicate.evaluate(None, 'u', 'c', 'omi', 'd', 'id', None, ['synthetic'], claims, 'shadow', 1) is None


@pytest.mark.parametrize('claims', ({}, {'a': {}, 'b': {}}))
@pytest.mark.asyncio
async def test_ineligible_shadow_upload_does_not_claim_a_slot(monkeypatch, claims):
    claim = Mock(side_effect=AssertionError('ineligible shadow request reached slot arbitration'))
    monkeypatch.setattr(duplicate, '_claim_process', claim)
    assert await duplicate.evaluate(None, 'u', 'c', 'omi', 'd', 'id', None, ['synthetic'], claims, 'shadow', 1) is None
    claim.assert_not_called()


def test_spanning_packs_requires_one_archive_session():
    first = frames(1, 2, 3, 4)
    second = frames(5, 6, 7, 8, first=4, begin=48000 + 4 * 960)
    assert prove([first, second], wal=first + second)[0][0]
    assert prove([first, second], wal=first + second, capture_sessions=('first', 'second'))[0] == [None]
    assert prove([first], wal=first, capture_sessions=(None,))[0] == [None]


@pytest.fixture
def snapshot_rpc(monkeypatch):
    clock = SimpleNamespace(now=100)
    monkeypatch.setattr(time, 'monotonic', lambda: clock.now)
    api = Mock()
    api.begin_transaction.return_value = SimpleNamespace(transaction=b'wal-snapshot')
    client = firestore.Client(project='synthetic-project', credentials=AnonymousCredentials())
    client._firestore_api_internal = api
    store = SimpleNamespace(client=client, namespace='batch_pipeline_dev')
    events = []
    yield SimpleNamespace(
        api=api,
        store=store,
        budget=ArtifactReadBudget(101, 0, 0),
        clock=clock,
        events=events,
        observe=lambda stage, outcome: events.append((stage, outcome)),
    )
    client._firestore_api_internal = None


def _stage_intake(view):
    view.put('intakes', 'synthetic', {'kind': 'synthetic'})
    return 'staged'


def test_lifecycle_rpc_observes_successful_commit(snapshot_rpc):
    case = snapshot_rpc

    # A confirmed server commit remains successful even if its reply arrives at the deadline.
    def complete_at_deadline(**kwargs):
        case.clock.now = case.budget.deadline

    case.api.commit.side_effect = complete_at_deadline
    assert write_snapshot(case.store, _stage_intake, case.budget, on_rpc=case.observe) == 'staged'
    assert [call[0] for call in case.api.mock_calls] == ['begin_transaction', 'commit']
    assert case.api.begin_transaction.call_args.kwargs['request']['options'] == {'read_write': {}}
    commit = case.api.commit.call_args.kwargs
    assert commit['request']['transaction'] == b'wal-snapshot'
    assert len(commit['request']['writes']) == 1
    assert commit['timeout'] == 1 and commit['retry'] is None
    assert case.events == [('begin', 'attempt'), ('begin', 'success'), ('commit', 'attempt'), ('commit', 'success')]


def test_lifecycle_fence_can_refuse_dispatch_after_staging(snapshot_rpc):
    case = snapshot_rpc

    def refuse():
        assert case.api.begin_transaction.called
        assert not case.api.commit.called
        raise ArtifactReadLimit('already falling back')

    with pytest.raises(ArtifactReadLimit, match='already falling back'):
        write_snapshot(case.store, _stage_intake, case.budget, on_rpc=case.observe, before_commit=refuse)
    case.api.commit.assert_not_called()
    case.api.rollback.assert_called_once()
    assert ('commit', 'attempt') not in case.events


@pytest.mark.parametrize(
    'failure, outcome, propagated',
    [
        (ServiceUnavailable, 'error', ServiceUnavailable),
        (DeadlineExceeded, 'deadline', ArtifactReadLimit),
        (Cancelled, 'cancelled', Cancelled),
    ],
)
def test_lifecycle_rpc_observes_failed_commit_then_rollback(snapshot_rpc, failure, outcome, propagated):
    case = snapshot_rpc
    case.api.commit.side_effect = failure('synthetic transport failure')
    with pytest.raises(propagated):
        write_snapshot(case.store, _stage_intake, case.budget, on_rpc=case.observe)
    assert [call[0] for call in case.api.mock_calls] == ['begin_transaction', 'commit', 'rollback']
    assert case.api.rollback.call_args.kwargs['request']['transaction'] == b'wal-snapshot'
    assert case.events == [
        ('begin', 'attempt'),
        ('begin', 'success'),
        ('commit', 'attempt'),
        ('commit', outcome),
        ('rollback', 'attempt'),
        ('rollback', 'success'),
    ]


def test_lifecycle_rpc_records_rollback_expiry_without_attempt(snapshot_rpc):
    case = snapshot_rpc

    def expire(view):
        assert view.transaction.id == b'wal-snapshot'
        case.clock.now = case.budget.deadline

    with pytest.raises(ArtifactReadLimit, match='artifact read deadline'):
        read_snapshot(case.store, expire, case.budget, on_rpc=case.observe)
    case.api.rollback.assert_not_called()
    assert case.events == [('begin', 'attempt'), ('begin', 'success'), ('rollback', 'expired_before_attempt')]
