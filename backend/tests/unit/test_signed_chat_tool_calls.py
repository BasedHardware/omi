"""Chat-tool calls carry a v2 X-Omi-Signature when the app has a signing secret (#20939).

Every test drives ``app_tools._call_tool_endpoint`` against a real httpx client on a
``MockTransport``, so the assertions run on the request as it leaves Omi (method, raw path and
query, headers, body bytes), not on the arguments handed to a mock. The receiver side is the
contract in ``utils/webhook_signing.verify_request``, fed exactly what a receiver would see.
"""

import json
import uuid
from typing import Any
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qsl

import httpx
import pytest
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

import utils.retrieval.tools.app_tools as app_tools
from database import webhook_signing as store
from database.webhook_signing import WebhookSigningSecrets
from models.app import ChatTool
from utils import webhook_signing as signing

UID = 'u1AbC'
APP_ID = '01KAPP'
CURRENT = 'whsec_current'
PREVIOUS = 'whsec_previous'
CONFIG = {'configurable': {'user_id': UID}}
_RealAsyncClient = httpx.AsyncClient


def _tool(name, method='POST', endpoint=None):
    return ChatTool(
        name=name,
        description='d',
        endpoint=endpoint or f'https://tools.example.com/tools/{name}',
        method=method,
    )


@pytest.fixture
def wire(monkeypatch):
    """Capture the real outgoing requests; every call answers 200 {"result": "ok"}."""
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={'result': 'ok'})

    def client_factory(**kwargs: Any) -> httpx.AsyncClient:
        return _RealAsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    breaker = MagicMock()
    breaker.allow_request.return_value = True
    monkeypatch.setattr(app_tools.httpx, 'AsyncClient', client_factory)
    monkeypatch.setattr(app_tools, 'is_app_webhook_disabled', lambda app_id: False)
    monkeypatch.setattr(app_tools, 'get_cached_user_geolocation', lambda uid: None)
    monkeypatch.setattr(app_tools, 'get_webhook_circuit_breaker', lambda url: breaker)
    monkeypatch.setattr(app_tools, 'record_app_webhook_success', MagicMock())
    monkeypatch.setattr(app_tools, 'record_app_webhook_failure', MagicMock(return_value=0))
    monkeypatch.setattr(app_tools, 'active_app_signing_secrets', MagicMock(return_value=[CURRENT]))
    return sent


async def _call(tool, arguments):
    return await app_tools._call_tool_endpoint(dict(arguments), CONFIG, tool, APP_ID)


def _receiver_view(request: httpx.Request, *, path=None, query=None, method=None, body=None):
    """What a receiver passes to verify_request for this request (optionally tampered)."""
    raw_path, _, raw_query = request.url.raw_path.decode('ascii').partition('?')
    return {
        'headers': dict(request.headers),
        'body': request.content if body is None else body,
        'method': method or request.method,
        'path': raw_path if path is None else path,
        'query': raw_query if query is None else query,
    }


def _verifies(view, secret=CURRENT):
    return signing.verify_request(
        view['headers'], view['body'], secret, method=view['method'], path=view['path'], query=view['query']
    )


# --- what goes on the wire ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signed_post_sends_the_bytes_it_signed(wire):
    result = await _call(_tool('like_tweet'), {'tweet_id': '1850000000000000000'})
    assert result == 'ok'
    (request,) = wire
    payload = {'tweet_id': '1850000000000000000', 'uid': UID, 'app_id': APP_ID, 'tool_name': 'like_tweet'}
    # The same bytes an unsigned json= call sends, now signed.
    assert request.content == httpx.Request('POST', 'https://x', json=payload).content
    assert request.headers['X-Omi-Event'] == 'chat_tool'
    assert uuid.UUID(request.headers['X-Omi-Delivery'])
    assert request.headers['X-Omi-Signature'].startswith('t=')
    assert ',v2=' in request.headers['X-Omi-Signature'] and 'v1=' not in request.headers['X-Omi-Signature']
    assert _verifies(_receiver_view(request)) is True
    assert json.loads(request.content)['uid'] == UID


