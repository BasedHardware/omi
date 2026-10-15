"""Bounded read-only seed: no intake, migration, materialization or control writes."""

from typing import Any
from models.person_confidence import evidence_count, MANUAL_LABELS, CARD_CONFIRMS, CARD_PICKS, AUTO_CONFIRMED

from database import dream_history, dream_store, review_store, users
from config.dream_session import SessionLimits
from models.agent_refs import canonical_ref
from utils.agent_capabilities.evidence import EvidenceRecords
from utils.agent_capabilities.session import serialized_bytes
from utils.agent_capabilities.reads import read_record, unavailable_is_transient

# A pile of deleted ids must not walk the dirty queue. Past this many examined
# refs the seed page may be short.
_SEED_SCAN_CAP = 64


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
        .select(['name', 'user_confirmed', 'is_user_created', 'is_dismissed', 'label_evidence', 'pinned'])
        .limit(32)
        .stream()
    ):
        row = snapshot.to_dict() or {}
        confirmed = any(
            evidence_count(row.get('label_evidence') or {}, key)
            for key in (MANUAL_LABELS, CARD_CONFIRMS, CARD_PICKS, AUTO_CONFIRMED)
        )
        if not row.get('is_dismissed') and (
            row.get('user_confirmed') or row.get('is_user_created') or row.get('pinned') or confirmed
        ):
            append('confirmed_people', {'ref': 'people/' + snapshot.id, 'name': row.get('name', '')})
    dirty = [snapshot.to_dict() for snapshot in dream_store.dirty_refs(uid, limit=32, newest=False)]
    readable = []
    unavailable = {}
    for item in dirty[:_SEED_SCAN_CAP]:
        ref = canonical_ref(str(item.get('collection') or '') + '/' + str(item.get('id') or ''))
        try:
            row = read_record(uid, ref)
        except Exception as error:
            # Dead or unreadable dirty ids are not seeds. The session still sees
            # which refs were skipped.
            unavailable[ref] = unavailable_is_transient(error)
            continue
        if row is None:
            unavailable[ref] = False
            continue
        if not append('targets', ref):
            break
        readable.append((ref, row))
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
    for ref, row in readable[:initial]:
        if serialized_bytes(records) + serialized_bytes({ref: row}) <= min(16000, limits.read_bytes // 4):
            records[ref] = row
    seed['unavailable_targets'] = unavailable
    while serialized_bytes(seed) > ceiling:
        if seed['previous_notes']:
            seed['previous_notes'] = seed['previous_notes'][: len(seed['previous_notes']) // 2]
        elif seed['recent_feedback']:
            seed['recent_feedback'].pop()
        elif seed['vocabulary']:
            seed['vocabulary'].pop()
        else:
            raise ValueError('dream_seed_byte_budget')
    return seed, records, dirty, limits
