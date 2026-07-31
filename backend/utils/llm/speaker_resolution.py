"""Speaker identity resolution LLM route.

Runs once over a finalized transcript and proposes "speaker N is <name>" for
the speakers diarization left as bare indices. It is deliberately a batch,
post-processing route rather than a per-segment one: the live path already
pays for ``detect_speaker_from_text`` on every segment, and issue #6901 was
closed because a per-segment model added container weight to that hot loop. One
call per conversation costs a fraction of a cent and sees the whole
conversation, which is what naming actually needs.

The model is asked for evidence, not for identities. Every claim must quote the
line that supports it, and ``utils.speaker_resolution`` then verifies that
quote against the transcript. Prompt wording is not a safety boundary here, and
neither is anything this route returns: a claim only becomes an assignment once
``utils.llm.speaker_verification`` has independently tried and failed to refute
it.
"""

import logging
from typing import Any, List, Optional, Sequence, cast

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from utils.speaker_resolution import SpeakerClaim

from .clients import get_llm

logger = logging.getLogger(__name__)

MAX_TRANSCRIPT_CHARS = 24000


class RawSpeakerClaim(BaseModel):
    """One identity proposal, as the model returns it."""

    speaker_id: int = Field(description="The numeric speaker index from the transcript, e.g. 2 for 'Speaker 2'")
    person_name: str = Field(description="The person's name, as spoken in the transcript")
    evidence_quote: str = Field(
        description=(
            "The exact words from the transcript that establish the name, copied verbatim. "
            "Must contain the name. Do not paraphrase or reconstruct."
        )
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description="Confidence in this identification (0.0 to 1.0)")


class SpeakerResolutionResponse(BaseModel):
    """Model for the speaker resolution response."""

    claims: List[RawSpeakerClaim] = Field(
        default_factory=list, description="One entry per speaker that can be identified. Omit speakers you cannot name."
    )


def build_speaker_transcript(segments: Sequence[Any]) -> str:
    """Render segments as ``Speaker N: text``, truncated to the prompt budget.

    Segments already bound to a person or to the user keep their name so the
    model can use them as context, and so it does not propose a name for a
    speaker that is already decided.
    """
    lines: List[str] = []
    for segment in segments:
        text = getattr(segment, 'text', None)
        if not isinstance(text, str) or not text.strip():
            continue
        if getattr(segment, 'is_user', False):
            label = 'The user'
        else:
            person_name = getattr(segment, 'person_name', None)
            speaker_id = getattr(segment, 'speaker_id', None)
            if isinstance(person_name, str) and person_name:
                label = person_name
            elif isinstance(speaker_id, int):
                label = f'Speaker {speaker_id}'
            else:
                label = 'Unknown speaker'
        lines.append(f'{label}: {text.strip()}')

    transcript = '\n'.join(lines)
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        transcript = transcript[:MAX_TRANSCRIPT_CHARS]
    return transcript


def build_known_people_context(known_names: Sequence[str]) -> str:
    if not known_names:
        return "None on record yet."
    return "\n".join(f"- {name}" for name in known_names)


def to_speaker_claims(response: SpeakerResolutionResponse) -> List[SpeakerClaim]:
    """Convert parsed model output into gate input, dropping nameless rows."""
    claims: List[SpeakerClaim] = []
    for raw in response.claims:
        if not raw.person_name.strip():
            continue
        claims.append(
            SpeakerClaim(
                speaker_id=raw.speaker_id,
                person_name=raw.person_name.strip(),
                evidence_quote=raw.evidence_quote,
                confidence=float(raw.confidence),
            )
        )
    return claims


def resolve_speakers(
    segments: Sequence[Any],
    known_names: Sequence[str] = (),
    user_name: Optional[str] = None,
) -> List[SpeakerClaim]:
    """Ask the model who the unnamed speakers are.

    Args:
        segments: The conversation's transcript segments, in order.
        known_names: Names the user already has Person records for. Supplied so
            the model prefers an existing person over a new spelling of them.
        user_name: The account owner's display name, so the model can tell who
            "the user" is and does not propose the owner as a separate person.

    Returns:
        Parsed claims, unvalidated. Callers must pass these through
        ``plan_speaker_resolution`` before acting on any of them.
    """
    transcript = build_speaker_transcript(segments)
    if not transcript:
        return []

    prompt_text = '''You are a speaker identification system. You are given a transcript where some speakers are named and others are only numbered. Your job is to work out which numbered speakers can be identified by name, using only what is actually said.

TRANSCRIPT:
{transcript}

PEOPLE THE USER ALREADY KNOWS:
{known_people}

THE USER IS: {user_name}

INSTRUCTIONS:
- Only identify a numbered speaker when a name for them is actually spoken in the transcript.
- Prefer a name from the known-people list when the transcript matches one of them, including a shortened or informal form of it. Use the spelling from that list.
- Never propose a name for "The user" or for a speaker who is already named.
- Never propose the same name for two different speaker numbers.
- Omit any speaker you cannot name. An empty list is the correct answer for a transcript where nobody is named.
- Do not guess from topic, job title, accent, or who is likely to be in the room. If you find yourself reasoning about what kind of person this sounds like, omit the speaker instead.

For each speaker you can identify, provide:
- speaker_id: the speaker number from the transcript
- person_name: the name, spelled as it appears in the known-people list when it is one of them
- evidence_quote: the exact words from the transcript that establish the name, copied character for character from a single line above. It must contain the name. Do not paraphrase, merge lines, or clean up the wording.
- confidence: how sure you are (0.0-1.0)

{format_instructions}'''

    parser = PydanticOutputParser(pydantic_object=SpeakerResolutionResponse)
    prompt = cast(Any, ChatPromptTemplate).from_messages([('system', prompt_text)])
    chain = prompt | get_llm('speaker_resolution') | parser

    try:
        response = cast(
            SpeakerResolutionResponse,
            chain.invoke(
                {
                    'transcript': transcript,
                    'known_people': build_known_people_context(known_names),
                    'user_name': user_name or 'the user',
                    'format_instructions': parser.get_format_instructions(),
                }
            ),
        )
    except Exception as e:
        logger.error('Speaker resolution LLM call failed: %s', e)
        return []

    return to_speaker_claims(response)
