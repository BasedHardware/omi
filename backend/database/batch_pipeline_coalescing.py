"""Pre-unit custody transactions. No audio or private upload context in rows.

The quota row bounds the entire held queue, not merely one instance. It is
released only after every original member is bound to admitted work (or purge).
Group/member/source writes recheck live authority in their own transaction.
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from config import batch_pipeline_coalescing as config


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    ).hexdigest()


def authorize(tx, row):
    tx.check_privacy(row['owner_id'], (row['conversation_id'],), row['privacy_generation'])


def enqueue(store, member, key, now):
    """Atomic ownership + runnable custody + per-upload nonterminal receipt.

    None declines a hold before it owns content. Errors are ambiguous and must
    retain the existing retryable response; callers never fall through on error.
    """

    def commit(tx):
        authorize(tx, member)
        prior = tx.get('content', f"{member['owner_id']}/{member['content_id']}")
        if prior:
            return prior.get('job_id')  # A racing legacy owner is not ours to replace.
        head = tx.get('coalesce_heads', key)
        group = tx.get('coalesce_groups', head.get('group_id', 'missing'))
        quota = tx.get('coalesce_quota', 'global')
        owner = member['owner_key']
        join = bool(group and group['state'] == 'holding' and group['release_by'] > now)
        if group and not join and group['state'] != 'done':
            return 'wait'  # Do not overtake a sealed/draining predecessor.
        if not quota or not -5 <= now - quota.get('last_scan_at', 0) <= 5:
            if join:
                group.update(release_by=now, scan_at=now)
                tx.put('coalesce_groups', group['id'], group)
                return 'wait'  # Ordering fence + client custody while the drainer recovers.
            return None  # Unknown/stalled drainer: ordinary admission for a new recording.
        if join and (
            len(group['members']) >= config.MAX_MEMBERS
            or group['bytes'] + member['bytes'] > config.MAX_GROUP_BYTES
            or group['files'] + member['files'] > config.MAX_FILES
            or group['seconds'] + member['seconds'] > config.MAX_AUDIO_SECONDS
            or any(not (member['end'] <= m['start'] or member['start'] >= m['end']) for m in group['members'])
            or set(member['filenames']).intersection(name for m in group['members'] for name in m['filenames'])
        ):
            # Release the older hold rather than silently admit a newer upload
            # ahead of it. The caller retries with local custody intact.
            group['release_by'] = now
            group['scan_at'] = now
            tx.put('coalesce_groups', group['id'], group)
            return 'wait'
        if not join:
            if quota['groups'] >= config.MAX_GROUPS or quota['owners'].get(owner, 0) >= config.MAX_OWNER_GROUPS:
                return None
            group_id = digest([key, member['content_id']])
            group = {k: member[k] for k in ('owner_id', 'owner_key', 'conversation_id', 'privacy_generation')}
            group.update(
                id=group_id,
                key=key,
                state='holding',
                first_accept_at=now,
                release_by=now + member['hold_seconds'],
                scan_at=now + member['hold_seconds'],
                members=[],
                bytes=0,
                files=0,
                seconds=0,
            )
            quota['groups'] += 1
            quota['owners'][owner] = quota['owners'].get(owner, 0) + 1
            tx.put('coalesce_quota', 'global', quota)
            tx.put('coalesce_heads', key, {**group, 'group_id': group_id, 'members': []})
        group['members'].append(member)
        group['bytes'] += member['bytes']
        group['files'] += member['files']
        group['seconds'] += member['seconds']
        tx.put('coalesce_groups', group['id'], group)
        tx.put('coalesce_sources', member['item']['segment_id'], {**member, 'group_id': group['id']})
        tx.put(
            'intakes',
            member['job_id'],
            {**member, 'coalesce_group': group['id'], 'segment_ids': [], 'total_files': member['files']},
        )
        tx.put(
            'content',
            f"{member['owner_id']}/{member['content_id']}",
            {
                'owner_id': member['owner_id'],
                'status': 'processing',
                'dispatch_protocol': 'batch_v1',
                'job_id': member['job_id'],
                'batch_pipeline': {'namespace': store.namespace},
            },
        )
        return member['job_id']

    return store.run(commit)


def claim(store, group_id, now, *, producer_enabled):
    token = uuid4().hex

    def commit(tx):
        row = tx.get('coalesce_groups', group_id)
        if not row or row['state'] == 'done' or row.get('lease_until', 0) > now:
            return None
        authorize(tx, row)
        if row['state'] == 'holding' and producer_enabled and row['release_by'] > now:
            return None
        # Membership becomes immutable before IO. The mode can change from
        # merged to individual only if no merged intake ever committed.
        merged = tx.get('intakes', 'bp_' + digest([row['id'], 'merged']))
        row['members'].sort(key=lambda m: (m['start'], m['content_id']))
        row.update(state='sealed', token=token, lease_until=now + config.LEASE_SECONDS)
        row['scan_at'] = row['lease_until']
        row['mode'] = (
            'individual'
            if row.get('mode') == 'individual'
            else 'merged' if merged or producer_enabled else 'individual'
        )
        tx.put('coalesce_groups', group_id, row)
        return row

    return store.run(commit)


def guard(tx, group, now):
    current = tx.get('coalesce_groups', group['id'])
    if (
        not current
        or current.get('token') != group['token']
        or current['state'] != 'sealed'
        or current.get('lease_until', 0) <= now
        or current['mode'] != group['mode']
    ):
        raise ValueError('coalescing drain lease lost')
    authorize(tx, current)


def release_quota(tx, row):
    if row.get('quota_released'):
        return
    quota = tx.get('coalesce_quota', 'global')
    if not quota or quota['groups'] <= 0 or quota['owners'].get(row['owner_key'], 0) <= 0:
        raise ValueError('coalescing quota custody mismatch')
    quota['groups'] -= 1
    key = row['owner_key']
    quota['owners'][key] -= 1
    if not quota['owners'][key]:
        del quota['owners'][key]
    row['quota_released'] = True
    tx.put('coalesce_quota', 'global', quota)


def finish(store, group, targets, now):
    def commit(tx):
        guard(tx, group, now)
        row = tx.get('coalesce_groups', group['id'])
        # Targets must be real committed intakes; never fan out an HTTP guess.
        for member, target in zip(row['members'], targets):
            intake = tx.get('intakes', target)
            if not intake or not intake.get('segment_ids') or intake['owner_id'] != row['owner_id']:
                raise ValueError('coalescing target intake missing')
            # After conversion, normal unit custody owns every decoded sample.
            # Attach the encrypted original to that same completion-led
            # retention lifecycle; never leave accepted originals orphan-reapable
            # or silently introduce permanent retention for sync-off users.
            from database.batch_pipeline_staging import artifact_id

            source_id = member['item']['segment_id']
            artifact_key = artifact_id(source_id, member['uri'])
            artifact = tx.get('artifacts', artifact_key)
            if not artifact or artifact.get('erasure_requested') or artifact.get('cleanup_after'):
                raise ValueError('coalescing source custody metadata lost')
            artifact['segment_id'] = intake['segment_ids'][-1]
            artifact.pop('write_pending_until', None)
            completed = tx.get('results', artifact['segment_id'])
            if completed.get('expires_at'):
                # A very fast worker may finish before receipt fanout. Native
                # expiry is idempotent, so attach the original's cleanup clock
                # now rather than relying on expiry to run a second time.
                from utils.batch_pipeline.retention import RECEIPT_RETENTION, ARTIFACT_RETENTION

                artifact['cleanup_after'] = completed['expires_at'] - RECEIPT_RETENTION + ARTIFACT_RETENTION
            tx.put('artifacts', artifact_key, artifact)
            source = tx.get('coalesce_sources', source_id)
            source['expires_at'] = datetime.fromtimestamp(now, timezone.utc) + timedelta(days=45)
            tx.put('coalesce_sources', source_id, source)
            if target == member['job_id']:
                continue  # OFF converted the original receipt in-place.
            prior = tx.get('intakes', member['job_id'])
            if prior.get('coalesce_group') != row['id']:
                raise ValueError('coalescing member receipt lost')
            tx.put('intakes', member['job_id'], {**prior, 'coalesce_target': target})
        release_quota(tx, row)
        row.update(state='done', lease_until=0)
        row['expires_at'] = datetime.fromtimestamp(now, timezone.utc) + timedelta(days=45)
        row.pop('scan_at', None)
        tx.put('coalesce_groups', group['id'], row)
        head = tx.get('coalesce_heads', row['key'])
        if head.get('group_id') == row['id']:
            head['expires_at'] = row['expires_at']
            tx.put('coalesce_heads', row['key'], head)

    if len(targets) != len(group['members']):
        raise ValueError('complete coalescing target set required')
    store.run(commit)


def due(client, namespace, now, *, producer_enabled, after=None):
    # Single-field deadline index only; scan bounded even during OFF. Done
    # rows drop this indexed field after fanout and never consume a due page.
    query = client.collection(f'{namespace}_coalesce_groups')
    if producer_enabled:
        query = query.where('scan_at', '<=', now)
    query = query.order_by('scan_at').order_by('__name__')
    if after is not None:
        query = query.start_after(
            {
                'scan_at': after['scan_at'],
                '__name__': client.collection(f'{namespace}_coalesce_groups').document(after['id']),
            }
        )
    return [{'id': doc.id, 'scan_at': doc.to_dict()['scan_at']} for doc in query.limit(config.DRAIN_PAGE).stream()]


def scan_position(store):
    def read(tx):
        quota = tx.get('coalesce_quota', 'global')
        return quota.get('scan_epoch', 0), quota.get('scan_after')

    return store.run(read)


def advance_scan(store, epoch, after):
    """Fair scan progress only; never mutate denied custody or grant processing.

    Advance even for a failed page. A stale concurrent scanner cannot move the
    cursor backwards; a deleted boundary remains usable as a value cursor.
    Empty pages wrap on the next tick. A dark, empty queue creates no row.
    """

    def commit(tx):
        quota = tx.get('coalesce_quota', 'global')
        if not quota or quota.get('scan_epoch', 0) != epoch or quota.get('scan_after') == after:
            return
        quota.update(scan_epoch=epoch + 1, scan_after=after)
        tx.put('coalesce_quota', 'global', quota)

    store.run(commit)


def note_scan(store, now, *, producer_enabled):
    def commit(tx):
        quota = tx.get('coalesce_quota', 'global')
        if not quota and not producer_enabled:
            return  # Default OFF + no accepted holds: no heartbeat writes.
        quota = quota or {'groups': 0, 'owners': {}}
        quota['last_scan_at'] = now
        tx.put('coalesce_quota', 'global', quota)

    store.run(commit)


def release_for_open(store, uid, job_id, now):
    def commit(tx):
        member = tx.get('intakes', job_id)
        if not member or member.get('owner_id') != uid or not member.get('coalesce_group'):
            return False
        authorize(tx, member)
        group = tx.get('coalesce_groups', member['coalesce_group'])
        if group.get('state') == 'holding':
            group['release_by'] = min(now, group['release_by'])
            group['scan_at'] = now
            tx.put('coalesce_groups', group['id'], group)
        return True

    return store.run(commit)


def checkpoint_completion(store, intake, result, now):
    """Arm replay/metadata TTL only after authoritative group completion."""

    def commit(tx):
        current = tx.get('intakes', intake['job_id'])
        authorize(tx, intake)
        content_key = f"{intake['owner_id']}/{intake['content_id']}"
        content = tx.get('content', content_key)
        if current.get('coalesce_target') != intake.get('coalesce_target') or content.get('job_id') != intake['job_id']:
            raise ValueError('coalescing completion identity changed')
        if content.get('status') == 'completed':
            return
        expires = datetime.fromtimestamp(now, timezone.utc) + timedelta(days=45)
        current['expires_at'] = expires
        content.update(status='completed', result=result, expires_at=expires)
        tx.put('intakes', intake['job_id'], current)
        tx.put('content', content_key, content)

    store.run(commit)


def purge_group(client, namespace, group_id, uid, *, fence=None):
    """Erasure already fenced the owner; no processing/privacy allow is needed.

    Only unlink this owner's group and release its quota atomically. Sources
    remain discoverable through the normal erasure outbox until physically gone.
    """
    from google.cloud import firestore

    group_ref = client.collection(f'{namespace}_coalesce_groups').document(group_id)
    quota_ref = client.collection(f'{namespace}_coalesce_quota').document('global')

    @firestore.transactional
    def remove(transaction):
        if fence is not None:
            fence(transaction)
        row = group_ref.get(transaction=transaction).to_dict() or {}
        quota = quota_ref.get(transaction=transaction).to_dict() or {}
        if not row:
            return
        if row.get('owner_id') != uid:
            raise ValueError('coalescing erasure owner mismatch')
        if not row.get('quota_released'):
            key = row['owner_key']
            if quota.get('groups', 0) <= 0 or quota.get('owners', {}).get(key, 0) <= 0:
                raise ValueError('coalescing erasure quota mismatch')
            quota['groups'] -= 1
            quota['owners'][key] -= 1
            if not quota['owners'][key]:
                del quota['owners'][key]
            transaction.set(quota_ref, quota)
        transaction.delete(group_ref)

    remove(client.transaction())
