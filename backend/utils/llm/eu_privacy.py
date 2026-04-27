"""EU Privacy Mode dispatcher.

When a user opts in (Firestore `users/{uid}.eu_privacy_mode = true`), backend
LLM features re-route to Regolo's Italy-hosted inference for the supported
workloads, and HARD-BLOCK workloads we cannot serve in-EU yet (vision,
web-search, embeddings, the Anthropic-only chat agent).

We deliberately do NOT silently fall back to non-EU providers for blocked
features. A banner-only fallback would mean the privacy guarantee leaks data
even with the toggle on; the right answer is to disable the affected feature
in the UI and tell the user.

A request-scoped contextvar holds the resolved EU-mode flag so every feature
in the same request sees a consistent value. Setting it from middleware
costs one Firestore read per privacy-conscious user — not the hot path.
"""

from __future__ import annotations

import enum
import logging
import os
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional

import database.users as users_db
from utils.llm.clients import get_model

logger = logging.getLogger('eu_privacy')

# Features that Regolo can serve today (Phase 1). Every entry below must
# have a corresponding model in `_EU_FEATURE_MODELS`. The set covers every
# Omi LLM feature except the hard-blocked ones (chat_agent → Anthropic-only,
# web_search → Perplexity-only, vision → no PAYG vision model on Regolo).
#
# Picks are based on live latency + JSON-quality probes (Apr 27 2026); see
# docs/04-model-mapping.md for the empirical data driving the mapping.
REGOLO_SUPPORTED_FEATURES: frozenset[str] = frozenset(
    {
        # Conversation post-processing (mid-tier)
        'conv_action_items',
        'conv_structure',
        'conv_app_result',
        'daily_summary',
        'external_structure',
        # Conversation lightweight (nano-tier)
        'conv_app_select',
        'conv_folder',
        'conv_discard',
        'daily_summary_simple',
        # Memory & knowledge (mid-tier extraction)
        'memories',
        'learnings',
        'memory_conflict',
        'knowledge_graph',  # LLM extraction, NOT search — search is in EMBEDDING_DEPENDENT_FEATURES
        # Memory lightweight (nano-tier)
        'memory_category',
        # Chat (mid-tier — chat_agent is excluded; that's Anthropic-only)
        'chat_responses',
        'chat_extraction',
        'chat_graph',
        # Chat lightweight (nano-tier)
        'session_titles',
        # Features (mid-tier)
        'goals',
        'goals_advice',
        'notifications',
        'proactive_notification',
        'app_generator',
        'persona_clone',
        'persona_chat_premium',
        'wrapped_analysis',
        # Features lightweight (nano-tier)
        'followup',
        'smart_glasses',
        'onboarding',
        'app_integration',
        'trends',
        'persona_chat',
    }
)

# Features that EU Privacy Mode HARD-BLOCKS. These either have no Regolo
# equivalent (Anthropic agent, Perplexity web search) or have one Regolo
# can't reliably serve on PAYG (vision via qwen3-vl-32b).
REGOLO_HARD_BLOCKED_FEATURES: frozenset[str] = frozenset(
    {
        'chat_agent',  # Anthropic-only
        'web_search',  # Perplexity-only
        'vision',  # qwen3-vl-32b not reliably available
    }
)

# Embedding-dependent features (search-side). Phase 1 keeps embeddings on
# OpenAI by carving them out — but EU mode HARD-BLOCKS them rather than
# silently leaking. Phase 2 will introduce the Qwen3-Embedding-8B 4096-dim
# adapter and graduate these to REGOLO_SUPPORTED_FEATURES.
#
# Note: `knowledge_graph` (LLM-side entity/relationship extraction, in
# REGOLO_SUPPORTED_FEATURES above) is distinct from `knowledge_graph_search`
# (vector lookup over the graph, listed here). Same domain, different code
# paths — only the search side is embedding-dependent.
EMBEDDING_DEPENDENT_FEATURES: frozenset[str] = frozenset(
    {
        'memory_search',
        'knowledge_graph_search',
        'screen_activity_search',
    }
)


class FeatureRouteKind(enum.Enum):
    REGOLO = 'regolo'
    PRIMARY = 'primary'
    HARD_BLOCK = 'hard_block'


@dataclass(frozen=True)
class FeatureRoute:
    """Outcome of `resolve_feature_model`.

    - REGOLO: caller should use `model` (a `regolo/<id>` string) via
      `get_llm()` / `_get_or_create_regolo_llm()`.
    - PRIMARY: caller should use `model` via the existing non-EU path; this
      is what happens when EU mode is OFF (the common case).
    - HARD_BLOCK: caller MUST refuse the request with `banner` as the user-
      facing reason. Do NOT make any LLM call.
    """

    kind: FeatureRouteKind
    model: Optional[str]
    banner: Optional[str] = None

    @property
    def is_eu_route(self) -> bool:
        return self.kind is FeatureRouteKind.REGOLO


