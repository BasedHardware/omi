"""Cohort read adapter. Unready users keep the legacy path; policies stay server-side."""

import os
from datetime import datetime, timezone

from config import episode_log as config
from database import episode_log as store, episodes
from database._client import get_firestore_client
from utils import omi_flags
from utils.episodes import home_read
from utils.episodes.log.codec import digest, loads
from utils.encryption import decrypt


def selected(uid):
    if not config.enabled(uid) or not config.home_enabled():
        return False
    resolved = omi_flags.resolve('EPISODES_LOG_READ_PERCENT', uid)
    return resolved.enabled if resolved is not None else config.read_cohort(uid)


def ready(uid, *, firestore_client=None, now=None):
    if not selected(uid):
        return None
    row = store.state(uid, firestore_client=firestore_client)
    if (
        not row.get('backfill_complete')
        or not row.get('home_rows_ready')
        or row.get('cursor', 0) != row.get('next_seq', 0)
        or row.get('policy_barriers')
    ):
        return None
    now = now or datetime.now(timezone.utc)
    if row.get('home_valid_until') and row['home_valid_until'] <= now:
        from utils.episodes.log import worker

        worker.note_home_clock(uid, row, firestore_client=firestore_client, now=now)
        return None
    return row


def version(uid, state, start, end, limit, cursor):
    # Bind conditional reads to the authenticated user AND exact page/filter.
    # A version for Monday must never suppress Tuesday or a later page.
    return digest(
        {
            'uid': uid,
            'version': state['home_version'],
            'from': start,
            'to': end,
            'limit': limit,
            'cursor': cursor,
            'policy': policy_version(),
        }
    )


def policy_version():
    return digest(
        {
            key: os.getenv(key)
            for key in (
                'HOME_HIDE_BELOW_FLOOR_ROWS',
                'HOME_NEUTRAL_MINIMUM_TITLES',
                'HOME_HIDE_EPISODE_MEMBERS',
            )
        }
    )


def list_window(uid, start, end, *, limit=50, cursor=None, firestore_client=None):
    rows, next_cursor = home_read.list_episode_window(
        uid,
        start,
        end,
        limit=limit,
        cursor=cursor,
        firestore_client=firestore_client,
        namespace='episode_views',
    )
    wires = []
    for row in rows:
        if row.get('home_policy_version') != policy_version() or row.get('home_payload') is None:
            raise ValueError('episode_home_policy_changed')
        if row.get('home_payload'):
            wire = loads(decrypt(row['home_payload'], uid))
            if wire is not None:
                wires.append(wire)
    contained = home_read.contained_ids(rows, wires)
    return rows, [wire for wire in wires if wire['id'] not in contained], next_cursor


def by_id(uid, eid, *, firestore_client=None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    seen = set()
    while eid and eid not in seen and len(seen) < 128:
        seen.add(eid)
        raw = store.root(client, uid).collection('episode_views').document(eid).get().to_dict()
        if not raw:
            return None
        if not raw.get('recorded_merged_into'):
            return episodes.unseal(uid, raw)
        eid = raw['recorded_merged_into']
    return None


def linked(uid, cid, *, firestore_client=None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    link = store.root(client, uid).collection('episode_view_links').document(cid).get().to_dict() or {}
    return by_id(uid, link.get('episode_id'), firestore_client=client) if link.get('episode_id') else None
