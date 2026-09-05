"""
Simple per-UID rate limiting config.

Each policy defines (max_requests, window_seconds). One window per policy —
no multi-tier caps. Fair use already handles budget enforcement; this layer
prevents abuse and protects backend resources.

Tuning knobs:
    RATE_LIMIT_BOOST: float multiplier on all limits (default 1.0).
        Set > 1.0 during events to relax limits, < 1.0 to tighten.
        Read from env var RATE_LIMIT_BOOST at startup.

    RATE_LIMIT_SHADOW: defaults OFF (enforcement/429 rejections). Set env var
        RATE_LIMIT_SHADOW_MODE=true to revert to shadow/log-only mode.

    RATE_LIMIT_BOOST_EXEMPT: comma-separated policy names that RATE_LIMIT_BOOST
        must NOT multiply. A boost sized for "relax everything during an event"
        also relaxes the few policies whose base limit is the whole point of the
        policy — a cap chosen to stop a client hot loop is not something an
        event boost should widen 100x. Those policies are listed here and always
        serve their base limit.

        Default: "action_items:list,action_items:list_hot_client". Read from env
        at startup, so the exemption is operator-escapable without a code change:
        set RATE_LIMIT_BOOST_EXEMPT="" to put every policy back under the boost.
        Unknown names are ignored (a typo must not take the process down).

    ACTION_ITEMS_LIST_HOT_CLIENT_MAX: requests per 60s that one uid may make to
        GET /v1/action-items *from a hot-loop client class* (see
        utils/action_items_list_guard.py). This is a second, stricter ceiling
        that composes with action_items:list rather than replacing it: every
        client keeps the 12/min cap, and a client identified as the stale
        polling build additionally may not exceed this number. Default 4.
        Set to 0 to disable the extra ceiling (the rollback).

Redis efficiency:
    Each check = 1 Lua script call (atomic INCR + TTL check).
    Multi-instance safe — all state in Redis, no in-process caching.
"""

import os

# ---------------------------------------------------------------------------
# Global knobs (read at import time from env vars)
# ---------------------------------------------------------------------------

RATE_LIMIT_BOOST: float = float(os.getenv("RATE_LIMIT_BOOST", "1.0"))
RATE_LIMIT_SHADOW: bool = os.getenv("RATE_LIMIT_SHADOW_MODE", "false").lower() == "true"


def _hot_client_max() -> int:
    """Base per-minute ceiling for the hot-loop list client class.

    Read once at import like every other policy number. Invalid input falls back
    to the default rather than raising: a typo in an env var must not refuse to
    start the process, and this is a cost control, not a correctness control.
    """
    raw = os.getenv("ACTION_ITEMS_LIST_HOT_CLIENT_MAX", "4").strip()
    try:
        value = int(raw)
    except ValueError:
        return 4
    return max(0, value)


ACTION_ITEMS_LIST_HOT_CLIENT_MAX: int = _hot_client_max()

# Policies the boost must not touch. Env-overridable (see module docstring);
# resolved against RATE_POLICIES below so a typo is dropped, not enforced.
_BOOST_EXEMPT_DEFAULT = "action_items:list,action_items:list_hot_client"
_RATE_LIMIT_BOOST_EXEMPT_RAW: str = os.getenv("RATE_LIMIT_BOOST_EXEMPT", _BOOST_EXEMPT_DEFAULT)

# ---------------------------------------------------------------------------
# Policies: "name" -> (max_requests, window_seconds)
#
# max_requests is the BASE limit before boost is applied.
# Effective limit = int(max_requests * boost), except for the policies in
# BOOST_EXEMPT_POLICIES, which always serve max_requests.
# ---------------------------------------------------------------------------

