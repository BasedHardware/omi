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
failures, settle terminal ``failed_held`` as before.
"""

from utils.observability.stt_cap_dispatch import DispatchPath, DispatchReason, record_decision

from dataclasses import asdict, dataclass, fields
import asyncio
import io
import logging
import time
from typing import Any, Awaitable, Callable, ClassVar, Literal
from uuid import uuid4
import wave

from config.batch_pipeline_vendor_failover import failover_enabled, held_redrive_enabled, held_redrive_seconds
from config.policy import BatchUnitPolicy
from config.stt_provider_policy import PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL, normalized_stt_language
from database.batch_pipeline_privacy import BatchPrivacyBlocked, BatchPrivacyReason
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.outbox import Claim, OutboxKind, Outcome
from database.batch_pipeline_quarantine_recovery import RecoveryStore
from utils.batch_pipeline import vendor_route_contracts as contracts
from utils.batch_pipeline import vendor_route_metrics as vendor_metrics
from utils.batch_pipeline.contracts import WorkItem, WorkResult, held_vad_census, projection_speech_spans
from utils.batch_pipeline.recovery_disposition import (
    REASONS,
    STAGES,
    RecoveryFailure,
    at_stage,
    inspect_audio,
    result_outcome,
    silence_payload,
)
from utils.batch_pipeline.scheduler import owner_key
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

PARAKEET_MODEL = 'nvidia/parakeet-tdt-0.6b-v3'
PENDING = 'provider_pending'
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

SttRouteName = Literal['parakeet', 'provider']
ProviderReason = Literal['none', 'byok', 'unsupported_language']
ProviderService = Literal['none', 'byok', 'soniox', 'deepgram', 'modulate']
_ROUTES = frozenset({'parakeet', 'provider'})
_PROVIDER_REASONS = frozenset({'none', 'byok', 'unsupported_language'})
_SERVICES = frozenset({'none', 'byok', 'soniox', 'deepgram', 'modulate'})
# Services this stage can actually call: Velma batch and Soniox async (failover capacity only;
# the route table marks it failover_only). Deepgram is retired.
_CALLABLE_SERVICES = frozenset(contracts.VENDOR_SERVICES)


@dataclass(frozen=True)
class SttRoute:
    """Admission-time STT route; the contract (c) policy fields of the same names."""

    stt_route: SttRouteName
    provider_reason: ProviderReason
    provider_service: ProviderService
    language: str

    def __post_init__(self):
        if self.stt_route not in _ROUTES:
            raise ValueError('closed stt_route required')
        if self.provider_reason not in _PROVIDER_REASONS:
            raise ValueError('closed provider_reason required')
        if self.provider_service not in _SERVICES:
            raise ValueError('closed provider_service required')
        if (self.stt_route == 'provider') != (self.provider_service != 'none'):
            raise ValueError('a provider route names exactly one provider service')
        if not self.language or len(self.language) > 16:
            raise ValueError('bounded language required')


def resolve_route(language: str | None, *, byok: bool = False) -> SttRoute:
    """Decide once at admission. Unknown language is ``multi``: Parakeet, as legacy sync.

    BYOK uploads are routed like every other upload (David, 10-19): sync
    pre-recorded STT has never used a BYOK key, and enrichment runs on Omi's keys.
    ``provider_reason='byok'`` only records the admission-time funding decision,
    made while the validated keys were present, so later keyless stages never
    re-hold the unit (contract (c): admission decides once).
    """
    normalized = normalized_stt_language(language) or 'multi'
    if normalized in PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL[PARAKEET_MODEL]:
        return SttRoute('parakeet', 'byok' if byok else 'none', 'none', normalized)
    return SttRoute('provider', 'byok' if byok else 'unsupported_language', 'modulate', normalized[:16])


def enqueue_in_transaction(tx, item: WorkItem, now: float, *, route: SttRoute, policy: BatchUnitPolicy) -> bool:
    """Write a provider unit outside the GPU ring; the admission ``enqueue`` hook.

    Mirrors ``Scheduler.enqueue_in_transaction``'s immutable-work check, owner
    revision fence and late-capture watermark, but never touches queues or
    control shards, so no GPU pull can lease it.
    """
    if route.stt_route != 'provider':
        raise ValueError('only provider routes bypass the GPU ring')
    if item.requires_compute_admission:
        raise ValueError('provider units are funded by the provider stage, not GPU compute admission')
    previous = tx.get('jobs', item.segment_id)
    immutable = {**asdict(item), 'priority': int(item.priority)}
    if previous:
        if previous.get('state') == 'record_pending':
            raise ValueError('a pending recording cannot take the provider route')
        if any(
            previous.get(key) != value
            for key, value in immutable.items()
            if not (key == 'privacy_generation' and value is None)
        ) or previous.get('stt_route') != asdict(route):
            raise ValueError('segment ID reused with different immutable work')
        return False
    key = owner_key(item.owner_id)
    owner = tx.get('owners', key)
    watermark = owner.get('watermark')
    job = {
        **immutable,
        'policy': policy.to_dict(),
        'policy_source': 'admission',
        'protocol_version': 1,
        'owner_key': key,
        'enqueued_at': now,
        'state': PENDING,
        'attempt': 0,
        'token': '',
        'lease_until': 0.0,
        'available_at': now,
        'merge_pending': True,
        'next': '',
        'stt_route': asdict(route),
        'late_capture': bool(
            watermark and (item.capture_at, item.segment_id) <= (watermark['capture_at'], watermark['segment_id'])
        ),
    }
    tx.put('jobs', item.segment_id, job)
    owner['revision'] = owner.get('revision', 0) + 1
    tx.put('owners', key, owner)
    return True


def provider_enqueue(route: SttRoute, outbox: Any, wakes: dict[str, str]) -> Callable[..., bool]:
    """The admit() ``enqueue`` hook: the job row and its outbox row commit together.

    ``wakes`` collects ``row_id -> wake_token``; the caller calls ``outbox.wake``
    for each after the admission transaction commits (contract (b), invariant 4).
    A retried transaction body overwrites the same keys.
    """

    def enqueue(tx: Any, item: WorkItem, now: float, *, policy: BatchUnitPolicy) -> bool:
        created = enqueue_in_transaction(tx, item, now, route=route, policy=policy)
        if created:
            result = outbox.enqueue(
                item.segment_id, item.owner_id, {'segment_id': item.segment_id}, now, tx=tx, now=now
            )
            if result.wake_token:
                wakes[result.row_id] = result.wake_token
        return created

    return enqueue


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


def _can_attempt(attempts: list[VendorAttempt], service: str) -> bool:
    try:
        check_new_attempt(attempts, service)
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
    measured = held_vad_census(job, speech_seconds)
    if measured is not None:
        job['measured_held_vad_speech_seconds'] = measured


class ProviderSttStore:
    """Job-row intent fences. Privacy and content ownership use RecoveryStore's checks."""

    def __init__(self, store: Any):
        self.store = store
        self.fence = RecoveryStore(store)

    def read(self, segment_id: str) -> dict:
        return self.store.run(lambda tx: self.fence.checked(tx, segment_id)[0])

    def start(self, segment_id: str, token: str, now: float, service: str, *, table_version: str = 'builtin'):
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
            attempts = attempts_of(job)
            number = check_new_attempt(attempts, service)
            attempt = VendorAttempt(number, service, token, binding.privacy_generation, now, table_version)
            job['state'] = RUNNING
            job[ATTEMPTS_FIELD] = [entry.to_dict() for entry in attempts] + [attempt.to_dict()]
            # Unchanged shape, mirroring the current attempt: a pre-D worker still reconciles it.
            job['provider_intent'] = {
                'token': token,
                'service': service,
                'privacy_generation': binding.privacy_generation,
                'started_at': now,
            }
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
        failed-held, never 'held', so quarantine recovery cannot spend another call. Returns
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
                    recovery_state='failed_held',
                )
                _record_held_vad(job, measured_held_vad_speech_seconds)
            else:
                job.update(state='result_ready', result=asdict(WorkResult(segment_id, result_uri or '', outcome)))
            owner['revision'] = owner.get('revision', 0) + 1
            tx.put('owners', owner_key(job['owner_id']), owner)
            tx.put('jobs', segment_id, job)
            return 'settled'

        return self.store.run(commit)

    def terminal(
        self, segment_id: str, now: float, failure: dict, *, measured_held_vad_speech_seconds: float | None = None
    ) -> bool:
        """Terminal failed-held for a pending unit no vendor may serve any more (attempts spent)."""

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
                recovery_state='failed_held',
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


