"""Tests for fetch_url_tool per-turn URL allowlist (prompt scoping + runtime enforcement)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.runnables import RunnableConfig

from models.chat import Message, MessageSender, MessageType
from utils.retrieval.agentic import (
    AGENT_SAFETY_INSTRUCTIONS,
    _inject_user_url_allowlist,
)
from utils.retrieval.tools.web_tools import (
    URL_NOT_ALLOWLISTED_MESSAGE,
    extract_urls_from_text,
    extract_user_turn_urls,
    fetch_url_tool,
    is_redirect_url_allowlisted,
    is_url_allowlisted,
    user_url_allowlist_block,
)


def _message(text: str, sender: MessageSender = MessageSender.human) -> Message:
    return Message(
        id='m1',
        text=text,
        created_at=datetime.now(timezone.utc),
        sender=sender,
        type=MessageType.text,
    )


class TestUrlExtraction:
    def test_extracts_urls_from_user_message(self):
        urls = extract_urls_from_text('Check https://example.com/article and http://foo.bar/baz.')
        assert urls == ['https://example.com/article', 'http://foo.bar/baz']

    def test_strips_trailing_punctuation(self):
        urls = extract_urls_from_text('See https://example.com/page, thanks!')
        assert urls == ['https://example.com/page']

    def test_preserves_balanced_parentheses(self):
        urls = extract_urls_from_text('See https://en.wikipedia.org/wiki/Function_(mathematics).')
        assert urls == ['https://en.wikipedia.org/wiki/Function_(mathematics)']

    def test_returns_all_urls_for_overflow_detection(self):
        text = ' '.join(f'https://example.com/{index}' for index in range(11))
        assert len(extract_urls_from_text(text)) == 11

    def test_extract_user_turn_urls_ignores_assistant_messages(self):
        messages = [
            _message('Old https://old.example.com/page'),
            _message('Reply with https://attacker.example.com/exfil', MessageSender.ai),
            _message('Summarize https://user.example.com/doc'),
        ]
        assert extract_user_turn_urls(messages) == ['https://user.example.com/doc']

    def test_extract_user_turn_urls_strips_sentence_terminal_punctuation(self):
        messages = [_message('Summarize https://example.com/article.')]
        assert extract_user_turn_urls(messages) == ['https://example.com/article']

    def test_extract_user_turn_urls_preserves_terminal_url_punctuation_in_explicit_delimiters(self):
        messages = [_message('Fetch <https://example.com/releases/v1.0.>')]
        assert extract_user_turn_urls(messages) == ['https://example.com/releases/v1.0.']

    def test_extract_user_turn_urls_preserves_terminal_url_punctuation_in_parentheses(self):
        messages = [_message('Fetch (https://example.com/releases/v1.0.)')]
        assert extract_user_turn_urls(messages) == ['https://example.com/releases/v1.0.']

    def test_extract_user_turn_urls_strips_unwrapped_sentence_punctuation(self):
        messages = [_message('Fetch https://example.com/article.!?')]
        assert extract_user_turn_urls(messages) == ['https://example.com/article']

    def test_extract_user_turn_urls_preserves_all_terminal_url_punctuation_in_backticks(self):
        messages = [_message('Fetch `https://example.com/releases/v1.0.!?`')]
        assert extract_user_turn_urls(messages) == ['https://example.com/releases/v1.0.!?']

    def test_extract_user_turn_urls_strips_closing_markdown_delimiters(self):
        messages = [_message('Fetch **https://example.com/article** and [https://example.com/docs]')]
        assert extract_user_turn_urls(messages) == ['https://example.com/article', 'https://example.com/docs']

    def test_extract_user_turn_urls_preserves_terminal_url_punctuation_in_markdown_delimiters(self):
        messages = [_message('Fetch **https://example.com/releases/v1.0.** and [https://example.com/releases/v2.0.?]')]
        assert extract_user_turn_urls(messages) == [
            'https://example.com/releases/v1.0.',
            'https://example.com/releases/v2.0.?',
        ]

    def test_extract_user_turn_urls_strips_closing_markdown_delimiters_before_sentence_punctuation(self):
        messages = [_message('Fetch **https://example.com/article**. and [https://example.com/docs].')]
        assert extract_user_turn_urls(messages) == ['https://example.com/article', 'https://example.com/docs']

    def test_extracted_terminal_url_punctuation_matches_literal_allowlist(self):
        url = extract_user_turn_urls([_message('Fetch <https://example.com/releases/v1.0.>')])[0]
        assert is_url_allowlisted(url, [url])

    def test_extract_user_turn_urls_bounds_overflow_scan(self):
        messages = [_message(' '.join(f'https://example.com/{index}' for index in range(1000)))]
        assert len(extract_user_turn_urls(messages, max_urls=11)) == 11

    def test_user_url_allowlist_block_empty_when_no_urls(self):
        assert user_url_allowlist_block([]) == ''

    def test_user_url_allowlist_block_lists_urls(self):
        block = user_url_allowlist_block(['https://example.com/a'])
        assert '<user_provided_urls>' in block
        assert 'https://example.com/a' in block


class TestPromptScoping:
    def test_agent_safety_instructions_forbid_unscoped_fetch(self):
        assert 'fetch_url_tool must not be used' in AGENT_SAFETY_INSTRUCTIONS
        assert '<user_provided_urls>' in AGENT_SAFETY_INSTRUCTIONS
        assert 'tool results' in AGENT_SAFETY_INSTRUCTIONS

    def test_inject_user_url_allowlist_prepends_to_latest_user_turn(self):
        messages = [{'role': 'user', 'content': 'hello https://example.com'}]
        updated = _inject_user_url_allowlist(messages, ['https://example.com'])
        assert '<user_provided_urls>' in updated[0]['content']
        assert 'https://example.com' in updated[0]['content']

    def test_inject_user_url_allowlist_skips_when_empty(self):
        messages = [{'role': 'user', 'content': 'hello'}]
        assert _inject_user_url_allowlist(messages, []) == messages


class TestRuntimeEnforcement:
    @pytest.mark.asyncio
    async def test_rejects_url_not_in_allowlist(self):
        config = RunnableConfig(configurable={'user_provided_urls': ['https://allowed.example.com']})
        result = await fetch_url_tool.ainvoke(
            {'url': 'https://attacker.example.com/steal?token=secret'},
            config=config,
        )
        assert result == URL_NOT_ALLOWLISTED_MESSAGE

    @pytest.mark.asyncio
    async def test_rejects_attacker_url_from_tool_result_scenario(self):
        """Simulate model trying to fetch a URL embedded in untrusted tool output."""
        user_url = 'https://user.example.com/article'
        attacker_url = 'https://attacker.example.com/exfil?data=leaked'
        config = RunnableConfig(configurable={'user_provided_urls': [user_url]})

        with patch('utils.retrieval.tools.web_tools._fetch_page', new_callable=AsyncMock) as mock_fetch:
            result = await fetch_url_tool.ainvoke({'url': attacker_url}, config=config)

        assert result == URL_NOT_ALLOWLISTED_MESSAGE
        mock_fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_when_allowlist_empty(self):
        config = RunnableConfig(configurable={'user_provided_urls': []})
        result = await fetch_url_tool.ainvoke({'url': 'https://example.com'}, config=config)
        assert result == URL_NOT_ALLOWLISTED_MESSAGE

    @pytest.mark.asyncio
    async def test_rejects_when_allowlist_missing(self):
        result = await fetch_url_tool.ainvoke({'url': 'https://example.com'})
        assert result == URL_NOT_ALLOWLISTED_MESSAGE

    @pytest.mark.asyncio
    async def test_allows_allowlisted_url(self):
        allowed = 'https://example.com/page'
        config = RunnableConfig(configurable={'user_provided_urls': [allowed]})

        with patch(
            'utils.retrieval.tools.web_tools._fetch_page',
            new_callable=AsyncMock,
            return_value=(200, 'text/html', '<html><body><p>Hello</p></body></html>'),
        ) as mock_fetch:
            result = await fetch_url_tool.ainvoke({'url': allowed}, config=config)

        assert mock_fetch.await_args.args[0] == allowed
        assert 'Content from' in result
        assert 'Hello' in result

    def test_is_url_allowlisted_rejects_outbound_trailing_punctuation(self):
        allowlist = ['https://example.com/page']
        assert not is_url_allowlisted('https://example.com/page.', allowlist)

    def test_is_url_allowlisted_accepts_literal_terminal_punctuation(self):
        allowlist = ['https://example.com/releases/v1.0.']
        assert is_url_allowlisted('https://example.com/releases/v1.0.', allowlist)

    def test_is_url_allowlisted_rejects_unlisted_path_parameters(self):
        allowlist = ['https://example.com/page']
        assert not is_url_allowlisted('https://example.com/page;secret', allowlist)

    def test_is_url_allowlisted_canonicalizes_host_and_default_port(self):
        allowlist = ['HTTPS://Example.COM:443/page']
        assert is_url_allowlisted('https://example.com/page', allowlist)

    def test_is_url_allowlisted_distinguishes_trailing_dot_hostname(self):
        assert not is_url_allowlisted('https://example.com/page', ['https://example.com./page'])
        assert is_url_allowlisted('https://example.com./page', ['https://example.com./page'])

    def test_is_url_allowlisted_rejects_unlisted_same_host_variants(self):
        allowlist = ['http://example.com/page']
        assert not is_url_allowlisted('https://example.com/page/', allowlist)
        assert not is_url_allowlisted('https://www.example.com/canonical', allowlist)
        assert not is_url_allowlisted('https://Example.COM/other', allowlist)
        assert not is_url_allowlisted('https://other.example/page', allowlist)

    def test_is_redirect_url_allowlisted_rejects_unlisted_same_host_variants(self):
        allowlist = ['http://example.com/page']
        assert not is_redirect_url_allowlisted('https://example.com/page/', allowlist)
        assert not is_redirect_url_allowlisted('https://www.example.com/canonical', allowlist)
        assert not is_redirect_url_allowlisted('https://other.example/page', allowlist)

    def test_is_redirect_url_allowlisted_allows_same_origin_canonical_redirect(self):
        allowlist = ['https://Example.COM:443/short']
        assert is_redirect_url_allowlisted('https://example.com/full', allowlist)

    @pytest.mark.asyncio
    async def test_rejects_same_host_variant_of_allowlisted_url(self):
        allowlist_url = 'http://example.com/page'
        fetch_url = 'https://www.example.com/canonical'
        config = RunnableConfig(configurable={'user_provided_urls': [allowlist_url]})

        with patch(
            'utils.retrieval.tools.web_tools._fetch_page',
            new_callable=AsyncMock,
            return_value=(200, 'text/html', '<html><body><p>Hello</p></body></html>'),
        ) as mock_fetch:
            result = await fetch_url_tool.ainvoke({'url': fetch_url}, config=config)

        mock_fetch.assert_not_called()
        assert result == URL_NOT_ALLOWLISTED_MESSAGE

    @pytest.mark.asyncio
    async def test_rejects_redirect_to_non_allowlisted_url(self):
        """Redirect targets must stay on an allowlisted host."""
        allowed = 'https://trusted.example/short'
        config = RunnableConfig(configurable={'user_provided_urls': [allowed]})

        class _FakeResponse:
            def __init__(self):
                self.status_code = 302
                self.headers = {'location': 'https://other.example/malicious'}

            async def aiter_bytes(self, chunk_size=8192):
                if False:
                    yield b''

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

        class _FakeClient:
            def __init__(self):
                self.urls = []

            def stream(self, method, url, **kwargs):
                self.urls.append(url)
                return _FakeResponse()

        client = _FakeClient()
        with (
            patch('utils.retrieval.tools.web_tools.get_web_fetch_client', return_value=client),
            patch(
                'utils.retrieval.tools.web_tools._hostname_is_public',
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            result = await fetch_url_tool.ainvoke({'url': allowed}, config=config)

        assert 'Redirect target is not in the current-turn user allowlist' in result
        assert client.urls == [allowed]

    @pytest.mark.asyncio
    async def test_allows_redirect_to_allowlisted_url(self):
        start = 'https://trusted.example/short'
        target = 'https://trusted.example/full'
        config = RunnableConfig(configurable={'user_provided_urls': [start, target]})

        class _FakeResponse:
            def __init__(self, status_code, headers=None, body=b''):
                self.status_code = status_code
                self.headers = headers or {}
                self._body = body

            async def aiter_bytes(self, chunk_size=8192):
                if self._body:
                    yield self._body

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

        class _FakeClient:
            def __init__(self):
                self.urls = []
                self._responses = [
                    _FakeResponse(302, headers={'location': target}),
                    _FakeResponse(200, headers={'content-type': 'text/html'}, body=b'<p>Hello</p>'),
                ]

            def stream(self, method, url, **kwargs):
                self.urls.append(url)
                return self._responses.pop(0)

        client = _FakeClient()
        with (
            patch('utils.retrieval.tools.web_tools.get_web_fetch_client', return_value=client),
            patch(
                'utils.retrieval.tools.web_tools._hostname_is_public',
                new_callable=AsyncMock,
                return_value=True,
            ),
        ):
            result = await fetch_url_tool.ainvoke({'url': start}, config=config)

        assert client.urls == [start, target]
        assert 'Content from' in result
        assert 'Hello' in result
