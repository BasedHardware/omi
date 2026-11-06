"""The fenced recovery lane holds typed staged faults once, then stops.

Failure-Class: FC-deterministic-staged-decode-failure-walks-gpu-retry-ladder-as-unclassified-valueerror

A quarantined staged decode fault is deterministic on the pinned bytes,
so the recovery sweep must hold it once under a closed refusal family —
exactly like its retained-audio sibling — instead of re-fetching the same
undecodable unit on every pass. Intentionally retryable refusals (the
bucket allowlist, storage faults) keep the prepared/retry semantics, and
the shadow CAS pins the same typed evidence the worker carried.
"""

import logging
from unittest.mock import Mock

import pytest

from utils.batch_pipeline.audio import StagedAudioInvalid
from utils.batch_pipeline.contracts import ValidationFailureWork
from utils.observability.reasons import WorkerValidationReason
from tests.unit.test_batch_pipeline_quarantine_recovery import row, setup  # noqa: F401
from tests.unit.test_batch_pipeline_invalid_manifest_hold import serve

STAGED = WorkerValidationReason.STAGED_AUDIO_INVALID.value
RECOVER = {'stage': 'prod', 'segment_id': 'bad'}


# --- the sweep holds the typed staged fault once ------------------------------------


def test_recovery_holds_once_for_typed_staged_fault(setup, monkeypatch):
    client, _, _, artifacts, stt, _ = setup
    artifacts.fetch_audio.side_effect = StagedAudioInvalid('invalid staged WAV container')
    response = serve(setup, monkeypatch).post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    assert response.status_code == 200 and response.json() == {'status': 'failed_held'}
    job = row(client)
    assert job['recovery_state'] == 'failed_held'
    assert job['recovery']['refusal'] == {'reason': STAGED}
    stt.assert_not_called()


@pytest.mark.parametrize(
    'message',
    [
        'staging requires 16kHz mono PCM16 WAV',
        'invalid staged audio length',
        'truncated staged WAV',
        'invalid staged WAV container',
        'invalid bounded intake context or WAV',
    ],
)
def test_recovery_holds_once_for_every_typed_staged_message(setup, monkeypatch, message):
    client, _, _, artifacts, stt, _ = setup
    artifacts.fetch_audio.side_effect = StagedAudioInvalid(message)
    response = serve(setup, monkeypatch).post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    assert response.json() == {'status': 'failed_held'}
    assert row(client)['recovery']['refusal'] == {'reason': STAGED}
    stt.assert_not_called()