@pytest.mark.asyncio
async def test_signed_get_sends_the_canonical_query_with_todays_values(wire):
    arguments = {'query': 'café & tea+milk', 'tags': ['b', 'a'], 'limit': 5, 'exact': True}
    await _call(_tool('search_notes', method='GET'), arguments)
    (request,) = wire
    raw_path, _, raw_query = request.url.raw_path.decode('ascii').partition('?')
    assert raw_path == '/tools/search_notes'
    assert raw_query == (
        'app_id=01KAPP&exact=true&limit=5&query=caf%C3%A9%20%26%20tea%2Bmilk&tags=b&tags=a'
        '&tool_name=search_notes&uid=u1AbC'
    )
    assert request.content == b''
    # Decoded, the parameters are exactly what the unsigned params= call has always sent.
    payload = {**arguments, 'uid': UID, 'app_id': APP_ID, 'tool_name': 'search_notes'}
    assert sorted(parse_qsl(raw_query, keep_blank_values=True)) == sorted(httpx.QueryParams(payload).multi_items())
    assert _verifies(_receiver_view(request)) is True
    assert _verifies(_receiver_view(request, query=parse_qsl(raw_query, keep_blank_values=True))) is True


@pytest.mark.asyncio
async def test_signed_get_keeps_todays_string_form_for_nested_values(wire, monkeypatch):
    geolocation = {'latitude': 30.2672, 'longitude': -97.7431}
    monkeypatch.setattr(app_tools, 'get_cached_user_geolocation', lambda uid: geolocation)
    await _call(_tool('nearby', method='GET'), {})
    (request,) = wire
    decoded = dict(parse_qsl(request.url.query.decode('ascii'), keep_blank_values=True))
    assert decoded['geolocation'] == str(geolocation)
    assert _verifies(_receiver_view(request)) is True


@pytest.mark.asyncio
async def test_a_post_endpoints_own_query_goes_out_canonical_and_signed(wire):
    await _call(_tool('x', endpoint='https://tools.example.com/tools/x?b=2&a=1+1'), {})
    (request,) = wire
    assert request.url.query == b'a=1%201&b=2'
    assert _verifies(_receiver_view(request)) is True


@pytest.mark.asyncio
async def test_a_model_supplied_uid_is_still_overridden_and_signed(wire):
    await _call(_tool('like_tweet'), {'tweet_id': '1', 'uid': 'victim', 'app_id': 'other'})
    (request,) = wire
    sent = json.loads(request.content)
    assert (sent['uid'], sent['app_id']) == (UID, APP_ID)
    assert _verifies(_receiver_view(request)) is True


@pytest.mark.asyncio
async def test_a_delete_tool_is_signed_with_an_empty_body_and_still_carries_no_payload(wire):
    await _call(_tool('forget', method='DELETE'), {'note_id': 'n1'})
    (request,) = wire
    assert request.method == 'DELETE'
    assert request.content == b'' and request.url.query == b''
    assert 'X-Omi-Signature' in request.headers
    assert _verifies(_receiver_view(request)) is True


@pytest.mark.asyncio
async def test_rotation_signs_with_both_secrets(wire):
    app_tools.active_app_signing_secrets.return_value = [CURRENT, PREVIOUS]
    await _call(_tool('like_tweet'), {'tweet_id': '1'})
    (request,) = wire
    assert request.headers['X-Omi-Signature'].count('v2=') == 2
    assert _verifies(_receiver_view(request), CURRENT) is True
    assert _verifies(_receiver_view(request), PREVIOUS) is True


@pytest.mark.asyncio
async def test_every_call_gets_its_own_delivery_id(wire):
    await _call(_tool('like_tweet'), {'tweet_id': '1'})
    await _call(_tool('like_tweet'), {'tweet_id': '1'})
    assert wire[0].headers['X-Omi-Delivery'] != wire[1].headers['X-Omi-Delivery']


