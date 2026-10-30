"""Canonical partition of newly recorded historical components.

All facts are recorded intervals, persisted alongside the episode metadata.
Repartitioning a new historical component when an earlier prefix arrives makes
its four-hour cuts independent of delivery order. Existing live/user/calendar
boundaries are immutable fences and keep the established attachment path.
"""

from datetime import timedelta
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from google.cloud import firestore

from config.recorded_time_tolerances import CLOSE_GAP_SECONDS, MAX_EPISODE_SECONDS
from database._client import run_transactional
from database import episodes


def _automatic(row):
    return (
        row.get('recorded_members') is not None
        and not row.get('discarded_conversation_ids')
        and row.get('status') == 'closed'
        and row.get('close_reason') in {'gap', 'idle', 'hard_cap'}
    )


def _connected(row, start, end):
    return (
        max(0, (start - row['last_activity_at']).total_seconds(), (row['started_at'] - end).total_seconds())
        < CLOSE_GAP_SECONDS
    )


def partition(uid, facts):
    """Pure canonical components and half-open cap windows, in recorded order."""
    groups = []
    for cid, fact in sorted(facts.items(), key=lambda pair: (pair[1]['start'], pair[1]['end'], pair[0])):
        if not groups or (fact['start'] - groups[-1][1]).total_seconds() >= CLOSE_GAP_SECONDS:
            groups.append([fact['start'], fact['end'], [cid]])
        else:
            groups[-1][1] = max(groups[-1][1], fact['end'])
            groups[-1][2].append(cid)
    windows = []
    for _, _, ids in groups:
        remaining = list(ids)
        while remaining:
            # The crossing capture remains in its starting window. Its tail
            # cannot open a successor or supply a successor member's clock.
            cursor = min(facts[cid]['start'] for cid in remaining)
            cap = cursor + timedelta(seconds=MAX_EPISODE_SECONDS)
            members = [cid for cid in remaining if facts[cid]['start'] < cap]
            remaining = [cid for cid in remaining if cid not in members]
            member_end = max(facts[cid]['end'] for cid in members)
            stop = min(member_end, cap)
            windows.append(
                {
                    'id': str(uuid5(NAMESPACE_URL, f'recorded-window:{uid}:{cursor.isoformat()}')),
                    'started_at': cursor,
                    'last_activity_at': stop,
                    'conversation_ids': sorted(members),
                    'close_reason': 'hard_cap' if member_end > stop or remaining else 'gap',
                }
            )
    return windows


def _state(template, window, previous, facts):
    overlapping = [
        row
        for row in previous
        if row['started_at'] <= window['last_activity_at'] and row['last_activity_at'] >= window['started_at']
    ]
    exact = next((row for row in previous if row['id'] == window['id']), None)
    result: dict[str, Any] = {
        **template,
        **(exact or {}),
        **window,
        'status': 'closed',
        'closed_at': window['last_activity_at'],
        'recorded_end': window['last_activity_at'],
        'member_activity': {
            cid: min(facts[cid]['end'], window['last_activity_at']) for cid in window['conversation_ids']
        },
        'state_version': int((exact or {}).get('state_version') or 0) + 1,
    }
    members = window['conversation_ids']
    result['recorded_members'] = {cid: facts[cid] for cid in members}
    if result.get('primary_conversation_id') not in members:
        result['primary_conversation_id'] = members[0] if members else None
    result['sources'] = sorted({facts[cid]['source'] for cid in members if facts[cid].get('source')})
    result['recovered_conversation_ids'] = sorted(
        {cid for row in overlapping for cid in row.get('recovered_conversation_ids') or [] if cid in members}
    )
    result['parallel_content_spans'] = {
        cid: at
        for row in overlapping
        for cid, at in (row.get('parallel_content_spans') or {}).items()
        if cid in members
    }
    for field in ('bullets', 'people', 'open_questions'):
        result[field] = list(dict.fromkeys(value for row in overlapping for value in row.get(field) or []))
    if not result.get('title'):
        result['title'] = next((row['title'] for row in overlapping if row.get('title')), '')
    for field in ('moments', 'provisional_items'):
        selected = {}
        for row in overlapping:
            for item in row.get(field) or []:
                cid = item.get('conversation_id')
                if cid not in members or not item.get('id'):
                    continue
                at = item.get('started_at')
                if at is None:
                    offset = item.get('segment_offset')
                    at = (
                        facts[cid]['start'] + timedelta(seconds=offset)
                        if isinstance(offset, (int, float))
                        else row['started_at']
                    )
                from utils.episodes.policy import utc

                at = utc(at)
                inside = at is not None and (
                    window['started_at'] < at <= window['last_activity_at']
                    if field == 'provisional_items'
                    else window['started_at'] <= at < window['last_activity_at']
                )
                if inside:
                    selected[item['id']] = item
        result[field] = list(selected.values())
    for field in ('applied', 'applied_segment_ids'):
        result[field] = {
            cid: value for row in overlapping for cid, value in (row.get(field) or {}).items() if cid in members
        }
    from config.episodes import MAX_MOMENTS

    if len(result['moments']) > MAX_MOMENTS:
        raise episodes.EpisodeConflict('recorded_compaction_capacity')
    return result


