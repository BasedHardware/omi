"""Stale refusal hints recover only through ordinary policy and mutation fences."""

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config.batch_pipeline import projection_privacy_refusal_resume_enabled
from config.policy import ProjectionPolicy
from database import batch_pipeline_projection as projection_store
from database.batch_pipeline_privacy import BatchPrivacyBlocked, BatchPrivacyReason
from database.batch_pipeline_projection_privacy import hold
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_store import FirestoreTransaction
from tests.unit.test_batch_projection_privacy_hold import lane, fence
from utils.batch_pipeline import projection_privacy as privacy

POLICY = replace(ProjectionPolicy(), require_live_target=True, authoritative_labels=True)
REASON = BatchPrivacyReason.DATA_PROTECTION_CHANGED


def setup_policy_store(lane):
    client, store, binding = lane
    client.rows[('privacy_hold_jobs', 'head')]['segment_id'] = 'head'

    def run(operation):
        tx = FirestoreTransaction(client, store.store.namespace, client.transaction())
        result = operation(tx)
        tx.flush()
        return result

    store.store.run = run
    return client, store, binding


def hinted_read(store, binding):
    # Model a refusal observed by read() immediately before the privacy repair.
    job = store.ref('jobs', 'head').get().to_dict()
    job.update(
        _projection_privacy_refusal=REASON.value,
        policy_parts={'projection': ProjectionPolicy().to_dict()},
    )
    return job, store.ref('results', 'head').get().to_dict(), binding


def assign_fenced(store):
    def assign(self, segment_id, job, entry, binding):
        assert not job.get('_projection_privacy_refusal')
        assert not entry.get('projection_privacy_refusal')
        policy = ProjectionPolicy.from_dict(job['policy_parts']['projection'])
        assert policy == POLICY  # Settlement-only defaults must never authorize content.
        session = store.session(segment_id, binding, 4000, policy=policy)
        transaction = store.client.transaction()
        session.prepare(transaction)
        session.speech_seconds = 4
        session.persist(transaction, ({'id': 'recovered-output'}, True, []))
        return 'proceeded'

    return Mock(side_effect=assign)


@pytest.mark.parametrize('stored_refusal', [False, True])
def test_no_longer_applicable_hint_replays_or_falls_through(lane, monkeypatch, stored_refusal):
    client, store, binding = setup_policy_store(lane)
    if stored_refusal:
        fence(client, binding, REASON)
        hold(store, 'head', binding, 2000, REASON, policy=POLICY)
        client.rows[('users', binding.owner_id)].pop('migration_status')
    client.rows[('privacy_hold_jobs', 'head')]['policy_parts'] = {'projection': POLICY.to_dict()}
    replay = Mock(wraps=privacy.resume)
    monkeypatch.setattr(privacy, 'resume', replay)
    attempted = privacy.PROJECTION_PRIVACY_RESUMES_ATTEMPTED._value.get()
    succeeded = privacy.PROJECTION_PRIVACY_RESUMES_SUCCEEDED._value.get()
    fallthroughs = privacy.PROJECTION_PRIVACY_FALLTHROUGHS._value.get()
    method = assign_fenced(store)
    coordinator = SimpleNamespace(store=store, clock=lambda: 3000)
    assert (
        privacy.settle_refusals(assignment=True)(method)(coordinator, 'head', *hinted_read(store, binding))
        == 'proceeded'
    )
    assert replay.call_count == int(stored_refusal)
    if stored_refusal:
        assert replay.call_args.kwargs['policy'] == POLICY
    assert privacy.PROJECTION_PRIVACY_RESUMES_ATTEMPTED._value.get() - attempted == int(stored_refusal)
    assert privacy.PROJECTION_PRIVACY_RESUMES_SUCCEEDED._value.get() - succeeded == int(stored_refusal)
    assert privacy.PROJECTION_PRIVACY_FALLTHROUGHS._value.get() - fallthroughs == int(not stored_refusal)
    assert store.ref('results', 'head').get().to_dict()['projection']['state'] == 'persisted'
    # Another ordinary read/turn no longer encounters the stale hint or refusal.
    job, entry, _ = store.read('head')
    assert not job.get('_projection_privacy_refusal') and not entry.get('projection_privacy_refusal')


@pytest.mark.parametrize('assignment', [False, True])
def test_applicable_refusal_remains_held_without_writes(lane, monkeypatch, assignment):
    client, store, binding = setup_policy_store(lane)
    fence(client, binding, REASON)
    hold(store, 'head', binding, 2000, REASON, policy=POLICY)
    before = deepcopy(client.rows)
    method = Mock()
    replay = Mock(wraps=privacy.resume)
    monkeypatch.setattr(privacy, 'resume', replay)
    refused = privacy.PROJECTION_PRIVACY_STILL_REFUSED._value.get()
    result = privacy.settle_refusals(assignment=assignment)(method)(
        SimpleNamespace(store=store, clock=lambda: 3000), 'head', *hinted_read(store, binding)
    )
    assert result is (privacy.PRIVACY_HELD if assignment else None)
    assert client.rows == before
    method.assert_not_called()
    replay.assert_not_called()
    assert privacy.PROJECTION_PRIVACY_STILL_REFUSED._value.get() == refused + 1


