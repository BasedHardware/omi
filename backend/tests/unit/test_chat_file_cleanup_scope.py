import os
from datetime import datetime, timezone

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")

import pytest

import utils.other.chat_file as chat_file


def _session(session_id, file_ids):
    return {'id': session_id, 'file_ids': file_ids, 'created_at': datetime.now(timezone.utc)}


class _ChatDb:
    """Mirrors the production contract: no ids means every file the account owns."""

    def __init__(self):
        self.files = {
            'file-a': {'id': 'file-a', 'openai_file_id': 'openai-a'},
            'file-b': {'id': 'file-b', 'openai_file_id': 'openai-b'},
        }
        self.sessions = {
            'session-a': _session('session-a', ['file-a']),
            'session-b': _session('session-b', ['file-b']),
            'session-empty': _session('session-empty', []),
        }

    def get_chat_session_by_id(self, _uid, session_id):
        return self.sessions.get(session_id)

    def get_chat_files(self, _uid, files_id=None):
        if not files_id:
            return list(self.files.values())
        return [self.files[file_id] for file_id in files_id if file_id in self.files]

    def delete_multi_files(self, _uid, files_data):
        for file_data in files_data:
            self.files.pop(file_data['id'], None)


@pytest.fixture
def chat_db(monkeypatch):
    fake = _ChatDb()
    deleted = []
    monkeypatch.setattr(chat_file, 'chat_db', fake)
    monkeypatch.setattr(
        chat_file.openai,
        'files',
        type('Files', (), {'delete': staticmethod(lambda file_id, **_kwargs: deleted.append(file_id))})(),
    )
    return fake, deleted


def test_clearing_one_chat_keeps_the_other_sessions_files(chat_db):
    fake, deleted = chat_db

    chat_file.FileChatTool('u1', 'session-a').cleanup()

    assert sorted(fake.files) == ['file-b']
    assert deleted == ['openai-a']


def test_clearing_a_chat_without_files_deletes_nothing(chat_db):
    fake, deleted = chat_db

    chat_file.FileChatTool('u1', 'session-empty').cleanup()

    assert sorted(fake.files) == ['file-a', 'file-b']
    assert deleted == []
