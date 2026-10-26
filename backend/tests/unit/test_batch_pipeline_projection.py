"""Projection binding validation and provider-free retry/publication guards."""

from dataclasses import replace
from config.policy import BatchUnitPolicy, ProjectionPolicy, resolve_batch_policy, resolve_stage_policy
import logging
from unittest.mock import Mock

from google.api_core.exceptions import Aborted, InvalidArgument
import pytest

from utils.batch_pipeline.contracts import ProjectionBinding
from database.batch_pipeline_projection import ProjectionStore
from utils.batch_pipeline import projection
from utils.sync import bridge


@pytest.fixture
def binding():
    return ProjectionBinding('synthetic-owner', 'job', 'content', ('segment',))


@pytest.mark.parametrize(
    'field,value',
    [
        ('segment_ids', ()),
        ('segment_ids', ('same', 'same')),
        ('segment_ids', tuple(str(n) for n in range(129))),
        ('owner_id', ''),
        ('content_id', 'path/id'),
        ('data_protection_level', 'e2ee'),
        ('run_token', 'without-epoch'),
        ('privacy_generation', -1),
    ],
)
def test_invalid_projection_binding_refused(binding, field, value):
    with pytest.raises(ValueError):
        replace(binding, **{field: value})


def test_read_contention_retry_uses_fresh_transactions_when_enabled(monkeypatch):
    monkeypatch.setenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'true')
    from database import firestore_transaction_retry

    actual = firestore_transaction_retry.run_with_transaction_contention_retry

    def fast(*args, **kwargs):
        return actual(*args, **kwargs, sleep=lambda _: None)

    monkeypatch.setattr(firestore_transaction_retry, 'run_with_transaction_contention_retry', fast)
    client = Mock()
    client.transaction.side_effect = [object(), object()]
    operation = Mock(side_effect=[Aborted('synthetic'), 'persisted'])
    store = ProjectionStore(Mock(client=client))
    assert store.run(operation, policy=resolve_stage_policy('synthetic-owner', 'projection')) == 'persisted'
    assert operation.call_args_list[0] != operation.call_args_list[1]


def test_read_contention_default_off_and_non_contention_never_replayed(monkeypatch):
    monkeypatch.delenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', raising=False)
    client = Mock()
    operation = Mock(side_effect=Aborted('synthetic'))
    store = ProjectionStore(Mock(client=client))
    with pytest.raises(Aborted):
        store.run(operation)
    assert operation.call_count == 1
    monkeypatch.setenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'true')
    operation = Mock(side_effect=InvalidArgument('not contention'))
    with pytest.raises(InvalidArgument):
        store.run(operation)
    assert operation.call_count == 1


def test_custom_enrichment_mutation_cannot_bypass_runtime_stage_guard(monkeypatch):
    from utils.sync import reprocess

    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    mutate = Mock()
    with pytest.raises(RuntimeError, match='production or a Firestore emulator'):
        reprocess.mark('synthetic-owner', 'conversation', 'en', mutate=mutate)
    mutate.assert_not_called()


@pytest.mark.parametrize(
    'spans',
    [
        None,
        [],
        [{'start': 2, 'end': 1}],
        [{'start': 0, 'end': float('nan')}],
        [{'start': -1, 'end': 1}],
        [{'start': 0, 'end': 5}],
        [{'start': 0, 'end': 2}, {'start': 1, 'end': 3}],
    ],
)
def test_original_vad_span_contract_rejects_invalid_or_noncanonical_union(spans):
    from utils.batch_pipeline.contracts import projection_speech_spans

    with pytest.raises(ValueError):
        projection_speech_spans({'speech_spans': spans, 'speech_seconds': 2}, 4)


def test_original_vad_union_must_agree_with_speech_metering():
    from utils.batch_pipeline.contracts import projection_speech_spans

    payload = {'speech_spans': [{'start': 0, 'end': 1}, {'start': 150, 'end': 151}], 'speech_seconds': 2}
    assert projection_speech_spans(payload, 160) == payload['speech_spans']
    payload['speech_seconds'] = 3
    with pytest.raises(ValueError, match='accounting'):
        projection_speech_spans(payload, 160)