# Request-scoped EU privacy flag. Default None so middleware can detect
# "never set" vs "explicitly False" if needed.
_eu_privacy_ctx: ContextVar[Optional[bool]] = ContextVar('eu_privacy_mode', default=None)


def set_eu_privacy_for_request(enabled: bool) -> None:
    """Called by FastAPI middleware after reading the user's setting."""
    _eu_privacy_ctx.set(bool(enabled))


def get_eu_privacy_for_request(uid: Optional[str]) -> bool:
    """Return the per-request EU Privacy Mode flag.

    If middleware already set it, return that. Otherwise, fall back to a
    direct Firestore read — covers WebSocket handlers and tests that bypass
    HTTP middleware.

    Privacy fail-safe: if Firestore is unreachable AND we have a uid, default
    to ON. The whole feature is a privacy guarantee; an outage briefly
    blocking blocked-feature requests is operationally better than briefly
    leaking data to non-EU providers. Operators who prefer availability over
    strict residency can set REGOLO_EU_FAIL_OPEN=1.

    If `uid` is missing (system-internal calls with no user context),
    defaults to OFF since there is no user to protect.
    """
    cached = _eu_privacy_ctx.get()
    if cached is not None:
        return cached
    if not uid:
        return False
    try:
        value = users_db.get_eu_privacy_mode(uid)
    except Exception:
        fail_open = os.environ.get('REGOLO_EU_FAIL_OPEN', '').strip() == '1'
        value = False if fail_open else True
        logger.exception(
            'eu_privacy: failed to read flag uid=%s — defaulting to %s (fail_open=%s)',
            uid,
            'OFF' if not value else 'ON',
            fail_open,
        )
    _eu_privacy_ctx.set(value)
    return value


def clear_eu_privacy_context() -> None:
    """Reset the per-request EU privacy contextvar.

    Call at the entry of background tasks that may inherit ContextVar state
    from a parent request. Without this, a task spawned via
    `asyncio.create_task` or `loop.run_in_executor` keeps the parent's
    privacy flag — which is wrong when the task is acting as a different
    user, or is a system-internal job that should hit the primary path.
    """
    _eu_privacy_ctx.set(None)


# Phase 1 EU model picks. Two-tier strategy mirroring upstream's gpt-4.1-mini
# vs gpt-4.1-nano split. Picks driven by a 5-sample latency probe (Apr 27 2026
# — see docs/04-model-mapping.md for raw data):
#
#   _EU_MID  = mistral-small-4-119b   (€0.50/€2.10, p50 0.43s, p90 0.44s,
#                                      tool-calling verified, no thinking quirks)
#   _EU_NANO = Llama-3.1-8B-Instruct  (€0.05/€0.25, p50 0.62s, p90 0.72s,
#                                      tool-calling verified)
#
# Why NOT thinking models as defaults (minimax-m2.5, qwen3.5-9b/122b/3.6-27b):
# the multi-sample probe revealed all of them have catastrophic tail latency
# on Regolo's PAYG tier. minimax-m2.5 had 3/5 timeouts at 60s (working calls
# took 48-60s). qwen3.5-122b is bimodal — p50 0.36s but p90 2.25s. qwen3.5-9b
# similar — p50 2.5s, p90 42s, one timeout. Llama-3.3-70B and
# mistral-small-4-119b were both rock-solid (P90 within 2% of P50).
#
# Why mistral over Llama-3.3-70B for mid-tier: 2× faster (0.43s vs 0.83s),
# 17% cheaper input, 22% cheaper output, equally consistent, equal
# tool-calling reliability. Llama wins on "household name" but loses on
# every measured dimension.
#
# Operators retain MODEL_QOS_<FEATURE>=regolo/<model> overrides for cases
# where a thinking model's reasoning genuinely beats mistral's instruct
# tuning (e.g. a complex extraction pipeline that's tolerant of tail latency).
_EU_MID = 'regolo/mistral-small-4-119b'
_EU_NANO = 'regolo/Llama-3.1-8B-Instruct'

