"""Read-only live ownership for Home; never changes episode membership."""

import logging
from typing import Mapping

from config.home_processing import ownership_enabled
from config.episodes import episodes_enabled_for
from database import episodes
from utils.conversations.recorded_time import conversation_span
from utils.episodes import client_gate, metrics
from utils.episodes.policy import utc
from utils.episodes.timeline import ownership_end
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)


def live_owner(uid: str, *, firestore_client=None) -> dict | None:
    if not ownership_enabled(uid) or not episodes_enabled_for(uid) or not client_gate.client_seen_cached(uid):
        return None
    try:
        owner = episodes.get_current_episode(uid, firestore_client=firestore_client)
        return owner if owner and owner.get('status') == 'live' else None
    except Exception as error:
        record_fallback(
            component='firestore_read', from_mode='none', to_mode='none', reason='other', outcome='degraded'
        )
        logger.warning('event=home_live_owner outcome=unavailable exception_type=%s', type(error).__name__)
        return None


def owns_recording(owner: Mapping | None, row: Mapping) -> bool:
    if not owner:
        return False
    # An existing different episode is authoritative, including a closed owner.
    if row.get('episode_id') and row['episode_id'] != owner.get('id'):
        return False
    if row.get('id') in (owner.get('conversation_ids') or []):
        return True
    span = conversation_span(row)
    lo, hi = utc(owner.get('started_at')), ownership_end(dict(owner))
    if span is None or lo is None or hi is None:
        return False
    if not (lo <= span.recorded_start < hi and span.recorded_end <= hi):
        return False
    # This is an observation of missing membership, not a synthetic attachment.
    # Its recording remains reachable from detail reads and attachment repair.
    metrics.EPISODE_HOME_ATTACH_GAP_TOTAL.inc()
    logger.warning('event=episode_attach_gap outcome=home_suppressed')
    return True