def _speech_seconds(inspected: tuple | None) -> float | None:
    """Strict-VAD speech seconds from ``inspect_audio``'s (pcm, duration, spans), or None."""
    if not inspected:
        return None
    try:
        return float(sum(span['end'] - span['start'] for span in inspected[2]))
    except (KeyError, TypeError, ValueError, IndexError):
        return None


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
            return await modulate_batch_async(wav, language=language)
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
            )
        except soniox_batch.SonioxBatchError as error:
            outcome = _SONIOX_OUTCOMES[error.kind]
            if error.submitted and outcome in contracts.UNBILLED_OUTCOMES:
                # The paid transcription exists (a later poll was refused): billed, so Soniox is
                # never submitted twice for this unit.
                outcome = VendorAttemptOutcome.ERROR_5XX
            raise VendorCallFailure('provider', 'provider_failed', outcome) from None
    raise VendorCallFailure('provider', 'provider_failed', VendorAttemptOutcome.LOCAL_FAILURE)


async def transcribe_async(item: WorkItem, language: str | None, inspected: tuple, *, service: str) -> dict:
    """One vendor call, awaited on the event loop: Velma batch has no submit/poll mode, so the
    open request holds a socket, never an executor thread. No client retry (one paid POST)."""
    from diarizer.batch_pipeline import validate_words

    pcm, duration, spans = inspected
    if service not in _CALLABLE_SERVICES:
        raise VendorCallFailure('provider', 'provider_failed', VendorAttemptOutcome.LOCAL_FAILURE)
    try:
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
        words = validate_words([{**word, 'word': word['text']} for word in raw], duration)
        if not words:
            raise RecoveryFailure('response_validation', 'empty_asr')
        return words, detected

    words, detected = at_stage('response_validation', 'invalid_response', validate_response)
    payload = {
        'audio_seconds': duration,
        'speech_seconds': sum(span['end'] - span['start'] for span in spans),
        'speech_spans': spans,
        'words': words,
        # Vendor speaker turns stay discarded (words-only, as recovered units; RouteConfig.speaker_turns).
        'diarization': {'turns': []},
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


def _default_allowed(owner_id: str, seconds: float, service: str) -> bool:
    from utils.stt_cap_dispatch import sync_allowed

    return sync_allowed(owner_id, seconds, service, lane='batch', path=DispatchPath.BATCH_PROVIDER)


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
        allowed: Callable[[str, float, str], bool] = _default_allowed,
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
        if not plan.inspected[2]:
            return silence_payload(plan.inspected[1])
        try:
            return self.stt(plan.item, plan.route.language, plan.inspected, service=plan.service)
        except BatchPrivacyBlocked:
            raise
        except RecoveryFailure as error:
            return error
        except Exception:
            return RecoveryFailure('provider', 'operation_failed')

    async def _call_async(self, plan: _Call) -> dict | RecoveryFailure:
        if self.stt_async is None or plan.failure is not None or not plan.inspected or not plan.inspected[2]:
            return self._call_sync(plan)
        try:
            return await self.stt_async(plan.item, plan.route.language, plan.inspected, service=plan.service)
        except BatchPrivacyBlocked:
            raise
        except RecoveryFailure as error:
            return error
        except Exception:
            return RecoveryFailure('provider', 'operation_failed')

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
        elif not self.allowed(item.owner_id, item.duration_seconds, route.provider_service):
            return UnitOutcome('deferred', 'not_due', self.clock() + FUNDING_RETRY_SECONDS)
        audio = self.artifacts.fetch_audio(item)
        inspected, failure = None, None
        try:
            inspected = self.inspect(item, audio)
        except RecoveryFailure as error:
            failure = {'stage': error.stage, 'reason': error.reason}
        # Download/inspection can queue behind other work. Recheck before the
        # one durable provider intent; denial must leave it unspent.
        if route.provider_reason != 'byok' and not self.allowed(
            item.owner_id, item.duration_seconds, route.provider_service
        ):
            return UnitOutcome('deferred', 'not_due', self.clock() + FUNDING_RETRY_SECONDS)
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
        if failure is not None or inspected is None or not inspected[2] or not self._armed():
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
            started = self.protocol.start(segment_id, token, self.clock(), service)
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
        return _Call(segment_id, item, route, token, service, inspected, failure, tuple(candidates))

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
        try:
            uri = self.artifacts.persist_recovery_result(item, response, token)
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
        except Exception:
            return UnitOutcome('retry', 'dependency_warming', provider_reason=route.provider_reason)
        if settled:
            vendor_metrics.attempt(plan.service, outcome, 0.0 if silence else duration)
            if not silence:
                self._record_attempt(plan.service, outcome, latency)
        else:
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
        try:
            return bool(self.health.allows(service)[0])
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
            return UnitOutcome('done', 'processed' if settled else 'superseded')
        if self.clock() - intent['started_at'] > ABANDON_SECONDS:
            failure = {'stage': 'provider', 'reason': 'abandoned_running'}
            settled = self.protocol.settle(
                segment_id,
                intent['token'],
                self.clock(),
                failure=failure,
                attempt_outcome=VendorAttemptOutcome.ABANDONED,
                audio_seconds=item.duration_seconds,
                failover_to=tuple(self._candidates(route)) if failover_enabled() and self._armed() else (),
            )
            if not settled:
                return UnitOutcome('done', 'superseded')
            vendor_metrics.attempt(intent['service'], VendorAttemptOutcome.ABANDONED, item.duration_seconds)
            self._record_attempt(intent['service'], VendorAttemptOutcome.ABANDONED, None)
            if settled == 'failover':
                self._log('failover', 'abandoned_running')
                return UnitOutcome('deferred', 'not_due', self.clock())
            self._log('failed_held', 'abandoned_running')
            return UnitOutcome('done', 'processed', provider_reason='provider_failed')
        return UnitOutcome('deferred', 'lease_held', intent['started_at'] + ABANDON_SECONDS)

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

    def __init__(self, stage_factory: Callable[[], ProviderSttStage] = _service_stage, clock=time.time):
        self.stage_factory, self.clock = stage_factory, clock

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
        return self._result(await stage.run_async(segment_id, run_sync))
