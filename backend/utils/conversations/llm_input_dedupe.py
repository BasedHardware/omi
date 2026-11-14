"""Exact effective-input fingerprints, stored only after successful feature output.

No transcript or prompt is stored in the fingerprint fields. Unsupported input
objects fail closed instead of silently stringifying two distinct inputs alike.
"""

from __future__ import annotations

from config.refactor_modes import serving_for
from config.llm_input_versions import prompt_version
from config.memory_l1_admission import noise_skip_enabled
from config.llm_input_legacy import (
    LEGACY_DEPENDENCY_VERSIONS,
    LEGACY_IMPLEMENTATIONS,
    LEGACY_ROUTING,
    LEGACY_PROMPT_VERSIONS,
)

import dataclasses
import hashlib
import json
import os
from functools import lru_cache
from importlib.metadata import version as distribution_version
from pathlib import Path
from datetime import date, datetime
from enum import Enum
from typing import Any

from prometheus_client import Counter
from pydantic import BaseModel
from models.structured import Structured

from utils.conversations.summary_delivery import present as summary_present
from config.sync_reprocess import dedupe_enabled

from utils.sync.repeat_work_metrics import record_feature
from utils.task_intelligence import reminder_policy

SKIPPED = Counter(
    'conversation_llm_input_dedupe_skipped_total', 'Successful conversation feature input reused', ['feature']
)
MISSES = Counter(
    'conversation_llm_input_dedupe_misses_total',
    'Conversation feature calls evaluated with no reusable input',
    ['feature'],
)
CHECKPOINT_ERRORS = Counter(
    'conversation_llm_input_dedupe_checkpoint_errors_total',
    'Input hash matched but the stored output checkpoint was unusable',
    ['feature'],
)
NOTES_HASH = 'notes_llm_input_hash'
NOTES_OUTPUT_HASH = 'notes_llm_output_hash'
L1_HASH = 'l1_llm_input_hash'
# Serialization and model wrappers can change effective inputs without a source
# edit. Installed distributions are immutable for this process; read them once.
INSTALLED_DEPENDENCY_VERSIONS = tuple((name, distribution_version(name)) for name in ('pydantic', 'langchain-core'))


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
    if isinstance(value, BaseModel):
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
def _legacy_implementation_digest(feature: str) -> str:
    # Invalidate persisted results on prompt/schema/orchestration edits as well
    # as input changes. Source files are read lazily; dependencies are snapshotted
    # at import so both key modes use the same installed-version identity.
    root = Path(__file__).resolve().parents[1]
    paths = [
        'conversations/process_conversation.py',
        'llm/jev_client.py',
        'llm/model_config.py',
        'llm/model_constants.py',
        'llm/clients.py',
        'llm/providers.py',
        '../config/jev_decisions.py',
        'llm/conversation_prompt_context.py',
        'llm/memories.py',
        'llm/working_observations.py',
        'llm/conversation_processing.py',
        'llm/conversation_notes_prompts.py',
        'llm/notes_packet.py',
        'llm/action_item_v2.py',
        'llm/notes_output.py',
        'llm/notes_lengths.py',
        'llm/notes_effort.py',
        'llm/notes_output_contract.py',
        'llm/notes_identity.py',
        'llm/output_language.py',
        'llm/speaker_evidence_prompt.py',
        'llm/notes_short_clip.py',
        'llm/notes_language_inputs.py',
        'llm/conversation_title_people.py',
        'llm/meeting_notes_rich_prompts.py',
        'llm/meeting_notes_presentation.py',
        'llm/meeting_notes_validation.py',
        'memory/rejected_memory_feedback.py',
        'prompts.py',
        '../models/structured.py',
        '../models/structured_extraction.py',
        '../models/memory_contracts.py',
        '../models/conversation.py',
        '../models/memories.py',
    ]
    dependencies = '|'.join(f'{name}:{version}' for name, version in INSTALLED_DEPENDENCY_VERSIONS).encode()
    return hashlib.sha256(b''.join((root / path).read_bytes() for path in paths) + dependencies).hexdigest()


