"""PL-396/105/363: retained audio never becomes a false ACK or a repeated paid attempt.

Same admission, status and recovery code on old Firestore, new Postgres and the
simulator. The CI proof runner requires sim/emulator; complete old/new
qualification requires OMI_REQUIRE_STORE_BACKENDS=all with no missing Postgres
leg. Audio/VAD/providers are synthetic, not serving A4 customer-bridge proof.
"""

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import HTTPException
import pytest
from google.cloud import firestore

from config.policy import BatchUnitPolicy, RecoveryPolicy
from database.batch_pipeline_intake import admit
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from testing.store_fixtures import store_backend  # noqa: F401
from utils.batch_pipeline import intake, quarantine_recovery
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem, vad_receipt
from utils.batch_pipeline.quarantine_recovery import QuarantineRecovery
from utils.batch_pipeline.source_audio import MAGIC, materialize

pytestmark = pytest.mark.integration

T0 = 1_800_000_000.0
AUDIO = 'gs://synthetic/retained-audio#7'
PARTIAL = json.loads((Path(__file__).parents[1] / 'fixtures/held_partial_status.json').read_text())


@pytest.fixture(autouse=True)
def offline_stage(monkeypatch):
    # Collection routing requires an explicit stage even on a loopback client.
    # The CI proof runner deliberately supplies no ambient serving stage.
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')


def seed(h, *, duration=61.0):
    """Admit through the real transaction, then model a failed worker handoff."""
    owner = h.seed_user('custody')
    h.customer.add_conversation(owner, 'visible')
    items = [
        WorkItem(sid, owner, T0 + offset, AUDIO, duration, Priority.FRESH, privacy_generation=0)
        for offset, sid in enumerate(('held', 'good'))
    ]
    binding = ProjectionBinding(owner, 'bp_upload', 'synthetic-content', ('held', 'good'))
    admission = {
        'owner_id': owner,
        'content_id': binding.content_id,
        'segment_ids': ['held', 'good'],
        'total_files': 1,
        'lane': 'backfill',
    }
    assert (
        admit(
            h.store,
            items,
            binding,
            T0,
            namespace=h.namespace,
            intake=admission,
            policy=BatchUnitPolicy(batch_enabled=True, batch_percent=100),
        )['outcome']
        == 'batch'
    )

    def failed(tx):
        held = tx.get('jobs', 'held')
        good = tx.get('jobs', 'good')
        held.update(
            state='quarantined',
            quarantine_reason='worker_failed',
            recovery_state='held',
            merge_pending=False,
            token='',
            lease_until=0,
            worker_failure={'stage': 'vad_windows', 'reason': 'unsupported_language'},
            worker_vad_receipt=vad_receipt(AUDIO, round(duration * 16000), 0),
            measured_held_vad_speech_seconds=2.0,
            policy_parts={'recovery': RecoveryPolicy(recovery_enabled=True).to_dict()},
        )
        good.update(state='committed', merge_pending=False)
        tx.put('jobs', 'held', held)
        tx.put('jobs', 'good', good)

    h.store.run(failed)
    return owner, binding, items[0]


def read(h, table='jobs', key='held'):
    return h.store.run(lambda tx: tx.get(table, key))


def patch(h, fields, table='jobs', key='held'):
    def update(tx):
        row = tx.get(table, key)
        tx.put(table, key, {**row, **fields})

    h.store.run(update)


def runner(h, monkeypatch, *, audio=b'synthetic', duration=61.0):
    artifacts = Mock()
    artifacts.fetch_audio.return_value = audio
    inspect = Mock(return_value=(b'\0\0', duration, []))
    monkeypatch.setattr(quarantine_recovery, 'inspect_audio', inspect)
    # The explicit duration limit applies even when independent recovery is enabled.
    monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED', 'true')
    first, second = Mock(), Mock()
    recovery = QuarantineRecovery(h.store, artifacts, stt=first, second_stt=second, clock=lambda: T0 + 10)
    return recovery, artifacts, inspect, first, second


