"""Read-only live ownership for Home; never changes episode membership."""

import logging
from typing import Mapping

from config.home_processing import ownership_enabled, owner_cache_enabled
from config.episodes import episodes_enabled_for
from database import episodes, conversations
from utils.conversations.recorded_time import conversation_span
from utils.episodes import client_gate, metrics, home_owner_cache
from utils.episodes.policy import owned_member_ids, utc
from utils.episodes.timeline import ownership_end
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
OWNERSHIP_HEADER = 'X-Omi-Home-Ownership'


def live_owner(uid: str, *, firestore_client=None, use_cache: bool = False) -> dict | None:
    if not ownership_enabled(uid) or not episodes_enabled_for(uid) or not client_gate.client_seen_cached(uid):
        return None
    try:

        def fetch():
            owner = episodes.get_current_episode(uid, firestore_client=firestore_client)
            return owner if owner and owner.get('status') == 'live' else None

        return home_owner_cache.read(uid, fetch, enabled=owner_cache_enabled()) if use_cache else fetch()
    except Exception as error:
        record_fallback(
            component='firestore_read', from_mode='none', to_mode='none', reason='other', outcome='degraded'
        )
        logger.warning('event=home_live_owner outcome=unavailable exception_type=%s', type(error).__name__)
        return None


def live_owner_for_home(uid: str) -> dict | None:
    """Only callers retaining the per-recording client acknowledgement may cache."""
    return live_owner(uid, use_cache=True)


def owns_recording(owner: Mapping | None, row: Mapping) -> bool:
    if not owner:
        return False
    # An existing different episode is authoritative, including a closed owner.
    if row.get('episode_id') and row['episode_id'] != owner.get('id'):
        return False
    if row.get('id') in owned_member_ids(owner):
        return True
    span = conversation_span(row)
    lo, hi = utc(owner.get('started_at')), ownership_end(dict(owner))
    if span is None or lo is None or hi is None:
        return False
    if not (lo <= span.recorded_start < hi and span.recorded_end <= hi):
        return False
    # This is an observation of missing membership, not a synthetic attachment.
    # Its recording remains reachable from detail reads and attachment repair.
    metrics.record_home_attach_gap()
    logger.info(
        'event=episode_attach_gap outcome=home_suppressed conversation_id=%s episode_id=%s',
        row.get('id'),
        owner.get('id'),
    )
    return True


def suppress_owned_syncs(uid: str, items: list[dict], owner: dict | None, represented: set[str]) -> list[dict]:
    """Resolve unlinked targets outside processing status without changing writer leases."""
    if not owner or not items:
        return items
    unknown = {cid for item in items for cid in item['conversation_ids']} - represented
    if unknown:
        try:
            rows = conversations.get_conversations_by_id_without_photos(uid, sorted(unknown))
            represented.update(row['id'] for row in rows if owns_recording(owner, row))
        except Exception as error:
            record_fallback(
                component='firestore_read', from_mode='none', to_mode='none', reason='other', outcome='degraded'
            )
            logger.warning('event=home_sync_owner outcome=unavailable exception_type=%s', type(error).__name__)
            return items
    return [
        item
        for item in items
        if not item['conversation_ids'] or not set(item['conversation_ids']).issubset(represented)
    ]
