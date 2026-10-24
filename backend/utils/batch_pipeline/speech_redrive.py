"""One explicit operator-paid epoch, with create-only output reconciliation."""

from utils.observability.stt_cap_dispatch import DispatchPath, DispatchReason, record_decision

from dataclasses import fields
import time

from database.batch_pipeline_policy import load_stage_policy, UnpinnedPolicyRefused
from config.prerecorded_stt import require_provider_environment, PrerecordedSTTService
from config.stt_cap_dispatch import execution_admission_enabled as cap_enabled
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection_protocol import normalized_binding
from database.batch_pipeline_speech_redrive import SpeechRedriveStore
from utils.batch_pipeline.contracts import WorkItem
from utils.batch_pipeline.quarantine_recovery import transcribe, log_failure, log_terminal_empty
from utils.batch_pipeline.correctness_metrics import record as record_correctness
from utils.batch_pipeline.recovery_disposition import (
    inspect_audio,
    result_outcome,
    RecoveryFailure,
    MultilingualEmpty,
    terminal_empty_payload,
    padded_empty,
    padded_skipped,
)
from utils.batch_pipeline.admission import admitted_as_byok
from utils.stt_cap_dispatch import sync_allowed, funded_allowance
from utils.observability.fallback import record_fallback
from utils.observability.stt_cap_dispatch import record_audio


def redrive_one(
    store,
    artifacts,
    sid,
    uid,
    plan_digest,
    expected_recovery,
    *,
    server_flags,
    silent=False,
    clock=time.time,
    stt=transcribe,
    gpu_padded_retry_empty=False
):
    """No automatic retry after dispatch, even on uncertain network/process loss.

    `server_flags` is required: the serving role's live settings for a unit with
    no stored recovery part, or None to refuse that unit ('policy_unpinned').
    This operator process's own environment is never pinned.
    """
    try:
        _, policy = load_stage_policy(store, sid, 'recovery', server_flags=server_flags)
    except UnpinnedPolicyRefused:
        return 'policy_unpinned'
    if policy is None or not policy.speech_empty_multilingual or not policy.recovery_enabled:
        return 'disabled'
    protocol = SpeechRedriveStore(store, server_flags=server_flags)
    job = protocol.prepare(
        sid, uid, plan_digest, expected_recovery, clock(), gpu_padded_retry_empty=gpu_padded_retry_empty, silent=silent
    )
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
            outcome = result_outcome(payload)
            if outcome not in {'success', 'no_recoverable_speech'} or (
                outcome == 'success' and not payload.get('words')
            ):
                raise RecoveryFailure('payload_validation', 'invalid_payload')
            return (
                'reconciled'
                if protocol.settle(sid, token, plan_digest, clock(), uri, outcome=result_outcome(payload))
                else 'fenced'
            )
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
    if admitted_as_byok(job):
        record_decision(DispatchPath.SPEECH_REDRIVE, True, DispatchReason.BYOK)
    elif not sync_allowed(uid, item.duration_seconds, 'modulate', lane='batch', path=DispatchPath.SPEECH_REDRIVE):
        return 'allowance_held'
    # Check deployment dependencies before spending the sole intent. No fallback
    # to Parakeet is permitted if the alternate provider is unconfigured.
    require_provider_environment(PrerecordedSTTService.MODULATE)
    if not protocol.start(sid, token, plan_digest, clock()):
        return 'fenced'
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
        if (
            policy.terminal_empty_disposition
            and isinstance(error, MultilingualEmpty)
            and not padded_skipped(job)
            and (padded_empty(job) or marker.get('gpu_padded_retry_empty') is True)
        ):
            payload = terminal_empty_payload(error.duration, error.spans)
            failure = None
    else:
        failure = None
    if failure:
        if protocol.settle(sid, token, plan_digest, clock(), failure=failure):
            log_failure(failure)
        return 'failed_held'
    if payload is None:
        raise RecoveryFailure('payload_validation', 'invalid_payload')
    # The operator path meters only answers with words. The automatic recovery
    # path also meters valid-empty Modulate answers as accepted provider audio.
    if cap_enabled(uid, 'batch') and result_outcome(payload) != 'no_recoverable_speech':
        record_audio(
            'sync',
            'accepted',
            'modulate',
            item.duration_seconds,
            funded_allowance(uid, lane='batch').reason == 'plan_allowance_exhausted',
        )
    # A storage/commit exception intentionally leaves running intact. A later
    # invocation may reconcile the object, but can never call the provider again.
    uri = artifacts.persist_recovery_result(item, payload, token)
    outcome = result_outcome(payload)
    changed = protocol.settle(sid, token, plan_digest, clock(), uri, outcome=outcome)
    if changed and outcome == 'no_recoverable_speech':
        record_correctness('no_recoverable_speech', seconds=item.duration_seconds)
        log_terminal_empty()
    return 'recovered' if changed else 'fenced'
