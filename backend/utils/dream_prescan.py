"""Deterministic no-LLM pre-scan: hand hunt passes concrete cleanup targets.

69% of completed passes apply nothing because hunts (passes with no dirty work)
explore from scratch. This scan reads only bounded projected metadata — never
decrypted content — and returns candidate cleanup refs for the people and task
signals the cleanup edits already validate. It measures recall in shadow and,
for a served cohort, puts its refs in front of the seed targets. It must never
skip or fail a pass: every error returns an empty scan.
"""

import logging
import re
import unicodedata
from difflib import SequenceMatcher

from google.cloud import firestore

from database import review_store
from models.agent_refs import canonical_ref
from utils.agent_capabilities.cleanup_edits import require_generated_task, require_unprotected_person
from utils.agent_capabilities.session import serialized_bytes
from utils import dream_seed

logger = logging.getLogger(__name__)

# Bounds mirror the seed's projected pages; only this scan pages this deep.
PEOPLE_LIMIT = 500
TASK_LIMIT = 300
MAX_REFS = 16
TASK_DUPLICATE_RATIO = 0.85
# Edit distance only distinguishes real re-spellings on longer names.
EDIT_DISTANCE_MIN_CHARS = 5
# Bound difflib work on pathological same-group groups; equality was deduped first.
MAX_TEXT_COMPARISONS = 2000
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

EMPTY_COUNTS = {'people_dupes': 0, 'junk_names': 0, 'task_dupes': 0}


def _client(firestore_client=None):
    return firestore_client if firestore_client is not None else review_store.client()


def normalized_name(value):
    """Casefolded name with punctuation replaced and diacritics stripped."""
    if not isinstance(value, str):
        return ''
    decomposed = unicodedata.normalize('NFKD', value)
    without_diacritics = ''.join(char for char in decomposed if not unicodedata.combining(char))
    return ' '.join(''.join(char if char.isalnum() else ' ' for char in without_diacritics.casefold()).split())


def _name_keys(row):
    keys = set()
    name = normalized_name(row.get('name'))
    if name:
        keys.add(name)
    aliases = row.get('aliases') if isinstance(row.get('aliases'), list) else []
    for alias in aliases:
        normalized = normalized_name(alias)
        if normalized:
            keys.add(normalized)
    return keys


def within_one(left, right):
    """True when the strings differ by at most one edit."""
    if left == right:
        return True
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        differences = 0
        for a, b in zip(left, right):
            if a != b:
                differences += 1
                if differences > 1:
                    return False
        return True
    if len(left) > len(right):
        left, right = right, left
    index = 0
    while index < len(left) and left[index] == right[index]:
        index += 1
    return left[index:] == right[index + 1 :]


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


def _scan_people(uid, firestore_client):
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


def _duplicate_people(candidates):
    """Refs of unprotected people tied by equal normalized names/aliases or one edit."""
    by_key = {}
    names = []
    for person_id, row in candidates:
        keys = _name_keys(row)
        names.append((person_id, normalized_name(row.get('name'))))
        for key in keys:
            by_key.setdefault(key, []).append(person_id)
    parent = {person_id: person_id for person_id, _ in candidates}

    def find(item):
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left, right):
        left, right = find(left), find(right)
        if left != right:
            parent[right] = left

    for ids in by_key.values():
        for other in ids[1:]:
            union(ids[0], other)
    # Edit distance works on names only, bucketed by length so pairs differ by
    # at most one edit; equal names already merged above.
    by_length = {}
    for person_id, name in names:
        if len(name) >= EDIT_DISTANCE_MIN_CHARS:
            by_length.setdefault(len(name), []).append((person_id, name))
    for length, same in by_length.items():
        for index, (left_id, left) in enumerate(same):
            for right_id, right in same[index + 1 :]:
                if within_one(left, right):
                    union(left_id, right_id)
        for left_id, left in same:
            for right_id, right in by_length.get(length + 1, ()):
                if within_one(left, right):
                    union(left_id, right_id)
    sizes = {}
    for person_id, _ in candidates:
        root = find(person_id)
        sizes[root] = sizes.get(root, 0) + 1
    return ['people/' + person_id for person_id, _ in candidates if sizes[find(person_id)] > 1]


