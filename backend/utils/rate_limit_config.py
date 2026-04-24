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

Redis efficiency:
    Each check = 1 Lua script call (atomic INCR + TTL check).
    Multi-instance safe — all state in Redis, no in-process caching.
"""

import os

# ---------------------------------------------------------------------------
# Global knobs (read at import time from env vars)
# ---------------------------------------------------------------------------

RATE_LIMIT_BOOST: float = float(os.getenv("RATE_LIMIT_BOOST", "1.0"))
RATE_LIMIT_SHADOW: bool = os.getenv("RATE_LIMIT_SHADOW_MODE", "false").lower() != "false"

# ---------------------------------------------------------------------------
# Policies: "name" -> (max_requests, window_seconds)
#
# max_requests is the BASE limit before boost is applied.
# Effective limit = int(max_requests * boost).
# ---------------------------------------------------------------------------

RATE_POLICIES: dict[str, tuple[int, int]] = {
    # Conversations — each triggers ~22 OpenAI calls
    "conversations:create": (10, 3600),
    "conversations:reprocess": (3, 3600),
    "conversations:merge": (5, 3600),
    # Chat — 2-6 LLM calls per message
    "chat:send_message": (120, 3600),
    "chat:initial": (60, 3600),
    # Voice — Deepgram + LLM
    "voice:transcribe": (60, 3600),
    "voice:transcribe_stream": (60, 3600),
    "voice:message": (60, 3600),
    "file:upload": (40, 3600),
    # Agent/MCP — bursty tool calls
    "agent:execute_tool": (120, 3600),
    # Platform tools — backend RAG endpoints
    "tools:search": (60, 3600),
    "tools:mutate": (60, 3600),
    "mcp:sse": (200, 3600),
    # Memories — single LLM call each
    "memories:create": (60, 3600),
    # Memory batch writes — each request can create up to 100 memories, so the
    # per-request cap is intentionally tighter than memories:create.
    "memories:batch": (30, 3600),
    # Memory mutations — lightweight Firestore writes
    "memories:modify": (120, 3600),
    # Memory deletes — destructive operations
    "memories:delete": (60, 3600),
    # Delete-all is extremely destructive; tight cap with one retry cushion
    "memories:delete_all": (2, 3600),
    # Goals — single LLM call
    "goals:suggest": (30, 3600),
    "goals:advice": (30, 3600),
    "goals:extract": (30, 3600),
    # Search
    "conversations:search": (60, 3600),
    # Expensive background ops
    "knowledge_graph:rebuild": (2, 3600),
    "wrapped:generate": (2, 86400),
    # Integration (key = app_id:uid)
    "integration:conversations": (10, 3600),
    "integration:memories": (60, 3600),
    # Phone verification uses IP-based rate_limit_dependency (pre-auth, no UID).
    # Not migrated to per-UID Lua limiter intentionally.
    # Dev API
    "dev:conversations": (25, 3600),
    "dev:memories": (120, 3600),
    "dev:memories_batch": (15, 3600),
    # Test
    "test:prompt": (30, 3600),
    # Apps
    "apps:generate_prompts": (30, 3600),
    # TTS — ElevenLabs proxy. Coarse outer ring; fine-grained burst + daily
    # char caps are enforced in database.redis_db.check_tts_rate_limit.
    "tts:synthesize": (300, 3600),
}


def get_effective_limit(policy_name: str, boost: float | None = None) -> tuple[int, int]:
    """Return (effective_max_requests, window_seconds) with boost applied."""
    base_max, window = RATE_POLICIES[policy_name]
    b = boost if boost is not None else RATE_LIMIT_BOOST
    return max(1, int(base_max * b)), window
