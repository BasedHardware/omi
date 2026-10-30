"""Source contract: metadata extraction must not recreate the retired Redis store."""

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def test_dead_filters_have_no_writers_or_accessors():
    removed = {'add_filter_category_item', 'get_filter_category_items', 'select_structured_filters'}
    for name in ('database/redis_db.py', 'utils/llm/chat.py', 'routers/mcp.py'):
        source = (BACKEND / name).read_text()
        tree = ast.parse(source)
        assert not any(isinstance(n, ast.FunctionDef) and n.name in removed for n in ast.walk(tree))
        assert not any(symbol in source for symbol in removed)
    assert 'ConversationMetadata(' in (BACKEND / 'utils/llm/chat.py').read_text()
