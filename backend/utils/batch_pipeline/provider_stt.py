"""C8 batch provider-STT stage: languages Parakeet cannot serve, without legacy sync.

A provider unit is admitted like any batch unit but never joins the GPU DRR
ring. It waits as ``provider_pending`` with ``merge_pending`` set, so
OrderedMerge holds the owner's later captures behind it exactly as it holds a
GPU unit. One at-most-once vendor call through ``utils.stt.pre_recorded``
produces an encrypted result; the unit then takes the same ``result_ready``
transition ``Scheduler.complete`` performs, and OrderedMerge, projection,
privacy and usage stay the single path.

Paid-once per vendor attempt (slice D, ``vendor_route_contracts``): the vendor is
called only by the delivery that wins the CAS ``provider_pending ->
provider_running``, which mints the attempt's token. Every later delivery of a
running unit reconciles that token's deterministic result object and never calls
the vendor again. A vendor-side failure may fail over to one other vendor (a
second attempt, never the same vendor twice once billed); when no permitted
vendor is healthy the unit parks in non-terminal ``vendor_held`` with its audio
and owner order intact and is redriven later. Only exhausted attempts, or our own
failures, settle terminal ``failed_held`` as before. Guarded validated-empty
exhaustion instead enters the bounded quarantine recovery while enabled.
"""

from utils.observability.stt_cap_dispatch import DispatchPath, DispatchReason, record_decision

from dataclasses import dataclass, fields
import asyncio
import io
import logging
import re
import time
from typing import Any, Awaitable, Callable, ClassVar, Literal
from uuid import uuid4
import wave

from config.batch_conversation_speakers import vendor_turns_enabled
from config.batch_language_recovery import enabled as independent_recovery_enabled, language_guarded
from config.batch_pipeline import provider_merge_membership_enabled
from config.batch_pipeline_vendor_failover import (
    failover_enabled,
    held_redrive_enabled,
    held_redrive_seconds,
    min_speech_seconds,
)
from database.batch_pipeline_privacy import BatchPrivacyBlocked, BatchPrivacyReason
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.outbox import Claim, OutboxKind, Outcome
from database.batch_pipeline_quarantine_recovery import RecoveryStore
from utils.batch_pipeline import vendor_route_contracts as contracts
from utils.batch_pipeline import vendor_route_metrics as vendor_metrics
from utils.batch_pipeline.contracts import (
    WorkItem,
    WorkResult,
    held_vad_census,
    projection_speech_spans,
    validate_measured_vad,
)
from utils.batch_pipeline.recovery_disposition import (
    REASONS,
    STAGES,
    RecoveryFailure,
    at_stage,
    inspect_audio,
    result_outcome,
    silence_payload,
    log_result_held,
)
from utils.batch_pipeline.scheduler import owner_key
from utils.batch_pipeline.input_retention import TERMINAL_SECONDS, staged_enqueue
from utils.batch_pipeline.provider_stt_admission import PENDING, SttRoute
from utils.batch_pipeline.vendor_route_contracts import (
    ATTEMPTS_FIELD,
    HOLD_FIELD,
    VENDOR_HELD,
    AttemptRefused,
    VendorAttempt,
    VendorHealth,
    VendorHold,
    check_new_attempt,
)
from utils.observability.reasons import (
    ConsumerReason,
    RetryReason,
    VendorAttemptOutcome,
    VendorHealthReason,
    VendorHoldOutcome,
    VendorHoldReason,
    VendorRouteTableOutcome,
)
from utils.workers.consumer import Result, Role

logger = logging.getLogger(__name__)

RUNNING = 'provider_running'
# Terminal: the content ledger no longer belongs to this unit's run, so its result can never project.
SUPERSEDED = 'provider_superseded'
STAGE_STATES = frozenset({PENDING, RUNNING, VENDOR_HELD})
# Invalid redirect topology is not evidence of deletion (utils/enrichment/custody.discard_blocked), and a
# lost result-write race is not privacy: keep the unit and its wake. Every other fence releases the unit
# terminally through the store's fence-bypass revoke (quarantine_fenced), because no purge is guaranteed to
# follow (a deleted merge survivor tombstones only the survivor, never the donor this job may name).
_TRANSIENT_FENCES = frozenset(
    {
        BatchPrivacyReason.CONVERSATION_REDIRECT_CYCLE,
        BatchPrivacyReason.CONVERSATION_REDIRECT_MISSING,
        BatchPrivacyReason.CONVERSATION_FENCE_BUDGET,
        BatchPrivacyReason.RESULT_LEASE_LOST,
    }
)
# A running intent older than this without a persisted result is settled as
# failed (abandoned), never re-dispatched under the same token (same bound as
# quarantine recovery). Longer than any one vendor call (Velma 300s, Soniox 120s).
ABANDON_SECONDS = 900.0
# Same wait as batch compute admission's cap deferral (admission.authorize).
FUNDING_RETRY_SECONDS = 60.0

# Services this stage can actually call: Velma batch and Soniox async (failover capacity only;
# the route table marks it failover_only). Deepgram is retired.
_CALLABLE_SERVICES = frozenset(contracts.VENDOR_SERVICES)


# --- attempt records -----------------------------------------------------------------------------


def attempts_of(job: dict) -> list[VendorAttempt]:
    """The unit's attempt records. A running unit from before slice D has only ``provider_intent``:
    that intent is attempt 1, so a pre-D running unit reconciles and settles exactly as before."""
    raw = job.get(ATTEMPTS_FIELD)
    if raw is not None:
        return [VendorAttempt.from_dict(entry) for entry in raw]
    intent = job.get('provider_intent')
    if not intent or job.get('state') != RUNNING or intent.get('settled_at') is not None:
        return []
    return [
        VendorAttempt(
            attempt=1,
            service=intent['service'],
            token=intent['token'],
            privacy_generation=intent.get('privacy_generation'),
            started_at=intent['started_at'],
            table_version='pre_d',
        )
    ]


def _exhausted_recovery_state(job: dict) -> str:
    """Only guarded validated-empty answers may spend the bounded recovery intent."""
    attempts = attempts_of(job)
    if (
        independent_recovery_enabled()
        and language_guarded(job)
        and attempts
        and attempts[-1].outcome == VendorAttemptOutcome.EMPTY_VALIDATED
    ):
        return 'held'
    return 'failed_held'


def bounding_attempts(attempts: list[VendorAttempt]) -> list[VendorAttempt]:
    """The records a new attempt is bounded by. Once the records are full, a trailing settled
    unbilled refusal (429, credits, client breaker) processed nothing, so the next attempt takes
    its record: a rate-limit or credit outage longer than a few redrives never exhausts
    ``MAX_ATTEMPT_RECORDS`` and ends the unit terminal. The refusal stays in the attempt metrics."""
    if (
        len(attempts) >= contracts.MAX_ATTEMPT_RECORDS
        and attempts[-1].settled_at is not None
        and attempts[-1].outcome in contracts.UNBILLED_OUTCOMES
    ):
        return attempts[:-1]
    return attempts


def _can_attempt(attempts: list[VendorAttempt], service: str) -> bool:
    try:
        check_new_attempt(bounding_attempts(attempts), service)
    except AttemptRefused:
        return False
    return True


