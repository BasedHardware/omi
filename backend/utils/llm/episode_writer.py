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
        content = message.get('content') if isinstance(message, dict) else message.content
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
    return (
        settings.thinking_max_input_bytes > 0
        and settings.effort in {'high', 'xhigh'}
        and size > settings.thinking_max_input_bytes
    )


def baseline_budget_fallback(notes_fn, run, prefix, inputs):
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
    names = (
        'started_at',
        'language_code',
        'output_language_code',
        'tz',
        'task_intelligence_capture',
        'existing_action_items',
        'trusted_wake_word_markers',
        'meeting_context',
        'rich_context_enabled',
        'roster',
    )
    return notes_fn(prefix, **{name: inputs[name] for name in names}, screen_frames=inputs['original_screen_frames'])


def prepare_episode_evidence(items, settings: EpisodeWriterSettings, *, started_at, finished_at, run, model_factory):
    items = compact_episode_items(items)
    if settings.selection == 'compact':
        return items
    conservative = deterministic_episode_selection(items, finished_at=finished_at)
    if settings.selection == 'deterministic':
        return conservative
    if settings.selection == 'jev':
        return prepare_jev_evidence(items, settings, started_at=started_at, finished_at=finished_at, run=run)
    # Do not buy another full-context call for a large meeting.
    if not model_selection_allowed(items):
        if run is not None:
            run.actual_selection = 'deterministic'
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
            run.actual_selection = 'deterministic'
            run.violations.add('selection_unavailable')
        record_fallback(
            component='conversation_notes',
            from_mode='episode_selection',
            to_mode='deterministic',
            reason='local_heal',
            outcome='degraded',
        )
        return conservative


def prepare_jev_evidence(items, settings, *, started_at, finished_at, run):
    from utils.conversations.episode_jev import LANE, evidence_question_batches, scored_episode_items
    from utils.llm.jev_client import ask_jev
    from utils.observability.fallback import record_fallback

    try:
        batches = evidence_question_batches(items, started_at=started_at, finished_at=finished_at)
        scores = {}
        for batch in batches:
            if run is not None:
                run.jev_calls += 1
            answers = ask_jev(batch.state, batch.questions, lane=LANE, max_attempts=1)
            if answers is None:
                if run is not None:
                    run.add_jev_usage({})
                raise ValueError('jev_unavailable')
            if run is not None:
                run.add_jev_usage(answers.usage)
            scores.update({q: answers.noul(q) for q in batch.questions})
        if run is not None:
            run.actual_selection = 'jev'
        return scored_episode_items(items, batches, scores, threshold=settings.jev_threshold, finished_at=finished_at)
    except Exception:
        if run is not None:
            run.actual_selection = 'deterministic'
            run.violations.add('jev_unavailable')
        record_fallback(
            component='conversation_notes',
            from_mode='jev_selection',
            to_mode='deterministic',
            reason='local_heal',
            outcome='degraded',
        )
        return deterministic_episode_selection(items, finished_at=finished_at)


def episode_runtime_settings(items, settings, run):
    from dataclasses import replace
    from utils.conversations.episode_runtime import durable_episode_job
    from utils.conversations.episode_tiers import episode_tier

    settings, tier, reason = episode_tier(items, settings)
    durable = durable_episode_job()
    configured = settings.c6_timeout if tier == 'C6' else settings.writer_timeout
    # The existing gateway route is 120s; leave transport headroom, without raising it.
    deadline = min(configured, 115 if tier == 'C6' else 120) if durable else min(configured, 60)
    if tier == 'C6' and not durable:
        settings, tier, reason = replace(settings, effort='default'), 'C7', 'synchronous_outer_limit'
    if run is not None:
        run.tier, run.route_reason = tier, reason
        run.writer_deadline, run.configured_deadline = deadline, configured
        run.effort = settings.effort
        if deadline < configured:
            run.violations.add('outer_deadline_clamped')
    return settings, deadline


def invoke_episode_writer(model, messages, settings, run, *, fallback_factory, deadline):
    from dataclasses import replace
    from utils.observability.fallback import record_fallback

    try:
        return run.invoke(model, messages) if run else model.invoke(messages), settings
    except Exception as exc:
        # Retry only a deadline/context-limit failure, never quota/auth/provider refusal.
        name = type(exc).__name__
        timeout = isinstance(exc, TimeoutError) or name in {'APITimeoutError', 'ReadTimeout', 'TimeoutException'}
        code = getattr(exc, 'code', None)
        if settings.effort != 'xhigh' or not (timeout or code == 'context_length_exceeded'):
            raise
        if run is not None:
            run.tier_fallback = True
            run.effort = 'default'
            run.violations.add('c6_timeout' if timeout else 'c6_oversize')
            run.repair_disabled = True
        record_fallback(
            component='conversation_notes',
            from_mode='C6',
            to_mode='C7',
            reason='timeout' if timeout else 'local_heal',
            outcome='degraded',
        )
        fallback = replace(settings, effort='default')
        from utils.conversations.episode_runtime import durable_episode_job

        fallback_deadline = min(settings.writer_timeout, 120 if durable_episode_job() else 60)
        if run is not None:
            run.writer_deadline = fallback_deadline
        model = fallback_factory(fallback_deadline)
        return (run.invoke(model, messages) if run else model.invoke(messages)), fallback


def episode_retry_model(get_llm, cache_key, cache_options, timeout, effort='default'):
    return bind_episode_effort(
        get_llm(
            'conv_structure',
            cache_key=cache_key,
            prompt_cache_options=cache_options,
            request_timeout=timeout,
            max_retries=0,
        ),
        effort,
    )
