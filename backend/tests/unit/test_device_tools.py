"""Contract tests for the client-executed device tool bridge."""

import asyncio
import json
from unittest.mock import patch

import pytest

from utils import device_tools
from utils.device_tools import (
    DEVICE_TOOL_NAMES,
    build_device_tools,
    device_tool_result_key,
)


class FakeCallback:
    """Captures the frames the bridge would put on the chat stream."""

    def __init__(self):
        self.requests = []

    async def put_device_tool_request(self, request):
        self.requests.append(request)


class FakeRedis:
    def __init__(self):
        self.store = {}

    def setex(self, key, _ttl, value):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        self.store.pop(key, None)


@pytest.fixture
def fake_redis():
    fake = FakeRedis()
    with patch.object(device_tools, 'redis_client', fake):
        yield fake


async def _run_blocking_inline(_executor, fn, *args):
    """Run the bridge's blocking Redis hops inline, without a thread pool."""
    return fn(*args)


@pytest.fixture(autouse=True)
def inline_executor():
    with patch.object(device_tools, 'run_blocking', _run_blocking_inline):
        yield


def test_only_declared_tools_are_built():
    callback = FakeCallback()

    tools = build_device_tools('uid-1', {'propose_message'}, callback)

    assert [t.name for t in tools] == ['propose_message']


def test_a_client_declaring_nothing_gets_no_tools():
    # An Android build or a device with no messaging service must not have the
    # model offered a capability it cannot run.
    assert build_device_tools('uid-1', set(), FakeCallback()) == []


def test_unknown_declared_names_are_ignored():
    tools = build_device_tools('uid-1', {'run_applescript', 'rm_rf'}, FakeCallback())

    assert tools == []


def test_every_spec_name_is_buildable():
    tools = build_device_tools('uid-1', set(DEVICE_TOOL_NAMES), FakeCallback())

    assert {t.name for t in tools} == set(DEVICE_TOOL_NAMES)
    for tool in tools:
        assert tool.description
        assert tool.args_schema is not None


def test_propose_message_description_states_it_does_not_send():
    tools = build_device_tools('uid-1', {'propose_message'}, FakeCallback())

    description = tools[0].description
    assert 'does NOT send' in description
    assert 'cancelled' in description


@pytest.mark.asyncio
async def test_call_announces_a_request_and_returns_the_client_result(fake_redis):
    callback = FakeCallback()
    tool = build_device_tools('uid-1', {'propose_message'}, callback)[0]

    async def respond_once():
        # Wait for the bridge to announce the call, then answer it the way the
        # client's POST handler would.
        while not callback.requests:
            await asyncio.sleep(0.01)
        call_id = callback.requests[0]['call_id']
        fake_redis.setex(
            device_tool_result_key('uid-1', call_id),
            60,
            json.dumps({'ok': True, 'status': 'sent'}),
        )

    responder = asyncio.create_task(respond_once())
    raw = await tool.ainvoke({'to': ['+15550100'], 'text': 'running late'})
    await responder

    assert json.loads(raw) == {'ok': True, 'status': 'sent'}
    request = callback.requests[0]
    assert request['tool'] == 'propose_message'
    assert request['arguments']['to'] == ['+15550100']
    assert request['arguments']['text'] == 'running late'
    assert request['call_id']


@pytest.mark.asyncio
async def test_a_cancelled_sheet_is_returned_verbatim(fake_redis):
    # The model must be able to tell "user declined" from "delivered"; the
    # bridge may not normalize a cancellation into a generic failure.
    callback = FakeCallback()
    tool = build_device_tools('uid-1', {'propose_message'}, callback)[0]

    async def respond_once():
        while not callback.requests:
            await asyncio.sleep(0.01)
        fake_redis.setex(
            device_tool_result_key('uid-1', callback.requests[0]['call_id']),
            60,
            json.dumps({'ok': False, 'status': 'cancelled'}),
        )

    responder = asyncio.create_task(respond_once())
    raw = await tool.ainvoke({'to': ['+15550100'], 'text': 'hi'})
    await responder

    assert json.loads(raw) == {'ok': False, 'status': 'cancelled'}


@pytest.mark.asyncio
async def test_the_result_is_consumed_so_a_later_call_cannot_reuse_it(fake_redis):
    callback = FakeCallback()
    tool = build_device_tools('uid-1', {'search_contacts'}, callback)[0]

    async def respond_once():
        while not callback.requests:
            await asyncio.sleep(0.01)
        fake_redis.setex(
            device_tool_result_key('uid-1', callback.requests[0]['call_id']),
            60,
            json.dumps({'ok': True, 'contacts': []}),
        )

    responder = asyncio.create_task(respond_once())
    await tool.ainvoke({'query': 'Ada'})
    await responder

    assert fake_redis.store == {}


@pytest.mark.asyncio
async def test_an_unanswered_call_times_out_instead_of_hanging(fake_redis):
    callback = FakeCallback()
    tool = build_device_tools('uid-1', {'propose_message'}, callback, timeout_seconds=0)[0]

    raw = await tool.ainvoke({'to': ['+15550100'], 'text': 'hi'})

    result = json.loads(raw)
    assert result['ok'] is False
    assert result['reason'] == 'timed_out'
    # The model must not silently retry a message the user may still be looking at.
    assert 'Do not retry automatically' in result['error']


@pytest.mark.asyncio
async def test_one_user_cannot_answer_another_users_call(fake_redis):
    callback = FakeCallback()
    tool = build_device_tools('uid-1', {'propose_message'}, callback, timeout_seconds=0)[0]

    # A result written under a different uid must not satisfy uid-1's call.
    fake_redis.setex(device_tool_result_key('uid-2', 'any'), 60, json.dumps({'ok': True}))
    raw = await tool.ainvoke({'to': ['+15550100'], 'text': 'hi'})

    assert json.loads(raw)['reason'] == 'timed_out'


@pytest.mark.asyncio
async def test_an_unparseable_stored_result_times_out_rather_than_crashing(fake_redis):
    callback = FakeCallback()
    tool = build_device_tools('uid-1', {'propose_message'}, callback, timeout_seconds=0)[0]
    fake_redis.setex(device_tool_result_key('uid-1', 'x'), 60, 'not json')

    raw = await tool.ainvoke({'to': ['+15550100'], 'text': 'hi'})

    assert json.loads(raw)['reason'] == 'timed_out'


def test_device_tool_names_are_excluded_from_app_tool_detection():
    # Device tools are named like core tools (propose_message). Without this
    # exclusion _extract_app_id reads "propose" as an app id and routes the call
    # to a non-existent app.
    from utils.retrieval.agentic import STANDARD_TOOL_NAMES, _extract_app_id

    for name in DEVICE_TOOL_NAMES:
        assert name in STANDARD_TOOL_NAMES
        assert _extract_app_id(name) is None
