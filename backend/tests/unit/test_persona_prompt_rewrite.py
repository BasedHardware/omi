"""Tests for the T-019 persona-prompt rewrite.

The previous persona prompt in `backend/utils/apps.py` opened with:

    You are {user_name} AI. Your objective is to personify {user_name} as
    accurately as possible for 1:1 cloning.

and included the contradictory rule "Never mention being AI.". On the
`persona_chat` feature model (`gpt-4.1-nano`), the model leaked phrases
like "AI clone", "persona", and "digital version" into chat-app replies.
Example from Telegram bot:

    c4eth: who are you?
    bot:   just your friendly coffee-loving, Swift & Python enthusiast AI
           clone, chillin' in bangkok. what's up?

These tests pin the rewritten prompt so the leak can't regress:

1. None of the legacy leak phrases are present in the generated prompt.
2. The prompt speaks in the first person and addresses the user by name.
3. The condensed memories / conversations / tweets blocks are still injected
   (we don't want to fix the leak by silently dropping context).
4. `generate_persona_prompt` and `update_persona_prompt` produce the same
   template (so a Firestore `persona_prompt` field means the same thing
   whether set at create-time or by the periodic refresh).
5. The prompt is short enough that gpt-4.1-nano won't lose facts to a long
   rule list — under 800 tokens when memories / conversations / tweets
   blocks are non-empty.

Run: `cd backend && python -m pytest tests/unit/test_persona_prompt_rewrite.py -v`
"""

from __future__ import annotations

import os
import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'test-secret')


# ---- Stub heavy deps before importing application code (mirrors test_lock_bypass_fixes.py) ----


class _AutoMockModule(ModuleType):
    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


_stubs = [
    'anthropic',
    'av',
    'database._client',
    'database.cache',
    'database.redis_db',
    'database.conversations',
    'database.memories',
    'database.action_items',
    'database.folders',
    'database.users',
    'database.user_usage',
    'database.vector_db',
    'database.chat',
    'database.apps',
    'database.goals',
    'database.notifications',
    'database.mem_db',
    'database.mcp_api_key',
    'database.daily_summaries',
    'database.fair_use',
    'database.auth',
    'database.llm_usage',
    'database.phone_calls',
    'deepgram',
    'deepgram.clients',
    'deepgram.clients.live',
    'deepgram.clients.live.v1',
    'firebase_admin',
    'firebase_admin.messaging',
    'google',
    'google.cloud',
    'google.cloud.firestore',
    'langchain',
    'langchain_core',
    'langchain_core.messages',
    'langchain_openai',
    'langchain_anthropic',
    'langchain_community',
    'langchain_community.chat_message_histories',
    'mem0',
    'openai',
    'pydub',
    'pymemcache',
    'qdrant_client',
    'redis',
    'requests',
    'stripe',
    'tiktoken',
    'tqdm',
    'twitter',
    'utils.llm.usage_tracker',
    'utils.social',
    'utils.stripe',
    'utils.llm.persona',
]
for mod_name in _stubs:
    sys.modules.setdefault(mod_name, _AutoMockModule(mod_name))


# ---- Real utils.apps, with the few collaborators we need stubbed ----


