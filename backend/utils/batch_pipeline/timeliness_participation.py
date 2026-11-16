"""Bounded TIMELINESS_METRICS-only participation control (SCA-1649).

The elected timeliness sampler reads one data-plane control document,
``{namespace}_control/timeliness_metrics_participation``, and withdraws exactly
like a follower while a validated suppression names this plane. Nothing else
changes: no lease release, no producer sampling, no companion counts, no
processing, queue, maintenance, projection or other monitoring.

Contract: ``sampler-control-design-amended.md`` (SCA-1649), admitted by the
rollout lead's implementation-only ``DESIGN: OK``. This module is the single
validator shared by the sampler gate and the operator helper at
``backend/scripts/rollout/timeliness_participation.py``.

Read bounds: one cold-start point read per process, then at most one attempt per
process per 60s, coalesced by the caller's lock. No query, list, watch, retry or
runtime control write. Every attempt is budgeted as a billable document read,
including absent documents and failures.
"""

import datetime as dt
import logging
import time
from dataclasses import dataclass

from utils import process_identity
from utils.observability.fallback import record_fallback as emit_fallback

logger = logging.getLogger(__name__)

CONTROL_COLLECTION_SUFFIX = '_control'
DOCUMENT_ID = 'timeliness_metrics_participation'
SCHEMA_VERSION = 1
# Only the GKE plane is suppressed for this operation; the allowlist is static.
GKE_PLANE = 'prod-omi-backend'
ALLOWED_TARGET_PLANES = frozenset({GKE_PLANE})
PROD_NAMESPACE = 'batch_pipeline_prod'
MAX_LIFETIME_SECONDS = 1800.0
MAX_FUTURE_SKEW_SECONDS = 60.0
MAX_OPERATION_ID_BYTES = 128
READ_INTERVAL_SECONDS = 60.0
READ_TIMEOUT_SECONDS = 10.0
# Monotonic end-of-window history is bounded so a long-lived process cannot grow
# it without limit; the oldest ended operation is forgotten first.
MAX_ENDED_OPERATIONS = 16
# Exception class names that mean the bounded read ran out of time rather than
# failing for another reason. Matched by name so this module needs no api_core.
TIMEOUT_EXCEPTION_NAMES = frozenset({'DeadlineExceeded', 'TimeoutError', 'ReadTimeout', 'RetryError'})
# Cloud Run injects these; GKE does not. The split matches omi_logging.
CLOUD_RUN_MARKERS = process_identity.CLOUD_RUN_MARKERS
IN_CLUSTER_MARKER = process_identity.IN_CLUSTER_MARKER
POD_NAMESPACE_ENV = process_identity.POD_NAMESPACE_ENV


class ParticipationInvalid(ValueError):
    """The control document is present but not a valid suppression."""


@dataclass(frozen=True)
class Participation:
    """One validated suppression that applies to this plane."""

    operation_id: str
    target_plane: str
    expires_monotonic: float


@dataclass(frozen=True)
class Observation:
    """What one parsed control document says about this plane's suppression.

    ``state`` distinguishes the ways a suppression ends. The cache needs that
    distinction: an operation observed ``expired`` or displaced must never be
    revived by a later reread under a rolled-back wall clock.
    """

    state: str  # 'active' | 'expired' | 'other_plane' | 'invalid' | 'absent'
    operation_id: str | None = None
    participation: Participation | None = None


def fallback_outcome(error: BaseException | None = None) -> str:
    """The shared fallback reason for a control read or control error."""
    if error is not None and type(error).__name__ in TIMEOUT_EXCEPTION_NAMES:
        return 'timeout'
    return 'other'


