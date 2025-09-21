from typing import List, Tuple, Optional

import database.memories as memories_db
from models.memories import MemoryDB, Memory, MemoryCategory
from models.integrations import ExternalIntegrationCreateMemory
from utils.llm.memories import extract_memories_from_text


def process_external_integration_memory(
    uid: str, memory_data: ExternalIntegrationCreateMemory, app_id: str
) -> List[MemoryDB]:
    memory_data.app_id = app_id
    saved_memories = []

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
            memory_db = MemoryDB.from_memory(memory, uid, None, False)
            memory_db.manually_added = False
            memory_db.app_id = app_id
            saved_memories.append(memory_db)

    # Extract memories from text if provided
    if memory_data.text and len(memory_data.text.strip()) > 0:
        extracted_memories = extract_memories_from_text(
            uid,
            memory_data.text,
            memory_data.text_source_spec if memory_data.text_source_spec else memory_data.text_source.value,
        )

        if extracted_memories and len(extracted_memories) > 0:
            # Save each extracted memory
            for memory in extracted_memories:
                memory_db = MemoryDB.from_memory(memory, uid, None, False)
                memory_db.manually_added = False
                memory_db.app_id = app_id
                saved_memories.append(memory_db)

    # Save all memories to the database if any were created
    if saved_memories:
        memories_db.save_memories(uid, [fact_db.dict() for fact_db in saved_memories])

    return saved_memories


def process_twitter_memories(uid: str, tweets_text: str, persona_id: str) -> List[MemoryDB]:
    # Extract memories from tweets using the LLM
    extracted_memories = extract_memories_from_text(uid, tweets_text, "twitter_tweets")

    if not extracted_memories or len(extracted_memories) == 0:
        print(f"No memories extracted from tweets for user {uid}")
        return []

    # Convert extracted memories to database format
    saved_memories = []
    for memory in extracted_memories:
        memory_db = MemoryDB.from_memory(memory, uid, None, False)
        memory_db.manually_added = False
        memory_db.app_id = persona_id
        saved_memories.append(memory_db)

    # Save all memories in batch
    memories_db.save_memories(uid, [memory_db.dict() for memory_db in saved_memories])

    return saved_memories
