"""Jev owner question for capture-time memory attribution (#14835).

Capture attributes each memory candidate to a subject (``_l1_candidate_subject``
in ``process_conversation.py``). A candidate attributed to someone else can
never be promoted to Long-term, and on the owner's own labels that attribution
was wrong far more often than right: when the pipeline said "someone else" and
Jev's P(owner = user) was at least 0.9, the owner judged 30 of 31 candidates to
be his own fact. Outside that band Jev was no better than the pipeline.

So this check runs only for candidates the pipeline attributed to a third
party, and it can only move them toward the user, never away. Below the
threshold, or without an answer, the pipeline's attribution stands. It asks
the owner question alone: the benchmark's ``p_save >= 0.6`` clause blocked half
of the facts the owner wanted and is deliberately not applied.

The state is the candidate, its speaker-labelled supporting quotes, and the
conversation title and summary (benchmark variant A), with a generic preamble
in place of the benchmark's owner biography.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence, Tuple

from config.jev_decisions import JEV_MODEL
from utils.llm.jev_client import ask_jev

LANE = 'memory_owner'
QUESTION_VERSION = 'owner_a1'
QUESTION_NAME = 'owner'
USER_OPTION = 'user'
# Flip to the user only at or above this P(owner = user). Measured band; see module docstring.
OWNER_FLIP_THRESHOLD = 0.9
# Candidates per conversation that may be checked; the rest keep the pipeline's attribution.
MAX_OWNER_CHECKS_PER_CONVERSATION = 8
MAX_QUOTES = 5
MAX_OVERVIEW_CHARS = 400

_DEVICE_DESCRIPTIONS = {
    'omi': 'Omi pendant (single microphone; nearby people, TV and media are also picked up)',
    'desktop': 'Omi desktop app (microphone plus system audio from calls and videos)',
}


@dataclass(frozen=True)
class OwnerFlip:
    """Provenance for a capture-time re-attribution, stored on the item so it can be audited or reverted."""

    p_user: float
    pipeline_subject_entity_id: Optional[str]
    pipeline_subject_kind: str

    def as_record(self) -> dict[str, Any]:
        return {
            'source': 'jev',
            'question_version': QUESTION_VERSION,
            'model': JEV_MODEL,
            'p_user': round(self.p_user, 4),
            'threshold': OWNER_FLIP_THRESHOLD,
            'pipeline_subject_attribution': 'third_party',
            'pipeline_subject_entity_id': self.pipeline_subject_entity_id,
            'pipeline_subject_kind': self.pipeline_subject_kind,
        }


def owner_questions(user_name: Optional[str]) -> dict[str, dict[str, Any]]:
    user_label = _user_label(user_name)
    return {
        QUESTION_NAME: {
            'type': 'choice',
            'instructions': 'Whose fact is this candidate memory?',
            'criteria': {
                USER_OPTION: (
                    f'a fact about the user ({user_label}) themself, their own work, plans, preferences, '
                    'or commitments'
                ),
                'third_party': 'a fact about some other person (a colleague, friend, stranger, or a speaker in media)',
                'general_knowledge': 'general world knowledge or information, not about any particular person',
            },
        },
    }


def owner_state(
    *,
    candidate: str,
    quotes: Sequence[Tuple[Optional[str], str]],
    title: Optional[str],
    overview: Optional[str],
    source: Optional[str],
    user_name: Optional[str],
) -> str:
    """Benchmark variant A's state: preamble, device, title, summary, candidate, labelled quotes."""
    device = _DEVICE_DESCRIPTIONS.get(source or '', str(source or 'unknown'))
    quote_lines = (
        '\n'.join(
            f'  [{speaker or "?"}] "{text.strip().strip(chr(34))}"' for speaker, text in list(quotes)[:MAX_QUOTES]
        )
        or '  (none)'
    )
    preamble = (
        'Omi is a personal AI memory device. It passively records its owner\'s conversations and extracts facts '
        f'to remember. The owner ("the user") is {_user_label(user_name)}. Transcripts come from speech-to-text '
        'and may contain errors. Speaker labels (SPEAKER_00 etc.) are unreliable and do not reliably say which '
        'speaker is the user.'
    )
    return (
        f'{preamble}\n\nCapture device: {device}\nConversation title: {title or ""}\n'
        f'Conversation summary: {(overview or "")[:MAX_OVERVIEW_CHARS]}\n\n'
        f'Candidate memory: "{candidate}"\nSupporting transcript quotes:\n{quote_lines}'
    )


def jev_owner_flip(
    *,
    candidate: str,
    quotes: Sequence[Tuple[Optional[str], str]],
    title: Optional[str],
    overview: Optional[str],
    source: Optional[str],
    user_name: Optional[str],
    pipeline_subject_entity_id: Optional[str],
    pipeline_subject_kind: str,
) -> Tuple[Optional[OwnerFlip], str]:
    """Ask the owner question for one third-party candidate.

    Returns ``(flip, outcome)``: a flip only when P(user) reaches the
    threshold; ``outcome`` is the bounded metric label.
    """
    answers = ask_jev(
        owner_state(
            candidate=candidate,
            quotes=quotes,
            title=title,
            overview=overview,
            source=source,
            user_name=user_name,
        ),
        owner_questions(user_name),
        lane=LANE,
    )
    if answers is None:
        return None, 'unavailable'
    p_user = answers.choice_probability(QUESTION_NAME, USER_OPTION)
    if p_user < OWNER_FLIP_THRESHOLD:
        return None, 'kept_third_party'
    return (
        OwnerFlip(
            p_user=p_user,
            pipeline_subject_entity_id=pipeline_subject_entity_id,
            pipeline_subject_kind=pipeline_subject_kind,
        ),
        'flipped',
    )


def _user_label(user_name: Optional[str]) -> str:
    name = (user_name or '').strip()
    return name if name and name.lower() != 'the user' else 'the device owner'
