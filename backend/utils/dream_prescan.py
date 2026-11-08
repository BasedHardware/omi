"""Bounded projected people and task metadata shared with the Dream state pass."""

import re
import unicodedata


from database import review_store
from utils.agent_capabilities.cleanup_edits import require_unprotected_person

# Bounds mirror the seed's projected pages; only this scan pages this deep.
PEOPLE_LIMIT = 500
TASK_LIMIT = 300
# Conservative: one built-in common word is not a person name. Keep this small.
COMMON_WORDS = frozenset({'thanks', 'okay', 'yeah', 'hello', 'canadian', 'sorry', 'welcome'})
SPEAKER_LABEL = re.compile(r'^(speaker|person)\s*\d+$')

# Name signal plus the small protected fields. Voice data (speech_samples,
# speaker_embedding) is deliberately not read: 500 embeddings per pass is the bulk
# read the seed avoids. A voiced person can still become a candidate; staging's
# require_unprotected_person rejects it, so the cost is one wasted target, not an edit.
PEOPLE_FIELDS = (
    'name',
    'aliases',
    'is_dismissed',
    'user_confirmed',
    'is_user_created',
    'pinned',
    'label_evidence',
)
# Projection for require_generated_task (source, active rules, protected_donor)
# plus the merge predicate (due_at, owner, account_generation) and description.
TASK_FIELDS = (
    'source',
    'status',
    'completed',
    'deleted',
    'due_at',
    'owner',
    'account_generation',
    'description',
    'folder_id',
    'manual_assignment',
    'apple_reminder_id',
    'external_task_id',
    'goal_id',
    'workstream_id',
    'recurrence_rule',
    'priority',
    'created_at',
    'updated_at',
)


def _client(firestore_client=None):
    return firestore_client if firestore_client is not None else review_store.client()


def normalized_name(value):
    """Casefolded name with punctuation replaced and diacritics stripped."""
    if not isinstance(value, str):
        return ''
    decomposed = unicodedata.normalize('NFKD', value)
    without_diacritics = ''.join(char for char in decomposed if not unicodedata.combining(char))
    return ' '.join(''.join(char if char.isalnum() else ' ' for char in without_diacritics.casefold()).split())


def is_junk_name(name):
    """A name that is clearly not a person name; deliberately conservative."""
    normalized = normalized_name(name)
    compact = normalized.replace(' ', '')
    if len(compact) <= 1:
        return True
    if compact.isdigit():
        return True
    if SPEAKER_LABEL.match(normalized) or normalized == 'unknown':
        return True
    tokens = normalized.split()
    return (
        len(tokens) == 1
        and tokens[0] in COMMON_WORDS
        and isinstance(name, str)
        and name.strip() == name.strip().casefold()
    )


def scan_people(uid, firestore_client):
    """Unprotected, not-dismissed people from one projected, name-ordered page."""
    people = _client(firestore_client).collection('users').document(uid).collection('people')
    rows = [
        (snapshot.id, snapshot.to_dict() or {})
        for snapshot in people.order_by('__name__').select(list(PEOPLE_FIELDS)).limit(PEOPLE_LIMIT).stream()
    ]
    candidates = []
    junk = []
    for person_id, row in rows:
        if row.get('is_dismissed'):
            continue
        try:
            require_unprotected_person(row)
        except ValueError:
            continue
        candidates.append((person_id, row))
        if is_junk_name(row.get('name')):
            junk.append('people/' + person_id)
    return candidates, junk