def record_fallback(*, to_mode: str, detail: str, error: BaseException | None = None) -> None:
    """Bounded shared telemetry for one control-path degrade. Never raises.

    One call per control read attempt at most, which the 60s cache bounds. The
    sampler continues on its normal cadence either way; this only makes the
    fail-safe branch visible to the shared ``omi_fallback_total`` series.
    """
    emit_fallback(
        component='firestore_read',
        from_mode='control',
        to_mode=to_mode,
        reason=fallback_outcome(error),
        outcome='degraded',
        log=logger,
    )
    logger.warning('event=batch_timeliness_participation outcome=%s detail=%s', to_mode, detail)


def control_document(store):
    """The one control document reference; never a lease or a new collection."""
    return store.client.collection(f'{store.namespace}{CONTROL_COLLECTION_SUFFIX}').document(DOCUMENT_ID)


def read_control(store):
    """One point-document read. Absent documents are still billable reads."""
    return control_document(store).get(retry=None, timeout=READ_TIMEOUT_SECONDS)


def timeliness_plane(namespace: str) -> str | None:
    """This process's allowlisted plane, or None when identity is not provable.

    None means participate: a missing or unrecognized identity never suppresses
    sampling. The binding is static and explicit; it is never inferred from
    generic Cloud Run labels.
    """
    if namespace != PROD_NAMESPACE:
        return None
    if process_identity.is_cloud_run():
        return None
    if not process_identity.is_in_cluster():
        return None
    pod_namespace = process_identity.pod_namespace()
    if pod_namespace and pod_namespace != GKE_PLANE:
        return None
    return GKE_PLANE


def _timestamp(value, field: str) -> float:
    if not isinstance(value, dt.datetime):
        raise ParticipationInvalid(f'{field} must be a Firestore timestamp')
    if value.tzinfo is None:
        raise ParticipationInvalid(f'{field} must be timezone-aware')
    return value.timestamp()


def observe_participation(data, *, plane: str | None, now_wall: float, now_monotonic: float) -> Observation:
    """Validate the strict schema and report how this plane's suppression stands.

    Absent, expired, malformed or non-target state means normal participation.
    The returned state keeps the operation identity so the caller can remember
    that the operation ended instead of forgetting it.
    """
    if not isinstance(data, dict):
        raise ParticipationInvalid('control document must be a map')
    version = data.get('version')
    if type(version) is not int or version != SCHEMA_VERSION:
        raise ParticipationInvalid('version must be the integer 1')
    target = data.get('target_plane')
    if not isinstance(target, str) or target not in ALLOWED_TARGET_PLANES:
        raise ParticipationInvalid('target_plane is not allowlisted')
    operation_id = data.get('operation_id')
    if not isinstance(operation_id, str) or not operation_id:
        raise ParticipationInvalid('operation_id must be a nonempty string')
    if len(operation_id.encode('utf-8')) > MAX_OPERATION_ID_BYTES:
        raise ParticipationInvalid('operation_id exceeds 128 UTF-8 bytes')
    created = _timestamp(data.get('created_at'), 'created_at')
    until = _timestamp(data.get('suppressed_until'), 'suppressed_until')
    if not until > created:
        raise ParticipationInvalid('suppressed_until must be after created_at')
    if until - created > MAX_LIFETIME_SECONDS:
        raise ParticipationInvalid('suppression lifetime exceeds 1800s')
    if created > now_wall + MAX_FUTURE_SKEW_SECONDS:
        raise ParticipationInvalid('created_at is beyond the 60s clock-skew allowance')
    if plane is None or target != plane:
        return Observation(state='other_plane', operation_id=operation_id)
    if until <= now_wall:
        return Observation(state='expired', operation_id=operation_id)
    # Bound the monotonic deadline by the contract lifetime so a wall-clock
    # rollback cannot stretch a suppression past its own maximum.
    remaining = min(until - max(now_wall, created), MAX_LIFETIME_SECONDS)
    return Observation(
        state='active',
        operation_id=operation_id,
        participation=Participation(
            operation_id=operation_id,
            target_plane=target,
            expires_monotonic=now_monotonic + remaining,
        ),
    )