# Routing is part of the effective model input, even if the prompt did not change.
ROUTING_SOURCES = (
    'llm/model_config.py',
    'llm/model_constants.py',
    'llm/clients.py',
    'llm/providers.py',
    'llm/jev_client.py',
    '../config/jev_decisions.py',
)


@lru_cache(maxsize=1)
def routing_digest() -> str:
    root = Path(__file__).resolve().parents[1]
    return hashlib.sha256(b''.join((root / path).read_bytes() for path in ROUTING_SOURCES)).hexdigest()


def stable_implementation(feature: str) -> str:
    dependencies = '|'.join(f'{name}:{version}' for name, version in INSTALLED_DEPENDENCY_VERSIONS)
    return f'{prompt_version(feature)}:{routing_digest()}:{dependencies}'


def implementation_digest(feature: str) -> str:
    return stable_implementation(feature) if noise_skip_enabled() else _legacy_implementation_digest(feature)


def _fingerprint(feature: str, inputs: Any, implementation: str) -> str:
    value = {'feature': feature, 'implementation': implementation, 'input': canonical(inputs)}
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def fingerprint(feature: str, inputs: Any) -> str:
    return _fingerprint(feature, inputs, implementation_digest(feature))


def _matches(saved: str | None, feature: str, inputs: Any, digest: str) -> bool:
    if saved == digest:
        return True
    # Accept both modes across a rollback. Never make a flag flip buy the same
    # eligible work again. Historical keys are allowed only for the same routing
    # and compatible prompt sources/dependencies; exact inputs + output validation
    # still apply. A dependency bump deliberately recomputes once per input.
    implementations = {stable_implementation(feature), _legacy_implementation_digest(feature)}
    if (
        INSTALLED_DEPENDENCY_VERSIONS == LEGACY_DEPENDENCY_VERSIONS
        and routing_digest() == LEGACY_ROUTING
        and prompt_version(feature) in LEGACY_PROMPT_VERSIONS[feature]
    ):
        implementations.update(LEGACY_IMPLEMENTATIONS[feature])
        implementations.update(f'{version}:{routing_digest()}' for version in LEGACY_PROMPT_VERSIONS[feature])
        dependencies = '|'.join(f'{name}:{version}' for name, version in INSTALLED_DEPENDENCY_VERSIONS)
        implementations.update(
            f'{version}:{routing_digest()}:{dependencies}' for version in LEGACY_PROMPT_VERSIONS[feature]
        )
    return bool(saved) and any(saved == _fingerprint(feature, inputs, item) for item in implementations)


def _stored(uid: str, conversation: Any, *, db_client: Any = None) -> dict[str, Any]:
    from database import conversations

    # L1 already has an injected persistence client. Its checkpoint is metadata
    # only, so use the raw read seam without resolving a second global client.
    row = (
        conversations.get_conversation_raw_snapshot(uid, conversation.id, firestore_client=db_client)
        if db_client is not None
        else conversations.get_conversation(uid, conversation.id)
    )
    if not row or row.get('deleted'):
        return {}
    if row.get('sync_content_revision') != getattr(conversation, 'sync_content_revision', None):
        return {}
    return row


def _notes_packet_identity(uid: str) -> dict[str, Any]:
    from config.refactor_modes import serving_for
    from utils.llm.notes_packet import PACKET_VERSION

    serving = serving_for('NOTES_PACKET_V2_MODE', uid)
    return {'mode': 'serve' if serving else 'legacy', 'version': PACKET_VERSION if serving else 1}


