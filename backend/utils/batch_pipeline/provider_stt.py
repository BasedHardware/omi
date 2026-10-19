"""C8 batch provider-STT stage: languages Parakeet cannot serve, without legacy sync.

A provider unit is admitted like any batch unit but never joins the GPU DRR
ring. It waits as ``provider_pending`` with ``merge_pending`` set, so
OrderedMerge holds the owner's later captures behind it exactly as it holds a
GPU unit. One at-most-once vendor call through ``utils.stt.pre_recorded``
produces an encrypted result; the unit then takes the same ``result_ready``
transition ``Scheduler.complete`` performs, and OrderedMerge, projection,
privacy and usage stay the single path.

Paid-once: the vendor is called only by the delivery that wins the CAS
``provider_pending -> provider_running``, which mints the intent token. Every
later delivery of a running unit reconciles the deterministic per-token result
object and never calls the vendor again.
"""

from dataclasses import asdict, dataclass, fields
import io
import logging
import time
from typing import Any, Callable, Literal
from uuid import uuid4
import wave

from config.stt_provider_policy import PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL, normalized_stt_language
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_quarantine_recovery import RecoveryStore
from utils.batch_pipeline.contracts import WorkItem, WorkResult, projection_speech_spans
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

logger = logging.getLogger(__name__)

PARAKEET_MODEL = 'nvidia/parakeet-tdt-0.6b-v3'
PENDING = 'provider_pending'
RUNNING = 'provider_running'
# A running intent older than this without a persisted result is settled as
# failed, never re-dispatched (same bound as quarantine recovery).
ABANDON_SECONDS = 900.0
# Same wait as batch compute admission's cap deferral (admission.authorize).
FUNDING_RETRY_SECONDS = 60.0

SttRouteName = Literal['parakeet', 'provider']
ProviderReason = Literal['none', 'byok', 'unsupported_language']
ProviderService = Literal['none', 'byok', 'soniox', 'deepgram', 'modulate']
_ROUTES = frozenset({'parakeet', 'provider'})
_PROVIDER_REASONS = frozenset({'none', 'byok', 'unsupported_language'})
_SERVICES = frozenset({'none', 'byok', 'soniox', 'deepgram', 'modulate'})
# Services this stage can actually call. Soniox and Deepgram are not serving
# pre-recorded providers (utils.stt.pre_recorded.get_prerecorded_provider).
_CALLABLE_SERVICES = frozenset({'modulate'})


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

    BYOK does not change the STT route. Sync pre-recorded STT has never used a
    BYOK key (only Modulate and Parakeet serve it), so a BYOK upload is routed by
    language like any other and its reason is recorded for funding.
    """
    normalized = normalized_stt_language(language) or 'multi'
    if normalized in PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL[PARAKEET_MODEL]:
        return SttRoute('parakeet', 'byok' if byok else 'none', 'none', normalized)
    return SttRoute('provider', 'unsupported_language', 'modulate', normalized[:16])


def enqueue_in_transaction(tx, item: WorkItem, now: float, *, route: SttRoute) -> bool:
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


def provider_enqueue(route: SttRoute) -> Callable[[Any, WorkItem, float], bool]:
    return lambda tx, item, now: enqueue_in_transaction(tx, item, now, route=route)


class ProviderSttStore:
    """Job-row intent fences. Privacy and content ownership use RecoveryStore's checks."""

    def __init__(self, store: Any):
        self.store = store
        self.fence = RecoveryStore(store)

    def read(self, segment_id: str) -> dict:
        return self.store.run(lambda tx: self.fence.checked(tx, segment_id)[0])

    def start(self, segment_id: str, token: str, now: float, service: str) -> dict | None:
        """CAS pending -> running. Returns the job if running (ours or a prior intent), else None."""
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
            job['state'] = RUNNING
            job['provider_intent'] = {
                'token': token,
                'service': service,
                'privacy_generation': binding.privacy_generation,
                'started_at': now,
            }
            tx.put('jobs', segment_id, job)
            return job

        return self.store.run(commit)

    def settle(
        self,
        segment_id: str,
        token: str,
        now: float,
        result_uri: str | None = None,
        *,
        outcome: str = 'success',
        failure: dict | None = None,
    ) -> bool:
        closed_failure = None
        if result_uri is None:
            if not failure or failure.get('stage') not in STAGES or failure.get('reason') not in REASONS:
                raise ValueError('closed provider failure required')
            closed_failure = {'stage': failure['stage'], 'reason': failure['reason']}

        def commit(tx):
            job, _ = self.fence.checked(tx, segment_id)
            if (
                job.get('state') != RUNNING
                or job.get('provider_intent', {}).get('token') != token
                or job.get('result')
                or tx.get('results', segment_id)
            ):
                return False
            owner = tx.get('owners', owner_key(job['owner_id']))
            if closed_failure is not None:
                # One vendor call was already spent: terminal failed-held, never
                # 'held', so quarantine recovery cannot spend a second call.
                job.update(
                    state='quarantined',
                    merge_pending=False,
                    failure='worker_failed',
                    quarantine_reason='worker_failed',
                    quarantined_at=now,
                    recovery_state='failed_held',
                )
                job['provider_intent']['failure'] = closed_failure
            else:
                job.update(state='result_ready', result=asdict(WorkResult(segment_id, result_uri or '', outcome)))
            job['provider_intent']['settled_at'] = now
            owner['revision'] = owner.get('revision', 0) + 1
            tx.put('owners', owner_key(job['owner_id']), owner)
            tx.put('jobs', segment_id, job)
            return True

        return self.store.run(commit)


