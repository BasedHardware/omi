"""Result metadata contract across independently deployed intake and mergers.

Only markers recoverable from the immutable job belong here. A merger copies
metadata, not source semantics; a pre-registry merger can omit the copy without
blocking projection. Unknown requirements must stay out of the ordered log.
"""

from prometheus_client import Counter

from config.policy.kill_switches import kill_switch

# One registry for intake requirements, merger copying, and projection recovery.
SOURCE_MARKERS = {'source_reuse_version': 1, 'source_alias_version': 1}
REQUIRED = 'required_result_markers'
REFUSED = Counter('omi_batch_result_protocol_refused_total', 'Merge transaction attempts refusing unknown requirements')


def stamp(job: dict, marker: str) -> None:
    """Attach a registered, job-authoritative requirement; never upgrade a version by accident."""
    version = SOURCE_MARKERS[marker]
    protocol = job.get('protocol_version', 1)
    if type(protocol) is not int or protocol not in {1, 2}:
        raise ValueError('cannot replace an unsupported result protocol')
    required = job.get(REQUIRED, {})
    if not isinstance(required, dict) or any(
        field in SOURCE_MARKERS and (type(value) is not int or value != SOURCE_MARKERS[field])
        for field, value in required.items()
    ):
        raise ValueError('cannot replace an unsupported result requirement')
    if marker in job and (type(job[marker]) is not int or job[marker] != version):
        raise ValueError('cannot change an accepted result marker')
    job.update(protocol_version=2, **{marker: version})
    # Legacy jobs can already carry another registered marker without a map.
    # Retain unknown requirements: rebuilding only known fields would launder
    # a future requirement into a commit supported by this binary.
    job[REQUIRED] = {**required, **{field: job[field] for field in SOURCE_MARKERS if field in job}}


def _witnesses_own_audio_fallback(job: dict, fallback: dict, slot: dict) -> bool:
    """Match the preserved log position and original result to the same job."""
    segment_id = job.get('segment_id')
    source_segment_id = fallback.get('source_segment_id')
    original_result = slot.get('result')
    current_result = job.get('result')
    route = job.get('stt_route')
    generation = job.get('privacy_generation')
    return (
        isinstance(source_segment_id, str)
        and bool(source_segment_id)
        and source_segment_id != segment_id
        and 'source_alias' not in job
        and 'source_alias_of' not in job
        and bool(job.get('owner_id'))
        and bool(job.get('owner_key'))
        and job.get('capture_at') is not None
        and job.get('requires_compute_admission') is False
        and isinstance(route, dict)
        and route.get('stt_route') == 'provider'
        and all(slot.get(field) == job.get(field) for field in ('owner_id', 'owner_key', 'capture_at'))
        and type(generation) is int
        and generation >= 0
        and type(slot.get('privacy_generation')) is int
        and slot['privacy_generation'] == generation
        # A previously projected alias can still have an active content ledger.
        and slot.get('projection_state') in ('pending', 'ready')
        and not slot.get('projection')
        and 'previous_segment_id' in slot
        and isinstance(original_result, dict)
        and original_result.get('segment_id') == segment_id
        and isinstance(current_result, dict)
        and current_result.get('segment_id') == segment_id
        and bool(original_result.get('result_uri'))
        and bool(current_result.get('result_uri'))
        and current_result['result_uri'] != original_result['result_uri']
    )


def requirements(job: dict):
    """Interpret registered requirements preserved by older job mutators.

    Older projectors can convert an accepted alias to own-audio work while
    leaving a stale alias requirement behind. The suspended log slot witnesses
    the exact registered alias-to-reuse transition.
    """
    markers = {field: job[field] for field in SOURCE_MARKERS if field in job}
    required = job.get(REQUIRED, markers)
    # Older intake can add a registered marker without extending an unknown
    # envelope. All existing requirements must still match; unknown ones never
    # disappear. Every recognized job marker remains reader-authoritative.
    if (
        isinstance(required, dict)
        and required
        and all(
            field in markers and type(value) is int and value == markers[field] for field, value in required.items()
        )
    ):
        return markers
    fallback = job.get('source_alias_fallback') or {}
    slot = fallback.get('log_slot') if isinstance(fallback, dict) else None
    if (
        markers == {'source_reuse_version': 1}
        and isinstance(slot, dict)
        and bool(job.get('segment_id'))
        and slot.get('segment_id') == job['segment_id']
        and bool(fallback.get('source_segment_id'))
        and not job.get('source_alias')
    ):
        if required == {'source_alias_version': 1} and type(required['source_alias_version']) is int:
            return markers
        # The registry-era fallback writer stamped before removing alias fields.
        # Its dual envelope is recoverable only with a matching dormant log slot.
        if (
            required == SOURCE_MARKERS
            and all(type(value) is int for value in required.values())
            and _witnesses_own_audio_fallback(job, fallback, slot)
        ):
            return markers
    return required


def supported(job: dict) -> bool:
    """Legacy jobs and witnessed fallback transitions retain their registered requirements."""
    protocol = job.get('protocol_version')
    if type(protocol) is not int or protocol not in {1, 2}:
        return False
    markers = {field: job[field] for field in SOURCE_MARKERS if field in job}
    required = requirements(job)
    if any(type(value) is not int for value in markers.values()):
        return False
    if not isinstance(required, dict) or required != markers:
        return False
    if any(type(value) is not int or value != SOURCE_MARKERS.get(field) for field, value in required.items()):
        return False
    if protocol == 2 and not markers:
        return False
    return not markers or protocol == 2 and bool(job.get('source_reuse_key'))


def merge_markers(job: dict) -> dict | None:
    """None means delay without consuming the job, predecessor edge, or log sequence.

    The counter counts transaction attempts, including retries. No fleet inventory
    is inferred from successful output by a single worker.
    """
    if kill_switch('BATCH_RESULT_PROTOCOL_GUARD_ENABLED', log=False) and not supported(job):
        REFUSED.inc()
        return None
    return {field: job[field] for field in SOURCE_MARKERS if field in job}
