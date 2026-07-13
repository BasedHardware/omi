"""utils.other.chat_file._safe_file_chats skips a malformed file doc instead of 500ing the chat-file flow.

get_chat_files / get_chat_files_desc results were turned into FileChat objects with unguarded
[FileChat(**f) for f in ...] comprehensions at three sites. FileChat requires id/name/mime_type/
openai_file_id/created_at, so one legacy or partial file document raised ValidationError and 500'd
the whole attach / answer / cleanup flow. All three sites now route through _safe_file_chats, which
skips a malformed record (mirroring utils.apps._safe_build_app). The helper is pure, so the test
imports and calls it directly.
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from datetime import datetime, timezone

import utils.other.chat_file as cf  # noqa: E402
from models.chat import FileChat  # noqa: E402


def _valid_file_dict():
    return {
        'id': 'f1',
        'name': 'a.png',
        'mime_type': 'image/png',
        'openai_file_id': 'oai-1',
        'created_at': datetime(2026, 1, 1, tzinfo=timezone.utc),
    }


def test_safe_file_chats_returns_files_for_valid_records():
    out = cf._safe_file_chats([_valid_file_dict(), {**_valid_file_dict(), 'id': 'f2'}])
    assert [f.id for f in out] == ['f1', 'f2']
    assert all(isinstance(f, FileChat) for f in out)


def test_safe_file_chats_skips_malformed_record():
    # A doc missing required fields (openai_file_id/mime_type/created_at) is skipped, not raised.
    records = [_valid_file_dict(), {'id': 'broken'}, {**_valid_file_dict(), 'id': 'f3'}]
    out = cf._safe_file_chats(records)
    assert [f.id for f in out] == ['f1', 'f3']  # malformed 'broken' skipped, list survives


def test_safe_file_chats_empty():
    assert cf._safe_file_chats([]) == []


def test_openai_file_ids_includes_malformed_docs():
    # A doc that fails FileChat validation can still carry openai_file_id; cleanup must see it.
    records = [
        _valid_file_dict(),
        {'id': 'broken', 'openai_file_id': 'oai-orphan'},
        {'id': 'no-provider'},
        {**_valid_file_dict(), 'id': 'f3', 'openai_file_id': 'oai-3'},
    ]
    assert cf._openai_file_ids(records) == ['oai-1', 'oai-orphan', 'oai-3']


def test_cleanup_deletes_openai_file_even_when_doc_is_malformed(monkeypatch):
    deleted: list[str] = []
    firestore_deleted: list = []

    monkeypatch.setattr(
        cf.chat_db,
        'get_chat_files',
        lambda _uid: [
            _valid_file_dict(),
            {'id': 'broken', 'openai_file_id': 'oai-orphan'},
        ],
    )
    monkeypatch.setattr(
        cf.chat_db,
        'delete_multi_files',
        lambda _uid, files: firestore_deleted.extend(files),
    )
    monkeypatch.setattr(
        cf.openai.files,
        'delete',
        lambda file_id, timeout=30.0: deleted.append(file_id),
    )

    # Bypass __init__ (Firestore session load); cleanup only needs uid + optional ids.
    tool = cf.FileChatTool.__new__(cf.FileChatTool)
    tool.uid = 'u1'
    tool.thread_id = None
    tool.assistant_id = None
    tool.cleanup()

    assert deleted == ['oai-1', 'oai-orphan']
    assert [f.get('id') for f in firestore_deleted] == ['f1', 'broken']