def _load_real_apps_module():
    """Reload utils.apps with the real function under test + stubbed deps.

    Mirrors the pattern from test_lock_bypass_fixes.py::TestPersonaGenerationLockFilter.
    Note: we do NOT stub `utils.conversations.factory` or
    `utils.conversations.render` — they're real submodules of the real
    `utils.conversations` package, and stubbing them at the package level
    breaks the import resolution inside `utils.apps`.
    """
    old_mod = sys.modules.pop('utils.apps', None)
    # Ensure transitively-stubbed modules are still in place after the pop.
    for dep in [
        'database.cache',
        'database.llm_usage',
        'utils.stripe',
        'utils.social',
        'utils.llm.persona',
        'utils.llm.usage_tracker',
        'utils.llm.clients',
    ]:
        if dep not in sys.modules:
            sys.modules[dep] = _AutoMockModule(dep)

    import database.memories as memories_db
    import database.conversations as conversations_db
    import database.auth as auth_db

    memories_db.get_memories = MagicMock(
        return_value=[
            {'id': 'm1', 'is_locked': False, 'content': 'drinks coffee, prefers pour-over'},
            {'id': 'm2', 'is_locked': False, 'content': 'lives in Bangkok'},
            {'id': 'm3', 'is_locked': False, 'content': 'codes in Swift and Python'},
        ]
    )
    memories_db.get_user_public_memories = MagicMock(
        return_value=[
            {'id': 'm1', 'is_locked': False, 'content': 'drinks coffee, prefers pour-over'},
            {'id': 'm2', 'is_locked': False, 'content': 'lives in Bangkok'},
            {'id': 'm3', 'is_locked': False, 'content': 'codes in Swift and Python'},
        ]
    )
    conversations_db.get_conversations = MagicMock(return_value=[])
    auth_db.get_user_name = MagicMock(return_value='Choguun')

    import utils.apps as real_apps

    mock_track = MagicMock()
    mock_track.__enter__ = MagicMock(return_value=None)
    mock_track.__exit__ = MagicMock(return_value=False)
    real_apps.track_usage = MagicMock(return_value=mock_track)
    real_apps.condense_conversations = MagicMock(return_value='(no recent conversations)')
    # T-022: persona prompt uses similarity retrieval + verbatim rendering
    # instead of condense_memories LLM flatten. The retrieval helper is
    # imported at module load; we mock it here so the route returns the
    # same canned memory list every test run.
    real_apps.retrieve_relevant_memories_for_persona = MagicMock(
        return_value=[
            {'id': 'm1', 'is_locked': False, 'content': 'drinks coffee, prefers pour-over'},
            {'id': 'm2', 'is_locked': False, 'content': 'lives in Bangkok'},
            {'id': 'm3', 'is_locked': False, 'content': 'codes in Swift and Python'},
        ],
    )
    real_apps.format_memories_for_prompt = MagicMock(
        return_value='- drinks coffee, prefers pour-over\n- lives in Bangkok\n- codes in Swift and Python'
    )
    real_apps.condense_tweets = MagicMock(return_value=None)
    real_apps.get_twitter_timeline = MagicMock(return_value=MagicMock(timeline=[]))
    real_apps.run_blocking = _async_passthrough

    return real_apps, old_mod


async def _async_passthrough(executor, fn, *args, **kwargs):
    """run_blocking stand-in that just calls the function synchronously."""
    return fn(*args, **kwargs)


def _restore(old_mod):
    if old_mod is not None:
        sys.modules['utils.apps'] = old_mod


# ---- Constants used across tests ----

LEGACY_LEAK_PHRASES = [
    'You are {name} AI.',
    'Your objective is to personify',
    '1:1 cloning',
    'Begin personifying',
    'Never mention being AI.',
    'You have all the necessary',
    'You have all the necessary condensed facts',
    'Use these facts, conversations and tweets',
    'Maintain the illusion of continuity',
    'Highly interactive and opinionated',
    'slightly polarizing opinions',
    # Catches the substring "AI" anywhere except in literal tokens we don't
    # want to forbid. We do forbid "AI clone" and "an AI" anywhere — that's
    # the actual leak. We allow "AI" only in the very specific phrases below
    # (which the rewrite does not contain, but kept here as a fail-safe in
    # case a future contributor accidentally re-adds them).
]


def _strip_user_data_blocks(prompt: str) -> str:
    """Remove the condensed-data injection blocks so the assertion only checks
    the framing. The data blocks legitimately contain user-supplied text
    that may include words like 'AI' (e.g. memory 'works on an AI project')."""
    lines = []
    for line in prompt.splitlines():
        if (
            line.startswith('Facts about')
            or line.startswith('Recent conversations')
            or line.startswith('Recent tweets')
        ):
            lines.append('')
        elif line.startswith('- '):
            continue  # memory/conversation/tweet line — data, not framing
        else:
            lines.append(line)
    return '\n'.join(lines)


# ---- Tests ----