def test_production_result_cannot_invent_vad_groups_from_transcript_gaps():
    from utils.batch_pipeline.contracts import WorkItem, Priority
    from utils.batch_pipeline.projection_parts import split_result

    item = WorkItem(
        'segment', 'synthetic-owner', 0, 'gs://synthetic/wav', 200, Priority.FRESH, requires_compute_admission=True
    )
    payload = {'audio_seconds': 200, 'words': [{'word': 'Text.', 'timestamp': [0, 1]}]}
    with pytest.raises(ValueError, match='speech_spans'):
        split_result(item, payload)


@pytest.mark.parametrize('bound', [False, True])
def test_projection_enrichment_and_receipt_share_transaction_on_unbound_host(binding, monkeypatch, bound):
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
    from utils.sync import reprocess

    client = StrictFirestore()
    store = ProjectionStore(Mock(client=client))
    receipt_ref = client.collection('receipts').document('segment')
    receipt_ref.create({'state': 'persisted'})
    session = Mock()
    session.job = {'priority': 0}
    session.prepare.side_effect = lambda transaction, **_: receipt_ref.get(transaction=transaction)
    session.guard.side_effect = lambda transaction, _: receipt_ref.get(transaction=transaction)
    session.receipt.return_value = {'state': 'persisted'}
    session.write_receipt.side_effect = lambda transaction, receipt: transaction.set(receipt_ref, receipt)
    monkeypatch.setattr(store, 'session', lambda *a, **k: session)
    monkeypatch.setattr(store, 'run', lambda operation, **kwargs: operation(client.transaction()))
    monkeypatch.setattr(reprocess, 'owns_runtime', lambda: True)
    monkeypatch.setenv('SYNC_TASKS_QUEUE', 'sync-jobs' if bound else '')
    monkeypatch.setenv('SYNC_TASKS_HANDLER_URL', 'https://fresh.invalid/v2/sync-jobs/run')
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'invoker@example.invalid')
    monkeypatch.delenv('SYNC_TASKS_OIDC_AUDIENCE', raising=False)
    enqueue = Mock()

    def after_commit(row):
        assert receipt_ref.get().to_dict()['state'] == 'ready'
        assert client.collection(reprocess.COLLECTION).document(reprocess.key(binding.owner_id, 'c')).get().exists
        enqueue(row)

    monkeypatch.setattr(reprocess, '_enqueue', after_commit)
    store.mark_enrichment('segment', binding, 0, 'c', 'en', policy=ProjectionPolicy())
    transaction = client.transactions[0]
    assert [path for path, _ in transaction.sets] == [
        (reprocess.COLLECTION, reprocess.key(binding.owner_id, 'c')),
        ('receipts', 'segment'),
    ]
    outbox = transaction.sets[0][1]
    assert '_wake' not in outbox
    assert (outbox['dispatch'] is not None) == bound
    assert enqueue.call_count == int(bound)
    session.guard.assert_called_once_with(transaction, ['c'])
    session.receipt.return_value = {'state': 'ready'}
    store.mark_enrichment('segment', binding, 1, 'c', 'en', policy=ProjectionPolicy())
    assert not client.transactions[1].sets
    assert enqueue.call_count == int(bound)
    assert (
        client.collection(reprocess.COLLECTION)
        .document(reprocess.key(binding.owner_id, 'c'))
        .get()
        .to_dict()['version']
        == 1
    )


