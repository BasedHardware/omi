"""Content-free joins. IDs are hashed in logs and never Prometheus labels."""

import hashlib
import inspect
import logging
import time
from contextvars import ContextVar
from functools import wraps
from types import SimpleNamespace
from typing import Any, Callable, ParamSpec, TypeVar

from prometheus_client import Counter, Histogram

from config.repeat_work import revision_reuse

P = ParamSpec('P')
R = TypeVar('R')

logger = logging.getLogger(__name__)
_scope: ContextVar[tuple[str, object] | None] = ContextVar('repeat_work_conversation', default=None)
FEATURES = Counter(
    'omi_repeat_work_features_total', 'Feature invocations and exact successful reuse', ['feature', 'outcome']
)
CALLS = Counter('omi_repeat_work_llm_calls_total', 'Observed LangChain calls in conversation scope', ['outcome'])
FINALS = Counter(
    'omi_repeat_work_finalizations_total', 'Durable conversation revisions; join logs for distinct survivors'
)
PLAYBACK_WRITES = Counter('omi_playback_writes_total', 'Playback write decisions', ['outcome'])
PLAYBACK_BUILDS = Counter('omi_playback_artifacts_total', 'Playback artifact work', ['representation', 'outcome'])
PLAYBACK_BUILD_SECONDS = Histogram(
    'omi_playback_build_seconds',
    'Cold playback build duration',
    ['representation'],
    buckets=(0.1, 1, 3, 5, 10, 20, 30, 60, 120, 300),
)


def _join(uid: str, conversation: object, event: str, feature: str = 'none', outcome: str = 'success') -> None:
    identity = getattr(conversation, 'id', None)
    current = _scope.get()
    if not identity and current is not None and current[0] == uid:
        identity = getattr(current[1], 'id', None)
    if not identity:
        return  # Initial captures acquire their durable ID after generation.
    logger.info(
        'event=repeat_work kind=%s conversation_key=%s revision=%s feature=%s outcome=%s',
        event,
        hashlib.sha256(f'{uid}\0{identity}'.encode()).hexdigest(),
        getattr(conversation, 'sync_content_revision', None),
        feature,
        outcome,
    )


def record_feature(uid: str, conversation: object, feature: str, outcome: str) -> None:
    if revision_reuse():
        FEATURES.labels(feature, outcome).inc()
        _join(uid, conversation, 'feature', feature, outcome)


def record_final(uid: str, conversation: object) -> None:
    if revision_reuse():
        FINALS.inc()
        _join(uid, conversation, 'durable_final')


def record_llm_call(outcome: str, feature: str = 'other') -> None:
    current = _scope.get()
    if revision_reuse() and current is not None:
        CALLS.labels(outcome).inc()
        bounded_feature = {'conv_structure': 'notes', 'memories': 'l1'}.get(feature, 'other')
        _join(*current, 'llm_call', feature=bounded_feature, outcome=outcome)


def conversation_scope(function: Callable[P, R]) -> Callable[P, R]:
    signature = inspect.signature(function)

    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        if not revision_reuse():
            return function(*args, **kwargs)
        bound = signature.bind(*args, **kwargs)
        token = _scope.set((bound.arguments['uid'], bound.arguments['conversation']))
        try:
            return function(*args, **kwargs)
        finally:
            _scope.reset(token)

    return wrapped


PLAYBACK_READY_SECONDS = Histogram(
    'omi_playback_demand_to_ready_seconds',
    'First demand enqueue to artifact ready, including queue/retry time',
    ['representation'],
    buckets=(1, 3, 5, 10, 20, 30, 60, 120, 300, 600),
)


def record_playback_ready(payload: dict[str, Any], representation: str) -> None:
    requested = payload.get('requested_at')
    if payload.get('on_demand') and isinstance(requested, (int, float)):
        PLAYBACK_READY_SECONDS.labels(representation).observe(max(0, time.time() - requested))


def bind_generation(uid: str, conversation_id: str | None, revision: int | None = None) -> None:
    """Bind ingress calls to the ID chosen before notes run, without storing content."""
    if revision_reuse() and conversation_id:
        _scope.set((uid, SimpleNamespace(id=conversation_id, sync_content_revision=revision)))
