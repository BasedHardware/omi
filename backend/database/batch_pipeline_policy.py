"""Persist a unit's first fallback through a canonical sibling fence."""

import logging
from dataclasses import dataclass, replace
from typing import Any, Literal, overload
from collections.abc import Iterable

from config.policy import (
    BatchUnitPolicy,
    ProjectionPolicy,
    SchedulerPolicy,
    RecoveryPolicy,
    FirstSummaryPolicy,
    resolve_batch_policy,
    resolve_stage_policy,
)
from config.policy.stages import STAGE_TYPES
from config.policy.parts import PolicyPart
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection_protocol import ProjectionBlocked

logger = logging.getLogger(__name__)

# `server_flags` default: this process is a serving role, so its environment
# is the server configuration. Operator runs (scripts on a laptop or VM) must
# pass `server_flags` explicitly: None refuses an unpinned unit, and a mapping
# is the serving role's live settings. An operator never pins its own env.
PROCESS_ENVIRONMENT: Any = object()
UNPINNED_REFUSAL = 'unpinned_policy_requires_server_flags'
ANCHOR_STAGE_PIN_OPERATION = 'batch_anchor_stage_pin'
ADMISSION_STAGE = 'admission'


@dataclass(frozen=True)
class AnchorStagePin:
    """A canonical owner part resolved by one sibling, pinned separately.

    The staging transaction self-stages the resolved part on the calling
    job's own row and defers the canonical anchor write to
    ``flush_anchor_stage_pins``. A sibling that wrote the shared anchor row
    inside its own transition collided with every concurrently publishing
    sibling on that single document and burned whole retry budgets
    (``operation=... attempt=5/5 outcome=exhausted``). The pin lands in its
    own single-document transaction: the first writer wins, every later
    staging call copies from the anchor, and convergence is unchanged.
    """

    segment_id: str
    stage: str
    part: dict
    source: str


class UnpinnedPolicyRefused(ProjectionBlocked):
    """An operator run met a unit with no stored stage part and no server flags."""

    def __init__(self, stage: str):
        super().__init__(UNPINNED_REFUSAL)
        self.stage = stage


def recorded_policy(job: dict) -> dict | None:
    raw = job.get('policy')
    if raw is not None and not isinstance(raw, dict):
        raise ValueError('serialized batch policy must be a dict')
    return raw


def policy_in_transaction(
    tx, job: dict, *, observations=None, candidates=None, pins: list | None = None
) -> BatchUnitPolicy:
    raw = recorded_policy(job)
    if raw is not None:
        policy = BatchUnitPolicy.from_dict(raw)
        return policy
    # All siblings serialize through the first extant sibling. Do not rewrite
    # 128 siblings per queue visited: a pull can visit 128 owners and must stay
    # below Firestore's 450 buffered-write budget. Each old reader copies the
    # canonical snapshot to its own row before using it.
    anchor = unit_anchor(tx, job)
    raw = recorded_policy(anchor)
    policy = (
        BatchUnitPolicy.from_dict(raw)
        if raw is not None
        else candidate_once(
            candidates,
            (anchor['segment_id'], 'admission'),
            lambda: admission_fallback(job),
        )
    )
    if observations is not None:
        observations.append(('policy_fallback', policy.policy_id))
    siblings = [job] if raw is not None or anchor['segment_id'] == job['segment_id'] else [anchor, job]
    if pins is not None and len(siblings) == 2:
        # A sibling transition must not write the shared anchor row: every
        # concurrently publishing sibling of the same owner would read-modify-
        # write that one document inside its own retry budget and exhaust it.
        # The sibling self-stages the same resolution; the canonical pin lands
        # after commit in flush_anchor_stage_pins's single-document txn.
        siblings = [job]
        pins.append(AnchorStagePin(anchor['segment_id'], ADMISSION_STAGE, policy.to_dict(), 'fallback'))
    for sibling in siblings:
        sibling['policy'] = policy.to_dict()
        sibling['policy_source'] = 'fallback'
        tx.put('jobs', sibling['segment_id'], sibling)
    # The row is the durable event receipt. Emit outside the retriable callback
    # via load_job_policy; transactional stage callers also retain policy_source.
    return policy