@pytest.mark.parametrize('invalid_field', ['audience', 'invoker_sa'])
def test_projection_cannot_override_mark_with_poison_backfill_binding(binding, monkeypatch, invalid_field):
    from database.batch_pipeline_projection import ProjectionBlocked
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
    from utils.sync import reprocess

    client = StrictFirestore()
    store = ProjectionStore(Mock(client=client))
    session = Mock()
    session.job = {'priority': 1}
    session.receipt.return_value = {'state': 'persisted'}
    monkeypatch.setattr(store, 'session', lambda *a, **k: session)
    monkeypatch.setattr(store, 'run', lambda operation, **kwargs: operation(client.transaction()))
    monkeypatch.setattr(reprocess, 'owns_runtime', lambda: True)
    monkeypatch.setenv('SYNC_BACKFILL_ROUTING_ENABLED', 'true')
    monkeypatch.setenv('SYNC_BACKFILL_TASKS_QUEUE', 'sync-backfill')
    monkeypatch.setenv('SYNC_BACKFILL_TASKS_HANDLER_URL', 'https://backfill.invalid/v2/sync-jobs/run')
    monkeypatch.setenv('SYNC_BACKFILL_TASKS_OIDC_AUDIENCE', 'https://backfill.invalid/v2/sync-jobs/run')
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'invoker@example.invalid')
    monkeypatch.setenv(
        'SYNC_BACKFILL_TASKS_OIDC_AUDIENCE' if invalid_field == 'audience' else 'SYNC_TASKS_INVOKER_SA',
        'https://sibling.invalid/v2/sync-jobs/run' if invalid_field == 'audience' else '',
    )
    with pytest.raises(ProjectionBlocked, match='complete backfill'):
        store.mark_enrichment('segment', binding, 0, 'c', 'en', policy=ProjectionPolicy())
    assert not client.transactions[0].sets
    session.write_receipt.assert_not_called()