def _settled(attempt: VendorAttempt, outcome: VendorAttemptOutcome, now: float, audio_seconds: float) -> VendorAttempt:
    return VendorAttempt(
        attempt=attempt.attempt,
        service=attempt.service,
        token=attempt.token,
        privacy_generation=attempt.privacy_generation,
        started_at=attempt.started_at,
        table_version=attempt.table_version,
        outcome=outcome,
        settled_at=now,
        audio_seconds=audio_seconds if outcome not in contracts.UNBILLED_OUTCOMES else 0.0,
    )


_HOLD_REASONS = {
    VendorHealthReason.FUNDS_REFUSAL: VendorHoldReason.FUNDS_REFUSAL,
    VendorHealthReason.DAILY_CAP_REACHED: VendorHoldReason.CAP_REACHED,
    VendorHealthReason.MONTHLY_BUDGET_REACHED: VendorHoldReason.CAP_REACHED,
    VendorHealthReason.RATE_LIMITED: VendorHoldReason.RATE_LIMITED,
    VendorHealthReason.STATE_UNAVAILABLE: VendorHoldReason.HEALTH_UNAVAILABLE,
}
# An unbilled refusal the vendor itself just answered, read as the health it implies.
_REFUSAL_HEALTH = {
    VendorAttemptOutcome.RATE_LIMITED: VendorHealthReason.RATE_LIMITED,
    VendorAttemptOutcome.CREDIT_REFUSAL: VendorHealthReason.FUNDS_REFUSAL,
    VendorAttemptOutcome.SILENCE: VendorHealthReason.HEALTHY,
}


class VendorCallFailure(RecoveryFailure):
    """A vendor call failed with a typed attempt outcome (never a body or a key)."""

    def __init__(self, stage: str, reason: str, outcome: VendorAttemptOutcome):
        super().__init__(stage, reason)
        self.outcome = outcome


def attempt_outcome_for(failure: RecoveryFailure) -> VendorAttemptOutcome:
    """Classify a stage failure. Untyped provider failures are vendor errors; payload and local
    failures are ours and never fail over."""
    if isinstance(failure, VendorCallFailure):
        return failure.outcome
    if failure.stage == 'provider' and failure.reason == 'provider_failed':
        return VendorAttemptOutcome.ERROR_5XX
    if failure.stage == 'response_validation':
        return (
            VendorAttemptOutcome.EMPTY_VALIDATED
            if failure.reason == 'empty_asr'
            else VendorAttemptOutcome.INVALID_RESPONSE
        )
    if failure.stage == 'provider' and failure.reason == 'abandoned_running':
        return VendorAttemptOutcome.ABANDONED
    return VendorAttemptOutcome.LOCAL_FAILURE


def _record_held_vad(job: dict, speech_seconds: float | None) -> None:
    """F2: a terminal failed_held unit carries its strict-VAD speech, as quarantine recovery's do, so
    the T2 observer measures it instead of falling back to the whole duration. Unmeasured stays unset."""
    # Reconciliation has no in-memory call plan. Reuse the intent's pre-call
    # measurement, keeping the greatest evidence across all settlement paths.
    for seconds in (speech_seconds, (job.get('provider_intent') or {}).get('measured_vad_speech_seconds')):
        measured = held_vad_census(job, seconds)
        if measured is not None:
            job['measured_held_vad_speech_seconds'] = measured


