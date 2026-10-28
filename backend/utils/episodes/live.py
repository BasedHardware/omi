"""Live moment detection on the realtime transcript stream.

``trigger_realtime_integrations`` hands every new batch of final segments to
``observe_segments``. Segments accumulate per user until the moment ends:

- a pause: the next batch arrives at least ``MOMENT_PAUSE_SECONDS`` after the
  previous one;
- a rollover: the buffer reaches ``MOMENT_MAX_WORDS``, or the stream moves to
  another conversation;
- an interval: the buffer has spanned ``MOMENT_MAX_SECONDS`` of steady speech, or,
  for the first moment of a live stretch, ``FIRST_MOMENT_MIN_SECONDS`` and
  ``FIRST_MOMENT_MIN_WORDS`` (so the episode has a title within a minute);
- a session end: the pusher session closes (``on_session_end``), so a pod move or
  a reconnect does not strand what was buffered. Only the ending session's own
  conversation is flushed: a parallel capture on the same pod keeps its buffer.
  (The listen fallback, used only when pusher is unavailable, still relies on
  finalization for what it buffered.)

A moment shorter than ``MOMENT_MIN_WORDS``, or one inside
``MOMENT_MIN_INTERVAL_SECONDS`` of the last flush, keeps accumulating instead
of costing a call. The buffer is in-process and bounded (TTL plus a size cap):
losing it on a crash loses nothing durable, because finalization applies
every segment the live stream did not (``service.on_conversation_finalized``).

Structure does not wait for a moment. The first speech of each conversation
attaches it to the live episode (``service.attach_conversation``, no model
call), so the app shows the episode, its start time and its member
conversations from the first words; the moments only fill in the notes.

Only users whose app can show episodes cost anything: attaching and ended
moments first check the client-capability marker
(``client_gate.client_seen_cached``, at most one Redis read per user per
process every couple of minutes, on ``db_executor``) and are dropped, counted,
when no capable client was seen.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

from config.episodes import (
    FIRST_MOMENT_MIN_SECONDS,
    FIRST_MOMENT_MIN_WORDS,
    MOMENT_MAX_SECONDS,
    MOMENT_MAX_WORDS,
    MOMENT_MIN_INTERVAL_SECONDS,
    MOMENT_MIN_WORDS,
    MOMENT_PAUSE_SECONDS,
    episodes_enabled_for,
)
from utils.episodes import client_gate, metrics
from utils.episodes.moment import MomentInput
from utils import executors

logger = logging.getLogger(__name__)

BUFFER_TTL_SECONDS = 2 * 60 * 60
MAX_BUFFERS = 5_000
MAX_BUFFERED_SEGMENTS = 400
ACTIVITY_INTERVAL_SECONDS = 60


@dataclass
class _Buffer:
    conversation_id: str
    source: Optional[str]
    first_wall: float
    last_wall: float
    segments: list[dict[str, Any]] = field(default_factory=list)
    words: int = 0
    last_flush_wall: float = 0.0


class MomentTracker:
    """Per-user moment buffers. Thread-safe; never does I/O."""

    def __init__(self) -> None:
        self._buffers: dict[str, _Buffer] = {}
        self._lock = threading.Lock()

    def _evict(self, now: float) -> None:
        stale = [uid for uid, buf in self._buffers.items() if now - buf.last_wall > BUFFER_TTL_SECONDS]
        for uid in stale:
            del self._buffers[uid]
        while len(self._buffers) > MAX_BUFFERS:
            oldest = min(self._buffers, key=lambda uid: self._buffers[uid].last_wall)
            del self._buffers[oldest]

    @staticmethod
    def _moment(buf: _Buffer, trigger: str) -> MomentInput:
        return MomentInput(
            conversation_id=buf.conversation_id,
            source=buf.source,
            segments=list(buf.segments),
            started_at=datetime.fromtimestamp(buf.first_wall, timezone.utc),
            ended_at=datetime.fromtimestamp(buf.last_wall, timezone.utc),
            trigger=trigger,
        )

    def observe(
        self,
        uid: str,
        segments: Sequence[Mapping[str, Any]],
        conversation_id: Optional[str],
        source: Optional[str],
        *,
        now: Optional[float] = None,
    ) -> list[MomentInput]:
        """Returns the moments that ended with this batch (usually none, at most two)."""
        if not conversation_id:
            return []
        wall = time.time() if now is None else now
        fresh = [dict(s) for s in segments if str(s.get('text') or '').strip()]
        ended: list[MomentInput] = []
        with self._lock:
            self._evict(wall)
            buf = self._buffers.get(uid)
            if buf is not None and buf.segments:
                moved = buf.conversation_id != conversation_id
                paused = wall - buf.last_wall >= MOMENT_PAUSE_SECONDS
                spaced = wall - buf.last_flush_wall >= MOMENT_MIN_INTERVAL_SECONDS
                if moved or (paused and buf.words >= MOMENT_MIN_WORDS and spaced):
                    ended.append(self._moment(buf, 'rollover' if moved else 'pause'))
                    buf = _Buffer(conversation_id, source, wall, wall, last_flush_wall=wall)
                    self._buffers[uid] = buf
            if buf is None or (buf.conversation_id != conversation_id and not buf.segments):
                buf = _Buffer(conversation_id, source, wall, wall, last_flush_wall=buf.last_flush_wall if buf else 0.0)
                self._buffers[uid] = buf
            if fresh:
                if not buf.segments:
                    buf.first_wall = wall
                buf.segments.extend(fresh)
                del buf.segments[:-MAX_BUFFERED_SEGMENTS]
                buf.words += sum(len(str(s.get('text') or '').split()) for s in fresh)
                buf.last_wall = wall
                if buf.words >= MOMENT_MAX_WORDS:
                    ended.append(self._moment(buf, 'rollover'))
                    self._buffers[uid] = _Buffer(conversation_id, source, wall, wall, last_flush_wall=wall)
                elif (
                    wall - buf.first_wall >= MOMENT_MAX_SECONDS
                    and buf.words >= MOMENT_MIN_WORDS
                    and wall - buf.last_flush_wall >= MOMENT_MIN_INTERVAL_SECONDS
                ) or (
                    # Nothing flushed yet in this live stretch: give the episode its first notes early.
                    buf.last_flush_wall == 0.0
                    and buf.words >= FIRST_MOMENT_MIN_WORDS
                    and wall - buf.first_wall >= FIRST_MOMENT_MIN_SECONDS
                ):
                    ended.append(self._moment(buf, 'interval'))
                    self._buffers[uid] = _Buffer(conversation_id, source, wall, wall, last_flush_wall=wall)
        return ended

    def flush(self, uid: str, conversation_id: Optional[str]) -> Optional[MomentInput]:
        """The session for ``conversation_id`` ended: hand over its buffer (the service drops it when too short)."""
        if not conversation_id:
            return None
        with self._lock:
            buf = self._buffers.get(uid)
            if buf is None or buf.conversation_id != conversation_id or not buf.segments:
                return None
            del self._buffers[uid]
        return self._moment(buf, 'session_end')

    def clear(self) -> None:
        with self._lock:
            self._buffers.clear()


tracker = MomentTracker()


class _SessionCounter:
    """Remembers each user's recent conversations, so each one is attached and counted once.

    A few per user, not just the last: two devices capturing in parallel alternate batches,
    and remembering only the last id re-attached (and re-counted) on every switch.
    """

    RECENT_PER_USER = 6

    def __init__(self, cap: int = MAX_BUFFERS) -> None:
        self._last: dict[str, list[str]] = {}
        self._activity: dict[str, dict[str, float]] = {}
        self._cap = cap
        self._lock = threading.Lock()

    def first_moment(self, uid: str, conversation_id: str) -> bool:
        with self._lock:
            recent = self._last.pop(uid, [])
            self._last[uid] = recent
            if conversation_id in recent:
                return False
            recent.append(conversation_id)
            for stale in recent[: -self.RECENT_PER_USER]:
                self._activity.get(uid, {}).pop(stale, None)
            del recent[: -self.RECENT_PER_USER]
            while len(self._last) > self._cap:
                stale_uid = next(iter(self._last))
                del self._last[stale_uid]
                self._activity.pop(stale_uid, None)
            return True

    def activity_due(self, uid: str, conversation_id: str) -> bool:
        """Coalesce retained batches into a minute clock, independent of notes calls."""
        now = time.monotonic()
        with self._lock:
            times = self._activity.setdefault(uid, {})
            previous = times.get(conversation_id)
            if previous is not None and now - previous < ACTIVITY_INTERVAL_SECONDS:
                return False
            times[conversation_id] = now
            return True

    def clear(self) -> None:
        with self._lock:
            self._last.clear()
            self._activity.clear()


sessions = _SessionCounter()


async def _attach_if_client_seen(
    uid: str, conversation_id: str, source: Optional[str], started_at: datetime, *, first: bool = True
) -> str:
    """Retained speech: open/join or advance activity, with no model call."""
    seen = await executors.run_blocking(executors.db_executor, client_gate.client_seen_cached, uid)
    if first:
        metrics.record_live_session(seen)
    if not seen:
        metrics.record_moment_skipped_no_client('attach')
        return 'skipped_no_client'
    from utils.episodes.service import attach_conversation

    return await executors.run_blocking(
        executors.db_executor, attach_conversation, uid, conversation_id, source, started_at=started_at
    )


async def _moment_if_client_seen(uid: str, moment: MomentInput) -> str:
    """One ended moment: spend only when the user's app can show episodes."""
    seen = await executors.run_blocking(executors.db_executor, client_gate.client_seen_cached, uid)
    if not seen:
        metrics.record_moment_skipped_no_client(moment.trigger)
        return 'skipped_no_client'
    # Deferred: this module sits on the realtime fan-out's import path (app_integrations), and the
    # orchestration pulls in the model client stack only once a moment actually ends.
    from utils.episodes.service import record_moment

    return await executors.run_blocking(executors.lifecycle_executor(uid), record_moment, uid, moment)


