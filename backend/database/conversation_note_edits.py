"""Atomic visible-note edits and their provenance invalidation."""

import copy
from typing import Any, Callable

from google.cloud import firestore

from utils.conversations.note_claim_mutations import claim_invalidation_patch


def note_edit_targets(fields: dict) -> tuple[str, ...]:
    return tuple(
        '/' + key.removeprefix('structured.').replace('.', '/')
        for key in fields
        if key.startswith('structured.') and key != 'structured.note_claims'
    )


def write_note_edit(ref: Any, transaction: Any, fields: dict, prepare: Callable[[dict, str], dict]) -> bool:
    @firestore.transactional
    def update(tx):
        snapshot = ref.get(transaction=tx)
        if not snapshot.exists:
            return False
        current = snapshot.to_dict() or {}
        patch = prepare(copy.deepcopy(fields), current.get('data_protection_level', 'standard'))
        if 'structured' in fields:
            # Complete replacement carries its own claims; absent metadata must
            # not survive a recursively merged legacy replacement.
            note = patch.get('structured')
            if (
                isinstance(note, dict)
                and 'note_claims' not in note
                and 'note_claims' in (current.get('structured') or {})
            ):
                note['note_claims'] = firestore.DELETE_FIELD
        elif 'structured.note_claims' not in fields:
            patch.update(claim_invalidation_patch(current.get('structured'), note_edit_targets(fields)))
        tx.update(ref, patch)
        return True

    return update(transaction)
