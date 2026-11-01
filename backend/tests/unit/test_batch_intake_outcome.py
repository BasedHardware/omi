"""The per-upload batch intake outcome counter: one closed label per fresh routing decision.

``batch`` is an upload batch intake accepted; ``heavy_excluded`` /
``language_excluded`` are fresh exclusions that landed the upload on legacy;
``not_cohort`` is the ramp cohort decision. An upload following a prior durable
owner carries no fresh decision and must not be counted.
"""

from unittest.mock import AsyncMock, Mock, patch
from types import SimpleNamespace

import pytest
from starlette.datastructures import UploadFile

from config.policy import BatchUnitPolicy, ramp
from database import batch_ramp
from services import summary_debt_repair  # noqa: F401 - initialize the router harness dependency at collection
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreSnapshot
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_legacy_dark_router import _restore
from tests.unit.test_sync_cloud_tasks import _load_sync_router_for_fast_path
from utils.batch_pipeline import intake, live_upload
from utils.batch_pipeline.artifacts import ProtectionContext
from utils.batch_pipeline.intake_outcome import (
    INTAKE_OUTCOMES,
    OUTCOMES,
    IntakeRouteEvidence,
    legacy_landing_outcome,
    record_upload_outcome,
)
from utils.batch_pipeline.live_upload import RecordUploadRoute
from utils.sync import legacy_dark
from utils.sync.legacy_dark import LegacySyncMode

UID, CID = 'test-uid', 'synthetic-conversation'
USER = ('users', UID)
CONVERSATION = (*USER, 'conversations', CID)
ON = LegacySyncMode.ON


