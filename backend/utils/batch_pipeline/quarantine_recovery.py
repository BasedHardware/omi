"""Fenced legacy recovery with bounded independent recognition for language guards."""

from utils.observability.stt_cap_dispatch import DispatchPath, DispatchReason, record_decision

from dataclasses import fields
import hashlib
import os
import re
from urllib.parse import urlsplit
import logging
import threading
import time

from prometheus_client import Counter

from utils.batch_pipeline.admission import admitted_as_byok
from utils.stt_cap_dispatch import sync_allowed, funded_allowance
from config.stt_cap_dispatch import offline_admission_enabled as cap_enabled
from utils.observability.stt_cap_dispatch import record_audio
from utils.observability.fallback import record_fallback
from config.batch_pipeline import (
    LONG_SPEECH_HANDOFF_SECONDS,
    recovery_dispatch_batch_size,
    recovery_wake_lease_seconds,
    empty_asr_disposition_enabled,
    recovery_policy_refresh_enabled,
    second_multilingual_enabled,
)
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_policy import load_stage_policy, refresh_disabled_recovery
from config.policy import kill_switch
from config.batch_pipeline_empty_asr import safety_net_enabled, terminal_empty_allowed
from config.stt_provider_policy import HELD_RECOVERY_SECOND_PROVIDER
from config.batch_language_recovery import (
    MAX_AUDIO_SECONDS,
    allowed as independent_allowed,
    language_guarded,
    below_silence_threshold,
)
from database.batch_pipeline_recognizer_receipts import record_recognizer
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_quarantine_recovery import RecoveryStore, recovery_candidates, cancel_fenced_recovery
from utils.batch_pipeline.contracts import (
    WorkItem,
    held_vad_census,
    held_silence_allowed,
    held_result_allowed,
    worker_vad_speech,
)
from utils.batch_pipeline.recovery_recognizers import (
    transcribe,
    second_transcribe,
    second_transcribe_async,
    recognizer_attempt,
    independent_ready,
)
from utils.batch_pipeline.recovery_steps import ProviderStep, run_sync, run_async
from utils.batch_pipeline.recovery_disposition import (
    inspect_audio,
    silence_payload,
    RecoveryFailure,
    result_outcome,
    result_vad_evidence,
    MultilingualEmpty,
    WordsWithoutVad,
    padded_empty,
    padded_long_speech,
    terminal_empty_payload,
    TWO_PROVIDER_EMPTY_EVIDENCE,
    independent_silence_payload,
)

from utils.cloud_tasks import enqueue_named_task, named_task_exists
from utils.sync.stage import current_stage

logger = logging.getLogger(__name__)

# A delivered wake that could not start (allowance, cap or transient refusal)
# is retried on the former 120s cadence rather than waiting out the lease.
REWAKE_AFTER_HELD_SECONDS = 120
# Consecutive failed custody probes before a new wake is minted regardless.
MAX_WAKE_PROBE_ERRORS = 3
# Billing label from config.stt_provider_policy.HELD_RECOVERY_SECOND_PROVIDER.
# None keeps the historical long-speech hook disabled (Deepgram retired).
# Language-guarded units use the separately bounded Soniox recovery policy.
SECOND_PROVIDER = HELD_RECOVERY_SECOND_PROVIDER
SECOND_PROVIDER_CALLS = Counter(
    'omi_batch_recovery_second_provider_total',
    'Second multilingual recovery calls after a valid-empty Modulate response',
    ['provider', 'outcome'],
)


def log_failure(failure):
    # Called only outside a provider exception handler; never chain its context.
    try:
        logger.warning('event=batch_recovery_failure stage=%s reason=%s', failure['stage'], failure['reason'])
    except Exception:
        pass


def log_terminal_empty():
    record_fallback(component='stt_selection', from_mode='batch', to_mode='none', reason='other', outcome='degraded')
    logger.info('event=batch_terminal_empty stage=response_validation reason=no_recoverable_speech')


def metered(record, *args):
    # Metering is best-effort: it must never change a unit's disposition.
    try:
        record(*args)
    except Exception:
        pass