def parse_participation(data, *, plane: str | None, now_wall: float, now_monotonic: float) -> Participation | None:
    """Validate the strict schema; return a suppression only when it applies here."""
    return observe_participation(data, plane=plane, now_wall=now_wall, now_monotonic=now_monotonic).participation


class ParticipationCache:
    """At most one control read per process per 60s, with fail-safe retention.

    A read failure may retain only the last validated operation until its
    earliest monotonic expiry deadline and never extends it. Same-operation
    rereads and wall-clock rollback cannot extend it either; forward clock
    movement may expire it early.

    An operation that has been observed to end — expired, displaced by another
    operation, absent or malformed — is remembered by its monotonic end, so a
    later reread under a rolled-back wall clock cannot revive it. The history is
    bounded to ``MAX_ENDED_OPERATIONS`` entries.
    """

    def __init__(self, *, read_interval: float = READ_INTERVAL_SECONDS):
        self._read_interval = read_interval
        self._last_attempt: float | None = None
        self._validated: Participation | None = None
        self._ended: dict[str, None] = {}

    @property
    def operation_id(self) -> str | None:
        return self._validated.operation_id if self._validated is not None else None

    @property
    def ended_operations(self) -> tuple[str, ...]:
        """The bounded monotonic end-of-window history, oldest first."""
        return tuple(self._ended)

    def _remember_ended(self, operation_id: str | None) -> None:
        if not operation_id:
            return
        self._ended.pop(operation_id, None)
        self._ended[operation_id] = None
        while len(self._ended) > MAX_ENDED_OPERATIONS:
            self._ended.pop(next(iter(self._ended)))

    def _end_current(self) -> None:
        if self._validated is not None:
            self._remember_ended(self._validated.operation_id)
            self._validated = None

    def _active(self, now_monotonic: float) -> bool:
        if self._validated is None:
            return False
        if now_monotonic < self._validated.expires_monotonic:
            return True
        # The window ended on the monotonic clock: remember it so no later
        # observation of the same operation can revive it.
        self._end_current()
        return False

    def _apply(self, observed: Observation, now_monotonic: float) -> bool:
        if observed.state != 'active' or observed.participation is None:
            self._remember_ended(observed.operation_id)
            self._end_current()
            return False
        validated = observed.participation
        if validated.operation_id in self._ended:
            # This operation already ended in this process; a rolled-back wall
            # clock does not reopen it.
            self._validated = None
            return False
        if self._validated is not None and self._validated.operation_id != validated.operation_id:
            # Another operation took over: the previous one ended here.
            self._end_current()
        if self._validated is not None and self._validated.operation_id == validated.operation_id:
            # A reread of the same operation never extends the deadline.
            validated = Participation(
                operation_id=validated.operation_id,
                target_plane=validated.target_plane,
                expires_monotonic=min(validated.expires_monotonic, self._validated.expires_monotonic),
            )
        self._validated = validated
        return self._active(now_monotonic)

    def suppressed(self, store, *, plane: str | None, now_wall: float, now_monotonic: float) -> bool:
        if plane is None:
            return False
        if self._last_attempt is not None and now_monotonic - self._last_attempt < self._read_interval:
            return self._active(now_monotonic)
        self._last_attempt = now_monotonic
        try:
            snapshot = read_control(store)
        except Exception as error:  # Fail safe: keep only the last validated operation.
            record_fallback(
                to_mode='last_validated',
                detail=f'read_failed exception_type={type(error).__name__}',
                error=error,
            )
            return self._active(now_monotonic)
        if not getattr(snapshot, 'exists', False):
            self._end_current()
            return False
        try:
            observed = observe_participation(
                snapshot.to_dict() or {},
                plane=plane,
                now_wall=now_wall,
                now_monotonic=now_monotonic,
            )
        except ParticipationInvalid as error:
            record_fallback(to_mode='participate', detail=f'invalid reason={error}')
            self._end_current()
            return False
        return self._apply(observed, now_monotonic)


def monotonic() -> float:
    """Indirection so tests can move the reservation clock without patching time."""
    return time.monotonic()
