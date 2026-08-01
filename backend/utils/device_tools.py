"""Client-executed device tools.

Some capabilities only exist on the user's own device. iOS can present a message
compose sheet but has no API for sending silently, and only the phone can read
its own Contacts store. Those tools cannot run on the server, so the model calls
them like any other tool and the backend round-trips the call to the client that
opened this chat stream.

Transport, deliberately reusing what already exists:

1. The tool coroutine announces the call on the SSE stream that is *already open*
   for this turn, as a ``tool:`` frame. No suspend/resume of the streaming
   generator is required — the turn simply stays open while the user decides.
2. The client executes it locally and POSTs the result to
   ``/v2/messages/device-tool/{call_id}/result``.
3. That handler writes the result to Redis; the awaiting coroutine polls for it.

Polling rather than pub/sub is what makes this correct under multiple workers:
the POST may land on a different worker than the one holding the awaiting
coroutine, and a poll on a shared key does not care which worker wrote it. The
latency floor is a human tapping a compose sheet, so a 250ms poll is far below
the noise.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from database.redis_db import r as redis_client
from utils.executors import db_executor, run_blocking
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

# A device tool call is bounded by how long a person plausibly takes to answer a
# system sheet. Beyond this the model gets a timeout result and can respond
# without it, rather than the whole turn hanging on an unanswered prompt.
#
# That bound only means anything if it is reached before the turn's own deadline.
# The agent stream cancels the producer at a hard wall clock, so a tool that
# waits past it never returns a timeout result at all: the stream dies with
# `idle_timeout` while the user is still looking at the sheet, and they can go on
# to send the message afterwards — exactly the ambiguous outcome this surface
# exists to avoid. The wait is therefore derived from the stream budget rather
# than written down beside it, so the two cannot drift apart.
DEVICE_TOOL_POLL_INTERVAL_SECONDS = 0.25

# Reserved out of the stream budget: the model still has to reason and dispatch
# the call before the wait starts, and still has to say something about the
# result after it ends. A tool that consumed the whole budget would leave no room
# for the sentence explaining what happened.
DEVICE_TOOL_STREAM_HEADROOM_SECONDS = 30

# Below this a sheet cannot realistically be answered, so a budget that tight
# means the deployment has no room for device tools rather than a shorter wait.
DEVICE_TOOL_MIN_TIMEOUT_SECONDS = 15


def device_tool_timeout_for_stream_budget(stream_budget_seconds: float) -> int:
    """The longest wait that still lets the tool time out before the turn does."""
    return max(
        DEVICE_TOOL_MIN_TIMEOUT_SECONDS,
        int(stream_budget_seconds - DEVICE_TOOL_STREAM_HEADROOM_SECONDS),
    )


# Results outlive the poll window slightly so a result that arrives just as the
# tool gives up is still readable for diagnostics rather than vanishing. The
# write side has no view of the turn's budget, so this is sized against the
# longest wait any budget can produce.
DEVICE_TOOL_RESULT_TTL_SECONDS = 600


class ProposeMessageInput(BaseModel):
    to: list[str] = Field(description="Recipient phone numbers or email addresses.")
    text: str = Field(description="Exact message body to prefill.")
    subject: Optional[str] = Field(default=None, description="Optional subject, when the device supports it.")


class SearchContactsInput(BaseModel):
    query: str = Field(description="Name or partial name to search for.")
    limit: Optional[int] = Field(default=10, description="Maximum contacts to return (max 50).")


# Descriptions are written for the model and must state the consent model, so it
# does not promise the user a message was sent when it only opened a sheet.
DEVICE_TOOL_SPECS: dict[str, dict[str, Any]] = {
    'propose_message': {
        'args_schema': ProposeMessageInput,
        'description': (
            "Open the system message composer on the user's phone, prefilled with a recipient "
            "and body. This does NOT send on its own: iOS requires the user to tap Send. The "
            "result reports status=sent when they sent it, or status=cancelled when they "
            "dismissed the sheet. Never tell the user a message was sent unless the result says "
            "sent. Resolve a named person with search_contacts first."
        ),
    },
    'search_contacts': {
        'args_schema': SearchContactsInput,
        'description': (
            "Resolve a person's name to their phone numbers and email addresses from the "
            "contacts on the user's own device. Use before propose_message when the user names "
            "a person instead of giving a raw handle. Ask which one when several match."
        ),
    },
}

DEVICE_TOOL_NAMES = frozenset(DEVICE_TOOL_SPECS)


def device_tool_result_key(uid: str, call_id: str) -> str:
    return f'device_tool_result:{uid}:{call_id}'


def device_tool_inflight_key(uid: str, call_id: str) -> str:
    return f'device_tool_inflight:{uid}:{call_id}'


# A device tool result is a small status object: ok, a reason, a handful of
# contacts. Anything larger is not a result this surface produces.
MAX_DEVICE_TOOL_RESULT_BYTES = 64 * 1024


class UnknownDeviceToolCall(Exception):
    """Raised when a result arrives for a call that is not in flight."""


def mark_device_tool_inflight(uid: str, call_id: str) -> None:
    """Record that this uid is genuinely waiting on this call.

    Without a marker the result endpoint is a write primitive: any authenticated
    caller could invent call ids and park a value in shared Redis for each one.
    The marker is what makes an accepted write mean "you were asked for this".
    """
    redis_client.setex(device_tool_inflight_key(uid, call_id), DEVICE_TOOL_RESULT_TTL_SECONDS, '1')


def claim_device_tool_inflight(uid: str, call_id: str) -> bool:
    """Consume the in-flight marker, returning whether this call was expected.

    DELETE reports how many keys it removed, so the check and the consume are one
    atomic operation: two racing submissions cannot both be accepted.
    """
    return bool(redis_client.delete(device_tool_inflight_key(uid, call_id)))


def clear_device_tool_inflight(uid: str, call_id: str) -> None:
    try:
        redis_client.delete(device_tool_inflight_key(uid, call_id))
    except Exception as error:
        # The marker expires on its own; a cleanup failure is not worth failing
        # a tool call the user already answered.
        logger.warning('Could not clear device tool marker error_type=%s', type(error).__name__)


def store_device_tool_result(uid: str, call_id: str, payload: dict) -> None:
    """Record a client's result for an in-flight device tool call.

    Raises ``UnknownDeviceToolCall`` when nothing was waiting for this call id,
    and ``ValueError`` when the payload is larger than a result can legitimately
    be — both before anything is written.
    """
    serialized = json.dumps(payload)
    if len(serialized.encode('utf-8')) > MAX_DEVICE_TOOL_RESULT_BYTES:
        raise ValueError('Device tool result too large')
    if not claim_device_tool_inflight(uid, call_id):
        raise UnknownDeviceToolCall(call_id)
    redis_client.setex(device_tool_result_key(uid, call_id), DEVICE_TOOL_RESULT_TTL_SECONDS, serialized)


def _read_device_tool_result(uid: str, call_id: str) -> Optional[dict]:
    raw = redis_client.get(device_tool_result_key(uid, call_id))
    if raw is None:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8')
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning('Discarding unparseable device tool result uid=%s call_id=%s', uid, call_id)
        return None
    return parsed if isinstance(parsed, dict) else None


def _clear_device_tool_result(uid: str, call_id: str) -> None:
    try:
        redis_client.delete(device_tool_result_key(uid, call_id))
    except Exception as error:
        # A stale key expires on its own; failing the tool over cleanup would
        # discard a result the user already produced.
        logger.warning('Could not clear device tool result error_type=%s', type(error).__name__)


async def _await_device_tool_result(uid: str, call_id: str, timeout_seconds: int) -> dict:
    """Poll for the client's result until it arrives or the bound elapses."""
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        try:
            result = await run_blocking(db_executor, _read_device_tool_result, uid, call_id)
        except Exception as error:
            # The request frame is already on the wire and the compose sheet may
            # already be open, so a Redis outage here says nothing about whether
            # the user sent the message. Letting this propagate would surface a
            # generic execution error, and the model would be free to retry —
            # sending the same message twice. A transient blip should not end the
            # wait either, so keep polling and only give up at the deadline.
            record_fallback(
                component='chat',
                from_mode='device_tool_result',
                to_mode='device_tool_poll_retry',
                reason=type(error).__name__,
                outcome='degraded',
                log=logger,
            )
            await asyncio.sleep(DEVICE_TOOL_POLL_INTERVAL_SECONDS)
            continue
        if result is not None:
            await run_blocking(db_executor, _clear_device_tool_result, uid, call_id)
            return result
        await asyncio.sleep(DEVICE_TOOL_POLL_INTERVAL_SECONDS)

    return {
        'ok': False,
        'reason': 'timed_out',
        'error': (
            'The user did not respond on their device in time. Do not retry automatically; '
            'ask them whether they still want this.'
        ),
    }


