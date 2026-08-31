"""Controlled provider leaves for the durable finalization worker harness."""

from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path
from typing import Any

from models.structured import Structured
from utils.conversations import finalizer
from utils.conversations import process_conversation as processing
from utils.conversations.memory_extraction_telemetry import (
    PATH_CANONICAL,
    ConversationMemoryExtractionResult,
    source_for_conversation,
)

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


def _offline_get_structured(_uid: str, _language: str, conversation: Any, *_args: Any, **_kwargs: Any):
    """Replace only the summary-provider leaf; lifecycle persistence stays real."""

    conversation_id = str(conversation.id)
    if _consume_failure('process', conversation_id):
        raise RuntimeError('controlled finalization processing failure')
    _record(
        {
            'event': 'provider_leaf',
            'stage': 'process',
            'outcome': 'completed',
            'conversation_id': conversation_id,
        }
    )
    return Structured(title='Hermetic finalization', overview='Provider leaf completed locally.'), False


def _offline_extract_memories_canonical(
    _uid: str, conversation: Any, *, db_client: Any, parity_capture: Any = None
) -> ConversationMemoryExtractionResult:
    """Replace the memory provider/store leaf reached only after the real fence."""

    del db_client, parity_capture
    _record(
        {'event': 'provider_leaf', 'stage': 'memory', 'outcome': 'completed', 'conversation_id': str(conversation.id)}
    )
    return ConversationMemoryExtractionResult(
        count=0,
        source=source_for_conversation(conversation),
        path=PATH_CANONICAL,
    )


def _offline_noop(*_args: Any, **_kwargs: Any) -> None:
    """Credentialed derived-effect leaf intentionally excluded from this harness."""


async def _offline_noop_async(*_args: Any, **_kwargs: Any) -> None:
    """Async credentialed derived-effect leaf intentionally excluded here."""


def _offline_folder_assignment(*_args: Any, **_kwargs: Any) -> tuple[None, float, str]:
    return None, 0.0, 'offline_provider_leaf'


async def _offline_trigger_integrations(_uid: str, conversation: Any, *, idempotency_key: str, **_kwargs: Any) -> None:
    conversation_id = str(conversation.id)
    fanout_key_sha256 = sha256(idempotency_key.encode()).hexdigest()
    if _consume_failure('integration', conversation_id, fanout_key_sha256=fanout_key_sha256):
        raise ConnectionError('controlled finalization integration failure')
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
    """Install provider leaves below the real process/fence/finalizer path."""
    global _failure_budget
    _failure_budget = _parse_failure_budget()
    processing._get_structured = _offline_get_structured
    processing._extract_memories_canonical = _offline_extract_memories_canonical
    processing.trigger_conversation_apps = _offline_noop
    processing.assign_conversation_to_folder = _offline_folder_assignment
    processing.save_structured_vector = _offline_noop
    processing.save_transcript_chunk_vectors = _offline_noop
    processing._save_action_items = _offline_noop
    processing.update_goal_progress = _offline_noop
    processing.conversation_created_webhook = _offline_noop_async
    processing.conversations_db.create_audio_files_from_chunks = lambda *_args, **_kwargs: []
    finalizer.trigger_external_integrations = _offline_trigger_integrations
