"""Exact row and generation fences for reversible soft cleanup, never hard deletion."""

from copy import deepcopy
import math
from typing import Any, Dict, cast

from database import review_store as store
from database.review_field_states import read_field_state


def _coerce_generation(value: object) -> int:
    if value is None or isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return 0
        return max(0, int(value))
    if isinstance(value, str):
        try:
            return max(0, int(value.strip()))
        except ValueError:
            return 0
    return 0


def patched_row(row: Any, patch: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = deepcopy(row) if isinstance(row, dict) else {}
    if not isinstance(patch, dict):
        return result
    for path, value in patch.items():
        if not isinstance(path, str) or not path.strip():
            continue
        parent: Dict[str, Any] = result
        parts = [p for p in path.split('.') if p]
        if not parts:
            continue
        for part in parts[:-1]:
            existing = parent.get(part)
            if not isinstance(existing, dict):
                existing = {}
                parent[part] = existing
            parent = existing
        parent[parts[-1]] = deepcopy(value)
    return result


def restored_row(row: Any, fields: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = deepcopy(row) if isinstance(row, dict) else {}
    if not isinstance(fields, dict):
        return result
    for path, state in fields.items():
        if not isinstance(path, str) or not path.strip() or not isinstance(state, dict):
            continue
        parts = [p for p in path.split('.') if p]
        if not parts:
            continue
        parent: Dict[str, Any] = result
        present = bool(state.get('present'))
        valid_parent = True
        for part in parts[:-1]:
            existing = parent.get(part)
            if not isinstance(existing, dict):
                if not present:
                    valid_parent = False
                    break
                existing = {}
                parent[part] = existing
            parent = existing
        if not valid_parent:
            continue
        if present:
            parent[parts[-1]] = deepcopy(state.get('value'))
        else:
            parent.pop(parts[-1], None)
    return result


def journal_fences(edits: Any, rows: Any, expected_records: Any, witnesses: Any = None, *, uid: Any = None) -> dict:
    # The ordinary owned-field journal still performs reversal. Full-row hashes
    # ensure a later user edit cannot be touched by cleanup's Undo/Redo.
    safe_rows = rows if isinstance(rows, (list, tuple)) else []
    safe_expected = expected_records if isinstance(expected_records, dict) else {}
    journal: dict = {
        'reversal_fences': [
            {
                'collection': edit.collection,
                'document_id': edit.document_id,
                'fields': list(edit.patch),
                'before': {key: read_field_state(raw if isinstance(raw, dict) else {}, key) for key in edit.patch},
                'after': {key: read_field_state(patched_row(raw, edit.patch), key) for key in edit.patch},
            }
            for edit, _, raw in safe_rows
        ],
        'generation_fences': {
            path: _coerce_generation((raw if isinstance(raw, dict) else {}).get('account_generation', 0))
            for path, raw in safe_expected.items()
            if path == 'task_intelligence_control/state'
        },
    }
    if isinstance(witnesses, dict) and witnesses:
        # Redo-only survivor fences for merges: the hidden target points at a
        # survivor this edit never owned, so Redo must verify it is unchanged.
        journal['witness_fences'] = {
            path: witness_snapshot(uid, path, raw) for path, raw in witnesses.items() if raw is not None
        }
    return journal


def validate_generation(uid: Any, tx: Any, journal: Any) -> None:
    if not isinstance(journal, dict):
        return
    gen_fences = journal.get('generation_fences')
    if not isinstance(gen_fences, dict):
        return
    for path, generation in gen_fences.items():
        if not isinstance(path, str) or '/' not in path:
            continue
        collection, key = path.split('/', 1)
        if not collection.strip() or not key.strip():
            continue
        snapshot = store.user(uid).collection(collection.strip()).document(key.strip()).get(transaction=tx)
        raw_current: object = snapshot.to_dict() if getattr(snapshot, 'exists', True) else {}
        current: Dict[str, Any] = cast(Dict[str, Any], raw_current) if isinstance(raw_current, dict) else {}
        if _coerce_generation(current.get('account_generation', 0)) != _coerce_generation(generation):
            raise store.ReviewConflict('Cleanup account generation changed')


def validate_row(journal: Any, collection: Any, key: Any, current: Any, expected: Any) -> bool:
    if not isinstance(journal, dict):
        return False
    reversal_fences = journal.get('reversal_fences')
    if not isinstance(reversal_fences, list):
        return False
    fence = next(
        (
            row
            for row in reversal_fences
            if isinstance(row, dict) and row.get('collection') == collection and row.get('document_id') == key
        ),
        None,
    )
    if fence is None:
        return False
    safe_current: Dict[str, Any] = current if isinstance(current, dict) else {}
    observed = (
        {field_key: read_field_state(safe_current, field_key) for field_key in fence['fields']}
        if isinstance(fence.get('fields'), (list, tuple))
        else store.fingerprint(safe_current)
    )
    if not isinstance(current, dict) or expected not in fence or observed != fence[expected]:
        raise store.ReviewConflict('Cleanup row has a newer edit')
    return True


def witness_snapshot(uid: Any, path: Any, raw: Any) -> dict:
    safe_path = path if isinstance(path, str) else ''
    collection = safe_path.split('/')[0]
    safe_raw: Dict[str, Any] = raw if isinstance(raw, dict) else {}
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
