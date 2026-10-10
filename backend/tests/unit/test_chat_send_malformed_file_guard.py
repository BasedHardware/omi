"""The chat send path must build attachments through `safe_file_chats`, not a raw `FileChat(**f)`.

#9608 (merged) moved the three chat-file builders in `utils/other/chat_file.py` onto
`safe_file_chats` so one legacy/partial file doc (missing `openai_file_id`/`mime_type`/`created_at`)
could not 500 the attach/answer/cleanup flow. The send path's own builder in `routers/chat.py`
(`send_message`) predates that sweep and kept the raw comprehension: a `POST /v2/messages` whose
`file_ids` entry points at a partial stored doc raised `ValidationError` and 500'd before the turn
was persisted.

The helper's skip behaviour is covered by `test_chat_file_skip_malformed.py`; this test pins that
the send path routes through it and cannot regress to a raw builder.
"""

import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
CHAT_ROUTER = BACKEND_DIR / 'utils' / 'chat_turn.py'


def test_send_path_imports_the_safe_builder():
    tree = ast.parse(CHAT_ROUTER.read_text())
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == 'utils.other.chat_file'
        for alias in node.names
    }

    assert 'safe_file_chats' in imported


def test_no_raw_filechat_comprehension_in_the_send_path():
    tree = ast.parse(CHAT_ROUTER.read_text())
    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.ListComp)
        and isinstance(node.elt, ast.Call)
        and getattr(node.elt.func, 'id', None) == 'FileChat'
    ]

    assert offenders == [], f'raw FileChat(**record) comprehensions reintroduced at lines {offenders}'