class ProviderSttStore:
    """Job-row intent fences. Privacy and content ownership use RecoveryStore's checks."""

    def __init__(self, store: Any):
        self.store = store
        self.fence = RecoveryStore(store)

    def read(self, segment_id: str) -> dict:
        return self.store.run(lambda tx: self.fence.checked(tx, segment_id)[0])

    def start(
        self,
        segment_id: str,
        token: str,
        now: float,
        service: str,
        *,
        table_version: str = 'builtin',
        measured_vad_speech_seconds: float | None = None,
        vendor_skipped: bool = False,
    ):
        """CAS pending -> running, minting attempt N. Returns the job if running (ours or a prior
        intent), else None. Raises ``AttemptRefused`` when the paid-once bounds forbid the mint."""
        if service not in _CALLABLE_SERVICES:
            raise ValueError('callable provider service required')

        def commit(tx):
            job, binding = self.fence.checked(tx, segment_id)
            if job.get('result') or tx.get('results', segment_id):
                return None
            if job.get('state') == RUNNING:
                return job
            if job.get('state') != PENDING:
                return None
            attempts = bounding_attempts(attempts_of(job))
            number = check_new_attempt(attempts, service)
            attempt = VendorAttempt(number, service, token, binding.privacy_generation, now, table_version)
            # A failover still owns the same immutable audio. Keep earlier
            # evidence if its next inspection is unavailable or lower.
            prior = (job.get('provider_intent') or {}).get('measured_vad_speech_seconds')
            measurements = [
                validate_measured_vad(value, job['duration_seconds'])
                for value in (prior, measured_vad_speech_seconds)
                if value is not None
            ]
            job['state'] = RUNNING
            job[ATTEMPTS_FIELD] = [entry.to_dict() for entry in attempts] + [attempt.to_dict()]
            # Mirror the current attempt; pre-D workers ignore the additive VAD evidence.
            job['provider_intent'] = {
                'token': token,
                'service': service,
                'privacy_generation': binding.privacy_generation,
                'started_at': now,
            }
            if measurements:
                job['provider_intent']['measured_vad_speech_seconds'] = max(measurements)
            if vendor_skipped:
                # Strict VAD found no speech spans: the stage answers silence locally and never
                # calls the vendor. Reconciliation settles an abandoned intent as that silence.
                job['provider_intent']['vendor_skipped'] = True
            tx.put('jobs', segment_id, job)
            return job

        return self.store.run(commit)

    def _settle_attempt(self, job: dict, token: str, outcome: VendorAttemptOutcome, now: float, audio: float):
        attempts = attempts_of(job)
        if not attempts or attempts[-1].token != token:
            return None
        attempts[-1] = _settled(attempts[-1], outcome, now, audio)
        job[ATTEMPTS_FIELD] = [entry.to_dict() for entry in attempts]
        return attempts

    def settle(
        self,
        segment_id: str,
        token: str,
        now: float,
        result_uri: str | None = None,
        *,
        outcome: str = 'success',
        failure: dict | None = None,
        attempt_outcome: VendorAttemptOutcome | None = None,
        audio_seconds: float = 0.0,
        failover_to: tuple[str, ...] = (),
        measured_held_vad_speech_seconds: float | None = None,
    ) -> Literal['settled', 'failover', False]:
        """Settle the running attempt ``token``: a result, a failover back to pending, or terminal.

        A failure fails over only when the attempt outcome is a vendor-side failover outcome and
        ``check_new_attempt`` still admits one of ``failover_to``; otherwise it is terminal
        failed-held. Guarded validated-empty attempts enter bounded quarantine recovery
        while its kill switch is on. Returns
        ``'failover'`` for the pending transition, ``'settled'`` otherwise, False when the
        attempt is no longer the unit's current one (a late result: nothing is written).
        """
        closed_failure = None
        if result_uri is None:
            if not failure or failure.get('stage') not in STAGES or failure.get('reason') not in REASONS:
                raise ValueError('closed provider failure required')
            closed_failure = {'stage': failure['stage'], 'reason': failure['reason']}
        if attempt_outcome is None:
            attempt_outcome = (
                VendorAttemptOutcome.SILENCE
                if outcome == 'silence'
                else VendorAttemptOutcome.OK if result_uri is not None else VendorAttemptOutcome.LOCAL_FAILURE
            )

        def commit(tx):
            job, _ = self.fence.checked(tx, segment_id)
            if (
                job.get('state') != RUNNING
                or job.get('provider_intent', {}).get('token') != token
                or job.get('result')
                or tx.get('results', segment_id)
            ):
                return False
            attempts = self._settle_attempt(job, token, attempt_outcome, now, audio_seconds)
            owner = tx.get('owners', owner_key(job['owner_id']))
            job['provider_intent']['settled_at'] = now
            if closed_failure is not None:
                job['provider_intent']['failure'] = closed_failure
                if (
                    attempts is not None
                    and attempt_outcome in contracts.FAILOVER_OUTCOMES
                    and any(_can_attempt(attempts, service) for service in failover_to)
                ):
                    # Back to pending with the audio and merge position intact; the next delivery
                    # picks a healthy unpaid vendor or parks the unit in vendor_held.
                    job['state'] = PENDING
                    tx.put('jobs', segment_id, job)
                    return 'failover'
                job.update(
                    state='quarantined',
                    merge_pending=False,
                    failure='worker_failed',
                    quarantine_reason='worker_failed',
                    quarantined_at=now,
                    recovery_state=_exhausted_recovery_state(job),
                )
                _record_held_vad(job, measured_held_vad_speech_seconds)
            else:
                job.update(state='result_ready', result=WorkResult(segment_id, result_uri or '', outcome).to_dict())
                if provider_merge_membership_enabled():
                    # As Scheduler.complete stamps it: the merge's head wait orders by ready_at, and
                    # a row without one can never commit past an unready head.
                    job['ready_at'] = now
            owner['revision'] = owner.get('revision', 0) + 1
            tx.put('owners', owner_key(job['owner_id']), owner)
            tx.put('jobs', segment_id, job)
            return 'settled'

        return self.store.run(commit)

    def terminal(
        self, segment_id: str, now: float, failure: dict, *, measured_held_vad_speech_seconds: float | None = None
    ) -> bool:
        """Quarantine an exhausted unit; guarded empty answers may enter bounded recovery."""

        def commit(tx):
            job, _ = self.fence.checked(tx, segment_id)
            if job.get('state') != PENDING or job.get('result') or tx.get('results', segment_id):
                return False
            key = owner_key(job['owner_id'])
            owner = tx.get('owners', key)
            job.update(
                state='quarantined',
                merge_pending=False,
                failure='worker_failed',
                quarantine_reason='worker_failed',
                quarantined_at=now,
                recovery_state=_exhausted_recovery_state(job),
            )
            job.setdefault('provider_intent', {})['failure'] = {'stage': failure['stage'], 'reason': failure['reason']}
            _record_held_vad(job, measured_held_vad_speech_seconds)
            owner['revision'] = owner.get('revision', 0) + 1
            tx.put('owners', key, owner)
            tx.put('jobs', segment_id, job)
            return True

        return self.store.run(commit)

    def hold(self, segment_id: str, hold: VendorHold) -> bool:
        """CAS pending -> vendor_held. ``merge_pending`` and the audio stay: owner order holds."""

        def commit(tx):
            job, _ = self.fence.checked(tx, segment_id)
            if job.get('state') != PENDING or job.get('result') or tx.get('results', segment_id):
                return False
            job['state'] = VENDOR_HELD
            job[HOLD_FIELD] = hold.to_dict()
            tx.put('jobs', segment_id, job)
            return True

        return self.store.run(commit)

    def redrive(self, segment_id: str) -> dict | None:
        """CAS vendor_held -> pending (attempts preserved, the hold kept as history). Returns the job."""

        def commit(tx):
            job, _ = self.fence.checked(tx, segment_id)
            if job.get('state') != VENDOR_HELD:
                return None
            hold = dict(job.get(HOLD_FIELD) or {})
            hold['redrives'] = int(hold.get('redrives', 0)) + 1
            job[HOLD_FIELD] = hold
            job['state'] = PENDING
            tx.put('jobs', segment_id, job)
            return job

        return self.store.run(commit)

    def supersede(self, segment_id: str, now: float) -> bool:
        """Terminal release of a unit whose content run was superseded (ProjectionBlocked).

        Clears ``merge_pending`` and bumps the owner revision in one transaction, as terminal
        quarantine does, so OrderedMerge stops holding the owner's later captures behind it.
        """

        def commit(tx):
            job = tx.get('jobs', segment_id)
            if job.get('state') not in STAGE_STATES or not job.get('merge_pending') or job.get('result'):
                return False
            key = owner_key(job['owner_id'])
            owner = tx.get('owners', key)
            job.update(state=SUPERSEDED, merge_pending=False, superseded_at=now)
            owner['revision'] = owner.get('revision', 0) + 1
            tx.put('owners', key, owner)
            tx.put('jobs', segment_id, job)
            return True

        return self.store.run(commit)


# --- vendor calls --------------------------------------------------------------------------------

# Typed client failures -> attempt outcomes. Unbilled outcomes (contracts.UNBILLED_OUTCOMES) leave
# the vendor unspent; a breaker refusal never sent a POST.
_MODULATE_OUTCOMES = {
    'breaker_open': VendorAttemptOutcome.RATE_LIMITED,
    'credit_refusal': VendorAttemptOutcome.CREDIT_REFUSAL,
    'rate_limited': VendorAttemptOutcome.RATE_LIMITED,
    'error_5xx': VendorAttemptOutcome.ERROR_5XX,
    'timeout': VendorAttemptOutcome.TIMEOUT,
    'invalid_response': VendorAttemptOutcome.INVALID_RESPONSE,
    'error': VendorAttemptOutcome.ERROR_5XX,
}
_SONIOX_OUTCOMES = {
    # Our own admission (surface policy, duration bound) refused before any request.
    'refused': VendorAttemptOutcome.LOCAL_FAILURE,
    'credit_refusal': VendorAttemptOutcome.CREDIT_REFUSAL,
    'rate_limited': VendorAttemptOutcome.RATE_LIMITED,
    'error_5xx': VendorAttemptOutcome.ERROR_5XX,
    'timeout': VendorAttemptOutcome.TIMEOUT,
    'invalid_response': VendorAttemptOutcome.INVALID_RESPONSE,
    'error': VendorAttemptOutcome.ERROR_5XX,
}


def _vendor_skipped(intent: dict) -> bool:
    """True when the stage answered this intent's unit as local silence without a vendor call.

    New intents carry ``vendor_skipped``. An intent minted by an older worker has only the
    strict-VAD measurement: spans are validated with ``start < end``, so 0 measured speech
    seconds means no spans, the same condition ``_call_sync`` uses to skip the vendor.
    """
    return bool(intent.get('vendor_skipped')) or intent.get('measured_vad_speech_seconds') == 0


def _speech_seconds(inspected: tuple | None) -> float | None:
    """Strict-VAD speech seconds from ``inspect_audio``'s (pcm, duration, spans), or None."""
    if not inspected:
        return None
    try:
        return float(sum(span['end'] - span['start'] for span in inspected[2]))
    except (KeyError, TypeError, ValueError, IndexError):
        return None


def _skips_vendor(inspected: tuple | None) -> bool:
    """True when this inspected unit is answered as local silence without a vendor call.

    Strict VAD found no speech spans, or found less speech than ``min_speech_seconds()``
    (``BATCH_VENDOR_MIN_SPEECH_SECONDS``, default 2 s; 0 restores the no-spans-only rule). A unit is
    billed for its whole ~31 s span, so a sub-2 s fragment costs as much as a full one for a word
    or two. The intent records ``vendor_skipped`` with the measured speech, so a short-speech skip
    stays distinguishable from true silence (speech > 0).
    """
    if not inspected:
        return False
    if not inspected[2]:
        return True
    threshold = min_speech_seconds()
    speech = _speech_seconds(inspected)
    return threshold > 0 and speech is not None and speech < threshold


