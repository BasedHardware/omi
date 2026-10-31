"""Content-free joins. IDs are hashed in logs and never Prometheus labels."""

import hashlib
import inspect
import json
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
PHASE_A_CALLS = Counter(
    'omi_conversation_llm_calls_total',
    'Observed calls by bounded feature in conversation scope',
    ['feature', 'outcome'],
)
SURVIVOR_REFRESHES = Counter(
    'omi_episode_survivor_refreshes_total',
    'Actual survivor processing attempts; episode joins are in content-free logs',
    ['membership'],
)
# Static conversation feature vocabulary; unknown/custom feature names use other.
LLM_FEATURES = frozenset(
    {
        'app_generator',
        'app_integrations',
        'chat',
        'conv_action_items',
        'conv_apps',
        'conv_discard',
        'conv_folder',
        'conv_structure',
        'conversation_processing',
        'daily_summary',
        'episode_boundary',
        'episode_composer',
        'episode_incremental',
        'episode_moment',
        'followup',
        'goals',
        'jev_conversation_relevance',
        'jev_conversation_smart_merge',
        'jev_episode_boundary',
        'knowledge_graph',
        'memories',
        'notifications',
        'onboarding',
        'open_loop_card',
        'open_loop_daily',
        'openglass',
        'other',
        'persona',
        'proactive_notification',
        'rag',
        'realtime_integrations',
        'screen_frame_judge',
        'speaker_identification',
        'subscription_notification',
        'transcribe',
        'trends',
        'wake_word_adjudication',
    }
)

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


# Bounded outcome labels for on-demand playback work. Every terminal and retry
# response of an on-demand task lands in one of these, so failed playback is
# visible next to built/exists instead of only lowering queue and GCS volume.
DEMAND_PLAYBACK_OUTCOMES = frozenset(
    {
        'built',
        'exists',
        'superseded',
        'unavailable',
        'failed_final',
        'retry',
        'locked',
        'destructive_deferred',
        'skipped',
        'account_pending_deletion',
        'chunks_missing',
        'empty_audio',
        'no_audio_files',
        'deleted_conversation',
        'invalid_payload',
        'error',
    }
)

_DEMAND_STATUS_OUTCOMES = {'done': 'built', 'deferred': 'destructive_deferred'}


def record_demand_playback_outcome(payload: Any, response_body: bytes | None) -> None:
    """Count one on-demand audio-merge response; ``None`` body means an unhandled exception."""
    if not isinstance(payload, dict) or payload.get('on_demand') is not True:
        return
    representation = 'conversation' if payload.get('schema_version') == 2 else 'file'
    outcome = 'error'
    if response_body is not None:
        try:
            body: Any = json.loads(response_body)
        except Exception:
            body = None
        fields: dict[str, Any] = body if isinstance(body, dict) else {}
        status = str(fields.get('status') or '')
        if status == 'dropped':
            outcome = str(fields.get('reason') or '')
        else:
            outcome = _DEMAND_STATUS_OUTCOMES.get(status, status)
    PLAYBACK_BUILDS.labels(representation, outcome if outcome in DEMAND_PLAYBACK_OUTCOMES else 'other').inc()


def _join(uid: str, conversation: object, event: str, feature: str = 'none', outcome: str = 'success') -> None:
    identity = (
        getattr(conversation, 'conversation_id', None)
        or getattr(conversation, 'id', None)
        or getattr(conversation, 'processing_conversation_id', None)
    )
    current = _scope.get()
    if not identity and current is not None and current[0] == uid:
        identity = getattr(current[1], 'conversation_id', None) or getattr(current[1], 'id', None)
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


def record_llm_call(outcome: str, feature: str = 'other', *, direct: bool = False) -> None:
    current = _scope.get()
    if current is not None:
        bounded_feature = feature if feature in LLM_FEATURES else 'other'
        bounded_outcome = outcome if outcome in {'completed', 'failed'} else 'other'
        PHASE_A_CALLS.labels(bounded_feature, bounded_outcome).inc()
        _join(*current, 'llm_call', feature=bounded_feature, outcome=bounded_outcome)
        if revision_reuse() and not direct:
            CALLS.labels(outcome).inc()


def record_survivor_refresh(uid: str, conversation_id: str, episode_id: str | None) -> None:
    SURVIVOR_REFRESHES.labels('episode' if episode_id else 'unassigned').inc()
    logger.info(
        'event=episode_survivor_refresh conversation_key=%s episode_key=%s',
        hashlib.sha256(f'{uid}\0{conversation_id}'.encode()).hexdigest(),
        hashlib.sha256(f'{uid}\0{episode_id}'.encode()).hexdigest() if episode_id else 'unassigned',
    )


def conversation_scope(function: Callable[P, R]) -> Callable[P, R]:
    signature = inspect.signature(function)

    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        bound = signature.bind(*args, **kwargs)
        conversation = bound.arguments.get('conversation')
        if conversation is None:
            conversation = bound.arguments.get('moment')
        if conversation is None:
            conversation = SimpleNamespace(id=bound.arguments.get('conversation_id'))
        token = _scope.set((bound.arguments['uid'], conversation))
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
    if conversation_id:
        _scope.set((uid, SimpleNamespace(id=conversation_id, sync_content_revision=revision)))
