"""Shared generated-note policy. No provider calls, transcript reads, or content logging.

Automatic refreshes retain valid titles until at least 40% of their current content
units arrived since the title was set (and at least 20 units were added). User
edits always win. Legacy titles bootstrap a numeric basis without renaming.
"""

from __future__ import annotations

import re
from copy import deepcopy
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
Never narrate the current capture's transcript/pipeline mechanics: missing transcript, audio gaps,
processing, recording availability, or insufficient evidence. Omit unsupported content without explaining
its absence. Preserve supported subject-matter work, such as fixing software pipeline failures.
Every title and chapter/moment heading must be non-empty and describe supported subject matter.
In the same response emit quality_flags: [] when no availability narration remains. If any output field
still states that THIS capture cannot be summarized/processed because its transcript/audio/recording is
unavailable, emit an entry in quality_flags with field set to that.field.path and kind set to capture_availability.
A flag without statement classifies the WHOLE field as availability-only. If a field mixes real notes
with availability narration, also set statement to the EXACT availability-only sentence or bullet;
never classify the real notes as availability. Preserve every other supported sentence/bullet.
Classify meaning in EVERY output language, including Japanese. Paths use zero-based array indices, e.g.
sections.0.body_markdown, bullets.0, chapters.0.points.0.text. Never flag subject-matter evidence,
scientific/legal uncertainty, or work on transcription/audio products; these are useful notes.
Do not invent names, numbers, units, decisions or commitments to make a note specific.
"""

# Availability statements about this capture, never generic evidence/technical topics.
_MECHANICS = re.compile(
    r"\b(?:missing from (?:the )?transcript(?:[.!?]|$)|"
    r"(?:not|never) (?:in|captured in|present in) (?:the )?transcript(?:[.!?]|$)|"
    r"^(?:(?:the |this |our )?transcript (?:is |was |remains )?"
    r"(?:missing|unavailable|incomplete|empty)|missing transcript)[.!]?$|"
    r"^(?:this |the |our )?(?:audio|capture|recording|transcription) "
    r"(?:is |was |remains )?(?:missing|unavailable|pending|incomplete)[.!]?$|"
    r"(?:audio gaps?|pipeline failures?) (?:prevent|preclude) (?:a |the )?(?:recap|summary|notes)\b|"
    r"^(?:still|awaiting|pending|finishing) (?:processing|transcription) (?:the |this |our )?"
    r"(?:recording|capture|audio|transcript)[.!]?$|"
    r"(?:no|insufficient|without) (?:usable )?(?:transcript|audio|recording) (?:evidence |content )?"
    r"(?:is available|to (?:summarize|recap)|for (?:a |the )?(?:summary|recap)))",
    re.I,
)
_META_NARRATION = re.compile(
    r"\b(?:(?:a |the )?(?:speaker discusses|conversation covers)|episode notes.*continue)\b", re.I
)
_JAPANESE_MECHANICS = re.compile(
    r"(?:文字起こし|書き起こし|録音|音声)(?:が|は)(?:ない|無い|ありません|不足|利用でき|存在しない)"
    r"[^。！？\n]{0,45}(?:要約でき|まとめられ|内容を確認でき)|"
    r"^(?:文字起こし|書き起こし|録音|音声)(?:が|は)(?:ありません|利用できません|欠落しています)[。！]?$"
)
# The same-call structured signal handles any language, including unspaced scripts.
_QUALITY_PATH = re.compile(
    r"^(?:title|overview|gist|moment_heading|lede|(?:bullets|follow_ups|open_questions)\.\d+|"
    r"sections\.\d+\.(?:heading|body_markdown)|"
    r"(?:chapters|moments)\.\d+\.(?:title|heading|summary|points\.\d+\.(?:text|details\.\d+)))$"
)


def capture_availability(value: Any) -> bool:
    return isinstance(value, str) and any(
        _MECHANICS.search(part.strip().lstrip('-*• ')) or _JAPANESE_MECHANICS.search(part.strip().lstrip('-*• '))
        for part in re.split(r'\n|(?<=[.!?])\s+(?=[A-Z])|(?<=[。！？])', value)
    )


def _drop_flagged_text(value: str, flag: Mapping[str, Any]) -> str:
    statement = flag.get('statement')
    if statement is None:
        return ''
    if not isinstance(statement, str) or not statement.strip() or len(statement) > 4000 or statement not in value:
        return value
    # Exact spans only: a paraphrase or invalid offset cannot erase useful content.
    return '\n'.join(
        line for line in value.replace(statement, '').splitlines() if line.strip() not in {'-', '*', '•'}
    ).strip()


def filter_output(data: Mapping[str, Any]) -> dict[str, Any]:
    """Consume generated field-path classifications; they never reach client/storage models."""
    out = deepcopy(dict(data))
    flags = out.pop('quality_flags', [])
    for flag in flags[:64] if isinstance(flags, list) else []:
        if not isinstance(flag, Mapping) or flag.get('kind') != 'capture_availability':
            continue
        path = flag.get('field')
        if not isinstance(path, str) or len(path) > 120 or not _QUALITY_PATH.fullmatch(path):
            continue
        parts = path.split('.')
        node: Any = out
        try:
            for part in parts[:-1]:
                node = node[int(part)] if isinstance(node, list) else node[part]
            if isinstance(node, list):
                index = int(parts[-1])
                if isinstance(node[index], str):
                    node[index] = _drop_flagged_text(node[index], flag)
            elif isinstance(node, dict):
                name = parts[-1]
                if isinstance(node.get(name), str):
                    node[name] = _drop_flagged_text(node[name], flag)
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return out


_PLACEHOLDER = re.compile(
    r"^(?:[-—–….*\s]+|(?:new|unknown) moment.*|untitled|none|null|in progress|processing[.…]*|transcribing[.…]*|writing notes[.…]*|conversation|talking|discussion notes|discussion \d+)$",
    re.I,
)


def safe_text(value: Any) -> str:
    text = value.strip() if isinstance(value, str) else ''
    return '' if capture_availability(text) or _META_NARRATION.search(text) else text


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


def content_units(segments: Any) -> int:
    """Word units, with CJK characters counted separately; no text/hash history is stored."""
    return sum(
        len(
            re.findall(
                r'[\u3040-\u30ff\u3400-\u9fff]|[^\W_]+',
                str(segment.get('text', '') if isinstance(segment, Mapping) else getattr(segment, 'text', '')),
            )
        )
        for segment in segments or []
    )


def stable_title(
    previous: Any,
    proposed: Any,
    *,
    index: int | None = None,
    previous_units: float = 0,
    current_units: float = 0,
) -> tuple[str, str | None]:
    old = valid_title(previous)
    growth = max(0, current_units - previous_units)
    material = previous_units > 0 and growth >= 20 and growth >= 0.4 * current_units
    replacement = valid_title(proposed)
    title = replacement if old and material and replacement else old or title_or_fallback(proposed, index=index)
    reason = (
        None
        if title == previous
        else ('material_content_growth' if old else 'initial_title' if not previous else 'invalid_title_repaired')
    )
    return title, reason


def title_basis(previous: Any, current: float, reason: str | None) -> float:
    return current if reason or not isinstance(previous, (int, float)) or previous <= 0 else previous


def safe_body(value: Any) -> str:
    """Drop unsafe sentences/bullets, keeping unrelated supported specifics."""
    if not isinstance(value, str):
        return ''
    if not capture_availability(value) and not _META_NARRATION.search(value):
        return value
    return '\n'.join(
        part
        for line in value.splitlines()
        for part in re.split(r'(?<=[.!?])\s+(?=[A-Z])|(?<=[。！？])', line)
        if safe_text(part) and part.strip() not in {'-', '*', '•'}
    )


def clean_structured(data: Mapping[str, Any]) -> dict[str, Any]:
    out = filter_output(data)
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
    if (
        not previous.get('title')
        and not out.get('title')
        and not any(out.get(key) for key in ('bullets', 'lede', 'moments'))
    ):
        # An unprocessed episode must keep its honest pending presentation.
        out['title'] = ''
    else:
        units = out.get('content_word_units', previous.get('content_word_units', 0)) or 0
        title, reason = stable_title(
            previous.get('title'),
            out.get('title'),
            previous_units=previous.get('title_content_units') or 0,
            current_units=units,
        )
        out['title'] = previous.get('user_title') or out.get('user_title') or title
        if units or previous.get('title_content_units'):
            out['title_content_units'] = title_basis(previous.get('title_content_units'), units, reason)
        if reason and not (previous.get('user_title') or out.get('user_title')):
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
        span = max(0, (moment.get('end_offset') or 0) - (moment.get('start_offset') or 0))
        old_span = max(0, (old.get('end_offset') or 0) - (old.get('start_offset') or 0))
        heading, change = stable_title(
            old.get('heading'),
            moment.get('heading'),
            index=index,
            previous_units=old.get('title_span_seconds', old_span),
            current_units=span,
        )
        if old and span and (span != old_span or old.get('title_span_seconds')):
            moment['title_span_seconds'] = title_basis(old.get('title_span_seconds', old_span), span, change)
        moment['heading'] = old.get('user_title') or moment.get('user_title') or heading
        if change and not (old.get('user_title') or moment.get('user_title')):
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
