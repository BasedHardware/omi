"""Execute the pre-extraction route and shared service against identical dependencies."""

import asyncio
import ast
from datetime import datetime, timezone
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from tests.unit.test_chat_quota_counting_router import _make_chat_client, _cleanup


@pytest.fixture
def environment():
    client, router, saved = _make_chat_client()
    service = sys.modules['utils.chat_turn']
    source = Path(__file__).parents[1] / 'fixtures/messaging/mobile_turn_before.py.txt'
    namespace = dict(vars(service))
    namespace["_safe_file_chats"] = service.safe_file_chats
    exec(compile(ast.parse(source.read_text()), str(source), 'exec'), namespace)
    yield router, service, namespace['send_message'], namespace
    _cleanup(saved)


@pytest.mark.parametrize('scenario', ['success', 'quota', 'accounting', 'typed_error', 'malformed_history', 'files'])
@pytest.mark.parametrize('typed', [False, True])
def test_mobile_stored_documents_stream_bytes_and_prompt_inputs_match(environment, scenario, typed):
    router, service, old_send, namespace = environment
    now = datetime(2026, 10, 10, tzinfo=timezone.utc)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    headers = {'X-Omi-Chat-Failure-Protocol': '1'} if typed else {}
    request = SimpleNamespace(headers=headers)
    captures = []

    async def provider(*args, **kwargs):
        captures.append((args, {k: v for k, v in kwargs.items() if k != 'callback_data'}))
        if scenario == 'typed_error':
            kwargs['callback_data'].update(error='timeout', answer='Try again')
            yield 'error: timed out'
        else:
            kwargs['callback_data']['answer'] = 'answer\nwith bytes'
            yield 'data: answer\nwith bytes'
        yield None

    namespace['execute_chat_stream'] = provider
    namespace['datetime'] = FrozenDatetime
    service.execute_chat_stream = provider
    service.datetime = FrozenDatetime
    docs = []
    service.chat_db.add_message.side_effect = lambda uid, data: docs.append(data.copy()) or data
    session = {'id': 's', 'created_at': now, 'message_ids': [], 'file_ids': [], 'app_id': None}
    service.chat_db.get_chat_session_by_id.return_value = session
    service.chat_db.get_chat_session.return_value = session
    service.chat_db.get_chat_files.return_value = []
    service.chat_db.get_cache_aligned_messages.return_value = (
        [{'broken': True}] if scenario == 'malformed_history' else []
    )
    if scenario == 'quota':
        service.enforce_chat_quota.side_effect = HTTPException(402, {'error': 'quota_exceeded', 'plan': 'Free'})
    if scenario == 'accounting':
        service.llm_usage_db.record_chat_quota_question.side_effect = RuntimeError('unavailable')
    data = service.SendMessageRequest(text='hello', file_ids=['f'] if scenario == 'files' else [], device_tools=[])

    async def collect(response):
        return ''.join([chunk async for chunk in response.body_iterator])

    outcomes = []
    for send in (old_send, router.send_message):
        docs.clear()
        captures.clear()
        with patch.object(service.uuid, 'uuid4', side_effect=['human', 'assistant']):
            response = send(data, request, uid='test-uid', chat_session_id='s', x_app_platform='ios')
            wire = asyncio.run(collect(response))
        outcomes.append((wire, list(docs), list(captures)))
    assert outcomes[0] == outcomes[1]
