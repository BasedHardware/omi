"""T-020 storage tests for the Telegram plugin's recent-messages ring buffer.

The buffer is a per-chat list[{'role','text','ts'}] capped at CHAT_HISTORY_MAX
(10). Older entries drop FIFO via list slicing in append_message. These
tests pin the buffer's invariants:

- get_recent_messages returns [] for unknown chats
- append_message adds entries in order, oldest first
- append_message trims to CHAT_HISTORY_MAX (FIFO)
- invalid role / non-string / empty text are silently dropped
- clear_recent_messages wipes the buffer
- append_message no-ops (with warning) for unknown chat_ids
- Per-chat isolation: chats don't see each other's entries
- save_user pre-seeds recent_messages=[] for new users (no missing-key
  surprises at the call site)

Run: `cd plugins/omi-telegram-app && OMI_DEV_MODE=1 pytest test/test_recent_messages_storage.py -v`
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault('OMI_DEV_MODE', '1')
os.environ.setdefault('TELEGRAM_WEBHOOK_SECRET', 'test-secret')
os.environ.setdefault('AI_CLONE_PLUGIN_TOKEN', 'test-token')


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    """Point the storage layer at a tmp dir so tests don't pollute users_data.json."""
    monkeypatch.setenv('STORAGE_DIR', str(tmp_path))
    # Force a fresh import per test so the in-memory `users` dict is clean.
    import importlib
    import sys

    # Remove any cached module so re-import picks up the new STORAGE_DIR.
    sys.modules.pop('simple_storage', None)
    import simple_storage  # noqa: F401  -- intentional fresh import

    yield


def _make_user(chat_id='42'):
    """Insert a minimal user record so we can exercise the buffer."""
    import simple_storage

    simple_storage.save_user(
        chat_id=chat_id,
        omi_uid='uid-1',
        persona_id='persona-1',
        omi_dev_api_key='dev-key',
        bot_token='bot-token',
        auto_reply_enabled=True,
    )


class TestGetRecentMessages:
    def test_unknown_chat_returns_empty(self):
        import simple_storage

        assert simple_storage.get_recent_messages('999') == []

    def test_known_chat_with_no_messages_returns_empty(self):
        import simple_storage

        _make_user('42')
        assert simple_storage.get_recent_messages('42') == []

    def test_save_user_pre_seeds_empty_list(self):
        """New users must have recent_messages=[] so callers don't need to
        handle the missing-key case. The T-020 migration shouldn't silently
        break existing user records."""
        import simple_storage

        _make_user('42')
        user = simple_storage.get_user_by_chat_id('42')
        assert 'recent_messages' in user
        assert user['recent_messages'] == []


class TestAppendMessage:
    def test_append_in_order_oldest_first(self):
        import simple_storage

        _make_user('42')
        simple_storage.append_message('42', 'human', 'hi')
        simple_storage.append_message('42', 'ai', 'hey')
        simple_storage.append_message('42', 'human', "what's up?")
        msgs = simple_storage.get_recent_messages('42')
        assert [m['role'] for m in msgs] == ['human', 'ai', 'human']
        assert [m['text'] for m in msgs] == ['hi', 'hey', "what's up?"]

    def test_append_records_iso_timestamp(self):
        import simple_storage

        _make_user('42')
        simple_storage.append_message('42', 'human', 'hi')
        msg = simple_storage.get_recent_messages('42')[0]
        assert isinstance(msg['ts'], str)
        # ISO 8601 — should parse cleanly via fromisoformat.
        from datetime import datetime

        ts = datetime.fromisoformat(msg['ts'])
        assert ts.year >= 2024

    def test_trims_to_chat_history_max(self):
        """FIFO: append CHAT_HISTORY_MAX + 5 entries, oldest 5 dropped."""
        import simple_storage

        _make_user('42')
        max_entries = simple_storage.CHAT_HISTORY_MAX
        for i in range(max_entries + 5):
            simple_storage.append_message('42', 'human', f'msg-{i}')
        msgs = simple_storage.get_recent_messages('42')
        assert len(msgs) == max_entries
        # First retained entry is the (5th from end) — older entries drop.
        assert msgs[0]['text'] == 'msg-5'
        assert msgs[-1]['text'] == f'msg-{max_entries + 4}'

    def test_invalid_role_silently_dropped(self):
        import simple_storage

        _make_user('42')
        simple_storage.append_message('42', 'system', 'oops')  # not human/ai
        assert simple_storage.get_recent_messages('42') == []

    def test_empty_text_silently_dropped(self):
        import simple_storage

        _make_user('42')
        simple_storage.append_message('42', 'human', '')
        assert simple_storage.get_recent_messages('42') == []

    def test_non_string_text_silently_dropped(self):
        import simple_storage

        _make_user('42')
        simple_storage.append_message('42', 'human', 42)  # not a str
        assert simple_storage.get_recent_messages('42') == []

    def test_unknown_chat_id_no_op(self):
        """append_message shouldn't crash the webhook if the chat isn't bound yet."""
        import simple_storage

        simple_storage.append_message('999', 'human', 'hi')  # unknown chat
        assert simple_storage.get_recent_messages('999') == []


class TestClearRecentMessages:
    def test_clear_empties_buffer(self):
        import simple_storage

        _make_user('42')
        simple_storage.append_message('42', 'human', 'hi')
        simple_storage.append_message('42', 'ai', 'hey')
        assert len(simple_storage.get_recent_messages('42')) == 2
        simple_storage.clear_recent_messages('42')
        assert simple_storage.get_recent_messages('42') == []

    def test_clear_unknown_chat_is_safe(self):
        import simple_storage

        # Should not raise — caller might pass a stale chat_id.
        simple_storage.clear_recent_messages('999')


class TestPerChatIsolation:
    def test_chats_dont_share_buffers(self):
        """Two different chats must not see each other's messages."""
        import simple_storage

        _make_user('42')
        _make_user('99')
        simple_storage.append_message('42', 'human', 'to alice')
        simple_storage.append_message('99', 'human', 'to bob')
        msgs_42 = simple_storage.get_recent_messages('42')
        msgs_99 = simple_storage.get_recent_messages('99')
        assert [m['text'] for m in msgs_42] == ['to alice']
        assert [m['text'] for m in msgs_99] == ['to bob']
