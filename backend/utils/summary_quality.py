"""Shared generated-note policy. No provider calls, transcript reads, or content logging.

Automatic refreshes may update notes but never rename a valid displayed title.
Only empty/placeholder/mechanics titles are replaceable; user edits are authority
at the persistence boundary. This deliberately conservative rule needs no paid
semantic comparison and no transcript fingerprint or title history.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

NOTE_QUALITY_RULES = """Write concrete notes, not narration about a conversation.
State the actual proposal, reason, number with its referent, decision or unresolved question.
Use second person only when the supplied SpeakerRoleMap/owner_attribution authority marks the source as
primary_user (the owner). A raw is_user flag, account name, episode membership, calendar or nearby speech
never establishes owner participation. Unknown voices stay neutral: "someone", "a participant", or a
subject-focused fact with no attribution. Never turn their first-person speech into "you" or an owner fact.
Do not omit a chapter merely because its voices are unknown or is_user=false.
For example: "The pilot budget is $8,000; approval is due Friday", not "a speaker discusses budgets".
Never write "a speaker discusses", "the conversation covers", or "episode notes continue".
Never describe transcript/pipeline/capture mechanics: missing transcript, audio gaps, processing,
recording availability, or insufficient evidence. Omit unsupported content without explaining its absence.
Every title and chapter/moment heading must be non-empty and describe supported subject matter.
Do not invent names, numbers, units, decisions or commitments to make a note specific.
"""

# Match narration of our evidence, not ordinary product topics such as building a
# transcript editor, processing invoices, or measuring an audio-gap detector.
_MECHANICS = re.compile(
    r"\b(?:missing (?:from (?:the )?)?transcript|(?:not|never) (?:in|captured in|present in) (?:the )?transcript|"
    r"transcript (?:is |was |remains )?(?:missing(?! from\b)|unavailable|incomplete|empty)|"
    r"(?:no|without|insufficient) (?:usable )?(?:transcript|transcription|audio evidence)|"
    r"(?:audio|capture|recording|transcription|pipeline) (?:gaps?|missing|unavailable|pending|failures?)|"
    r"(?:still|awaiting|pending|finishing) (?:processing|transcription)|"
    r"(?:not enough|insufficient|lack of) (?:transcript |audio )?evidence|"
    r"(?:a |the )?(?:speaker discusses|conversation covers)|episode notes.*continue)\b",
    re.I,
)
_PLACEHOLDER = re.compile(
    r"^(?:[-—–….*\s]+|(?:new|unknown) moment.*|untitled|none|null|conversation|talking|discussion notes|discussion \d+)$",
    re.I,
)


def safe_text(value: Any) -> str:
    text = value.strip() if isinstance(value, str) else ''
    return '' if _MECHANICS.search(text) else text


def valid_title(value: Any) -> str:
    text = re.sub(r'\s+', ' ', safe_text(value)).strip()
    return '' if not text or _PLACEHOLDER.fullmatch(text) else text


def title_or_fallback(value: Any, *, index: int | None = None) -> str:
    # Do not promote generated bullet text into a factual headline. Neutral
    # numbered labels are deterministic even when every model field is unsafe.
    title = valid_title(value)
    if title:
        return title
    from utils.observability.fallback import record_fallback

    record_fallback(
        component='conversation_notes',
        from_mode='generated_title',
        to_mode='deterministic_title',
        reason='other',
        outcome='degraded',
    )
    return f'Discussion {index}' if index is not None else 'Discussion notes'


def stable_title(previous: Any, proposed: Any, *, index: int | None = None) -> tuple[str, str | None]:
    old = valid_title(previous)
    title = old or title_or_fallback(proposed, index=index)
    reason = None if title == previous else ('initial_title' if not previous else 'invalid_title_repaired')
    return title, reason


def safe_body(value: Any) -> str:
    """Drop unsafe sentences/bullets, keeping unrelated supported specifics."""
    if not isinstance(value, str):
        return ''
    if not _MECHANICS.search(value):
        return value
    return '\n'.join(
        part
        for line in value.splitlines()
        for part in re.split(r'(?<=[.!?])\s+(?=[A-Z])', line)
        if safe_text(part) and part.strip() not in {'-', '*', '•'}
    )


def clean_structured(data: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(data)
    out['title'] = title_or_fallback(out.get('title'))
    for key in ('overview', 'gist'):
        if key in out:
            out[key] = safe_body(out[key])
    sections = []
    raw_sections = out.get('sections')
    for index, section in enumerate(raw_sections if isinstance(raw_sections, list) else [], 1):
        if not isinstance(section, Mapping):
            continue
        section = dict(section)
        section['heading'] = title_or_fallback(section.get('heading'), index=index)
        section['body_markdown'] = safe_body(section.get('body_markdown'))
        if section['body_markdown']:
            sections.append(section)
    if 'sections' in out:
        out['sections'] = sections
    return out


def episode_quality(previous: Mapping[str, Any], proposed: Mapping[str, Any]) -> dict[str, Any]:
    """Apply inside the episode CAS, after membership/deletion handling."""
    out = dict(proposed)
    title, reason = stable_title(previous.get('title'), out.get('title'))
    out['title'] = title
    if reason:
        out['title_change_reason'] = reason
    for key in ('bullets', 'follow_ups', 'open_questions'):
        if key in out:
            out[key] = [text for item in out[key] or [] if (text := safe_body(item))]
    if 'lede' in out:
        out['lede'] = safe_body(out['lede'])
    old_moments = list(previous.get('moments') or [])
    used = set()
    moments = []
    for index, moment in enumerate(out.get('moments') or [], 1):
        moment = dict(moment)
        candidates = []
        for old_index, old in enumerate(old_moments):
            if old_index in used or old.get('conversation_id') != moment.get('conversation_id'):
                continue
            # Match identity first. Composer IDs are regenerated, so tolerate
            # boundary drift only while at least half of both spans overlaps.
            same = bool(old.get('id') and old.get('id') == moment.get('id'))
            a, b = old.get('start_offset'), moment.get('start_offset')
            if a is not None and b is not None:
                same = same or a == b
                end_a, end_b = old.get('end_offset'), moment.get('end_offset')
                if end_a is not None and end_b is not None:
                    overlap = max(0, min(end_a, end_b) - max(a, b))
                    same = same or overlap > 0 and overlap >= 0.5 * max(end_a - a, end_b - b)
            if same:
                candidates.append((abs((a or 0) - (b or 0)), old_index, old))
        matched = min(candidates, key=lambda item: (item[0], item[1])) if candidates else None
        old = matched[2] if matched else {}
        if matched:
            used.add(matched[1])
            if old.get('id'):
                moment['id'] = old['id']
        heading, change = stable_title(old.get('heading'), moment.get('heading'), index=index)
        moment['heading'] = heading
        if change:
            moment['title_change_reason'] = change
        if 'points' in moment:
            moment['points'] = [
                {**point, 'text': text, 'details': [d for v in point.get('details') or [] if (d := safe_body(v))]}
                for point in moment['points'] or []
                if (text := safe_body(point.get('text')))
            ]
        moments.append(moment)
    out['moments'] = moments
    return out
