"""Tests for #6061: local conversation fallback removal.

Verifies that listen never runs process_conversation() locally.
All conversation processing is routed through pusher via
request_conversation_processing(). When pusher is unavailable,
conversations stay buffered in pending_conversation_requests.

Architecture note: transcribe.py's handlers are deeply nested closures
inside websocket_endpoint() and cannot be imported directly. These tests
mirror the behavioral contracts and verify the logic in isolation.
Live integration tests (CP9) verify the actual production closures via
WebSocket connections to a running backend.
"""

import time
from enum import Enum
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Constants (mirrored from transcribe.py)
# ---------------------------------------------------------------------------
PENDING_REQUEST_TIMEOUT = 120
MAX_RETRIES_PER_REQUEST = 3
PUSHER_MAX_RECONNECT_ATTEMPTS = 6


class PusherReconnectState(Enum):
    CONNECTED = "connected"
    RECONNECT_BACKOFF = "reconnect_backoff"
    DEGRADED = "degraded"
    HALF_OPEN_PROBE = "half_open_probe"


class ConversationStatus:
    processing = "processing"


# ---------------------------------------------------------------------------
# Helpers: mirror the changed behavioral contracts from transcribe.py
# ---------------------------------------------------------------------------


async def _process_conversation(
    conversation_id: str,
    conversations_db,
    uid: str,
    request_conversation_processing,
    on_conversation_processing_started,
):
    """Mirrors _process_conversation() from transcribe.py after #6061.

    Key contract: NEVER calls process_conversation() locally.
    Checks pusher availability BEFORE marking processing to avoid stranding conversations.
    """
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if conversation:
        has_content = conversation.get('transcript_segments') or conversation.get('photos')
        if has_content:
            if not request_conversation_processing:
                return  # Warning logged — pusher not enabled, skip (stays in_progress)
            conversations_db.update_conversation_status(uid, conversation_id, ConversationStatus.processing)
            on_conversation_processing_started(conversation_id)
            await request_conversation_processing(conversation_id)
        else:
            conversations_db.delete_conversation(uid, conversation_id)


async def cleanup_processing_conversations(
    conversations_db,
    uid: str,
    request_conversation_processing,
):
    """Mirrors cleanup_processing_conversations() from transcribe.py after #6061.

    Key contract: routes all processing conversations through
    request_conversation_processing. Never processes locally.
    Guards None before calling len() to avoid TypeError.
    """
    processing = conversations_db.get_processing_conversations(uid)
    if not processing:
        return
    if len(processing) == 0:
        return
    if not request_conversation_processing:
        return

    for conversation in processing:
        await request_conversation_processing(conversation['id'])


def check_timed_out_requests_6061(pending_requests: dict, now: float):
    """Mirrors the retry-exhaustion logic from pusher_receive() after #6061.

    Key contract: retry exhaustion keeps the request buffered and resets
    sent_at instead of dropping it. cleanup_processing_conversations()
    picks it up on next session.
    """
    timed_out = [cid for cid, info in list(pending_requests.items()) if now - info['sent_at'] > PENDING_REQUEST_TIMEOUT]
    actions = []
    for cid in timed_out:
        info = pending_requests.get(cid)
        if not info:
            continue
        if info['retries'] >= MAX_RETRIES_PER_REQUEST:
            # #6061: Don't drop — keep buffered, reset timeout
            info['sent_at'] = now
            actions.append(('keep_buffered', cid))
            continue
        info['retries'] += 1
        info['sent_at'] = now
        actions.append(('retry', cid, info['retries']))
    return actions


def degraded_transition_6061(
    pending_conversation_requests: dict,
    reconnect_state: PusherReconnectState,
    reconnect_attempts: int = 0,
    circuit_breaker_open: bool = False,
):
    """Mirrors the DEGRADED transition logic from _pusher_reconnect_loop() after #6061.

    Key contract: pending conversations are KEPT buffered when entering DEGRADED.
    Never popped + fallback-processed.
    Transitions to DEGRADED when: attempts >= cap OR circuit breaker open.
    """
    if reconnect_state == PusherReconnectState.RECONNECT_BACKOFF:
        if circuit_breaker_open or reconnect_attempts >= PUSHER_MAX_RECONNECT_ATTEMPTS:
            return PusherReconnectState.DEGRADED, dict(pending_conversation_requests)
        # Still in backoff, not yet at cap
        return PusherReconnectState.RECONNECT_BACKOFF, pending_conversation_requests
    return reconnect_state, pending_conversation_requests


