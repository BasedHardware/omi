"""Shadow isolation and distributed spend state on strict Firestore transactions."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock
from datetime import datetime, timezone

import pytest

from config import batch_pipeline_shadow as config
from config.policy import resolve_batch_policy
from database import batch_pipeline_store as storage
from database.batch_pipeline_shadow import ShadowStore, identity
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.batch_pipeline.artifacts import ArtifactStore
from utils.batch_pipeline.contracts import WorkItem, RecoveryWork
from utils.batch_pipeline.projection import Projector, ProjectionBlocked
from utils.batch_pipeline.scheduler import Scheduler
from utils.batch_pipeline.shadow_recovery import recover
from utils.batch_pipeline.recovery_disposition import MultilingualEmpty


@pytest.fixture
def repository(monkeypatch):
    # Production answers None (Deepgram retired 2026-08-27); the second-provider
    # machinery these shadows exercise stays covered under a named provider.
    from utils.batch_pipeline import quarantine_recovery as _qr

    monkeypatch.setattr(_qr, 'SECOND_PROVIDER', 'deepgram')
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_PERCENT', '100')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('BATCH_PIPELINE_TERMINAL_EMPTY_DISPOSITION_ENABLED', 'false')
    monkeypatch.setattr(storage, 'assert_batch_write_allowed', lambda *args, **kwargs: 0)
    store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=StrictFirestore())
    return ShadowStore(store, clock=lambda: 7200, busy=lambda: False)


def running(repository, name='one', *, duration=300):
    repository.offer('worker-' + name)
    reservation = repository.reserve('synthetic-owner', name, 'deep')
    assert reservation
    item = WorkItem(
        reservation[0], 'synthetic-owner', 1, 'encrypted:shadow', duration, 2, shadow=True, privacy_generation=0
    )
    assert repository.ready(reservation, item, '')
    assert repository.take('worker-' + name) == item
    assert repository.handoff(item.segment_id, RecoveryWork(item.segment_id, padded_retry='skipped_long_speech'))
    return item


def row(repository, segment):
    return repository.store.run(lambda tx: tx.get('shadow_jobs', segment))


def test_cohort_is_static_independent_and_disjoint(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_PERCENT', '30')
    monkeypatch.setattr(config, 'in_rollout_cohort', lambda uid, name, **kw: kw.get('legacy_all', False))
    selected = []
    for index in range(400):
        uid = f'synthetic-{index}'
        policy = resolve_batch_policy(uid, flags={'BATCH_PIPELINE_ENABLED': 'true', 'BATCH_PIPELINE_PERCENT': '25'})
        shadow = config.selected(uid, policy)
        assert not (shadow and policy.batch_enabled)
        assert shadow == config.selected(uid, policy)
        selected.append(shadow)
    assert 30 < sum(selected) < 140
    # An explicit remote membership cannot bypass the static hash or kill switch.
    monkeypatch.setattr(config, 'in_rollout_cohort', lambda uid, name, **kw: name == 'batch-pipeline-shadow')
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_PERCENT', '0')
    assert not config.selected('synthetic', SimpleNamespace(batch_enabled=False))


@pytest.mark.parametrize('value', ['0', '-1', 'nan', 'inf', '101', 'invalid'])
def test_invalid_or_disabled_percentage_denies(monkeypatch, value):
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_PERCENT', value)
    assert config.shadow_percent() == 0
    assert not config.selected('synthetic', SimpleNamespace(batch_enabled=False))


def test_busy_pool_drops_without_queue_or_legacy_mutations(repository):
    repository.offer('worker')
    repository.busy = lambda: True
    assert repository.reserve('synthetic', 'upload', 'fresh') is None
    result = row(repository, identity('synthetic', 'upload'))
    assert result['outcome'] == 'dropped'
    assert 'synthetic' not in repr(result)
    assert all(path[0].startswith('batch_pipeline_dev_shadow_') for path in repository.store.client.rows)


def test_only_four_offers_no_pending_queue_and_duplicate_suppression(repository):
    for index in range(5):
        repository.offer(str(index))
    assert len(repository.store.client.rows) == 4
    for index in range(4):
        assert repository.reserve('synthetic', str(index), 'recent')
    assert repository.reserve('synthetic', 'overflow', 'recent') is None
    assert row(repository, identity('synthetic', 'overflow'))['outcome'] == 'dropped'
    assert repository.reserve('synthetic', '0', 'recent') is None


def test_live_arrival_revokes_staging_offer(repository):
    repository.offer('worker')
    reservation = repository.reserve('synthetic', 'upload', 'fresh')
    repository.offer('worker', close=True)
    assert row(repository, reservation[0])['outcome'] == 'dropped'
    item = WorkItem(reservation[0], 'synthetic', 1, 'encrypted:shadow', 30, 2, shadow=True)
    assert not repository.ready(reservation, item, '')


def test_no_compute_after_offer_expiry_or_kill_switch(repository, monkeypatch):
    running(repository)
    repository.offer('worker')
    reservation = repository.reserve('synthetic', 'late', 'deep')
    repository.clock = lambda: 7400
    repository.offer('worker')
    assert row(repository, reservation[0])['outcome'] == 'dropped'
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_PERCENT', '0')
    assert repository.take('worker') is None
    assert repository.reserve('synthetic', 'off', 'deep') is None


def test_atomic_hourly_cap_shared_by_instances_and_each_provider(repository, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_PAID_RECOVERY_PER_HOUR', '2')
    first, second = running(repository, 'first'), running(repository, 'second')
    repository.start_recovery(first.segment_id)
    repository.start_recovery(second.segment_id)
    another = ShadowStore(repository.store, clock=repository.clock, busy=lambda: False)
    assert repository.paid(first.segment_id, 'modulate')
    assert not another.paid(first.segment_id, 'modulate')
    assert another.paid(first.segment_id, 'deepgram')
    assert not repository.paid(second.segment_id, 'modulate')
    another.clock = lambda: 10800
    assert not another.paid(first.segment_id, 'modulate')  # same intent, next hour
    assert another.paid(second.segment_id, 'modulate')
    assert not repository.start_recovery(first.segment_id)  # duplicate delivery


def test_cap_default_invalid_and_zero(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_SHADOW_PAID_RECOVERY_PER_HOUR', raising=False)
    assert config.paid_recovery_limit() == 200
    for value in ['bad', '-1', '0']:
        monkeypatch.setenv('BATCH_PIPELINE_SHADOW_PAID_RECOVERY_PER_HOUR', value)
        assert config.paid_recovery_limit() == 0


def test_uncertain_spend_reservation_denies_provider_permission(repository, monkeypatch):
    monkeypatch.setattr(repository.store, 'run', Mock(side_effect=RuntimeError('synthetic lost commit reply')))
    assert repository.paid('sh_uncertain', 'modulate') is False


def test_full_second_provider_recovery_writes_only_hashed_shadow_outcome(repository, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_SECOND_MULTILINGUAL_ENABLED', 'true')
    item = running(repository)
    artifacts = SimpleNamespace(fetch_audio=lambda _: b'private audio')
    spans = [{'start': 0.0, 'end': 300.0}]
    first = Mock(side_effect=MultilingualEmpty(300, spans))
    second = Mock(return_value={'words': [{'word': 'private transcript'}]})
    assert (
        recover(
            repository, artifacts, item.segment_id, stt=first, second_stt=second, inspect=lambda *a: (b'', 300, spans)
        )
        == 'recovered'
    )
    assert first.call_count == second.call_count == 1
    result = row(repository, item.segment_id)
    assert result['speech_seconds'] == 300 and result['speech_loss_seconds'] == 0
    assert 'synthetic-owner' not in repr(result) and 'private transcript' not in repr(result)
    assert all(path[0].startswith('batch_pipeline_dev_shadow_') for path in repository.store.client.rows)
    assert recover(repository, artifacts, item.segment_id, stt=first, second_stt=second) == 'held'
    assert first.call_count == second.call_count == 1


def test_failed_held_and_speech_loss(repository, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_SECOND_MULTILINGUAL_ENABLED', 'true')
    item = running(repository)
    spans = [{'start': 0.0, 'end': 300.0}]
    empty = Mock(side_effect=MultilingualEmpty(300, spans))
    assert (
        recover(
            repository,
            SimpleNamespace(fetch_audio=lambda _: b'audio'),
            item.segment_id,
            stt=empty,
            second_stt=empty,
            inspect=lambda *a: (b'', 300, spans),
        )
        == 'failed_held'
    )
    assert empty.call_count == 2
    assert row(repository, item.segment_id)['speech_loss_seconds'] == 300


def test_cap_records_paid_skipped_without_provider_call(repository, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_PAID_RECOVERY_PER_HOUR', '0')
    item = running(repository)
    provider = Mock()
    assert (
        recover(
            repository,
            SimpleNamespace(fetch_audio=lambda _: b'audio'),
            item.segment_id,
            stt=provider,
            inspect=lambda *a: (b'', 300, [{'start': 1, 'end': 20}]),
        )
        == 'paid_skipped'
    )
    provider.assert_not_called()
    assert row(repository, item.segment_id)['speech_loss_seconds'] == 19


def test_second_provider_requires_same_long_speech_handoff_as_live(repository):
    item = running(repository)
    repository.store.run(
        lambda tx: tx.put(
            'shadow_jobs',
            item.segment_id,
            {
                **tx.get('shadow_jobs', item.segment_id),
                'language': 'en',
                'worker_empty_evidence': {'padded_retry': 'empty', 'version': 1},
            },
        )
    )
    spans = [{'start': 0.0, 'end': 300.0}]
    first = Mock(side_effect=MultilingualEmpty(300, spans))
    second = Mock()
    assert (
        recover(
            repository,
            SimpleNamespace(fetch_audio=lambda _: b'audio'),
            item.segment_id,
            stt=first,
            second_stt=second,
            inspect=lambda *a: (b'', 300, spans),
        )
        == 'failed_held'
    )
    second.assert_not_called()


def test_shadow_terminal_empty_follows_pinned_recovery_policy(repository, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_TERMINAL_EMPTY_DISPOSITION_ENABLED', 'true')
    item = running(repository)
    spans = [{'start': 0.0, 'end': 300.0}]
    empty = Mock(side_effect=MultilingualEmpty(300, spans))
    assert (
        recover(
            repository,
            SimpleNamespace(fetch_audio=lambda _: b'audio'),
            item.segment_id,
            stt=empty,
            second_stt=empty,
            inspect=lambda *a: (b'', 300, spans),
        )
        == 'empty'
    )


@pytest.mark.parametrize('failed_provider', ['modulate', 'deepgram'])
def test_provider_failures_keep_the_live_failed_held_disposition(repository, failed_provider):
    item = running(repository)
    spans = [{'start': 0.0, 'end': 300.0}]
    first = Mock(
        side_effect=(
            RuntimeError('synthetic provider failure')
            if failed_provider == 'modulate'
            else MultilingualEmpty(300, spans)
        )
    )
    second = Mock(side_effect=RuntimeError('synthetic provider failure'))
    assert (
        recover(
            repository,
            SimpleNamespace(fetch_audio=lambda _: b'audio'),
            item.segment_id,
            stt=first,
            second_stt=second,
            inspect=lambda *a: (b'', 300, spans),
        )
        == 'failed_held'
    )
    assert second.call_count == (failed_provider == 'deepgram')


def test_active_recovery_reap_uses_its_start_time_and_transport_cannot_settle_it(repository, monkeypatch):
    from database import batch_pipeline_shadow as module

    item = running(repository)
    repository.clock = lambda: 11000
    repository.start_recovery(item.segment_id)
    monkeypatch.setattr(module, 'stale_jobs', lambda *args: [SimpleNamespace(id=item.segment_id)])
    repository.reap()
    repository.recovery_transport_failed(item.segment_id)
    assert row(repository, item.segment_id)['state'] == 'recovering'


def test_shadow_artifact_cleanup_removes_raw_owner_receipt(repository, monkeypatch):
    from utils.batch_pipeline import retention

    reference = Mock()
    artifact = SimpleNamespace(
        id='synthetic-artifact',  # integration's retention records touched ids for the A2 mirror refresh
        reference=reference,
        to_dict=lambda: {
            'owner_id': 'synthetic-owner',
            'conversation_ids': ['synthetic-conversation'],
            'shadow': True,
            'uri': 'synthetic:audio',
        },
    )
    monkeypatch.setattr(retention.queries, 'due_artifacts', lambda *args: [artifact])
    delete = Mock()
    assert retention.cleanup_completed_artifacts(repository.store, datetime.now(timezone.utc), delete_uri=delete) == 1
    delete.assert_called_once_with('synthetic-owner', 'synthetic:audio')
    reference.delete.assert_called_once()
    reference.update.assert_not_called()


def test_artifact_sink_cannot_persist_shadow_transcript(repository):
    item = running(repository)
    from utils.batch_pipeline.artifact_policy import shadow_result

    artifacts = ArtifactStore(
        Mock(),
        bucket='synthetic-bucket',
        namespace='batch_pipeline_dev',
        authorize=Mock(),
        key_for_owner=Mock(),
        register_artifact=Mock(),
        shadow_result=lambda work, payload: shadow_result(repository.store, work, payload),
    )
    artifacts._write = Mock(side_effect=AssertionError('no durable transcript writes'))
    assert artifacts.persist_result(item, {'words': [{'word': 'secret'}], 'speech_seconds': 20}).startswith('shadow:')
    artifacts._write.assert_not_called()
    artifacts.register_artifact.assert_not_called()
    assert 'secret' not in repr(repository.store.client.rows)
    with pytest.raises(PermissionError):
        artifacts.persist_recovery_result(item, {'words': []}, 'token')


def test_projection_and_normal_scheduler_refuse_shadow_before_any_side_effect():
    projector = object.__new__(Projector)
    for method in (projector._persist_read, projector._project_read, projector._assign, projector._finish):
        with pytest.raises(ProjectionBlocked, match='shadow'):
            method('segment', {'shadow': True}, {}, None)
    item = WorkItem('segment', 'synthetic', 1, 'encrypted:shadow', 30, 2, shadow=True)
    with pytest.raises(ValueError, match='shadow'):
        Scheduler.enqueue_in_transaction(Mock(), item, 0)


def test_pre_shadow_normal_job_duplicates_keep_their_immutable_identity():
    from tests.unit.test_batch_pipeline_scheduler import MemoryStore
    from copy import deepcopy

    store = MemoryStore()
    queue = Scheduler(store)
    work = WorkItem('normal-segment', 'synthetic', 1, 'encrypted:normal', 30, 2)
    assert queue.enqueue(work, 1)
    # Live documents stay identical to those persisted before this rollout.
    assert 'shadow' not in store.rows['jobs', work.segment_id]
    before = deepcopy(store.rows)
    assert queue.enqueue(work, 2) is False
    assert store.rows == before