def _scan_tasks(uid, firestore_client):
    """Refs of active generated tasks grouped by merge metadata with near-equal text."""
    tasks = _client(firestore_client).collection('users').document(uid).collection('action_items')
    rows = (
        tasks.where(filter=firestore.FieldFilter('source', '==', 'conversation'))
        .select(list(TASK_FIELDS))
        .limit(TASK_LIMIT)
        .stream()
    )
    groups = {}
    for snapshot in rows:
        row = snapshot.to_dict() or {}
        try:
            require_generated_task(row)
        except ValueError:
            continue
        groups.setdefault((row.get('due_at'), row.get('owner'), row.get('account_generation')), []).append(
            ('action_items/' + snapshot.id, str(row.get('description') or ''))
        )
    comparisons = 0
    dupes = []
    for members in groups.values():
        if len(members) < 2:
            continue
        texts = {}
        for ref, description in members:
            texts.setdefault(description, []).append(ref)
        distinct = list(texts)
        duplicate_refs = [ref for refs in texts.values() if len(refs) > 1 for ref in refs]
        for index, left in enumerate(distinct):
            if comparisons >= MAX_TEXT_COMPARISONS:
                break
            for right in distinct[index + 1 :]:
                if comparisons >= MAX_TEXT_COMPARISONS:
                    break
                comparisons += 1
                if SequenceMatcher(None, left, right, autojunk=True).ratio() >= TASK_DUPLICATE_RATIO:
                    duplicate_refs.extend(texts[right])
                    duplicate_refs.extend(texts[left])
        if duplicate_refs:
            dupes.extend(sorted(set(duplicate_refs)))
    return dupes


def scan(uid, *, firestore_client=None) -> dict:
    """Bounded projected cleanup candidates: ``refs`` (ordered, <= MAX_REFS) and per-signal counts.

    Fails open: any error logs one ``dream_lever_error`` line and returns an empty scan.
    """
    try:
        candidates, junk = _scan_people(uid, firestore_client)
        dupes = _duplicate_people(candidates)
        tasks = _scan_tasks(uid, firestore_client)
        counts = {'people_dupes': len(dupes), 'junk_names': len(junk), 'task_dupes': len(tasks)}
        # Dismiss candidates first: junk dismissals dominate applied cleanup today.
        ordered, seen = [], set()
        for signal in (junk, dupes, tasks):
            for ref in signal:
                if ref not in seen:
                    seen.add(ref)
                    ordered.append(canonical_ref(ref))
        return {'refs': ordered[:MAX_REFS], 'counts': counts}
    except Exception as error:
        logger.warning('event=dream_lever_error lever=prescan exc=%s', type(error).__name__)
        return {'refs': [], 'counts': dict(EMPTY_COUNTS)}


def serve_targets(seed, refs, limits) -> int:
    """Serve arm: put scan refs first in the seed targets, inside the seed byte ceiling.

    Dirty targets are never removed; only the prepended refs are dropped when the
    serialized seed would exceed ``dream_seed.byte_ceiling``. Returns refs served.
    """
    try:
        existing = list(seed.get('targets') or [])
        fresh, seen = [], set(existing)
        for ref in refs:
            if ref not in seen:
                fresh.append(ref)
                seen.add(ref)
        while fresh and serialized_bytes({**seed, 'targets': fresh + existing}) > dream_seed.byte_ceiling(limits):
            fresh.pop()
        if fresh:
            seed['targets'] = fresh + existing
        return len(fresh)
    except Exception as error:
        logger.warning('event=dream_lever_error lever=prescan exc=%s', type(error).__name__)
        return 0


def applied_hits(report, refs) -> int:
    """Applied outcomes whose staged target is one of the scan refs."""
    wanted = set(refs or [])
    if not wanted:
        return 0
    targets = {
        row.get('key'): (row.get('target') or '').partition('#')[0]
        for rows in (report.get('proposed') or {}).values()
        if isinstance(rows, list)
        for row in rows
        if isinstance(row, dict)
    }
    return sum(
        1
        for row in report.get('outcomes') or []
        if isinstance(row, dict) and row.get('status') == 'applied' and targets.get(row.get('key')) in wanted
    )
