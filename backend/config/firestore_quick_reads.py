# LIFECYCLE: permanent
"""Default-on structural optimizations; independent emergency kill switches."""

import os


def smart_merge_partition_enabled() -> bool:
    return os.getenv('FSR_SMART_MERGE_PARTITION', 'on').strip().lower() != 'off'


def kg_citation_index_enabled() -> bool:
    return os.getenv('FSR_KG_CITATION_INDEX', 'on').strip().lower() != 'off'


def indexed_string_value_safe(value: object) -> bool:
    """Only query identifiers fully represented by Firestore's UTF-8 index value."""
    if not isinstance(value, str):
        return False
    try:
        return len(value.encode('utf-8')) <= 1500
    except UnicodeEncodeError:
        return False