def admission_fallback(job):
    """Called only by an admitting role, never a scheduler/projection role."""
    policy = resolve_batch_policy(job['owner_id'], source='fallback')
    if job.get('state') == 'record_pending':
        # Pre-E1 main's live-owner reservation already accepted this capture.
        policy = replace(policy, batch_enabled=True, live_admission_enabled=True, live_record_enabled=True)
    return policy


def candidate_once(candidates, key, resolve):
    if candidates is None:
        return resolve()
    if key not in candidates:
        candidates[key] = resolve()
    return candidates[key]


def flush_anchor_stage_pins(store, pins) -> int:
    """Land deferred canonical pins, one single-document transaction each.

    Best-effort by contract: every caller's transition is already durable when
    this runs, so a contended, refused or raced pin is simply deferred to the
    next staging touch, which re-emits it and converges on the anchor's part.
    Duplicate descriptors from retried transaction bodies collapse on
    ``(segment_id, stage)``; the first emitted resolution wins the anchor and
    later CAS attempts observe the pinned part and no-op. Never raises.
    Returns the number of anchors pinned.
    """
    pinned = 0
    seen = set()
    while pins:
        pin = pins.pop(0)
        key = (pin.segment_id, pin.stage)
        if key in seen:
            continue
        seen.add(key)

        def commit(tx, pin=pin):
            anchor = tx.get('jobs', pin.segment_id)
            if not anchor:
                return False
            if pin.stage == ADMISSION_STAGE:
                if recorded_policy(anchor) is not None:
                    return False
                anchor['policy'] = dict(pin.part)
                anchor['policy_source'] = pin.source
            else:
                raw = (anchor.get('policy_parts') or {}).get(pin.stage)
                if raw is not None:
                    # Another writer pinned first (a retried sibling body, a
                    # concurrent publisher or a partial stamp): it wins.
                    return False
                anchor['policy_parts'] = {**(anchor.get('policy_parts') or {}), pin.stage: dict(pin.part)}
                if recorded_policy(anchor) is None:
                    anchor['policy_part_sources'] = {
                        **(anchor.get('policy_part_sources') or {}),
                        pin.stage: pin.source,
                    }
            tx.put('jobs', pin.segment_id, anchor)
            return True

        try:
            if store.run(commit, operation='batch_anchor_stage_pin'):
                pinned += 1
        except Exception as error:
            logger.warning(
                'event=batch_anchor_stage_pin outcome=deferred segment_id=%s stage=%s exception_type=%s',
                pin.segment_id,
                pin.stage,
                type(error).__name__,
            )
    return pinned


def check_unit_privacy(tx, job):
    binding = job.get('projection_binding') or {}
    ids: set[str] = set(job.get('conversation_ids') or ())
    ids.update(value for value in (job.get('conversation_id'), binding.get('target_conversation_id')) if value)
    if binding and 'capture_at' in job:
        from utils.sync.capture import chunk_identity

        ids.add(
            chunk_identity(
                job['owner_id'],
                binding.get('source', 'omi'),
                binding.get('client_device_id'),
                binding.get('is_locked', False),
                job['capture_at'],
            )
        )
    tx.check_privacy(job['owner_id'], ids, job.get('privacy_generation', binding.get('privacy_generation')))


def unit_anchor(tx, job):
    binding = job.get('projection_binding') or {}
    anchor = job
    for sid in binding.get('segment_ids', ()):
        candidate = job if sid == job['segment_id'] else tx.get('jobs', sid)
        if candidate:
            if candidate.get('owner_id') != job['owner_id']:
                raise ValueError('policy sibling owner mismatch')
            if candidate['segment_id'] != job['segment_id']:
                try:
                    check_unit_privacy(tx, candidate)
                except BatchPrivacyBlocked:
                    continue
            anchor = candidate
            break
    return anchor


