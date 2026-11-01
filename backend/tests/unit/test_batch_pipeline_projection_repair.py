"""Owner repair plans are read-only and never fetch artifacts or pin policies."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database.batch_pipeline_projection_protocol import ProjectionBlocked
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.batch_pipeline.projection_repair import plan_owner, apply_owner
from utils.batch_pipeline.scheduler import owner_key
from utils.batch_pipeline.contracts import WorkItem, ProjectionBinding, Priority
from utils.batch_pipeline import context
from utils.sync import recording_lineage


def seed(*, missing_results=()):
    client = StrictFirestore()
    key = owner_key('synthetic')
    client.collection('test_owners').document(key).create({'projection_watermark': 'old'})
    rows = client.collection('test_results')
    for sid, previous, state in [('old', None, 'persisted'), ('head', 'old', 'pending'), ('tail', 'head', 'pending')]:
        if sid not in missing_results:
            rows.document(sid).create(
                {
                    'segment_id': sid,
                    'owner_key': key,
                    'previous_segment_id': previous,
                    'projection_state': state,
                    'committed_at': 1,
                    'result': {'uri': f'gs://synthetic/{sid}'},
                }
            )
        client.collection('test_jobs').document(sid).create(
            {'owner_id': 'synthetic', 'policy_parts': {'projection': {}}}
        )
    successors = {'old': 'head', 'head': 'tail', 'tail': None}
    return SimpleNamespace(client=client, namespace='test', projection_successor=lambda key, sid: successors[sid])


def test_plan_is_readonly_bounded_and_contains_only_owner_obligations(monkeypatch):
    store = seed()
    # Any attempted policy pin, receipt or ledger write is a hard failure.
    reference_type = type(store.client.collection('test_results').document('old'))
    monkeypatch.setattr(reference_type, 'create', Mock(side_effect=AssertionError('dry-run wrote')))
    monkeypatch.setattr(store.client, 'transaction', Mock(side_effect=AssertionError('dry-run transacted')))
    plan = plan_owner(store, 'synthetic', max_units=1)
    assert plan['units'] == ['old', 'head'] and plan['forward_truncated']
    assert plan == plan_owner(store, 'synthetic', max_units=1)


def test_plan_refuses_cross_owner_and_invalid_budgets():
    store = seed()
    store.client.transaction().update(
        store.client.collection('test_results').document('head'), {'owner_key': 'foreign'}
    )
    with pytest.raises(ProjectionBlocked, match='scope mismatch'):
        plan_owner(store, 'synthetic')
    with pytest.raises(ValueError):
        plan_owner(store, 'synthetic', max_units=0)


def test_privacy_holds_are_repairable_and_the_plan_binds_the_control_receipt():
    store = seed()
    row = store.client.rows[('test_results', 'head')]
    row.update(
        projection_state='quarantine_held',
        protocol_version=2,
        privacy_quarantine_version=1,
        projection_privacy_checkpoint={
            'version': 1,
            'ordering_settled': True,
            'protocol_before': 1,
            'state_before': 'pending',
        },
        projection_privacy_refusal={'version': 1, 'reason': 'data_protection_changed'},
    )
    first = plan_owner(store, 'synthetic')
    assert first['units'] == ['old', 'head', 'tail']
    row['projection_privacy_refusal']['reason'] = 'privacy_generation_changed'
    assert plan_owner(store, 'synthetic')['plan_sha256'] != first['plan_sha256']
    row.pop('privacy_quarantine_version')
    assert plan_owner(store, 'synthetic')['units'] == ['old', 'tail']


def test_plan_survives_missing_watermark_receipt_and_discovers_forward_units(monkeypatch):
    store = seed(missing_results={'old'})
    # Expired history truncates the backward walk; the plan itself stays
    # read-only and deterministic, and forward obligations are still found.
    reference_type = type(store.client.collection('test_results').document('head'))
    monkeypatch.setattr(reference_type, 'create', Mock(side_effect=AssertionError('dry-run wrote')))
    monkeypatch.setattr(store.client, 'transaction', Mock(side_effect=AssertionError('dry-run transacted')))
    plan = plan_owner(store, 'synthetic')
    assert plan['units'] == ['head', 'tail']
    assert plan['lookback_missing'] and not plan['lookback_truncated']
    assert plan == plan_owner(store, 'synthetic')


def test_plan_stops_at_missing_older_predecessor_without_losing_intact_history():
    store = seed(missing_results={'old'})
    key = owner_key('synthetic')
    store.client.transaction().update(
        store.client.collection('test_owners').document(key), {'projection_watermark': 'head'}
    )
    plan = plan_owner(store, 'synthetic')
    assert plan['units'] == ['head', 'tail']
    assert plan['lookback_missing'] and not plan['lookback_truncated']


def test_plan_still_refuses_existing_foreign_history_row():
    store = seed()
    key = owner_key('synthetic')
    store.client.transaction().update(
        store.client.collection('test_owners').document(key), {'projection_watermark': 'head'}
    )
    store.client.transaction().update(store.client.collection('test_results').document('old'), {'owner_key': 'foreign'})
    with pytest.raises(ProjectionBlocked, match='scope mismatch'):
        plan_owner(store, 'synthetic')


def test_plan_fails_closed_on_missing_forward_result():
    store = seed(missing_results={'tail'})
    with pytest.raises(ProjectionBlocked, match='forward result missing'):
        plan_owner(store, 'synthetic')


def test_apply_stops_on_fence_and_never_advances_later_units():
    projector = Mock()
    projector.project.side_effect = ProjectionBlocked('synthetic fence')
    projector.store.ref.return_value.get.return_value.to_dict.return_value = {'policy_parts': {'projection': {}}}
    assert apply_owner(projector, {'units': ['head', 'tail']}) == {'blocked': 1}
    projector.project.assert_called_once_with('head')


def test_unpinned_policy_is_reported_without_resolution_and_apply_refuses():
    store = seed()
    store.client.transaction().update(store.client.collection('test_jobs').document('head'), {'policy_parts': {}})
    plan = plan_owner(store, 'synthetic')
    assert plan['unpinned_units'] == 1
    projector = Mock()
    with pytest.raises(ProjectionBlocked, match='unpinned_policy'):
        apply_owner(projector, plan)
    projector.project.assert_not_called()


def strict_inputs():
    item = WorkItem('segment', 'synthetic', 1000, 'gs://synthetic/audio', 30, Priority.DEEP)
    binding = ProjectionBinding('synthetic', 'job', 'content', ('segment',))
    manifest = {
        'owner_id': item.owner_id,
        'job_id': binding.job_id,
        'content_id': binding.content_id,
        'segment_id': item.segment_id,
        'capture_at': item.capture_at,
        'source': binding.source,
        'should_lock': binding.is_locked,
        'client_device_id': binding.client_device_id,
        'client_platform': binding.client_platform,
        'conversation_id': binding.target_conversation_id,
        'recording_session_id': 'synthetic-recording',
        'audio_start_seconds': 1000,
        'audio_end_seconds': 1030,
    }
    return item, binding, manifest


@pytest.mark.parametrize('requested,active', [(False, False), (False, True), (True, False)])
def test_strict_repair_refuses_missing_lineage_proof_or_disabled_fence(monkeypatch, requested, active):
    item, binding, manifest = strict_inputs()
    monkeypatch.setattr(recording_lineage, 'lineage_resolution_requested', lambda *a, **kw: requested)
    monkeypatch.setattr(context, 'sync_live_dedupe_active_for', lambda _: active)
    planner = Mock(side_effect=AssertionError('unsafe planner reached'))
    monkeypatch.setattr(recording_lineage, 'plan_segment_targets', planner)
    with pytest.raises(ProjectionBlocked, match='active proven lineage fence'):
        context.resolve_context(item, binding, manifest, Mock(), require_lineage_fence=True)
    planner.assert_not_called()


@pytest.mark.parametrize('reason', ['unbound', 'stamp_fallback', None, 'bound'])
def test_strict_repair_refuses_unproven_planner_fallback(monkeypatch, reason):
    item, binding, manifest = strict_inputs()
    monkeypatch.setattr(recording_lineage, 'lineage_resolution_requested', lambda *a, **kw: True)
    monkeypatch.setattr(context, 'sync_live_dedupe_active_for', lambda _: True)

    def plan(ids, *args):
        args[-1][ids[0]] = reason
        return {ids[0]: None if reason == 'bound' else 'unproven-stamp'}

    monkeypatch.setattr(recording_lineage, 'plan_segment_targets', plan)
    with pytest.raises(ProjectionBlocked, match='proven generation disposition'):
        context.resolve_context(item, binding, manifest, Mock(), require_lineage_fence=True)


def test_strict_repair_cannot_take_legacy_manifest_free_assignment():
    item = WorkItem('segment', 'synthetic', 1000, 'gs://synthetic/audio', 30, Priority.DEEP)
    binding = ProjectionBinding('synthetic', 'job', 'content', ('segment',))
    with pytest.raises(ProjectionBlocked, match='authenticated lineage manifest'):
        context.require_repair_manifest(item, binding, None, True)