# --- what a captured call can no longer be turned into -----------------------------------------


@pytest.mark.asyncio
async def test_a_captured_get_replayed_with_altered_arguments_fails_verification(wire):
    await _call(_tool('search_notes', method='GET'), {'query': 'meeting', 'limit': 5})
    (request,) = wire
    view = _receiver_view(request)
    assert _verifies(view) is True
    for tampered in (
        view['query'].replace('limit=5', 'limit=500'),
        view['query'].replace('query=meeting', 'query=passwords'),
        view['query'].replace(f'uid={UID}', 'uid=victim'),
        view['query'] + '&uid=victim',
        view['query'] + '&delete_all=true',
    ):
        assert _verifies(_receiver_view(request, query=tampered)) is False, tampered


@pytest.mark.asyncio
async def test_a_captured_post_replayed_against_a_sibling_tool_fails_verification(wire):
    # like_tweet, unlike_tweet, retweet and delete_tweet all take the same {tweet_id} body.
    await _call(_tool('like_tweet'), {'tweet_id': '1850000000000000000'})
    (request,) = wire
    for sibling in ('/tools/unlike_tweet', '/tools/retweet', '/tools/delete_tweet'):
        assert _verifies(_receiver_view(request, path=sibling)) is False, sibling


@pytest.mark.asyncio
async def test_a_captured_post_with_a_changed_body_fails_verification(wire):
    await _call(_tool('like_tweet'), {'tweet_id': '1'})
    (request,) = wire
    tampered = request.content.replace(f'"uid":"{UID}"'.encode(), b'"uid":"victim"')
    assert tampered != request.content
    assert _verifies(_receiver_view(request, body=tampered)) is False


@pytest.mark.asyncio
async def test_get_and_post_cannot_be_swapped(wire):
    await _call(_tool('search_notes', method='GET'), {'query': 'meeting'})
    await _call(_tool('like_tweet'), {'tweet_id': '1'})
    get_request, post_request = wire
    get_view = _receiver_view(get_request)
    post_view = _receiver_view(post_request)
    # The GET's arguments moved into a POST body to the same URL.
    assert _verifies(_receiver_view(get_request, method='POST', query='', body=get_view['query'].encode())) is False
    # The POST's body moved into a GET query string.
    moved = httpx.QueryParams(json.loads(post_request.content)).multi_items()
    assert _verifies(_receiver_view(post_request, method='GET', query=moved, body=b'')) is False
    assert _verifies(_receiver_view(post_request, method='PUT')) is False
    assert _verifies(get_view) is True and _verifies(post_view) is True


@pytest.mark.asyncio
async def test_v1_and_v2_are_never_accepted_for_each_other(wire):
    await _call(_tool('like_tweet'), {'tweet_id': '1'})
    (request,) = wire
    view = _receiver_view(request)
    # A webhook (v1) verifier finds no v1 signature on a tool call.
    assert signing.verify(view['headers'], view['body'], CURRENT, uid=UID) is False
    # A v1 signature over the same body, as a captured webhook would carry, does not pass v2.
    t = signing.parse_signature_header(view['headers']['x-omi-signature'])[0]
    assert t is not None
    v1_headers = {
        **view['headers'],
        'x-omi-signature': f't={t},v1={signing.compute_signature(CURRENT, t, UID, view["body"])}',
    }
    assert _verifies({**view, 'headers': v1_headers}) is False


# --- unsigned apps and store failures ----------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize('method', ['POST', 'GET', 'DELETE'])
async def test_an_app_without_a_secret_gets_exactly_the_old_request(wire, method):
    app_tools.active_app_signing_secrets.return_value = []
    await _call(_tool('search', method=method), {'query': 'a b', 'tags': ['x', 'y']})
    (request,) = wire
    payload = {'query': 'a b', 'tags': ['x', 'y'], 'uid': UID, 'app_id': APP_ID, 'tool_name': 'search'}
    body_kwargs: dict[str, Any] = {'POST': {'json': payload}, 'GET': {'params': payload}, 'DELETE': {}}[method]
    old = httpx.Request(
        method, 'https://tools.example.com/tools/search', headers={'Content-Type': 'application/json'}, **body_kwargs
    )
    assert request.url.raw_path == old.url.raw_path
    assert request.content == old.content
    assert not {'x-omi-signature', 'x-omi-event', 'x-omi-delivery'} & set(request.headers.keys())


