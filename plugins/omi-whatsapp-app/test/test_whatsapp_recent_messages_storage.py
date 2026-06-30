"""T-020 storage tests for the WhatsApp plugin's recent-messages ring buffer.

Phone-keyed buffer (vs chat_id-keyed for Telegram) because Meta's WhatsApp
Cloud API identifies a 1:1 conversation by the sender's phone number.
Same shape, same CHAT_HISTORY_MAX (10), same FIFO trim, same defensive
no-op semantics as the Telegram plugin.

Mirrors plugins/omi-telegram-app/test/test_recent_messages_storage.py so a
future shared base class can host both. We keep the tests separate because
the two plugins' conftest setup differs (sys.modules isolation for cross-
plugin test runs) and the user/chat_id vs user/phone storage keying differs.

Run: `cd plugins/omi-whatsapp-app && OMI_DEV_MODE=1 pytest test/test_whatsapp_recent_messages_storage.py -v`
"""

from __future__ import annotations

import os

import pytest

# conftest.py loads when pytest collects this file. The autouse
# `_whatsapp_sys_modules_isolation` fixture there handles sys.modules
# swapping for the test's duration.
from conftest import load_simple_storage


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    """Point the storage layer at a tmp dir and reset in-memory state per test.

    The conftest autouse fixture caches the loaded simple_storage module
    across tests (to keep Telegram's tests from colliding). That means the
    in-memory `users` dict persists across tests within this file. We
    explicitly clear it here so each test starts from a clean slate.
    """
    monkeypatch.setenv('STORAGE_DIR', str(tmp_path))
    mod = load_simple_storage()
    # Reset module-level state. We deliberately don't reload the module —
    # the conftest's autouse fixture relies on the cached object.
    mod.users = {}
    mod.pending_setups = {}
    mod.USERS_FILE = os.path.join(str(tmp_path), 'users_data.json')
    mod.PENDING_FILE = os.path.join(str(tmp_path), 'pending_setups.json')
    yield


def _make_user(phone='+15550000001', persona='persona-1', uid='uid-1'):
    """Insert a minimal user record so we can exercise the buffer."""
    mod = load_simple_storage()
    mod.save_user(
        phone=phone,
        omi_uid=uid,
        persona_id=persona,
        omi_dev_api_key='dev-key',
        access_token='access-token',
        phone_number_id='phone-id-1',
        verify_token='verify-token-1',
        auto_reply_enabled=True,
    )


class TestGetRecentMessages:
    def test_unknown_phone_returns_empty(self):
        mod = load_simple_storage()
        assert mod.get_recent_messages('+19990000000') == []

    def test_known_phone_with_no_messages_returns_empty(self):
        _make_user('+15550000001')
        mod = load_simple_storage()
        assert mod.get_recent_messages('+15550000001') == []

    def test_save_user_pre_seeds_empty_list(self):
        _make_user('+15550000001')
        mod = load_simple_storage()
        # The user record is keyed by raw phone (no leading '+'), so look
        # up via the storage key. save_user str-coerces the phone; we
        # pass it as-is.
        user = mod.users.get('+15550000001')
        assert 'recent_messages' in user
        assert user['recent_messages'] == []


class TestAppendMessage:
    def test_append_in_order_oldest_first(self):
        _make_user('+15550000001')
        mod = load_simple_storage()
        mod.append_message('+15550000001', 'human', 'hi')
        mod.append_message('+15550000001', 'ai', 'hey')
        mod.append_message('+15550000001', 'human', "what's up?")
        msgs = mod.get_recent_messages('+15550000001')
        assert [m['role'] for m in msgs] == ['human', 'ai', 'human']
        assert [m['text'] for m in msgs] == ['hi', 'hey', "what's up?"]

    def test_append_records_iso_timestamp(self):
        _make_user('+15550000001')
        mod = load_simple_storage()
        mod.append_message('+15550000001', 'human', 'hi')
        msg = mod.get_recent_messages('+15550000001')[0]
        assert isinstance(msg['ts'], str)
        from datetime import datetime

        ts = datetime.fromisoformat(msg['ts'])
        assert ts.year >= 2024

    def test_trims_to_chat_history_max(self):
        """FIFO: append CHAT_HISTORY_MAX + 5 entries, oldest 5 dropped."""
        _make_user('+15550000001')
        mod = load_simple_storage()
        max_entries = mod.CHAT_HISTORY_MAX
        for i in range(max_entries + 5):
            mod.append_message('+15550000001', 'human', f'msg-{i}')
        msgs = mod.get_recent_messages('+15550000001')
        assert len(msgs) == max_entries
        assert msgs[0]['text'] == 'msg-5'
        assert msgs[-1]['text'] == f'msg-{max_entries + 4}'

    def test_invalid_role_silently_dropped(self):
        _make_user('+15550000001')
        mod = load_simple_storage()
        mod.append_message('+15550000001', 'system', 'oops')  # not human/ai
        assert mod.get_recent_messages('+15550000001') == []

    def test_empty_text_silently_dropped(self):
        _make_user('+15550000001')
        mod = load_simple_storage()
        mod.append_message('+15550000001', 'human', '')
        assert mod.get_recent_messages('+15550000001') == []

    def test_non_string_text_silently_dropped(self):
        _make_user('+15550000001')
        mod = load_simple_storage()
        mod.append_message('+15550000001', 'human', 42)
        assert mod.get_recent_messages('+15550000001') == []

    def test_unknown_phone_no_op(self):
        """append_message shouldn't crash the webhook if the phone isn't bound yet."""
        mod = load_simple_storage()
        mod.append_message('+19990000000', 'human', 'hi')  # unknown
        assert mod.get_recent_messages('+19990000000') == []