def transcribe(item: WorkItem, language: str | None, inspected: tuple, *, service: str) -> dict:
    """One vendor call with client retries disabled (attempts=2), as quarantine recovery."""
    from diarizer.batch_pipeline import validate_words

    # Deferred: the provider module's encryption import needs runtime secrets.
    from utils.stt.pre_recorded import modulate_prerecorded_from_bytes

    pcm, duration, spans = inspected
    if service != 'modulate':
        raise RecoveryFailure('provider', 'provider_failed')
    output = io.BytesIO()
    with wave.open(output, 'wb') as clean:
        clean.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        clean.writeframes(pcm)
    response = at_stage(
        'provider',
        'provider_failed',
        lambda: modulate_prerecorded_from_bytes(output.getvalue(), language=language, return_language=True, attempts=2),
    )

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
        # Vendor speaker labels are used directly, as recovered units' are.
        'diarization': {'turns': []},
        'words_provider': service,
        'language': detected,
        'recovery_version': 1,
    }
    at_stage('payload_validation', 'invalid_payload', lambda: projection_speech_spans(payload, duration))
    return payload


Outcome = Literal['done', 'deferred', 'discarded', 'retry']


@dataclass(frozen=True)
class UnitOutcome:
    """Transport-free result; the queue consumer maps it onto contract (a)'s Result."""

    outcome: Outcome
    reason: str  # ConsumerReason value, or a RetryReason value for 'retry'
    available_at: float | None = None
    provider_reason: str = 'none'  # ProviderSttReason value, for metrics only


def _default_allowed(owner_id: str, seconds: float, service: str) -> bool:
    from utils.stt_cap_dispatch import sync_allowed

    return sync_allowed(owner_id, seconds, service)


