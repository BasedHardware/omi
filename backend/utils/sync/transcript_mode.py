"""Typed mutation contract for uploaded sync transcripts."""

from enum import Enum


class SyncTranscriptMode(str, Enum):
    """Select how a completed sync job may mutate its target conversation."""

    MERGE = 'merge'
    REPLACE = 'replace'

    @classmethod
    def from_task_payload(cls, value: object) -> 'SyncTranscriptMode':
        """Parse durable task input without silently changing mutation semantics."""
        if value is None:
            # Tasks admitted before this field existed are merge jobs.
            return cls.MERGE
        if not isinstance(value, str):
            raise ValueError('transcript_mode must be a string')
        return cls(value)
