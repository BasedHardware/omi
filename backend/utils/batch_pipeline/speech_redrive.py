"""One explicit operator-paid epoch, with create-only output reconciliation."""

from dataclasses import fields
import time

from config.batch_pipeline import recovery_enabled_for, speech_empty_multilingual_enabled
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection_protocol import normalized_binding
from database.batch_pipeline_speech_redrive import SpeechRedriveStore
from utils.batch_pipeline.contracts import WorkItem
from utils.batch_pipeline.quarantine_recovery import transcribe, log_failure
from utils.batch_pipeline.recovery_disposition import inspect_audio, result_outcome, RecoveryFailure
from utils.stt_cap_dispatch import sync_allowed


def redrive_one(store, artifacts, sid, uid, plan_digest, expected_recovery, *, clock=time.time, stt=transcribe):
    """No automatic retry after dispatch, even on uncertain network/process loss."""
    if not speech_empty_multilingual_enabled() or not recovery_enabled_for(uid):
        return 'disabled'
    protocol = SpeechRedriveStore(store)
    job = protocol.prepare(sid, uid, plan_digest, expected_recovery, clock())
    marker = job['speech_redrive']
    token = marker['token']
    item = WorkItem(**{f.name: job[f.name] for f in fields(WorkItem) if f.name in job})
    if marker['state'] == 'completed':
        return 'already_applied'
    if marker['state'] == 'failed_held':
        return 'failed_held'
    if marker['state'] == 'running':
        uri = artifacts.find_recovery_result(item, token)
        if uri:
            payload = artifacts.load_result(item, uri)
            if result_outcome(payload) != 'success' or not payload.get('words'):
                raise RecoveryFailure('payload_validation', 'invalid_payload')
            return 'reconciled' if protocol.settle(sid, token, plan_digest, clock(), uri) else 'fenced'
        if clock() - marker['started_at'] > 900:
            failure = {'stage': 'provider', 'reason': 'abandoned_running'}
            if protocol.settle(sid, token, plan_digest, clock(), failure=failure):
                log_failure(failure)
                return 'failed_held'
        return 'running_held'
    audio = artifacts.fetch_audio(item)
    _, _, spans = inspect_audio(item, audio)
    if not spans:
        raise RecoveryFailure('strict_vad', 'no_speech')
    if not sync_allowed(uid, item.duration_seconds):
        return 'allowance_held'
    # Check deployment dependencies before spending the sole intent. No fallback
    # to Parakeet is permitted if the alternate provider is unconfigured.
    from config.prerecorded_stt import require_provider_environment, PrerecordedSTTService

    require_provider_environment(PrerecordedSTTService.MODULATE)
    if not protocol.start(sid, token, plan_digest, clock()):
        return 'fenced'
    from utils.observability.fallback import record_fallback

    record_fallback(
        component='stt_selection', from_mode='batch', to_mode='modulate', reason='other', outcome='degraded'
    )
    payload = None
    try:
        payload = stt(item, normalized_binding(job['projection_binding']), audio, multilingual=True)
        if result_outcome(payload) != 'success' or not payload.get('words'):
            raise RecoveryFailure('payload_validation', 'invalid_payload')
    except BatchPrivacyBlocked:
        raise
    except Exception as error:
        failure = (
            {'stage': error.stage, 'reason': error.reason}
            if isinstance(error, RecoveryFailure)
            else {'stage': 'provider', 'reason': 'operation_failed'}
        )
    else:
        failure = None
    if failure:
        if protocol.settle(sid, token, plan_digest, clock(), failure=failure):
            log_failure(failure)
        return 'failed_held'
    if payload is None:
        raise RecoveryFailure('payload_validation', 'invalid_payload')
    from config.stt_cap_dispatch import enabled as cap_enabled
    from utils.stt_cap_dispatch import funded_allowance
    from utils.observability.stt_cap_dispatch import record_audio

    if cap_enabled():
        record_audio(
            'sync',
            'accepted',
            'unknown',
            item.duration_seconds,
            funded_allowance(uid).reason == 'plan_allowance_exhausted',
        )
    # A storage/commit exception intentionally leaves running intact. A later
    # invocation may reconcile the object, but can never call the provider again.
    uri = artifacts.persist_recovery_result(item, payload, token)
    return 'recovered' if protocol.settle(sid, token, plan_digest, clock(), uri) else 'fenced'
