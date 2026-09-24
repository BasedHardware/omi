"""Non-prompt validation and sanitization for meeting-notes output.

These helpers were split out of ``conversation_processing`` so that module stays
focused on LLM orchestration. ``conversation_processing`` re-exports the names
callers and tests already import from it.
"""

import re
from typing import Any, Iterable, List, Optional

from models.structured import Participant, Structured  # type: ignore[reportAttributeAccessIssue]  # SDK/fallback export is runtime-complete.
from utils.conversations.meeting_participants import MeetingRoster


def _validate_source_segment_ids(values: Any, valid_ids: set[str]) -> list[str]:
    """Keep valid, unique source IDs in model order; reject all other values."""

    if not valid_ids or not values:
        return []
    validated: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or value not in valid_ids or value in seen:
            continue
        seen.add(value)
        validated.append(value)
    return validated


def validate_structured_source_segment_ids(
    structured: Structured, transcript_segment_ids: Optional[Iterable[object]]
) -> Structured:
    """Drop fabricated/duplicate evidence references from any summary output.

    The caller supplies IDs from typed ``TranscriptSegment`` objects. This
    boundary intentionally has no transcript-string parser: external text and
    bracket-like content are not evidence of a persisted segment identity.
    """

    valid_ids = {
        segment_id for segment_id in (transcript_segment_ids or ()) if isinstance(segment_id, str) and segment_id
    }
    for section in structured.sections:
        section.source_segment_ids = _validate_source_segment_ids(section.source_segment_ids, valid_ids)
    for action_item in structured.action_items:
        action_item.source_segment_ids = _validate_source_segment_ids(action_item.source_segment_ids, valid_ids)
    return structured


# Diarization placeholders are transcript machinery, not people. Prompt wording alone
# does not hold — v2 already forbade "Speaker 1 said that" and still leaked the token.
# `spk N` is the compact speaker-map key (SCA-454) and leaks the same way.
_SPEAKER_PLACEHOLDER_RE = re.compile(r'(?i)\b(?:spk|speaker)[ _]\d+\b:?[ \t]*')


def strip_speaker_placeholders(text: str) -> str:
    """Drop leftover Speaker N / SPEAKER_00 tokens rather than inventing a name."""
    if not text:
        return text
    cleaned = _SPEAKER_PLACEHOLDER_RE.sub('', text)
    cleaned = re.sub(r'[^\S\n]+', ' ', cleaned)
    cleaned = re.sub(r' *\n *', '\n', cleaned)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def sanitize_structured_speaker_placeholders(structured: Structured) -> Structured:
    """Strip diarization placeholders from every user-visible notes field."""
    structured.title = strip_speaker_placeholders(structured.title)
    structured.overview = strip_speaker_placeholders(structured.overview)
    for section in structured.sections:
        section.heading = strip_speaker_placeholders(section.heading)
        section.body_markdown = strip_speaker_placeholders(section.body_markdown)
    for item in structured.action_items:
        item.description = strip_speaker_placeholders(item.description)
        if item.owner_name:
            cleaned_owner = strip_speaker_placeholders(item.owner_name)
            item.owner_name = cleaned_owner or None
        if item.context:
            item.context = strip_speaker_placeholders(item.context)
    return structured


def _name_in_transcript(name: str, transcript_body: str) -> bool:
    """Case-insensitive whole-name (word-boundary) match against the transcript body."""
    name = name.strip()
    if not name or not transcript_body:
        return False
    return re.search(r'(?<!\w)' + re.escape(name) + r'(?!\w)', transcript_body, re.IGNORECASE) is not None


def validate_rich_meeting_notes(
    structured: Structured,
    *,
    transcript_body: str,
    roster: Optional[MeetingRoster],
    has_background_context: bool,
    background_body: str = '',
) -> Structured:
    """Server-side guardrails for rich-only fields; the flag-off path never runs this.

    Participants must be corroborated (roster name/email or a whole-name transcript
    match), the account owner is never a participant, and nameless participants
    survive only on a roster email. Insights exist only with background context,
    capped at 4 entries of <=30 words. At most one side_notes section survives,
    forced last with heading "Side notes" and 1-4 bullets.
    """
    roster_entries = list(roster.entries) if roster else []
    roster_by_name = {e.display_name.casefold(): e for e in roster_entries if e.display_name}
    roster_by_email = {e.email.casefold(): e for e in roster_entries if e.email}
    owner_names = {e.display_name.casefold() for e in roster_entries if e.kind == 'owner' and e.display_name}
    owner_emails = {e.email.casefold() for e in roster_entries if e.kind == 'owner' and e.email}
    # A first-name-only owner entry still owns bare repeats of that first name
    # in the model output.
    owner_first_tokens = {name.split()[0] for name in owner_names if len(name.split()) == 1}

    validated_participants: List[Participant] = []
    for participant in structured.participants:
        name = (participant.name or '').strip()
        email = (participant.email or '').strip()
        if name.casefold() in owner_names or email.casefold() in owner_emails:
            continue
        if owner_first_tokens and len(name.split()) == 1 and name.casefold() in owner_first_tokens:
            continue
        matched_entry = None
        if name:
            matched_entry = roster_by_name.get(name.casefold())
            # Screen text (a call's participant list, a profile opened during the
            # call) is a legitimate identity source alongside the transcript.
            if (
                matched_entry is None
                and not _name_in_transcript(name, transcript_body)
                and not (background_body and _name_in_transcript(name, background_body))
            ):
                continue
        elif email:
            matched_entry = roster_by_email.get(email.casefold())
            if matched_entry is None:
                continue
        else:
            continue
        # Keep an email only when it belongs to the same roster entry that
        # corroborated the participant — a name match must not inherit someone
        # else's roster email, and untrusted emails are dropped.
        if (
            email
            and matched_entry is not None
            and matched_entry.email
            and matched_entry.email.casefold() == email.casefold()
        ):
            participant.email = email
        else:
            participant.email = None
        if name:
            participant.name = name
        validated_participants.append(participant)
    structured.participants = validated_participants

    if not has_background_context:
        structured.insights = []
    else:
        kept = []
        for insight in structured.insights[:4]:
            words = insight.text.split()
            if len(words) > 30:
                insight.text = ' '.join(words[:30])
            if insight.text.strip():
                kept.append(insight)
        structured.insights = kept

    side_notes = [s for s in structured.sections if getattr(s, 'kind', 'main') == 'side_notes']
    main_sections = [s for s in structured.sections if getattr(s, 'kind', 'main') != 'side_notes']
    if side_notes:
        # Merge every side_notes section's bullets into one last section rather
        # than silently dropping earlier tangents.
        bullets: List[str] = []
        for section in side_notes:
            for line in (section.body_markdown or '').split('\n'):
                line = line.strip()
                if not line.startswith('-') or not line.lstrip('- ').strip():
                    continue
                if line not in bullets:
                    bullets.append(line)
        bullets = bullets[:4]
        if bullets:
            merged = side_notes[-1]
            merged.heading = 'Side notes'
            merged.body_markdown = '\n'.join(bullets)
            structured.sections = [*main_sections, merged]
        else:
            structured.sections = main_sections
    else:
        structured.sections = main_sections
    return structured