def test_switch_off_preserves_no_longer_applies_exception(lane, monkeypatch):
    client, store, binding = setup_policy_store(lane)
    monkeypatch.setenv('PROJECTION_PRIVACY_REFUSAL_RESUME', 'off')
    before = deepcopy(client.rows)
    method = Mock()
    with pytest.raises(ProjectionBlocked, match='^privacy refusal no longer applies$'):
        privacy.settle_refusals()(method)(
            SimpleNamespace(store=store, clock=lambda: 3000), 'head', *hinted_read(store, binding)
        )
    assert client.rows == before
    method.assert_not_called()


@pytest.mark.parametrize('value', [None, 'false', '0', 'unknown', ' OFF '])
def test_switch_is_default_on_and_off_only(monkeypatch, value):
    monkeypatch.delenv('PROJECTION_PRIVACY_REFUSAL_RESUME', raising=False)
    if value is not None:
        monkeypatch.setenv('PROJECTION_PRIVACY_REFUSAL_RESUME', value)
    assert projection_privacy_refusal_resume_enabled() is (value != ' OFF ')


def test_repaired_policy_read_pins_serving_policy_before_assignment(lane, monkeypatch):
    client, store, binding = setup_policy_store(lane)
    monkeypatch.setattr(projection_store, 'load_stage_policy', Mock(wraps=projection_store.load_stage_policy))
    monkeypatch.setattr('database.batch_pipeline_policy.resolve_stage_policy', lambda *args, **kwargs: POLICY)
    method = assign_fenced(store)
    result = privacy.settle_refusals(assignment=True)(method)(
        SimpleNamespace(store=store, clock=lambda: 3000), 'head', *hinted_read(store, binding)
    )
    assert result == 'proceeded'
    assert client.rows[('privacy_hold_jobs', 'head')]['policy_parts']['projection'] == POLICY.to_dict()


@pytest.mark.parametrize('stored_refusal', [False, True])
def test_persistent_policy_refusal_does_not_assign_with_synthetic_defaults(lane, monkeypatch, stored_refusal):
    client, store, binding = setup_policy_store(lane)
    if stored_refusal:
        fence(client, binding, REASON)
        hold(store, 'head', binding, 2000, REASON, policy=POLICY)
        client.rows[('users', binding.owner_id)].pop('migration_status')
    # A policy-side guard may still disagree with the session. Recovery must not
    # circumvent that independent fence just to make a drain turn productive.
    monkeypatch.setattr(projection_store, 'load_stage_policy', Mock(side_effect=BatchPrivacyBlocked(REASON)))
    before = deepcopy(client.rows)
    method = Mock()
    with pytest.raises(BatchPrivacyBlocked):
        privacy.settle_refusals()(method)(
            SimpleNamespace(store=store, clock=lambda: 3000), 'head', *hinted_read(store, binding)
        )
    assert client.rows == before
    method.assert_not_called()


def test_tombstone_refusal_is_not_resumed(lane, monkeypatch):
    client, store, binding = setup_policy_store(lane)
    method = Mock(side_effect=BatchPrivacyBlocked('conversation_deleted'))
    replay = Mock(wraps=privacy.resume)
    monkeypatch.setattr(privacy, 'resume', replay)
    before = deepcopy(client.rows)
    with pytest.raises(BatchPrivacyBlocked) as error:
        privacy.settle_refusals()(method)(
            SimpleNamespace(store=store, clock=lambda: 3000),
            'head',
            {'policy_parts': {'projection': POLICY.to_dict()}},
            store.ref('results', 'head').get().to_dict(),
            binding,
        )
    assert error.value.reason == BatchPrivacyReason.CONVERSATION_DELETED
    assert client.rows == before
    replay.assert_not_called()


def test_other_projection_blocks_are_not_swallowed(lane, monkeypatch):
    client, store, binding = setup_policy_store(lane)
    monkeypatch.setattr(privacy, 'hold', Mock(side_effect=ProjectionBlocked('durable intake ledger binding required')))
    with pytest.raises(ProjectionBlocked, match='durable intake ledger binding required'):
        privacy.settle_refusals()(Mock())(
            SimpleNamespace(store=store, clock=lambda: 3000), 'head', *hinted_read(store, binding)
        )