@pytest.fixture(autouse=True)
def defaults(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.delenv(ramp.SWITCH, raising=False)
    monkeypatch.delenv('BATCH_ADMISSION_LANGUAGE_EXCLUSION_ENABLED', raising=False)
    monkeypatch.setattr(
        StrictFirestoreSnapshot,
        'update_time',
        property(lambda self: (self._data or {}).get('_test_revision')),
        raising=False,
    )


def enabled_policy():
    return BatchUnitPolicy(batch_enabled=True, batch_percent=5, live_admission_enabled=True, live_record_enabled=True)


def _counts():
    return {outcome: INTAKE_OUTCOMES.labels(outcome=outcome)._value.get() for outcome in sorted(OUTCOMES)}


def _router():
    module, saved, jobs, BytesIO, _, _ = _load_sync_router_for_fast_path()
    return module, saved, BytesIO


async def _upload(module, BytesIO, *, conversation_id=None):
    return await module.sync_local_files_v2(
        files=[UploadFile(filename='omi_1792152000.bin', file=BytesIO(b'\x00' * 10))],
        uid=UID,
        conversation_id=conversation_id,
    )


def _no_durable_owner_client():
    client = Mock()
    ref = client.collection.return_value.document.return_value.collection.return_value.document.return_value
    ref.get.return_value = SimpleNamespace(exists=False, to_dict=lambda: {})
    return client


def _language_world(monkeypatch):
    row = {'status': 'completed', 'language': 'auto', '_test_revision': 1}
    user = {'language': 'en', 'transcription_preferences': {'single_language_mode': False}}
    client = StrictFirestore({USER: user, CONVERSATION: row})
    store = MemoryStore()
    store.client, store.namespace = client, 'batch_pipeline_dev'
    claims = []

    def claim(uid, cid, selected, expected, *, firestore_client):
        assert (uid, cid, expected) == (UID, CID, 1) and firestore_client is client
        claims.append(selected)
        client.rows[CONVERSATION]['record_lane_owner'] = selected
        return 2

    monkeypatch.setattr(live_upload, 'FirestoreStore', lambda *_: store)
    monkeypatch.setattr(live_upload, 'claim_record_lane_owner', claim)
    monkeypatch.setattr(intake, 'FirestoreStore', lambda *_: store)
    return SimpleNamespace(client=client, store=store, claims=claims, policy=enabled_policy())


# --- closed label set and priority ---------------------------------------------------------------


def test_closed_outcome_set_folds_unknown_labels():
    assert OUTCOMES == frozenset({'batch', 'heavy_excluded', 'language_excluded', 'not_cohort'})
    before = INTAKE_OUTCOMES.labels(outcome='unknown')._value.get()
    record_upload_outcome('legacy_owner')  # A durable owner is not a fresh decision.
    assert INTAKE_OUTCOMES.labels(outcome='unknown')._value.get() == before + 1


def test_legacy_landing_priority_and_residual():
    both = IntakeRouteEvidence(heavy_owner_excluded=True, language_excluded=True)
    assert legacy_landing_outcome(both, candidate_batch_enabled=True) == 'heavy_excluded'
    language = IntakeRouteEvidence(language_excluded=True)
    assert legacy_landing_outcome(language, candidate_batch_enabled=False) == 'language_excluded'
    assert legacy_landing_outcome(IntakeRouteEvidence(), candidate_batch_enabled=False) == 'not_cohort'
    assert legacy_landing_outcome(IntakeRouteEvidence(), candidate_batch_enabled=True) is None


# --- evidence provenance -------------------------------------------------------------------------


def test_owner_load_exclusion_marks_evidence_but_durable_owners_do_not(monkeypatch):
    monkeypatch.setattr(batch_ramp, 'current_stage', lambda: 'dev')
    client = _no_durable_owner_client()
    monkeypatch.setattr(batch_ramp, 'get_data_plane_firestore_client', lambda: client)
    excluded = IntakeRouteEvidence()
    with patch.object(
        batch_ramp,
        'read_owner_load',
        return_value={'open_backlog': 42, 'recording_seconds': 0, 'complete': True},
    ):
        filtered = batch_ramp.ramp_admission_policy(UID, enabled_policy(), content_id='content', evidence=excluded)
    assert not filtered.batch_enabled
    assert excluded.heavy_owner_excluded and not excluded.language_excluded

    durable = IntakeRouteEvidence()
    ref = client.collection.return_value.document.return_value.collection.return_value.document.return_value
    ref.get.return_value = SimpleNamespace(exists=True, to_dict=lambda: {'dispatch_protocol': 'legacy_v1'})
    with patch.object(batch_ramp, 'read_owner_load', side_effect=AssertionError('prior custody must not rescan')):
        filtered = batch_ramp.ramp_admission_policy(UID, enabled_policy(), content_id='content', evidence=durable)
    assert not filtered.batch_enabled
    assert not durable.heavy_owner_excluded and not durable.language_excluded


async def test_intake_language_exclusion_decline_marks_evidence(monkeypatch):
    world = _language_world(monkeypatch)
    monkeypatch.setattr(intake, 'current_stage', lambda: 'dev')
    monkeypatch.setattr(legacy_dark, 'current_mode', lambda uid=None: ON)

    def authorize(_store, _work, snapshots):
        snapshots['user'] = dict(world.client.rows[USER])
        snapshots['conversations'] = {CID: dict(world.client.rows[CONVERSATION])}
        return ProtectionContext('standard', 0)

    monkeypatch.setattr(intake, 'batch_artifact_authorize', authorize)
    monkeypatch.setattr(
        intake, 'artifacts_for', Mock(side_effect=AssertionError('excluded upload must not stage batch artifacts'))
    )
    evidence = IntakeRouteEvidence()
    arguments = dict(
        uid=UID,
        job_id='job',
        content_id='content',
        paths=['retained.bin'],
        lane='fresh',
        recording_age_seconds=60,
        source='omi',
        should_lock=False,
        conversation_id=CID,
        client_device_id=None,
        client_platform='ios',
        policy=enabled_policy(),
        evidence=evidence,
    )
    assert await intake.accept_upload(**arguments) is None
    assert evidence.language_excluded and not evidence.heavy_owner_excluded
    assert not world.store.rows  # No batch ledger, jobs, intakes or queue writes.


# --- one counter branch per upload outcome, through the real router ------------------------------


async def test_upload_accepted_by_batch_counts_batch(monkeypatch):
    module, saved, BytesIO = _router()
    try:
        monkeypatch.setattr(legacy_dark, 'current_mode', lambda uid=None: ON)
        module.resolve_batch_policy = lambda uid: enabled_policy()
        module.ramp_admission_policy = lambda uid, policy, **kwargs: policy
        module.accept_batch_upload = AsyncMock(
            return_value=module.JSONResponse(status_code=202, content={'job_id': 'bp_1', 'status': 'queued'})
        )
        module.create_sync_job = Mock()
        before = _counts()
        response = await _upload(module, BytesIO)
        assert response.status_code == 202
        after = _counts()
        assert after['batch'] == before['batch'] + 1
        assert {k: v for k, v in after.items() if k != 'batch'} == {k: v for k, v in before.items() if k != 'batch'}
        module.create_sync_job.assert_not_called()
    finally:
        _restore(saved)


async def test_heavy_owner_excluded_upload_counts_heavy_excluded(monkeypatch):
    module, saved, BytesIO = _router()
    try:
        monkeypatch.setattr(legacy_dark, 'current_mode', lambda uid=None: ON)
        module.resolve_batch_policy = lambda uid: enabled_policy()
        module.registered_record_response = AsyncMock(return_value=None)
        # The narrowed policy declines the upload back to legacy inside intake.
        module.accept_batch_upload = AsyncMock(return_value=None)
        module.create_sync_job = Mock()
        # Real ramp: no durable owner, the owner-load read excludes this uid.
        monkeypatch.setattr(batch_ramp, 'current_stage', lambda: 'dev')
        monkeypatch.setattr(batch_ramp, 'get_data_plane_firestore_client', _no_durable_owner_client)
        monkeypatch.setattr(
            batch_ramp,
            'read_owner_load',
            lambda *a, **k: {'open_backlog': 42, 'recording_seconds': 0, 'complete': True},
        )
        before = _counts()
        response = await _upload(module, BytesIO)
        assert response.status_code == 202
        after = _counts()
        assert after['heavy_excluded'] == before['heavy_excluded'] + 1
        assert {k: v for k, v in after.items() if k != 'heavy_excluded'} == {
            k: v for k, v in before.items() if k != 'heavy_excluded'
        }
        module.create_sync_job.assert_called_once()
    finally:
        _restore(saved)


async def test_language_excluded_upload_counts_language_excluded(monkeypatch):
    world = _language_world(monkeypatch)
    module, saved, BytesIO = _router()
    try:
        monkeypatch.setattr(legacy_dark, 'current_mode', lambda uid=None: ON)
        monkeypatch.setattr(legacy_dark, 'read_ledger_row', lambda *a: None)
        module.resolve_batch_policy = lambda uid: world.policy
        module.ramp_admission_policy = lambda uid, policy, **kwargs: policy
        module.compute_sync_content_id = lambda *a: 'new'
        module.registered_record_response = live_upload.registered_record_response
        module.accept_batch_upload = Mock(side_effect=AssertionError('excluded upload must not enter batch intake'))
        module.archive_mobile_batch_raw_files = lambda *a, **k: []
        before = _counts()
        response = await _upload(module, BytesIO, conversation_id=CID)
        assert response.status_code == 202
        assert world.claims == ['legacy_final_pass_v1']
        after = _counts()
        assert after['language_excluded'] == before['language_excluded'] + 1
        assert {k: v for k, v in after.items() if k != 'language_excluded'} == {
            k: v for k, v in before.items() if k != 'language_excluded'
        }
    finally:
        _restore(saved)


async def test_not_cohort_upload_counts_not_cohort(monkeypatch):
    module, saved, BytesIO = _router()
    try:
        monkeypatch.setattr(legacy_dark, 'current_mode', lambda uid=None: ON)
        module.resolve_batch_policy = lambda uid: BatchUnitPolicy(batch_enabled=False)
        module.registered_record_response = AsyncMock(return_value=None)
        module.accept_batch_upload = AsyncMock(side_effect=AssertionError('batch is not enabled for this uid'))
        module.create_sync_job = Mock()
        before = _counts()
        response = await _upload(module, BytesIO)
        assert response.status_code == 202
        after = _counts()
        assert after['not_cohort'] == before['not_cohort'] + 1
        assert {k: v for k, v in after.items() if k != 'not_cohort'} == {
            k: v for k, v in before.items() if k != 'not_cohort'
        }
        module.create_sync_job.assert_called_once()
    finally:
        _restore(saved)


async def test_durable_legacy_owner_landing_is_not_counted(monkeypatch):
    module, saved, BytesIO = _router()
    try:
        monkeypatch.setattr(legacy_dark, 'current_mode', lambda uid=None: ON)
        module.resolve_batch_policy = lambda uid: enabled_policy()
        module.ramp_admission_policy = lambda uid, policy, **kwargs: policy
        module.registered_record_response = AsyncMock(return_value=RecordUploadRoute.LEGACY)
        module.accept_batch_upload = AsyncMock(side_effect=AssertionError('a legacy owner must not enter batch intake'))
        module.create_sync_job = Mock()
        before = _counts()
        response = await _upload(module, BytesIO)
        assert response.status_code == 202
        assert _counts() == before  # Prior owner: no fresh decision, no outcome.
        module.create_sync_job.assert_called_once()
    finally:
        _restore(saved)
