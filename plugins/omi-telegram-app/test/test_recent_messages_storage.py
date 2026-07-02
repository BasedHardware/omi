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


def _make_user(chat_id='42', persona='persona-1', uid='uid-1'):
    """Insert a minimal user record so we can exercise the buffer."""
    import simple_storage

    simple_storage.save_user(
        chat_id=chat_id,
        omi_uid=uid,
        persona_id=persona,
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


class TestRebindWipesHistory:
    """P1 from cubic AI review: rebinding a chat to a different persona
    or omi_uid MUST wipe the previous owner's history. Without this,
    user A's chat history would silently leak into user B's persona
    prompt on a re-bind."""

    def test_rebind_to_different_persona_wipes_history(self):
        import simple_storage

        _make_user('42', persona='persona-A', uid='uid-A')
        simple_storage.append_message('42', 'human', 'alice told bob a secret')
        simple_storage.append_message('42', 'ai', 'ack secret')
        assert len(simple_storage.get_recent_messages('42')) == 2

        # Rebind to a different persona (same omi_uid is fine — the
        # existing user record would be carried forward, but we expect
        # the persona change to trigger a wipe).
        simple_storage.save_user(
            chat_id='42',
            omi_uid='uid-A',
            persona_id='persona-B',
            omi_dev_api_key='dev-key',
            bot_token='bot-token',
            auto_reply_enabled=True,
        )
        assert simple_storage.get_recent_messages('42') == []

    def test_rebind_to_different_uid_wipes_history(self):
        import simple_storage

        _make_user('42', persona='persona-X', uid='uid-X')
        simple_storage.append_message('42', 'human', 'leaky message')
        simple_storage.append_message('42', 'ai', 'leaky reply')
        assert len(simple_storage.get_recent_messages('42')) == 2

        simple_storage.save_user(
            chat_id='42',
            omi_uid='uid-Y',
            persona_id='persona-X',
            omi_dev_api_key='dev-key',
            bot_token='bot-token',
            auto_reply_enabled=True,
        )
        assert simple_storage.get_recent_messages('42') == []

    def test_same_identity_re_save_preserves_history(self):
        """Re-saving the same chat (e.g., token rotation, nudge update)
        MUST NOT wipe the buffer — that would erase legitimate context."""
        import simple_storage

        _make_user('42', persona='persona-X', uid='uid-X')
        simple_storage.append_message('42', 'human', 'keep me')
        simple_storage.append_message('42', 'ai', 'kept')

        simple_storage.save_user(
            chat_id='42',
            omi_uid='uid-X',
            persona_id='persona-X',
            omi_dev_api_key='dev-key',
            bot_token='bot-token',
            auto_reply_enabled=False,
        )
        assert len(simple_storage.get_recent_messages('42')) == 2


class TestAppendTurnAtomic:
    """P2 from cubic AI review: appending both halves of a turn via two
    separate append_message() calls risks persisting a half-turn on
    crash. append_turn() commits both entries in a single save so they
    land together or not at all."""

    def test_human_and_ai_land_together(self):
        import simple_storage

        _make_user('42')
        simple_storage.append_turn('42', human_text='hello', ai_text='hi back')
        msgs = simple_storage.get_recent_messages('42')
        assert len(msgs) == 2
        assert msgs[0]['role'] == 'human'
        assert msgs[0]['text'] == 'hello'
        assert msgs[1]['role'] == 'ai'
        assert msgs[1]['text'] == 'hi back'

    def test_empty_ai_text_no_op(self):
        """append_turn refuses to persist a half-turn even when called
        via the atomic helper. Both human and ai must be non-empty."""
        import simple_storage

        _make_user('42')
        simple_storage.append_turn('42', human_text='hello', ai_text='')
        assert simple_storage.get_recent_messages('42') == []

    def test_empty_human_text_no_op(self):
        import simple_storage

        _make_user('42')
        simple_storage.append_turn('42', human_text='', ai_text='hi')
        assert simple_storage.get_recent_messages('42') == []


class TestGetReturnsDeepCopy:
    """P2 from cubic AI review: the previous shallow list() copy let
    callers mutate nested fields and silently corrupt the stored
    history. Verify deep-copy semantics."""

    def test_mutating_returned_list_does_not_affect_storage(self):
        import simple_storage

        _make_user('42')
        simple_storage.append_message('42', 'human', 'keep me safe')
        msgs = simple_storage.get_recent_messages('42')
        original_ts = msgs[0]['ts']
        msgs.clear()
        # Storage still has the entry — a deep copy means clearing the
        # returned list leaves the in-memory dict intact.
        fresh = simple_storage.get_recent_messages('42')
        assert len(fresh) == 1
        assert fresh[0] == {'role': 'human', 'text': 'keep me safe', 'ts': original_ts}

    def test_mutating_nested_dict_does_not_affect_storage(self):
        import simple_storage

        _make_user('42')
        simple_storage.append_message('42', 'human', 'keep me safe')
        msgs = simple_storage.get_recent_messages('42')
        msgs[0]['text'] = 'MUTATED'
        msgs[0]['role'] = 'system'
        # Re-read; should still see the original.
        fresh = simple_storage.get_recent_messages('42')
        assert fresh[0]['text'] == 'keep me safe'
        assert fresh[0]['role'] == 'human'


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


class TestDurabilityChain:
    """P1 from cubic AI review (PR #8682): every save must run the
    full durability chain — tmp file fsync, os.replace, parent
    directory fsync. Skipping any step risks zeros/garbage on power
    loss. The previous round tried to skip the tmp file fsync on
    history writes for a perf win, but USERS_FILE holds both
    credentials AND recent_messages in the same JSON, so a skipped
    fsync on a history append could leave the credential file as
    zeros/garbage. Reverted: always fsync, accept the 5-30ms cost."""

    def test_save_does_not_accept_fsync_kwarg(self):
        """The round-4 `fsync=` parameter is gone — all saves go
        through the full durability chain. Pinning this so a future
        refactor doesn't re-introduce the per-callsite fsync knob
        without realizing the credential-vs-history split is at the
        file level (single USERS_FILE), not the call site."""
        import inspect

        import simple_storage

        sig = inspect.signature(simple_storage._save)
        params = list(sig.parameters.keys())
        # _save(path, payload) — no fsync kwarg.
        assert 'fsync' not in params, (
            f"_save must not accept fsync (single USERS_FILE holds " f"creds + history). Got parameters: {params}"
        )

    def test_save_fsyncs_tmp_file_and_parent_directory(self):
        """Pin the full durability chain: tmp file gets fsynced (so
        contents are on stable storage), then os.replace, then the
        parent directory gets fsynced (so the rename link itself
        survives power loss). A future refactor that drops the
        parent-dir fsync re-introduces the P2 from cubic AI review."""
        from unittest.mock import patch

        import simple_storage

        with patch.object(simple_storage.os, 'fsync') as mock_fsync, patch.object(
            simple_storage.os, 'open', wraps=simple_storage.os.open
        ) as mock_open:
            _make_user('42')
            simple_storage.append_message('42', 'human', 'hi')

        # We expect at least two fsync calls: one for the tmp file
        # (during the `with open(tmp, "w") as f:` block) and one for
        # the parent directory (after os.replace).
        assert mock_fsync.call_count >= 2, (
            f"_save must fsync both the tmp file and the parent " f"directory. Got {mock_fsync.call_count} fsync calls."
        )

        # At least one fsync must have been on a directory fd (O_RDONLY
        # of the parent dir), not the tmp file fd. The mock records
        # all the args passed to os.open; filter to ones opening the
        # parent directory.
        parent_dir = os.path.dirname(simple_storage.USERS_FILE)
        opened_parent = [
            call_args
            for call_args in mock_open.call_args_list
            if len(call_args.args) >= 1 and call_args.args[0] == parent_dir
        ]
        assert opened_parent, (
            f"_save must open the parent directory ({parent_dir}) to "
            f"fsync the rename link. open calls: "
            f"{[c.args for c in mock_open.call_args_list]}"
        )
