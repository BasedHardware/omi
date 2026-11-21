"""Deleted input without a tombstone settles without publishing its content."""

from copy import deepcopy
from dataclasses import asdict, replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config.policy import ProjectionPolicy
from database import batch_pipeline_projection as projection_database
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection import ProjectionBlocked, ProjectionStore
from database.batch_pipeline_projection_session import SOURCE_DELETED_JOBS
from database.sync_ledger import BATCH_PARTIAL_STATUS, sync_content_ledger_ref
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
    from utils.sync import bridge

    monkeypatch.setattr(retention, 'expire_completed_segment', Mock(return_value=True))
    monkeypatch.setattr(bridge, 'finish_sync_bridges', lambda uid, cid, **kwargs: cid)
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    monkeypatch.delenv(FLAG, raising=False)
    client = StrictFirestore()
    store = ProjectionStore(SimpleNamespace(client=client, namespace='source_deleted'))
    usage_cache_writing = Mock(wraps=projection_database.writing)
    monkeypatch.setattr(projection_database, 'writing', usage_cache_writing)
    commit_usage = Mock(wraps=store._commit_usage)
    monkeypatch.setattr(store, '_commit_usage', commit_usage)
    record_speech, record_speech_steps = Mock(), Mock()
    monkeypatch.setattr(projection, 'record_speech', record_speech)
    monkeypatch.setattr(projection, 'record_speech_steps', record_speech_steps)
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
    before_usage = usage_snapshot(f)
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
    # The real completion returns an empty terminal status without publishing.
    accounting = f.store.prepare_accounting(binding, 2000)
    assert accounting['seconds'] == 0 and accounting['updates'] == {}
    assert_no_usage(f, before_usage)
    assert result['reason_code'] == 'source_deleted'
    assert result['new_memories'] == result['updated_memories'] == []
    assert f.ledger_ref.get().to_dict()['status'] == 'completed'
    assert f.store.ref('jobs', 'head').get().to_dict()['client_status'] == 'completed'
    publish.assert_not_called()
    assert settle(f) == receipt
    assert SOURCE_DELETED_JOBS._value.get() == counter + 1
    assert f.store.complete('head', binding, 2001, accounting, policy=POLICY) == result
    assert_no_usage(f, before_usage)
    assert SOURCE_DELETED_JOBS._value.get() == counter + 1


def test_kill_switch_off_restores_block_without_writes_or_counter(lane, monkeypatch):
    monkeypatch.setenv(FLAG, 'false')
    before = deepcopy(lane.client.rows)
    counter = SOURCE_DELETED_JOBS._value.get()
    projector = make_projector(lane, monkeypatch)
    job, entry, binding = lane.store.read('head')
    with pytest.raises(ProjectionBlocked, match='requires a source deletion tombstone'):
        projector._project('head', job, entry, binding)
    projector.publish.assert_not_called()
    assert_no_usage(lane, usage_snapshot(lane))
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
        assert SOURCE_DELETED_JOBS._value.get() == counter
    entry = f.store.ref('results', 'head').get().to_dict()
    assert entry['projection_state'] == 'ready'
    assert entry['projection']['disposition'] == 'source_deleted'
    assert entry['projection']['speech_seconds'] == 0
    assert settle(f)['disposition'] == 'source_deleted'
    assert SOURCE_DELETED_JOBS._value.get() == counter
    projector = make_projector(f, f.monkeypatch)
    result = projector.complete_content('head', f.binding, policy=POLICY)
    assert result['reason_code'] == 'source_deleted'
    projector.publish.assert_not_called()
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


def usage_snapshot(lane):
    return deepcopy(
        {
            'users': {
                key: value
                for key, value in lane.client.rows.items()
                if key[0] == 'users' and key != lane.ledger_ref.path and (len(key) == 2 or key[2] != 'conversations')
            },
            'ledger': {key: value for key, value in lane.ledger_ref.get().to_dict().items() if key.startswith('usage')},
        }
    )


def assert_no_usage(lane, before):
    lane.commit_usage.assert_not_called()
    lane.usage_cache_writing.assert_not_called()
    lane.record_speech.assert_not_called()
    lane.record_speech_steps.assert_not_called()
    assert usage_snapshot(lane) == before