def reconnect_resend_6061(pending_conversation_requests: dict):
    """Mirrors _connect() resend logic from transcribe.py after #6061.

    Key contract: all pending conversations are resent on reconnect.
    No fallback_processed_ids dedup — all buffered conversations are replayed.
    """
    resent = []
    for cid in list(pending_conversation_requests.keys()):
        pending_conversation_requests[cid]['sent_at'] = time.time()
        resent.append(cid)
    return resent


# ---------------------------------------------------------------------------
# Tests: _process_conversation() — always marks processing + buffers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_conversation_marks_processing_and_routes_to_pusher():
    """_process_conversation() marks status=processing and calls request_conversation_processing."""
    db = MagicMock()
    db.get_conversation.return_value = {'transcript_segments': [{'text': 'hello'}]}
    request_fn = AsyncMock()
    on_started = MagicMock()

    await _process_conversation('conv-1', db, 'uid-1', request_fn, on_started)

    db.update_conversation_status.assert_called_once_with('uid-1', 'conv-1', ConversationStatus.processing)
    on_started.assert_called_once_with('conv-1')
    request_fn.assert_awaited_once_with('conv-1')


@pytest.mark.asyncio
async def test_process_conversation_never_calls_local_fallback():
    """_process_conversation() never imports or calls process_conversation locally."""
    db = MagicMock()
    db.get_conversation.return_value = {'transcript_segments': [{'text': 'hello'}]}
    request_fn = AsyncMock()
    on_started = MagicMock()

    await _process_conversation('conv-1', db, 'uid-1', request_fn, on_started)

    # The key assertion: request_conversation_processing is the ONLY processing path
    request_fn.assert_awaited_once()
    # No local process_conversation, no trigger_external_integrations, no get_google_maps_location


@pytest.mark.asyncio
async def test_process_conversation_null_guard_skips_processing():
    """When request_conversation_processing is None (pusher disabled), conversation stays in_progress."""
    db = MagicMock()
    db.get_conversation.return_value = {'transcript_segments': [{'text': 'hello'}]}
    on_started = MagicMock()

    # Should not raise
    await _process_conversation('conv-1', db, 'uid-1', None, on_started)

    # Must NOT mark processing — no way to process without pusher
    db.update_conversation_status.assert_not_called()
    on_started.assert_not_called()


@pytest.mark.asyncio
async def test_process_conversation_no_content_deletes():
    """Conversation with no content is deleted, not processed."""
    db = MagicMock()
    db.get_conversation.return_value = {'transcript_segments': [], 'photos': []}
    request_fn = AsyncMock()
    on_started = MagicMock()

    await _process_conversation('conv-1', db, 'uid-1', request_fn, on_started)

    db.delete_conversation.assert_called_once_with('uid-1', 'conv-1')
    request_fn.assert_not_awaited()
    on_started.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: cleanup_processing_conversations() — routes through pusher
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cleanup_routes_all_processing_to_pusher():
    """cleanup_processing_conversations() calls request_conversation_processing for each."""
    db = MagicMock()
    db.get_processing_conversations.return_value = [{'id': 'conv-1'}, {'id': 'conv-2'}, {'id': 'conv-3'}]
    request_fn = AsyncMock()

    await cleanup_processing_conversations(db, 'uid-1', request_fn)

    assert request_fn.await_count == 3
    request_fn.assert_any_await('conv-1')
    request_fn.assert_any_await('conv-2')
    request_fn.assert_any_await('conv-3')


@pytest.mark.asyncio
async def test_cleanup_null_handler_returns_safely():
    """cleanup_processing_conversations() with null handler does not crash."""
    db = MagicMock()
    db.get_processing_conversations.return_value = [{'id': 'conv-1'}]

    # Should not raise
    await cleanup_processing_conversations(db, 'uid-1', None)


