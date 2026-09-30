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
soon as this environment's adjudication marker for the conversation is set,
otherwise after MEETING_NOTES_EVIDENCE_WAIT_SECONDS. It never fails
finalization: every error proceeds without evidence.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Awaitable, Callable, Mapping, Optional

from database.screen_frames import get_conversation_screen_frames_adjudicated_at
from database.users import get_meeting_note_screenshots_enabled
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.executors import db_executor, run_blocking
from utils.metrics import MEETING_NOTES_EVIDENCE_WAIT_TOTAL
from utils.other.storage import configured_screen_frames_bucket

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
    source = conversation_data.get('source')
    external_data = conversation_data.get('external_data')
    return (
        getattr(source, 'value', source) == 'desktop'
        and isinstance(external_data, Mapping)
        and external_data.get('conversation_role') == 'meeting'
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
    there. ``arrived``: landed during the wait. ``timed_out``: proceeded without.
    """
    bound = evidence_wait_seconds()
    bucket = configured_screen_frames_bucket()
    if trigger not in _WAITING_TRIGGERS or bound <= 0 or not bucket:
        return 'not_applicable'
    if not is_desktop_meeting_capture(conversation_data):
        return 'not_applicable'
    outcome = 'timed_out'
    started = monotonic()
    try:
        if not await run_blocking(db_executor, get_meeting_note_screenshots_enabled, uid):
            return 'not_applicable'
        first = True
        while True:
            if await _evidence_landed(uid, conversation_id, bucket):
                outcome = 'present' if first else 'arrived'
                break
            first = False
            remaining = bound - (monotonic() - started)
            if remaining <= 0:
                break
            await sleep(min(EVIDENCE_POLL_SECONDS, remaining))
    except Exception as error:  # noqa: BLE001 - evidence is optional; notes must proceed
        logger.warning('meeting notes evidence wait failed uid=%s error_type=%s', uid, type(error).__name__)
        outcome = 'error'
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


async def _evidence_landed(uid: str, conversation_id: str, bucket: str) -> bool:
    stamp: Optional[Any] = await run_blocking(
        db_executor, get_conversation_screen_frames_adjudicated_at, uid, conversation_id, bucket=bucket
    )
    return stamp is not None
