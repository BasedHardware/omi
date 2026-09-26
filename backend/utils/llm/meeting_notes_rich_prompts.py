from __future__ import annotations

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_LEGACY_NOTE_BODY_OPENING = (
    "- Write section bodies as '- ' bullets in plain, readable sentences. Each bullet should group one\n"
    '  coherent point with its useful supporting details. Separate distinct points when combining them\n'
    '  makes reading harder; do not force terse fragments or one bullet per sentence.'
)
_LEGACY_SELECT_THREADS = (
    '- Select the main meaningful threads, including social experiences, problems, reasons, proposals,\n'
    '  decisions, and unresolved questions. Keep concrete details that help recall them. Omit repetition,\n'
    '  incidental tangents, and unclear fragments; do not retain something just because it contains a name\n'
    '  or number. Understandable multilingual content is not noise.'
)
_RICH_NOTE_BODY_OPENING = (
    '- Open each section with a one-line takeaway bullet. Put supporting details in short, specific '
    'bullets (aim for at most 25 words each); use nested `  - ` sub-bullets for detail instead of '
    '40–60-word compound paragraphs. Preserve every supported commitment and concrete detail: '
    'coverage beats brevity.'
)
_RICH_SELECT_THREADS = (
    '- Select the main meaningful threads, including social experiences, problems, reasons, proposals, '
    'decisions, and unresolved questions. Put worthwhile tangents (tools, products, links, '
    'recommendations, memorable personal asides) in one side_notes section rather than dropping them. '
    'Still omit filler, logistics chatter, repetition, and unclear fragments. Understandable '
    'multilingual content is not noise.'
)
_RICH_MEETING_RULES = '''MEETING TITLE AND PEOPLE
- The note title must be at most 70 characters. Never use a raw window title, meeting code, app name, or unread counter as the note title, and never put the account owner's name in it (the note is theirs). When a human counterpart is identified, lead with their name (for example, "Intro with Ash Kalb (via Boardy): founding engineer"); otherwise lead with the topic. Do not invent names.
- A person's name may come only from the roster's display names, from the transcript (self-introductions, being addressed by name), or from background screen text that shows it in the call's participant list or in a profile or document opened during the call. Never turn an email address or handle into a name, and never assume a nameless roster email belongs to a name you saw elsewhere unless the conversation makes that link clear.
- Refer to non-owner humans by name when known. Otherwise use a role grounded in this conversation (for example, "the candidate"), never a speaker key. Never infer anyone's gender from a name or voice: use their name or "they" unless the conversation itself states their pronouns.
- Set a participant's organization when the conversation, a non-freemail email domain, or background screen text (for example, a profile headline opened during the call) states it, and use that spelling in the note. Treat an AI agent as a separate speaker: attribute introductions, facilitation, and stepping out to that agent when the content supports it; never merge its words into a human's.
- Fill participants from the roster and transcript evidence. Exclude the account owner. Keep a roster-only human nameless when only an email is known; never guess their name. Set role to at most eight words grounded in this conversation. Set meeting_type only to interview, intro, sales, customer, one_on_one, team_sync, planning, demo, social, or other.
- A request the account owner makes of another participant that they accept (for example, "keep an eye out for introductions") is an action item owned by that participant.
- When the transcript makes an action item's owner clear, set owner_name to that participant's name, including the account owner's name for their own commitments. If the owner is clear but has no known name, set owner_name to their short role from this conversation (for example, "Candidate").
SIDE NOTES AND BACKGROUND
- At most one section has kind side_notes: place it last with heading Side notes and 1–4 short bullets on worthwhile tangents. Keep main threads in main sections; do not put prior-meeting links or goals into sections.
- BACKGROUND CONTEXT (not part of this conversation) may help identify people, spell names/products/companies, and connect prior commitments; it was NOT said in this meeting. Never state a background fact as something said here. Do not summarize screen text that was not discussed: use it only to spell names/products correctly and identify what was shown.
- Prior-meeting links and goal relevance go ONLY in insights, never in sections or overview. Insights are private: at most four, each at most 30 words, each grounded in supplied background context. An insight must be specific and useful to act on (an open item from a prior meeting with this person, a concrete link between what was said and a named goal or fact); never restate a goal generically or say a topic "aligns with" a goal. Return [] when nothing specific qualifies or no background context exists.'''


def rich_static_instructions(format_instructions: str, legacy_static: Callable[[str], str]) -> str:
    base = legacy_static(format_instructions)
    # Rewrites anchor on exact legacy wording. If that wording drifts, keep producing a
    # note (the rich rules still append) and log loudly; a unit test pins the anchors.
    for anchor, label in ((_LEGACY_NOTE_BODY_OPENING, 'note body'), (_LEGACY_SELECT_THREADS, 'select threads')):
        if anchor not in base:
            logger.error('rich meeting notes: legacy %s anchor missing; keeping legacy wording', label)
    if base.count(format_instructions) != 1:
        logger.error('rich meeting notes: format instructions anchor count %d', base.count(format_instructions))
        return f'{base}\n\n{_RICH_MEETING_RULES}'
    text = base.replace(_LEGACY_NOTE_BODY_OPENING, _RICH_NOTE_BODY_OPENING)
    text = text.replace(_LEGACY_SELECT_THREADS, _RICH_SELECT_THREADS)
    return text.replace(format_instructions, f'{_RICH_MEETING_RULES}\n\n{format_instructions}')


def _rich_density_bullet(density: str) -> str:
    return (
        f'- {density} These are flexible guides, not quotas. Use a one-line takeaway plus short '
        'supporting bullets (aim at most 25 words per bullet); nest details with `  - `. Coverage '
        'beats brevity: keep every commitment and specific even when the note grows beyond the target.\n'
        '- Pronouns: write people by name (or "they"). Do not use he/she/his/her for anyone, including the '
        'account owner, unless the conversation states that person\'s pronouns.'
    )


def _legacy_density_bullet(density: str) -> str:
    return (
        f'- {density} These are flexible guides, not quotas. Prefer one or two substantial bullets '
        'per section,\n  with connected sentences rather than splitting every sentence into its own '
        'bullet.\n  Give distinct subtopics room instead of cramming them into a final bullet. Keep '
        'the main threads\n  while removing minor details if the note grows much beyond the target.'
    )


def rich_volatile_instructions(
    *,
    legacy_volatile: Callable[..., str],
    response_language: str,
    density: str,
    task_intelligence_capture: bool,
    existing_context: str,
    started_local_iso: str,
    current_local_iso: str,
    tz_label: str,
    conversation_context: str,
    meeting_context: Optional[str],
    wake_word_rules: str = '',
) -> str:
    text = legacy_volatile(
        response_language=response_language,
        density=density,
        task_intelligence_capture=task_intelligence_capture,
        existing_context=existing_context,
        started_local_iso=started_local_iso,
        current_local_iso=current_local_iso,
        tz_label=tz_label,
        conversation_context=conversation_context,
        wake_word_rules=wake_word_rules,
    )
    legacy_density = _legacy_density_bullet(density)
    if legacy_density not in text:
        logger.error('rich meeting notes: legacy density anchor missing; keeping legacy density wording')
    text = text.replace(legacy_density, _rich_density_bullet(density))
    if meeting_context and meeting_context.strip():
        text = f'{text}\n\n{meeting_context.strip()}'
    return text