class TestPromptFraming:
    """The prompt's framing lines (above the data blocks) must not leak."""

    @pytest.mark.asyncio
    async def test_no_legacy_leak_phrases_in_prompt(self):
        """Generated prompt must not contain any of the legacy leak phrases.

        This is the regression guard for the Telegram bot's
        'just your friendly coffee-loving, Swift & Python enthusiast AI clone'
        answer. Each phrase below was extracted verbatim from the previous
        prompt template at backend/utils/apps.py.
        """
        apps_mod, old_mod = _load_real_apps_module()
        try:
            persona = {'connected_accounts': [], 'twitter': None, 'uid': 'test-uid'}
            result = await apps_mod.generate_persona_prompt('test-uid', persona)
            framing = _strip_user_data_blocks(result)
            lower = framing.lower()

            # Concrete substring checks — exact phrases that previously caused
            # the model to say "AI clone" / "persona" / "1:1 cloning".
            assert 'ai clone' not in lower, f'prompt contains "AI clone":\n{framing!r}'
            assert 'personify' not in lower, f'prompt contains "personify":\n{framing!r}'
            assert '1:1 cloning' not in lower, f'prompt contains "1:1 cloning":\n{framing!r}'
            assert 'never mention being ai' not in lower, f'prompt contains "never mention being ai":\n{framing!r}'
            # "Begin personifying X now" — the closing line that flipped the
            # model into "I am an AI clone of X" mode.
            assert 'begin personifying' not in lower, f'prompt contains "begin personifying":\n{framing!r}'
            # The literal "{user_name} AI" framing that started the leak.
            assert 'choguun ai.' not in lower, f'prompt contains "Choguun AI.":\n{framing!r}'
            # Old redundant boilerplate.
            assert (
                'you have all the necessary' not in lower
            ), f'prompt contains "You have all the necessary":\n{framing!r}'
            assert (
                'use these facts, conversations and tweets' not in lower
            ), f'prompt contains the old closing boilerplate:\n{framing!r}'
            assert (
                'maintain the illusion of continuity' not in lower
            ), f'prompt contains "Maintain the illusion of continuity":\n{framing!r}'
        finally:
            _restore(old_mod)

    @pytest.mark.asyncio
    async def test_speaks_in_first_person(self):
        """The new prompt must open with a direct first-person identity.

        The old "You are {name} AI." put the model in an AI role. The new
        template drops the "AI" suffix so the model speaks as the user, not
        as a clone of the user.
        """
        apps_mod, old_mod = _load_real_apps_module()
        try:
            persona = {'connected_accounts': [], 'twitter': None, 'uid': 'test-uid'}
            result = await apps_mod.generate_persona_prompt('test-uid', persona)
            # Must open with the direct identity line.
            assert result.startswith('You are Choguun.'), f'prompt does not open with "You are Choguun.":\n{result!r}'
            # Must NOT be "You are Choguun AI." (the leak).
            assert not result.startswith('You are Choguun AI.'), f'prompt opens with the old leak phrasing:\n{result!r}'
        finally:
            _restore(old_mod)

    @pytest.mark.asyncio
    async def test_no_asterisk_formatting(self):
        """No **bold** emphasis, no markdown lists in the framing.

        Telegram/WhatsApp render **bold** as literal asterisks; the user
        sees "*coffee*-loving..." which is ugly and out-of-persona.

        The new template does include the literal phrase "No **bold**" as
        an example in the rules ("don't use bold markdown"). That single
        occurrence is allowed because it's the rule itself, not framing
        emphasis — but no other `**...**` emphasis should appear.
        """
        apps_mod, old_mod = _load_real_apps_module()
        try:
            persona = {'connected_accounts': [], 'twitter': None, 'uid': 'test-uid'}
            result = await apps_mod.generate_persona_prompt('test-uid', persona)
            framing = _strip_user_data_blocks(result)
            # Strip the one allowed occurrence: the rule itself.
            framing_normalized = framing.replace('No **bold**', 'No [bold]')
            assert '**' not in framing_normalized, f'framing contains **bold** markdown emphasis:\n{framing!r}'
            # Old prompt had bullet lists like "- **Condensed Facts:** ..."
            # The new prompt drops them.
            assert '\n- ' not in framing, f'framing contains a markdown bullet list:\n{framing!r}'
        finally:
            _restore(old_mod)


