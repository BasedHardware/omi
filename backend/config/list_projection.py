"""Pure list projection schema and live writer switch."""

import os

STATE_COLLECTION = 'list_serving_versions'
ROW_COLLECTIONS = {'conversations': 'conversation_list_rows', 'action_items': 'action_item_list_rows'}


def writer_enabled() -> bool:
    # Off by default until the OMI_LIST_VERSION_EPOCH reader ramp is scheduled
    # (fswrites, 2026-11-01): with no reader, the version and row writes were
    # ~4M Firestore writes/day that nothing read. Turning the writer back on is a
    # fleet-wide flip followed by full writer convergence before any epoch is set.
    return os.getenv('OMI_LIST_PROJECTION_WRITER_ENABLED', 'false').strip().lower() not in {'0', 'false', 'off'}