@overload
def stage_in_transaction(
    tx,
    job,
    stage: Literal['projection'],
    *,
    observations=None,
    candidates=None,
    server_flags=PROCESS_ENVIRONMENT,
    pins: list | None = None,
) -> ProjectionPolicy: ...


@overload
def stage_in_transaction(
    tx,
    job,
    stage: Literal['scheduler'],
    *,
    observations=None,
    candidates=None,
    server_flags=PROCESS_ENVIRONMENT,
    pins: list | None = None,
) -> SchedulerPolicy: ...


@overload
def stage_in_transaction(
    tx,
    job,
    stage: Literal['recovery'],
    *,
    observations=None,
    candidates=None,
    server_flags=PROCESS_ENVIRONMENT,
    pins: list | None = None,
) -> RecoveryPolicy: ...


@overload
def stage_in_transaction(
    tx,
    job,
    stage: Literal['first_summary'],
    *,
    observations=None,
    candidates=None,
    server_flags=PROCESS_ENVIRONMENT,
    pins: list | None = None,
) -> FirstSummaryPolicy: ...


@overload
def stage_in_transaction(
    tx,
    job,
    stage: str,
    *,
    observations=None,
    candidates=None,
    server_flags=PROCESS_ENVIRONMENT,
    pins: list | None = None,
) -> PolicyPart: ...


def stage_in_transaction(
    tx,
    job,
    stage: str,
    *,
    observations=None,
    candidates=None,
    server_flags=PROCESS_ENVIRONMENT,
    pins: list | None = None,
):
    """CAS one owner part, serializing sibling segments through the same anchor.

    An absent part is expected on new work. No other role's values are filled
    here. Once present, even a partial dict uses code defaults without env.

    `server_flags` selects where an absent part resolves from: the serving
    process's own env (default), an explicit server settings mapping, or, for
    None, nowhere (UnpinnedPolicyRefused before any write).
    """
    raw = (job.get('policy_parts') or {}).get(stage)
    cls = STAGE_TYPES[stage]
    if raw is not None:
        if not isinstance(raw, dict):
            raise ValueError('serialized stage policy must be a dict')
        return cls.from_dict(raw)
    check_unit_privacy(tx, job)
    anchor = unit_anchor(tx, job)
    raw = (anchor.get('policy_parts') or {}).get(stage)
    serving = server_flags is PROCESS_ENVIRONMENT
    if raw is None and server_flags is None:
        raise UnpinnedPolicyRefused(stage)
    # Only a resolution reads server_flags; copying a stored sibling part never does.
    flags = dict(server_flags) if raw is None and not serving else None
    policy = (
        cls.from_dict(raw)
        if raw is not None
        else candidate_once(
            candidates,
            (anchor['segment_id'], stage),
            lambda: (
                resolve_stage_policy(job['owner_id'], stage)
                if serving
                else resolve_stage_policy(job['owner_id'], stage, flags=flags)
            ),
        )
    )
    if serving:
        source = 'fallback'
    elif raw is not None:
        # A copied part keeps its anchor's provenance (only `job` is written).
        source = (anchor.get('policy_part_sources') or {}).get(stage, 'fallback')
    else:
        source = 'operator_server_flags'
    siblings = [job] if raw is not None or anchor['segment_id'] == job['segment_id'] else [anchor, job]
    if pins is not None and len(siblings) == 2:
        # A sibling transition must not write the shared anchor row: every
        # concurrently publishing sibling of the same owner would read-modify-
        # write that one document inside its own retry budget and exhaust it
        # (the batch_completion outcome=retry exhaustion). The sibling
        # self-stages the same resolution; the canonical pin lands after
        # commit in flush_anchor_stage_pins's single-document txn.
        siblings = [job]
        pins.append(AnchorStagePin(anchor['segment_id'], stage, policy.to_dict(), source))
    for sibling in siblings:
        # Copy only this part; retain every concurrent/previous owner's receipt.
        sibling['policy_parts'] = {**(sibling.get('policy_parts') or {}), stage: policy.to_dict()}
        if recorded_policy(sibling) is None:
            sibling['policy_part_sources'] = {**(sibling.get('policy_part_sources') or {}), stage: source}
        tx.put('jobs', sibling['segment_id'], sibling)
    if observations is not None:
        observations.append(('policy_fallback' if recorded_policy(job) is None else 'policy_stage', policy.policy_id))
    return policy


