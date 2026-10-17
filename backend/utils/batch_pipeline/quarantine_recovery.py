"""Default-off, at-most-once legacy STT dispatch with durable result reconciliation."""

from dataclasses import fields
import io
import logging
import time
import wave

from utils.stt_cap_dispatch import sync_allowed, funded_allowance
from config.stt_cap_dispatch import execution_admission_enabled as cap_enabled
from utils.observability.stt_cap_dispatch import record_audio
from config.batch_pipeline import (
    recovery_owners,
    recovery_enabled_for,
    recover_all_admitted,
    empty_asr_disposition_enabled,
)
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_quarantine_recovery import RecoveryStore, recovery_candidates, cancel_fenced_recovery
from utils.batch_pipeline.contracts import WorkItem, projection_speech_spans

logger = logging.getLogger(__name__)


def log_failure(failure):
    # Called only outside a provider exception handler; never chain its context.
    try:
        logger.warning('event=batch_recovery_failure stage=%s reason=%s', failure['stage'], failure['reason'])
    except Exception:
        pass


def transcribe(item, binding, audio):
    """Use the sync client directly, with no whole-upload coordinator or retries."""
    from diarizer.batch_pipeline import validate_words
    from utils.stt.pre_recorded import prerecorded_from_bytes

    from utils.batch_pipeline.recovery_disposition import inspect_audio, silence_payload, at_stage, RecoveryFailure

    pcm, duration, spans = inspect_audio(item, audio)
    if not spans:
        if empty_asr_disposition_enabled():
            return silence_payload(duration)
        raise RecoveryFailure('strict_vad', 'no_speech')
    # Keep the authenticated intake manifest in the original artifact only;
    # third-party STT receives canonical audio without ancillary provenance.
    output = io.BytesIO()
    with wave.open(output, 'wb') as clean:
        clean.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        clean.writeframes(pcm)
    # attempts=2 disables all existing client retry branches. An uncertain call
    # must remain held, never be silently reissued by the recovery dispatcher.
    response = at_stage(
        'provider',
        'provider_failed',
        lambda: prerecorded_from_bytes(output.getvalue(), language=binding.language, return_language=True, attempts=2),
    )

    def validate_response():
        if not isinstance(response, tuple) or len(response) != 2:
            raise ValueError('response shape')
        raw, language = response
        if not isinstance(language, str) or not language:
            raise ValueError('response language')
        words = validate_words([{**word, 'word': word['text']} for word in raw], duration)
        if not words:
            raise RecoveryFailure('response_validation', 'empty_asr')
        return words, language

    words, language = at_stage('response_validation', 'invalid_response', validate_response)
    # Preserve legacy speaker labels directly in build_incoming. Exclusive batch
    # diarization turns cannot represent overlapping legacy utterances.
    payload = {
        'audio_seconds': duration,
        'speech_seconds': sum(s['end'] - s['start'] for s in spans),
        'speech_spans': spans,
        'words': words,
        'diarization': {'turns': []},
        'words_provider': 'legacy_sync',
        'language': language,
        'recovery_version': 1,
    }
    at_stage('payload_validation', 'invalid_payload', lambda: projection_speech_spans(payload, duration))
    return payload


