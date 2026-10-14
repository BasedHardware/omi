"""Bounded read-only seed: no intake, migration, materialization or control writes."""

from typing import Any

from database import dream_history, dream_store, review_store, users
from config.dream_session import SessionLimits
from utils.dream_context import EvidenceRecords
from utils.dream_session import serialized_bytes
from utils.dream_reads import read_record


def load(uid, caps):
    size = sum(dream_history.history_count(uid, collection) for collection in dream_history.COLLECTIONS)
    limits = SessionLimits.for_size(size, token_ceiling=caps.tokens, edit_ceiling=caps.edits)
    profile = users.get_user_profile(uid)
    seed: dict[str, Any] = {
        'profile': {
            key: str(profile[key])[:500]
            for key in ('name', 'given_name', 'family_name', 'language', 'timezone')
            if key in profile
        },
        'vocabulary': [],
        'confirmed_people': [],
        'targets': [],
        'recent_feedback': [],
        'previous_notes': '',
    }
    ceiling = 8000 if limits.bucket in {'empty', 'light'} else 24000

    def append(key, value):
        seed[key].append(value)
        if serialized_bytes(seed) > ceiling:
            seed[key].pop()
            return False
        return True

    for term in dream_store.vocabulary(uid)[:500]:
        if not append('vocabulary', term):
            break
    people = review_store.user(uid).collection('people')
    # Read a bounded projected page, never every person's voice embedding.
    for snapshot in (
        people.order_by('__name__')
        .select(['name', 'user_confirmed', 'is_user_created', 'is_dismissed'])
        .limit(32)
        .stream()
    ):
        row = snapshot.to_dict() or {}
        if not row.get('is_dismissed') and (row.get('user_confirmed') or row.get('is_user_created')):
            append('confirmed_people', {'ref': 'people/' + snapshot.id, 'name': row.get('name', '')})
    dirty = [snapshot.to_dict() for snapshot in dream_store.dirty_refs(uid, limit=32, newest=False)]
    for item in dirty:
        append('targets', item['collection'] + '/' + item['id'])
    changes = (
        review_store.user(uid).collection('review_changes').order_by('created_at', direction='DESCENDING').limit(5)
    )
    for snapshot in changes.stream():
        row = review_store.decode_doc(uid, snapshot.to_dict()) or {}
        if (row.get('change') or {}).get('undone'):
            change = row.get('change') or {}
            append(
                'recent_feedback',
                {
                    'kind': change.get('edit_kind') or change.get('kind'),
                    'undone': True,
                    'before': change.get('before'),
                    'after': change.get('after'),
                },
            )
    for _, raw in dream_store.own_runs(uid, limit=1):
        source = (review_store.decode_doc(uid, raw) or {}).get('source') or {}
        notes = source.get('notes')
        if isinstance(notes, str) and len(notes) <= 2000:
            seed['previous_notes'] = notes
    records = EvidenceRecords()
    initial = 2 if limits.bucket in {'empty', 'light'} else 4 if limits.bucket == 'medium' else 8
    for ref in seed['targets'][:initial]:
        try:
            row = read_record(uid, ref)
            if row and serialized_bytes(records) + serialized_bytes({ref: row}) <= min(16000, limits.read_bytes // 4):
                records[ref] = row
        except Exception:
            # Search/read tools explicitly retry unavailable sources; never
            # acknowledge an unread dirty version from seed construction.
            continue
    return seed, records, dirty, limits