@pytest.mark.asyncio
async def test_a_signing_store_failure_sends_unsigned_and_reports_once(wire, monkeypatch):
    monkeypatch.setattr(app_tools, 'active_app_signing_secrets', store.active_app_signing_secrets)
    monkeypatch.setattr(store, 'get_app_webhook_signing_db', MagicMock(side_effect=RuntimeError('firestore down')))
    note = MagicMock()
    monkeypatch.setattr(store, 'note_unsigned_delivery', note)
    assert await _call(_tool('like_tweet'), {'tweet_id': '1'}) == 'ok'
    (request,) = wire
    assert 'x-omi-signature' not in request.headers
    note.assert_called_once_with('other', APP_ID)


def test_the_shared_loader_returns_the_active_secrets_current_first(monkeypatch):
    rotated = WebhookSigningSecrets.issue(CURRENT, previous=WebhookSigningSecrets.issue(PREVIOUS))
    monkeypatch.setattr(store, 'get_app_webhook_signing_db', MagicMock(side_effect=[rotated, None]))
    assert store.active_app_signing_secrets(APP_ID) == [CURRENT, PREVIOUS]
    assert store.active_app_signing_secrets(APP_ID) == []


@pytest.mark.asyncio
async def test_an_unencodable_argument_sends_nothing_and_reports_an_error(wire):
    result = await _call(_tool('search', method='GET'), {'query': '\ud800'})
    assert wire == []
    assert result.startswith('Error calling search')


# --- the documented receiver recipe, end to end -------------------------------------------------


def _receiver_app() -> FastAPI:
    app = FastAPI()

    async def omi_tool_call(request: Request) -> dict:
        body = await request.body()
        if not signing.verify_request(
            request.headers,
            body,
            CURRENT,
            method=request.method,
            path=request.url.path,
            query=request.query_params.multi_items(),
        ):
            raise HTTPException(status_code=401, detail='Invalid Omi signature')
        return json.loads(body) if body else dict(request.query_params)

    @app.api_route('/tools/{name}', methods=['GET', 'POST'])
    async def tool(name: str, call: dict = Depends(omi_tool_call)):
        return {'uid': call['uid'], 'tool': name}

    return app


def _replay(client: TestClient, request: httpx.Request, *, target=None, content=None):
    return client.request(
        request.method,
        target or request.url.raw_path.decode('ascii'),
        headers={key: value for key, value in request.headers.items() if key.lower() != 'host'},
        content=request.content if content is None else content,
    )


@pytest.mark.asyncio
async def test_the_documented_fastapi_receiver_accepts_omis_calls_and_rejects_tampering(wire):
    await _call(_tool('search_notes', method='GET'), {'query': 'café & tea+milk', 'tags': ['b', 'a']})
    await _call(_tool('like_tweet'), {'tweet_id': '1'})
    get_request, post_request = wire
    client = TestClient(_receiver_app(), base_url='https://tools.example.com')

    assert _replay(client, get_request).json() == {'uid': UID, 'tool': 'search_notes'}
    assert _replay(client, post_request).json() == {'uid': UID, 'tool': 'like_tweet'}

    tampered_get = get_request.url.raw_path.decode('ascii').replace('tags=b&tags=a', 'tags=a&tags=b')
    assert _replay(client, get_request, target=tampered_get).status_code == 401
    assert _replay(client, post_request, target='/tools/unlike_tweet').status_code == 401
    assert _replay(client, post_request, content=post_request.content.replace(b'"1"', b'"2"')).status_code == 401
