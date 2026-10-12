"""The released in-app final message owns citation cards, not raw markers."""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from tests.unit import _chat_router_test_harness as harness

import pytest

from tests.unit.test_chat_stream_error_fallback import (
    _cleanup,
    _collect_voice_frames,
    _decode_done_frame,
    _make_client,
)


@pytest.fixture
def environment():
    client, router, chat, chat_db, saved = _make_client()
    try:
        helpers = harness.load_real_module(
            'utils.conversation_helpers', harness.BACKEND_DIR / 'utils/conversation_helpers.py'
        )
        service = sys.modules['utils.chat_turn']
        chat.extract_memory_ids = service.extract_memory_ids = helpers.extract_memory_ids
        yield client, chat, chat_db, service
    finally:
        _cleanup(saved)


def _conversations():
    return [
        {
            'id': f'conversation-{index}',
            'created_at': '2026-10-12T00:00:00Z',
            'structured': {'title': f'Conversation {index}', 'emoji': '📝'},
        }
        for index in range(1, 9)
    ]


def test_app_sse_bytes_preserve_the_pre_channel_citation_contract(environment, monkeypatch):
    client, _chat, _chat_db, service = environment
    historical_source = os.environ.get('OMI_CITATION_HISTORICAL_SOURCE')
    if historical_source:
        service = harness.load_real_module('utils.chat_turn_historical', Path(historical_source))
        service.extract_memory_ids = sys.modules['utils.chat_turn'].extract_memory_ids
        router = sys.modules['routers.chat']
        monkeypatch.setattr(router, 'run_chat_turn', service.run_chat_turn)
        monkeypatch.setattr(router, 'TurnOptions', service.TurnOptions)
        monkeypatch.setattr(router, 'MobileReplySink', service.MobileReplySink)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 12, 7, 58, 37, tzinfo=timezone.utc)

    identifiers = iter(['fixture-human', 'fixture-ai'])
    monkeypatch.setattr(service, 'datetime', FixedDateTime)
    monkeypatch.setattr(service, 'uuid', SimpleNamespace(uuid4=lambda: next(identifiers)))

    async def stream(*args, **kwargs):
        kwargs['callback_data'].update(
            answer='I can name them.[1][2][4][6][7]',
            memories_found=_conversations(),
            prompt_name='fixture-prompt',
            prompt_commit='fixture-commit',
            langsmith_run_id='fixture-run',
            action_receipts=[],
            channel_items=[],
        )
        # Include a split marker and a thinking frame, exactly as token streaming permits.
        yield 'think: Searching conversations'
        yield 'data: I can name them.[1][2][4]['
        yield 'data: 6][7]'
        yield None

    monkeypatch.setattr(service, 'execute_chat_stream', stream)
    response = client.post('/v2/messages', json={'text': 'Who did I meet?'}, headers={'User-Agent': ''})
    assert response.status_code == 200
    fixture = harness.BACKEND_DIR / 'tests/fixtures/chat_app_citations_pre_21240.sse.json'
    capture = os.environ.get('OMI_CITATION_CAPTURE_PATH')
    if capture:
        Path(capture).write_bytes(response.content)
    assert response.content == json.loads(fixture.read_text()).encode('utf-8')
    payload = _decode_done_frame(response.text)
    assert payload['text'] == 'I can name them.'
    assert payload['memories_id'] == [f'conversation-{index}' for index in [1, 2, 4, 6, 7]]
    assert [card['id'] for card in payload['memories']] == payload['memories_id']
    assert payload['content_blocks'] == []
    assert payload['evidence'] is None


