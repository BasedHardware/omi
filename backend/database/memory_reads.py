from typing import Dict, List

from database import memories as memories_db
from database import short_term_memories as short_term_db


def get_retrievable_memories(uid: str, *, limit: int = 100, include_short_term: bool = True) -> List[Dict]:
    long_term = memories_db.get_memories(uid, limit=limit, offset=0)
    long_term_records = [{**memory, 'source': 'long_term'} for memory in long_term]
    if not include_short_term:
        return long_term_records

    short_term = short_term_db.get_short_term_memories(uid, status='pending_consolidation', limit=limit)
    return long_term_records + [short_term_db.to_retrieval_record(memory) for memory in short_term]
