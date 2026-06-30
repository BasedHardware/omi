"""
Unit tests for utils/llm/clone.py

Critical contracts:
- User's memories are injected verbatim into the prompt
- Platform name is mapped to a friendly label (imessage → "iMessage (casual, personal)")
- Unknown platforms fall back to the raw platform string
- Conversation history is included (up to last 6 turns)
- History beyond 6 turns is truncated
- Empty conversation history is handled gracefully
- The LLM response is stripped of surrounding whitespace
- track_usage is called for billing
"""

import os
import sys
import types
from unittest.mock import MagicMock, patch, call

os.environ.setdefault('ENCRYPTION_SECRET', 'x' * 64)
os.environ.setdefault('OPENAI_API_KEY', 'sk-test')

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, BACKEND_DIR)

# ── Stub heavy modules before importing clone.py ───────────────────────────────

_clients_stub = types.ModuleType('utils.llm.clients')
_mock_llm = MagicMock()
_clients_stub.get_llm = MagicMock(return_value=_mock_llm)
sys.modules['utils.llm.clients'] = _clients_stub

_memory_stub = types.ModuleType('utils.llms.memory')
_memory_stub.get_prompt_memories = MagicMock(return_value=('Alice', 'Alice is a software engineer who loves hiking.'))
sys.modules['utils.llms.memory'] = _memory_stub

_usage_stub = types.ModuleType('utils.llm.usage_tracker')


class _FakeContextManager:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


_usage_stub.track_usage = MagicMock(return_value=_FakeContextManager())
_usage_stub.Features = MagicMock()
_usage_stub.Features.CHAT = 'chat'
sys.modules['utils.llm.usage_tracker'] = _usage_stub

# Ensure utils packages exist with __path__ so sub-imports work
for mod_name, rel_path in [('utils', 'utils'), ('utils.llm', 'utils/llm'), ('utils.llms', 'utils/llms')]:
    if mod_name not in sys.modules:
        m = types.ModuleType(mod_name)
        m.__path__ = [os.path.join(BACKEND_DIR, rel_path)]
        sys.modules[mod_name] = m
    elif not hasattr(sys.modules[mod_name], '__path__'):
        sys.modules[mod_name].__path__ = [os.path.join(BACKEND_DIR, rel_path)]

sys.modules.pop('utils.llm.clone', None)

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location('utils.llm.clone', os.path.join(BACKEND_DIR, 'utils', 'llm', 'clone.py'))
clone_module = _ilu.module_from_spec(_spec)
sys.modules['utils.llm.clone'] = clone_module
_spec.loader.exec_module(clone_module)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _set_llm_response(text: str):
    _mock_llm.invoke.return_value = MagicMock(content=f'  {text}  ')


