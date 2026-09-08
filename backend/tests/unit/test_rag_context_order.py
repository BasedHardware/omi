from types import SimpleNamespace
from unittest.mock import patch

from utils.retrieval import rag


class _ReverseCompletionExecutor:
    def __init__(self):
        self.jobs = []
        self.completed = False

    def submit(self, function, *args):
        self.jobs.append((function, args))
        return _ReverseCompletionFuture(self)


class _ReverseCompletionFuture:
    def __init__(self, executor):
        self.executor = executor

    def result(self):
        if self.executor.completed:
            return None
        self.executor.completed = True
        for function, args in reversed(self.executor.jobs):
            function(*args)
        return None


def test_retrieve_rag_conversation_context_preserves_memory_order_after_parallel_completion():
    memories = [
        SimpleNamespace(id='memory-1', get_person_ids=lambda: []),
        SimpleNamespace(id='memory-2', get_person_ids=lambda: []),
    ]
    source_memory = SimpleNamespace(transcript_segments=[], get_person_ids=lambda: [])
    executor = _ReverseCompletionExecutor()

    def write_context(memory, _topics, context_data, _people, _user_name):
        context_data[memory.id] = memory.id

    with (
        patch.object(rag, 'retrieve_memory_context_params', return_value=['topic']),
        patch.object(
            rag,
            'retrieve_memories_for_topics',
            return_value=({'memory-1': ['topic'], 'memory-2': ['topic']}, [{'id': 'memory-1'}, {'id': 'memory-2'}]),
        ),
        patch.object(rag, 'deserialize_conversations', return_value=memories),
        patch.object(rag, 'get_user_name', return_value=None),
        patch.object(rag, 'get_better_conversation_chunk', side_effect=write_context),
        patch.object(rag, 'db_executor', executor),
    ):
        context, returned_memories = rag.retrieve_rag_conversation_context('user-1', source_memory)

    assert context == 'memory-1\nmemory-2'
    assert returned_memories == memories