def load_stage_policy(store, segment_id, stage, *, server_flags=PROCESS_ENVIRONMENT):
    observations = []
    candidates = {}
    pins: list = []

    def commit(tx):
        observations.clear()  # Retried callbacks publish only the committed attempt.
        job = tx.get('jobs', segment_id)
        if not job:
            return job, None
        policy = stage_in_transaction(
            tx,
            job,
            stage,
            observations=observations,
            candidates=candidates,
            server_flags=server_flags,
            pins=pins,
        )
        return job, policy

    job, policy = store.run(commit, operation='batch_stage_policy_load')
    flush_anchor_stage_pins(store, pins)
    record_policy_observations(observations)
    return job, policy


def refresh_disabled_recovery(store, segment_id, owner_id):
    """Re-resolve a recovery-disabled snapshot while no paid intent exists.

    A unit admitted during a recovery-off window otherwise holds that verdict
    forever: its upload reads `processing` and only a prod write could release
    it. Only a `held` unit with no `recovery` intent (so no provider call was
    ever authorized) and a disabled recorded part is rewritten, and only to an
    enabled policy. An enabled snapshot is never re-resolved or downgraded.
    Returns the refreshed (job, policy), or None when nothing changed.
    """
    fresh = resolve_stage_policy(owner_id, 'recovery')
    if not fresh.recovery_enabled:
        return None

    def commit(tx):
        job = tx.get('jobs', segment_id)
        if (
            not job
            or job.get('owner_id') != owner_id
            or job.get('state') != 'quarantined'
            or job.get('recovery_state') != 'held'
            or job.get('recovery')
        ):
            return None
        raw = (job.get('policy_parts') or {}).get('recovery')
        if not isinstance(raw, dict) or RecoveryPolicy.from_dict(raw).recovery_enabled:
            return None
        check_unit_privacy(tx, job)
        job['policy_parts'] = {**(job.get('policy_parts') or {}), 'recovery': fresh.to_dict()}
        job['policy_part_sources'] = {**(job.get('policy_part_sources') or {}), 'recovery': 'refreshed'}
        tx.put('jobs', segment_id, job)
        return job, fresh

    refreshed = store.run(commit, operation='batch_recovery_policy_refresh')
    if refreshed is not None:
        logger.info('event=batch_recovery_policy outcome=refreshed policy_id=%s', fresh.policy_id)
    return refreshed


def record_policy_observations(observations: Iterable[tuple[str, Any]]) -> None:
    from config.policy.telemetry import record_policy_source

    for event, policy_id in observations:
        if event in {'policy_fallback', 'policy_stage'}:
            record_policy_source('fallback' if event == 'policy_fallback' else 'stage', policy_id)


def load_job_policy(store, segment_id: str):
    candidates = {}
    pins: list = []

    def commit(tx):
        job = tx.get('jobs', segment_id)
        if not job:
            return job, None, False
        missing = recorded_policy(job) is None
        policy = policy_in_transaction(tx, job, candidates=candidates, pins=pins)
        return job, policy, missing

    job, policy, fallback = store.run(commit, operation='batch_job_policy_load')
    flush_anchor_stage_pins(store, pins)
    if fallback:
        from config.policy.telemetry import record_policy_source

        record_policy_source('fallback', policy.policy_id)
    return job, policy
