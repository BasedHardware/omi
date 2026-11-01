"""Pure list projection schema and live writer kill switch."""

import os

STATE_COLLECTION = 'list_serving_versions'
ROW_COLLECTIONS = {'conversations': 'conversation_list_rows', 'action_items': 'action_item_list_rows'}


def writer_enabled() -> bool:
    return os.getenv('OMI_LIST_PROJECTION_WRITER_ENABLED', 'true').strip().lower() not in {'0', 'false', 'off'}
