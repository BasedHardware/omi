"""Exact effective-input fingerprints, stored only after successful feature output.

No transcript or prompt is stored in the fingerprint fields. Unsupported input
objects fail closed instead of silently stringifying two distinct inputs alike.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from datetime import date, datetime
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

from prometheus_client import Counter

from config.sync_reprocess import dedupe_enabled

SKIPPED = Counter(
    'conversation_llm_input_dedupe_skipped_total', 'Successful conversation feature input reused', ['feature']
)
NOTES_HASH = 'notes_llm_input_hash'
L1_HASH = 'l1_llm_input_hash'


def canonical(value: Any) -> Any:
    if isinstance(value, Enum):
        return canonical(value.value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return {'date': value.isoformat()}
    if isinstance(value, bytes):
        return {'bytes_sha256': hashlib.sha256(value).hexdigest()}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return canonical(dataclasses.asdict(value))
    if hasattr(value, 'model_dump'):
        return canonical(value.model_dump(mode='python'))
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError('LLM input mappings require string keys')
        return {key: canonical(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted((canonical(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True))
    if isinstance(value, (tuple, list)):
        return [canonical(item) for item in value]
    raise TypeError(f'Unsupported LLM input type: {type(value).__name__}')


@lru_cache(maxsize=2)
def implementation_digest(feature: str) -> str:
    # Invalidate persisted results on prompt/schema/orchestration edits as well
    # as input changes. Read lazily: imports perform no filesystem/client IO.
    root = Path(__file__).resolve().parents[1]
    paths = [
        'conversations/process_conversation.py',
        'llm/conversation_prompt_context.py',
        'llm/memories.py',
        'llm/working_observations.py',
        'llm/conversation_processing.py',
        'llm/conversation_notes_prompts.py',
        'llm/conversation_title_people.py',
        'llm/meeting_notes_rich_prompts.py',
        'llm/meeting_notes_presentation.py',
        'llm/meeting_notes_validation.py',
        'memory/belief_model.py',
        'memory/rejected_memory_feedback.py',
        'prompts.py',
        '../models/structured.py',
        '../models/structured_extraction.py',
        '../models/memory_contracts.py',
        '../models/conversation.py',
        '../models/memories.py',
    ]
    return hashlib.sha256(b''.join((root / path).read_bytes() for path in paths)).hexdigest()


def fingerprint(feature: str, inputs: Any) -> str:
    value = {'feature': feature, 'implementation': implementation_digest(feature), 'input': canonical(inputs)}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _stored(uid: str, conversation: Any) -> dict[str, Any]:
    from database import conversations

    row = conversations.get_conversation(uid, conversation.id)
    if not row or row.get('deleted'):
        return {}
    if row.get('sync_content_revision') != getattr(conversation, 'sync_content_revision', None):
        return {}
    return row


def notes(uid: str, conversation: Any, prefix: Any, generate, hashes: dict[str, str] | None, **kwargs):
    if not dedupe_enabled() or hashes is None:
        return generate(prefix, uid=uid, **kwargs)
    digest = fingerprint(
        'notes',
        {
            'prefix': prefix,
            'arguments': kwargs,
            'tier_escalation': os.getenv('NOTES_TIER_ESCALATION_ENABLED', ''),
            'shaped_notes_mode': os.getenv('OMI_SHAPED_AGENT_MODE', 'off'),
        },
    )
    row = _stored(uid, conversation) if getattr(conversation, 'id', None) else {}
    if row.get(NOTES_HASH) == digest and row.get('structured') and not row.get('discarded'):
        from models.conversation import Structured

        output = Structured.model_validate(row['structured'])
        SKIPPED.labels(feature='notes').inc()
    else:
        output = generate(prefix, uid=uid, **kwargs)
    hashes[NOTES_HASH] = digest
    return output


def l1_input(uid: str, conversation: Any, inputs: Any) -> tuple[str | None, bool]:
    if not dedupe_enabled():
        return None, False
    digest = fingerprint('l1', inputs)
    matched = _stored(uid, conversation).get(L1_HASH) == digest
    if matched:
        SKIPPED.labels(feature='l1').inc()
    return digest, matched


def l1_succeeded(uid: str, conversation: Any, digest: str | None) -> bool:
    if digest is None:
        return False
    from google.cloud import firestore
    from database._client import get_firestore_client

    client = get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(conversation.id)

    @firestore.transactional
    def commit(transaction):
        snapshot = ref.get(transaction=transaction)
        row = snapshot.to_dict() if snapshot.exists else None
        if not row or row.get('deleted') or row.get('discarded'):
            return False
        # An older run must never mark a newer transcript successfully handled.
        if row.get('sync_content_revision') != getattr(conversation, 'sync_content_revision', None):
            return False
        transaction.update(ref, {L1_HASH: digest})
        return True

    return commit(client.transaction())
