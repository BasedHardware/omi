"""The router must exclude unsafe new uploads before reserving batch ownership."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from starlette.datastructures import UploadFile

from config.policy import BatchUnitPolicy
from services import summary_debt_repair  # noqa: F401 - initialize the router harness dependency at collection
from tests.unit.fixtures.strict_firestore_transaction import (
    StrictFirestore,
    StrictFirestoreDocument,
    StrictFirestoreSnapshot,
)
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_legacy_dark_router import _restore
from tests.unit.test_sync_cloud_tasks import _load_sync_router_for_fast_path
from utils.batch_pipeline import intake, live_upload
from utils.batch_pipeline.artifacts import ProtectionContext
from utils.batch_pipeline.live_upload import RecordUploadRoute
from utils.sync import final_pass_rehome, legacy_dark
from utils.sync.final_pass_rehome import RehomeOutcome
from utils.sync.legacy_dark import LegacySyncMode

UID, CID = 'test-uid', 'synthetic-conversation'
USER = ('users', UID)
CONVERSATION = (*USER, 'conversations', CID)


@pytest.fixture(autouse=True)
def defaults(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.delenv('BATCH_ADMISSION_LANGUAGE_EXCLUSION_ENABLED', raising=False)
    monkeypatch.setenv('BATCH_PIPELINE_LANGUAGE_ELIGIBILITY_ENABLED', 'false')
    monkeypatch.setattr(
        StrictFirestoreSnapshot,
        'update_time',
        property(lambda self: (self._data or {}).get('_test_revision')),
        raising=False,
    )


def setup(monkeypatch, language, *, owner=None, single=False, user_language='en'):
    row = {'status': 'completed', 'language': language, '_test_revision': 1}
    if owner:
        row['record_lane_owner'] = owner
    user = {'language': user_language, 'transcription_preferences': {'single_language_mode': single}}
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
    policy = BatchUnitPolicy(batch_enabled=True, live_admission_enabled=True, live_record_enabled=False)
    return SimpleNamespace(client=client, store=store, claims=claims, policy=policy)


async def route(world, mode):
    return await live_upload.registered_record_response(
        uid=UID,
        conversation_id=CID,
        content_id='new',
        paths=[],
        source='omi',
        client_device_id=None,
        policy=world.policy,
        legacy_mode=mode,
    )


@pytest.mark.parametrize('mode', list(LegacySyncMode))
@pytest.mark.parametrize('language', ['auto', 'ja'])
async def test_actual_sync_router_excludes_before_claim_and_batch_intake(monkeypatch, mode, language):
    world = setup(monkeypatch, language)
    module, saved, jobs, BytesIO, _, _ = _load_sync_router_for_fast_path()
    before = deepcopy(world.client.rows)
    try:
        monkeypatch.setattr(legacy_dark, 'current_mode', lambda: mode)
        monkeypatch.setattr(legacy_dark, 'read_ledger_row', lambda *a: None)
        module.resolve_batch_policy = lambda uid: world.policy
        module.ramp_admission_policy = lambda uid, policy, **kwargs: policy
        module.compute_sync_content_id = lambda *a: 'new'
        module.registered_record_response = live_upload.registered_record_response
        module.accept_batch_upload = intake.accept_upload
        module.archive_mobile_batch_raw_files = lambda *a: []

        def authorize(store, work, snapshots):
            snapshots['user'] = deepcopy(world.client.rows[USER])
            snapshots['conversations'] = {CID: deepcopy(world.client.rows[CONVERSATION])}
            return ProtectionContext('standard', 0)

        monkeypatch.setattr(intake, 'batch_artifact_authorize', authorize)
        staging = Mock(side_effect=AssertionError('unsafe bound upload entered batch staging'))
        monkeypatch.setattr(intake, 'artifacts_for', staging)
        response = await module.sync_local_files_v2(
            files=[UploadFile(filename='omi_1792152000.bin', file=BytesIO(b'\x00' * 10))],
            uid=UID,
            conversation_id=CID,
        )
        assert not world.store.rows  # No batch ledger, jobs, intakes or queue writes.
        staging.assert_not_called()
        if mode is LegacySyncMode.ON:
            assert response.status_code == 202
            assert world.claims == ['legacy_final_pass_v1']
            module.create_sync_job.assert_called_once()
        else:
            assert response.status_code == 409 and b'sync_content_retry_later' in response.body
            assert not world.claims and world.client.rows == before
            module.create_sync_job.assert_not_called()
    finally:
        _restore(saved)


@pytest.mark.parametrize('mode', list(LegacySyncMode))
@pytest.mark.parametrize('language,single', [('en', False), ('auto', True)])
async def test_supported_context_or_single_preference_can_still_claim_batch(monkeypatch, mode, language, single):
    world = setup(monkeypatch, language, single=single)
    assert await route(world, mode) is RecordUploadRoute.BATCH
    assert world.claims == ['batch_sync_v1']


@pytest.mark.parametrize('mode', list(LegacySyncMode))
async def test_prior_batch_receipt_precedes_a_new_owner_exclusion_without_writes(monkeypatch, mode):
    world = setup(monkeypatch, 'auto')
    world.store.rows['content', f'{UID}/new'] = {'dispatch_protocol': 'batch_v1', 'job_id': 'bp_prior'}
    before = deepcopy(world.store.rows), deepcopy(world.client.rows)
    assert await route(world, mode) is RecordUploadRoute.BATCH
    assert not world.claims
    assert (world.store.rows, world.client.rows) == before


@pytest.mark.parametrize('mode', [LegacySyncMode.DRAINING, LegacySyncMode.DARK])
@pytest.mark.parametrize('language', ['auto', 'ja'])
async def test_excluded_legacy_owner_is_not_rehomed_to_batch(monkeypatch, mode, language):
    world = setup(monkeypatch, language, owner='legacy_final_pass_v1')
    rehome = Mock(side_effect=AssertionError('unsafe upload re-homed to batch'))
    monkeypatch.setattr(final_pass_rehome, 'upload_rehome', rehome)
    before = deepcopy(world.client.rows)
    assert await route(world, mode) is RecordUploadRoute.LEGACY
    assert not world.claims and world.client.rows == before
    rehome.assert_not_called()


async def test_supported_legacy_owner_still_rehomes_in_dark(monkeypatch):
    world = setup(monkeypatch, 'en', owner='legacy_final_pass_v1')
    rehome = Mock(return_value=RehomeOutcome.REHOMED)
    monkeypatch.setattr(final_pass_rehome, 'upload_rehome', rehome)
    assert await route(world, LegacySyncMode.DARK) is RecordUploadRoute.BATCH
    rehome.assert_called_once()


@pytest.mark.parametrize('disabled', [False, True])
@pytest.mark.parametrize('mode', list(LegacySyncMode))
async def test_existing_batch_owner_and_kill_switch_never_read_new_preferences(monkeypatch, disabled, mode):
    if disabled:
        monkeypatch.setenv('BATCH_ADMISSION_LANGUAGE_EXCLUSION_ENABLED', 'false')
    world = setup(monkeypatch, 'auto', owner=None if disabled else 'batch_sync_v1')
    original = StrictFirestoreDocument.get

    def get(ref, *args, **kwargs):
        assert ref.path != f'users/{UID}', 'rollback/existing owner performed new preference IO'
        return original(ref, *args, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    assert await route(world, mode) is RecordUploadRoute.BATCH
    assert world.claims == (['batch_sync_v1'] if disabled else [])


async def test_negative_control_router_without_preclaim_gate_exposes_the_reviewed_bypass(monkeypatch):
    # Disable only the early gate, leaving the intake exclusion ON. The real
    # router reserves batch_sync_v1 first, and the regression catches staging.
    monkeypatch.setattr(live_upload, 'admission_language_exclusion_enabled', lambda: False)
    with pytest.raises(AssertionError, match='not have been called'):
        await test_actual_sync_router_excludes_before_claim_and_batch_intake(monkeypatch, LegacySyncMode.DARK, 'auto')