def test_recovery_staged_hold_logs_the_closed_reason(setup, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    client, _, _, artifacts, _, _ = setup
    artifacts.fetch_audio.side_effect = StagedAudioInvalid('invalid staged WAV container')
    serve(setup, monkeypatch).post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    assert 'event=batch_quarantine_recovery outcome=failed_held reason=staged_audio_invalid' in caplog.text


def test_recovery_staged_hold_leaves_the_candidate_set(setup, monkeypatch):
    client, _, binding, artifacts, stt, recovery = setup
    artifacts.fetch_audio.side_effect = StagedAudioInvalid('invalid staged WAV container')
    http = serve(setup, monkeypatch)
    assert http.post('/v2/batch-pipeline/recover-quarantine', json=RECOVER).json() == {'status': 'failed_held'}
    assert recovery.protocol.prepare('bad', binding.owner_id, 200) is None
    assert http.post('/v2/batch-pipeline/recover-quarantine', json=RECOVER).json() == {'status': 'held'}
    artifacts.fetch_audio.assert_called_once()


def test_recovery_staged_hold_keeps_audio_without_persist_or_delete(setup, monkeypatch):
    client, _, _, artifacts, stt, _ = setup
    artifacts.fetch_audio.side_effect = StagedAudioInvalid('invalid staged WAV container')
    http = serve(setup, monkeypatch)
    http.post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    assert not [name for name, *_ in artifacts.mock_calls if 'delete' in name or 'persist' in name]
    stt.assert_not_called()


def test_recovery_staged_hold_carries_no_error_text(setup, monkeypatch):
    client, _, _, artifacts, _, _ = setup
    artifacts.fetch_audio.side_effect = StagedAudioInvalid('invalid staged WAV container')
    serve(setup, monkeypatch).post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    refusal = row(client)['recovery']['refusal']
    assert refusal == {'reason': STAGED}
    assert 'WAV' not in str(refusal)


# --- intentionally retryable refusals keep the prepared semantics --------------------


def test_recovery_stays_prepared_for_a_bare_value_error_refusal(setup, monkeypatch):
    # The bucket-allowlist refusal is deploy configuration, not the bytes:
    # a retry may succeed after a rollout, so it must not hold.
    client, _, _, artifacts, _, _ = setup
    artifacts.fetch_audio.side_effect = ValueError('retained audio reference is outside admitted source')
    response = serve(setup, monkeypatch).post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    assert response.status_code == 500
    assert row(client)['recovery_state'] == 'prepared'
    assert 'refusal' not in row(client)['recovery']


def test_recovery_stays_prepared_for_a_storage_fault(setup, monkeypatch):
    client, _, _, artifacts, _, _ = setup
    artifacts.fetch_audio.side_effect = OSError('storage unavailable')
    response = serve(setup, monkeypatch).post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    assert response.status_code == 500
    assert row(client)['recovery_state'] == 'prepared'


def test_recovery_retained_family_keeps_its_own_refusal_reason(setup, monkeypatch):
    client, _, _, artifacts, _, _ = setup
    artifacts.fetch_audio.side_effect = type('RAI', (StagedAudioInvalid,), {})('nope')
    # A StagedAudioInvalid SUBCLASS is still the staged family; the retained
    # reason stays reserved for the retained type itself.
    from utils.batch_pipeline.source_audio import RetainedAudioInvalid

    artifacts.fetch_audio.side_effect = RetainedAudioInvalid('retained capture checksum mismatch')
    response = serve(setup, monkeypatch).post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    assert response.json() == {'status': 'failed_held'}
    assert row(client)['recovery']['refusal'] == {'reason': 'retained_audio_invalid'}


# --- the protocol fence for the staged refusal ---------------------------------------


def test_protocol_hold_accepts_the_staged_refusal_reason(setup):
    client, _, binding, _, _, recovery = setup
    token = recovery.protocol.prepare('bad', binding.owner_id, 100)['recovery']['token']
    assert recovery.protocol.hold_invalid_manifest(
        'bad', token, 100, audio_uri='gs://synthetic/audio', refusal_reason=STAGED
    )
    assert row(client)['recovery']['refusal'] == {'reason': STAGED}


def test_protocol_hold_default_refusal_reason_unchanged(setup):
    client, _, binding, _, _, recovery = setup
    token = recovery.protocol.prepare('bad', binding.owner_id, 100)['recovery']['token']
    assert recovery.protocol.hold_invalid_manifest('bad', token, 100, audio_uri='gs://synthetic/audio')
    assert row(client)['recovery']['refusal'] == {'reason': 'invalid_retained_manifest'}


def test_protocol_staged_hold_is_fenced_to_unstarted_intents(setup):
    client, _, binding, _, _, recovery = setup
    token = recovery.protocol.prepare('bad', binding.owner_id, 100)['recovery']['token']
    assert not recovery.protocol.hold_invalid_manifest(
        'bad', 'f' * 32, 100, audio_uri='gs://synthetic/audio', refusal_reason=STAGED
    )
    assert not recovery.protocol.hold_invalid_manifest(
        'bad', token, 100, audio_uri='gs://synthetic/other', refusal_reason=STAGED
    )
    assert recovery.protocol.start('bad', token, 100)
    assert not recovery.protocol.hold_invalid_manifest(
        'bad', token, 100, audio_uri='gs://synthetic/audio', refusal_reason=STAGED
    )


def test_protocol_staged_hold_refuses_after_a_wrong_token_once(setup):
    client, _, binding, _, _, recovery = setup
    token = recovery.protocol.prepare('bad', binding.owner_id, 100)['recovery']['token']
    assert not recovery.protocol.hold_invalid_manifest(
        'bad', 'f' * 32, 100, audio_uri='gs://synthetic/audio', refusal_reason=STAGED
    )
    assert recovery.protocol.hold_invalid_manifest(
        'bad', token, 100, audio_uri='gs://synthetic/audio', refusal_reason=STAGED
    )


# --- the shadow CAS pins the same typed evidence -------------------------------------


@pytest.fixture
def shadow_store():
    from tests.unit.fixtures.shadow_slot_cas_firestore import ShadowStoreDouble

    return ShadowStoreDouble()


@pytest.fixture
def repository(shadow_store, monkeypatch):
    import database.batch_pipeline_shadow as shadow_module
    from database.batch_pipeline_shadow import ShadowStore

    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_PERCENT', '100')
    monkeypatch.setattr(shadow_module, 'shadow_slot_cas_enabled', lambda: True)
    return ShadowStore(shadow_store, clock=shadow_store.clock, busy=lambda: False)


def ready_offer(repository, name='one'):
    from utils.batch_pipeline.contracts import WorkItem as Item

    repository.offer('worker-' + name)
    reservation = repository.reserve('synthetic-owner', 'content', 'deep')
    assert reservation is not None, 'admission expected an idle slot'
    item_work = Item(reservation[0], 'synthetic-owner', 1, 'encrypted:shadow', 2, 0, shadow=True, privacy_generation=0)
    assert repository.ready(reservation, item_work, '') is True
    return item_work


def test_shadow_handoff_pins_typed_staged_evidence(repository):
    shadow_item = ready_offer(repository)
    repository.take('worker-one')
    assert repository.handoff(
        shadow_item.segment_id, ValidationFailureWork(shadow_item.segment_id, 'fetch_decode', STAGED)
    )
    job = repository.store.job(shadow_item.segment_id)
    assert job['state'] == 'recovery_ready'
    assert job['worker_failure'] == {'stage': 'fetch_decode', 'reason': STAGED}


def test_shadow_handoff_still_pins_recovery_evidence(repository):
    shadow_item = ready_offer(repository)
    repository.take('worker-one')
    from utils.batch_pipeline.contracts import RecoveryWork

    assert repository.handoff(shadow_item.segment_id, RecoveryWork(shadow_item.segment_id))
    assert repository.store.job(shadow_item.segment_id)['state'] == 'recovery_ready'


def test_shadow_handoff_refuses_untyped_evidence(repository):
    shadow_item = ready_offer(repository)
    repository.take('worker-one')
    with pytest.raises(ValueError, match='typed worker recovery evidence required'):
        repository.handoff(shadow_item.segment_id, {'stage': 'fetch_decode', 'reason': STAGED})


def test_shadow_take_refuses_after_typed_staged_recovery_ready(repository):
    shadow_item = ready_offer(repository)
    repository.take('worker-one')
    repository.handoff(shadow_item.segment_id, ValidationFailureWork(shadow_item.segment_id, 'fetch_decode', STAGED))
    assert repository.take('worker-two') is None


# --- the closed vocabulary gates keep the staged reason ------------------------------


def test_staged_reason_is_a_closed_vocabulary_member():
    from utils.batch_pipeline.errors import WORKER_VALIDATION_REASONS, validate_worker_failure

    assert STAGED in WORKER_VALIDATION_REASONS
    validate_worker_failure({'stage': 'fetch_decode', 'reason': STAGED})


def test_staged_reason_passes_the_evidence_gate():
    from utils.batch_pipeline.errors import validate_worker_failure_evidence

    validate_worker_failure_evidence({'stage': 'fetch_decode', 'reason': STAGED})


def test_staged_refusal_reason_is_content_free():
    assert STAGED == 'staged_audio_invalid'
    assert len(STAGED) <= 40


def test_staged_and_retained_refusal_reasons_stay_distinct():
    retained = WorkerValidationReason.RETAINED_AUDIO_INVALID.value
    assert STAGED != retained


# --- protocol and store invariants for the staged refusal ----------------------------


def test_protocol_staged_hold_is_idempotent_fenced(setup):
    client, _, binding, _, _, recovery = setup
    token = recovery.protocol.prepare('bad', binding.owner_id, 100)['recovery']['token']
    assert recovery.protocol.hold_invalid_manifest(
        'bad', token, 100, audio_uri='gs://synthetic/audio', refusal_reason=STAGED
    )
    assert not recovery.protocol.hold_invalid_manifest(
        'bad', token, 100, audio_uri='gs://synthetic/audio', refusal_reason=STAGED
    )


@pytest.mark.parametrize('reason', ['staged_audio_invalid', 'retained_audio_invalid', 'invalid_retained_manifest'])
def test_protocol_hold_accepts_every_closed_permanent_family(setup, reason):
    client, _, binding, _, _, recovery = setup
    token = recovery.protocol.prepare('bad', binding.owner_id, 100)['recovery']['token']
    assert recovery.protocol.hold_invalid_manifest(
        'bad', token, 100, audio_uri='gs://synthetic/audio', refusal_reason=reason
    )
    assert row(client)['recovery']['refusal'] == {'reason': reason}


def test_protocol_staged_hold_refuses_a_live_lease(setup):
    client, _, binding, _, _, recovery = setup
    token = recovery.protocol.prepare('bad', binding.owner_id, 100)['recovery']['token']
    client.rows['batch_pipeline_prod_jobs', 'bad']['lease_until'] = 200
    assert not recovery.protocol.hold_invalid_manifest(
        'bad', token, 100, audio_uri='gs://synthetic/audio', refusal_reason=STAGED
    )


def test_staged_hold_never_touches_the_results_table(setup, monkeypatch):
    client, _, _, artifacts, _, _ = setup
    artifacts.fetch_audio.side_effect = StagedAudioInvalid('invalid staged WAV container')
    http = serve(setup, monkeypatch)
    http.post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    results_rows = [key for key in client.rows if 'results' in key[0] and key[1] == 'bad']
    assert results_rows == []


def test_failed_held_keeps_the_quarantine_reason(setup, monkeypatch):
    client, _, _, artifacts, _, _ = setup
    artifacts.fetch_audio.side_effect = StagedAudioInvalid('invalid staged WAV container')
    serve(setup, monkeypatch).post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    job = row(client)
    assert job['quarantine_reason'] == 'worker_failed'
    assert job['recovery_state'] == 'failed_held'


def test_recovery_state_ledger_for_the_staged_hold(setup, monkeypatch):
    client, _, binding, artifacts, _, recovery = setup
    assert row(client)['recovery_state'] == 'held'
    token = recovery.protocol.prepare('bad', binding.owner_id, 100)['recovery']['token']
    assert row(client)['recovery_state'] == 'prepared'
    artifacts.fetch_audio.side_effect = StagedAudioInvalid('invalid staged WAV container')
    serve(setup, monkeypatch).post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    assert row(client)['recovery_state'] == 'failed_held'


def test_bare_value_error_recovery_log_has_no_failed_held_line(setup, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    client, _, _, artifacts, _, _ = setup
    artifacts.fetch_audio.side_effect = ValueError('retained audio reference is outside admitted source')
    serve(setup, monkeypatch).post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    assert 'outcome=failed_held' not in caplog.text


def test_typed_and_retryable_refusals_take_different_status_codes(setup, monkeypatch):
    client, _, _, artifacts, _, _ = setup
    http = serve(setup, monkeypatch)
    artifacts.fetch_audio.side_effect = StagedAudioInvalid('invalid staged WAV container')
    assert http.post('/v2/batch-pipeline/recover-quarantine', json=RECOVER).status_code == 200
    client.rows['batch_pipeline_prod_jobs', 'bad']['recovery_state'] = 'held'
    client.rows['batch_pipeline_prod_jobs', 'bad']['recovery'] = {}
    artifacts.fetch_audio.side_effect = ValueError('retained audio reference is outside admitted source')
    assert http.post('/v2/batch-pipeline/recover-quarantine', json=RECOVER).status_code == 500


def test_shadow_handoff_refuses_a_mismatched_segment_for_staged(repository):
    shadow_item = ready_offer(repository)
    repository.take('worker-one')
    with pytest.raises(ValueError, match='typed worker recovery evidence required'):
        repository.handoff('sh_other', ValidationFailureWork(shadow_item.segment_id, 'fetch_decode', STAGED))


def test_failed_held_unit_is_not_prepared_again_after_a_new_offer(repository):
    shadow_item = ready_offer(repository)
    repository.take('worker-one')
    repository.handoff(shadow_item.segment_id, ValidationFailureWork(shadow_item.segment_id, 'fetch_decode', STAGED))
    assert repository.take('worker-two') is None


def test_staged_refusal_dict_has_exactly_the_reason_key(setup, monkeypatch):
    client, _, _, artifacts, _, _ = setup
    artifacts.fetch_audio.side_effect = StagedAudioInvalid('invalid staged WAV container')
    serve(setup, monkeypatch).post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    assert set(row(client)['recovery']['refusal']) == {'reason'}


def test_quarantined_job_keeps_the_typed_worker_failure_through_the_hold(setup, monkeypatch):
    client, _, _, artifacts, _, _ = setup
    client.rows['batch_pipeline_prod_jobs', 'bad']['worker_failure'] = {
        'stage': 'fetch_decode',
        'reason': STAGED,
    }
    artifacts.fetch_audio.side_effect = StagedAudioInvalid('invalid staged WAV container')
    serve(setup, monkeypatch).post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    job = row(client)
    assert job['worker_failure'] == {'stage': 'fetch_decode', 'reason': STAGED}
    assert job['recovery']['refusal'] == {'reason': STAGED}


def test_staged_evidence_stage_matches_the_fetch_decode_token(setup, monkeypatch):
    from utils.observability.reasons import WorkerValidationStage

    client, _, _, artifacts, _, _ = setup
    client.rows['batch_pipeline_prod_jobs', 'bad']['worker_failure'] = {
        'stage': WorkerValidationStage.FETCH_DECODE.value,
        'reason': STAGED,
    }
    artifacts.fetch_audio.side_effect = StagedAudioInvalid('invalid staged WAV container')
    serve(setup, monkeypatch).post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    assert row(client)['worker_failure']['stage'] == 'fetch_decode'


def test_staged_hold_works_without_prior_worker_failure_evidence(setup, monkeypatch):
    # The recovery fence holds on the deterministic fetch fault itself; it
    # does not require the worker diagnosis to be present.
    client, _, _, artifacts, _, _ = setup
    assert 'worker_failure' not in row(client)
    artifacts.fetch_audio.side_effect = StagedAudioInvalid('invalid staged WAV container')
    response = serve(setup, monkeypatch).post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    assert response.json() == {'status': 'failed_held'}
    assert row(client)['recovery']['refusal'] == {'reason': STAGED}


def test_staged_hold_keeps_the_audio_uri_binding(setup, monkeypatch):
    client, _, _, artifacts, _, _ = setup
    artifacts.fetch_audio.side_effect = StagedAudioInvalid('invalid staged WAV container')
    serve(setup, monkeypatch).post('/v2/batch-pipeline/recover-quarantine', json=RECOVER)
    assert row(client)['audio_uri'] == 'gs://synthetic/audio'
