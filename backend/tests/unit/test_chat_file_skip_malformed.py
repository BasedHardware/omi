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