def _wav(pcm: bytes) -> bytes:
    output = io.BytesIO()
    with wave.open(output, 'wb') as clean:
        clean.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        clean.writeframes(pcm)
    return output.getvalue()


async def _vendor_words(service: str, wav: bytes, duration: float, language: str | None) -> Any:
    """One awaited vendor call; failures become ``VendorCallFailure`` with a typed outcome."""
    if service == 'modulate':
        from utils.stt.modulate_batch import ModulateBatchError, modulate_batch_async

        try:
            return await modulate_batch_async(wav, language=language, mark_fallback=True)
        except ModulateBatchError as error:
            raise VendorCallFailure('provider', 'provider_failed', _MODULATE_OUTCOMES[error.kind]) from None
    if service == 'soniox':
        from utils.http_client import get_batch_vendor_client, get_batch_vendor_semaphore
        from utils.stt import soniox_batch

        try:
            return await soniox_batch.transcribe_async(
                wav,
                duration,
                language=language,
                failover=True,
                client=get_batch_vendor_client(),
                semaphore=get_batch_vendor_semaphore(),
                mark_fallback=True,
            )
        except soniox_batch.SonioxBatchError as error:
            outcome = _SONIOX_OUTCOMES[error.kind]
            if error.submitted and outcome in contracts.UNBILLED_OUTCOMES:
                # The paid transcription exists (a later poll was refused): billed, so Soniox is
                # never submitted twice for this unit.
                outcome = VendorAttemptOutcome.ERROR_5XX
            raise VendorCallFailure('provider', 'provider_failed', outcome) from None
    raise VendorCallFailure('provider', 'provider_failed', VendorAttemptOutcome.LOCAL_FAILURE)


_VOICE_LABEL = re.compile(r'SPEAKER_[0-9]{2,3}')


def vendor_turns(words: list[dict], duration: float, *, fallback: bool = False) -> list[dict]:
    """Pyannote-shaped turns from the vendor's labelled utterances.

    Only positive-duration records with a valid label carry voice; touching
    records of one label merge, so pauses never enter a voice clip. A response
    with any defaulted speaker is no diarization at all: its words-only labels
    could join two people into one voice. Past the centroid label budget, the
    labels with the least speech keep their text but carry no voice evidence.
    """
    from utils.batch_pipeline.voice_centroids import MAX_LABELS

    if fallback:
        return []
    turns: list[dict] = []
    for word in words:
        label = word.get('speaker')
        start, end = float(word['timestamp'][0]), min(float(word['timestamp'][1]), duration)
        if not isinstance(label, str) or not _VOICE_LABEL.fullmatch(label) or not 0 <= start < end:
            continue
        if turns and turns[-1]['speaker'] == label and start <= turns[-1]['end']:
            turns[-1]['end'] = max(turns[-1]['end'], end)
        else:
            turns.append({'start': start, 'end': end, 'speaker': label})
    seconds: dict[str, float] = {}
    for turn in turns:
        seconds[turn['speaker']] = seconds.get(turn['speaker'], 0.0) + turn['end'] - turn['start']
    if len(seconds) > MAX_LABELS:
        kept = set(sorted(seconds, key=lambda label: (-seconds[label], label))[:MAX_LABELS])
        turns = [turn for turn in turns if turn['speaker'] in kept]
    return turns


async def transcribe_async(item: WorkItem, language: str | None, inspected: tuple, *, service: str) -> dict:
    """One vendor call, awaited on the event loop: Velma batch has no submit/poll mode, so the
    open request holds a socket, never an executor thread. No client retry (one paid POST)."""
    from utils.batch_pipeline.word_validation import validate_words
    from utils.stt.allowance_session import Operation, current, track

    pcm, duration, spans = inspected
    if service not in _CALLABLE_SERVICES:
        raise VendorCallFailure('provider', 'provider_failed', VendorAttemptOutcome.LOCAL_FAILURE)
    scope = current.get()
    if scope is None or scope.uid != item.owner_id or scope.operation != f'batch-unit:{item.segment_id}':
        scope = Operation(item.owner_id, 'batch_provider', operation=f'batch-unit:{item.segment_id}', seconds=duration)
    try:
        async with track(scope):
            await scope.reserve_async(service)
            response = await _vendor_words(service, _wav(pcm), duration, language)
    except (RecoveryFailure, BatchPrivacyBlocked):
        raise
    except Exception:
        raise VendorCallFailure('provider', 'provider_failed', VendorAttemptOutcome.ERROR_5XX) from None

    def validate_response():
        if not isinstance(response, tuple) or len(response) != 2:
            raise ValueError('response shape')
        raw, detected = response
        if not isinstance(detected, str) or not detected:
            raise ValueError('response language')
        fallback = any(word.get('speaker_fallback') for word in raw)
        words = validate_words(
            [{**{k: v for k, v in word.items() if k != 'speaker_fallback'}, 'word': word['text']} for word in raw],
            duration,
        )
        if not words:
            raise RecoveryFailure('response_validation', 'empty_asr')
        return words, detected, fallback

    words, detected, fallback = at_stage('response_validation', 'invalid_response', validate_response)
    payload = {
        'audio_seconds': duration,
        'speech_seconds': sum(span['end'] - span['start'] for span in spans),
        'speech_spans': spans,
        'words': words,
        # The vendor's own unit-local turns (diarization was requested); the kill
        # switch restores words-only units at projection too.
        'diarization': {'turns': vendor_turns(words, duration, fallback=fallback) if vendor_turns_enabled() else []},
        'words_provider': service,
        'language': detected,
        'recovery_version': 1,
    }
    at_stage('payload_validation', 'invalid_payload', lambda: projection_speech_spans(payload, duration))
    return payload


def transcribe(item: WorkItem, language: str | None, inspected: tuple, *, service: str) -> dict:
    """Synchronous seam for callers without an event loop (pull consumers, offline tools)."""
    return asyncio.run(transcribe_async(item, language, inspected, service=service))


UnitOutcomeName = Literal['done', 'deferred', 'discarded', 'retry']


@dataclass(frozen=True)
class UnitOutcome:
    """Transport-free result; the queue consumer maps it onto contract (a)'s Result."""

    outcome: UnitOutcomeName
    reason: str  # ConsumerReason value, or a RetryReason value for 'retry'
    available_at: float | None = None
    provider_reason: str = 'none'  # ProviderSttReason value, for metrics only


@dataclass(frozen=True)
class _Call:
    """A minted attempt awaiting its one vendor call (between ``prepare`` and ``finish``)."""

    segment_id: str
    item: WorkItem
    route: SttRoute
    token: str
    service: str
    inspected: tuple | None
    failure: dict | None  # inspection failed: no vendor call, settle terminal
    failover_to: tuple[str, ...]
    allowance_period: str | None = None
    # Decided once in ``_prepare`` and recorded on the intent as ``vendor_skipped``.
    skip_vendor: bool = False


def _default_allowed(owner_id: str, seconds: float, service: str) -> tuple[bool, str]:
    from utils.stt_cap_dispatch import sync_admission

    return sync_admission(owner_id, seconds, service, lane='batch', path=DispatchPath.BATCH_PROVIDER)