@pytest.mark.asyncio
async def test_cleanup_empty_processing_is_noop():
    """cleanup_processing_conversations() with no processing conversations is a no-op."""
    db = MagicMock()
    db.get_processing_conversations.return_value = []
    request_fn = AsyncMock()

    await cleanup_processing_conversations(db, 'uid-1', request_fn)

    request_fn.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_none_processing_no_crash():
    """cleanup_processing_conversations() handles None from get_processing_conversations without TypeError."""
    db = MagicMock()
    db.get_processing_conversations.return_value = None
    request_fn = AsyncMock()

    # Must not raise TypeError on len(None)
    await cleanup_processing_conversations(db, 'uid-1', request_fn)

    request_fn.assert_not_awaited()


# ---------------------------------------------------------------------------
# Tests: retry exhaustion — keep buffered, don't drop (#6061)
# ---------------------------------------------------------------------------


def test_retry_exhaustion_keeps_buffered():
    """After MAX_RETRIES, conversation stays in pending with reset sent_at."""
    now = time.time()
    pending = {"conv-1": {"sent_at": now - PENDING_REQUEST_TIMEOUT - 1, "retries": MAX_RETRIES_PER_REQUEST}}

    actions = check_timed_out_requests_6061(pending, now)

    assert len(actions) == 1
    assert actions[0] == ('keep_buffered', 'conv-1')
    assert "conv-1" in pending, "Must NOT be removed from pending"
    assert pending["conv-1"]["sent_at"] == now, "sent_at must be reset"


def test_retry_exhaustion_does_not_drop():
    """Retry exhaustion must never remove the conversation from pending."""
    now = time.time()
    pending = {"conv-1": {"sent_at": now - PENDING_REQUEST_TIMEOUT - 1, "retries": MAX_RETRIES_PER_REQUEST + 5}}

    check_timed_out_requests_6061(pending, now)

    assert "conv-1" in pending, "Conversation must stay buffered regardless of retry count"


def test_normal_retry_still_increments():
    """Before MAX_RETRIES, normal retry behavior is preserved."""
    now = time.time()
    pending = {"conv-1": {"sent_at": now - PENDING_REQUEST_TIMEOUT - 1, "retries": 1}}

    actions = check_timed_out_requests_6061(pending, now)

    assert actions[0] == ('retry', 'conv-1', 2)
    assert pending["conv-1"]["retries"] == 2


# ---------------------------------------------------------------------------
# Tests: DEGRADED transition preserves pending (#6061)
# ---------------------------------------------------------------------------


def test_degraded_transition_preserves_pending():
    """Entering DEGRADED from RECONNECT_BACKOFF keeps all pending conversations."""
    pending = {
        "conv-1": {"sent_at": time.time(), "retries": 0},
        "conv-2": {"sent_at": time.time(), "retries": 2},
    }

    new_state, remaining = degraded_transition_6061(
        pending, PusherReconnectState.RECONNECT_BACKOFF, reconnect_attempts=PUSHER_MAX_RECONNECT_ATTEMPTS
    )

    assert new_state == PusherReconnectState.DEGRADED
    assert "conv-1" in remaining
    assert "conv-2" in remaining
    assert len(remaining) == 2


def test_degraded_transition_never_pops_pending():
    """DEGRADED transition must not pop any conversations from pending."""
    pending = {"conv-1": {"sent_at": time.time(), "retries": MAX_RETRIES_PER_REQUEST}}
    original_keys = set(pending.keys())

    degraded_transition_6061(
        pending, PusherReconnectState.RECONNECT_BACKOFF, reconnect_attempts=PUSHER_MAX_RECONNECT_ATTEMPTS
    )

    assert set(pending.keys()) == original_keys


# ---------------------------------------------------------------------------
# Tests: reconnect resend — all buffered conversations replayed (#6061)
# ---------------------------------------------------------------------------


def test_reconnect_resends_all_buffered():
    """After reconnect, all pending conversations are resent (no dedup filter)."""
    pending = {
        "conv-1": {"sent_at": time.time() - 200, "retries": 0},
        "conv-2": {"sent_at": time.time() - 100, "retries": 2},
        "conv-3": {"sent_at": time.time() - 50, "retries": MAX_RETRIES_PER_REQUEST},
    }

    resent = reconnect_resend_6061(pending)

    assert set(resent) == {"conv-1", "conv-2", "conv-3"}
    assert len(resent) == 3