def record_accepted(owner_id, provider, seconds):
    if cap_enabled(owner_id, 'batch'):
        record_audio(
            'sync',
            'accepted',
            provider,
            seconds,
            funded_allowance(owner_id, lane='batch').reason == 'plan_allowance_exhausted',
        )


def second_provider_eligible(job, empty):
    # The language guard has its own bounded, ship-on independent path.
    if language_guarded(job):
        return independent_allowed(empty.duration)
    if SECOND_PROVIDER is None:
        return False
    speech = sum(span['end'] - span['start'] for span in empty.spans)
    return second_multilingual_enabled() and padded_long_speech(job) and speech >= LONG_SPEECH_HANDOFF_SECONDS


class QuarantineRecovery:
    def __init__(self, store, artifacts, *, stt=transcribe, second_stt=second_transcribe, clock=time.time):
        self.store, self.artifacts, self.stt, self.clock = store, artifacts, stt, clock
        self.second_stt = second_stt
        self.protocol = RecoveryStore(store)
        self._candidate_after: str | None = None
        # The serving pass and the dispatch loop share this instance.
        self._sweeping = threading.Lock()

    def _refreshed(self, segment_id, owner_id, job, policy):
        """A disabled snapshot with no paid intent follows today's recovery setting."""
        if not recovery_policy_refresh_enabled():
            return job, policy
        refreshed = refresh_disabled_recovery(self.store, segment_id, owner_id)
        return refreshed if refreshed is not None else (job, policy)

    def _second_eligible(self, job, empty):
        return second_provider_eligible(job, empty)

    def _second_multilingual(
        self, item, owner_id, audio, empty, policy, *, guarded=False, byok=False, token=None, first_empty=True, job=None
    ):
        """At most one independent call inside the running intent; None leaves custody held."""
        payload, outcome, word_count = None, 'refused', None
        provider = 'soniox' if guarded else SECOND_PROVIDER
        if provider is None:
            return None
        measured = sum(span['end'] - span['start'] for span in empty.spans)
        try:
            # The allowance and consent are rechecked before spending the extra call.
            ready = not guarded or self.second_stt is not second_transcribe or independent_ready()
            if ready and (
                (byok and not guarded)
                or sync_allowed(owner_id, item.duration_seconds, provider, lane='batch', path=DispatchPath.QUARANTINE)
            ):
                if guarded and not record_recognizer(
                    self.store, item.segment_id, token, 'recovery', provider, 'started', None, measured, claim=True
                ):
                    return None
                outcome = 'error'
                record_fallback(
                    component='stt_selection',
                    from_mode='modulate',
                    to_mode=provider,
                    reason='other',
                    outcome='degraded',
                )
                reply = yield ProviderStep(
                    self.second_stt,
                    (item, audio, empty),
                    second_transcribe_async if self.second_stt is second_transcribe else None,
                )
                payload, outcome, word_count = recognizer_attempt(reply.result)
        except (BatchPrivacyBlocked, ProjectionBlocked):
            raise
        except Exception:
            payload, outcome = None, 'error'
        if guarded and outcome in {'words', 'empty', 'error'}:
            record_recognizer(
                self.store,
                item.segment_id,
                token,
                'recovery',
                provider,
                outcome,
                word_count,
                measured,
            )
        elif guarded and outcome == 'refused':
            record_recognizer(self.store, item.segment_id, token, 'recovery', provider, 'refused', None, measured)
        SECOND_PROVIDER_CALLS.labels(provider, outcome).inc()
        try:
            logger.info('event=batch_recovery_second_provider provider=%s outcome=%s', provider, outcome)
        except Exception:
            pass
        if outcome in ('words', 'empty'):
            metered(record_accepted, owner_id, provider, item.duration_seconds)
        if guarded:
            if (
                outcome == 'empty'
                and first_empty
                and below_silence_threshold(
                    held_vad_census(job or {'duration_seconds': item.duration_seconds}, measured)
                )
            ):
                return independent_silence_payload(empty.duration, empty.spans)
            return payload
        if outcome == 'empty' and policy.terminal_empty_disposition and terminal_empty_allowed(empty.spans):
            return terminal_empty_payload(empty.duration, empty.spans, TWO_PROVIDER_EMPTY_EVIDENCE)
        return payload

    def recover(self, segment_id, owner_id):
        """Synchronous operator/test entrypoint; serving uses recover_async."""
        return run_sync(self._recover_steps(segment_id, owner_id))

    async def recover_async(self, segment_id, owner_id):
        return await run_async(self._recover_steps(segment_id, owner_id))

    def _recover_steps(self, segment_id, owner_id):
        try:
            job, policy = load_stage_policy(self.store, segment_id, 'recovery')
            if not job or job.get('owner_id') != owner_id:
                return 'held'
            if not policy.recovery_enabled:
                job, policy = self._refreshed(segment_id, owner_id, job, policy)
            if not policy.recovery_enabled:
                return 'disabled'
            job = self.protocol.prepare(segment_id, owner_id, self.clock())
            if job is None:
                return 'held'
            item = WorkItem(**{field.name: job[field.name] for field in fields(WorkItem) if field.name in job})
            token = job['recovery']['token']
            if job['recovery_state'] == 'running':
                uri = self.artifacts.find_recovery_result(item, token)
                if uri:
                    payload = self.artifacts.load_result(item, uri)
                    outcome = result_outcome(payload)
                    measured = result_vad_evidence(payload)
                    independent = payload.get('words_provider') == 'independent_empty_strict_vad'
                    if not held_result_allowed(job, outcome, measured, independent=independent):
                        failure = {'stage': 'payload_validation', 'reason': 'invalid_payload'}
                        return (
                            'failed_held'
                            if self.protocol.settle(
                                segment_id,
                                token,
                                self.clock(),
                                failure=failure,
                                measured_held_vad_speech_seconds=measured,
                            )
                            else 'held'
                        )
                    return (
                        'reconciled'
                        if self.protocol.settle(
                            segment_id,
                            token,
                            self.clock(),
                            uri,
                            outcome=outcome,
                            measured_held_vad_speech_seconds=measured,
                            independent_silence=independent,
                        )
                        else 'held'
                    )
                # Bound the scan dwell without allowing takeover. A very late
                # provider reply is rejected after this terminal transition.
                if self.clock() - job['recovery']['started_at'] > 900:
                    failure = {'stage': 'provider', 'reason': 'abandoned_running'}
                    if self.protocol.settle(segment_id, token, self.clock(), failure=failure):
                        log_failure(failure)
                return 'held'
            byok = admitted_as_byok(job)
            if byok and not language_guarded(job):
                record_decision(DispatchPath.QUARANTINE, True, DispatchReason.BYOK)
            disposition = (
                language_guarded(job)
                or empty_asr_disposition_enabled()
                or (safety_net_enabled() and self.stt is transcribe)
            )
            if (
                not disposition
                and (not byok or language_guarded(job))
                and not sync_allowed(owner_id, item.duration_seconds, lane='batch', path=DispatchPath.QUARANTINE)
            ):
                return 'held'
            audio = self.artifacts.fetch_audio(item)
            duration = item.duration_seconds
            local_payload, inspection_failure, measured_vad, inspected_spans = None, None, None, None
            if disposition:
                try:
                    _, duration, spans = inspect_audio(item, audio)
                    inspected_spans = spans
                    measured_vad = sum(span['end'] - span['start'] for span in spans)
                    if not spans and not language_guarded(job):
                        if not held_silence_allowed(job, measured_vad):
                            raise RecoveryFailure('payload_validation', 'invalid_payload')
                        local_payload = silence_payload(duration)
                except RecoveryFailure as error:
                    inspection_failure = error
            if language_guarded(job) and inspected_spans == [] and not independent_allowed(duration):
                if duration > MAX_AUDIO_SECONDS and self.protocol.hold_duration_limit(
                    segment_id, token, self.clock(), audio_uri=item.audio_uri, audio_seconds=duration
                ):
                    logger.info('event=batch_quarantine_recovery outcome=failed_held reason=independent_duration_limit')
                    return 'failed_held'
                self.protocol.observe_vad(segment_id, token, 0)
                return 'held'

            # Privacy and the intent token are rechecked after download and
            # immediately before issuing the sole application-level STT call.
            if (
                local_payload is None
                and inspection_failure is None
                and (not byok or language_guarded(job))
                and not sync_allowed(owner_id, item.duration_seconds, lane='batch', path=DispatchPath.QUARANTINE)
            ):
                if measured_vad is not None:
                    self.protocol.observe_vad(segment_id, token, measured_vad)
                return 'held'
            # Existing guard-owned custody must drain safely even after the
            # new-admission guard is rolled back.
            # The worker's bound VAD receipt is the only evidence that may
            # locate recognized words when strict CPU VAD finds no speech.
            worker = worker_vad_speech(job) if language_guarded(job) else None
            multilingual = (
                safety_net_enabled()
                or policy.speech_empty_multilingual
                or ((job.get('worker_failure') or {}).get('reason') == 'unsupported_language')
            )
            if not self.protocol.start(
                segment_id, token, self.clock(), provider='modulate' if multilingual else 'legacy_sync'
            ):
                return 'held'
            from database.batch_pipeline_projection_protocol import normalized_binding

            if local_payload is None and inspection_failure is None:
                record_fallback(
                    component='stt_selection',
                    from_mode='batch',
                    to_mode='modulate' if multilingual else 'legacy_sync',
                    reason='other',
                    outcome='degraded',
                )
            payload, empty, recognized_count = None, None, None
            try:
                if inspection_failure is not None:
                    raise inspection_failure
                payload = (
                    local_payload
                    if local_payload is not None
                    else (
                        self.stt(
                            item,
                            normalized_binding(job['projection_binding']),
                            audio,
                            multilingual=multilingual,
                            force_recognition=language_guarded(job),
                            worker_speech=worker,
                        )
                        if self.stt is transcribe
                        else self.stt(item, normalized_binding(job['projection_binding']), audio)
                    )
                )
                result_outcome(payload)
                if payload.get('outcome') != 'silence':
                    metered(record_accepted, owner_id, 'modulate' if multilingual else 'unknown', item.duration_seconds)
                    if language_guarded(job):
                        raw_words = payload['words']
                        if not isinstance(raw_words, list):
                            raise RecoveryFailure('payload_validation', 'invalid_payload')
                        record_recognizer(
                            self.store,
                            segment_id,
                            token,
                            'recovery',
                            'modulate',
                            'words',
                            len(raw_words),
                            measured_vad,
                        )
            except BatchPrivacyBlocked:
                raise
            except Exception as error:
                recognized_count = error.word_count if isinstance(error, WordsWithoutVad) else None
                failure = (
                    {'stage': error.stage, 'reason': error.reason}
                    if isinstance(error, RecoveryFailure)
                    else {'stage': 'provider', 'reason': 'operation_failed'}
                )
                if multilingual and isinstance(error, MultilingualEmpty):
                    empty = MultilingualEmpty(error.duration, error.spans, worker)
                    measured_vad = sum(span['end'] - span['start'] for span in error.spans)
                    if (
                        not language_guarded(job)
                        and policy.terminal_empty_disposition
                        and padded_empty(job)
                        and terminal_empty_allowed(error.spans)
                    ):
                        payload = terminal_empty_payload(error.duration, error.spans)
                        failure = None
            else:
                failure = None
            first_empty = empty is not None
            if (
                failure
                and language_guarded(job)
                and empty is None
                and inspected_spans is not None
                and inspection_failure is None
            ):
                record_recognizer(
                    self.store,
                    segment_id,
                    token,
                    'recovery',
                    'modulate',
                    'words' if recognized_count else 'error',
                    recognized_count,
                    measured_vad,
                )
                empty = MultilingualEmpty(duration, inspected_spans, worker)
            # Outside the handler: neither metering nor a second provider may chain the first.
            if empty is not None:
                # A valid empty answer is still accepted, billed audio.
                if first_empty or recognized_count:
                    metered(record_accepted, owner_id, 'modulate', item.duration_seconds)
                if first_empty and language_guarded(job):
                    record_recognizer(self.store, segment_id, token, 'recovery', 'modulate', 'empty', 0, measured_vad)
                if failure and self._second_eligible(job, empty):
                    payload = yield from self._second_multilingual(
                        item,
                        owner_id,
                        audio,
                        empty,
                        policy,
                        guarded=(job.get('worker_failure') or {}).get('reason') == 'unsupported_language',
                        byok=byok,
                        token=token,
                        first_empty=first_empty,
                        job=job,
                    )
                    if payload is not None:
                        failure = None
                elif failure and language_guarded(job):
                    record_recognizer(
                        self.store, segment_id, token, 'recovery', 'soniox', 'refused', None, measured_vad
                    )
            # Log outside the exception handler: logger failures must not chain a private exception.
            if failure:
                if not self.protocol.settle(
                    segment_id, token, self.clock(), failure=failure, measured_held_vad_speech_seconds=measured_vad
                ):
                    return 'held'
                log_failure(failure)
                return 'failed_held'
            if payload is None:
                return 'held'
            # Storage/commit failures leave running intact: the deterministic
            # encrypted object can be reconciled without repeating STT.
            try:
                outcome = result_outcome(payload)
                uri = self.artifacts.persist_recovery_result(item, payload, token)
                changed = self.protocol.settle(
                    segment_id,
                    token,
                    self.clock(),
                    uri,
                    outcome=outcome,
                    measured_held_vad_speech_seconds=result_vad_evidence(payload),
                    independent_silence=payload.get('words_provider') == 'independent_empty_strict_vad',
                )
                if changed and outcome == 'no_recoverable_speech':
                    log_terminal_empty()
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

    def dispatch(self, segment_id, owner_id):
        try:
            return self._dispatch(segment_id, owner_id)
        except BatchPrivacyBlocked:
            cancel_fenced_recovery(self.store, segment_id)
            return 'cancelled'
        except ProjectionBlocked:
            return 'held'
        except Exception as error:
            # A broken queue must not move a guarded Soniox poll into a
            # maintenance thread. Keep the prepared obligation for dispatch.
            job, _ = load_stage_policy(self.store, segment_id, 'recovery')
            if job and language_guarded(job):
                logger.warning('event=batch_quarantine_recovery action=dispatch outcome=held')
                return 'held'
            # A lost create-task acknowledgement can race delivery. Both paths
            # adopt the SAME intent; only RecoveryStore.start may spend it.
            logger.warning(
                'event=batch_quarantine_recovery action=dispatch outcome=inline exception_type=%s',
                type(error).__name__,
            )
            record_fallback(
                component='sync_dispatch',
                from_mode='cloud_tasks',
                to_mode='inline',
                reason='enqueue_failed',
                outcome='degraded',
            )
            return self.recover(segment_id, owner_id)

    def _dispatch(self, segment_id, owner_id):
        existing, policy = load_stage_policy(self.store, segment_id, 'recovery')
        if not existing or existing.get('owner_id') != owner_id:
            return 'held'
        if not policy.recovery_enabled:
            existing, policy = self._refreshed(segment_id, owner_id, existing, policy)
        if not policy.recovery_enabled:
            return 'disabled'
        # prepare() is the existing durable privacy/ownership fence. Enqueue
        # acknowledgement loss never spends the intent. The HTTP handler or
        # inline fallback must win prepared -> running before a provider call.
        job = self.protocol.prepare(segment_id, owner_id, self.clock())
        if job is None:
            return 'held'
        if job['recovery_state'] == 'running':
            return self.recover(segment_id, owner_id)  # Artifact reconciliation only.
        audience = os.getenv('BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE', '').strip()
        target = urlsplit(audience)
        if (
            target.scheme != 'https'
            or not target.netloc
            or target.path not in ('', '/')
            or target.query
            or target.fragment
        ):
            raise ValueError('recovery task requires the serving origin audience')
        token = job['recovery']['token']
        digest = hashlib.sha256(segment_id.encode()).hexdigest()
        queue = os.getenv('BATCH_PIPELINE_RECOVERY_TASKS_QUEUE', '').strip() or os.getenv('SYNC_TASKS_QUEUE', '')
        lease, seq = recovery_wake_lease_seconds(), 0
        if lease:
            # One outstanding wake per intent. A leased wake is queued or being
            # delivered, so the sweep adds nothing. At expiry only an
            # authoritative NotFound for that task permits the next wake: a
            # task still waiting in a saturated queue keeps its lease. Parallel
            # deliveries remain fenced by RecoveryStore.start.
            now = self.clock()
            wake = job.get('recovery_wake') or {}
            current = wake.get('seq', 0) if wake.get('token') == token else 0
            if current and wake.get('wake_until', 0) > now:
                return 'pending'  # Read from prepare()'s snapshot: no extra transaction.
            if current and wake.get('probe_errors', 0) < MAX_WAKE_PROBE_ERRORS:
                previous = f'bpr-{current_stage()}-{digest}-{token}-w{current}'
                probe_error = False
                try:
                    alive = named_task_exists(wake.get('queue') or queue, previous)
                except Exception:
                    # Unknown custody keeps the old wake; bounded so a broken
                    # probe cannot strand the intent.
                    alive, probe_error = True, True
                if alive:
                    self.protocol.extend_wake(segment_id, token, current, now, lease, probe_error=probe_error)
                    return 'pending'
            seq = self.protocol.claim_wake(segment_id, token, now, lease, queue=queue, expected_seq=current)
            if seq is None:
                return 'pending'
            task_id = f'bpr-{current_stage()}-{digest}-{token}-w{seq}'
        else:
            # Kill switch: legacy time-bucketed wake on every sweep.
            task_id = f'bpr-{current_stage()}-{digest}-{token}-{int(self.clock() // 120)}'
        try:
            enqueue_named_task(
                queue,
                audience.rstrip('/') + '/v2/batch-pipeline/recover-quarantine',
                task_id,
                {'stage': current_stage(), 'segment_id': segment_id},
                audience=audience,
                invoker_sa=os.getenv('SYNC_TASKS_INVOKER_SA', '').strip(),
            )
        except Exception:
            # The task may not exist. If the inline fallback leaves the intent
            # prepared, re-wake on the 120s cadence rather than the full lease.
            if lease:
                try:
                    self.protocol.shorten_wake(segment_id, seq, self.clock(), REWAKE_AFTER_HELD_SECONDS)
                except Exception:
                    pass
            raise
        return 'queued'

    def delivered(self, segment_id, outcome, task_name=None):
        """A delivery of wake ``-w<seq>`` that left the intent prepared re-arms the
        120s cadence for that wake only. Legacy or unnamed deliveries change nothing."""
        match = re.search(r'-w([0-9]{1,9})$', str(task_name or '').rsplit('/', 1)[-1])
        if outcome == 'held' and match and recovery_wake_lease_seconds():
            self.protocol.shorten_wake(segment_id, int(match.group(1)), self.clock(), REWAKE_AFTER_HELD_SECONDS)

    def sweep(self):
        if not self._sweeping.acquire(blocking=False):
            return {}  # A concurrent scan of the same instance is already dispatching.
        try:
            return self._sweep()
        finally:
            self._sweeping.release()

    def _sweep(self):
        counts = {}
        budget = recovery_dispatch_batch_size()
        # Discovery is independent of today's admission/recovery cohort. Every
        # candidate is authorized by its recorded policy; rollback must drain it.
        candidates = recovery_candidates(
            self.store.client, self.store.namespace, None, limit=budget, after_id=self._candidate_after
        )
        if not candidates:
            self._candidate_after = None
        for segment_id, owner_id in candidates[:budget]:
            self._candidate_after = segment_id
            try:
                _, policy = load_stage_policy(self.store, segment_id, 'recovery')
                task = (
                    kill_switch('BATCH_PIPELINE_RECOVERY_TASKS_ENABLED', policy_id=policy.policy_id)
                    if policy
                    else False
                )
                outcome = (self.dispatch if task else self.recover)(segment_id, owner_id)
            except Exception as error:
                logger.warning(
                    'event=batch_quarantine_recovery action=dispatch outcome=retry exception_type=%s',
                    type(error).__name__,
                )
                outcome = 'held'
            counts[outcome] = counts.get(outcome, 0) + 1
            try:
                logger.info('event=batch_quarantine_recovery outcome=%s', outcome)
            except Exception:
                pass
        if len(candidates) < budget:
            # A short page reached the end of the scan. Resuming after its last
            # ID would skip every earlier candidate, including new quarantines,
            # for a whole pass.
            self._candidate_after = None
        return counts
