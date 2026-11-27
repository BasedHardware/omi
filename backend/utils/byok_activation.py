"""Evaluate persisted BYOK activation without loading the user document."""

from datetime import datetime, timezone

BYOK_HEARTBEAT_TTL_SECONDS = 7 * 24 * 60 * 60


def byok_state_is_active(state: dict, *, heartbeat_ttl_seconds: int = BYOK_HEARTBEAT_TTL_SECONDS) -> bool:
    last_seen = state.get('last_seen_at')
    if not state.get('active') or not isinstance(last_seen, datetime):
        return False
    age = (datetime.now(timezone.utc) - last_seen).total_seconds()
    return age <= heartbeat_ttl_seconds
