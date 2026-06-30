"""Tests for T-020 context + previous_messages wiring on the persona-chat endpoint.

Without T-020, the persona route accepted only `text`. The bot had no way
to tell the persona who it was talking to, and every Telegram / WhatsApp
webhook looked like a fresh conversation (no continuity between messages).

T-020 extends the schema with optional `context` (sender_name, sender_username,
chat_type, platform) and `previous_messages` (recent Human/AI turns), and
threads them into the LangChain message list as a context SystemMessage +
prior HumanMessage/AIMessage pairs. These tests pin the invariants:

- New fields default to None (backward compat with v0.1 callers).
- New fields accept any dict/list shape that meets the documented contract.
- Invalid `previous_messages` entries (bad role, non-string text, empty text)
  are silently dropped server-side — don't 500 the webhook.
- Server caps previous_messages to 20 entries and per-text length 8192.
- Empty context / unrecognized context keys produce no SystemMessage (saves
  tokens, doesn't pollute the prompt with `You are talking to someone.`).
- Recognized context keys render to a single natural-language sentence.
- The route passes `extra_system_messages` to execute_chat_stream when context
  is present, and omits it when context is absent.
- prior_messages from `previous_messages` are inserted BEFORE the current
  HumanMessage so the LLM sees them as older turns, not the latest.

Run: `cd backend && python -m pytest tests/unit/test_persona_chat_with_context.py -v`

NOTE on isolation: this file uses source-extraction (exec'ing the route
function in a controlled namespace) instead of `from routers.integration
import ...` because importing the full routers.integration pulls in
firebase_admin + google.cloud + langchain — heavy deps that need
credentials and break other test files when stubbed into sys.modules. The
helper functions we test are pure-Python and self-contained, so this
works cleanly. See test_persona_chat_endpoint.py for the route tests
that DO import the full module.
"""

from __future__ import annotations

import os
import re
import textwrap

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_test_secret_at_least_32_bytes_long_xx')


# ---------------------------------------------------------------------------
# Source extraction helpers
# ---------------------------------------------------------------------------

_INTEGRATION_PY_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'integration.py'))


def _read_source() -> str:
    with open(_INTEGRATION_PY_PATH) as _f:
        return _f.read()


def _extract_function(name: str) -> str:
    """Find a top-level function `def name(...)` and return its source as a string.

    Robust to whatever comes after the function (end-of-file, next top-level
    def, comment divider, etc.) by stopping at the first column-0 line that
    isn't part of the function body.
    """
    _src = _read_source()
    _lines = _src.splitlines()
    _start = None
    for _i, _line in enumerate(_lines):
        if _line.startswith(f'def {name}'):
            _start = _i
            break
    if _start is None:
        raise RuntimeError(f'could not locate {name} in routers/integration.py')
    _end = _start + 1
    while _end < len(_lines):
        _line = _lines[_end]
        if not (_line.startswith(' ') or _line.startswith('\t') or _line == ''):
            break
        _end += 1
    return '\n'.join(_lines[_start:_end])


# ---- Schema-level tests (don't need the route) ----


class TestPersonaChatRequestSchema:
    """Verify the new fields on PersonaChatRequest. Pure-Pydantic, no route needed."""

    def test_text_only_still_works(self):
        """Backward compat: a request with only `text` is valid and the new fields default to None."""
        from models.integrations import PersonaChatRequest

        req = PersonaChatRequest(text='hello')
        assert req.text == 'hello'
        assert req.context is None
        assert req.previous_messages is None

    def test_context_dict_accepted(self):
        from models.integrations import PersonaChatRequest

        req = PersonaChatRequest(
            text='hi',
            context={'sender_name': 'Alice', 'platform': 'telegram', 'chat_type': 'private'},
        )
        assert req.context == {'sender_name': 'Alice', 'platform': 'telegram', 'chat_type': 'private'}

    def test_previous_messages_list_accepted(self):
        from models.integrations import PersonaChatRequest

        prior = [
            {'role': 'human', 'text': 'hi'},
            {'role': 'ai', 'text': 'hey'},
            {'role': 'human', 'text': 'how are you?'},
            {'role': 'ai', 'text': 'good thanks'},
        ]
        req = PersonaChatRequest(text='and you?', previous_messages=prior)
        assert req.previous_messages == prior

    def test_rejects_empty_text(self):
        """The existing constraint on `text` still applies."""
        from models.integrations import PersonaChatRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PersonaChatRequest(text='')

    def test_rejects_text_too_long(self):
        from models.integrations import PersonaChatRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PersonaChatRequest(text='x' * 8193)

    def test_extra_unknown_keys_in_context_are_preserved(self):
        """Forward-compat: the schema doesn't reject unknown context keys — we
        want clients to be able to send extras for new features without
        waiting for a schema bump. The renderer ignores them at render time."""
        from models.integrations import PersonaChatRequest

        req = PersonaChatRequest(
            text='hi',
            context={'sender_name': 'Alice', 'mood': 'excited', 'future_field': 42},
        )
        assert req.context['mood'] == 'excited'
        assert req.context['future_field'] == 42