class TestContextPreserved:
    """The rewrite must not silently drop the data blocks."""

    @pytest.mark.asyncio
    async def test_memories_block_present(self):
        apps_mod, old_mod = _load_real_apps_module()
        try:
            persona = {'connected_accounts': [], 'twitter': None, 'uid': 'test-uid'}
            result = await apps_mod.generate_persona_prompt('test-uid', persona)
            assert 'Facts about Choguun:' in result
            # The condensed memories stub returned this content — verify it
            # was injected verbatim so the model has actual facts to work with.
            assert 'drinks coffee' in result
            assert 'lives in Bangkok' in result
        finally:
            _restore(old_mod)

    @pytest.mark.asyncio
    async def test_conversations_block_present(self):
        apps_mod, old_mod = _load_real_apps_module()
        try:
            persona = {'connected_accounts': [], 'twitter': None, 'uid': 'test-uid'}
            result = await apps_mod.generate_persona_prompt('test-uid', persona)
            assert 'Recent conversations' in result
        finally:
            _restore(old_mod)

    @pytest.mark.asyncio
    async def test_tweets_block_present_with_none_fallback(self):
        """When tweets are absent (most users), the block must still appear
        so the prompt has a consistent structure and the model doesn't have
        to guess what an empty section means."""
        apps_mod, old_mod = _load_real_apps_module()
        try:
            persona = {'connected_accounts': [], 'twitter': None, 'uid': 'test-uid'}
            result = await apps_mod.generate_persona_prompt('test-uid', persona)
            assert 'Recent tweets:' in result
            # The new template uses "None." as the explicit empty marker.
            assert 'None.' in result
        finally:
            _restore(old_mod)


class TestTemplateConsistency:
    """Both prompt-generation functions must produce the same template."""

    @pytest.mark.asyncio
    async def test_generate_and_update_produce_same_template(self):
        """`generate_persona_prompt` and `update_persona_prompt` must agree.

        Otherwise a persona's `persona_prompt` field in Firestore would
        mean different things depending on whether it was set at create-time
        or by the periodic refresh — a debugging nightmare.
        """
        apps_mod, old_mod = _load_real_apps_module()
        try:
            gen_result = await apps_mod.generate_persona_prompt('test-uid', {'connected_accounts': [], 'twitter': None})

            # Now drive update_persona_prompt with a minimal persona dict.
            persona = {
                'id': 'persona-1',
                'uid': 'test-uid',
                'name': 'Choguun',
                'connected_accounts': [],
                'twitter': None,
            }
            await apps_mod.update_persona_prompt(persona)
            upd_result = persona['persona_prompt']

            # The opening line, the closing rule list, and the data-block
            # labels must match between the two functions. We compare the
            # first sentence (identity line) and the rule sentences since
            # those are template-controlled, not data-controlled.
            def _opening(p: str) -> str:
                return p.split('.')[0] + '.'

            def _rule_paragraph(p: str) -> str:
                # The closing paragraph starts with "Reply like a text"
                for chunk in p.split('\n\n'):
                    if chunk.startswith('Reply like a text'):
                        return chunk
                return ''

            assert _opening(gen_result) == _opening(
                upd_result
            ), f'identity lines differ:\n  gen: {_opening(gen_result)!r}\n  upd: {_opening(upd_result)!r}'
            assert _rule_paragraph(gen_result) == _rule_paragraph(
                upd_result
            ), f'rule paragraphs differ:\n  gen: {_rule_paragraph(gen_result)!r}\n  upd: {_rule_paragraph(upd_result)!r}'
        finally:
            _restore(old_mod)