class TestClearRecentMessages:
    def test_clear_empties_buffer(self):
        _make_user('+15550000001')
        mod = load_simple_storage()
        mod.append_message('+15550000001', 'human', 'hi')
        mod.append_message('+15550000001', 'ai', 'hey')
        assert len(mod.get_recent_messages('+15550000001')) == 2
        mod.clear_recent_messages('+15550000001')
        assert mod.get_recent_messages('+15550000001') == []

    def test_clear_unknown_phone_is_safe(self):
        mod = load_simple_storage()
        # Should not raise — caller might pass a stale phone.
        mod.clear_recent_messages('+19990000000')


class TestRebindWipesHistory:
    """P1 from cubic AI review: rebinding a phone to a different persona
    or omi_uid MUST wipe the previous owner's history. Same shape as the
    Telegram plugin's TestRebindWipesHistory."""

    def test_rebind_to_different_persona_wipes_history(self):
        _make_user('+15550000001', persona='persona-A', uid='uid-A')
        mod = load_simple_storage()
        mod.append_message('+15550000001', 'human', 'alice told bob a secret')
        mod.append_message('+15550000001', 'ai', 'ack secret')
        assert len(mod.get_recent_messages('+15550000001')) == 2

        mod.save_user(
            phone='+15550000001',
            omi_uid='uid-A',
            persona_id='persona-B',
            omi_dev_api_key='dev-key',
            access_token='access-token',
            phone_number_id='phone-id-1',
            verify_token='verify-token-1',
            auto_reply_enabled=True,
        )
        assert mod.get_recent_messages('+15550000001') == []

    def test_rebind_to_different_uid_wipes_history(self):
        _make_user('+15550000001', persona='persona-X', uid='uid-X')
        mod = load_simple_storage()
        mod.append_message('+15550000001', 'human', 'leaky message')
        mod.append_message('+15550000001', 'ai', 'leaky reply')
        assert len(mod.get_recent_messages('+15550000001')) == 2

        mod.save_user(
            phone='+15550000001',
            omi_uid='uid-Y',
            persona_id='persona-X',
            omi_dev_api_key='dev-key',
            access_token='access-token',
            phone_number_id='phone-id-1',
            verify_token='verify-token-1',
            auto_reply_enabled=True,
        )
        assert mod.get_recent_messages('+15550000001') == []

    def test_same_identity_re_save_preserves_history(self):
        _make_user('+15550000001', persona='persona-X', uid='uid-X')
        mod = load_simple_storage()
        mod.append_message('+15550000001', 'human', 'keep me')
        mod.append_message('+15550000001', 'ai', 'kept')

        mod.save_user(
            phone='+15550000001',
            omi_uid='uid-X',
            persona_id='persona-X',
            omi_dev_api_key='dev-key',
            access_token='access-token',
            phone_number_id='phone-id-1',
            verify_token='verify-token-1',
            auto_reply_enabled=False,
        )
        assert len(mod.get_recent_messages('+15550000001')) == 2


class TestAppendTurnAtomic:
    """P2 from cubic AI review: append_turn commits both halves of a
    turn in a single save so a crash between writes can't persist a
    half-turn."""

    def test_human_and_ai_land_together(self):
        _make_user('+15550000001')
        mod = load_simple_storage()
        mod.append_turn('+15550000001', human_text='hello', ai_text='hi back')
        msgs = mod.get_recent_messages('+15550000001')
        assert len(msgs) == 2
        assert msgs[0]['role'] == 'human'
        assert msgs[0]['text'] == 'hello'
        assert msgs[1]['role'] == 'ai'
        assert msgs[1]['text'] == 'hi back'

    def test_empty_ai_text_no_op(self):
        _make_user('+15550000001')
        mod = load_simple_storage()
        mod.append_turn('+15550000001', human_text='hello', ai_text='')
        assert mod.get_recent_messages('+15550000001') == []


class TestGetReturnsDeepCopy:
    """P2 from cubic AI review: verify deep-copy semantics for the
    returned recent-messages list."""

    def test_mutating_nested_dict_does_not_affect_storage(self):
        _make_user('+15550000001')
        mod = load_simple_storage()
        mod.append_message('+15550000001', 'human', 'keep me safe')
        msgs = mod.get_recent_messages('+15550000001')
        msgs[0]['text'] = 'MUTATED'
        msgs[0]['role'] = 'system'
        fresh = mod.get_recent_messages('+15550000001')
        assert fresh[0]['text'] == 'keep me safe'
        assert fresh[0]['role'] == 'human'


class TestPerPhoneIsolation:
    def test_phones_dont_share_buffers(self):
        """Two different phones must not see each other's messages."""
        _make_user('+15550000001')
        _make_user('+15550000002')
        mod = load_simple_storage()
        mod.append_message('+15550000001', 'human', 'to alice')
        mod.append_message('+15550000002', 'human', 'to bob')
        msgs_1 = mod.get_recent_messages('+15550000001')
        msgs_2 = mod.get_recent_messages('+15550000002')
        assert [m['text'] for m in msgs_1] == ['to alice']
        assert [m['text'] for m in msgs_2] == ['to bob']
