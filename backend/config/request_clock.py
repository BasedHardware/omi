"""Server request clocks and closed upload metadata; no client-supplied clock or storage IO."""

from contextvars import ContextVar
import math

started_at: ContextVar[float | None] = ContextVar('omi_request_started_at', default=None)

CLASSES = frozenset({'paid', 'trial', 'free', 'unknown'})


def bounded_class(value):
    return value if isinstance(value, str) and value in CLASSES else 'unknown'


def clock_fields(arrived_at, entitlement):
    if type(arrived_at) not in (int, float) or not math.isfinite(arrived_at) or arrived_at < 0:
        return {}
    return {'upload_arrived_at': arrived_at, 'upload_entitlement': bounded_class(entitlement)}


def context_fields(context):
    context = context or {}
    return clock_fields(context.get('upload_arrived_at'), context.get('upload_entitlement'))
