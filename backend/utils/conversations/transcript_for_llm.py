"""Render conversation transcripts for LLM prompts with the configured user name.

#5319: ``TranscriptSegment.segments_as_string`` defaults missing ``user_name`` to
``"User"``. Callers that feed transcripts into summary / summarization-app LLMs
must pass the profile name from ``get_user_name`` so the model never sees the
generic label when the user has configured one.
"""

from __future__ import annotations

from typing import List, Optional, Protocol

from database.auth import get_user_name
from models.other import Person


class _TranscriptSource(Protocol):
    def get_transcript(
        self, include_timestamps: bool, people: Optional[List[Person]] = None, user_name: Optional[str] = None
    ) -> str: ...


def conversation_transcript_for_llm(
    uid: str,
    conversation: _TranscriptSource,
    people: Optional[List[Person]] = None,
    *,
    include_timestamps: bool = False,
) -> str:
    """Build a transcript string for LLM prompts using the user's configured name."""
    user_name = get_user_name(uid, use_default=False)
    return conversation.get_transcript(include_timestamps, people=people, user_name=user_name)
