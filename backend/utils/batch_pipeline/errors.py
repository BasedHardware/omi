"""Model-free process fencing shared by the worker and lease coordinator."""

import os
import traceback

from utils.observability.reasons import WorkerValidationReason, WorkerValidationStage, reason_values

WORKER_VALIDATION_STAGES = reason_values(WorkerValidationStage)
WORKER_VALIDATION_REASONS = reason_values(WorkerValidationReason)


def error_site_field(error: BaseException) -> str:
    """Return a static source file and line from an exception, never its payload."""
    try:
        frames = traceback.extract_tb(error.__traceback__)
    except Exception:
        return ''
    for frame in reversed(frames):
        if 'site-packages' not in frame.filename and 'dist-packages' not in frame.filename:
            return f' site={os.path.basename(frame.filename)}:{frame.lineno}'
    return ''


def validate_worker_failure(failure):
    """Durable diagnostics accept closed codes only, never an exception message."""
    if (
        not isinstance(failure, dict)
        or set(failure) != {'stage', 'reason'}
        or failure['stage'] not in WORKER_VALIDATION_STAGES
        or failure['reason'] not in WORKER_VALIDATION_REASONS
    ):
        raise ValueError('closed worker validation failure required')


WORKER_VALIDATION_REASON_TOKENS = frozenset(member.value for member in WorkerValidationReason)


def validate_worker_failure_evidence(failure):
    """Evidence-only diagnostics from an ordinary retryable failure.

    The stage stays closed. The reason may additionally be the enum's own
    ``unknown`` token: an unclassified exception is still a diagnosed stage,
    and the evidence never decides a transition, so its vocabulary is the
    strict superset of the terminal gate's. Exception messages stay out.
    """
    if (
        not isinstance(failure, dict)
        or set(failure) != {'stage', 'reason'}
        or failure['stage'] not in WORKER_VALIDATION_STAGES
        or failure['reason'] not in WORKER_VALIDATION_REASON_TOKENS
    ):
        raise ValueError('closed worker failure evidence required')


class FatalGpuError(RuntimeError):
    """GPU process must restart; never turn this flight into a segment failure."""
