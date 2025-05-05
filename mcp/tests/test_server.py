from mcp_server_omi.server import get_memories, get_conversations, MemoryCategory


def test_get_memories(uid):
    # Test getting memories with default parameters
    result = get_memories(uid)
    assert isinstance(result, list)

    # Test getting memories with specific limit
    result = get_memories(uid, limit=5)
    assert isinstance(result, list)
    assert len(result) <= 5

    # Test getting memories with categories filter
    categories = [MemoryCategory.personal, MemoryCategory.work]
    result = get_memories(uid, categories=categories)
    assert isinstance(result, list)


def test_get_conversations(uid):
    # Test getting conversations with default parameters
    result = get_conversations(uid)
    assert isinstance(result, list)

    # Test getting conversations with include_discarded
    result = get_conversations(uid, include_discarded=True)
    assert isinstance(result, list)

    # Test getting conversations with specific limit
    result = get_conversations(uid, limit=10)
    assert isinstance(result, list)
    assert len(result) <= 10
