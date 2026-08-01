"""Adversarial second opinion on a proposed speaker identity.

``utils.llm.speaker_resolution`` proposes names and ``utils.speaker_resolution``
proves the supporting quote was really said. Neither establishes that the words
*mean* this speaker is that person -- "thanks, Alex" grounds perfectly whether
Alex is the listener, someone across the room, or a name being read off a
slide. Asking the same model to also classify its own evidence does not help:
the classification is one more thing it can be confidently wrong about.

So this is a separate call with the opposite job. It is shown one proposal and
asked to *break* it, and it is told to say refuted whenever it is unsure. That
asymmetry is the point: a false refusal costs the user a tap on a suggestion,
while a false acceptance enrols a voiceprint under the wrong person and cannot
be undone. Anything that goes wrong here -- a parse failure, a timeout, an
unusable answer -- resolves to refuted for the same reason.
"""

import logging
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Sequence, cast

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from utils.log_sanitizer import sanitize
from utils.observability.fallback import record_fallback

from .clients import get_llm
from .speaker_resolution import MAX_TRANSCRIPT_CHARS, build_speaker_transcript

logger = logging.getLogger(__name__)

MAX_SPEAKER_LINES = 40


class SpeakerVerificationResponse(BaseModel):
    """The refutation attempt, as the model returns it."""

    refuted: bool = Field(
        description=(
            "true if the transcript does not clearly establish that this speaker is this person, "
            "including when you are merely unsure. false only when the identification is unmistakable."
        )
    )
    reason: str = Field(default="", description="One sentence explaining the verdict.")


@dataclass(frozen=True)
class SpeakerVerdict:
    """A verified-or-not answer for one proposed identity."""

    refuted: bool
    reason: str


REFUTED_ON_ERROR = SpeakerVerdict(refuted=True, reason="verification_unavailable")


def record_verification_exhausted(reason: str) -> None:
    """Report a refutation that came from a broken verifier, not from the evidence.

    Refuting on failure is deliberate, but it silently downgrades the feature
    from automatic assignment to suggestion-only, and a log line alone leaves
    that invisible to operations. The shared counter is what distinguishes a
    provider outage from a transcript that genuinely names nobody.
    """
    record_fallback(
        component='other',
        from_mode='verified_assignment',
        to_mode='suggestion_only',
        reason=reason,
        outcome='exhausted',
        log=logger,
    )


def build_speaker_lines(segments: Sequence[Any], speaker_id: int) -> str:
    """Render only the lines the proposed speaker said themselves.

    Given separately from the transcript so the model can check a claimed
    self-introduction against this speaker's own words without having to hunt
    for them, and so it can see when this speaker never says anything that
    would place them in the conversation at all.
    """
    lines: List[str] = []
    for segment in segments:
        if getattr(segment, 'is_user', False) or getattr(segment, 'person_id', None):
            continue
        if getattr(segment, 'speaker_id', None) != speaker_id:
            continue
        text = getattr(segment, 'text', None)
        if not isinstance(text, str) or not text.strip():
            continue
        lines.append(f'- {text.strip()}')
        if len(lines) >= MAX_SPEAKER_LINES:
            break
    if not lines:
        return "This speaker has no lines of their own in the transcript."
    return '\n'.join(lines)


def verify_speaker_identification(
    segments: Sequence[Any],
    speaker_id: int,
    person_name: str,
    evidence_quote: str = "",
    user_name: Optional[str] = None,
    person_names: Optional[Mapping[str, str]] = None,
) -> SpeakerVerdict:
    """Try to refute "speaker N is <name>". Blocking; run it off the event loop.

    Args:
        segments: The conversation's transcript segments, in order.
        speaker_id: The numbered speaker the proposal is about.
        person_name: The name being proposed for that speaker.
        evidence_quote: The line the proposal rests on, already grounded.
        user_name: The account owner's display name, so the model does not read
            the owner's own turns as a third person.
        person_names: ``person_id`` to display name for the people already bound
            in this transcript. Without it every decided speaker renders as a
            number and the "another speaker fits the name at least as well" test
            below cannot see that one of them already *is* this name, which is
            how a second voice gets enrolled into an existing person.

    Returns:
        A ``SpeakerVerdict``. ``refuted`` is true on any failure, so a caller
        that treats false as permission to enrol stays safe when this breaks.
    """
    transcript = build_speaker_transcript(segments, person_names)
    if not transcript:
        return REFUTED_ON_ERROR

    speaker_lines = build_speaker_lines(segments, speaker_id)

    prompt_text = '''You are auditing a speaker identification that another system has proposed. Your job is to REFUTE it if you can. You are not being asked whether the name is plausible; you are being asked whether the transcript makes it certain.

TRANSCRIPT:
{transcript}

THE CLAIM UNDER AUDIT: Speaker {speaker_id} is "{person_name}".

THE LINE THE CLAIM RESTS ON: {evidence_quote}

EVERYTHING SPEAKER {speaker_id} SAYS:
{speaker_lines}

THE USER IS: {user_name}

Refute the claim (refuted = true) if any of these hold:
- The name is spoken, but about somebody who is not Speaker {speaker_id}: a third party being discussed, a name read aloud, a person who is absent.
- The name appears as the subject of a sentence rather than as the person being spoken to, and nothing else ties it to Speaker {speaker_id}.
- Another speaker fits the name at least as well as Speaker {speaker_id} does.
- Speaker {speaker_id} says nothing that a person of that name would have to have said.
- The line is ambiguous, or you find yourself reasoning from role, topic, or who is likely to be present.
- You are simply not sure.

Accept the claim (refuted = false) ONLY when the transcript leaves no reasonable alternative: Speaker {speaker_id} states this name as their own, or another speaker addresses Speaker {speaker_id} by it and Speaker {speaker_id} responds as the person addressed.

When in doubt, refute. A wrongly accepted identification is not recoverable; a wrongly refuted one costs nothing.

{format_instructions}'''

    parser = PydanticOutputParser(pydantic_object=SpeakerVerificationResponse)
    prompt = cast(Any, ChatPromptTemplate).from_messages([('system', prompt_text)])
    chain = prompt | get_llm('speaker_verification') | parser

    try:
        response = cast(
            SpeakerVerificationResponse,
            chain.invoke(
                {
                    'transcript': transcript,
                    'speaker_id': speaker_id,
                    'person_name': person_name,
                    'evidence_quote': (evidence_quote or '(none supplied)')[:MAX_TRANSCRIPT_CHARS],
                    'speaker_lines': speaker_lines,
                    'user_name': user_name or 'the user',
                    'format_instructions': parser.get_format_instructions(),
                }
            ),
        )
    except Exception as e:
        logger.error('Speaker verification LLM call failed speaker=%s: %s', speaker_id, sanitize(e))
        record_verification_exhausted('other')
        return REFUTED_ON_ERROR

    return SpeakerVerdict(refuted=bool(response.refuted), reason=response.reason.strip())
