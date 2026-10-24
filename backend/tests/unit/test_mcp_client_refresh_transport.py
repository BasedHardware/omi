"""Refreshing is bounded, keeps the new token across candidates and never follows redirects."""

from unittest.mock import AsyncMock

import httpx
import pytest

from utils import mcp_client


@pytest.mark.asyncio
async def test_http_next_candidate_uses_the_refreshed_token(monkeypatch):
    seen = []

    async def initialize(url, token=None):
        seen.append((url, token))
        if token == 'old':
            raise PermissionError('expired')
        if url == 'https://mcp.example':
            response = httpx.Response(404, request=httpx.Request('POST', url))
            response.raise_for_status()
        return None

    monkeypatch.setattr(mcp_client, '_initialize_session', initialize)
    monkeypatch.setattr(
        mcp_client,
        '_mcp_post',
        AsyncMock(return_value=({'result': {'content': [{'type': 'text', 'text': 'ok'}]}}, None)),
    )
    refresh = AsyncMock(return_value='new')
    result = await mcp_client.call_mcp_tool('https://mcp.example', 'check', {}, 'old', refresh_access_token=refresh)
    assert result == 'ok'
    refresh.assert_awaited_once_with('old')
    assert seen == [('https://mcp.example', 'old'), ('https://mcp.example', 'new'), ('https://mcp.example/http', 'new')]


@pytest.mark.parametrize('transport', ['streamable_http', 'sse'])
@pytest.mark.asyncio
async def test_rejected_fresh_access_does_not_trigger_a_refresh_loop(monkeypatch, transport):
    reject = AsyncMock(side_effect=PermissionError('rejected'))
    monkeypatch.setattr(mcp_client, '_initialize_session', reject)
    monkeypatch.setattr(mcp_client, '_call_tool_via_sse', reject)
    refresh = AsyncMock(return_value='new')
    result = await mcp_client.call_mcp_tool('https://mcp.example', 'check', {}, 'old', transport, refresh)
    assert result.startswith('Error')
    refresh.assert_awaited_once_with('old')
    assert reject.await_count == 2


@pytest.mark.parametrize('transport', ['streamable_http', 'sse'])
@pytest.mark.asyncio
async def test_post_refresh_redirect_is_not_followed_or_retried(monkeypatch, transport):
    response = httpx.Response(
        307, request=httpx.Request('POST', 'https://mcp.example'), headers={'Location': 'https://elsewhere.example'}
    )
    redirect = httpx.HTTPStatusError('redirect', request=response.request, response=response)
    attempt = AsyncMock(side_effect=[PermissionError('expired'), redirect])
    monkeypatch.setattr(mcp_client, '_initialize_session', attempt)
    monkeypatch.setattr(mcp_client, '_call_tool_via_sse', attempt)
    refresh = AsyncMock(return_value='new')
    with pytest.raises(httpx.HTTPStatusError):
        await mcp_client.call_mcp_tool('https://mcp.example', 'check', {}, 'old', transport, refresh)
    refresh.assert_awaited_once()
    assert attempt.await_count == 2


@pytest.mark.parametrize('transport', ['streamable_http', 'sse'])
@pytest.mark.asyncio
async def test_discovery_propagates_unauthorized_to_the_refresh_owner(monkeypatch, transport):
    response = httpx.Response(404, request=httpx.Request('POST', 'https://mcp.example'))
    missing = httpx.HTTPStatusError('missing', request=response.request, response=response)
    initialize = AsyncMock(side_effect=PermissionError('expired') if transport == 'streamable_http' else missing)
    sse = AsyncMock(side_effect=PermissionError('expired'))
    monkeypatch.setattr(mcp_client, '_initialize_session', initialize)
    monkeypatch.setattr(mcp_client, '_discover_tools_via_sse', sse)
    with pytest.raises(PermissionError):
        await mcp_client.discover_mcp_tools('https://mcp.example/http', 'old')
    if transport == 'streamable_http':
        sse.assert_not_awaited()
    else:
        sse.assert_awaited_once()


@pytest.mark.asyncio
async def test_sse_post_unauthorized_stops_before_sending_more_payloads(monkeypatch):
    requests = []

    def respond(request):
        requests.append(request.method)
        if request.method == 'GET':
            return httpx.Response(200, text='event: endpoint\ndata: /messages\n\n')
        return httpx.Response(401)

    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        mcp_client.httpx, 'AsyncClient', lambda **kwargs: client_class(transport=httpx.MockTransport(respond), **kwargs)
    )
    with pytest.raises(PermissionError):
        await mcp_client._sse_send_and_receive('https://mcp.example/sse', [{'id': 1}, {'id': 3}], 'old')
    assert requests == ['GET', 'POST']
