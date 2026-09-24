"""The Jev question for the relevance model tier (``relevance.py``, #14835).

Wording B from the 2026-09-23 benchmark ("would the user want to find this
later"), asked about the transcript in the shipped ``User:`` / ``Speaker N:``
format plus its word count. The state deliberately omits the conversation
duration and the ``conv_discard`` "under 2 minutes, apply a higher bar"
clause: measured durations are unreliable (most short captures read as under
120 s, often 0 s), and that clause is what made gpt-5-nano discard real
conversations in the benchmark.

Only the question text and state shape live here; the threshold and the tier
order live in ``relevance.py``. Changing the wording changes calibration, so
bump ``QUESTION_VERSION`` and re-measure the threshold together.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from models.transcript_segment import TranscriptSegment
from utils.conversations.relevance_rules import KEEP_WORD_COUNT, transcript_word_count
from utils.llm.jev_client import ask_jev

LANE = 'conversation_relevance'
QUESTION_VERSION = 'relevance_b1'
QUESTION_NAME = 'worth_keeping'
QUESTIONS: dict[str, dict[str, Any]] = {
    QUESTION_NAME: {
        'type': 'noul',
        'instructions': (
            "This is an automatically captured snippet from the user's always-on wearable. Would the user "
            'plausibly want to find this later in their memory log? Losing a real memory is much worse than '
            'keeping a bit of noise.'
        ),
        'criteria': {
            'true': (
                'it mentions anything the user could want later: a task, a name, a time, a number, a place, '
                'a plan, an open question, or a personal fact'
            ),
            'false': (
                'it is noise: filler, acknowledgments, garbled fragments, background media, or throwaway '
                'remarks with nothing to remember'
            ),
        },
    },
}


def relevance_transcript(segments: Sequence[TranscriptSegment]) -> str:
    """The shipped transcript rendering, without names from the people map."""
    return TranscriptSegment.segments_as_string([segment for segment in segments if (segment.text or '').strip()])


def relevance_state(transcript: str) -> str:
    return f'Transcript:\n```\n{transcript}\n```\nWord count: {transcript_word_count(transcript)} words.'


def jev_tier_applies(transcript: str) -> bool:
    """Jev replaces ``conv_discard`` only where the benchmark measured it.

    An empty transcript and anything over ``KEEP_WORD_COUNT`` stay on the
    existing path (``conv_discard`` keeps long transcripts without a model
    call). Photos and trusted wake-word markers are excluded by the caller.
    """
    return bool(transcript.strip()) and transcript_word_count(transcript) <= KEEP_WORD_COUNT


def jev_discard_probability(transcript: str) -> Optional[float]:
    """P(discard) = 1 - P(worth keeping), or ``None`` when Jev gave no answer."""
    answers = ask_jev(relevance_state(transcript), QUESTIONS, lane=LANE)
    if answers is None:
        return None
    return 1.0 - answers.noul(QUESTION_NAME)
