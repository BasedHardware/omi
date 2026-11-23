"""Rollout controls for reading transcript content before enrichment."""

import os


def deferred_transcript_reads_enabled() -> bool:
    return os.getenv('OMI_DEFERRED_TRANSCRIPT_READS_ENABLED', 'on').lower() == 'on'
