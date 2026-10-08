"""Non-prompt validation and sanitization for meeting-notes output.

These helpers were split out of ``conversation_processing`` so that module stays
focused on LLM orchestration. ``conversation_processing`` re-exports the names
callers and tests already import from it.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from models.structured import Structured  # type: ignore[reportAttributeAccessIssue]  # SDK/fallback export is runtime-complete.

PRESENTATION_CONTRACT_VERSION = 'v1'


@dataclass
class PresentationContractReport:
    """Bounded, content-free evidence about generated-note conformance."""

    repairs: set[str] = field(default_factory=set)
    violations: set[str] = field(default_factory=set)

    @property
    def needs_revision(self) -> bool:
        return bool(self.violations)


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


_MARKDOWN_LINK_RE = re.compile(r'\[([^\]\n]+)\]\(([^)\n]*)\)')
_PARENTHETICAL_RE = re.compile(r'(?<!\])\(((?:[^()\n]|\([^()\n]*\))+)\)')
_SAFE_MARKDOWN_SCHEMES = {'http', 'https', 'mailto'}
_REMOVAL_MARKER = '\x00'


def _id_pattern(source_id: str) -> re.Pattern[str]:
    return re.compile(rf'(?<![\w-]){re.escape(source_id)}(?![\w-])')


def _citation_token_id(token: str, valid_ids: set[str]) -> Optional[str]:
    token = token.strip()
    if token in valid_ids:
        return token
    match = _MARKDOWN_LINK_RE.fullmatch(token)
    if match and match.group(1).strip() in valid_ids:
        return match.group(1).strip()
    return None


def _clean_after_removal(text: str) -> str:
    marker = re.escape(_REMOVAL_MARKER)
    text = re.sub(rf'[ \t]+{marker}[ \t]+', ' ', text)
    text = re.sub(rf'[ \t]+{marker}(?=[,.;:]|\n|$)', '', text)
    text = re.sub(rf'{marker}[ \t]+', '', text)
    text = text.replace(_REMOVAL_MARKER, '')
    return text.strip()


def _normalize_section_citations(
    body: str, source_ids: list[str], valid_ids: set[str], report: PresentationContractReport
) -> tuple[str, list[str]]:
    recovered: list[str] = []
    changed = False

    def recover_parenthetical(match: re.Match[str]) -> str:
        nonlocal changed
        tokens = [token for token in re.split(r'\s*[;,]\s*', match.group(1)) if token.strip()]
        ids = [_citation_token_id(token, valid_ids) for token in tokens]
        if tokens and all(ids):
            recovered.extend(source_id for source_id in ids if source_id is not None)
            report.repairs.add('inline_source_citation')
            changed = True
            return _REMOVAL_MARKER
        return match.group(0)

    body = _PARENTHETICAL_RE.sub(recover_parenthetical, body)

    def normalize_link(match: re.Match[str]) -> str:
        nonlocal changed
        label = match.group(1).strip()
        destination = match.group(2).strip()
        if label in valid_ids:
            recovered.append(label)
            report.repairs.add('inline_source_citation')
            changed = True
            return _REMOVAL_MARKER
        scheme = destination.split(':', 1)[0].casefold() if ':' in destination else ''
        if scheme not in _SAFE_MARKDOWN_SCHEMES:
            report.repairs.add('unsafe_markdown_link')
            changed = True
            return label
        return match.group(0)

    body = _MARKDOWN_LINK_RE.sub(normalize_link, body)
    merged = _validate_source_segment_ids([*source_ids, *recovered], valid_ids)
    return (_clean_after_removal(body) if changed else body), merged


def visible_text_fields(structured: Structured) -> list[tuple[Any, str]]:
    fields: list[tuple[Any, str]] = [(structured, 'title'), (structured, 'overview')]
    for section in structured.sections:
        fields.extend(((section, 'heading'), (section, 'body_markdown')))
    for item in structured.action_items:
        fields.append((item, 'description'))
        if item.owner_name is not None:
            fields.append((item, 'owner_name'))
        if item.context is not None:
            fields.append((item, 'context'))
    for event in structured.events:
        fields.extend(((event, 'title'), (event, 'description')))
    for participant in structured.participants:
        for attribute in ('name', 'organization', 'role'):
            if getattr(participant, attribute, None) is not None:
                fields.append((participant, attribute))
    for insight in structured.insights:
        fields.append((insight, 'text'))
    return fields


def enforce_structured_presentation_contract(
    structured: Structured,
    transcript_segment_ids: Optional[Iterable[object]],
    *,
    safe_fallback: bool = False,
) -> PresentationContractReport:
    """Keep internal evidence identifiers out of user-visible generated notes.

    Citation-only syntax is repaired deterministically and moved into the typed
    evidence field. A known source ID in ordinary prose is ambiguous and asks
    the caller for one revision pass. ``safe_fallback`` removes that identifier
    after the revision budget is exhausted. Unknown UUID-like text is preserved.
    """

    report = PresentationContractReport()
    valid_ids = {
        segment_id for segment_id in (transcript_segment_ids or ()) if isinstance(segment_id, str) and segment_id
    }
    for section in structured.sections:
        before = list(section.source_segment_ids)
        section.body_markdown, section.source_segment_ids = _normalize_section_citations(
            section.body_markdown, section.source_segment_ids, valid_ids, report
        )
        if _validate_source_segment_ids(before, valid_ids) != before:
            report.repairs.add('invalid_source_reference')
    for action_item in structured.action_items:
        before = list(action_item.source_segment_ids)
        action_item.source_segment_ids = _validate_source_segment_ids(action_item.source_segment_ids, valid_ids)
        if action_item.source_segment_ids != before:
            report.repairs.add('invalid_source_reference')

    for owner, attribute in visible_text_fields(structured):
        value = getattr(owner, attribute, '') or ''
        for source_id in valid_ids:
            pattern = _id_pattern(source_id)
            if not pattern.search(value):
                continue
            if safe_fallback:
                value = _clean_after_removal(pattern.sub(_REMOVAL_MARKER, value))
                report.repairs.add('source_id_in_prose')
            else:
                report.violations.add('source_id_in_prose')
        setattr(owner, attribute, value)

    before_fields = [getattr(owner, attribute, '') for owner, attribute in visible_text_fields(structured)]
    sanitize_structured_speaker_placeholders(structured)
    after_fields = [getattr(owner, attribute, '') for owner, attribute in visible_text_fields(structured)]
    if before_fields != after_fields:
        report.repairs.add('speaker_placeholder')
    return report


# Diarization placeholders are transcript machinery, not people. Prompt wording alone
# does not hold — v2 already forbade "Speaker 1 said that" and still leaked the token.
# `spk N` is the compact speaker-map key (SCA-454) and leaks the same way.
_SPEAKER_PLACEHOLDER_RE = re.compile(r'(?i)\b(?:spk|speaker)[ _]\d+\b:?[ \t]*')


def strip_speaker_placeholders(text: str) -> str:
    """Drop leftover Speaker N / SPEAKER_00 tokens rather than inventing a name."""
    if not text or not _SPEAKER_PLACEHOLDER_RE.search(text):
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
