"""One bounded, leased episode drain per UID. Never invokes a paid operation.

Other services append/mark only; backend-sync handles wakes and the existing
scheduler tick redrives missed wakes, expired owners and retry deadlines.
"""

import hashlib
import os
import logging
import random
import time
from datetime import datetime, timezone

from config import episode_log as config
from database import episode_log as store, episodes
from database._client import get_firestore_client
from utils import cloud_tasks
from utils.episodes import home_read
from utils.episodes.log import metrics
from utils.episodes.log.codec import dumps, digest, loads
from utils.episodes.log.fold import Fold
from utils.episodes.log.clock import home_clock
from utils.episodes.log.key import gate_digest, uncertain_key
from utils.encryption import encrypt, decrypt

logger = logging.getLogger(__name__)


def wake(uid, deadline):
    # Ceiling to the same stable future bucket in every producing service.
    seconds = int(deadline.timestamp())
    bucket = max(
        ((seconds + config.WAKE_BUCKET_SECONDS - 1) // config.WAKE_BUCKET_SECONDS) * config.WAKE_BUCKET_SECONDS,
        (int(time.time()) // config.WAKE_BUCKET_SECONDS + 1) * config.WAKE_BUCKET_SECONDS,
    )
    cloud_tasks.enqueue_episode_uid_wake(uid, hashlib.sha256(uid.encode()).hexdigest()[:24], bucket)


def mark_dirty(uid, cid, row, *, firestore_client=None):
    if not config.enabled(uid) or not cid or not row:
        return False
    # No placement or composer call here. Payload carries only already-read
    # member metadata; the full transcript contributes to the key, never the log.
    fields = {key: row.get(key) for key in home_read.MEMBER_FIELDS}
    deadline = store.append(
        uid,
        gate_digest(dict(row, id=cid)) or uncertain_key(cid, fields),
        [{'kind': 'member', 'cid': cid, 'payload': fields}],
        firestore_client=firestore_client,
    )
    if deadline is not None:
        try:
            wake(uid, deadline)
        except Exception as error:
            logger.warning('event=episode_log_wake outcome=sweep_recovery exception_type=%s', type(error).__name__)
        return True
    return False


def note_dirty(uid, cid, row):
    try:
        return mark_dirty(uid, cid, row)
    except Exception as error:
        logger.warning('event=episode_log_mark outcome=error exception_type=%s', type(error).__name__)
        return False


def note_home_clock(uid, state, *, firestore_client=None, now=None):
    """Expiry is durable refresh debt, using the same queued phase and lease."""
    cid, at = state.get('home_refresh_cid'), state.get('home_valid_until')
    if not cid or not at:
        return
    try:
        deadline = store.append(
            uid,
            digest({'home_clock': at, 'cid': cid}),
            [{'kind': 'member_refresh', 'cid': cid, 'payload': {'clock_at': at}}],
            firestore_client=firestore_client,
            now=now,
            urgent=True,
        )
        if deadline is not None:
            wake(uid, deadline)
    except Exception as error:
        logger.warning('event=episode_home_clock outcome=sweep_recovery exception_type=%s', type(error).__name__)


def _legacy(uid, eid, client):
    raw = client.collection('users').document(uid).collection('episodes').document(eid).get().to_dict()
    return episodes.unseal(uid, raw)


def _comparison_token(state):
    if not state or state.get('cursor') != state.get('next_seq') or state.get('policy_barriers'):
        return None
    return state.get('cursor'), state.get('home_version'), state.get('epoch')


def compare_rows(uid, rows, homes, client, *, cursor=None):
    token = _comparison_token(store.state(uid, firestore_client=client))
    if token is None or (cursor is not None and token[0] != cursor):
        metrics.COMPARE_SKIPPED.labels(reason='pending').inc()
        return
    comparisons = []
    for eid, row in rows.items():

        def read():
            legacy = _legacy(uid, eid, client)
            if legacy is not None and config.home_enabled() and not legacy.get('recorded_merged_into'):
                legacy['home_row'] = home_read.project_episode(uid, legacy, list_row=True)
            return legacy

        legacy = read()
        view = dict(row, home_row=homes.get(eid)) if row is not None else None
        if any(value != 'match' for value in metrics.differences(legacy, view).values()):
            legacy = read()
        comparisons.append((legacy, view))
    # Legacy mutations append in the same transaction. Bracket every source
    # read with one watermark: ordinary queue lag is never projection drift.
    if _comparison_token(store.state(uid, firestore_client=client)) != token:
        metrics.COMPARE_SKIPPED.labels(reason='inflight').inc()
        return
    for legacy, view in comparisons:
        metrics.compare(legacy, view)


def drain(uid, *, firestore_client=None, now=None):
    if not config.enabled(uid):
        return 'disabled'
    client = firestore_client if firestore_client is not None else get_firestore_client()
    fixed_now = now
    now = now or datetime.now(timezone.utc)
    started = time.monotonic()
    recovered = store.recover_policy_barriers(uid, firestore_client=client, now=now)
    if recovered:
        metrics.observe_state(recovered, 'queued', now)
    claimed = store.claim(uid, firestore_client=client, now=now)
    if not claimed:
        return 'not_due'
    prior = claimed['prior']
    # An expired owner is still a running phase exit, even though derive_phase
    # now derives queued from the elapsed lease.
    phase = 'running' if prior.get('lease_owner') else store.derive_phase(prior, now)
    metrics.observe_state(prior, phase, now)
    outcome = 'error'
    try:
        fold = Fold(uid, store.checkpoint(uid, firestore_client=client))
        before = fold.rows()
        old_links = dict(fold.links)
        events, cursor = store.read_batch(uid, claimed, firestore_client=client)
        changed_members = {event['cid'] for event in events if event['kind'] in {'member', 'member_refresh'}}
        for event in events:
            fold.apply(event)
        rows = fold.rows()
        changed = {
            eid: row
            for eid, row in rows.items()
            if row != before.get(eid)
            or changed_members.intersection(row.get('conversation_ids') or [])
            or (config.home_enabled() and not claimed['state'].get('home_rows_ready'))
        }
        homes, views = {}, {}
        active = [row for row in changed.values() if not row.get('recorded_merged_into')]
        members = (
            home_read.read_members(uid, active, firestore_client=client) if active and config.home_enabled() else {}
        )
        for eid, row in changed.items():
            if config.home_enabled() and not row.get('recorded_merged_into'):
                homes[eid] = home_read.project_episode(uid, row, members=members, list_row=True)
            # Home rows carry only server-filtered wire data, sealed per UID.
            # Fingerprint/receipt decisions remain the existing composer's job.
            view = episodes.seal(uid, row)
            view['home_payload'] = encrypt(dumps(homes.get(eid)), uid) if config.home_enabled() else None
            view['home_policy_version'] = digest(
                {
                    key: os.getenv(key)
                    for key in (
                        'HOME_HIDE_BELOW_FLOOR_ROWS',
                        'HOME_NEUTRAL_MINIMUM_TITLES',
                        'HOME_HIDE_EPISODE_MEMBERS',
                    )
                }
            )
            view['compose_dirty'] = bool(
                row.get('status') == 'closed'
                and not row.get('recorded_merged_into')
                and (
                    not row.get('composed_fingerprint')
                    or row.get('summary_needs_regeneration')
                    or changed_members.intersection(row.get('conversation_ids') or [])
                    or any(
                        row.get(field) != before.get(eid, {}).get(field)
                        for field in ('recorded_members', 'conversation_ids', 'discarded_conversation_ids')
                    )
                )
            )
            views[eid] = view
        links = {cid: link for cid, link in fold.links.items() if old_links.get(cid) != link}
        clock = None
        if config.home_enabled():
            refreshed = {cid for row in active for cid in row.get('conversation_ids') or []}
            clock = home_clock(rows, members, claimed['state'].get('home_member_clocks') or {}, refreshed, now)
        result = store.publish(
            uid,
            claimed,
            cursor,
            fold.checkpoint(),
            views,
            links,
            firestore_client=client,
            now=fixed_now or datetime.now(timezone.utc),
            home_clock=clock,
        )
        metrics.observe_state(claimed['state'], 'running', datetime.now(timezone.utc))
        # Never redrain a committed batch just because an observational read fails.
        outcome = 'drained'
        try:
            compare_rows(uid, changed, homes, client, cursor=cursor)
        except Exception as error:
            logger.warning('event=episode_view_compare outcome=error exception_type=%s', type(error).__name__)
        if result.get('scan_at'):
            wake(uid, result['scan_at'])
        return outcome
    except store.LostLease:
        outcome = 'lost_lease'
        return outcome
    except Exception:
        metrics.observe_state(claimed['state'], 'running', fixed_now or datetime.now(timezone.utc))
        store.retry(uid, claimed, firestore_client=client, now=fixed_now or datetime.now(timezone.utc))
        raise
    finally:
        metrics.DRAIN.labels(outcome=outcome).inc()
        metrics.SECONDS.labels(outcome=outcome).observe(time.monotonic() - started)


def sweep(*, firestore_client=None, now=None):
    now = now or datetime.now(timezone.utc)
    client = firestore_client if firestore_client is not None else get_firestore_client()
    if not config.default_on('EPISODES_LOG_ENABLED'):
        metrics.SWEEP_OBSERVED.set(time.time())  # A deliberate kill is not a stale scheduler.
        return {'disabled': 1}
    outcomes = {'scanned': 0, 'redriven': 0, 'error': 0}
    for uid, state in store.due_owners(now, firestore_client=client):
        outcomes['scanned'] += 1
        try:
            if not store.redrive_scan(uid, state, firestore_client=client, now=now) or not config.enabled(uid):
                continue
            phase = 'running' if state.get('lease_owner') else store.derive_phase(state, now)
            metrics.observe_state(state, phase, now)
            store.recover_policy_barriers(uid, firestore_client=client, now=now)
            wake(uid, now)
            outcomes['redriven'] += 1
        except Exception as error:
            outcomes['error'] += 1
            logger.warning('event=episode_log_sweep outcome=error exception_type=%s', type(error).__name__)
    metrics.SWEEP_OBSERVED.set(time.time())
    return outcomes


def sample_read(uid, rows, *, firestore_client=None):
    if not config.enabled(uid) or random.random() >= 0.01:
        return
    client = firestore_client if firestore_client is not None else get_firestore_client()
    try:
        state = store.state(uid, firestore_client=client)
        token = _comparison_token(state)
        if not state.get('backfill_complete') or token is None:
            metrics.COMPARE_SKIPPED.labels(reason='unready_sample').inc()
            return
        views, homes = {}, {}
        for row in rows[:3]:
            snapshot = store.root(client, uid).collection('episode_views').document(row['id']).get().to_dict()
            view = episodes.unseal(uid, snapshot)
            views[row['id']] = view
            if config.home_enabled() and view is not None and snapshot.get('home_payload'):
                homes[row['id']] = loads(decrypt(snapshot['home_payload'], uid))
        compare_rows(uid, views, homes, client, cursor=token[0])
    except Exception as error:
        logger.warning('event=episode_view_sample outcome=error exception_type=%s', type(error).__name__)
