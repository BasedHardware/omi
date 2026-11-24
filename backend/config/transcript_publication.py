"""Rollout controls for reading transcript content before enrichment."""

import os


def deferred_transcript_reads_enabled() -> bool:
    return os.getenv('OMI_DEFERRED_TRANSCRIPT_READS_ENABLED', 'on').lower() == 'on'


def discovery_statuses(categories: list[str] | None) -> list[str]:
    # Two IN filters expand into disjunctive normal form. Six categories fit
    # with both date bounds and keyset ordering under Firestore's 100-term cap.
    if deferred_transcript_reads_enabled() and len(set(categories or ())) <= 6:
        return ['completed', 'processing']
    return ['completed']


def ready_for_discovery(row: dict) -> bool:
    return row.get('status') != 'processing' or bool(
        row.get('deferred') or row.get('processing_deferred') or row.get('has_content')
    )


def pre_chat_memory_catch_up_enabled() -> bool:
    return (
        deferred_transcript_reads_enabled() and os.getenv('OMI_PRE_CHAT_MEMORY_CATCH_UP_ENABLED', 'off').lower() == 'on'
    )