class QuarantineRecovery:
    def __init__(self, store, artifacts, *, stt=transcribe, clock=time.time):
        self.store, self.artifacts, self.stt, self.clock = store, artifacts, stt, clock
        self.protocol = RecoveryStore(store)
        self._candidate_after: str | None = None

    def recover(self, segment_id, owner_id):
        if not recovery_enabled_for(owner_id):
            return 'disabled'
        try:
            job = self.protocol.prepare(segment_id, owner_id, self.clock())
            if job is None:
                return 'held'
            item = WorkItem(**{field.name: job[field.name] for field in fields(WorkItem) if field.name in job})
            token = job['recovery']['token']
            if job['recovery_state'] == 'running':
                uri = self.artifacts.find_recovery_result(item, token)
                if uri:
                    from utils.batch_pipeline.recovery_disposition import result_outcome

                    outcome = result_outcome(self.artifacts.load_result(item, uri))
                    return (
                        'reconciled'
                        if self.protocol.settle(segment_id, token, self.clock(), uri, outcome=outcome)
                        else 'held'
                    )
                # Bound the scan dwell without allowing takeover. A very late
                # provider reply is rejected after this terminal transition.
                if self.clock() - job['recovery']['started_at'] > 900:
                    failure = {'stage': 'provider', 'reason': 'abandoned_running'}
                    if self.protocol.settle(segment_id, token, self.clock(), failure=failure):
                        log_failure(failure)
                return 'held'
            disposition = empty_asr_disposition_enabled()
            if not disposition and not sync_allowed(owner_id, item.duration_seconds):
                return 'held'
            audio = self.artifacts.fetch_audio(item)
            local_payload, inspection_failure = None, None
            if disposition:
                from utils.batch_pipeline.recovery_disposition import inspect_audio, silence_payload, RecoveryFailure

                try:
                    _, duration, spans = inspect_audio(item, audio)
                    if not spans:
                        local_payload = silence_payload(duration)
                except RecoveryFailure as error:
                    inspection_failure = error

            # Privacy and the intent token are rechecked after download and
            # immediately before issuing the sole application-level STT call.
            if (
                local_payload is None
                and inspection_failure is None
                and not sync_allowed(owner_id, item.duration_seconds)
            ):
                return 'held'
            if not recovery_enabled_for(owner_id) or not self.protocol.start(segment_id, token, self.clock()):
                return 'held'
            from database.batch_pipeline_projection_protocol import normalized_binding
            from utils.observability.fallback import record_fallback

            if local_payload is None and inspection_failure is None:
                record_fallback(
                    component='stt_selection',
                    from_mode='batch',
                    to_mode='legacy_sync',
                    reason='other',
                    outcome='degraded',
                )
            payload = None
            try:
                if inspection_failure is not None:
                    raise inspection_failure
                payload = (
                    local_payload
                    if local_payload is not None
                    else self.stt(item, normalized_binding(job['projection_binding']), audio)
                )
                from utils.batch_pipeline.recovery_disposition import result_outcome

                result_outcome(payload)
                if cap_enabled() and payload.get('outcome') != 'silence':
                    record_audio(
                        'sync',
                        'accepted',
                        'unknown',
                        item.duration_seconds,
                        funded_allowance(owner_id).reason == 'plan_allowance_exhausted',
                    )
            except BatchPrivacyBlocked:
                raise
            except Exception as error:
                from utils.batch_pipeline.recovery_disposition import RecoveryFailure

                failure = (
                    {'stage': error.stage, 'reason': error.reason}
                    if isinstance(error, RecoveryFailure)
                    else {'stage': 'provider', 'reason': 'operation_failed'}
                )
            else:
                failure = None
            # Log outside the exception handler: logger failures must not chain a private exception.
            if failure:
                if not self.protocol.settle(segment_id, token, self.clock(), failure=failure):
                    return 'held'
                log_failure(failure)
                return 'failed_held'
            if payload is None:
                return 'held'
            # Storage/commit failures leave running intact: the deterministic
            # encrypted object can be reconciled without repeating STT.
            try:
                from utils.batch_pipeline.recovery_disposition import result_outcome

                outcome = result_outcome(payload)
                uri = self.artifacts.persist_recovery_result(item, payload, token)
                changed = self.protocol.settle(segment_id, token, self.clock(), uri, outcome=outcome)
                if changed and outcome == 'silence':
                    record_fallback(
                        component='stt_selection',
                        from_mode='batch',
                        to_mode='none',
                        reason='other',
                        outcome='recovered',
                    )
                return 'recovered' if changed else 'result_held'
            except BatchPrivacyBlocked:
                raise
            except Exception:
                return 'result_held'
        except BatchPrivacyBlocked:
            cancel_fenced_recovery(self.store, segment_id)
            return 'cancelled'
        except ProjectionBlocked:
            return 'held'

    def sweep(self):
        counts = {}
        all_admitted = recover_all_admitted()
        owners = (None,) if all_admitted else recovery_owners()
        for selected_owner in owners:
            if all_admitted:
                candidates = recovery_candidates(
                    self.store.client, self.store.namespace, None, after_id=self._candidate_after
                )
            else:
                candidates = recovery_candidates(self.store.client, self.store.namespace, selected_owner)
            if all_admitted and not candidates:
                self._candidate_after = None  # Wrap next tick, without a second query.
            for segment_id, owner_id in candidates:
                if all_admitted:
                    self._candidate_after = segment_id  # Held/capped rows cannot pin the global page.
                try:
                    outcome = self.recover(segment_id, owner_id)
                except Exception:
                    outcome = 'held'
                counts[outcome] = counts.get(outcome, 0) + 1
                try:
                    logger.info('event=batch_quarantine_recovery outcome=%s', outcome)
                except Exception:
                    pass
                if outcome in {'recovered', 'failed_held', 'result_held', 'cancelled'}:
                    break  # One provider dispatch per queried cohort per sweep; continue at this cursor next tick.
        return counts
