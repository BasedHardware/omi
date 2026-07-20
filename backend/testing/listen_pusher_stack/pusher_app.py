"""Instrumented entrypoint for the real pusher ASGI application.

It preserves the production WebSocket router, wire protocol, Firestore jobs,
leases, fanout claims, and result frames.  The three provider-side finalizer
leaves are replaced before importing ``pusher.main`` so a local test cannot
call LLMs, vector stores, or user integrations.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from fastapi.websockets import WebSocketDisconnect

from models.conversation_enums import ConversationStatus
from utils.conversations import finalizer
from utils.conversations import lifecycle as lifecycle_service


def _record(event: dict[str, Any]) -> None:
    """Record frame metadata only; transcript/audio contents never leave memory."""
    state_dir = os.getenv('OMI_STACK_STATE_DIR')
    if not state_dir:
        return
    path = Path(state_dir) / 'pusher.jsonl'
    with path.open('a', encoding='utf-8') as output:
        output.write(json.dumps(event, sort_keys=True) + '\n')


def _offline_process_conversation(uid: str, _language: str, conversation: Any, **_kwargs: Any) -> Any:
    """Finish through the production lifecycle owner without external providers."""
    conversation.status = ConversationStatus.completed
    persisted = lifecycle_service.persist_processed_conversation(uid, conversation.model_dump())
    _record(
        {
            'event': 'offline_process',
            'conversation_id': str(conversation.id),
            'persisted': bool(persisted),
        }
    )
    return conversation


def _offline_extract_memories(_uid: str, _conversation: Any) -> None:
    _record({'event': 'memory_extraction_skipped'})


async def _offline_trigger_integrations(_uid: str, conversation: Any, *, idempotency_key: str, **_kwargs: Any) -> None:
    release_file = os.getenv('OMI_STACK_INLINE_FINALIZATION_RELEASE_FILE')
    if release_file:
        release_path = Path(release_file)
        _record({'event': 'inline_finalization_hold_entered', 'conversation_id': str(conversation.id)})
        while not release_path.exists():
            await asyncio.sleep(0.01)
        _record({'event': 'inline_finalization_hold_released', 'conversation_id': str(conversation.id)})
    _record(
        {
            'event': 'integration_fanout_skipped',
            'conversation_id': str(conversation.id),
            'fanout_key_present': bool(idempotency_key),
        }
    )


# Patch imported leaves, not finalizer ownership.  Its real Firestore
# persistence, fanout claim/completion and fenced disposition continue to run.
finalizer.process_conversation = _offline_process_conversation
finalizer.extract_memories = _offline_extract_memories
finalizer.trigger_external_integrations = _offline_trigger_integrations

from routers import pusher as pusher_router  # noqa: E402  (patch finalizer first)

_receive_bytes = pusher_router.WebSocket.receive_bytes
_send_bytes = pusher_router.WebSocket.send_bytes
_drain_tasks = pusher_router.drain_tasks


def _offline_store_audio_chunks(chunks: list[dict[str, Any]], _uid: str, conversation_id: str, _level: str) -> None:
    """Keep the real pusher queue/flush path local when 101 frames are enabled."""
    _record(
        {
            'event': 'audio_storage_skipped',
            'conversation_id': conversation_id,
            'chunks': len(chunks),
            'bytes': sum(len(chunk.get('data') or b'') for chunk in chunks),
        }
    )


def _offline_create_audio_files(*_args: Any, **_kwargs: Any) -> list[Any]:
    return []


pusher_router.upload_audio_chunks_batch = _offline_store_audio_chunks
pusher_router.conversations_db.create_audio_files_from_chunks = _offline_create_audio_files


def _frame_metadata(data: bytes, direction: str) -> dict[str, Any]:
    opcode = int.from_bytes(data[:4], byteorder='little', signed=False) if len(data) >= 4 else None
    event: dict[str, Any] = {'event': 'frame', 'direction': direction, 'opcode': opcode, 'bytes': len(data)}
    if opcode in {102, 104, 201}:
        try:
            payload = json.loads(data[4:].decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {}
        if isinstance(payload, dict):
            event['conversation_id'] = payload.get('conversation_id') or payload.get('memory_id')
            if opcode == 102:
                event['segments'] = len(payload.get('segments') or [])
            if opcode == 104:
                event['finalization_job_id'] = payload.get('finalization_job_id')
                event['dispatch_generation'] = payload.get('dispatch_generation')
            if opcode == 201:
                event['success'] = bool(payload.get('success'))
                event['fenced'] = bool(payload.get('fenced'))
                event['terminal'] = bool(payload.get('terminal'))
    return event


async def _observed_receive_bytes(websocket: Any) -> bytes:
    data = await _receive_bytes(websocket)
    event = _frame_metadata(data, 'in')
    _record(event)
    drop_opcode = os.getenv('OMI_STACK_DROP_PUBLISHING_ON_OPCODE')
    if drop_opcode and event.get('opcode') == int(drop_opcode):
        # The test asks the real pusher route to lose this socket *before* it
        # can claim the durable job.  This deterministically verifies replay
        # after a real service restart without creating an artificial stale
        # lease.
        _record({'event': 'intentional_drop_before_dispatch', 'opcode': event['opcode']})
        await websocket.close(code=1012)
        raise WebSocketDisconnect(code=1012)
    return data


async def _observed_send_bytes(websocket: Any, data: bytes) -> None:
    _record(_frame_metadata(data, 'out'))
    await _send_bytes(websocket, data)


pusher_router.WebSocket.receive_bytes = _observed_receive_bytes
pusher_router.WebSocket.send_bytes = _observed_send_bytes


async def _observed_drain_tasks(*args: Any, **kwargs: Any) -> int:
    result = await _drain_tasks(*args, **kwargs)
    if kwargs.get('label') == 'pusher_cleanup':
        _record({'event': 'pusher_cleanup_completed'})
    return result


pusher_router.drain_tasks = _observed_drain_tasks

from pusher.main import app  # noqa: E402
