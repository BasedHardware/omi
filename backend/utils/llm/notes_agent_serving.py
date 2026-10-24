"""Serve agentic notes for an eligible conversation, or return None for the one-shot path.

Called only from the shaped notes writer. Every failure (gateway capability not
yet deployed, provider error, deadline, no submission) records a fallback and
returns None, so the existing one-shot call writes the notes instead.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional, Sequence

from langchain_openai import ChatOpenAI

from utils.byok import has_byok_keys
from utils.conversations.notes_agent_tools import NotesToolbox, build_packet, owner_profile
from utils.llm.meeting_notes_rich_prompts import NotesFrameImage
from utils.llm.notes_agent import langchain_complete, record_decision, record_run, run_notes_agent
from config.refactor_modes import serving_for
from utils.llm.notes_packet import select_notes_packet
from utils.llm.notes_agent_policy import plan_notes_agent
from utils.llm.notes_lengths import length_guide
from utils.llm.notes_agent_prompt import (
    PROMPT_VERSION,
    cache_key_material,
    conversation_seed,
    owner_message,
)
from utils.llm.prompt_cache import (
    EXPLICIT_CACHE_OPTIONS,
    gpt56_explicit_cache_enabled,
    model_supports_explicit_cache,
    prefix_cache_key,
)
from utils.llm.shaped_notes_transport import isolated_notes_model
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

# Speech rate used only to bound the screen/calendar window when the caller has no end time.
_WORDS_PER_MINUTE = 150


def naming_leads(packet: Mapping[str, Any]) -> list[str]:
    """Names strong enough that a note naming nobody is sent back once to check them."""
    names = [
        lead['name']
        for lead in packet.get('people_on_screen') or []
        if {'call_window', 'profile_page'} & set(lead.get('evidence') or ())
    ]
    names += [
        entry['name']
        for entry in packet.get('listed_participants') or []
        if entry.get('kind') == 'human' and entry.get('name')
    ]
    return list(dict.fromkeys(names))[:6]


def transport_ready(model: Any) -> bool:
    """Tools ride only the managed OpenAI-compatible gateway lane; BYOK and direct routes stay one-shot."""
    return isinstance(model, ChatOpenAI) and gpt56_explicit_cache_enabled() and not has_byok_keys()


def _window_end(started_at: datetime, finished_at: Any, words: int) -> datetime:
    if isinstance(finished_at, datetime):
        end = finished_at if finished_at.tzinfo else finished_at.replace(tzinfo=timezone.utc)
        if end >= started_at:
            return end
    return started_at + timedelta(minutes=max(5, words // _WORDS_PER_MINUTE))


def agentic_notes_payload(
    *,
    uid: Optional[str],
    prefix: Any,
    model: Any,
    capture_evidence: str,
    words: int,
    frames: Sequence[NotesFrameImage],
    kwargs: Mapping[str, Any],
) -> Optional[dict[str, Any]]:
    """A validated ``submit_notes`` payload, or None to keep the one-shot path."""
    roster = kwargs.get('roster')
    decision = plan_notes_agent(
        uid=uid,
        conversation_id=prefix.conversation_id,
        words=words,
        has_calendar=roster is not None,
        has_call_screen=bool(frames) or bool(kwargs.get('desktop_meeting_capture')),
        capture_sources=len(kwargs.get('capture_sources') or ()) or 1,
        transport_ready=bool(uid) and transport_ready(model),
    )
    record_decision(decision.reason)
    if not decision.run or decision.budget is None or not uid:
        return None
    budget = decision.budget
    try:
        started_at = kwargs['started_at']
        started_at = started_at if started_at.tzinfo else started_at.replace(tzinfo=timezone.utc)
        finished_at = _window_end(started_at, kwargs.get('finished_at'), words)
        open_tasks = list(kwargs.get('existing_action_items') or [])
        owner_name = prefix.account_owner_name or next(iter(prefix.owner_names), None)
        owner_names = tuple(name for name in (owner_name, *prefix.owner_names) if name)
        explicit_cache = model_supports_explicit_cache(model)
        owner = owner_message(
            lexicon=prefix.known_spellings,
            owner_name=owner_name,
            owner_profile=owner_profile(uid),
            explicit_cache=explicit_cache,
        )
        packet, seen = build_packet(
            uid=uid,
            conversation_id=prefix.conversation_id,
            started_at=started_at,
            finished_at=finished_at,
            timezone_name=kwargs.get('tz') or '',
            response_language=kwargs.get('output_language_code') or kwargs.get('language_code') or 'en',
            length=length_guide(words),
            transcript_words=words,
            account_owner_name=owner_name,
            task_intelligence_capture=bool(kwargs.get('task_intelligence_capture')),
            open_tasks=open_tasks,
            roster=roster,
            owner_names=owner_names,
            background=kwargs.get('meeting_context'),
            frames=frames,
            capture_sources=tuple(kwargs.get('capture_sources') or ()),
        )
        packet = select_notes_packet(
            packet, prefix=prefix, uid=uid, capture_evidence=capture_evidence, words=words, inputs=kwargs
        )
        seed = conversation_seed(packet, capture_evidence, explicit_cache=explicit_cache)
        toolbox = NotesToolbox(
            uid=uid,
            conversation_id=prefix.conversation_id,
            started_at=started_at,
            finished_at=finished_at,
            frames=tuple(frames),
            seen_conversations=set(seen),
        )
        # Per-user routing key over the stable bytes only; the gateway scopes it to the owner again.
        cache_key = (
            prefix_cache_key(PROMPT_VERSION, cache_key_material(owner), owner_uid=uid) if explicit_cache else None
        )

        async def invoke():
            async with isolated_notes_model(model) as isolated_model:
                complete = langchain_complete(
                    isolated_model,
                    cache_options=EXPLICIT_CACHE_OPTIONS if explicit_cache else None,
                    cache_key=cache_key,
                )
                return await run_notes_agent(
                    uid=uid,
                    owner=owner,
                    seed=seed,
                    complete=complete,
                    toolbox=toolbox,
                    budget=budget,
                    transcript_words=words,
                    open_tasks=open_tasks,
                    owner_names=owner_names,
                    naming_leads=() if serving_for('NOTES_PACKET_V2_MODE', uid) else naming_leads(packet),
                    contract_v2=serving_for('NOTES_PACKET_V2_MODE', uid),
                    transcript_segment_ids=prefix.transcript_segment_ids,
                )

        result = asyncio.run(invoke())
    except Exception as error:  # noqa: BLE001 - the one-shot path still writes the notes
        reason = 'capability_mismatch' if 'capability' in type(error).__name__.lower() else 'other'
        logger.warning('conversation notes agent failed uid=%s error=%s', uid, type(error).__name__)
        record_fallback(
            component='conversation_notes', from_mode='agent', to_mode='one_shot', reason=reason, outcome='degraded'
        )
        return None
    record_run(result)
    if result.submission is None:
        record_fallback(
            component='conversation_notes',
            from_mode='agent',
            to_mode='one_shot',
            reason='timeout' if result.stop == 'deadline' else 'malformed',
            outcome='degraded',
        )
        return None
    return result.submission
