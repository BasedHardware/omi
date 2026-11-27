"""Field updates for a conversation processing result."""

from collections.abc import Mapping
from typing import Any

from models.conversation import ConversationStatus
from utils.conversations.summary_delivery import present
from utils.conversations.v3 import policy as v3_policy


def cleared_native_visibility(existing, *, has_notes):
    if not has_notes and existing.get(v3_policy.NATIVE_MANUAL_NOTES_VISIBILITY):
        return {
            v3_policy.NATIVE_MANUAL_NOTES_VISIBILITY: None,
            'v3_notes_written': False,
            'summary_covers_through': None,
        }
    return {}


def stamp_native_visibility(existing, write_data):
    if 'structured' in write_data and existing.get(v3_policy.NATIVE_MANUAL_NOTES_VISIBILITY):
        incoming = write_data['structured']
        prior = existing.get('structured')
        # Processing writes merge structured leaves, so omitted body fields can survive.
        merged = (
            {**prior, **incoming} if isinstance(prior, dict) and isinstance(incoming, dict) and incoming else incoming
        )
        clearing = cleared_native_visibility(existing, has_notes=present(merged))
        if clearing:
            write_data.update(clearing)
            return
    if (
        write_data.get('status') == ConversationStatus.completed
        and write_data.get('summary_output_present') is True
        and not any(write_data.get(key) for key in ('discarded', 'terminal_no_derived_effects', 'deferred'))
    ):
        visibility_receipt = v3_policy.native_manual_notes_receipt(existing)
        if visibility_receipt:
            # Commit with the genuine notes, before the builder can observe
            # a new upload revision and revoke the transient native proof.
            write_data[v3_policy.NATIVE_MANUAL_NOTES_VISIBILITY] = visibility_receipt


def update_fields(data: Mapping[str, Any]) -> dict:
    """Preserve set(merge=True)'s recursive leaf mask in one update of an existing row.

    Empty maps replace that map; arrays and scalars are leaves. FieldPath quotes
    literal dotted/backtick keys rather than treating them as update paths.
    """
    from google.cloud.firestore_v1.field_path import FieldPath

    fields = {}

    def visit(value, path):
        if isinstance(value, dict) and value:
            for key, child in value.items():
                visit(child, (*path, key))
        else:
            fields[FieldPath(*path).to_api_repr()] = value

    for key, value in data.items():
        visit(value, (key,))
    return fields
