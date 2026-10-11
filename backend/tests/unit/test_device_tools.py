"""Contract tests for the client-executed device tool bridge."""

import asyncio
import json
from unittest.mock import patch

import pytest

from utils import device_tools
from utils.device_tools import (
    DEVICE_TOOL_NAMES,
    DEVICE_TOOL_MIN_TIMEOUT_SECONDS,
    DEVICE_TOOL_STREAM_HEADROOM_SECONDS,
    MAX_DEVICE_TOOL_RESULT_BYTES,
    UnknownDeviceToolCall,
    build_device_tools,
    device_tool_inflight_key,
    device_tool_result_key,
    device_tool_timeout_for_stream_budget,
    mark_device_tool_inflight,
    store_device_tool_result,
)
from utils.retrieval.agentic import STANDARD_TOOL_NAMES, _extract_app_id

# Long enough that nothing in these tests reaches it; the tests that exercise the
# timeout path pass timeout_seconds=0 explicitly.
TEST_TIMEOUT = 180


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
        # Redis reports how many keys it removed, and the in-flight claim relies
        # on that count to be atomic.
        return 1 if self.store.pop(key, None) is not None else 0

    def eval(self, _script, _numkeys, marker_key, result_key, _ttl, value):
        if marker_key not in self.store:
            return 0
        self.store[result_key] = value
        self.store.pop(marker_key)
        return 1


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

    tools = build_device_tools('uid-1', {'propose_message'}, callback, timeout_seconds=TEST_TIMEOUT)

    assert [t.name for t in tools] == ['propose_message']


def test_a_client_declaring_nothing_gets_no_tools():
    # An Android build or a device with no messaging service must not have the
    # model offered a capability it cannot run.
    assert build_device_tools('uid-1', set(), FakeCallback(), timeout_seconds=TEST_TIMEOUT) == []


def test_unknown_declared_names_are_ignored():
    tools = build_device_tools('uid-1', {'run_applescript', 'rm_rf'}, FakeCallback(), timeout_seconds=TEST_TIMEOUT)

    assert tools == []


def test_every_spec_name_is_buildable():
    tools = build_device_tools('uid-1', set(DEVICE_TOOL_NAMES), FakeCallback(), timeout_seconds=TEST_TIMEOUT)

    assert {t.name for t in tools} == set(DEVICE_TOOL_NAMES)
    for tool in tools:
        assert tool.description
        assert tool.args_schema is not None


def test_propose_message_description_states_it_does_not_send():
    tools = build_device_tools('uid-1', {'propose_message'}, FakeCallback(), timeout_seconds=TEST_TIMEOUT)

    description = tools[0].description
    assert 'does NOT send' in description
    assert 'cancelled' in description


@pytest.mark.asyncio
async def test_call_announces_a_request_and_returns_the_client_result(fake_redis):
    callback = FakeCallback()
    tool = build_device_tools('uid-1', {'propose_message'}, callback, timeout_seconds=TEST_TIMEOUT)[0]

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
async def test_device_tool_timeout_provider_is_evaluated_at_wait_start(fake_redis):
    callback = FakeCallback()
    observed = []

    async def capture_wait(_uid, _call_id, timeout_seconds):
        observed.append(timeout_seconds)
        return {'ok': True, 'status': 'sent'}

    with patch.object(device_tools, '_await_device_tool_result', capture_wait):
        tool = build_device_tools('uid-1', {'propose_message'}, callback, timeout_seconds=lambda: 17)[0]
        raw = await tool.ainvoke({'to': ['+15550100'], 'text': 'hi'})

    assert observed == [17]
    assert json.loads(raw) == {'ok': True, 'status': 'sent'}


@pytest.mark.asyncio
async def test_a_cancelled_sheet_is_returned_verbatim(fake_redis):
    # The model must be able to tell "user declined" from "delivered"; the
    # bridge may not normalize a cancellation into a generic failure.
    callback = FakeCallback()
    tool = build_device_tools('uid-1', {'propose_message'}, callback, timeout_seconds=TEST_TIMEOUT)[0]

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
    tool = build_device_tools('uid-1', {'search_contacts'}, callback, timeout_seconds=TEST_TIMEOUT)[0]

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
    for name in DEVICE_TOOL_NAMES:
        assert name in STANDARD_TOOL_NAMES
        assert _extract_app_id(name) is None