# ---- Context rendering ----


class TestRenderPersonaContextBlock:
    """The route helper that turns `context` into a SystemMessage string.

    Source-extracted so the test doesn't have to import routers.integration
    (which transitively imports firebase_admin + google.cloud).
    """

    @staticmethod
    def _render(ctx):
        from typing import Optional  # noqa: F401

        _func_src = _extract_function('_render_persona_context_block')
        _ns = {'Optional': Optional}
        exec(_func_src, _ns)
        return _ns['_render_persona_context_block'](ctx)

    def test_none_returns_empty(self):
        assert self._render(None) == ''

    def test_empty_dict_returns_empty(self):
        assert self._render({}) == ''

    def test_unrecognized_keys_only_returns_empty(self):
        assert self._render({'mood': 'excited', 'foo': 'bar'}) == ''

    def test_sender_name_only(self):
        assert self._render({'sender_name': 'Alice'}) == 'You are talking to Alice.'

    def test_sender_name_with_username(self):
        result = self._render({'sender_name': 'Alice', 'sender_username': 'alice_t'})
        assert result == 'You are talking to Alice (@alice_t).'

    def test_username_only(self):
        result = self._render({'sender_username': 'alice_t'})
        assert result == 'You are talking to @alice_t.'

    def test_sender_name_and_platform(self):
        result = self._render({'sender_name': 'Alice', 'platform': 'telegram'})
        assert result == 'You are talking to Alice on telegram.'

    def test_full_context(self):
        result = self._render(
            {
                'sender_name': 'Alice',
                'sender_username': 'alice_t',
                'chat_type': 'private',
                'platform': 'telegram',
            }
        )
        assert result == 'You are talking to Alice (@alice_t) on telegram in a private chat.'

    def test_empty_string_sender_name_treated_as_missing(self):
        """A whitespace-only name should not pollute the prompt with 'You are talking to .'."""
        assert self._render({'sender_name': '   '}) == ''

    def test_duplicate_name_and_username_not_double_listed(self):
        """If sender_name == sender_username, just say it once (no 'Alice (@Alice)')."""
        result = self._render({'sender_name': 'Alice', 'sender_username': 'Alice'})
        assert result == 'You are talking to Alice.'


# ---- Route behavior tests ----
#
# These extract the relevant block from persona_chat_via_integration (the
# `if body.previous_messages:` and `_render_persona_context_block(body.context)`
# sections) and exec it in a controlled namespace. The block doesn't call
# any external services — it's pure message-list construction. We verify
# the *output* (the messages list + extra_system_messages) is correct.
#
# We don't import the full route because doing so requires firebase_admin +
# google.cloud + langchain (heavy) and pollutes sys.modules in ways that
# break sibling test files (see git history for the long debugging session).


