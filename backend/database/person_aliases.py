"""Stable person rename and bounded exact-alias retention."""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import os
import pickle
import threading

from config.firestore_read_levers import lever_enabled
from database import chat_edits
from database.people_generation import bump_people_generation, read_people_generation
from typing import Any, Optional

from google.api_core.exceptions import NotFound
from google.cloud.firestore_v1 import FieldFilter, transactional
from utils.speakers import auto_enroll
from utils.observability.fallback import record_fallback


class _PeopleScanMemo:
    def __init__(self, parent):
        self.parent = parent
        self.entries = {}
        self.bytes_used = 0
        self.generation = 0
        self.writers = 0
        self.active = True
        self.client = None
        self.lock = threading.RLock()
        self.max_entries = _memo_bound('FIRESTORE_PEOPLE_SCAN_MEMO_MAX_ENTRIES', 256)
        self.max_bytes = _memo_bound('FIRESTORE_PEOPLE_SCAN_MEMO_MAX_BYTES', 2 * 1024 * 1024)

    def clear(self):
        self.entries.clear()
        self.bytes_used = 0
        self.generation += 1


def _memo_bound(name: str, default: int) -> int:
    try:
        # Zero disables admission; invalid config retains the documented default.
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        return default


_people_scan_memo: ContextVar[_PeopleScanMemo | None] = ContextVar('people_scan_attempt', default=None)


@contextmanager
def people_scan_attempt():
    """Explicitly bound raw People reuse to ONE sync task attempt.

    The integrator must enter/exit this at the attempt boundary, including retries,
    errors and cancellation. There is no implicit request, thread, TTL or UID cache.
    Inherited executor contexts become inactive when this scope exits. A new attempt
    MUST enter a new scope, even when its Python context was copied from another.
    Nested attempts are isolated; invalidate parent snapshots when returning.
    """
    memo = _PeopleScanMemo(_people_scan_memo.get())
    token = _people_scan_memo.set(memo)
    try:
        yield
    finally:
        with memo.lock:
            memo.active = False
            memo.clear()
            memo.client = None
        _people_scan_memo.reset(token)
        _invalidate_people_scans()


def _invalidate_people_scans():
    # Clearing every UID is deliberately conservative. Also invalidate ancestors
    # when a nested attempt writes; never restore a parent's pre-write snapshot.
    memo = _people_scan_memo.get()
    while memo is not None:
        with memo.lock:
            memo.clear()
        memo = memo.parent


@contextmanager
def _people_write():
    # Fence both sides of commit (including an uncertain/failed commit), and do
    # not admit/hit snapshots while another context-propagated worker is writing.
    memos = []
    memo = _people_scan_memo.get()
    while memo is not None:
        with memo.lock:
            memo.clear()
            memo.writers += 1
        memos.append(memo)
        memo = memo.parent
    try:
        yield
    finally:
        for memo in memos:
            with memo.lock:
                memo.clear()
                memo.writers -= 1


