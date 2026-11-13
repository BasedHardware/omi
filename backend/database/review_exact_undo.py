"""Exact row and generation fences for reversible soft cleanup, never hard deletion."""

import math
from copy import deepcopy

from database import review_store as store
from database.review_field_states import read_field_state


def _as_mapping(value):
    """Return *value* when it is a mapping, otherwise an empty dict."""
    return value if isinstance(value, dict) else {}


def _dotted_parts(path):
    """Split a dotted field path, rejecting non-string and empty segments."""
    if not isinstance(path, str):
        return None
    parts = path.split('.')
    if not parts or any(not part for part in parts):
        return None
    return parts


def _coerce_generation(value):
    """Normalize ``account_generation`` to a non-negative int.

    ``None``, booleans, non-finite floats, non-numeric strings and negative
    numbers all collapse to ``0`` so a malformed fence can never raise
    ``TypeError``/``ValueError`` inside a Firestore transaction.
    """
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value if value >= 0 else 0
    if isinstance(value, float):
        return int(value) if math.isfinite(value) and value >= 0 else 0
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return 0
        try:
            parsed = int(text, 10)
        except ValueError:
            return 0
        return parsed if parsed >= 0 else 0
    return 0


def _apply_dotted(result, parts, value, *, present):
    """Write or drop ``value`` at ``parts`` inside ``result``.

    Intermediate segments that are ``None`` or hold a scalar are replaced with a
    fresh dict, so traversal never raises ``TypeError``/``AttributeError`` on
    documents such as ``{'promotion': None}``.
    """
    parent = result
    for part in parts[:-1]:
        child = parent.get(part)
        if not isinstance(child, dict):
            child = {}
            parent[part] = child
        parent = child
    if present:
        parent[parts[-1]] = deepcopy(value)
    else:
        parent.pop(parts[-1], None)


def patched_row(row, patch):
    result = deepcopy(row)
    if not isinstance(result, dict):
        result = {}
    if not isinstance(patch, dict):
        return result
    for path, value in patch.items():
        parts = _dotted_parts(path)
        if parts is None:
            continue
        _apply_dotted(result, parts, value, present=True)
    return result


def restored_row(row, fields):
    result = deepcopy(row)
    if not isinstance(result, dict):
        result = {}
    if not isinstance(fields, dict):
        return result
    for path, state in fields.items():
        parts = _dotted_parts(path)
        if parts is None or not isinstance(state, dict):
            continue
        _apply_dotted(result, parts, state.get('value'), present=bool(state.get('present')))
    return result


def journal_fences(edits, rows, expected_records, witnesses=None, *, uid=None):
    # The ordinary owned-field journal still performs reversal. Full-row hashes
    # ensure a later user edit cannot be touched by cleanup's Undo/Redo.
    reversal_fences = []
    for edit, _, raw in rows:
        patch_map = edit.patch if isinstance(getattr(edit, 'patch', None), dict) else {}
        safe_raw = _as_mapping(raw)
        reversal_fences.append(
            {
                'collection': getattr(edit, 'collection', None),
                'document_id': getattr(edit, 'document_id', None),
                'fields': list(patch_map),
                'before': {key: read_field_state(safe_raw, key) for key in patch_map},
                'after': {key: read_field_state(patched_row(safe_raw, patch_map), key) for key in patch_map},
            }
        )
    records = _as_mapping(expected_records)
    journal: dict = {
        'reversal_fences': reversal_fences,
        'generation_fences': {
            path: _coerce_generation(_as_mapping(raw).get('account_generation', 0))
            for path, raw in records.items()
            if path == 'task_intelligence_control/state'
        },
    }
    witness_map = _as_mapping(witnesses)
    if witness_map:
        # Redo-only survivor fences for merges: the hidden target points at a
        # survivor this edit never owned, so Redo must verify it is unchanged.
        journal['witness_fences'] = {
            path: witness_snapshot(uid, path, raw) for path, raw in witness_map.items() if raw is not None
        }
    return journal


def validate_generation(uid, tx, journal):
    fences = _as_mapping(journal).get('generation_fences')
    if not isinstance(fences, dict):
        return
    for path, generation in fences.items():
        if not isinstance(path, str) or '/' not in path:
            continue
        collection, key = path.split('/', 1)
        if not collection or not key:
            continue
        current = store.user(uid).collection(collection).document(key).get(transaction=tx).to_dict() or {}
        if _coerce_generation(_as_mapping(current).get('account_generation', 0)) != _coerce_generation(generation):
            raise store.ReviewConflict('Cleanup account generation changed')


def validate_row(journal, collection, key, current, expected):
    fences = _as_mapping(journal).get('reversal_fences')
    if not isinstance(fences, list):
        return False
    fence = next(
        (
            row
            for row in fences
            if isinstance(row, dict) and row.get('collection') == collection and row.get('document_id') == key
        ),
        None,
    )
    if fence is None:
        return False
    if 'fields' in fence:
        names = fence.get('fields')
        observed = {
            name: read_field_state(_as_mapping(current), name)
            for name in (names if isinstance(names, list) else [])
            if isinstance(name, str)
        }
    else:
        observed = store.fingerprint(current)
    if not isinstance(expected, str) or expected not in fence:
        raise store.ReviewConflict('Cleanup row has no expected fence state')
    if current is None or observed != fence[expected]:
        raise store.ReviewConflict('Cleanup row has a newer edit')
    return True


def witness_snapshot(uid, path, raw):
    collection = path.split('/')[0] if isinstance(path, str) and path else ''
    safe_raw = _as_mapping(raw)
    fields = {
        'action_items': (
            'description',
            'owner',
            'due_at',
            'source',
            'account_generation',
            'status',
            'deleted',
            'superseded_by',
            'completed',
        ),
        'conversations': ('status', 'deleted', 'discarded', 'dream_duplicate', 'dream_duplicate_of', 'is_locked'),
    }.get(collection, ('name', 'redirect_entity_id'))
    result: dict = {'fields': {key: read_field_state(safe_raw, key) for key in fields}}
    if collection == 'conversations':
        from utils.agent_capabilities.transcripts import original_fingerprint

        result['speech'] = original_fingerprint(uid, safe_raw)
    return result