def test_job_policy_refusal_with_clear_session_does_not_repeat_stale_hint(lane, monkeypatch):
    client, store, binding = setup_policy_store(lane)
    real_load = projection_store.load_stage_policy

    # Reproduce the independent guard results at the policy/session boundary:
    # the initial job/output policy read refuses, the fenced session is clear.
    def load(*args, **kwargs):
        if loads.call_count == 1:
            raise BatchPrivacyBlocked(REASON)
        return real_load(*args, **kwargs)

    loads = Mock(side_effect=load)
    monkeypatch.setattr(projection_store, 'load_stage_policy', loads)
    monkeypatch.setattr('database.batch_pipeline_policy.resolve_stage_policy', lambda *args, **kwargs: POLICY)
    job, entry, binding = store.read('head')
    assert job['_projection_privacy_refusal'] == REASON.value
    method = assign_fenced(store)
    coordinator = SimpleNamespace(store=store, clock=lambda: 3000)
    assert privacy.settle_refusals()(method)(coordinator, 'head', job, entry, binding) == 'proceeded'
    assert loads.call_count == 2
    assert store.ref('results', 'head').get().to_dict()['projection']['state'] == 'persisted'


def test_replay_failure_counts_attempt_without_success(lane, monkeypatch):
    client, store, binding = setup_policy_store(lane)
    fence(client, binding, REASON)
    hold(store, 'head', binding, 2000, REASON, policy=POLICY)
    client.rows[('users', binding.owner_id)].pop('migration_status')
    # Isolate replay failure from the separately tested first policy pin.
    client.rows[('privacy_hold_jobs', 'head')]['policy_parts'] = {'projection': POLICY.to_dict()}
    monkeypatch.setattr(privacy, 'resume', Mock(side_effect=ProjectionBlocked('privacy ordering checkpoint required')))
    before = deepcopy(client.rows)
    attempted = privacy.PROJECTION_PRIVACY_RESUMES_ATTEMPTED._value.get()
    succeeded = privacy.PROJECTION_PRIVACY_RESUMES_SUCCEEDED._value.get()
    method = Mock()
    with pytest.raises(ProjectionBlocked, match='privacy ordering checkpoint required'):
        privacy.settle_refusals()(method)(
            SimpleNamespace(store=store, clock=lambda: 3000), 'head', *hinted_read(store, binding)
        )
    assert privacy.PROJECTION_PRIVACY_RESUMES_ATTEMPTED._value.get() == attempted + 1
    assert privacy.PROJECTION_PRIVACY_RESUMES_SUCCEEDED._value.get() == succeeded
    assert client.rows == before
    method.assert_not_called()


@pytest.mark.parametrize('stored_refusal', [False, True])
def test_real_job_output_refusal_then_clear_session_retries_head(lane, monkeypatch, stored_refusal):
    client, store, binding = setup_policy_store(lane)
    if stored_refusal:
        fence(client, binding, REASON)
        hold(store, 'head', binding, 2000, REASON, policy=POLICY)
        client.rows[('users', binding.owner_id)].pop('migration_status')
    output = 'previous-private-output'
    client.rows[('privacy_hold_jobs', 'head')]['conversation_ids'] = [output]
    client.rows[('users', binding.owner_id, 'conversations', output)] = {
        'record_lane_owner': 'batch_live_v1',
        'uses_custom_stt': True,
    }
    monkeypatch.setattr('database.batch_pipeline_policy.resolve_stage_policy', lambda *args, **kwargs: POLICY)
    # The real policy guard rejects the job's output and read() returns its hint.
    job, entry, binding = store.read('head')
    assert job['_projection_privacy_refusal'] == BatchPrivacyReason.RECORDING_PRIVACY_CHANGED.value
    assert 'projection' not in client.rows[('privacy_hold_jobs', 'head')].get('policy_parts', {})
    # A concurrent job update detaches that previous output. The subsequent
    # session sees a different id set: inputs are clear, and the output is no
    # longer part of the durable job. Its private source document stays private.
    client.rows[('privacy_hold_jobs', 'head')].pop('conversation_ids')
    private_output = deepcopy(client.rows[('users', binding.owner_id, 'conversations', output)])
    method = assign_fenced(store)
    assert (
        privacy.settle_refusals(assignment=True)(method)(
            SimpleNamespace(store=store, clock=lambda: 3000), 'head', job, entry, binding
        )
        == 'proceeded'
    )
    assert client.rows[('users', binding.owner_id, 'conversations', output)] == private_output
    assert store.ref('results', 'head').get().to_dict()['projection']['state'] == 'persisted'
    fresh_job, fresh_entry, _ = store.read('head')
    assert not fresh_job.get('_projection_privacy_refusal')
    assert not fresh_entry.get('projection_privacy_refusal')
