"""Exact row and generation fences for reversible soft cleanup, never hard deletion."""

from copy import deepcopy

from database import review_store as store


def patched_row(row, patch):
    result = deepcopy(row)
    for path, value in patch.items():
        parent = result
        parts = path.split('.')
        for part in parts[:-1]:
            parent = parent.setdefault(part, {})
        parent[parts[-1]] = deepcopy(value)
    return result


def restored_row(row, fields):
    result = deepcopy(row)
    for path, state in fields.items():
        parent = result
        parts = path.split('.')
        for part in parts[:-1]:
            parent = parent.setdefault(part, {})
        if state['present']:
            parent[parts[-1]] = deepcopy(state['value'])
        else:
            parent.pop(parts[-1], None)
    return result


def journal_fences(edits, rows, expected_records, witnesses=None):
    # The ordinary owned-field journal still performs reversal. Full-row hashes
    # ensure a later user edit cannot be touched by cleanup's Undo/Redo.
    journal: dict = {
        'reversal_fences': [
            {
                'collection': edit.collection,
                'document_id': edit.document_id,
                'before': store.fingerprint(raw),
                'after': store.fingerprint(patched_row(raw, edit.patch)),
            }
            for edit, _, raw in rows
        ],
        'generation_fences': {
            path: int((raw or {}).get('account_generation', 0))
            for path, raw in (expected_records or {}).items()
            if path == 'task_intelligence_control/state'
        },
    }
    if witnesses:
        # Redo-only survivor fences for merges: the hidden target points at a
        # survivor this edit never owned, so Redo must verify it is unchanged.
        journal['witness_fences'] = {path: store.fingerprint(raw) for path, raw in witnesses.items() if raw is not None}
    return journal


def validate_generation(uid, tx, journal):
    for path, generation in journal.get('generation_fences', {}).items():
        collection, key = path.split('/', 1)
        current = store.user(uid).collection(collection).document(key).get(transaction=tx).to_dict() or {}
        if int(current.get('account_generation', 0)) != generation:
            raise store.ReviewConflict('Cleanup account generation changed')


def validate_row(journal, collection, key, current, expected):
    fence = next(
        (
            row
            for row in journal.get('reversal_fences', [])
            if row['collection'] == collection and row['document_id'] == key
        ),
        None,
    )
    if fence is None:
        return False
    if current is None or store.fingerprint(current) != fence[expected]:
        raise store.ReviewConflict('Cleanup row has a newer edit')
    return True