def assert_unspent(h, before, reason):
    held = read(h)
    assert held['state'] == 'quarantined' and held['recovery_state'] == 'failed_held'
    assert held['audio_uri'] == before['audio_uri']
    assert held['projection_binding'] == before['projection_binding']
    assert held['worker_vad_receipt'] == before['worker_vad_receipt']
    assert held['measured_held_vad_speech_seconds'] == 2.0
    assert held['recovery']['refusal']['reason'] == reason
    assert not set(held['recovery']) & {
        'provider',
        'started_at',
        'recognizers',
        'attempts',
        'paid_state',
        'attempt_count',
        'paid_provider',
        'attempt_history',
        'max_attempts',
    }
    assert held.get('attempt', 0) == before.get('attempt', 0)
    assert not held.get('result') and read(h, 'results') == {}
    return held


@pytest.mark.parametrize('state', ['held', 'prepared', 'running', 'failed_held'])
def test_pl396_partial_results_never_acknowledge_unresolved_custody(store_backend, monkeypatch, state):
    h = store_backend
    owner, binding, _ = seed(h)
    result = {**PARTIAL['result'], 'new_memories': ['visible']}
    patch(h, {'recovery_state': state})
    patch(h, {'status': 'partial', 'result': result}, 'content', f'{owner}/{binding.content_id}')
    ledger = read(h, 'content', f'{owner}/{binding.content_id}')
    expected = {**PARTIAL, 'result': result}
    for elapsed in (0, 31 * 60, 14 * 86400):
        monkeypatch.setattr(intake, 'time', SimpleNamespace(time=lambda: T0 + elapsed))
        assert intake.durable_status(h.store, owner, binding.job_id) == expected
    assert read(h, 'content', f'{owner}/{binding.content_id}') == ledger
    assert read(h)['audio_uri'] == AUDIO
    visible = h.customer.client.collection('users').document(owner).collection('conversations').document('visible')
    assert visible.get().to_dict()['status'] == 'completed'


def test_pl396_only_valid_completed_ledger_releases_custody(store_backend, monkeypatch):
    h = store_backend
    owner, binding, _ = seed(h)
    monkeypatch.setattr(intake, 'time', SimpleNamespace(time=lambda: T0 + 20))
    # A completed label with an invalid result is not a completion receipt.
    key = f'{owner}/{binding.content_id}'
    patch(h, {'status': 'completed', 'result': {}}, 'content', key)
    assert intake.durable_status(h.store, owner, binding.job_id)['status'] != 'completed'
    patch(h, {'state': 'committed', 'recovery_state': 'recovered'})
    completed = {
        'new_memories': ['visible'],
        'updated_memories': [],
        'failed_segments': 0,
        'total_segments': 2,
        'errors': [],
    }
    patch(h, {'status': 'completed', 'result': completed}, 'content', key)
    status = intake.durable_status(h.store, owner, binding.job_id)
    assert status['status'] == 'completed' and status['poll_after_ms'] == 0
    assert status['result'] == completed and status['successful_segments'] == 2
    with pytest.raises(HTTPException) as denied:
        intake.durable_status(h.store, h.uid('foreign'), binding.job_id)
    assert denied.value.status_code == 403


@pytest.mark.parametrize('stored,decoded', [(61.0, 61.0), (60.0, 60.04)])
def test_pl105_over_limit_refuses_once_without_losing_speech_or_buying_recovery(
    store_backend, monkeypatch, stored, decoded
):
    h = store_backend
    owner, _, _ = seed(h, duration=stored)
    before = read(h)
    recovery, artifacts, inspect, first, second = runner(h, monkeypatch, duration=decoded)
    assert recovery.recover('held', owner) == 'failed_held'
    held = assert_unspent(h, before, 'independent_duration_limit')
    assert held['recovery']['refusal']['audio_seconds'] == decoded
    for _ in range(3):
        assert (
            QuarantineRecovery(h.store, artifacts, stt=first, second_stt=second, clock=lambda: T0 + 100).recover(
                'held', owner
            )
            == 'held'
        )
    assert read(h) == held
    artifacts.fetch_audio.assert_called_once()
    inspect.assert_called_once()
    artifacts.persist_recovery_result.assert_not_called()
    first.assert_not_called()
    second.assert_not_called()