@pytest.mark.parametrize('platform', ['ios', 'android', 'macos'])
@pytest.mark.parametrize('markers', ['[8][7][6]', '[5][4]', '[1][2][4][6][7]'])
def test_app_done_frame_replaces_streamed_markers_with_conversation_cards(environment, platform, markers):
    client, _chat, chat_db, service = environment

    async def stream(*args, **kwargs):
        kwargs['callback_data'].update(answer='The answer.' + markers, memories_found=_conversations())
        yield 'data: The answer.' + markers
        yield None

    service.execute_chat_stream = stream
    response = client.post('/v2/messages', json={'text': 'Recall the discussion'}, headers={'X-App-Platform': platform})
    payload = _decode_done_frame(response.text)
    assert payload['text'] == 'The answer.'
    expected = {f'conversation-{index}' for index in range(1, 9) if f'[{index}]' in markers}
    assert {memory['id'] for memory in payload['memories']} == expected
    ai = [call.args[1] for call in chat_db.add_message.call_args_list if call.args[1]['sender'] == 'ai'][0]
    assert ai['text'] == payload['text']
    assert set(ai['memories_id']) == expected


def test_voice_done_frame_uses_the_same_citation_contract(environment):
    _client, chat, chat_db, service = environment

    async def stream(*args, **kwargs):
        kwargs['callback_data'].update(answer='The answer.[8][7][6]', memories_found=_conversations())
        yield 'data: The answer.[8][7][6]'
        yield None

    chat.execute_graph_chat_stream = stream
    payload = _decode_done_frame(''.join(_collect_voice_frames(chat)))
    assert payload['text'] == 'The answer.'
    assert {memory['id'] for memory in payload['memories']} == {'conversation-6', 'conversation-7', 'conversation-8'}


@pytest.mark.parametrize('surface', ['telegram', 'imessage'])
def test_channel_done_frame_strips_markers_and_retains_item_links(environment, surface):
    from utils.messaging.contracts import Principal
    from utils.messaging.projection import SurfaceRuntime, surface_runtime

    _client, _chat, chat_db, service = environment
    principal = Principal('test-uid')
    session = {
        'id': 'channel-session',
        'surface': surface,
        'created_at': '2026-10-12T00:00:00Z',
        'message_ids': [],
        'file_ids': [],
    }
    chat_db.get_chat_session_by_id.return_value = session
    writes = []
    runtime = SurfaceRuntime(
        surface, '', principal, session_id=session['id'], persist=lambda uid, doc, sid: writes.append(doc)
    )

    async def stream(*args, **kwargs):
        kwargs['callback_data'].update(answer='The answer.[8][7][6]', memories_found=_conversations())
        yield None

    service.execute_chat_stream = stream
    token = surface_runtime.set(runtime)
    try:
        response = service.run_chat_turn(
            'test-uid',
            surface,
            session['id'],
            service.SendMessageRequest(text='Recall', file_ids=None),
            service.MobileReplySink(),
            principal=principal,
        )

        async def collect():
            return ''.join([frame async for frame in response.body_iterator])

        payload = _decode_done_frame(asyncio.run(collect()))
    finally:
        surface_runtime.reset(token)
    assert payload['text'] == 'The answer.'
    assert [block['id'] for block in payload['content_blocks'] if block['type'] == 'itemLink'] == [
        'conversation-8',
        'conversation-7',
        'conversation-6',
    ]
    assert writes[-1]['text'] == payload['text']


@pytest.mark.parametrize('marker', ['[2]', '[#2]', '[2, 1]', '【2】', '[^2]'])
def test_marker_variants_map_to_owned_sources(environment, marker):
    from utils.chat_citations import resolve_conversation_citations

    text, sources = resolve_conversation_citations('Answer' + marker, _conversations())
    assert text == 'Answer'
    assert sources[0]['id'] == 'conversation-2'


def test_unknown_indices_do_not_invent_sources_and_markdown_links_remain_links(environment):
    from utils.chat_citations import resolve_conversation_citations

    text, sources = resolve_conversation_citations('Answer[99][0] [2](https://example.com)', _conversations())
    assert text == 'Answer [2](https://example.com)'
    assert sources == []