@pytest.mark.parametrize(
    'flag', ['SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'BATCH_PIPELINE_PROJECTION_CONTENTION_ENABLED']
)
def test_batch_contention_control_retries_projection_transactions(monkeypatch, flag):
    from database import firestore_transaction_retry

    monkeypatch.delenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', raising=False)
    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_CONTENTION_ENABLED', raising=False)
    monkeypatch.setenv(flag, 'true')
    actual = firestore_transaction_retry.run_with_transaction_contention_retry
    monkeypatch.setattr(
        firestore_transaction_retry,
        'run_with_transaction_contention_retry',
        lambda *args, **kwargs: actual(*args, **kwargs, sleep=lambda _: None),
    )
    client = Mock()
    client.transaction.side_effect = [object(), object()]
    operation = Mock(side_effect=[Aborted('synthetic'), 'persisted'])
    assert (
        ProjectionStore(Mock(client=client)).run(
            operation, policy=resolve_stage_policy('synthetic-owner', 'projection')
        )
        == 'persisted'
    )
    assert operation.call_count == 2


@pytest.fixture
def claim_redis(monkeypatch):
    import fakeredis
    from database import batch_pipeline_projection_claim as claims

    redis = fakeredis.FakeRedis()
    redis.eval('return 1', 0)  # Load the Lua emulator in harness setup.
    claims._redis_client.cache_clear()
    factory = Mock(return_value=redis)
    monkeypatch.setattr(claims.redis_db, 'create_bounded_redis_client', factory)
    try:
        yield redis
        factory.assert_called_once_with(1.0)
    finally:
        claims._redis_client.cache_clear()


def test_owner_claim_is_shared_token_fenced_with_bounded_ttl(monkeypatch, claim_redis):
    from database import batch_pipeline_projection_claim as claims

    redis = claim_redis
    with claims.projection_claim('synthetic', 'owner') as first:
        assert first
        assert 0 < redis.ttl('batch_projection:synthetic:owner') <= claims.LEASE_SECONDS
        with claims.projection_claim('synthetic', 'owner') as second:
            assert not second
        # A timed-out caller must never release the replacement's token.
        redis.set('batch_projection:synthetic:owner', 'replacement', ex=300)
    assert redis.get('batch_projection:synthetic:owner') == b'replacement'
    redis.delete('batch_projection:synthetic:owner')
    with pytest.raises(RuntimeError):
        with claims.projection_claim('synthetic', 'owner') as acquired:
            assert acquired
            raise RuntimeError('synthetic interruption')
    assert not redis.exists('batch_projection:synthetic:owner')


def test_claim_redis_unavailable_keeps_firestore_as_authority(monkeypatch):
    from database import batch_pipeline_projection_claim as claims

    redis = Mock()
    redis.set.side_effect = ConnectionError('synthetic')
    monkeypatch.setattr(claims, '_redis_client', lambda: redis)
    with claims.projection_claim('synthetic', 'owner') as acquired:
        assert acquired


def test_default_off_projection_uses_one_existing_read_and_no_claim(monkeypatch):
    from types import SimpleNamespace
    from utils.batch_pipeline import projection

    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_CONTENTION_ENABLED', raising=False)
    claim = Mock(side_effect=AssertionError('dark flag touched Redis'))
    monkeypatch.setattr(projection, 'projection_claim', claim)
    projector = projection.Projector(Mock(), Mock())
    projector.store = Mock()
    job, entry, binding = (
        {'policy_parts': {'projection': ProjectionPolicy().to_dict()}},
        {},
        SimpleNamespace(owner_id='synthetic-owner', policy=BatchUnitPolicy()),
    )
    projector.store.read.return_value = (job, entry, binding)
    projector._project = Mock(return_value={'outcome': 'success'})
    assert projector.project('synthetic-segment') == {'outcome': 'success'}
    projector.store.read.assert_called_once_with('synthetic-segment')
    projector._project.assert_called_once_with('synthetic-segment', job, entry, binding, hint=None)
    claim.assert_not_called()


def test_dark_control_preserves_empty_race_failure_boundary(monkeypatch, binding):
    from dataclasses import asdict
    from utils.batch_pipeline.contracts import WorkItem, Priority
    from utils.batch_pipeline.projection import Projector
    from database.batch_pipeline_projection import ProjectionReplay

    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_CONTENTION_ENABLED', raising=False)
    projector = Projector(Mock(), Mock())
    projector.store = Mock()
    projector.store.session.return_value.persist_empty.side_effect = ProjectionReplay({'state': 'persisted'})
    item = WorkItem('segment', binding.owner_id, 0, 'gs://synthetic/audio', 1, Priority.DEEP)
    with pytest.raises(ProjectionReplay):
        projector._project(
            'segment',
            {**asdict(item), 'policy_parts': {'projection': ProjectionPolicy().to_dict()}},
            {'result': {'outcome': 'silence'}},
            binding,
        )
    projector.store.complete.assert_not_called()


@pytest.mark.parametrize(
    'flag', ['SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'BATCH_PIPELINE_PROJECTION_CONTENTION_ENABLED']
)
def test_contention_control_retains_existing_expired_transaction_restart(monkeypatch, flag):
    monkeypatch.delenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', raising=False)
    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_CONTENTION_ENABLED', raising=False)
    monkeypatch.setenv(flag, 'true')
    client = Mock()
    client.transaction.side_effect = [object(), object()]
    operation = Mock(
        side_effect=[InvalidArgument('The referenced transaction has expired or is no longer valid'), 'persisted']
    )
    assert (
        ProjectionStore(Mock(client=client)).run(
            operation, policy=resolve_stage_policy('synthetic-owner', 'projection')
        )
        == 'persisted'
    )
    assert operation.call_count == client.transaction.call_count == 2
    assert operation.call_args_list[0] != operation.call_args_list[1]


@pytest.mark.parametrize('enabled', [False, True])
def test_phase_timing_preserves_playback_retry_and_never_logs_private_error(binding, monkeypatch, caplog, enabled):

    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_TIMING_ENABLED', str(enabled).lower())
    policy = resolve_stage_policy(binding.owner_id, 'projection')
    monkeypatch.setattr(bridge, 'finish_sync_bridges', lambda *_, **kw: 'synthetic-conversation')
    playback = Mock(side_effect=ValueError('private-error-must-never-be-logged'))
    projector = projection.Projector(Mock(), Mock(), playback=playback)
    receipt = {
        'state': 'persisted',
        'conversation_id': 'synthetic-conversation',
        'audio_required': True,
        'enrichment_required': True,
    }
    mark = Mock()
    monkeypatch.setattr(projector.store, 'mark_enrichment', mark)
    with caplog.at_level(logging.INFO, logger=projection.__name__):
        with pytest.raises(ValueError, match='private-error'):
            projector.finish_part(Mock(), binding, receipt, None, policy=policy)
    mark.assert_not_called()  # Playback failure retains its durable retry obligation.
    text = caplog.text
    assert 'private-error-must-never-be-logged' not in text
    assert 'synthetic-conversation' not in text
    if enabled:
        assert 'phase=bridge outcome=completed elapsed_ms=' in text
        assert 'phase=playback outcome=started' in text
        assert 'phase=playback outcome=error elapsed_ms=' in text
        assert 'exception_type=ValueError' in text
    else:
        assert 'event=batch_projection_phase' not in text


@pytest.mark.parametrize('finish', [False, True])
@pytest.mark.parametrize('failure', ['superseded', 'conflict'])
def test_assignment_supersession_settles_part_but_conflicts_still_retry(binding, monkeypatch, finish, failure):
    from utils.batch_pipeline.contracts import WorkItem, Priority
    from utils.sync.assignment_errors import SyncAssignmentSuperseded, SyncAssignmentConflict

    item = WorkItem('segment', binding.owner_id, 0, 'gs://synthetic/audio', 1, Priority.DEEP)
    payload = {
        'words': [{'word': 'Fixture.', 'timestamp': [0, 1]}],
        'audio_seconds': 1,
        'speech_seconds': 1,
        'diarization': {'turns': []},
    }
    projector = projection.Projector(Mock(), Mock(return_value=payload))
    projector.store = Mock()
    session = projector.store.session.return_value
    receipt = {'state': 'ready', 'disposition': 'superseded', 'conversation_id': None, 'speech_seconds': 0.0}
    session.persist_empty.return_value = receipt
    projector.finish_part = Mock()
    monkeypatch.setattr(
        projection,
        'build_incoming',
        lambda *a, **k: {
            'started_at': Mock(timestamp=lambda: 0),
            'finished_at': Mock(timestamp=lambda: 1),
            'transcript_segments': [{'speaker_id_scope': 'sync:fixture'}],
        },
    )
    monkeypatch.setattr(projection.conversations_db, 'get_closest_conversation_to_timestamps', lambda *a: None)
    error = (
        SyncAssignmentSuperseded('private fixture reason')
        if failure == 'superseded'
        else SyncAssignmentConflict('fixture')
    )
    assign = Mock(side_effect=error)
    monkeypatch.setattr(projection.conversations_db, 'assign_sync_conversation', assign)
    if failure == 'conflict':
        with pytest.raises(SyncAssignmentConflict):
            projector.assign_parts(item, {'result': {'result_uri': 'fixture'}}, binding, finish=finish)
        session.persist_empty.assert_not_called()
    else:
        projector.assign_parts(item, {'result': {'result_uri': 'fixture'}}, binding, finish=finish)
        session.persist_empty.assert_called_once_with(superseded=True)
        assert session.speech_seconds == session.total_speech_seconds == 1
        assert projector.finish_part.call_count == int(finish)


def test_supersession_losing_assignment_race_preserves_committed_receipt(binding):
    from database.batch_pipeline_projection import ProjectionReplay

    projector = projection.Projector(Mock(), Mock())
    winner = {'state': 'persisted', 'conversation_id': 'synthetic-winner', 'speech_seconds': 4}
    session = Mock()
    session.persist_empty.side_effect = ProjectionReplay(winner)
    assert projector.supersede(session) == winner


def test_supersession_cannot_bypass_privacy_fence(binding):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    projector = projection.Projector(Mock(), Mock())
    session = Mock()
    session.persist_empty.side_effect = BatchPrivacyBlocked('privacy_generation_changed')
    with pytest.raises(BatchPrivacyBlocked):
        projector.supersede(session)


@pytest.mark.parametrize('reason', ['conversation_fence_budget', 'conversation_deleted', 'private-text-not-a-reason'])
def test_assignment_privacy_fence_logs_bounded_reason(binding, monkeypatch, caplog, reason):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked
    from utils.batch_pipeline.contracts import WorkItem, Priority

    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_CONTENTION_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_TIMING_ENABLED', 'true')
    policy = resolve_stage_policy(binding.owner_id, 'projection')
    item = WorkItem('segment', binding.owner_id, 0, 'gs://synthetic/audio', 1, Priority.DEEP)
    payload = {
        'words': [{'word': 'Fixture.', 'timestamp': [0, 1]}],
        'audio_seconds': 1,
        'speech_seconds': 1,
        'diarization': {'turns': []},
    }
    projector = projection.Projector(Mock(), Mock(return_value=payload))
    projector.store = Mock()
    monkeypatch.setattr(
        projection,
        'build_incoming',
        lambda *a, **k: {
            'started_at': Mock(timestamp=lambda: 0),
            'finished_at': Mock(timestamp=lambda: 1),
            'transcript_segments': [{'speaker_id_scope': 'sync:fixture'}],
        },
    )
    monkeypatch.setattr(projection.conversations_db, 'get_closest_conversation_to_timestamps', lambda *a: None)
    monkeypatch.setattr(
        projection.conversations_db, 'assign_sync_conversation', Mock(side_effect=BatchPrivacyBlocked(reason))
    )
    with caplog.at_level(logging.INFO, logger=projection.__name__):
        with pytest.raises(BatchPrivacyBlocked):
            with projection.projection_phase('assignment', policy):
                projector.assign_parts(item, {'result': {'result_uri': 'fixture'}}, binding, policy=policy)
    expected = reason if reason != 'private-text-not-a-reason' else 'unknown'
    text = caplog.text
    assert f'action=assignment outcome=error exception_type=BatchPrivacyBlocked fence_reason={expected}' in text
    assert f'phase=assignment outcome=error' in text
    assert text.count(f'fence_reason={expected}') == 2
    assert 'private-text' not in text
    assert binding.owner_id not in text


def test_non_privacy_errors_log_no_fence_reason(caplog):
    policy = Mock(projection_timing=True)
    with caplog.at_level(logging.INFO, logger=projection.__name__):
        with pytest.raises(ValueError):
            with projection.projection_phase('assignment', policy):
                raise ValueError('private')
    assert 'exception_type=ValueError' in caplog.text
    assert 'fence_reason' not in caplog.text


def test_stamp_gap_reroute_reports_lineage_telemetry_after_batch_commit(binding, monkeypatch, caplog):
    from utils.batch_pipeline.contracts import WorkItem, Priority

    item = WorkItem('segment', binding.owner_id, 0, 'gs://synthetic/audio', 1, Priority.DEEP)
    payload = {
        'words': [{'word': 'Fixture.', 'timestamp': [0, 1]}],
        'audio_seconds': 1,
        'speech_seconds': 1,
        'diarization': {'turns': []},
    }
    projector = projection.Projector(Mock(), Mock(return_value=payload))
    projector.store = Mock()
    session = projector.store.session.return_value
    monkeypatch.setattr(
        projection,
        'build_incoming',
        lambda *a, **k: {
            'started_at': Mock(timestamp=lambda: 0),
            'finished_at': Mock(timestamp=lambda: 1),
            'transcript_segments': [{'speaker_id_scope': 'sync:fixture'}],
        },
    )
    monkeypatch.setattr(projection.conversations_db, 'get_closest_conversation_to_timestamps', lambda *a: None)
    assigned = {'id': 'synthetic-neighbour', '_sync_lineage_stamp_gap_refused': True}

    def committed(*args, after_assign, **kwargs):
        planned = (assigned, False, [])
        after_assign(Mock(), planned)
        return planned

    monkeypatch.setattr(projection.conversations_db, 'assign_sync_conversation', committed)
    with caplog.at_level(logging.INFO):
        projector.assign_parts(item, {'result': {'result_uri': 'fixture'}}, binding, finish=False)
    session.persist.assert_called_once()
    assert 'event=sync_lineage_stamp_append outcome=stamp_gap_refused span_delta_bucket=0' in caplog.text
    assert 'synthetic-neighbour' not in caplog.text
    assert '_sync_lineage_stamp_gap_refused' not in assigned
