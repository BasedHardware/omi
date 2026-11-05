"""Deleted input without a tombstone settles without publishing its content."""

from copy import deepcopy
from dataclasses import asdict, replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config.policy import ProjectionPolicy
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection import ProjectionBlocked, ProjectionStore
from database.batch_pipeline_projection_session import SOURCE_DELETED_JOBS
from database.sync_ledger import sync_content_ledger_ref
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.batch_pipeline import projection, projection_disposition
from utils.batch_pipeline.contracts import ProjectionBinding, WorkItem, Priority
from utils.batch_pipeline.scheduler import owner_key
from utils.sync.capture import chunk_identity

FLAG = 'BATCH_PIPELINE_PROJECTION_SOURCE_DELETED_ENABLED'
POLICY = ProjectionPolicy()


@pytest.fixture
def lane(monkeypatch):
    from utils.batch_pipeline import retention

    monkeypatch.setattr(retention, 'expire_completed_segment', Mock(return_value=True))
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    monkeypatch.delenv(FLAG, raising=False)
    client = StrictFirestore()
    store = ProjectionStore(SimpleNamespace(client=client, namespace='source_deleted'))
    binding = ProjectionBinding('synthetic-owner', 'job', 'content', ('head',))
    work = WorkItem('head', binding.owner_id, 1000, 'gs://synthetic/audio', 4, Priority.DEEP, privacy_generation=0)
    user = client.collection('users').document(binding.owner_id)
    user.create({'data_protection_level': 'standard'})
    cid = chunk_identity(binding.owner_id, binding.source, binding.client_device_id, binding.is_locked, 1000)
    user.collection('conversations').document(cid).create({'deleted': True})
    result = {'outcome': 'success', 'result_uri': 'gs://synthetic/result'}
    store.ref('jobs', 'head').create(
        {
            **asdict(work),
            'projection_binding': asdict(binding),
            'result': result,
            'policy_parts': {'projection': POLICY.to_dict()},
        }
    )
    store.ref('results', 'head').create(
        {
            'protocol_version': 1,
            'segment_id': 'head',
            'owner_key': owner_key(binding.owner_id),
            'capture_at': 1000,
            'committed_at': 1000,
            'previous_segment_id': None,
            'projection_state': 'pending',
            'result': result,
        }
    )
    store.ref('owners', owner_key(binding.owner_id)).create({'projection_watermark': None})
    ledger_ref = sync_content_ledger_ref(client, binding.owner_id, binding.content_id)
    ledger_ref.create(
        {
            'dispatch_protocol': 'batch_v1',
            'status': 'processing',
            'job_id': binding.job_id,
            'batch_pipeline': {'protocol_version': 1, 'namespace': store.store.namespace, 'segment_ids': ['head']},
        }
    )
    return SimpleNamespace(**locals())


def settle(lane):
    return projection_disposition.persist_disposition(
        lane.store.session('head', lane.binding, 2000, policy=POLICY), privacy_deleted=True
    )


def test_default_on_terminal_receipt_completion_and_replay_never_publish_deleted_content(lane, monkeypatch):
    f = lane
    load, assign, publish, playback = Mock(), Mock(), Mock(), Mock()
    projector = projection.Projector(
        f.store.store,
        load,
        projection_store=f.store,
        assign_conversation=assign,
        publish=publish,
        playback=playback,
        clock=lambda: 2000,
    )
    job, entry, binding = f.store.read('head')
    before = deepcopy(f.client.rows)
    counter = SOURCE_DELETED_JOBS._value.get()
    # Fair-use dispatch is outside this privacy test; real accounting/completion
    # still prove that this disposition supplies zero speech and no usage deltas.
    record_speech = Mock()
    monkeypatch.setattr(projection, 'record_speech', record_speech)
    result = projector._project('head', job, entry, binding)
    receipt = f.store.ref('results', 'head').get().to_dict()['projection']
    assert receipt['state'] == 'ready' and receipt['disposition'] == 'source_deleted'
    assert receipt['conversation_id'] is None and receipt['speech_seconds'] == 0
    assert not receipt['audio_required'] and not receipt['enrichment_required']
    assert SOURCE_DELETED_JOBS._value.get() == counter + 1
    assert f.store.projection_watermark(owner_key(binding.owner_id)) == 'head'
    # A ready receipt needs no playback, enrichment or content assignment.
    projector.finish_part(f.work, binding, receipt, None, policy=POLICY)
    load.assert_not_called()
    assign.assert_not_called()
    playback.assert_not_called()
    assert {k: v for k, v in f.client.rows.items() if k[:1] == ('users',) and 'conversations' in k} == {
        k: v for k, v in before.items() if k[:1] == ('users',) and 'conversations' in k
    }
    # The real completion publishes only an empty terminal status.
    accounting = f.store.prepare_accounting(binding, 2000)
    assert accounting['seconds'] == 0 and accounting['updates'] == {}
    record_speech.assert_called_once()
    assert record_speech.call_args.args[0] == binding
    assert record_speech.call_args.args[1]['seconds'] == 0
    assert record_speech.call_args.args[1]['updates'] == {}
    assert result['reason_code'] == 'source_deleted'
    assert result['new_memories'] == result['updated_memories'] == []
    assert f.ledger_ref.get().to_dict()['status'] == 'completed'
    assert f.store.ref('jobs', 'head').get().to_dict()['client_status'] == 'completed'
    publish.assert_called_once_with(binding, result)
    assert settle(f) == receipt
    assert SOURCE_DELETED_JOBS._value.get() == counter + 1
    assert f.store.complete('head', binding, 2001, accounting, policy=POLICY) == result


