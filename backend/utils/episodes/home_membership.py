"""Home list suppression requires an acknowledged replacement, never just a link.

The header names episode snapshots held by this particular client. Older clients,
first loads, filtered lists and unfetched older pages keep their member rows.
Suppression happens after paging; the raw page size remains the storage cursor.
"""

import logging
import re

from config.app_channel import APP_CHANNEL_HEADER
from config.episodes import home_hide_episode_members_enabled, episodes_enabled_for, client_channel_admitted
from config.home_processing import ownership_enabled
from database import episodes
from utils.episodes import client_gate
from utils.episodes.home_processing import live_owner, owns_recording, OWNERSHIP_HEADER

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
        from utils.episodes import home_read

        represented = set()
        ids = sorted({row['episode_id'] for row in rows if (row.get('episode_id'), row.get('id')) in acknowledged})
        for eid, episode in episodes.get_home_episode_snapshots(uid, ids).items():
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


def held_for(request) -> str:
    if request is None or not home_hide_episode_members_enabled():
        return ''
    # A date-filtered view shows its exact matches, including old pages whose
    # episode overlay may fall outside that view's selected window.
    query = getattr(request, 'query_params', {})
    if query.get('start_date') or query.get('end_date'):
        return ''
    return request.headers.get(HELD_EPISODES_HEADER, '')


def live_suppression_for(uid: str, request) -> bool:
    if request is None or not ownership_enabled(uid):
        return False
    query = getattr(request, 'query_params', {})
    return (
        request.headers.get(OWNERSHIP_HEADER) == '1'
        and not query.get('start_date')
        and not query.get('end_date')
        and client_channel_admitted(request.headers.get(APP_CHANNEL_HEADER))
    )


def project_list(uid: str, rows: list[dict], request, response, *, filtered: bool) -> list[dict]:
    """Home-only suppression retains the original storage count for pagination."""
    held = held_for(request)
    if filtered:
        return rows
    owner = live_owner(uid) if live_suppression_for(uid, request) else None
    if not held and owner is None:
        return rows
    if response is not None:
        response.headers[PAGE_SIZE_HEADER] = str(len(rows))
    held_retained = suppress_held_members(uid, rows, held)
    retained = [row for row in held_retained if not owns_recording(owner, row)]
    if response is not None:
        kept = {row['id'] for row in held_retained}
        response.headers[SUPPRESSED_HEADER] = ','.join(row['id'] for row in rows if row['id'] not in kept)
    return retained
