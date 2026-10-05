"""Bounded optional selection pass; writer receives only original selected evidence."""

import json
from datetime import timezone
from typing import Any

from config.episode_writer import EpisodeWriterSettings
from utils.conversations.episode_compaction import compact_episode_items
from utils.conversations.episode_selection import (
    SELECTION_PROMPT,
    deterministic_episode_selection,
    selected_episode_items,
    selection_payload,
    model_selection_allowed,
)


def bind_episode_effort(model: Any, effort: str) -> Any:
    if effort == 'default':
        return model
    underlying = getattr(model, 'bound', model)
    name = getattr(underlying, 'model_name', None) or getattr(underlying, 'model', None)
    if isinstance(name, str) and not (
        name.rsplit('/', 1)[-1].startswith(('gpt-5.6', 'gpt-6'))
        or type(underlying).__module__ == 'utils.llm.gateway_client'
    ):
        # BYOK can resolve this feature to another provider/model. Keep its own options.
        from utils.llm.notes_observability import current_run
        from utils.observability.fallback import record_fallback

        run = current_run()
        if run is not None:
            run.effort = 'default'
            run.violations.add('effort_unsupported_model')
        record_fallback(
            component='conversation_notes',
            from_mode='episode_effort',
            to_mode='model_default',
            reason='local_heal',
            outcome='degraded',
        )
        return model
    return model.bind(reasoning_effort=effort)


def episode_input_bytes(messages) -> int:
    """Measure text/image payload locally, without tokenizer downloads or model calls."""
    total = 0
    for message in messages:
        content = message.content
        blocks = content if isinstance(content, list) else [content]
        for block in blocks:
            if isinstance(block, dict) and block.get('type') == 'text':
                block = block.get('text', '')
            text = block if isinstance(block, str) else json.dumps(block, ensure_ascii=False)
            total += len(text.encode('utf-8'))
    return total


def episode_finish_local_iso(finished_at, user_tz):
    if finished_at is None:
        return None
    aware = finished_at if finished_at.tzinfo else finished_at.replace(tzinfo=timezone.utc)
    return aware.astimezone(user_tz).isoformat()


def episode_budget_exceeded(messages, settings, run) -> bool:
    size = episode_input_bytes(messages)
    if run is not None:
        run.estimated_input_bytes = size
    return settings.effort in {'high', 'xhigh'} and size > settings.thinking_max_input_bytes


def baseline_budget_fallback(notes_fn, run, prefix, **kwargs):
    """Reuse the same receipt and original rich inputs; never buy a timed-out writer first."""
    from utils.observability.fallback import record_fallback

    if run is not None:
        run.arm = 'baseline_budget'
        run.effort = 'default'
        run.claims_enabled = False
        run.violations.add('thinking_input_baseline')
    record_fallback(
        component='conversation_notes',
        from_mode='episode_notes',
        to_mode='baseline_budget',
        reason='local_heal',
        outcome='degraded',
    )
    return notes_fn(prefix, **kwargs)


def prepare_episode_evidence(items, settings: EpisodeWriterSettings, *, started_at, finished_at, run, model_factory):
    items = compact_episode_items(items)
    if settings.selection == 'compact':
        return items
    conservative = deterministic_episode_selection(items, finished_at=finished_at)
    if settings.selection == 'deterministic':
        return conservative
    # Do not buy another full-context call for a large meeting.
    if not model_selection_allowed(items):
        if run is not None:
            run.violations.add('selection_long_input')
        return conservative
    try:
        model = model_factory()
        messages = [
            {'role': 'system', 'content': SELECTION_PROMPT},
            {
                'role': 'user',
                'content': json.dumps(selection_payload(items, started_at, finished_at), ensure_ascii=False),
            },
        ]
        response = run.invoke(model, messages, kind='selection') if run else model.invoke(messages)
        content = response.content
        if not isinstance(content, str):
            raise ValueError('invalid_selection')
        return selected_episode_items(items, json.loads(content), finished_at=finished_at)
    except Exception:
        from utils.observability.fallback import record_fallback

        if run is not None:
            run.violations.add('selection_unavailable')
        record_fallback(
            component='conversation_notes',
            from_mode='episode_selection',
            to_mode='deterministic',
            reason='local_heal',
            outcome='degraded',
        )
        return conservative