_EU_FEATURE_MODELS: dict[str, str] = {
    # Conversation post-processing — mid-tier (matches gpt-5.4-mini upstream)
    'conv_action_items': _EU_MID,
    'conv_structure': _EU_MID,
    'conv_app_result': _EU_MID,
    'daily_summary': _EU_MID,
    'external_structure': _EU_MID,
    # Conversation lightweight — nano-tier (matches gpt-4.1-nano upstream)
    'conv_app_select': _EU_NANO,
    'conv_folder': _EU_NANO,
    'conv_discard': _EU_NANO,
    'daily_summary_simple': _EU_NANO,
    # Memory & knowledge — quality-sensitive extraction stays mid
    'memories': _EU_MID,
    'learnings': _EU_MID,
    'memory_conflict': _EU_MID,
    'knowledge_graph': _EU_MID,
    'memory_category': _EU_NANO,
    # Chat — mid-tier
    'chat_responses': _EU_MID,
    'chat_extraction': _EU_MID,
    'chat_graph': _EU_MID,
    'session_titles': _EU_NANO,
    # Features
    'goals': _EU_MID,
    'goals_advice': _EU_MID,
    'notifications': _EU_MID,
    'proactive_notification': _EU_MID,
    'app_generator': _EU_MID,  # could swap to regolo/qwen3-coder-next if code-heavy
    'persona_clone': _EU_MID,
    'persona_chat_premium': _EU_MID,
    'wrapped_analysis': _EU_MID,  # was google/gemini-3-flash-preview upstream
    'followup': _EU_NANO,
    'smart_glasses': _EU_NANO,
    'onboarding': _EU_NANO,
    'app_integration': _EU_NANO,
    'trends': _EU_NANO,
    'persona_chat': _EU_NANO,
}


def _hard_block_banner(feature: str) -> str:
    if feature in EMBEDDING_DEPENDENT_FEATURES:
        return (
            'Memory search and knowledge-graph features are disabled in EU '
            'Privacy Mode. Disable EU Privacy Mode in Settings to use them.'
        )
    if feature == 'vision':
        return 'Vision features require a non-EU provider and are disabled in EU Privacy Mode.'
    if feature == 'web_search':
        return 'Web search requires a non-EU provider and is disabled in EU Privacy Mode.'
    if feature == 'chat_agent':
        return 'The chat agent currently runs on a non-EU provider and is disabled in EU Privacy Mode.'
    return f'Feature "{feature}" is unavailable in EU Privacy Mode.'


def eu_embedding_index_provisioned() -> bool:
    """True when the EU-side Pinecone index has been provisioned at 4096-dim
    and surfaced via PINECONE_INDEX_NAME_EU. While False, embedding-dependent
    features stay HARD_BLOCKED in EU mode — writing a 4096-dim vector to the
    legacy 3072-dim index would hard-fail server-side.

    Set this env var on the deploy that has the second Pinecone index
    available. Until then M2.5 ships dormant: the proxy classes exist
    but the dispatcher never routes embedding workloads to them.
    """
    return bool(os.environ.get('PINECONE_INDEX_NAME_EU', '').strip())


def resolve_feature_model(uid: Optional[str], feature: str) -> FeatureRoute:
    """Decide where to route a feature for the given user.

    The caller passes the user's uid (or None for system-internal calls
    that always use the primary path) and the feature name. The returned
    FeatureRoute tells the caller which path to take — including HARD_BLOCK
    cases where the caller MUST refuse the request without making any LLM
    call (banner field carries the user-facing reason).
    """
    eu_mode = get_eu_privacy_for_request(uid)

    if not eu_mode:
        return FeatureRoute(kind=FeatureRouteKind.PRIMARY, model=get_model(feature))

    if feature in REGOLO_HARD_BLOCKED_FEATURES:
        return FeatureRoute(kind=FeatureRouteKind.HARD_BLOCK, model=None, banner=_hard_block_banner(feature))

    if feature in EMBEDDING_DEPENDENT_FEATURES:
        # M2.5: lift HARD_BLOCK to REGOLO route only when the EU-side Pinecone
        # index is provisioned. Without it, the 4096-dim Qwen3 embedding
        # would have nowhere safe to write — keep blocking.
        if eu_embedding_index_provisioned():
            return FeatureRoute(kind=FeatureRouteKind.REGOLO, model='regolo/Qwen3-Embedding-8B')
        return FeatureRoute(kind=FeatureRouteKind.HARD_BLOCK, model=None, banner=_hard_block_banner(feature))

    if feature in REGOLO_SUPPORTED_FEATURES:
        model = _EU_FEATURE_MODELS.get(feature, 'regolo/Llama-3.3-70B-Instruct')
        return FeatureRoute(kind=FeatureRouteKind.REGOLO, model=model)

    # Unmapped feature in EU mode — block by default. Better to surface a
    # disabled feature than to leak by accident on a feature we forgot to
    # categorize.
    logger.warning('eu_privacy: feature %s has no EU mapping — hard-blocking', feature)
    return FeatureRoute(
        kind=FeatureRouteKind.HARD_BLOCK,
        model=None,
        banner=f'Feature "{feature}" is not yet certified for EU Privacy Mode.',
    )