class ProviderSttStage:
    def __init__(
        self,
        store: Any,
        artifacts: Any,
        *,
        stt: Callable[..., dict] = transcribe,
        allowed: Callable[[str, float, str], bool] = _default_allowed,
        inspect: Callable[[WorkItem, bytes], tuple] = inspect_audio,
        clock: Callable[[], float] = time.time,
    ):
        self.protocol = ProviderSttStore(store)
        self.artifacts, self.stt, self.allowed, self.inspect, self.clock = artifacts, stt, allowed, inspect, clock

    def run(self, segment_id: str) -> UnitOutcome:
        try:
            return self._run(segment_id)
        except BatchPrivacyBlocked:
            return UnitOutcome('discarded', 'privacy_blocked')
        except ProjectionBlocked:
            return UnitOutcome('discarded', 'superseded')

    def _run(self, segment_id: str) -> UnitOutcome:
        job = self.protocol.read(segment_id)
        if job.get('state') not in (PENDING, RUNNING):
            return UnitOutcome('done', 'superseded')
        item = WorkItem(**{field.name: job[field.name] for field in fields(WorkItem) if field.name in job})
        route = SttRoute(**job['stt_route'])
        if job['state'] == RUNNING:
            return self._reconcile(segment_id, job, item)
        if not self.allowed(item.owner_id, item.duration_seconds, route.provider_service):
            return UnitOutcome('deferred', 'not_due', self.clock() + FUNDING_RETRY_SECONDS)
        audio = self.artifacts.fetch_audio(item)
        inspected, failure = None, None
        try:
            inspected = self.inspect(item, audio)
        except RecoveryFailure as error:
            failure = {'stage': error.stage, 'reason': error.reason}
        token = uuid4().hex
        started = self.protocol.start(segment_id, token, self.clock(), route.provider_service)
        if started is None:
            return UnitOutcome('done', 'superseded')
        if started['provider_intent']['token'] != token:
            return self._reconcile(segment_id, started, item)
        payload = None
        if failure is None and inspected is not None:
            try:
                payload = (
                    silence_payload(inspected[1])
                    if not inspected[2]
                    else self.stt(item, route.language, inspected, service=route.provider_service)
                )
                result_outcome(payload)
            except BatchPrivacyBlocked:
                raise
            except RecoveryFailure as error:
                failure = {'stage': error.stage, 'reason': error.reason}
            except Exception:
                failure = {'stage': 'provider', 'reason': 'operation_failed'}
        if failure is not None:
            if not self.protocol.settle(segment_id, token, self.clock(), failure=failure):
                return UnitOutcome('done', 'superseded')
            self._log('failed_held', failure['reason'])
            return UnitOutcome('done', 'processed', provider_reason='provider_failed')
        # A storage/commit failure leaves the intent running; the deterministic
        # encrypted object is reconciled by a later delivery without a vendor call.
        try:
            uri = self.artifacts.persist_recovery_result(item, payload, token)
            settled = self.protocol.settle(segment_id, token, self.clock(), uri, outcome=result_outcome(payload))
        except BatchPrivacyBlocked:
            raise
        except Exception:
            return UnitOutcome('retry', 'dependency_warming', provider_reason=route.provider_reason)
        self._log('settled' if settled else 'superseded', 'none')
        return UnitOutcome('done', 'processed' if settled else 'superseded', provider_reason=route.provider_reason)

    def _reconcile(self, segment_id: str, job: dict, item: WorkItem) -> UnitOutcome:
        intent = job['provider_intent']
        uri = self.artifacts.find_recovery_result(item, intent['token'])
        if uri:
            outcome = result_outcome(self.artifacts.load_result(item, uri))
            settled = self.protocol.settle(segment_id, intent['token'], self.clock(), uri, outcome=outcome)
            return UnitOutcome('done', 'processed' if settled else 'superseded')
        if self.clock() - intent['started_at'] > ABANDON_SECONDS:
            failure = {'stage': 'provider', 'reason': 'abandoned_running'}
            settled = self.protocol.settle(segment_id, intent['token'], self.clock(), failure=failure)
            if settled:
                self._log('failed_held', 'abandoned_running')
            return UnitOutcome('done', 'processed' if settled else 'superseded', provider_reason='provider_failed')
        return UnitOutcome('deferred', 'lease_held', intent['started_at'] + ABANDON_SECONDS)

    @staticmethod
    def _log(outcome: str, reason: str) -> None:
        try:
            logger.info('event=batch_provider_stt outcome=%s reason=%s', outcome, reason)
        except Exception:
            pass