def attach(uid, cid, source, start, end, *, candidates, template, choose, firestore_client, page_limit):
    """One fenced transaction, or None when an established boundary owns intake."""
    client = firestore_client
    root = client.collection('users').document(uid)
    collection = root.collection('episodes')
    fence = root.collection('episode_links').document('recorded_timeline')

    @firestore.transactional
    def commit(transaction):
        fence_row = fence.get(transaction=transaction).to_dict() or {}
        linked = root.collection('episode_links').document(cid).get(transaction=transaction).to_dict() or {}
        if linked.get('episode_id'):
            owner = collection.document(linked['episode_id']).get(transaction=transaction).to_dict() or {}
            if not _automatic(owner):
                return None
        facts = {cid: {'start': start, 'end': end, 'source': source}}
        previous = {}
        lo, hi = start, end
        while True:
            rows = [
                row
                for row in candidates(uid, lo, hi, firestore_client=client, transaction=transaction)
                if not row.get('recorded_merged_into')
            ]
            fixed = [row for row in rows if not _automatic(row)]
            if choose(fixed, start, end) is not None or choose(fixed, start, start) is not None:
                return None
            added = False
            for row in rows:
                if not _automatic(row) or row['id'] in previous or not _connected(row, lo, hi):
                    continue
                full = episodes.unseal(uid, collection.document(row['id']).get(transaction=transaction).to_dict())
                if full is None:
                    raise episodes.EpisodeConflict('recorded_owner_missing')
                previous[row['id']] = full
                for member, fact in full['recorded_members'].items():
                    old = facts.get(member)
                    facts[member] = {
                        **fact,
                        'start': min(fact['start'], old['start']) if old else fact['start'],
                        'end': max(fact['end'], old['end']) if old else fact['end'],
                    }
                lo, hi = min(f['start'] for f in facts.values()), max(f['end'] for f in facts.values())
                added = True
            if not added:
                break
        # A fixed boundary anywhere inside the expanded component is a fence.
        if any(_connected(row, lo, hi) for row in fixed):
            return None
        windows = partition(uid, facts)
        if len(windows) > page_limit:
            raise episodes.EpisodeConflict('recorded_capture_window_exhausted')
        targets = {}
        for window in windows:
            # A discard can advance a fixed episode's start without changing
            # its original deterministic ID. Never reuse that occupied ID (or
            # a redirect) for a disconnected component at the former start.
            for attempt in range(page_limit):
                target = collection.document(window['id']).get(transaction=transaction).to_dict() or {}
                if not target or window['id'] in previous:
                    targets[window['id']] = target
                    break
                window['id'] = str(
                    uuid5(
                        NAMESPACE_URL,
                        f"recorded-window-displaced:{uid}:{window['started_at'].isoformat()}:{attempt}",
                    )
                )
            else:
                raise episodes.EpisodeConflict('recorded_window_id_exhausted')
        members: dict[str, tuple[bool, dict[str, Any]]] = {}
        member_ids = sorted(facts)
        # A connected component may contain many short captures. Keep each
        # membership read bounded, with every chunk in the transaction's read phase.
        for index in range(0, len(member_ids), episodes.MEMBERSHIP_BATCH_LIMIT):
            chunk = member_ids[index : index + episodes.MEMBERSHIP_BATCH_LIMIT]
            members.update(episodes.read_memberships(transaction, client, uid, chunk, admit_conversation_id=cid))
        result = [_state(template, window, list(previous.values()), facts) for window in windows]
        for row in result:
            row['state_version'] = max(row['state_version'], int(targets[row['id']].get('state_version') or 0) + 1)
        new_ids = {row['id'] for row in result}
        assignments = {member: [row['id'] for row in result if member in row['conversation_ids']] for member in members}
        if any(not ids for ids in assignments.values()):
            raise episodes.EpisodeConflict('recorded_member_unassigned')
        for row in previous.values():
            if row['id'] not in new_ids:
                owner = next(
                    (w for w in result if w['started_at'] <= row['started_at'] < w['last_activity_at']), result[-1]
                )
                transaction.update(
                    collection.document(row['id']),
                    {'recorded_merged_into': owner['id'], 'state_version': int(row.get('state_version') or 0) + 1},
                )
        for row in result:
            transaction.set(collection.document(row['id']), episodes.seal(uid, row))
        for member, (exists, old) in members.items():
            assigned = assignments[member]
            retained = [eid for eid in old.get('episode_ids') or [] if eid not in previous and eid not in new_ids]
            transaction.set(
                root.collection('episode_links').document(member),
                {
                    'episode_id': assigned[-1],
                    'episode_ids': list(dict.fromkeys([*retained, *assigned])),
                    'updated_at': template.get('created_at'),
                },
            )
            if exists:
                transaction.update(root.collection('conversations').document(member), {'episode_id': assigned[-1]})
        transaction.set(fence, {'version': int(fence_row.get('version') or 0) + 1})
        incoming = [row for row in result if cid in row['conversation_ids']]
        return {**incoming[-1], '_recorded_windows': incoming}

    return run_transactional(client, commit, transient=True)