def test_the_tool_gives_up_before_the_turn_does():
    # The wait shipped at 180s against a 150s stream cap, so the stream cancelled
    # the producer first: the model never saw a timed_out result, the turn died
    # with idle_timeout, and the user could still send the message afterwards.
    from utils.retrieval.agentic import AGENT_STREAM_MAX_DURATION_SECONDS

    timeout = device_tool_timeout_for_stream_budget(AGENT_STREAM_MAX_DURATION_SECONDS)
    assert timeout < AGENT_STREAM_MAX_DURATION_SECONDS


def test_the_wait_leaves_room_to_report_what_happened():
    # Reaching the timeout is not enough on its own; the model still has to say
    # the user did not respond, which needs budget left after the tool returns.
    budget = 150
    assert device_tool_timeout_for_stream_budget(budget) == budget - DEVICE_TOOL_STREAM_HEADROOM_SECONDS


def test_a_budget_too_small_for_a_sheet_does_not_produce_a_negative_wait():
    # A misconfigured deployment should not turn every device tool call into an
    # instant timeout with a negative deadline.
    assert device_tool_timeout_for_stream_budget(5) == DEVICE_TOOL_MIN_TIMEOUT_SECONDS


def test_a_result_for_a_call_that_was_never_made_is_refused(fake_redis):
    # Without this the endpoint is a write primitive: any authenticated caller
    # could invent call ids and park a value in shared Redis for each one.
    with pytest.raises(UnknownDeviceToolCall):
        store_device_tool_result('uid-1', 'never-dispatched', {'ok': True})

    assert fake_redis.store == {}


def test_an_oversized_result_is_refused_before_anything_is_written(fake_redis):
    mark_device_tool_inflight('uid-1', 'call-1')

    with pytest.raises(ValueError):
        store_device_tool_result('uid-1', 'call-1', {'blob': 'x' * (MAX_DEVICE_TOOL_RESULT_BYTES + 1)})

    assert device_tool_result_key('uid-1', 'call-1') not in fake_redis.store
    # The call is still in flight: an oversized submission must not consume the
    # marker and lock the real client out of answering.
    assert device_tool_inflight_key('uid-1', 'call-1') in fake_redis.store


def test_only_the_first_submission_for_a_call_is_accepted(fake_redis):
    mark_device_tool_inflight('uid-1', 'call-1')

    store_device_tool_result('uid-1', 'call-1', {'ok': True, 'status': 'sent'})
    with pytest.raises(UnknownDeviceToolCall):
        store_device_tool_result('uid-1', 'call-1', {'ok': True, 'status': 'sent'})


def test_one_user_cannot_answer_a_call_dispatched_for_another(fake_redis):
    mark_device_tool_inflight('uid-1', 'call-1')

    with pytest.raises(UnknownDeviceToolCall):
        store_device_tool_result('uid-2', 'call-1', {'ok': True})


@pytest.mark.asyncio
async def test_a_redis_outage_mid_wait_does_not_become_a_retriable_error(fake_redis):
    # The compose sheet may already be open, so a failed poll says nothing about
    # whether the user sent the message. Surfacing a generic execution error
    # would leave the model free to retry and send it twice.
    callback = FakeCallback()
    tool = build_device_tools('uid-1', {'propose_message'}, callback, timeout_seconds=1)[0]

    calls = {'n': 0}
    real_get = fake_redis.get

    def flaky_get(key):
        calls['n'] += 1
        if calls['n'] <= 2:
            raise ConnectionError('redis is down')
        return real_get(key)

    fake_redis.get = flaky_get

    async def respond_once():
        while not callback.requests:
            await asyncio.sleep(0.01)
        fake_redis.setex(
            device_tool_result_key('uid-1', callback.requests[0]['call_id']),
            60,
            json.dumps({'ok': True, 'status': 'sent'}),
        )

    responder = asyncio.create_task(respond_once())
    raw = await tool.ainvoke({'to': ['+15550100'], 'text': 'hi'})
    await responder

    # The wait survived the outage and still delivered the real answer.
    assert json.loads(raw) == {'ok': True, 'status': 'sent'}


@pytest.mark.asyncio
async def test_a_late_result_is_refused_once_the_wait_is_over(fake_redis):
    callback = FakeCallback()
    tool = build_device_tools('uid-1', {'propose_message'}, callback, timeout_seconds=0)[0]

    raw = await tool.ainvoke({'to': ['+15550100'], 'text': 'hi'})
    assert json.loads(raw)['reason'] == 'timed_out'

    call_id = callback.requests[0]['call_id']
    with pytest.raises(UnknownDeviceToolCall):
        store_device_tool_result('uid-1', call_id, {'ok': True, 'status': 'sent'})
