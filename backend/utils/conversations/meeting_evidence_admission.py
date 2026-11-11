"""Bounded wait for a desktop meeting's screen evidence before its notes are written.

When a cloud-STT desktop meeting stops, the Mac closes the listen socket first
and only then runs its pre-notes evidence pass (screenshot adjudication, the
on-device meeting identity upload, the OCR flush). Socket teardown admits
finalization at once, so without a wait the notes are written before that
evidence lands and the one-pass design never engages.

This admission step runs in the shared persisted-conversation finalizer (pusher
and Cloud Tasks workers alike, which also covers POST /finalize). It is an async
wait: each poll borrows a db_executor thread for one Firestore read and the
sleep holds no thread, so no pool slot is held for the bound. It proceeds as
soon as this environment's adjudication marker for the conversation is set for
its current content window (same fingerprint the Mac's pass stamped), otherwise after MEETING_NOTES_EVIDENCE_WAIT_SECONDS. It never fails
finalization: every error proceeds without evidence.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Awaitable, Callable, Mapping

from database.screen_frames import get_conversation_content_window_fields, get_conversation_screen_frames_marker
from database.users import get_meeting_note_screenshots_enabled
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.executors import db_executor, run_blocking
from utils.metrics import MEETING_NOTES_EVIDENCE_WAIT_TOTAL
from utils.observability.fallback import record_fallback
from utils.other.storage import configured_screen_frames_bucket
from utils.conversations.screen_content_window import selection_fingerprint, trusted_content_window

logger = logging.getLogger(__name__)

EVIDENCE_WAIT_ENV = 'MEETING_NOTES_EVIDENCE_WAIT_SECONDS'
MAX_EVIDENCE_WAIT_SECONDS = 60.0
EVIDENCE_POLL_SECONDS = 2.0
# A client ending its own capture races the same way; a reprocess, a merge, a
# first open, or a server recovery comes long after the evidence pass.
_WAITING_TRIGGERS = frozenset({ProcessingTrigger.CAPTURE_END, ProcessingTrigger.CLIENT_FINALIZE})


def evidence_wait_seconds() -> float:
    """The configured bound; 0 (no wait) unless a deployment opts in."""
    raw = (os.getenv(EVIDENCE_WAIT_ENV) or '').strip()
    try:
        value = float(raw) if raw else 0.0
    except ValueError:
        return 0.0
    return min(max(value, 0.0), MAX_EVIDENCE_WAIT_SECONDS)


def is_desktop_meeting_capture(conversation_data: Mapping[str, Any]) -> bool:
    """A desktop meeting whose client declared it runs the pre-notes evidence pass.

    The declaration (listen query ``screen_evidence=enabled``, persisted as
    ``external_data.screen_evidence_pass``) keeps released desktop builds, which
    never run the pass, from waiting on evidence that will not come.
    """
    source = conversation_data.get('source')
    external_data = conversation_data.get('external_data')
    return (
        getattr(source, 'value', source) == 'desktop'
        and isinstance(external_data, Mapping)
        and external_data.get('conversation_role') == 'meeting'
        and external_data.get('screen_evidence_pass') is True
    )


async def await_meeting_evidence(
    uid: str,
    conversation_id: str,
    conversation_data: Mapping[str, Any],
    *,
    trigger: ProcessingTrigger,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> str:
    """Wait (bounded) for the Mac's evidence pass; returns the outcome label.

    ``not_applicable``: not a waiting trigger, not a desktop meeting, the wait
    is disabled, this host has no screen-frame bucket, or the account's
    screenshot setting is off (no evidence will come). ``present``: already
    there. ``arrived``: landed during the wait. ``no_window``: the conversation has
    no trusted content window, so no pass can be stamped; proceeded at once.
    ``timed_out``: proceeded without.
    """
    bound = evidence_wait_seconds()
    bucket = configured_screen_frames_bucket()
    if trigger not in _WAITING_TRIGGERS or bound <= 0 or not bucket:
        return 'not_applicable'
    if not is_desktop_meeting_capture(conversation_data):
        return 'not_applicable'
    outcome = 'timed_out'
    started = monotonic()

    def remaining() -> float:
        return bound - (monotonic() - started)

    try:
        if not await _bounded(get_meeting_note_screenshots_enabled, uid, budget=remaining()):
            return 'not_applicable'
        first = True
        while True:
            state = await _current_pass_state(uid, conversation_id, bucket, remaining)
            if state == 'landed':
                outcome = 'present' if first else 'arrived'
                break
            if state == 'no_window' and first:
                # Nothing the Mac can select or stamp: the adjudication route refuses an
                # open conversation without a trusted content window. Proceed now.
                outcome = 'no_window'
                break
            first = False
            if remaining() <= 0:
                break
            await sleep(min(EVIDENCE_POLL_SECONDS, remaining()))
    except asyncio.TimeoutError:
        outcome = 'timed_out'  # a read that outlived the bound: proceed without evidence
    except Exception as error:  # noqa: BLE001 - evidence is optional; notes must proceed
        logger.warning('meeting notes evidence wait failed uid=%s error_type=%s', uid, type(error).__name__)
        outcome = 'error'
    if outcome in ('timed_out', 'error'):
        # Either way the notes are written without the evidence the client declared.
        record_fallback(
            component='conversation_finalization',
            from_mode='screen_evidence',
            to_mode='notes_without_evidence',
            reason='timeout' if outcome == 'timed_out' else 'other',
            outcome='degraded',
            log=logger,
        )
    waited = monotonic() - started
    MEETING_NOTES_EVIDENCE_WAIT_TOTAL.labels(outcome=outcome).inc()
    logger.info(
        'meeting notes evidence admission outcome=%s waited_s=%.1f uid=%s conversation=%s',
        outcome,
        waited,
        uid,
        conversation_id,
    )
    return outcome


async def _current_pass_state(uid: str, conversation_id: str, bucket: str, remaining: Callable[[], float]) -> str:
    """``landed``: this bucket's marker covers the conversation's CURRENT trusted
    content window. ``no_window``: the conversation has no trusted window, so no
    pass can be stamped for it. ``waiting``: otherwise.

    A marker stamped mid-meeting for an earlier window is stale once the
    transcript extends: the Mac then runs a fresh pass for the new fingerprint,
    and the notes must wait for that one. Both reads are re-done each poll.
    """
    conversation = await _bounded(get_conversation_content_window_fields, uid, conversation_id, budget=remaining())
    window = trusted_content_window(conversation) if conversation else None
    if window is None:
        return 'no_window'
    stamp, fingerprint = await _bounded(
        get_conversation_screen_frames_marker, uid, conversation_id, bucket=bucket, budget=remaining()
    )
    return 'landed' if stamp is not None and fingerprint == selection_fingerprint(*window) else 'waiting'


async def _bounded(fn: Callable[..., Any], *args: Any, budget: float, **kwargs: Any) -> Any:
    """One Firestore read within what is left of the bound: the await is cut at
    the deadline and the RPC itself gets one attempt with that timeout."""
    if budget <= 0:
        raise asyncio.TimeoutError()
    return await asyncio.wait_for(
        run_blocking(db_executor, fn, *args, rpc_timeout=budget, **kwargs),
        timeout=budget,
    )