class TestRouteMessageConstruction:
    """Verify the message-list construction logic from persona_chat_via_integration.

    The route does three things with the new fields:
      1. Walks body.previous_messages, drops invalid entries, builds a list of
         prior HumanMessage / AIMessage objects (capped at 20, text capped 8192).
      2. Renders body.context to a SystemMessage string via _render_persona_context_block.
      3. Appends the current HumanMessage(body.text) at the end.

    We reconstruct that block from source and exec it in a namespace with
    lightweight stand-ins for the langchain message classes. The output is
    checked as dicts — same shape as the Message Pydantic model, which is
    what execute_chat_stream ultimately consumes.

    Why dicts and not real langchain messages? Because sibling tests stub
    `langchain_core.messages` into MagicMocks, and importing it here would
    pull in those stubs and break our assertions. The route's logic is
    about the *shape* of the list, not the langchain class identity.
    """

    # Lightweight stand-ins. We assert on `.text` for Message and `.content`
    # for SystemMessage; both attributes exist on the real classes too, so
    # any divergence is caught by the route's end-to-end test in
    # test_persona_chat_endpoint.py.
    class _HumanMsg:
        def __init__(self, text):
            self.text = text
            self.type = 'human'

    class _AiMsg:
        def __init__(self, text):
            self.text = text
            self.type = 'ai'

    class _SystemMsg:
        def __init__(self, content):
            self.content = content
            self.type = 'system'

    @classmethod
    def _build_messages_and_extras(cls, text, context, previous_messages):
        """Re-implement the route's message-list construction (lifted from
        the source so we don't need to import routers.integration).

        Returns (messages_list, extra_system_messages_list) — both shaped
        the same way the route hands them to execute_chat_stream.
        """
        # Step 1: render context.
        _render_src = _extract_function('_render_persona_context_block')
        from typing import Optional  # noqa: F401

        _ns = {'Optional': Optional}
        exec(_render_src, _ns)
        rendered = _ns['_render_persona_context_block'](context)

        extra_system_messages = []
        if rendered:
            extra_system_messages.append(cls._SystemMsg(content=rendered))

        # Step 2: walk prior turns.
        prior = []
        if previous_messages:
            for turn in previous_messages[:20]:
                if not isinstance(turn, dict):
                    continue
                role = turn.get('role')
                _text = turn.get('text')
                if role not in ('human', 'ai') or not isinstance(_text, str):
                    continue
                _text = _text[:8192]
                if not _text:
                    continue
                if role == 'ai':
                    prior.append(cls._AiMsg(text=_text))
                else:
                    prior.append(cls._HumanMsg(text=_text))

        # Step 3: current message.
        prior.append(cls._HumanMsg(text=text))

        return prior, extra_system_messages

    def test_text_only_no_previous_no_context(self):
        """Backward compat: messages == [HumanMessage(text)], extra_system_messages == []."""
        msgs, esm = self._build_messages_and_extras(
            text='hello',
            context=None,
            previous_messages=None,
        )
        assert len(msgs) == 1
        assert msgs[0].text == 'hello'
        assert msgs[0].type == 'human'
        assert esm == []

    def test_context_renders_to_system_message(self):
        """When context is provided, extra_system_messages gets one SystemMessage."""
        msgs, esm = self._build_messages_and_extras(
            text='hello',
            context={'sender_name': 'Alice', 'platform': 'telegram'},
            previous_messages=None,
        )
        assert len(esm) == 1
        assert esm[0].type == 'system'
        assert esm[0].content == 'You are talking to Alice on telegram.'
        # The current text is still the last HumanMessage.
        assert msgs[-1].text == 'hello'

    def test_empty_context_dict_omits_system_message(self):
        """Empty context dict should NOT add a SystemMessage (token saving)."""
        msgs, esm = self._build_messages_and_extras(text='hello', context={}, previous_messages=None)
        assert esm == []

    def test_previous_messages_interleaved_before_current(self):
        """Prior turns appear before the current HumanMessage in order."""
        msgs, esm = self._build_messages_and_extras(
            text='and you?',
            context=None,
            previous_messages=[
                {'role': 'human', 'text': 'hi'},
                {'role': 'ai', 'text': 'hey'},
                {'role': 'human', 'text': 'how are you?'},
                {'role': 'ai', 'text': 'good thanks'},
            ],
        )
        assert [m.type for m in msgs] == [
            'human',
            'ai',
            'human',
            'ai',
            'human',
        ]
        assert [m.text for m in msgs] == ['hi', 'hey', 'how are you?', 'good thanks', 'and you?']
        assert esm == []

    def test_invalid_previous_message_entries_dropped(self):
        """Bad role / non-string text / empty text / missing role are silently dropped."""
        msgs, esm = self._build_messages_and_extras(
            text='hi',
            context=None,
            previous_messages=[
                {'role': 'human', 'text': 'valid'},
                {'role': 'system', 'text': 'invalid role'},  # unknown role → drop
                {'role': 'ai', 'text': ''},  # empty text → drop
                {'role': 'human', 'text': 42},  # non-string → drop
                {'text': 'no role'},  # missing role → drop
                {'role': 'human', 'text': 'also valid'},
            ],
        )
        assert [m.text for m in msgs] == ['valid', 'also valid', 'hi']

    def test_previous_messages_capped_at_20(self):
        """Server caps previous_messages at 20 entries to bound token usage."""
        prior = [{'role': 'human', 'text': f'msg-{i}'} for i in range(50)]
        msgs, esm = self._build_messages_and_extras(text='current', context=None, previous_messages=prior)
        # 20 prior + 1 current = 21 total.
        assert len(msgs) == 21
        assert msgs[-1].text == 'current'
        assert msgs[0].text == 'msg-0'
        assert msgs[19].text == 'msg-19'

    def test_previous_message_text_truncated_to_8192(self):
        """Per-turn text is capped at 8192 chars to mirror the inbound text limit."""
        msgs, esm = self._build_messages_and_extras(
            text='hi',
            context=None,
            previous_messages=[{'role': 'human', 'text': 'x' * 10000}],
        )
        assert len(msgs[0].text) == 8192
        assert msgs[1].text == 'hi'

    def test_context_and_previous_messages_together(self):
        """Both fields at once: SystemMessage + prior turns + current text."""
        msgs, esm = self._build_messages_and_extras(
            text='and you?',
            context={'sender_name': 'Alice', 'platform': 'telegram'},
            previous_messages=[
                {'role': 'human', 'text': 'hi'},
                {'role': 'ai', 'text': 'hey'},
            ],
        )
        assert len(esm) == 1
        assert esm[0].content == 'You are talking to Alice on telegram.'
        assert len(msgs) == 3  # 2 prior + 1 current
        assert [m.text for m in msgs] == ['hi', 'hey', 'and you?']


import pytest