def normalized_person_alias(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = ' '.join(value.split()).strip()
    if not normalized or len(normalized) > 128:
        return None
    return normalized


@transactional
def update_person_name_transaction(
    transaction: Any, person_ref: Any, name: str, expected_chat_state: dict | None = None
) -> bool:
    """Rename one stable person while retaining bounded exact aliases."""

    snapshot = person_ref.get(transaction=transaction)
    if not snapshot.exists:
        return False
    raw = snapshot.to_dict()
    data = raw if isinstance(raw, dict) else {}
    if expected_chat_state is not None:
        fields = {key: data[key] for key in chat_edits.FIELDS['person'] if key in data}
        if chat_edits.encode(fields) != expected_chat_state['before']:
            raise PermissionError('Person changed before rename')
    normalized_name = normalized_person_alias(name)
    if normalized_name is None:
        return False

    aliases: list[str] = []
    seen: set[str] = {normalized_name.casefold()}
    stored_aliases = data.get('aliases')
    if isinstance(stored_aliases, list):
        for value in stored_aliases:
            alias = normalized_person_alias(value)
            if alias is None or alias.casefold() in seen:
                continue
            seen.add(alias.casefold())
            aliases.append(alias)
    prior_name = normalized_person_alias(data.get('name'))
    if prior_name is not None and prior_name.casefold() not in seen:
        aliases.append(prior_name)
    patch = {
        'name': normalized_name,
        'aliases': aliases[-24:],
        'updated_at': datetime.now(timezone.utc),
        'is_user_created': True,
    }
    _invalidate_people_scans()
    transaction.update(person_ref, patch)
    bump_people_generation(transaction, person_ref)
    if expected_chat_state is not None:
        expected_chat_state['after'] = chat_edits.encode(patch)
    return True


def rename_person_retaining_aliases(
    db_client: Any, uid: str, person_id: str, name: str, *, expected_chat_state: dict | None = None
) -> bool:
    """Rename an owner-scoped person and map concurrent deletion to missing."""

    person_ref = db_client.collection('users').document(uid).collection('people').document(person_id)
    with _people_write():
        try:
            if expected_chat_state is not None:
                return update_person_name_transaction(db_client.transaction(), person_ref, name, expected_chat_state)
            return update_person_name_transaction(db_client.transaction(), person_ref, name)
        except NotFound:
            return False


@transactional
def dismiss_person_transaction(transaction: Any, person_ref: Any) -> bool:
    """Soft-dismiss one person while preserving its history and voice data."""

    snapshot = person_ref.get(transaction=transaction)
    if not snapshot.exists:
        return False
    raw = snapshot.to_dict()
    data = raw if isinstance(raw, dict) else {}
    has_pool = isinstance(data.get(auto_enroll.POOL_FIELD), str)
    if data.get('is_dismissed') is True and not has_pool:
        return True
    authority_change = None
    if has_pool:
        owner_ref = person_ref.parent.parent
        owner = owner_ref.get(transaction=transaction)
        if owner.exists:
            authority_change = (owner_ref, auto_enroll.authority_after(owner.to_dict() or {}, {person_ref.id: None}))
    if data.get('is_dismissed') is True:
        if authority_change is not None:
            transaction.update(*authority_change)
        return True
    now = datetime.now(timezone.utc)
    _invalidate_people_scans()
    if authority_change is not None:
        transaction.update(*authority_change)
    transaction.update(
        person_ref,
        {
            'is_dismissed': True,
            'dismissed_at': data.get('dismissed_at') or now,
            'updated_at': now,
        },
    )
    bump_people_generation(transaction, person_ref)
    return True


def dismiss_person_soft(db_client: Any, uid: str, person_id: str) -> bool:
    """Soft-dismiss an owner-scoped person and map concurrent deletion to missing."""

    person_ref = db_client.collection('users').document(uid).collection('people').document(person_id)
    with _people_write():
        try:
            return dismiss_person_transaction(db_client.transaction(), person_ref)
        except NotFound:
            return False


def list_people(
    db_client: Any,
    uid: str,
    *,
    include_dismissed: bool = False,
    limit: Optional[int] = None,
    memoize: bool = False,
) -> list[dict[str, Any]]:
    """List people; only audited, read-only context callers may opt into reuse.

    Learning/entitlement authority, privacy, destructive and mutation-adjacent
    callers MUST keep memoize=False (the default). Complete/dismissed exports
    always read live. Stored bytes contain only this raw result, never a learning
    projection. Each hit decodes its own copy, preserving Firestore value types.
    """
    memo = _people_scan_memo.get()
    key = (uid, include_dismissed, limit)
    generation = None
    people_generation = None
    if memo is not None:
        if memoize and not include_dismissed and lever_enabled('people_scan_dedupe', uid):
            with memo.lock:
                if memo.active and not memo.writers and (memo.client is None or memo.client is db_client):
                    memo.client = db_client
                    generation = memo.generation
                    entry = memo.entries.get(key)
                    # Capture BEFORE the scan, never after: a write during a fill
                    # must retire that fill on the next hit. Hits cost one lookup.
                    try:
                        people_generation = read_people_generation(db_client, uid)
                    except Exception:
                        record_fallback(
                            component='other',
                            from_mode='cached',
                            to_mode='uncached',
                            reason='dependency_unavailable',
                            outcome='recovered',
                        )
                    if entry is not None:
                        stored_generation, payload = entry
                        if people_generation is not None and stored_generation == people_generation:
                            try:
                                # Only deserialize bytes produced here, never external data.
                                return pickle.loads(payload)
                            except Exception:
                                pass
                        memo.clear()
                        generation = memo.generation
        else:
            # A live authority read must not leave an older hint snapshot usable.
            _invalidate_people_scans()

    people_ref = db_client.collection('users').document(uid).collection('people')
    if limit is not None:
        people_ref = people_ref.limit(limit)
    result = []
    for person in people_ref.stream():
        data = person.to_dict()
        if not include_dismissed and data.get('is_dismissed') is True:
            continue
        data.setdefault('id', person.id)
        result.append(data)
    if memo is not None and generation is not None and people_generation is not None:
        try:
            payload = pickle.dumps(result, protocol=pickle.HIGHEST_PROTOCOL)
            # Payload+key bytes bounded separately from <= max_entries metadata.
            size = len(payload) + len(uid.encode('utf-8')) + 64
            with memo.lock:
                if (
                    memo.active
                    and not memo.writers
                    and memo.generation == generation
                    and key not in memo.entries
                    and len(memo.entries) < memo.max_entries
                    and memo.bytes_used + size <= memo.max_bytes
                ):
                    memo.entries[key] = (people_generation, payload)
                    memo.bytes_used += size
        except Exception:
            # Unsupported raw values disable reuse, never change read semantics.
            pass
    return result


def find_person_by_name(db_client: Any, uid: str, name: str) -> dict[str, Any] | None:
    """Find the first active owner-scoped person with this display name, ignoring case.

    An exact match costs one indexed query. Firestore has no case-insensitive equality,
    so only a miss scans the owner's people, comparing names the way renames dedupe aliases.
    """

    people_ref = db_client.collection('users').document(uid).collection('people')
    query = people_ref.where(filter=FieldFilter('name', '==', name))
    for person in query.stream():
        data = person.to_dict()
        if data.get('is_dismissed') is True:
            continue
        data.setdefault('id', person.id)
        return data
    wanted = normalized_person_alias(name)
    if wanted is None:
        return None
    folded = wanted.casefold()
    for data in list_people(db_client, uid):
        stored = normalized_person_alias(data.get('name'))
        if stored is not None and stored.casefold() == folded:
            return data
    return None