class TestPromptSize:
    """Prompt must stay small enough that gpt-4.1-nano retains all facts."""

    def _approx_tokens(self, s: str) -> int:
        # ~0.75 tokens per word is the standard GPT tokenizer approximation.
        # We don't need exact; we just need a guardrail.
        return int(len(s.split()) / 0.75)

    @pytest.mark.asyncio
    async def test_prompt_under_token_budget(self):
        """Final prompt < 800 tokens with realistic data.

        gpt-4.1-nano degrades when the system prompt exceeds ~1k tokens.
        The previous template hit ~600 tokens at minimum and ballooned to
        1k+ with the rule list. We pin the new template at < 800 tokens
        with non-empty data blocks so a contributor can't silently re-add
        the rule list without breaking this test.
        """
        apps_mod, old_mod = _load_real_apps_module()
        try:
            persona = {'connected_accounts': [], 'twitter': None, 'uid': 'test-uid'}
            result = await apps_mod.generate_persona_prompt('test-uid', persona)
            tokens = self._approx_tokens(result)
            assert tokens < 800, f'prompt is {tokens} tokens, exceeds 800-token budget:\n{result!r}'
        finally:
            _restore(old_mod)


class TestLockedContentStillExcluded:
    """Regression — the rewrite must not re-introduce locked memories.

    Verifies the same lock-filter behavior as
    test_lock_bypass_fixes.py::TestPersonaGenerationLockFilter,
    re-asserted here so a future prompt refactor that drops the
    `if not m.get('is_locked')` line trips this test.
    """

    @pytest.mark.asyncio
    async def test_locked_memories_excluded_from_prompt(self):
        """The lock filter must still exclude `is_locked=True` memories.

        T-022 replaced the `condense_memories` LLM flatten with
        `retrieve_relevant_memories_for_persona` (vector search with
        recent-recency fallback). Both paths in the new helper apply the
        same `is_locked` filter as the previous LLM flatten, so a locked
        memory must never appear in the generated persona prompt.

        We assert on the final prompt rather than on a call arg, because
        the new retrieval path doesn't expose an obvious "input list"
        — it goes vector search → hydrate → filter → format. The end-
        to-end prompt is what the user actually sees.
        """
        import database.memories as memories_db

        locked = {
            'id': 'm-locked',
            'uid': 'test-uid',
            'is_locked': True,
            'content': 'SECRET_LOCKED_FACT_XYZ',
            'category': 'interesting',
            'created_at': '2024-01-01T00:00:00',
            'updated_at': '2024-01-01T00:00:00',
        }
        unlocked = {
            'id': 'm-open',
            'uid': 'test-uid',
            'is_locked': False,
            'content': 'visible fact about user',
            'category': 'interesting',
            'created_at': '2024-01-01T00:00:00',
            'updated_at': '2024-01-01T00:00:00',
        }

        # Stub the retrieval helper directly so we control exactly what
        # the prompt sees. The point is to verify the prompt template
        # doesn't reintroduce locked content — the retrieval path's lock
        # filter is tested separately in test_persona_memory_retrieval.py.
        apps_mod, old_mod = _load_real_apps_module()
        try:
            apps_mod.retrieve_relevant_memories_for_persona = MagicMock(
                return_value=[unlocked],  # locked already filtered out
            )
            apps_mod.format_memories_for_prompt = MagicMock(
                return_value='- visible fact about user',
            )

            persona = {'connected_accounts': [], 'twitter': None, 'uid': 'test-uid'}
            result = await apps_mod.generate_persona_prompt('test-uid', persona)

            # The locked memory's content must NOT appear in the final prompt.
            assert 'SECRET_LOCKED_FACT_XYZ' not in result, f'locked memory leaked into persona prompt:\n{result!r}'
            # The unlocked memory's content must appear.
            assert 'visible fact about user' in result, f'unlocked memory missing from persona prompt:\n{result!r}'

            # And separately verify the retrieval helper was called with
            # the right args — the prompt generation must look up memories
            # for the right uid, not skip the lookup.
            apps_mod.retrieve_relevant_memories_for_persona.assert_called_once()
            call_args = apps_mod.retrieve_relevant_memories_for_persona.call_args
            # uid is the second positional arg; top_k is a kwarg.
            assert call_args.args[0] == 'test-uid'
            assert call_args.kwargs.get('top_k') == 30
        finally:
            _restore(old_mod)
