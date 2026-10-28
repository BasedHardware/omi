"""One explicit operator-paid epoch, with create-only output reconciliation."""

from utils.observability.stt_cap_dispatch import DispatchPath, DispatchReason, record_decision

from dataclasses import fields
import time

from database.batch_pipeline_policy import load_stage_policy, UnpinnedPolicyRefused
from config.prerecorded_stt import require_provider_environment, PrerecordedSTTService
from config.stt_cap_dispatch import execution_admission_enabled as cap_enabled
from config.batch_pipeline_empty_asr import terminal_empty_allowed
from config.batch_language_recovery import (
    MAX_AUDIO_SECONDS,
    allowed as independent_allowed,
    below_silence_threshold,
    duration_limited,
    language_guarded,
    prior_modulate_empty,
    words_repair_eligible,
)
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection_protocol import normalized_binding
from database.batch_pipeline_quarantine_recovery import RecoveryStore
from database.batch_pipeline_speech_redrive import SpeechRedriveStore, independent_redrive
from database.batch_pipeline_recognizer_receipts import record_recognizer
from utils.batch_pipeline.contracts import WorkItem, held_vad_census, held_result_allowed, worker_vad_speech
from utils.batch_pipeline.quarantine_recovery import log_failure, log_terminal_empty
from utils.batch_pipeline.recovery_recognizers import transcribe, second_transcribe
from utils.batch_pipeline.correctness_metrics import record as record_correctness
from utils.batch_pipeline.recovery_disposition import (
    inspect_audio,
    result_outcome,
    result_vad_evidence,
    RecoveryFailure,
    MultilingualEmpty,
    terminal_empty_payload,
    padded_empty,
    padded_skipped,
    independent_silence_payload,
    WordsWithoutVad,
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
    gpu_padded_retry_empty=False,
    independent_stt=second_transcribe,
    independent_language=False,
    repair=False,
):
    """No automatic retry after dispatch, even on uncertain network/process loss.

    `repair` is the explicit lead-7fa3d2 language-guard words repair: one
    Modulate call per unit (paid epoch 4) under bound worker VAD evidence. It
    never consults or bypasses the spent independent (Soniox) attempt.

    `server_flags` is required: the serving role's live settings for a unit with
    no stored recovery part, or None to refuse that unit ('policy_unpinned').
    This operator process's own environment is never pinned.
    """
    try:
        original_job, policy = load_stage_policy(store, sid, 'recovery', server_flags=server_flags)
    except UnpinnedPolicyRefused:
        return 'policy_unpinned'
    if policy is None or not policy.recovery_enabled:
        return 'disabled'
    if repair:
        if independent_language or not words_repair_eligible(original_job):
            return 'repair_not_eligible'
    elif not policy.speech_empty_multilingual and not independent_redrive(original_job):
        return 'disabled'
    elif independent_redrive(original_job) != independent_language:
        return 'independent_plan_required'
    protocol = SpeechRedriveStore(store, server_flags=server_flags)
    job = protocol.prepare(
        sid,
        uid,
        plan_digest,
        expected_recovery,
        clock(),
        gpu_padded_retry_empty=gpu_padded_retry_empty,
        silent=silent,
        repair=repair,
    )
    marker = job['speech_redrive']
    token = marker['token']
    item = WorkItem(**{f.name: job[f.name] for f in fields(WorkItem) if f.name in job})
    independent = not repair and independent_redrive(job)
    provider = 'soniox' if independent else 'modulate'
    if marker['state'] == 'completed':
        return 'already_applied'
    if marker['state'] == 'failed_held':
        return 'failed_held'
    if marker['state'] == 'running':
        uri = artifacts.find_recovery_result(item, token)
        if uri:
            payload = artifacts.load_result(item, uri)
            outcome = result_outcome(payload)
            if outcome not in {'success', 'no_recoverable_speech', 'silence'} or (
                outcome == 'success' and not payload.get('words')
            ):
                raise RecoveryFailure('payload_validation', 'invalid_payload')
            measured = result_vad_evidence(payload)
            independent_silence = payload.get('words_provider') == 'independent_empty_strict_vad'
            if not held_result_allowed(job, outcome, measured, independent=independent_silence):
                failure = {'stage': 'payload_validation', 'reason': 'invalid_payload'}
                return (
                    'failed_held'
                    if protocol.settle(
                        sid, token, plan_digest, clock(), failure=failure, measured_held_vad_speech_seconds=measured
                    )
                    else 'fenced'
                )
            return (
                'reconciled'
                if protocol.settle(
                    sid,
                    token,
                    plan_digest,
                    clock(),
                    uri,
                    outcome=outcome,
                    measured_held_vad_speech_seconds=measured,
                    independent_silence=independent_silence,
                )
                else 'fenced'
            )
        if clock() - marker['started_at'] > 900:
            failure = {'stage': 'provider', 'reason': 'abandoned_running'}
            if protocol.settle(sid, token, plan_digest, clock(), failure=failure):
                log_failure(failure)
                return 'failed_held'
        return 'running_held'
    audio = artifacts.fetch_audio(item)
    _, duration, spans = inspect_audio(item, audio)
    measured = sum(span['end'] - span['start'] for span in spans)
    # Bound worker VAD may locate guarded words that strict CPU VAD missed.
    worker = worker_vad_speech(job) if independent or repair else None
    if independent and not protocol.observe_vad(sid, token, plan_digest, measured):
        return 'fenced'
    if not spans and not independent and worker is None:
        raise RecoveryFailure('strict_vad', 'no_speech')
    if independent and not independent_allowed(duration):
        return 'independent_budget_held'
    # The decoded audio (up to 0.1 s past the declared duration) bounds the repair call.
    if repair and duration > MAX_AUDIO_SECONDS:
        return 'repair_budget_held'
    if admitted_as_byok(job) and not independent and not repair:
        record_decision(DispatchPath.SPEECH_REDRIVE, True, DispatchReason.BYOK)
    elif not sync_allowed(
        uid,
        max(duration, item.duration_seconds) if repair else item.duration_seconds,
        provider,
        lane='batch',
        path=DispatchPath.SPEECH_REDRIVE,
    ):
        return 'allowance_held'
    # Check deployment dependencies before spending the sole intent. No fallback
    # to Parakeet is permitted if the alternate provider is unconfigured.
    if independent:
        require_provider_environment(PrerecordedSTTService.SONIOX)
    else:
        require_provider_environment(PrerecordedSTTService.MODULATE)
    if not protocol.start(sid, token, plan_digest, clock()):
        return 'fenced'
    record_fallback(component='stt_selection', from_mode='batch', to_mode=provider, reason='other', outcome='degraded')
    payload, billable_independent = None, False
    first_empty = prior_modulate_empty(job)
    if independent:
        record_recognizer(
            store,
            sid,
            token,
            'speech_redrive',
            'modulate',
            'empty' if first_empty else 'error',
            0 if first_empty else None,
            measured,
        )
        if not record_recognizer(store, sid, token, 'speech_redrive', provider, 'started', None, measured, claim=True):
            return 'running_held'
    if repair and not record_recognizer(
        store, sid, token, 'speech_redrive', provider, 'started', None, measured, claim=True
    ):
        return 'running_held'
    try:
        payload = (
            independent_stt(item, audio, MultilingualEmpty(duration, spans, worker))
            if independent
            else stt(
                item,
                normalized_binding(job['projection_binding']),
                audio,
                multilingual=True,
                **({'force_recognition': True, 'worker_speech': worker} if repair else {}),
            )
        )
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
        if independent or repair:
            empty = isinstance(error, MultilingualEmpty)
            billable_independent = isinstance(error, (MultilingualEmpty, WordsWithoutVad))
            count = error.word_count if isinstance(error, WordsWithoutVad) else 0 if empty else None
            record_recognizer(
                store,
                sid,
                token,
                'speech_redrive',
                provider,
                'words' if count else 'empty' if empty else 'error',
                count,
                measured,
            )
            if independent and empty and first_empty and below_silence_threshold(held_vad_census(job, measured)):
                payload = independent_silence_payload(duration, spans)
                failure = None
        if (
            not independent
            and not repair
            and policy.terminal_empty_disposition
            and isinstance(error, MultilingualEmpty)
            and terminal_empty_allowed(error.spans)
            and not padded_skipped(job)
            and (padded_empty(job) or marker.get('gpu_padded_retry_empty') is True)
        ):
            payload = terminal_empty_payload(error.duration, error.spans)
            failure = None
    else:
        failure = None
        if independent or repair:
            billable_independent = independent
            record_recognizer(store, sid, token, 'speech_redrive', provider, 'words', len(payload['words']), measured)
    if independent and billable_independent and cap_enabled(uid, 'batch'):
        # Valid empty responses also consume vendor spend.
        record_audio(
            'sync',
            'accepted',
            provider,
            item.duration_seconds,
            funded_allowance(uid, lane='batch').reason == 'plan_allowance_exhausted',
        )
    if failure:
        if protocol.settle(
            sid,
            token,
            plan_digest,
            clock(),
            failure=failure,
            measured_held_vad_speech_seconds=measured,
        ):
            log_failure(failure)
        return 'failed_held'
    if payload is None:
        raise RecoveryFailure('payload_validation', 'invalid_payload')
    # The operator path meters only answers with words. The automatic recovery
    # path also meters valid-empty Modulate answers as accepted provider audio.
    if not independent and cap_enabled(uid, 'batch') and result_outcome(payload) != 'no_recoverable_speech':
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
    changed = protocol.settle(
        sid,
        token,
        plan_digest,
        clock(),
        uri,
        outcome=outcome,
        measured_held_vad_speech_seconds=result_vad_evidence(payload),
        independent_silence=payload.get('words_provider') == 'independent_empty_strict_vad',
    )
    if changed and outcome == 'no_recoverable_speech':
        record_correctness('no_recoverable_speech', seconds=item.duration_seconds)
        log_terminal_empty()
    return 'recovered' if changed else 'fenced'


