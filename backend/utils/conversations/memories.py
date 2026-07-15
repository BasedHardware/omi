import hashlib
from typing import Any, Dict, List, Optional

import database._client as db_client_module
import database.memories as memories_db
import database.users as users_db
from models.memories import MemoryDB, Memory, MemoryCategory
from models.integrations import ExternalIntegrationCreateMemory
from utils.llm.memories import extract_memories_from_text
from utils.memory.memory_api_contract import MemoryApiExposure, memory_write_payload
from utils.memory.memory_service import MemoryService
from utils.memory.memory_system import MemorySystem, resolve_memory_system
import logging

logger = logging.getLogger(__name__)


def _stable_source_id(*parts: str) -> str:
    raw = "|".join(part or "" for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _artifact_ref(
    *,
    kind: str,
    source_label: Optional[str] = None,
    source_id: Optional[str] = None,
    source_url: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ref = dict(extra or {})
    ref['kind'] = kind
    if source_label:
        ref['text_source'] = source_label
    if source_id:
        ref['external_id'] = source_id
    if source_url:
        ref['url'] = source_url
    return ref


def process_external_integration_memory(
    uid: str, memory_data: ExternalIntegrationCreateMemory, app_id: str
) -> List[MemoryDB]:
    memory_data.app_id = app_id
    saved_memories: List[MemoryDB] = []
    explicit_memory_ids: set[str] = set()
    language = users_db.get_user_language_preference(uid)

    # Process explicit memories if provided
    if memory_data.memories and len(memory_data.memories) > 0:
        for explicit_memory in memory_data.memories:
            # Create a memory object from the explicit memory content
            memory = Memory(
                content=explicit_memory.content,
                category=MemoryCategory.system,
                tags=explicit_memory.tags if explicit_memory.tags else [],
            )

            # Convert to MemoryDB
            source_key = explicit_memory.source_id or _stable_source_id(explicit_memory.content)
            source_id = f"{app_id}:explicit:{source_key}"
            memory_db = MemoryDB.from_memory(
                memory,
                uid,
                None,
                False,
                source_id=source_id,
                source_type=f"integration:{app_id}",
                source_signal="integration",
                artifact_ref=_artifact_ref(
                    kind="integration_explicit_memory",
                    source_id=explicit_memory.source_id,
                    source_url=explicit_memory.source_url,
                    extra=explicit_memory.artifact_ref,
                ),
                extractor_id="external_integration_explicit",
            )
            memory_db.manually_added = False
            memory_db.app_id = app_id
            saved_memories.append(memory_db)
            explicit_memory_ids.add(memory_db.id)

    # Extract memories from text if provided
    if memory_data.text and len(memory_data.text.strip()) > 0:
        extracted_memories = extract_memories_from_text(
            uid,
            memory_data.text,
            memory_data.text_source_spec if memory_data.text_source_spec else memory_data.text_source.value,
            language=language,
        )

        if extracted_memories and len(extracted_memories) > 0:
            # Save each extracted memory
            for memory in extracted_memories:
                text_source = (
                    memory_data.text_source_spec if memory_data.text_source_spec else memory_data.text_source.value
                )
                source_key = memory_data.source_id or _stable_source_id(text_source, memory_data.text)
                source_id = f"{app_id}:text:{source_key}"
                memory_db = MemoryDB.from_memory(
                    memory,
                    uid,
                    None,
                    False,
                    source_id=source_id,
                    source_type=f"integration:{app_id}",
                    source_signal="integration",
                    artifact_ref=_artifact_ref(
                        kind="integration_text",
                        source_label=text_source,
                        source_id=memory_data.source_id,
                        source_url=memory_data.source_url,
                        extra=memory_data.artifact_ref,
                    ),
                    extractor_id="extract_memories_from_text",
                )
                memory_db.manually_added = False
                memory_db.app_id = app_id
                saved_memories.append(memory_db)

    # Save all memories to the database if any were created
    if saved_memories:
        # Background writers use resolve_memory_system (no request pin); routers use pin_memory_system.
        db_client = getattr(db_client_module, 'db', None)
        if resolve_memory_system(uid, db_client=db_client) == MemorySystem.CANONICAL:
            memory_service = MemoryService(db_client=db_client)
            for memory_db in saved_memories:
                if memory_db.id in explicit_memory_ids:
                    memory_service.create_external_memory(
                        uid,
                        memory_db,
                        memory_system=MemorySystem.CANONICAL,
                        consumer=f"integration:{app_id}",
                        operation="explicit_memory_create",
                        upsert_vector=False,
                        require_canonical_promotion=True,
                    )
                else:
                    memory_service.write(uid, memory_db.model_dump())
        else:
            memories_db.save_memories(
                uid,
                [memory_write_payload(fact_db, MemoryApiExposure.LEGACY) for fact_db in saved_memories],
            )

    return saved_memories


def process_twitter_memories(uid: str, tweets_text: str, persona_id: str) -> List[MemoryDB]:
    # Extract memories from tweets using the LLM
    language = users_db.get_user_language_preference(uid)
    extracted_memories = extract_memories_from_text(uid, tweets_text, "twitter_tweets", language=language)

    if not extracted_memories or len(extracted_memories) == 0:
        logger.info(f"No memories extracted from tweets for user {uid}")
        return []

    # Convert extracted memories to database format
    saved_memories: List[MemoryDB] = []
    for memory in extracted_memories:
        source_id = f"{persona_id}:text:{_stable_source_id('twitter_tweets', tweets_text)}"
        memory_db = MemoryDB.from_memory(
            memory,
            uid,
            None,
            False,
            source_id=source_id,
            source_type=f"integration:{persona_id}",
            source_signal="integration",
            artifact_ref=_artifact_ref(kind="integration_text", source_label="twitter_tweets"),
            extractor_id="extract_memories_from_text",
        )
        memory_db.manually_added = False
        memory_db.app_id = persona_id
        saved_memories.append(memory_db)

    # Save all memories in batch
    if saved_memories:
        # Background writers use resolve_memory_system (no request pin); routers use pin_memory_system.
        db_client = getattr(db_client_module, 'db', None)
        if resolve_memory_system(uid, db_client=db_client) == MemorySystem.CANONICAL:
            memory_service = MemoryService(db_client=db_client)
            for memory_db in saved_memories:
                memory_service.write(uid, memory_db.model_dump())
        else:
            memories_db.save_memories(
                uid,
                [memory_write_payload(memory_db, MemoryApiExposure.LEGACY) for memory_db in saved_memories],
            )

    return saved_memories