# An exhausted allowance or usage budget lasts until the plan changes, so a refused unit
# parks for the same hold window GPU compute admission uses (admission.authorize).
# Re-checking every FUNDING_RETRY_SECONDS made each refused unit a new Cloud Task per minute;
# on 2026-11-12 those loops took most of the provider-stt queue's 10/s and starved
# entitled owners' units for a week. Transient denials keep the short retry.
_DURABLE_DENIALS = frozenset({DispatchReason.ALLOWANCE_EXHAUSTED.value, DispatchReason.BUDGET_EXHAUSTED.value})


# A held unit's staged audio is deleted by the bucket lifecycle at 30 days; the pipeline treats
# 29 days as the end (input_retention.TERMINAL_SECONDS). Inside the unit's last day before that,
# the hold re-checks at this interval whatever the configured window, and a longer window is cut
# so the next re-check lands no later than the start of that day. A renewal in the last day is
# then seen as soon as it was when the window was 2 h.
NEAR_EXPIRY_WINDOW_SECONDS = 86400.0
NEAR_EXPIRY_RECHECK_SECONDS = 7200.0


def _hold_before_expiry(wait: float, job: dict | None, now: float | None) -> float:
    if job is None or now is None or wait <= NEAR_EXPIRY_RECHECK_SECONDS:
        return wait
    staged = staged_enqueue(job)
    if staged is None:
        return wait
    until_last_day = staged + TERMINAL_SECONDS - NEAR_EXPIRY_WINDOW_SECONDS - now
    return min(wait, max(NEAR_EXPIRY_RECHECK_SECONDS, until_last_day))


def funding_retry_seconds(
    decision: bool | tuple[bool, str], *, job: dict | None = None, now: float | None = None
) -> float | None:
    """None when funded; otherwise how long the refused unit waits before re-checking."""
    permitted, reason = decision if isinstance(decision, tuple) else (bool(decision), None)
    if permitted:
        return None
    if reason in _DURABLE_DENIALS:
        from config.batch_pipeline import allowance_hold_retry_seconds

        return _hold_before_expiry(float(allowance_hold_retry_seconds()), job, now)
    return FUNDING_RETRY_SECONDS


def _default_health() -> VendorHealth:
    # Offline callers and tests: no vendor is refused before its call. Serving passes
    # route_selection.serving_health() (_service_stage): slice C with the served table's caps.
    return contracts.AlwaysHealthy()


def _default_armed() -> bool:
    """Whether a configured route table is served. Until then the stage keeps pre-D semantics.

    Failover back to ``provider_pending`` and ``vendor_held`` are transitions a pre-D worker
    mishandles (it would re-call the admitted vendor, or ack a held unit and strand it). They arm
    only once the lead serves a configured table, which happens after every provider-STT worker runs
    this build. Before rolling back past it: unset the table, then wait until no `vendor_held` unit and
    no `provider_pending` unit with a settled attempt (a failover awaiting its immediate redelivery)
    remains; a pre-D worker ignores `provider_attempts` and would re-call the admitted vendor.
    """
    # Deferred: route_selection imports this module.
    from utils.batch_pipeline.route_selection import current_table

    return current_table()[1] in (VendorRouteTableOutcome.CONFIGURED, VendorRouteTableOutcome.LAST_VALID)


def _default_failover_routes(language: str | None) -> tuple[str, ...]:
    """Vendor routes the served route table (slice B) lists for the language, in row order.

    The builtin table (today's routing; also the kill-switch target) lists Modulate only, so no
    unit fails over until a configured table names a second vendor.
    """
    from utils.batch_pipeline.route_selection import current_table

    table, _ = current_table()
    return tuple(
        option.route
        for option in contracts.capable_options(table, language)
        if option.route in contracts.VENDOR_SERVICES
    )


