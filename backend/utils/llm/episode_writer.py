"""Bounded optional selection pass; writer receives only original selected evidence."""

import json
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
    return model if effort == 'default' else model.bind(reasoning_effort=effort)


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
