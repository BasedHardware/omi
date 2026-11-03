"""Home list suppression requires an acknowledged replacement, never just a link.

The header names episode snapshots held by this particular client. Older clients,
first loads, filtered lists and unfetched older pages keep their member rows.
Suppression happens after paging; the raw page size remains the storage cursor.
"""

import logging
import re

from config.episodes import home_hide_episode_members_enabled, episodes_enabled_for
from database import episodes
from utils.episodes import client_gate, home_read

logger = logging.getLogger(__name__)
HELD_EPISODES_HEADER = 'X-Omi-Home-Episode-Ids'
PAGE_SIZE_HEADER = 'X-Omi-Conversation-Page-Size'
SUPPRESSED_HEADER = 'X-Omi-Home-Suppressed-Ids'


def suppress_held_members(uid: str, rows: list[dict], held: str) -> list[dict]:
    if not held or not home_hide_episode_members_enabled() or not episodes_enabled_for(uid):
        return rows
    pairs = held.split(',')
    if len(pairs) > 50 or any(not re.fullmatch(r'[A-Za-z0-9_-]{1,200}:[A-Za-z0-9_-]{1,200}', pair) for pair in pairs):
        return rows
    acknowledged = {tuple(pair.split(':')) for pair in pairs}
    try:
        if not client_gate.client_seen(uid):
            return rows
        represented = set()
        for eid in {pair[0] for pair in acknowledged}:
            episode = episodes.get_episode(uid, eid)
            if not episode or episode.get('recorded_merged_into') or episode.get('status') == 'live':
                continue
            projected = home_read.project_episode(
                uid, episode, members={row['id']: row for row in rows if row.get('episode_id') == eid}, list_row=True
            )
            if projected:
                represented.update((eid, member['id']) for member in projected['members'])
        return [
            row
            for row in rows
            if row.get('status') != 'completed'
            or (row.get('episode_id'), row.get('id')) not in represented.intersection(acknowledged)
        ]
    except Exception as error:
        from utils.observability.fallback import record_fallback

        record_fallback(
            component='firestore_read', from_mode='none', to_mode='none', reason='other', outcome='degraded', log=logger
        )
        logger.warning('event=home_episode_members outcome=visible exception_type=%s', type(error).__name__)
        return rows