def prepared_independent_one(
    store,
    artifacts,
    sid,
    uid,
    max_seconds,
    *,
    server_flags,
    clock=time.time,
    independent_stt=second_transcribe,
):
    """Operator take-over of a sealed prepared epoch-1 intent; one Soniox call at most.

    Only this path may admit a language-guarded unit above the global 60s
    independent bound, and only up to ``max_seconds`` for ids the sealed plan
    froze. The existing epoch-1 token fence (``RecoveryStore.start``) stays the
    sole paid-intent CAS: no new intent is created, custody is preserved, and
    nothing is deleted. A unit that #23795's duration-limit refusal already
    settled without ever starting the intent is admitted through the mirrored
    ``RecoveryStore.start_duration_limited``; a spent intent never reopens. The
    sealed cohort file and the lead's approved plan sha are the audit trail;
    the receipts record the spend itself. An empty or failed answer settles
    ``failed_held`` through the same Soniox receipts as the runtime independent
    route; it never fabricates the unattempted Modulate receipt that the
    independent silence contract requires, so a guarded take-over cannot
    settle silence.
    """
    try:
        job, policy = load_stage_policy(store, sid, 'recovery', server_flags=server_flags)
    except UnpinnedPolicyRefused:
        return 'policy_unpinned'
    if policy is None or not policy.recovery_enabled:
        return 'disabled'
    recovery = job.get('recovery') or {}
    if not language_guarded(job) or recovery.get('epoch') != 1 or not recovery.get('token'):
        return 'unit_not_eligible'
    item = WorkItem(**{f.name: job[f.name] for f in fields(WorkItem) if f.name in job})
    if not MAX_AUDIO_SECONDS < item.duration_seconds <= max_seconds:
        return 'independent_budget_held'
    protocol = RecoveryStore(store)
    token = recovery['token']
    if job.get('result'):
        return 'already_applied'
    # A duration-limit refusal (#23795) never spent the intent; it reopens here.
    reopen = duration_limited(job)
    if job['recovery_state'] == 'failed_held' and not reopen:
        return 'failed_held'
    if job['recovery_state'] == 'running':
        # A crashed take-over reconciles its artifact without repeating STT.
        uri = artifacts.find_recovery_result(item, token)
        if uri:
            payload = artifacts.load_result(item, uri)
            outcome = result_outcome(payload)
            if outcome != 'success' or not payload.get('words'):
                failure = {'stage': 'payload_validation', 'reason': 'invalid_payload'}
                return (
                    'failed_held'
                    if protocol.settle(
                        sid,
                        token,
                        clock(),
                        failure=failure,
                        measured_held_vad_speech_seconds=result_vad_evidence(payload),
                    )
                    else 'fenced'
                )
            changed = protocol.settle(
                sid,
                token,
                clock(),
                uri,
                outcome=outcome,
                measured_held_vad_speech_seconds=result_vad_evidence(payload),
                independent_silence=payload.get('words_provider') == 'independent_empty_strict_vad',
            )
            return 'reconciled' if changed else 'fenced'
        if clock() - recovery.get('started_at', 0) > 900:
            failure = {'stage': 'provider', 'reason': 'abandoned_running'}
            if protocol.settle(sid, token, clock(), failure=failure):
                log_failure(failure)
                return 'failed_held'
        return 'running_held'
    if job['recovery_state'] != 'prepared' and not reopen:
        return 'unit_not_eligible'
    audio = artifacts.fetch_audio(item)
    _, duration, spans = inspect_audio(item, audio)
    measured = sum(span['end'] - span['start'] for span in spans)
    # Bound worker VAD may locate guarded words that strict CPU VAD missed.
    worker = worker_vad_speech(job)
    if not reopen and not protocol.observe_vad(sid, token, measured):
        return 'fenced'
    # The allowance is rechecked against the independent provider, exactly as
    # the runtime independent route does; the take-over never bypasses it.
    if not sync_allowed(uid, item.duration_seconds, 'soniox', lane='batch', path=DispatchPath.QUARANTINE):
        return 'allowance_held'
    require_provider_environment(PrerecordedSTTService.SONIOX)
    started = (
        protocol.start_duration_limited(sid, token, clock(), audio_uri=item.audio_uri, audio_seconds=duration)
        if reopen
        else protocol.start(sid, token, clock(), provider='modulate')
    )
    if not started:
        return 'fenced'
    record_fallback(component='stt_selection', from_mode='batch', to_mode='soniox', reason='other', outcome='degraded')
    if not record_recognizer(store, sid, token, 'recovery', 'soniox', 'started', None, measured, claim=True):
        return 'running_held'
    payload, failure, billable = None, None, False
    try:
        payload = independent_stt(item, audio, MultilingualEmpty(duration, spans, worker))
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
        empty = isinstance(error, MultilingualEmpty)
        billable = isinstance(error, (MultilingualEmpty, WordsWithoutVad))
        count = error.word_count if isinstance(error, WordsWithoutVad) else 0 if empty else None
        record_recognizer(
            store,
            sid,
            token,
            'recovery',
            'soniox',
            'words' if count else 'empty' if empty else 'error',
            count,
            measured,
        )
    else:
        billable = True
        record_recognizer(store, sid, token, 'recovery', 'soniox', 'words', len(payload['words']), measured)
    if billable and cap_enabled(uid, 'batch'):
        # Valid empty responses also consume vendor spend.
        record_audio(
            'sync',
            'accepted',
            'soniox',
            item.duration_seconds,
            funded_allowance(uid, lane='batch').reason == 'plan_allowance_exhausted',
        )
    if failure:
        if protocol.settle(sid, token, clock(), failure=failure, measured_held_vad_speech_seconds=measured):
            log_failure(failure)
        return 'failed_held'
    if payload is None:
        raise RecoveryFailure('payload_validation', 'invalid_payload')
    # A storage/commit exception intentionally leaves running intact. A later
    # invocation may reconcile the object, but can never call the provider again.
    uri = artifacts.persist_recovery_result(item, payload, token)
    changed = protocol.settle(
        sid,
        token,
        clock(),
        uri,
        outcome=result_outcome(payload),
        measured_held_vad_speech_seconds=result_vad_evidence(payload),
        independent_silence=payload.get('words_provider') == 'independent_empty_strict_vad',
    )
    return 'recovered' if changed else 'fenced'
