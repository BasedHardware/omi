import time
from typing import List
from models.memory import Memory, MemoryStatus
import database.memories as memories_db
from utils.memories.process_memory import process_memory

MEMORY_CREATION_TIMEOUT = 15

def get_memories(uid: str, limit: int = 100, offset: int = 0, include_discarded: bool = False, statuses: List[str] = []):
    memories = memories_db.get_memories(uid, limit, offset, include_discarded=include_discarded,statuses=statuses)

    # Refine the in_progress status
    for i, m in enumerate(memories):
        if 'status' in m and m['status'] == MemoryStatus.in_progress and time.time() - m['finished_at'].timestamp() > MEMORY_CREATION_TIMEOUT:
            memory = Memory(**m)
            memories_db.update_memory_status(uid, memory.id, MemoryStatus.processing)
            memory = process_memory(uid, memory.language, memory)
            memories_db.update_memory_status(uid, memory.id, MemoryStatus.completed)
            memories[i]['status'] = MemoryStatus.completed

    return memories
