"""Rollout controls for reading transcript content before enrichment."""

import os


def deferred_transcript_reads_enabled() -> bool:
    return os.getenv('OMI_DEFERRED_TRANSCRIPT_READS_ENABLED', 'on').lower() == 'on'


def discovery_statuses() -> list[str]:
    return ['completed', 'processing'] if deferred_transcript_reads_enabled() else ['completed']


def ready_for_discovery(row: dict) -> bool:
    return row.get('status') != 'processing' or bool(
        row.get('deferred') or row.get('processing_deferred') or row.get('has_content')
    )


def pre_chat_memory_catch_up_enabled() -> bool:
    return (
        deferred_transcript_reads_enabled() and os.getenv('OMI_PRE_CHAT_MEMORY_CATCH_UP_ENABLED', 'off').lower() == 'on'
    )