class ProviderSttStage:
    def __init__(
        self,
        store: Any,
        artifacts: Any,
        *,
        stt: Callable[..., dict] = transcribe,
        stt_async: Callable[..., Awaitable[dict]] | None = None,
        allowed: Callable[[str, float, str], bool | tuple[bool, str]] = _default_allowed,
        inspect: Callable[[WorkItem, bytes], tuple] = inspect_audio,
        clock: Callable[[], float] = time.time,
        health: VendorHealth | None = None,
        failover_routes: Callable[[str | None], tuple[str, ...]] = _default_failover_routes,
        armed: Callable[[], bool] = _default_armed,
    ):
        self.protocol = ProviderSttStore(store)
        self.artifacts, self.stt, self.allowed, self.inspect, self.clock = artifacts, stt, allowed, inspect, clock
        # An injected sync seam (tests, simulation) also serves the async driver.
        self.stt_async = stt_async if stt_async is not None else (transcribe_async if stt is transcribe else None)
        self.health = health if health is not None else _default_health()
        self.failover_routes = failover_routes
        self.armed = armed

    # -- drivers ----------------------------------------------------------------------------------

    def run(self, segment_id: str) -> UnitOutcome:
        """One delivery, synchronously (vendor call through the sync seam)."""
        plan = self._guarded(segment_id, self._prepare, segment_id)
        if isinstance(plan, UnitOutcome):
            return plan
        started = time.monotonic()
        response = self._call_sync(plan)
        return self._guarded(segment_id, self._finish, plan, response, time.monotonic() - started)

    async def run_async(self, segment_id: str, run_sync: Callable[..., Awaitable[Any]]) -> UnitOutcome:
        """One delivery: Firestore/GCS/VAD work through ``run_sync`` (an executor), the vendor call
        awaited on the event loop, so a long vendor answer never holds an executor thread."""
        plan = await run_sync(self._guarded, segment_id, self._prepare, segment_id)
        if isinstance(plan, UnitOutcome):
            return plan
        started = time.monotonic()
        response = await self._call_async(plan)
        return await run_sync(self._guarded, segment_id, self._finish, plan, response, time.monotonic() - started)

    def _guarded(self, segment_id: str, fn: Callable[..., Any], *args) -> Any:
        try:
            return fn(*args)
        except BatchPrivacyBlocked as error:
            if error.reason in _TRANSIENT_FENCES:
                # Keep the row: the GPU ring likewise re-checks a blocked head on every pull.
                return UnitOutcome('deferred', 'not_due', self.clock() + FUNDING_RETRY_SECONDS)
            # Ack the row only once the job no longer holds the owner's merge (the revoke rechecks the fence).
            try:
                self.protocol.store.quarantine_fenced(segment_id, self.clock())
            except Exception:
                return UnitOutcome('retry', 'dependency_warming')
            return UnitOutcome('discarded', 'privacy_blocked')
        except ProjectionBlocked:
            # Closing the row alone would leave merge_pending set and stall the owner's later units.
            try:
                self.protocol.supersede(segment_id, self.clock())
            except BatchPrivacyBlocked:
                return UnitOutcome('discarded', 'privacy_blocked')
            except Exception:
                return UnitOutcome('retry', 'dependency_warming')
            self._log('superseded', 'projection_blocked')
            return UnitOutcome('discarded', 'superseded')

    def _call_sync(self, plan: _Call) -> dict | RecoveryFailure:
        if plan.failure is not None or plan.inspected is None:
            failure = plan.failure or {'stage': 'provider', 'reason': 'operation_failed'}
            return RecoveryFailure(failure['stage'], failure['reason'])
        if plan.skip_vendor or not plan.inspected[2]:
            return silence_payload(plan.inspected[1])
        from utils.stt.allowance_session import Operation, current

        scope = Operation(
            plan.item.owner_id,
            'batch_provider',
            operation=f'batch-unit:{plan.segment_id}',
            seconds=plan.item.duration_seconds,
            billing_period=plan.allowance_period,
        )
        scope_token = current.set(scope)
        try:
            return self.stt(plan.item, plan.route.language, plan.inspected, service=plan.service)
        except BatchPrivacyBlocked:
            raise
        except RecoveryFailure as error:
            return error
        except Exception:
            return RecoveryFailure('provider', 'operation_failed')
        finally:
            scope.closed = True
            current.reset(scope_token)

    async def _call_async(self, plan: _Call) -> dict | RecoveryFailure:
        if (
            self.stt_async is None
            or plan.failure is not None
            or not plan.inspected
            or plan.skip_vendor
            or not plan.inspected[2]
        ):
            return self._call_sync(plan)
        from utils.stt.allowance_session import Operation, current

        scope = Operation(
            plan.item.owner_id,
            'batch_provider',
            operation=f'batch-unit:{plan.segment_id}',
            seconds=plan.item.duration_seconds,
            billing_period=plan.allowance_period,
        )
        scope_token = current.set(scope)
        try:
            return await self.stt_async(plan.item, plan.route.language, plan.inspected, service=plan.service)
        except BatchPrivacyBlocked:
            raise
        except RecoveryFailure as error:
            return error
        except Exception:
            return RecoveryFailure('provider', 'operation_failed')
        finally:
            scope.closed = True
            current.reset(scope_token)

    # -- phases -----------------------------------------------------------------------------------

    def _prepare(self, segment_id: str) -> UnitOutcome | _Call:
        job = self.protocol.read(segment_id)
        if job.get('state') not in STAGE_STATES:
            return UnitOutcome('done', 'superseded')
        item = WorkItem(**{field.name: job[field.name] for field in fields(WorkItem) if field.name in job})
        route = SttRoute(**job['stt_route'])
        if job['state'] == RUNNING:
            return self._reconcile(segment_id, job, item, route)
        redriven = job['state'] == VENDOR_HELD
        if redriven:
            waiting = self._held(segment_id, job)
            if waiting is not None:
                return waiting
            job = self.protocol.read(segment_id)
            if job.get('state') != PENDING:
                return UnitOutcome('done', 'superseded')
        # A BYOK unit was funded at admission; the keyless re-check would hold it forever.
        if route.provider_reason == 'byok':
            record_decision(DispatchPath.BATCH_PROVIDER, True, DispatchReason.BYOK)
        elif (
            wait := funding_retry_seconds(
                self.allowed(item.owner_id, item.duration_seconds, route.provider_service),
                job=job,
                now=self.clock(),
            )
        ) is not None:
            return UnitOutcome('deferred', 'not_due', self.clock() + wait)
        audio = self.artifacts.fetch_audio(item)
        inspected, failure = None, None
        try:
            inspected = self.inspect(item, audio)
        except RecoveryFailure as error:
            failure = {'stage': error.stage, 'reason': error.reason}
        # Download/inspection can queue behind other work. Recheck before the
        # one durable provider intent; denial must leave it unspent.
        if (
            route.provider_reason != 'byok'
            and (
                wait := funding_retry_seconds(
                    self.allowed(item.owner_id, item.duration_seconds, route.provider_service),
                    job=job,
                    now=self.clock(),
                )
            )
            is not None
        ):
            return UnitOutcome('deferred', 'not_due', self.clock() + wait)
        attempts = attempts_of(job)
        candidates = self._candidates(route)
        open_services = [service for service in candidates if _can_attempt(attempts, service)]
        if not open_services:
            # Only after a failover back to pending: every permitted vendor is spent or forbidden.
            reason = (job.get('provider_intent') or {}).get('failure') or {
                'stage': 'provider',
                'reason': 'provider_failed',
            }
            speech = _speech_seconds(inspected) if failure is None else None
            if self.protocol.terminal(segment_id, self.clock(), reason, measured_held_vad_speech_seconds=speech):
                self._log('failed_held', reason['reason'])
            return UnitOutcome('done', 'processed', provider_reason='provider_failed')
        skip_vendor = failure is None and _skips_vendor(inspected)
        if failure is not None or inspected is None or skip_vendor or not self._armed():
            # No vendor call (invalid audio, or strict-VAD silence), or routing not armed: the
            # admitted vendor, no health gate, no hold (pre-D semantics).
            service = open_services[0]
        else:
            # A vendor that just refused unbilled (429, credits, client breaker) is not re-called on
            # the immediate failover delivery: another vendor, or vendor_held until the redrive.
            last = attempts[-1] if attempts else None
            refused = last if last and last.outcome in contracts.UNBILLED_OUTCOMES and not redriven else None
            service = self._healthy(segment_id, job, open_services, refused)
            if isinstance(service, UnitOutcome):
                return service
        token = uuid4().hex
        try:
            started = self.protocol.start(
                segment_id,
                token,
                self.clock(),
                service,
                measured_vad_speech_seconds=_speech_seconds(inspected) if failure is None else None,
                # Same condition _call_sync uses to answer silence without a vendor call.
                vendor_skipped=skip_vendor,
            )
        except AttemptRefused:
            # Read-to-mint race on the attempt list; never mint past the bounds. Re-evaluate later.
            vendor_metrics.paid_intent_violation(service)
            return UnitOutcome('deferred', 'not_due', self.clock() + FUNDING_RETRY_SECONDS)
        if started is None:
            return UnitOutcome('done', 'superseded')
        if started['provider_intent']['token'] != token:
            return self._reconcile(segment_id, started, item, route)
        if service != route.provider_service:
            vendor_metrics.failover(route.provider_service, service)

        def read_intake(tx):
            binding = started.get('projection_binding') or {}
            return tx.get('intakes', binding.get('job_id', 'missing')) or {}

        intake = self.protocol.store.run(read_intake)
        return _Call(
            segment_id,
            item,
            route,
            token,
            service,
            inspected,
            failure,
            tuple(candidates),
            allowance_period=intake.get('usage_period'),
            skip_vendor=skip_vendor,
        )

    def _finish(self, plan: _Call, response: dict | RecoveryFailure, latency: float | None = None) -> UnitOutcome:
        segment_id, item, route, token = plan.segment_id, plan.item, plan.route, plan.token
        duration = item.duration_seconds
        if isinstance(response, dict):
            try:
                result_outcome(response)
            except RecoveryFailure as error:
                response = error
        if not isinstance(response, dict):
            failure = {'stage': response.stage, 'reason': response.reason}
            # A failed inspection never reached a vendor: ours, terminal, unbilled audio.
            outcome = attempt_outcome_for(response) if plan.failure is None else VendorAttemptOutcome.LOCAL_FAILURE
            audio = 0.0 if plan.failure is not None else duration
            failover_to = plan.failover_to if failover_enabled() and self._armed() else ()
            settled = self.protocol.settle(
                segment_id,
                token,
                self.clock(),
                failure=failure,
                attempt_outcome=outcome,
                audio_seconds=audio,
                failover_to=failover_to,
                measured_held_vad_speech_seconds=_speech_seconds(plan.inspected) if plan.failure is None else None,
            )
            if not settled:
                vendor_metrics.late_result(plan.service, 'ignored')
                return UnitOutcome('done', 'superseded')
            vendor_metrics.attempt(plan.service, outcome, 0.0 if outcome in contracts.UNBILLED_OUTCOMES else audio)
            vendor_metrics.overflow_attempt(
                route, plan.service, 0.0 if outcome in contracts.UNBILLED_OUTCOMES else audio
            )
            if plan.failure is None:
                self._record_attempt(plan.service, outcome, latency)
            if settled == 'failover':
                self._log('failover', failure['reason'])
                # Immediate redelivery picks the next healthy unpaid vendor, or parks in vendor_held.
                return UnitOutcome('deferred', 'not_due', self.clock())
            self._log('failed_held', failure['reason'])
            return UnitOutcome('done', 'processed', provider_reason='provider_failed')
        # A storage/commit failure leaves the intent running; the deterministic
        # encrypted object is reconciled by a later delivery without a vendor call.
        silence = response.get('outcome') == 'silence'
        outcome = VendorAttemptOutcome.SILENCE if silence else VendorAttemptOutcome.OK
        stage = 'persist'
        try:
            uri = self.artifacts.persist_recovery_result(item, response, token)
            stage = 'settle'
            settled = self.protocol.settle(
                segment_id,
                token,
                self.clock(),
                uri,
                outcome=result_outcome(response),
                attempt_outcome=outcome,
                audio_seconds=0.0 if silence else duration,
            )
        except BatchPrivacyBlocked:
            raise
        except Exception as error:
            log_result_held('provider', stage, exception_type=type(error).__name__)
            return UnitOutcome('retry', 'dependency_warming', provider_reason=route.provider_reason)
        if settled:
            vendor_metrics.attempt(plan.service, outcome, 0.0 if silence else duration)
            vendor_metrics.overflow_attempt(route, plan.service, 0.0 if silence else duration)
            if silence and plan.skip_vendor and plan.inspected and plan.inspected[2]:
                vendor_metrics.short_speech_skip(plan.service, duration)
            if not silence:
                self._record_attempt(plan.service, outcome, latency)
        else:
            log_result_held('provider', 'settle', reason='refused')
            # The attempt was settled elsewhere (abandoned, then failed over): never overwrite.
            vendor_metrics.late_result(plan.service, 'ignored')
        self._log('settled' if settled else 'superseded', 'none')
        return UnitOutcome('done', 'processed' if settled else 'superseded', provider_reason=route.provider_reason)

    # -- helpers ----------------------------------------------------------------------------------

    def _candidates(self, route: SttRoute) -> list[str]:
        """The admitted vendor first, then the table's other vendors when failover is on."""
        primary = route.provider_service
        candidates = [primary] if primary in _CALLABLE_SERVICES else []
        if failover_enabled() and self._armed():
            try:
                listed = self.failover_routes(route.language)
            except Exception:
                listed = ()
            candidates += [service for service in listed if service in _CALLABLE_SERVICES and service not in candidates]
        return candidates

    def _healthy(
        self, segment_id: str, job: dict, services: list[str], just_refused: VendorAttempt | None = None
    ) -> str | UnitOutcome:
        """The first healthy service, or park the unit in vendor_held waiting for the refused ones."""
        refused: list[tuple[str, VendorHealthReason]] = []
        for service in services:
            if just_refused is not None and service == just_refused.service:
                allowed, reason = False, _REFUSAL_HEALTH[just_refused.outcome]
            else:
                try:
                    allowed, reason = self.health.allows(service)
                    reserve = getattr(self.health, 'reserve', None)
                    if allowed and reserve is not None:
                        # Slice C: count the unit against the vendor's daily cap and month budget
                        # before the mint (never inside a retried transaction body). A cap is
                        # unhealthy, not an error: try the next vendor, else hold.
                        allowed, reason = reserve(service, float(job.get('duration_seconds') or 0.0))
                except Exception:
                    allowed, reason = False, VendorHealthReason.STATE_UNAVAILABLE
            if allowed:
                return service
            refused.append((service, reason))
        now = self.clock()
        previous = job.get(HOLD_FIELD) or {}
        hold = VendorHold(
            reason=_HOLD_REASONS.get(refused[0][1], VendorHoldReason.NO_HEALTHY_VENDOR),
            held_at=float(previous.get('held_at', now)) if previous else now,
            redrive_at=now + held_redrive_seconds(),
            redrives=int(previous.get('redrives', 0)) if previous else 0,
            waiting_for=tuple(service for service, _ in refused),
        )
        if not self.protocol.hold(segment_id, hold):
            return UnitOutcome('done', 'superseded')
        vendor_metrics.hold_transition(VendorHoldOutcome.HELD)
        self._log('vendor_held', hold.reason.value)
        return UnitOutcome('deferred', 'not_due', hold.redrive_at)

    def _held(self, segment_id: str, job: dict) -> UnitOutcome | None:
        """A held unit's delivery: redrive when due (or early when a waited-for vendor is back);
        otherwise defer to ``redrive_at``. Returns None once the unit is pending again."""
        now = self.clock()
        try:
            hold = VendorHold.from_dict(job[HOLD_FIELD])
        except (KeyError, TypeError, ValueError):
            hold = None  # malformed hold: redrive now rather than park it unmeasured
        if hold is not None:
            if not held_redrive_enabled():
                # Parked: no redrive and no new redrive_at, so the hold goes stale after the grace
                # and guards measure it as a wedge instead of excluding it.
                return UnitOutcome('deferred', 'not_due', max(hold.redrive_at, now) + held_redrive_seconds())
            early = any(self._allows_quietly(service) for service in hold.waiting_for)
            if now < hold.redrive_at and not early:
                return UnitOutcome('deferred', 'not_due', hold.redrive_at)
        if self.protocol.redrive(segment_id) is None:
            return UnitOutcome('done', 'superseded')
        vendor_metrics.hold_transition(VendorHoldOutcome.REDRIVEN)
        self._log('redriven', hold.reason.value if hold else 'malformed_hold')
        return None

    def _armed(self) -> bool:
        try:
            return bool(self.armed())
        except Exception:
            return False

    def _allows_quietly(self, service: str) -> bool:
        # Never the half-open probe (slice C ``peek``): it belongs to the mint in ``_healthy``; one
        # spent here makes no call, so an open breaker would never close and holds never drain.
        try:
            return bool(getattr(self.health, 'peek', self.health.allows)(service)[0])
        except Exception:
            return False

    def _record_attempt(self, service: str, outcome: VendorAttemptOutcome, latency: float | None) -> None:
        """Feed a settled vendor attempt to slice C's breaker windows, when the health has them."""
        record = getattr(self.health, 'record_attempt', None) if self._armed() else None
        if record is None:
            return
        try:
            record(service, outcome, latency_seconds=latency)
        except Exception:
            pass

    def _reconcile(self, segment_id: str, job: dict, item: WorkItem, route: SttRoute) -> UnitOutcome:
        intent = job['provider_intent']
        uri = self.artifacts.find_recovery_result(item, intent['token'])
        if uri:
            outcome = result_outcome(self.artifacts.load_result(item, uri))
            silence = outcome == 'silence'
            settled = self.protocol.settle(
                segment_id,
                intent['token'],
                self.clock(),
                uri,
                outcome=outcome,
                attempt_outcome=VendorAttemptOutcome.SILENCE if silence else VendorAttemptOutcome.OK,
                audio_seconds=0.0 if silence else item.duration_seconds,
            )
            if settled:
                vendor_metrics.late_result(intent['service'], 'reconciled')
                # A billed result saved before a failed settle is still overflow spend.
                vendor_metrics.overflow_attempt(route, intent['service'], 0.0 if silence else item.duration_seconds)
                if intent.get('vendor_skipped') and (intent.get('measured_vad_speech_seconds') or 0) > 0:
                    # A short-speech skip whose silence result was saved before its settle failed:
                    # count the unbilled audio once, as the direct and abandoned-intent paths do.
                    vendor_metrics.short_speech_skip(intent['service'], item.duration_seconds)
            return UnitOutcome('done', 'processed' if settled else 'superseded')
        if self.clock() - intent['started_at'] > ABANDON_SECONDS and _vendor_skipped(intent):
            return self._settle_skipped_silence(segment_id, intent, item, route)
        if self.clock() - intent['started_at'] > ABANDON_SECONDS:
            failure = {'stage': 'provider', 'reason': 'abandoned_running'}
            # No strict-VAD speech means _call_sync answered silence locally: no vendor call, so
            # nothing was sent or billed (attempt audio, vendor audio metrics and overflow spend).
            sent = 0.0 if intent.get('measured_vad_speech_seconds') == 0 else item.duration_seconds
            settled = self.protocol.settle(
                segment_id,
                intent['token'],
                self.clock(),
                failure=failure,
                attempt_outcome=VendorAttemptOutcome.ABANDONED,
                audio_seconds=sent,
                failover_to=tuple(self._candidates(route)) if failover_enabled() and self._armed() else (),
            )
            if not settled:
                return UnitOutcome('done', 'superseded')
            vendor_metrics.attempt(intent['service'], VendorAttemptOutcome.ABANDONED, sent)
            vendor_metrics.overflow_attempt(route, intent['service'], sent)
            self._record_attempt(intent['service'], VendorAttemptOutcome.ABANDONED, None)
            if settled == 'failover':
                self._log('failover', 'abandoned_running')
                return UnitOutcome('deferred', 'not_due', self.clock())
            self._log('failed_held', 'abandoned_running')
            return UnitOutcome('done', 'processed', provider_reason='provider_failed')
        return UnitOutcome('deferred', 'lease_held', intent['started_at'] + ABANDON_SECONDS)

    def _settle_skipped_silence(self, segment_id: str, intent: dict, item: WorkItem, route: SttRoute) -> UnitOutcome:
        """An abandoned intent whose strict VAD found no speech never reached the vendor.

        Its result is the same local silence the first delivery computed before its save failed:
        persist and settle that silence under the intent's token. It is not an ABANDONED vendor
        attempt, so it records no health failure (a burst cannot open a healthy vendor's breaker)
        and bills no audio.
        """
        stage = 'persist'
        try:
            payload = silence_payload(item.duration_seconds)
            uri = self.artifacts.persist_recovery_result(item, payload, intent['token'])
            stage = 'settle'
            settled = self.protocol.settle(
                segment_id,
                intent['token'],
                self.clock(),
                uri,
                outcome=result_outcome(payload),
                attempt_outcome=VendorAttemptOutcome.SILENCE,
                audio_seconds=0.0,
            )
        except BatchPrivacyBlocked:
            raise
        except Exception as error:
            log_result_held('provider', stage, exception_type=type(error).__name__)
            return UnitOutcome('retry', 'dependency_warming', provider_reason=route.provider_reason)
        if settled:
            vendor_metrics.attempt(intent['service'], VendorAttemptOutcome.SILENCE, 0.0)
            if (intent.get('measured_vad_speech_seconds') or 0) > 0:
                # A short-speech skip (spans under the threshold), not true silence.
                vendor_metrics.short_speech_skip(intent['service'], item.duration_seconds)
        self._log('settled' if settled else 'superseded', 'skipped_silence')
        return UnitOutcome('done', 'processed' if settled else 'superseded', provider_reason=route.provider_reason)

    @staticmethod
    def _log(outcome: str, reason: str) -> None:
        try:
            logger.info('event=batch_provider_stt outcome=%s reason=%s', outcome, reason)
        except Exception:
            pass