def make_projector(lane, monkeypatch, *, accounting_seconds=None):
    if accounting_seconds is not None:
        prepare = lane.store.prepare_accounting

        def supplied_accounting(*args, **kwargs):
            accounting = prepare(*args, **kwargs)
            # Even supplied positive seconds/usage deltas must never be committed
            # when the transactional aggregate contains a deletion receipt.
            return {
                **accounting,
                'seconds': accounting_seconds,
                'updates': {'speech_seconds': 2},
                'hour': '1970-01-01-00',
            }

        monkeypatch.setattr(lane.store, 'prepare_accounting', supplied_accounting)
    return projection.Projector(
        lane.store.store,
        Mock(),
        projection_store=lane.store,
        assign_conversation=Mock(),
        publish=Mock(),
        playback=Mock(),
        clock=lambda: 2000,
    )


def persist_mixed_parts(lane, deleted_index):
    """Use real fenced part commits; a source may change between independent parts."""
    f = lane
    source_row = f.client.rows[('users', f.binding.owner_id, 'conversations', f.cid)]
    f.user.collection('conversations').document('synthetic-output').create({'id': 'synthetic-output'})
    for index in range(2):
        session = f.store.session('head', f.binding, 2000, policy=POLICY, part_index=index, part_count=2)
        session.speech_seconds = 2
        session.total_speech_seconds = 4
        source_row['deleted'] = index == deleted_index
        if index == deleted_index:
            projection_disposition.persist_disposition(session, privacy_deleted=True)
        else:
            transaction = f.client.transaction()
            session.prepare(transaction)
            session.persist(transaction, ({'id': 'synthetic-output', '_sync_lineage_repeat_only': True}, True, []))
            # StrictFirestore retains transform sentinels. Supply the committed
            # ArrayUnion readback before the next independent transaction.
            f.client.rows[f.store.ref('jobs', 'head').path]['conversation_ids'] = ['synthetic-output']
    source_row['deleted'] = True


@pytest.mark.parametrize('deleted_index', [0, 1])
@pytest.mark.parametrize('previously_charged', [True, False])
def test_any_deleted_part_suppresses_entire_job_and_never_calls_publisher(
    lane, monkeypatch, deleted_index, previously_charged
):
    f = lane
    projector = make_projector(f, monkeypatch, accounting_seconds=2)
    counter = SOURCE_DELETED_JOBS._value.get()
    persist_mixed_parts(f, deleted_index)
    entry = f.store.ref('results', 'head').get().to_dict()
    assert entry['projection_parts'][str(1 - deleted_index)]['conversation_id'] == 'synthetic-output'
    assert entry['projection_parts'][str(1 - deleted_index)]['state'] == 'persisted'
    assert SOURCE_DELETED_JOBS._value.get() == counter
    if previously_charged:
        f.client.rows[f.ledger_ref.path].update(
            status=BATCH_PARTIAL_STATUS, usage_committed_seconds=1, usage_steps=[0, 1], usage_step_times=[1999]
        )
    job, entry, binding = f.store.read('head')
    before_usage = usage_snapshot(f)
    result = projector._finish('head', job, entry, binding)
    assert_no_usage(f, before_usage)
    assert result['reason_code'] == 'source_deleted'
    assert result['new_memories'] == result['updated_memories'] == []
    projector.publish.assert_not_called()
    projector.playback.assert_not_called()
    assert f.ledger_ref.get().to_dict()['result'] == result
    assert f.store.ref('jobs', 'head').get().to_dict()['client_result'] == result
    assert SOURCE_DELETED_JOBS._value.get() == counter + 1
    # A lost completion reply must not publish, charge or count a second termination.
    assert projector.complete_content('head', binding, policy=POLICY) == result
    projector.publish.assert_not_called()
    assert_no_usage(f, before_usage)
    assert SOURCE_DELETED_JOBS._value.get() == counter + 1