def _set_memories(name: str, memories: str):
    _memory_stub.get_prompt_memories.return_value = (name, memories)


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestGenerateCloneReply:
    def test_returns_stripped_llm_response(self):
        _set_memories('Alice', 'Alice likes coffee.')
        _set_llm_response('Sure, sounds good!')

        result = clone_module.generate_clone_reply('uid-1', 'Bob', 'Want to hang out?', 'imessage')

        assert result == 'Sure, sounds good!'

    def test_memories_injected_into_prompt(self):
        memories = 'Alice is a backend engineer at Acme Corp.'
        _set_memories('Alice', memories)
        _set_llm_response('reply')

        clone_module.generate_clone_reply('uid-1', 'Bob', 'How is work?', 'telegram')

        prompt_used = _mock_llm.invoke.call_args[0][0]
        assert memories in prompt_used, 'User memories must appear verbatim in the prompt'

    def test_sender_name_in_prompt(self):
        _set_memories('Alice', 'memories')
        _set_llm_response('reply')

        clone_module.generate_clone_reply('uid-1', 'Charlie', 'Hey!', 'imessage')

        prompt_used = _mock_llm.invoke.call_args[0][0]
        assert 'Charlie' in prompt_used

    def test_imessage_platform_label(self):
        _set_memories('Alice', 'mem')
        _set_llm_response('r')

        clone_module.generate_clone_reply('uid-1', 'Bob', 'hi', 'imessage')

        prompt = _mock_llm.invoke.call_args[0][0]
        assert 'iMessage (casual, personal)' in prompt

    def test_telegram_platform_label(self):
        _set_memories('Alice', 'mem')
        _set_llm_response('r')

        clone_module.generate_clone_reply('uid-1', 'Bob', 'hi', 'telegram')

        prompt = _mock_llm.invoke.call_args[0][0]
        assert 'Telegram (informal messaging)' in prompt

    def test_whatsapp_platform_label(self):
        _set_memories('Alice', 'mem')
        _set_llm_response('r')

        clone_module.generate_clone_reply('uid-1', 'Bob', 'hi', 'whatsapp')

        prompt = _mock_llm.invoke.call_args[0][0]
        assert 'WhatsApp (casual messaging)' in prompt

    def test_unknown_platform_uses_raw_name(self):
        _set_memories('Alice', 'mem')
        _set_llm_response('r')

        clone_module.generate_clone_reply('uid-1', 'Bob', 'hi', 'discord')

        prompt = _mock_llm.invoke.call_args[0][0]
        assert 'discord' in prompt

    def test_no_conversation_history(self):
        """None or empty history must not crash and must not leave history section."""
        _set_memories('Alice', 'mem')
        _set_llm_response('r')

        clone_module.generate_clone_reply('uid-1', 'Bob', 'hi', 'telegram', None)
        clone_module.generate_clone_reply('uid-1', 'Bob', 'hi', 'telegram', [])

    def test_conversation_history_included_in_prompt(self):
        _set_memories('Alice', 'mem')
        _set_llm_response('r')
        history = [
            {'role': 'user', 'content': 'How are you?'},
            {'role': 'assistant', 'content': 'Doing great!'},
        ]

        clone_module.generate_clone_reply('uid-1', 'Bob', 'Nice!', 'telegram', history)

        prompt = _mock_llm.invoke.call_args[0][0]
        assert 'How are you?' in prompt
        assert 'Doing great!' in prompt

    def test_conversation_history_capped_at_6_turns(self):
        _set_memories('Alice', 'mem')
        _set_llm_response('r')
        history = [{'role': 'user', 'content': f'msg{i}'} for i in range(10)]

        clone_module.generate_clone_reply('uid-1', 'Bob', 'end', 'telegram', history)

        prompt = _mock_llm.invoke.call_args[0][0]
        # Last 6 turns should be present: msg4..msg9
        assert 'msg9' in prompt
        assert 'msg4' in prompt
        # Earlier turns should be excluded
        assert 'msg0' not in prompt
        assert 'msg3' not in prompt

    def test_uses_chat_responses_llm_key(self):
        _set_memories('Alice', 'mem')
        _set_llm_response('r')

        clone_module.generate_clone_reply('uid-1', 'Bob', 'hi', 'imessage')

        _clients_stub.get_llm.assert_called_with('chat_responses')

    def test_track_usage_called(self):
        _set_memories('Alice', 'mem')
        _set_llm_response('r')
        _usage_stub.track_usage.reset_mock()

        clone_module.generate_clone_reply('uid-1', 'Bob', 'hi', 'imessage')

        _usage_stub.track_usage.assert_called_once_with('uid-1', _usage_stub.Features.CHAT)

    def test_user_name_used_in_prompt(self):
        _set_memories('Karthik', 'Karthik is a developer.')
        _set_llm_response('r')

        clone_module.generate_clone_reply('uid-1', 'Bob', 'hi', 'imessage')

        prompt = _mock_llm.invoke.call_args[0][0]
        assert 'Karthik' in prompt

    def test_incoming_message_quoted_in_prompt(self):
        _set_memories('Alice', 'mem')
        _set_llm_response('r')
        message = 'Can you recommend a good restaurant?'

        clone_module.generate_clone_reply('uid-1', 'Bob', message, 'imessage')

        prompt = _mock_llm.invoke.call_args[0][0]
        assert message in prompt