def notes(uid: str, conversation: Any, prefix: Any, generate, hashes: dict[str, str] | None, **kwargs):
    open_loop_out = kwargs.pop('open_loop_out', None)
    if kwargs.get('task_intelligence_capture') and reminder_policy.enabled():
        kwargs['reminder_source'] = reminder_policy.source_input(conversation)
    if not dedupe_enabled() or hashes is None:
        return generate(prefix, uid=uid, open_loop_out=open_loop_out, **kwargs)
    inputs = {
        'prefix': prefix,
        **({}),
        'arguments': kwargs,
        'notes_packet': _notes_packet_identity(uid),
        'action_items_v2': serving_for('ACTION_ITEMS_V2_MODE', uid),
        'tier_escalation': os.getenv('NOTES_TIER_ESCALATION_ENABLED', ''),
        'shaped_notes_mode': os.getenv('OMI_SHAPED_AGENT_MODE', 'off'),
        'notes_agent': os.getenv('CONVERSATION_NOTES_AGENT_ENABLED', 'true').strip().lower(),
    }
    digest = fingerprint('notes', inputs)
    row = _stored(uid, conversation) if getattr(conversation, 'id', None) else {}
    saved = None
    matched_input = _matches(row.get(NOTES_HASH), 'notes', inputs, digest) and not row.get('discarded')
    if matched_input and row.get(NOTES_OUTPUT_HASH):
        from pydantic import ValidationError

        try:
            candidate = Structured.model_validate(row.get('structured'))
            if row[NOTES_OUTPUT_HASH] == output_fingerprint(candidate) and summary_present(candidate):
                saved = candidate
        except ValidationError:
            pass  # An unusable optional checkpoint is an ordinary cache miss.
    if saved is not None:
        output = saved
        SKIPPED.labels(feature='notes').inc()
        record_feature(uid, conversation, 'notes', 'reused')
    else:
        if matched_input:
            CHECKPOINT_ERRORS.labels(feature='notes').inc()
        MISSES.labels(feature='notes').inc()
        record_feature(uid, conversation, 'notes', 'invoked')
        output = generate(prefix, uid=uid, open_loop_out=open_loop_out, **kwargs)
    hashes[NOTES_HASH] = digest
    hashes[NOTES_OUTPUT_HASH] = output_fingerprint(output)
    return output


def output_fingerprint(output: Any) -> str:
    return hashlib.sha256(
        json.dumps(canonical(output), sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def invalidate_l1(uid: str, conversation: Any, *, db_client: Any = None) -> bool:
    """A flag-off successful replacement must not leave an older hash trusted.

    Metadata only: no memory/transcript/output mutation. The update-time fence
    preserves a newer checkpoint if a peer completed while this read was in flight.
    """
    from google.api_core.exceptions import FailedPrecondition, NotFound
    from google.cloud import firestore
    from database._client import get_firestore_client

    client = db_client if db_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(conversation.id)
    snapshot = ref.get()
    row = snapshot.to_dict() if snapshot.exists else None
    if not row or not row.get(L1_HASH):
        return False
    try:
        ref.update({L1_HASH: None}, option=firestore.LastUpdateOption(snapshot.update_time))
    except (FailedPrecondition, NotFound):
        return False
    return True


def l1_input(uid: str, conversation: Any, inputs: Any, *, db_client: Any = None) -> tuple[str | None, bool]:
    if not dedupe_enabled():
        return None, False
    digest = fingerprint(
        'l1',
        (inputs),
    )
    matched = _matches(_stored(uid, conversation, db_client=db_client).get(L1_HASH), 'l1', inputs, digest)
    if matched:
        SKIPPED.labels(feature='l1').inc()
    else:
        MISSES.labels(feature='l1').inc()
    record_feature(uid, conversation, 'l1', 'reused' if matched else 'invoked')
    return digest, matched


def l1_succeeded(uid: str, conversation: Any, digest: str | None, *, db_client: Any = None) -> bool:
    if digest is None:
        return invalidate_l1(uid, conversation, db_client=db_client)
    from google.cloud import firestore
    from database._client import get_firestore_client

    client = db_client if db_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(conversation.id)

    @firestore.transactional
    def commit(transaction: Any) -> bool:
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