async def on_realtime_segments(
    uid: str, segments: Sequence[Mapping[str, Any]], conversation_id: Optional[str], source: Optional[str] = None
) -> None:
    """Fire-and-forget: never blocks or fails the realtime fan-out."""
    try:
        if not episodes_enabled_for(uid):
            return
        spoken = any(str(s.get('text') or '').strip() for s in segments)
        if conversation_id and spoken:
            first = sessions.first_moment(uid, conversation_id)
            if sessions.activity_due(uid, conversation_id):
                executors.start_background_task(
                    _attach_if_client_seen(uid, conversation_id, source, datetime.now(timezone.utc), first=first),
                    name='episode_attach',
                )
        moments = tracker.observe(uid, segments, conversation_id, source)
        if not moments:
            return
        for moment in moments:
            executors.start_background_task(_moment_if_client_seen(uid, moment), name='episode_moment')
    except Exception as error:
        logger.warning('event=episode_live outcome=error exception_type=%s', type(error).__name__)


async def on_session_end(uid: str, conversation_id: Optional[str]) -> None:
    """The pusher session for ``conversation_id`` closed: flush its buffered moment. Never raises."""
    try:
        if not episodes_enabled_for(uid):
            return
        moment = tracker.flush(uid, conversation_id)
        if moment is not None:
            executors.start_background_task(_moment_if_client_seen(uid, moment), name='episode_moment')
    except Exception as error:
        logger.warning('event=episode_live outcome=session_end_error exception_type=%s', type(error).__name__)
