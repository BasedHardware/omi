import os

os.environ.setdefault('TYPESENSE_API_KEY', 'test-key')
os.environ.setdefault('TYPESENSE_HOST', 'localhost')
os.environ.setdefault('TYPESENSE_HOST_PORT', '8108')

from unittest.mock import patch

from models.memories import MemoryDB
from utils.conversations import process_conversation as process_conversation_module


def test_kg_extraction_uses_idempotent_setter_for_stale_memory():
    memory = MemoryDB(
        id='memory-1',
        content='User loves hiking',
        category='interests',
        visibility='private',
        kg_extracted=False,
        is_locked=False,
    )

    with patch.object(process_conversation_module, 'get_user_name', return_value='User'), patch.object(
        process_conversation_module, 'extract_knowledge_from_memory', return_value={'nodes': [], 'edges': []}
    ), patch.object(
        process_conversation_module.memories_db,
        'set_memory_kg_extracted',
        return_value=None,
    ) as mock_set:
        user_name = process_conversation_module.get_user_name('uid-abc')
        for memory_db_obj in [memory]:
            if memory_db_obj.kg_extracted or memory_db_obj.is_locked:
                continue
            result = process_conversation_module.extract_knowledge_from_memory(
                'uid-abc', memory_db_obj.content, memory_db_obj.id, user_name
            )
            if result is not None:
                process_conversation_module.memories_db.set_memory_kg_extracted('uid-abc', memory_db_obj.id)

    mock_set.assert_called_once_with('uid-abc', 'memory-1')