RATE_POLICIES: dict[str, tuple[int, int]] = {
    # Conversations — each triggers ~22 OpenAI calls
    "conversations:create": (10, 3600),
    "conversations:reprocess": (3, 3600),
    "conversations:merge": (5, 3600),
    # From-segments: on-device-STT upload path (segments already transcribed, so
    # cheaper than :create — no Deepgram, just LLM structuring). Used per finished
    # conversation by Parakeet/local-STT users, so a bit more headroom than :create.
    "conversations:from-segments": (30, 3600),
    # Desktop sends running per-day totals periodically; allow several devices
    # plus reconnect bursts while still capping accidental hot loops.
    "users:desktop_usage_daily": (600, 3600),
    # Chat — 2-6 LLM calls per message
    "chat:send_message": (120, 3600),
    "chat:initial": (60, 3600),
    # Voice — Deepgram + LLM
    "voice:transcribe": (60, 3600),
    "voice:transcribe_stream": (60, 3600),
    "voice:message": (60, 3600),
    "file:upload": (40, 3600),
    # STT proxy — parakeet GPU batch transcription behind the Omi auth guard
    "stt:transcribe": (60, 3600),
    # Agent/MCP — bursty tool calls
    "agent:execute_tool": (120, 3600),
    # JIT frame metadata is cheap, but uploads carry bounded pixel bytes.
    "frame_requests:read": (120, 3600),
    "frame_requests:write": (120, 3600),
    "frame_requests:upload": (30, 3600),
    # The desktop screen-activity sync loop runs once per ~60s per device
    # (~60/hour each). It must NOT share a bucket with interactive reads:
    # a user with two Macs would saturate a 120/hour bucket from background
    # sync alone and 429 their conversation photo loads. Sized for several
    # devices plus reconnect bursts.
    "screen_activity:sync": (600, 3600),
    # Platform tools — backend RAG endpoints
    "tools:search": (60, 3600),
    "tools:mutate": (60, 3600),
    # MCP transport POSTs (initialize/tools-list/tool-calls) are cheap reads, but
    # one user often runs many concurrent MCP clients (multiple IDE/agent sessions)
    # under a single account, and clients reconnect in bursts. A tight cap here turns
    # a reconnect storm into a 429 death-spiral, so this is sized for heavy multi-session
    # use rather than a single client. Tune via RATE_LIMIT_BOOST for events.
    "mcp:sse": (2000, 3600),
    # Action items — lightweight Firestore writes from MCP clients (no LLM), but
    # an agent can loop, so cap creation per hour. Complete/update/delete operate
    # on existing tasks and ride the shared mcp:sse / per-request auth limits.
    # First-party GET /v1/action-items. Old Windows main-process listing
    # stormed this route (~120 qps fleet) with no platform/version header.
    # 12/min/uid covers Mac/Flutter hydrate plus a few pagination pages and
    # stops a tight loop. Enforced in Depends() before Firestore.
    # Boost-exempt (see BOOST_EXEMPT_POLICIES): with RATE_LIMIT_BOOST=100 in
    # prod this cap resolved to 1,200/60s and never fired once, while the loop
    # ran at ~97/min — 48.8% of all billable Firestore document reads.
    "action_items:list": (12, 60),
    # Second, stricter ceiling for the hot-loop client class only. It does not
    # replace action_items:list — both buckets are checked, so the tighter one
    # binds for a stale poller while every other client is governed solely by
    # the 12/min policy above. Base max is env-tunable
    # (ACTION_ITEMS_LIST_HOT_CLIENT_MAX, 0 disables); boost-exempt for the same
    # reason as its parent policy.
    "action_items:list_hot_client": (ACTION_ITEMS_LIST_HOT_CLIENT_MAX, 60),
    "action_items:write": (120, 3600),
    # Memories — single LLM call each
    "memories:create": (60, 3600),
    # Memory batch writes — each request can create up to 100 memories, so the
    # per-request cap is intentionally tighter than memories:create.
    "memories:batch": (30, 3600),
    # Memory import ingest writes source artifacts only; candidate extraction is
    # server-owned and rate-limited separately by worker scheduling.
    "memory_imports:batch": (60, 3600),
    # Memory mutations — lightweight Firestore writes
    "memories:modify": (120, 3600),
    # Memory review queue — lightweight read/resolve workflow over review artifacts
    "memories:review": (120, 3600),
    # Memory deletes — destructive operations
    "memories:delete": (60, 3600),
    # Delete-all is extremely destructive; tight cap with one retry cushion
    "memories:delete_all": (2, 3600),
    # Batch delete — each request removes up to 100 memories in one Firestore write,
    # so the per-request cap is tighter than memories:delete (which is one memory each).
    "memories:delete_batch": (10, 3600),
    # Goals — single LLM call
    "goals:suggest": (30, 3600),
    "goals:advice": (30, 3600),
    "goals:extract": (30, 3600),
    # Search
    "conversations:search": (60, 3600),
    # Expensive background ops
    "knowledge_graph:rebuild": (2, 3600),
    # Return-only SSOT extract for desktop onboarding / local graph writers
    "knowledge_graph:extract": (30, 3600),
    # Return-only SSOT memory-log extract (onboarding ChatGPT/Claude paste import)
    "memories:extract": (30, 3600),
    # Return-only SSOT calendar/gmail/notes synthesis for desktop connector imports
    "connectors:synthesize": (30, 3600),
    # Return-only SSOT provisional conversation topic (emoji + short title)
    "conversations:topic": (60, 3600),
    # Return-only SSOT AI user profile synthesis (once-daily desktop cadence)
    "users:ai_profile_synthesize": (8, 86400),
    # Canonical graph reads — paginated Firestore + assertion hydration
    "knowledge_graph:canonical": (120, 3600),
    "wrapped:generate": (2, 86400),
    # Integration (key = app_id:uid)
    "integration:conversations": (10, 3600),
    "integration:memories": (60, 3600),
    # Phone verification uses IP-based rate_limit_dependency (pre-auth, no UID).
    # Not migrated to per-UID Lua limiter intentionally.
    # Dev API. Read limits are intentionally separate from write limits so a
    # polling client cannot consume the processing/write budget. Developer and
    # MCP API-key contexts are keyed by app/key identity when available.
    "dev:memories_read": (120, 3600),
    "dev:action_items_read": (120, 3600),
    # Conversation reads are limited in two tiers. Every conversation read consumes
    # the shared "reads_total" ceiling plus its per-route budget, so splitting list
    # and detail into separately tunable policies cannot raise the aggregate number
    # of conversation reads one key can make. Transcript reads consume a third,
    # stricter bucket on top of the other two.
    "dev:conversation_reads_total": (60, 3600),
    "dev:conversations_read": (60, 3600),
    "dev:conversation_detail_read": (60, 3600),
    "dev:conversation_transcript_read": (25, 3600),
    "dev:goals_read": (120, 3600),
    "dev:conversations": (25, 3600),
    # Ask (/v1/dev/user/ask): one qa_rag LLM call per request over the caller's
    # conversations — billable like a conversation create, so it carries its own
    # low per-key cap instead of riding the cheap dev:conversations_read list limit.
    "dev:ask": (25, 3600),
    "dev:memories": (120, 3600),
    "dev:memories_batch": (15, 3600),
    "dev:action_items_write": (120, 3600),
    "dev:goals_write": (120, 3600),
    # MCP REST data API
    "mcp:read": (300, 3600),
    "mcp:memories_read": (120, 3600),
    "mcp:memories_write": (120, 3600),
    # Test
    "test:prompt": (30, 3600),
    # Apps
    "apps:generate_prompts": (30, 3600),
    # Persona intro message is a billable LLM call (Features.PERSONA) with no
    # quota gate, unlike its sibling generate_prompts. Same bound as that
    # sibling until a quota-gate policy decision is made (see #12781).
    "apps:twitter_initial_message": (30, 3600),
    # TTS — ElevenLabs proxy. Coarse outer ring; fine-grained burst + daily
    # char caps are enforced in database.redis_db.check_tts_rate_limit.
    "tts:synthesize": (300, 3600),
    # Screen-frame egress adjudication — each call canonicalizes + judges up
    # to 8 images (contract §1).
    "screenshots:adjudicate": (30, 3600),
}


# Resolved after RATE_POLICIES so unknown names (typos, policies deleted since the
# env var was set) are dropped rather than silently "exempting" nothing that exists.
BOOST_EXEMPT_POLICIES: frozenset[str] = frozenset(
    name for name in (n.strip() for n in _RATE_LIMIT_BOOST_EXEMPT_RAW.split(",")) if name in RATE_POLICIES
)


def get_effective_limit(policy_name: str, boost: float | None = None) -> tuple[int, int]:
    """Return (effective_max_requests, window_seconds) with boost applied.

    Policies in BOOST_EXEMPT_POLICIES ignore the boost entirely — including an
    explicitly passed ``boost`` — and always return their base limit. The point
    of exempting a policy is that its number is a decision, not a default.
    """
    base_max, window = RATE_POLICIES[policy_name]
    if policy_name in BOOST_EXEMPT_POLICIES:
        return base_max, window
    b = boost if boost is not None else RATE_LIMIT_BOOST
    return max(1, int(base_max * b)), window