def test_kill_switch_off_restores_block_without_writes_or_counter(lane, monkeypatch):
    monkeypatch.setenv(FLAG, 'false')
    before = deepcopy(lane.client.rows)
    counter = SOURCE_DELETED_JOBS._value.get()
    with pytest.raises(ProjectionBlocked, match='requires a source deletion tombstone'):
        settle(lane)
    assert lane.client.rows == before
    assert SOURCE_DELETED_JOBS._value.get() == counter


@pytest.mark.parametrize('case', ['tombstone', 'redirect', 'redirect_deleted', 'redirect_missing', 'live', 'absent'])
def test_other_privacy_cases_unchanged(lane, case):
    f = lane
    source = f.user.collection('conversations').document(f.cid)
    if case == 'tombstone':
        f.user.collection('deleted_conversations').document(f.cid).create({})
    elif case.startswith('redirect'):
        f.client.rows[source.path]['sync_merged_into'] = 'survivor'
        if case != 'redirect_missing':
            f.user.collection('conversations').document('survivor').create({'deleted': case == 'redirect_deleted'})
    elif case == 'live':
        f.client.rows[source.path]['deleted'] = False
    else:
        f.client.rows.pop(source.path)
    before = deepcopy(f.client.rows)
    counter = SOURCE_DELETED_JOBS._value.get()
    if case == 'tombstone':
        receipt = settle(f)
        assert receipt['disposition'] == 'superseded' and receipt['privacy_reason'] == 'conversation_deleted'
    elif case == 'redirect_missing':
        with pytest.raises(BatchPrivacyBlocked, match='conversation_redirect_missing'):
            settle(f)
        assert f.client.rows == before
    else:
        with pytest.raises(ProjectionBlocked, match='requires a source deletion tombstone'):
            settle(f)
        assert f.client.rows == before
        if case in {'redirect', 'live', 'absent'}:
            f.store.check(f.store.session('head', f.binding, 2000, policy=POLICY))
    assert SOURCE_DELETED_JOBS._value.get() == counter


@pytest.mark.parametrize('change', ['account', 'generation', 'binding', 'ledger', 'predecessor'])
def test_source_deleted_cannot_bypass_other_fences(lane, change):
    f = lane
    if change == 'account':
        f.client.collection('account_deletions').document(f.binding.owner_id).create({})
    elif change == 'generation':
        f.client.rows[('source_deleted_jobs', 'head')]['privacy_generation'] = 1
    elif change == 'binding':
        f.client.rows[('source_deleted_jobs', 'head')]['owner_id'] = 'foreign'
    elif change == 'ledger':
        f.client.rows[f.ledger_ref.path]['job_id'] = 'foreign'
    else:
        f.client.rows[('source_deleted_results', 'head')]['previous_segment_id'] = 'unsettled'
    before = deepcopy(f.client.rows)
    counter = SOURCE_DELETED_JOBS._value.get()
    with pytest.raises((ProjectionBlocked, BatchPrivacyBlocked)):
        settle(f)
    assert f.client.rows == before
    assert SOURCE_DELETED_JOBS._value.get() == counter


def test_source_deleted_proof_never_authorizes_content_assignment(lane):
    session = lane.store.session('head', lane.binding, 2000, policy=POLICY)
    transaction = lane.client.transaction()
    session.prepare(transaction, privacy_deleted=True)
    for options in ({}, {'privacy_deleted': True, 'superseded': True}):
        with pytest.raises(ProjectionBlocked, match='cannot assign content'):
            session.persist(transaction, ({'id': 'forbidden'}, True, []), **options)
    assert not transaction.has_written


@pytest.mark.parametrize('last_tombstoned', [False, True])
def test_multipart_counts_one_terminal_job_only_after_last_part(lane, last_tombstoned):
    f = lane
    counter = SOURCE_DELETED_JOBS._value.get()
    for index in range(2):
        if index and last_tombstoned:
            f.user.collection('deleted_conversations').document(f.cid).create({})
        session = f.store.session('head', f.binding, 2000, policy=POLICY, part_index=index, part_count=2)
        session.total_speech_seconds = 4
        session.speech_seconds = 2
        receipt = projection_disposition.persist_disposition(session, privacy_deleted=True)
        assert receipt['state'] == 'ready' and receipt['conversation_id'] is None
        assert SOURCE_DELETED_JOBS._value.get() == counter + index
    entry = f.store.ref('results', 'head').get().to_dict()
    assert entry['projection_state'] == 'ready'
    assert entry['projection']['disposition'] == 'source_deleted'
    assert entry['projection']['speech_seconds'] == 0
    assert settle(f)['disposition'] == 'source_deleted'
    assert SOURCE_DELETED_JOBS._value.get() == counter + 1


@pytest.mark.parametrize('target_field', ['binding', 'job'])
def test_deleted_destination_does_not_impersonate_deleted_original_source(lane, target_field):
    f = lane
    f.client.rows[('users', f.binding.owner_id, 'conversations', f.cid)]['deleted'] = False
    f.user.collection('conversations').document('deleted-target').create({'deleted': True})
    job = f.client.rows[('source_deleted_jobs', 'head')]
    if target_field == 'binding':
        f.binding = replace(f.binding, target_conversation_id='deleted-target')
        job['projection_binding'] = asdict(f.binding)
    else:
        job['conversation_id'] = 'deleted-target'
    before = deepcopy(f.client.rows)
    counter = SOURCE_DELETED_JOBS._value.get()
    with pytest.raises(ProjectionBlocked, match='requires a source deletion tombstone'):
        settle(f)
    assert f.client.rows == before
    assert SOURCE_DELETED_JOBS._value.get() == counter
