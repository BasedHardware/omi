"""Archived prompt bytes used only by synthetic episode experiments."""

from typing import Callable, Optional
import logging

logger = logging.getLogger(__name__)


def conversation_notes_volatile_instructions(
    *,
    response_language: str,
    density: str,
    task_intelligence_capture: bool,
    existing_context: str,
    started_local_iso: str,
    current_local_iso: str,
    tz_label: str,
    conversation_context: str,
    wake_word_rules: str = '',
) -> str:
    """Per-call suffix: language, density, dates, open tasks, and the transcript."""
    task_filter = (
        'capture clear commitments and direct requests'
        if task_intelligence_capture
        else 'apply the conservative legacy task filter'
    )
    text = f'''Respond entirely in {response_language}.

- {density} These are flexible guides, not quotas. Prefer one or two substantial bullets per section,
  with connected sentences rather than splitting every sentence into its own bullet.
  Give distinct subtopics room instead of cramming them into a final bullet. Keep the main threads
  while removing minor details if the note grows much beyond the target.
- For task-intelligence capture, {task_filter}.
- Potentially related open tasks:
{existing_context}

DATE CONTEXT
- Conversation local time: {started_local_iso}
- Current local time: {current_local_iso}
- Timezone: {tz_label}

{conversation_context}'''
    if wake_word_rules:
        text = f'{text}\n\n{wake_word_rules}'
    return text


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