# --- queue consumer (contract (a): kind provider_stt, role workers) -----------------------------

RETRY_SECONDS = 30.0


def _service_stage() -> ProviderSttStage:
    # Deferred: the batch store namespace and artifact bucket are resolved per host stage.
    from database.batch_pipeline_shadow_hook import shadow_from_env
    from database.batch_pipeline_store import FirestoreStore
    from utils.batch_pipeline.artifact_policy import artifacts_for
    from utils.batch_pipeline.route_selection import serving_health
    from utils.sync.stage import current_stage

    store = shadow_from_env(FirestoreStore(f'batch_pipeline_{current_stage()}'))  # A2 seam: provider-STT writes
    # The vendor health admission selection also uses: slice C reading the served table's caps.
    return ProviderSttStage(store, artifacts_for(store), health=serving_health())


class ProviderSttConsumer:
    """Push consumer: one outbox row per provider unit, keyed by its segment id."""

    kind: ClassVar[OutboxKind] = OutboxKind.PROVIDER_STT
    role: ClassVar[Role] = Role.WORKERS
    # No heartbeat: one vendor call per delivery. Longer than the 1500s dispatch deadline.
    lease_seconds: ClassVar[float] = 1800.0
    heartbeat_seconds: ClassVar[float] = 0.0

    def __init__(
        self,
        stage_factory: Callable[[], ProviderSttStage] = _service_stage,
        clock=time.time,
        *,
        settled: Callable[[str], None] | None = None,
    ):
        self.stage_factory, self.clock = stage_factory, clock
        # Called with the owner id after a delivery that changed the owner's merge order (a result,
        # or a terminal unit leaving it), so the host can wake that owner's ordered merge. Only the
        # serving route passes one; a hint, never a dependency of the delivery.
        self.settled = settled

    def _wake_merge(self, owner_id: str, unit: UnitOutcome) -> None:
        if self.settled is None or (unit.outcome, unit.reason) != ('done', 'processed'):
            return
        try:
            self.settled(owner_id)
        except Exception as error:
            logger.warning(
                'event=batch_provider_stt action=merge_wake outcome=failed exception_type=%s', type(error).__name__
            )

    def _segment(self, claim: Claim) -> str | None:
        segment_id = claim.payload.get('segment_id')
        if not isinstance(segment_id, str) or not segment_id or segment_id != claim.row_id:
            return None
        return segment_id

    def _result(self, unit: UnitOutcome) -> Result:
        if unit.outcome == 'retry':
            return Result(Outcome.RETRY, RetryReason(unit.reason), self.clock() + RETRY_SECONDS)
        outcome = {'done': Outcome.DONE, 'deferred': Outcome.DEFERRED, 'discarded': Outcome.DISCARDED}[unit.outcome]
        return Result(outcome, ConsumerReason(unit.reason), unit.available_at)

    def process(self, claim: Claim, heartbeat: Callable[[], bool]) -> Result:
        segment_id = self._segment(claim)
        if segment_id is None:
            # A malformed row can never succeed; close it rather than re-wake it forever.
            return Result(Outcome.DISCARDED, ConsumerReason.UNKNOWN)
        return self._result(self.stage_factory().run(segment_id))

    async def process_async(
        self, claim: Claim, heartbeat: Callable[[], bool], run_sync: Callable[..., Awaitable[Any]]
    ) -> Result:
        segment_id = self._segment(claim)
        if segment_id is None:
            return Result(Outcome.DISCARDED, ConsumerReason.UNKNOWN)
        stage = await run_sync(self.stage_factory)
        unit = await stage.run_async(segment_id, run_sync)
        self._wake_merge(claim.owner_id, unit)
        return self._result(unit)
