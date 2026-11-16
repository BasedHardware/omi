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
import os
import time
from dataclasses import dataclass

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
# Cloud Run injects these; GKE does not. The split matches omi_logging.
CLOUD_RUN_MARKERS = ('K_SERVICE', 'CLOUD_RUN_JOB', 'K_REVISION')
IN_CLUSTER_MARKER = 'KUBERNETES_SERVICE_HOST'
POD_NAMESPACE_ENV = 'POD_NAMESPACE'


class ParticipationInvalid(ValueError):
    """The control document is present but not a valid suppression."""


@dataclass(frozen=True)
class Participation:
    """One validated suppression that applies to this plane."""

    operation_id: str
    target_plane: str
    expires_monotonic: float


def control_document(store):
    """The one control document reference; never a lease or a new collection."""
    return store.client.collection(f'{store.namespace}{CONTROL_COLLECTION_SUFFIX}').document(DOCUMENT_ID)


def read_control(store):
    """One point-document read. Absent documents are still billable reads."""
    return control_document(store).get()


def timeliness_plane(namespace: str) -> str | None:
    """This process's allowlisted plane, or None when identity is not provable.

    None means participate: a missing or unrecognized identity never suppresses
    sampling. The binding is static and explicit; it is never inferred from
    generic Cloud Run labels.
    """
    if namespace != PROD_NAMESPACE:
        return None
    if any(os.getenv(marker) for marker in CLOUD_RUN_MARKERS):
        return None
    if not os.getenv(IN_CLUSTER_MARKER):
        return None
    pod_namespace = os.getenv(POD_NAMESPACE_ENV, '').strip()
    if pod_namespace and pod_namespace != GKE_PLANE:
        return None
    return GKE_PLANE


def _timestamp(value, field: str) -> float:
    if not isinstance(value, dt.datetime):
        raise ParticipationInvalid(f'{field} must be a Firestore timestamp')
    if value.tzinfo is None:
        raise ParticipationInvalid(f'{field} must be timezone-aware')
    return value.timestamp()


def parse_participation(data, *, plane: str | None, now_wall: float, now_monotonic: float) -> Participation | None:
    """Validate the strict schema; return a suppression only when it applies here.

    Absent, expired, malformed or non-target state means normal participation.
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
        return None
    if until <= now_wall:
        return None
    # Bound the monotonic deadline by the contract lifetime so a wall-clock
    # rollback cannot stretch a suppression past its own maximum.
    remaining = min(until - max(now_wall, created), MAX_LIFETIME_SECONDS)
    return Participation(
        operation_id=operation_id,
        target_plane=target,
        expires_monotonic=now_monotonic + remaining,
    )


class ParticipationCache:
    """At most one control read per process per 60s, with fail-safe retention.

    A read failure may retain only the last validated operation until its
    earliest monotonic expiry deadline and never extends it. Same-operation
    rereads and wall-clock rollback cannot extend it either; forward clock
    movement may expire it early.
    """

    def __init__(self, *, read_interval: float = READ_INTERVAL_SECONDS):
        self._read_interval = read_interval
        self._last_attempt: float | None = None
        self._validated: Participation | None = None

    @property
    def operation_id(self) -> str | None:
        return self._validated.operation_id if self._validated is not None else None

    def _active(self, now_monotonic: float) -> bool:
        return self._validated is not None and now_monotonic < self._validated.expires_monotonic

    def suppressed(self, store, *, plane: str | None, now_wall: float, now_monotonic: float) -> bool:
        if plane is None:
            return False
        if self._last_attempt is not None and now_monotonic - self._last_attempt < self._read_interval:
            return self._active(now_monotonic)
        self._last_attempt = now_monotonic
        try:
            snapshot = read_control(store)
        except Exception as error:  # Fail safe: keep only the last validated operation.
            logger.warning(
                'event=batch_timeliness_participation outcome=read_failed exception_type=%s',
                type(error).__name__,
            )
            return self._active(now_monotonic)
        if not getattr(snapshot, 'exists', False):
            self._validated = None
            return False
        try:
            validated = parse_participation(
                snapshot.to_dict() or {},
                plane=plane,
                now_wall=now_wall,
                now_monotonic=now_monotonic,
            )
        except ParticipationInvalid as error:
            logger.warning('event=batch_timeliness_participation outcome=invalid reason=%s', str(error))
            self._validated = None
            return False
        if validated is None:
            self._validated = None
            return False
        if self._validated is not None and self._validated.operation_id == validated.operation_id:
            # A reread of the same operation never extends the deadline.
            validated = Participation(
                operation_id=validated.operation_id,
                target_plane=validated.target_plane,
                expires_monotonic=min(validated.expires_monotonic, self._validated.expires_monotonic),
            )
        self._validated = validated
        return True


def monotonic() -> float:
    """Indirection so tests can move the reservation clock without patching time."""
    return time.monotonic()