@pytest.mark.parametrize('body', [MAGIC + b'{not-json', MAGIC + b'[]', MAGIC + b'{"references":null}'])
def test_pl363_permanent_manifest_failure_holds_once_before_paid_start(store_backend, monkeypatch, body):
    h = store_backend
    owner, _, _ = seed(h)
    before = read(h)
    recovery, artifacts, inspect, first, second = runner(h, monkeypatch)
    source_read = Mock(side_effect=AssertionError('malformed manifest tried to fetch a source'))
    artifacts.fetch_audio.side_effect = lambda item: materialize(body, item, source_read)
    assert recovery.recover('held', owner) == 'failed_held'
    held = assert_unspent(h, before, 'invalid_retained_manifest')
    assert recovery.protocol.prepare('held', owner, T0 + 50) is None
    assert recovery.recover('held', owner) == 'held'
    assert read(h) == held
    artifacts.fetch_audio.assert_called_once()
    source_read.assert_not_called()
    inspect.assert_not_called()
    artifacts.persist_recovery_result.assert_not_called()
    first.assert_not_called()
    second.assert_not_called()


@pytest.mark.parametrize('fault', [ValueError('synthetic changed digest'), TimeoutError('synthetic transient read')])
def test_pl363_transient_audio_failure_remains_retryable_not_permanent_custody(store_backend, monkeypatch, fault):
    h = store_backend
    owner, _, _ = seed(h)
    recovery, artifacts, _, first, second = runner(h, monkeypatch)
    artifacts.fetch_audio.side_effect = fault
    for _ in range(2):
        with pytest.raises(type(fault)):
            recovery.recover('held', owner)
        job = read(h)
        assert job['recovery_state'] == 'prepared'
        assert not set(job['recovery']) & {'started_at', 'provider', 'refusal'}
        assert job['audio_uri'] == AUDIO
    assert artifacts.fetch_audio.call_count == 2
    first.assert_not_called()
    second.assert_not_called()


@pytest.mark.parametrize('method', ['hold_invalid_manifest', 'hold_duration_limit'])
@pytest.mark.parametrize('change', ['token', 'audio', 'running', 'lease', 'result', 'privacy'])
def test_pl105_pl363_refusal_cannot_settle_a_foreign_or_started_epoch(store_backend, method, change):
    h = store_backend
    owner, _, _ = seed(h)
    from database.batch_pipeline_quarantine_recovery import RecoveryStore

    protocol = RecoveryStore(h.store)
    prepared = protocol.prepare('held', owner, T0 + 1)
    token = prepared['recovery']['token']
    if change == 'token':
        token = 'synthetic-stale'
    elif change == 'audio':
        patch(h, {'audio_uri': AUDIO + '-changed'})
    elif change == 'running':
        assert protocol.start('held', token, T0 + 2)
    elif change == 'lease':
        patch(h, {'lease_until': T0 + 100})
    elif change == 'result':
        patch(h, {'result': {'outcome': 'success'}})
    elif change == 'privacy':
        h.customer.block_privacy(owner)
    before = deepcopy(read(h))
    kwargs = {'audio_uri': AUDIO}
    if method == 'hold_duration_limit':
        kwargs['audio_seconds'] = 61.0
    if change == 'privacy':
        with pytest.raises(BatchPrivacyBlocked):
            getattr(protocol, method)('held', token, T0 + 3, **kwargs)
    else:
        assert not getattr(protocol, method)('held', token, T0 + 3, **kwargs)
    assert read(h) == before


def test_lease_token_shape_does_not_release_held_custody(store_backend, monkeypatch):
    h = store_backend
    owner, binding, _ = seed(h)
    ref = h.customer.client.collection('users').document(owner).collection('conversations').document('visible')
    tokens = {
        's': {
            'pod': 'synthetic-pusher',
            'process_started_at': T0 - 86400,
            'last_signal_at': T0 - 7200,
            'lease_expires_at': T0 - 3600,
            'signal_source': 'frames',
        }
    }

    @firestore.transactional
    def attach(tx):
        tx.update(ref, {'record_upload_sessions': tokens})

    attach(h.customer.client.transaction())
    monkeypatch.setattr(intake, 'time', SimpleNamespace(time=lambda: T0 + 20))
    patch(h, {'status': 'partial', 'result': PARTIAL['result']}, 'content', f'{owner}/{binding.content_id}')
    assert intake.durable_status(h.store, owner, binding.job_id)['status'] != 'completed'
    assert ref.get().to_dict()['record_upload_sessions'] == tokens
    assert read(h)['audio_uri'] == AUDIO