@pytest.mark.parametrize('deleted_index', [0, 1])
def test_mixed_deleted_parts_kill_switch_off_blocks_without_publishing(lane, monkeypatch, deleted_index):
    f = lane
    projector = make_projector(f, monkeypatch)
    persist_mixed_parts(f, deleted_index)
    monkeypatch.setenv(FLAG, 'false')
    before = deepcopy(f.client.rows)
    counter = SOURCE_DELETED_JOBS._value.get()
    job, entry, binding = f.store.read('head')
    with pytest.raises(ProjectionBlocked, match='requires a source deletion tombstone'):
        projector._finish('head', job, entry, binding)
    projector.publish.assert_not_called()
    assert_no_usage(f, usage_snapshot(f))
    assert f.client.rows == before
    assert SOURCE_DELETED_JOBS._value.get() == counter


@pytest.mark.parametrize('case', ['tombstone', 'redirect'])
def test_tombstone_and_redirect_keep_their_existing_publication_behavior(lane, monkeypatch, case):
    f = lane
    projector = make_projector(f, monkeypatch)
    counter = SOURCE_DELETED_JOBS._value.get()
    if case == 'tombstone':
        f.user.collection('deleted_conversations').document(f.cid).create({})
        job, entry, binding = f.store.read('head')
        result = projector._project('head', job, entry, binding)
        assert result['reason_code'] == 'conversation_deleted'
        assert result['new_memories'] == result['updated_memories'] == []
    else:
        f.client.rows[('users', f.binding.owner_id, 'conversations', f.cid)]['sync_merged_into'] = 'survivor'
        f.user.collection('conversations').document('survivor').create({'id': 'survivor'})
        session = f.store.session('head', f.binding, 2000, policy=POLICY)
        transaction = f.client.transaction()
        session.prepare(transaction)
        session.speech_seconds = 0
        session.persist(transaction, ({'id': 'survivor', '_sync_lineage_repeat_only': True}, True, []))
        job, entry, binding = f.store.read('head')
        result = projector._finish('head', job, entry, binding)
        assert result['new_memories'] == ['survivor']
        assert 'reason_code' not in result
    projector.publish.assert_called_once_with(binding, result)
    f.commit_usage.assert_called_once()
    f.usage_cache_writing.assert_called_once()
    f.record_speech.assert_called_once()
    assert SOURCE_DELETED_JOBS._value.get() == counter


@pytest.mark.parametrize('deleted_index', [0, 1])
def test_old_mixed_completion_is_scrubbed_once_without_usage_changes(lane, monkeypatch, deleted_index):
    f = lane
    projector = make_projector(f, monkeypatch, accounting_seconds=2)
    persist_mixed_parts(f, deleted_index)
    # Model an older binary's completed mixed result, including its frozen usage.
    result_ref = f.store.ref('results', 'head')
    entry = f.client.rows[result_ref.path]
    for receipt in entry['projection_parts'].values():
        receipt['state'] = 'ready'
    entry['projection']['state'] = 'ready'
    entry['projection_state'] = 'ready'
    old = {
        'new_memories': ['synthetic-output'],
        'updated_memories': [],
        'failed_segments': 0,
        'total_segments': 2,
        'errors': [],
        'outcome': 'success',
    }
    ledger = f.client.rows[f.ledger_ref.path]
    ledger.update(status='completed', result=old, usage_committed_seconds=2)
    f.client.rows[f.store.ref('jobs', 'head').path].update(client_status='completed', client_result=old)
    before_usage = usage_snapshot(f)
    counter = SOURCE_DELETED_JOBS._value.get()
    result = projector.complete_content('head', f.binding, policy=POLICY)
    assert result['reason_code'] == 'source_deleted'
    assert result['new_memories'] == result['updated_memories'] == []
    assert f.ledger_ref.get().to_dict()['result'] == result
    assert_no_usage(f, before_usage)
    assert SOURCE_DELETED_JOBS._value.get() == counter
    assert projector.complete_content('head', f.binding, policy=POLICY) == result
    assert SOURCE_DELETED_JOBS._value.get() == counter
    projector.publish.assert_not_called()