def build_device_tools(
    uid: str,
    available_tool_names: set[str],
    callback: Any,
    timeout_seconds: int,
) -> list:
    """Build LangChain tools for the device capabilities this client declared.

    ``available_tool_names`` comes from the client on the request that opened
    this turn. A tool the client did not declare is never advertised, so the
    model cannot call a capability the device in hand does not have — an iPad
    with no messaging service, or an Android build with no implementation.

    ``timeout_seconds`` has no default on purpose. Only the caller knows the
    turn's stream budget, and a wait that outlives it silently converts a
    user-cancelled sheet into a dead turn; requiring it makes the caller state
    the bound rather than inherit a stale one.
    """
    tools = []
    for name in sorted(DEVICE_TOOL_NAMES & set(available_tool_names)):
        spec = DEVICE_TOOL_SPECS[name]
        tools.append(_build_one(uid, name, spec, callback, timeout_seconds))
    return tools


def _build_one(uid: str, name: str, spec: dict, callback: Any, timeout_seconds: int):
    async def _call(**kwargs) -> str:
        # Drop the RunnableConfig LangChain injects; it is not part of the
        # payload the device should receive.
        kwargs.pop('config', None)
        call_id = str(uuid.uuid4())
        request = {
            'call_id': call_id,
            'tool': name,
            'arguments': {key: value for key, value in kwargs.items() if value is not None},
        }

        logger.info('Dispatching device tool uid=%s tool=%s call_id=%s', uid, name, call_id)
        started_at = time.monotonic()
        # Marked before the frame goes out, so the result endpoint can never
        # observe a result for a call this uid was not actually asked to make.
        await run_blocking(db_executor, mark_device_tool_inflight, uid, call_id)
        await callback.put_device_tool_request(request)

        try:
            result = await _await_device_tool_result(uid, call_id, timeout_seconds)
        finally:
            # Once the wait is over the answer is no longer wanted. Dropping the
            # marker means a late submission is rejected rather than left in
            # Redis for the remainder of its TTL.
            await run_blocking(db_executor, clear_device_tool_inflight, uid, call_id)
        logger.info(
            'Device tool settled uid=%s tool=%s call_id=%s ok=%s elapsed_ms=%d',
            uid,
            name,
            call_id,
            result.get('ok'),
            int((time.monotonic() - started_at) * 1000),
        )
        # Returned as JSON text: the model reads `status` and `ok` directly, and
        # a cancelled sheet must stay visibly distinct from a delivered message.
        return json.dumps(result)

    return StructuredTool.from_function(
        coroutine=_call,
        name=name,
        description=spec['description'],
        args_schema=spec['args_schema'],
    )
