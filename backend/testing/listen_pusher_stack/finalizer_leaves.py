"""Controlled provider leaves for the durable finalization worker harness."""

from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path
from typing import Any

from models.conversation_enums import ConversationStatus
from utils.conversations import finalizer
from utils.conversations import lifecycle as lifecycle_service
from utils.conversations.enrichment_plan import RequiredEnrichmentEffect

_failure_budget: dict[str, int] = {}


def _record(event: dict[str, Any]) -> None:
    state_dir = os.getenv('OMI_STACK_STATE_DIR')
    if not state_dir:
        return
    path = Path(state_dir) / 'finalizer.jsonl'
    with path.open('a', encoding='utf-8') as output:
        output.write(json.dumps(event, sort_keys=True) + '\n')


def _parse_failure_budget() -> dict[str, int]:
    raw = os.getenv('OMI_STACK_FINALIZATION_FAILURES', '{}')
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError('OMI_STACK_FINALIZATION_FAILURES must be JSON') from error
    if not isinstance(payload, dict) or set(payload) - {'process', 'integration'}:
        raise RuntimeError('OMI_STACK_FINALIZATION_FAILURES supports only process and integration budgets')
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in payload.values()):
        raise RuntimeError('OMI_STACK_FINALIZATION_FAILURES values must be non-negative integers')
    return {stage: int(payload.get(stage, 0)) for stage in ('process', 'integration')}


def _consume_failure(stage: str, conversation_id: str, **metadata: Any) -> bool:
    remaining = _failure_budget.get(stage, 0)
    if remaining <= 0:
        return False
    _failure_budget[stage] = remaining - 1
    _record(
        {
            'event': 'provider_leaf',
            'stage': stage,
            'outcome': 'controlled_failure',
            'conversation_id': conversation_id,
        }
        | metadata
    )
    return True


def _offline_process_conversation(uid: str, _language: str, conversation: Any, **kwargs: Any) -> Any:
    conversation_id = str(conversation.id)
    if _consume_failure('process', conversation_id):
        raise RuntimeError('controlled finalization processing failure')
    conversation.status = ConversationStatus.completed
    persisted = lifecycle_service.persist_processed_conversation(
        uid,
        conversation.model_dump(),
        expected_finalization_identity=kwargs.get('expected_finalization_identity'),
    )
    persistence_observer = kwargs.get('persistence_observer')
    if persistence_observer is not None:
        persistence_observer(persisted)
    derived_effects_observer = kwargs.get('derived_effects_observer')
    if persisted and derived_effects_observer is not None:
        derived_effects_observer(lambda: _offline_extract_memories(uid, conversation))
    _record(
        {
            'event': 'provider_leaf',
            'stage': 'process',
            'outcome': 'completed',
            'conversation_id': conversation_id,
            'persisted': bool(persisted),
            'force_process': bool(kwargs.get('force_process')),
            'defer_derived_effects': bool(kwargs.get('defer_derived_effects')),
        }
    )
    return conversation


def _offline_extract_memories(_uid: str, conversation: Any) -> None:
    _record(
        {'event': 'provider_leaf', 'stage': 'memory', 'outcome': 'skipped', 'conversation_id': str(conversation.id)}
    )


def _offline_required_enrichment_effects(
    _uid: str,
    conversation: Any,
    *,
    transcript_vector_count: int | None = None,
    **_kwargs: Any,
) -> tuple[RequiredEnrichmentEffect, ...]:
    def skip(stage: str) -> None:
        _record(
            {
                'event': 'provider_leaf',
                'stage': stage,
                'outcome': 'skipped',
                'conversation_id': str(conversation.id),
            }
        )

    return (
        RequiredEnrichmentEffect('structured_vector', lambda: skip('structured_vector'), resource_count=1),
        RequiredEnrichmentEffect(
            'transcript_vectors',
            lambda: skip('transcript_vectors'),
            resource_count=transcript_vector_count or 0,
        ),
    )


def _offline_cleanup_required_enrichment(
    _uid: str,
    conversation_id: str,
    **_kwargs: Any,
) -> None:
    _record(
        {
            'event': 'provider_leaf',
            'stage': 'required_enrichment_cleanup',
            'outcome': 'skipped',
            'conversation_id': conversation_id,
        }
    )


async def _offline_trigger_integrations(_uid: str, conversation: Any, *, idempotency_key: str, **_kwargs: Any) -> None:
    conversation_id = str(conversation.id)
    fanout_key_sha256 = sha256(idempotency_key.encode()).hexdigest()
    if _consume_failure('integration', conversation_id, fanout_key_sha256=fanout_key_sha256):
        raise RuntimeError('controlled finalization integration failure')
    _record(
        {
            'event': 'provider_leaf',
            'stage': 'integration',
            'outcome': 'completed',
            'conversation_id': conversation_id,
            'fanout_key_sha256': fanout_key_sha256,
        }
    )


def install_finalizer_leaves() -> None:
    """Install only controlled provider leaves before the real ASGI app imports."""
    global _failure_budget
    _failure_budget = _parse_failure_budget()
    finalizer.process_conversation = _offline_process_conversation
    finalizer.extract_memories = _offline_extract_memories
    finalizer.required_enrichment_effects = _offline_required_enrichment_effects
    finalizer.cleanup_required_enrichment = _offline_cleanup_required_enrichment
    finalizer.trigger_external_integrations = _offline_trigger_integrations