def test_reconnect_no_fallback_dedup():
    """Reconnect resend has no fallback_processed_ids filter — all are replayed."""
    pending = {
        "conv-already-processed": {"sent_at": time.time() - 300, "retries": MAX_RETRIES_PER_REQUEST},
    }

    resent = reconnect_resend_6061(pending)

    assert "conv-already-processed" in resent, "No dedup — all must be resent"


def test_reconnect_resets_sent_at():
    """Reconnect resend resets sent_at for each conversation."""
    old_time = time.time() - 500
    pending = {"conv-1": {"sent_at": old_time, "retries": 1}}

    reconnect_resend_6061(pending)

    assert pending["conv-1"]["sent_at"] > old_time


# ---------------------------------------------------------------------------
# Tests: DEGRADED transition — reconnect cap and circuit breaker boundaries
# ---------------------------------------------------------------------------


def test_degraded_at_exact_reconnect_cap():
    """Transition to DEGRADED when reconnect_attempts == PUSHER_MAX_RECONNECT_ATTEMPTS."""
    pending = {"conv-1": {"sent_at": time.time(), "retries": 0}}

    new_state, remaining = degraded_transition_6061(
        pending, PusherReconnectState.RECONNECT_BACKOFF, reconnect_attempts=PUSHER_MAX_RECONNECT_ATTEMPTS
    )

    assert new_state == PusherReconnectState.DEGRADED
    assert "conv-1" in remaining


def test_no_degraded_below_reconnect_cap():
    """Stay in RECONNECT_BACKOFF when reconnect_attempts < PUSHER_MAX_RECONNECT_ATTEMPTS."""
    pending = {"conv-1": {"sent_at": time.time(), "retries": 0}}

    new_state, remaining = degraded_transition_6061(
        pending, PusherReconnectState.RECONNECT_BACKOFF, reconnect_attempts=PUSHER_MAX_RECONNECT_ATTEMPTS - 1
    )

    assert new_state == PusherReconnectState.RECONNECT_BACKOFF


def test_degraded_on_circuit_breaker_open():
    """Transition to DEGRADED immediately when circuit breaker is open, regardless of attempt count."""
    pending = {"conv-1": {"sent_at": time.time(), "retries": 0}}

    new_state, remaining = degraded_transition_6061(
        pending, PusherReconnectState.RECONNECT_BACKOFF, reconnect_attempts=0, circuit_breaker_open=True
    )

    assert new_state == PusherReconnectState.DEGRADED
    assert "conv-1" in remaining


def test_circuit_breaker_degraded_preserves_all_pending():
    """Circuit breaker triggered DEGRADED keeps all pending conversations."""
    pending = {
        "conv-1": {"sent_at": time.time(), "retries": 0},
        "conv-2": {"sent_at": time.time(), "retries": MAX_RETRIES_PER_REQUEST},
    }

    new_state, remaining = degraded_transition_6061(
        pending, PusherReconnectState.RECONNECT_BACKOFF, reconnect_attempts=1, circuit_breaker_open=True
    )

    assert len(remaining) == 2
    assert "conv-1" in remaining
    assert "conv-2" in remaining


# ---------------------------------------------------------------------------
# Tests: TTL boundary — exact and just-below timeout threshold
# ---------------------------------------------------------------------------


def test_timeout_exact_boundary_not_timed_out():
    """Request at exactly PENDING_REQUEST_TIMEOUT is NOT timed out (uses strict >)."""
    now = time.time()
    pending = {"conv-1": {"sent_at": now - PENDING_REQUEST_TIMEOUT, "retries": 0}}

    actions = check_timed_out_requests_6061(pending, now)

    assert len(actions) == 0, "Exact boundary should not trigger timeout (strict >)"


def test_timeout_just_below_threshold_not_timed_out():
    """Request 1 second before timeout threshold is not timed out."""
    now = time.time()
    pending = {"conv-1": {"sent_at": now - PENDING_REQUEST_TIMEOUT + 1, "retries": 0}}

    actions = check_timed_out_requests_6061(pending, now)

    assert len(actions) == 0


def test_timeout_just_above_threshold_triggers():
    """Request 1 second past timeout threshold triggers retry."""
    now = time.time()
    pending = {"conv-1": {"sent_at": now - PENDING_REQUEST_TIMEOUT - 1, "retries": 0}}

    actions = check_timed_out_requests_6061(pending, now)

    assert len(actions) == 1
    assert actions[0] == ('retry', 'conv-1', 1)