@pytest.mark.parametrize('deleted_index', [0, 1])
@pytest.mark.parametrize('enabled', [True, False])
@pytest.mark.parametrize('previously_charged', [True, False])
def test_partial_completion_also_withholds_every_parts_ids(
    lane, monkeypatch, deleted_index, enabled, previously_charged
):
    f = lane
    persist_mixed_parts(f, deleted_index)
    binding = replace(f.binding, segment_ids=('head', 'held'))
    f.client.rows[f.store.ref('jobs', 'head').path]['projection_binding'] = asdict(binding)
    f.store.ref('jobs', 'held').create(
        {
            'owner_id': binding.owner_id,
            'projection_binding': asdict(binding),
            'state': 'quarantined',
            'recovery_state': 'failed_held',
        }
    )
    f.client.rows[f.ledger_ref.path]['batch_pipeline']['segment_ids'] = list(binding.segment_ids)
    entry = f.client.rows[f.store.ref('results', 'head').path]
    for receipt in entry['projection_parts'].values():
        receipt['state'] = 'ready'
    entry['projection']['state'] = entry['projection_state'] = 'ready'
    monkeypatch.setenv(FLAG, str(enabled).lower())
    counter = SOURCE_DELETED_JOBS._value.get()
    if previously_charged:
        f.client.rows[f.ledger_ref.path].update(
            status=BATCH_PARTIAL_STATUS, usage_committed_seconds=1, usage_steps=[0, 1], usage_step_times=[1999]
        )
    projector = make_projector(f, monkeypatch, accounting_seconds=2)
    before_usage = usage_snapshot(f)
    if not enabled:
        before = deepcopy(f.client.rows)
        with pytest.raises(ProjectionBlocked, match='requires a source deletion tombstone'):
            projector.complete_held(binding)
        assert f.client.rows == before
    else:
        result = projector.complete_held(binding)
        assert result['reason_code'] == 'source_deleted'
        assert projector.complete_held(binding) == result
        assert result['outcome'] == 'partial' and result['held_segments'] == 1
        assert result['new_memories'] == result['updated_memories'] == []
        assert f.ledger_ref.get().to_dict()['result'] == result
    projector.publish.assert_not_called()
    assert_no_usage(f, before_usage)
    # A partial retains custody obligations; it is not a new job termination.
    assert SOURCE_DELETED_JOBS._value.get() == counter


@pytest.mark.parametrize('deleted_index', [0, 1])
@pytest.mark.parametrize('enabled', [True, False])
def test_deletion_in_held_entry_suppresses_another_siblings_partial_output(lane, monkeypatch, deleted_index, enabled):
    f = lane
    persist_mixed_parts(f, deleted_index)
    binding = replace(f.binding, segment_ids=('head', 'other'))
    head_job = f.client.rows[f.store.ref('jobs', 'head').path]
    head_job.update(projection_binding=asdict(binding), recovery_state='held')
    head = f.client.rows[f.store.ref('results', 'head').path]
    head['projection']['state'] = 'quarantined'
    head['projection_state'] = 'quarantine_held'
    f.store.ref('jobs', 'other').create({'projection_binding': asdict(binding), 'owner_id': binding.owner_id})
    f.store.ref('results', 'other').create(
        {
            'projection': {
                'state': 'ready',
                'conversation_id': 'synthetic-output',
                'created': True,
                'speech_seconds': 0,
            },
        }
    )
    f.client.rows[f.ledger_ref.path]['batch_pipeline']['segment_ids'] = list(binding.segment_ids)
    monkeypatch.setenv(FLAG, str(enabled).lower())
    counter = SOURCE_DELETED_JOBS._value.get()
    projector = make_projector(f, monkeypatch, accounting_seconds=0)
    before_usage = usage_snapshot(f)
    if not enabled:
        before = deepcopy(f.client.rows)
        with pytest.raises(ProjectionBlocked, match='requires a source deletion tombstone'):
            projector.complete_held(binding)
        assert f.client.rows == before
    else:
        result = projector.complete_held(binding)
        assert result['reason_code'] == 'source_deleted'
        assert projector.complete_held(binding) == result
        assert result['new_memories'] == result['updated_memories'] == []
        assert result['held_segments'] == 1 and result['total_segments'] == 2
    projector.publish.assert_not_called()
    assert_no_usage(f, before_usage)
    assert SOURCE_DELETED_JOBS._value.get() == counter
