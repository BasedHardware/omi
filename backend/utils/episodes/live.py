"""Live moment detection on the realtime transcript stream.

``trigger_realtime_integrations`` hands every new batch of final segments to
``observe_segments``. Segments accumulate per user until the moment ends:

- a pause: the next batch arrives at least ``MOMENT_PAUSE_SECONDS`` after the
  previous one;
- a rollover: the buffer reaches ``MOMENT_MAX_WORDS``. A conversation change
  carries its buffered speech into the next moment rather than spending a call;
- an interval: the buffer has spanned ``MOMENT_MAX_SECONDS`` of steady speech, or,
  for the first moment of a live stretch, ``FIRST_MOMENT_MIN_SECONDS`` and
  ``FIRST_MOMENT_MIN_WORDS`` (so the episode has a title within a minute);
- a session end: the pusher session closes, and the buffer stays available for a
  reconnect during one ``MOMENT_PAUSE_SECONDS`` window. If none arrives, the
  remaining tail is flushed as a moment. Finalization and wrap-up consume any
  buffer that remains.

A moment shorter than ``MOMENT_MIN_WORDS``, or one inside
``MOMENT_MIN_INTERVAL_SECONDS`` of the last flush, keeps accumulating instead
of costing a call; the bounded session-end flush can send a short terminal
tail. The buffer is in-process and bounded (TTL plus a size cap). If the process
crashes before a flush, finalization can apply every segment the live stream did
not (``service.on_conversation_finalized``).

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

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence
from config.recorded_time import recorded_episodes_enabled
from database import conversations as conversations_db
from utils.conversations.recorded_time import recorded_span, is_late

from config.episodes import (
    FIRST_MOMENT_MIN_SECONDS,
    FIRST_MOMENT_MIN_WORDS,
    MOMENT_MAX_SECONDS,
    MOMENT_MAX_WORDS,
    MOMENT_MIN_INTERVAL_SECONDS,
    MOMENT_MIN_WORDS,
    MOMENT_PAUSE_SECONDS,
    episode_carry_on_session_end_enabled,
    episodes_enabled_for,
)
from utils.episodes import client_gate, metrics
from utils.episodes.moment import MomentFragment, MomentInput
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
    carried: list[MomentFragment] = field(default_factory=list)
    words: int = 0
    last_flush_wall: float = 0.0
    current_first_wall: Optional[float] = None
    session_ended: bool = False
    session_end_generation: int = 0


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
        current_started = buf.current_first_wall if buf.current_first_wall is not None else buf.first_wall
        carried_start = min((fragment.started_at.timestamp() for fragment in buf.carried), default=current_started)
        return MomentInput(
            conversation_id=buf.conversation_id,
            source=buf.source,
            segments=list(buf.segments),
            started_at=datetime.fromtimestamp(min(carried_start, current_started), timezone.utc),
            ended_at=datetime.fromtimestamp(buf.last_wall, timezone.utc),
            trigger=trigger,
            carried=tuple(buf.carried),
            current_started_at=datetime.fromtimestamp(current_started, timezone.utc),
            current_ended_at=datetime.fromtimestamp(buf.last_wall, timezone.utc),
        )

    @staticmethod
    def _trim(buf: _Buffer) -> None:
        """Keep carried plus current segments within the existing per-user bound."""
        total = sum(len(fragment.segments) for fragment in buf.carried) + len(buf.segments)
        overflow = total - MAX_BUFFERED_SEGMENTS
        while overflow > 0 and buf.carried:
            fragment = buf.carried[0]
            remove = min(overflow, len(fragment.segments))
            buf.words -= sum(len(str(segment.get('text') or '').split()) for segment in fragment.segments[:remove])
            overflow -= remove
            remaining = fragment.segments[remove:]
            if remaining:
                buf.carried[0] = MomentFragment(
                    conversation_id=fragment.conversation_id,
                    source=fragment.source,
                    segments=remaining,
                    started_at=fragment.started_at,
                    ended_at=fragment.ended_at,
                )
            else:
                del buf.carried[0]
        if overflow > 0:
            removed = buf.segments[:overflow]
            buf.words -= sum(len(str(segment.get('text') or '').split()) for segment in removed)
            del buf.segments[:overflow]

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
        if not fresh:
            return []
        ended: list[MomentInput] = []
        with self._lock:
            self._evict(wall)
            buf = self._buffers.get(uid)
            if buf is not None and buf.segments:
                moved = buf.conversation_id != conversation_id
                resumed = buf.session_ended and not moved
                paused = not moved and not resumed and wall - buf.last_wall >= MOMENT_PAUSE_SECONDS
                spaced = wall - buf.last_flush_wall >= MOMENT_MIN_INTERVAL_SECONDS
                if paused and buf.words >= MOMENT_MIN_WORDS and spaced:
                    ended.append(self._moment(buf, 'pause'))
                    buf = _Buffer(conversation_id, source, wall, wall, last_flush_wall=wall)
                    self._buffers[uid] = buf
                elif moved:
                    buf.carried.append(
                        MomentFragment(
                            conversation_id=buf.conversation_id,
                            source=buf.source,
                            segments=tuple(dict(segment) for segment in buf.segments),
                            started_at=datetime.fromtimestamp(
                                buf.current_first_wall if buf.current_first_wall is not None else buf.first_wall,
                                timezone.utc,
                            ),
                            ended_at=datetime.fromtimestamp(buf.last_wall, timezone.utc),
                        )
                    )
                    buf.segments.clear()
                    buf.conversation_id = conversation_id
                    buf.source = source
                    buf.current_first_wall = None
                    buf.session_ended = False
                    self._trim(buf)
                else:
                    buf.session_ended = False
            if buf is None:
                buf = _Buffer(conversation_id, source, wall, wall)
                self._buffers[uid] = buf
            elif buf.conversation_id != conversation_id:
                # A carried-only buffer can move again before the next moment ends.
                buf.conversation_id = conversation_id
                buf.source = source
                buf.current_first_wall = None
                buf.session_ended = False
            if fresh:
                if not buf.segments:
                    buf.current_first_wall = wall
                    if not buf.carried:
                        buf.first_wall = wall
                buf.segments.extend(fresh)
                buf.words += sum(len(str(s.get('text') or '').split()) for s in fresh)
                buf.last_wall = wall
                buf.session_ended = False
                self._trim(buf)
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
                    and wall - (buf.current_first_wall if buf.current_first_wall is not None else buf.first_wall)
                    >= FIRST_MOMENT_MIN_SECONDS
                ):
                    ended.append(self._moment(buf, 'interval'))
                    self._buffers[uid] = _Buffer(conversation_id, source, wall, wall, last_flush_wall=wall)
        return ended

    def flush(
        self, uid: str, conversation_id: Optional[str] = None, *, trigger: str = 'finalize'
    ) -> Optional[MomentInput]:
        """Hand a pending buffer to finalization or wrap-up; session ends never call this."""
        with self._lock:
            buf = self._buffers.get(uid)
            if buf is None:
                return None
            if conversation_id is None or (buf.conversation_id == conversation_id and buf.segments):
                del self._buffers[uid]
                return self._moment(buf, trigger)
            matching = [fragment for fragment in buf.carried if fragment.conversation_id == conversation_id]
            if not matching:
                return None
            buf.carried = [fragment for fragment in buf.carried if fragment.conversation_id != conversation_id]
            buf.words -= sum(
                len(str(segment.get('text') or '').split()) for fragment in matching for segment in fragment.segments
            )
            segments = [dict(segment) for fragment in matching for segment in fragment.segments]
            start = min(fragment.started_at for fragment in matching)
            end = max(fragment.ended_at for fragment in matching)
            source = matching[-1].source
            return MomentInput(
                conversation_id=conversation_id,
                source=source,
                segments=segments,
                started_at=start,
                ended_at=end,
                trigger=trigger,
                current_started_at=start,
                current_ended_at=end,
            )

    def mark_session_end(self, uid: str, conversation_id: Optional[str]) -> Optional[int]:
        """Remember a session close and return its fence for the bounded carry timer."""
        if not conversation_id:
            return None
        with self._lock:
            buf = self._buffers.get(uid)
            if buf is not None and buf.conversation_id == conversation_id and (buf.segments or buf.carried):
                buf.session_ended = True
                buf.session_end_generation += 1
                return buf.session_end_generation
        return None

    def flush_session_end(self, uid: str, conversation_id: Optional[str], generation: int) -> Optional[MomentInput]:
        """Flush only the still-ended buffer named by this timer, after reconnect time has elapsed."""
        with self._lock:
            buf = self._buffers.get(uid)
            if (
                buf is None
                or not conversation_id
                or buf.conversation_id != conversation_id
                or not buf.session_ended
                or buf.session_end_generation != generation
            ):
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
        self._origins: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}
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

    def recorded_origin(self, uid: str, conversation_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            cached = self._origins.get((uid, conversation_id))
            if cached is not None and time.monotonic() - cached[0] < ACTIVITY_INTERVAL_SECONDS:
                return dict(cached[1])
            self._origins.pop((uid, conversation_id), None)
            return None

    def remember_origin(self, uid: str, conversation_id: str, row: Mapping[str, Any]) -> None:
        with self._lock:
            self._origins.pop((uid, conversation_id), None)
            self._origins[(uid, conversation_id)] = (time.monotonic(), dict(row))
            while len(self._origins) > self._cap:
                self._origins.pop(next(iter(self._origins)))

    def clear(self) -> None:
        with self._lock:
            self._last.clear()
            self._activity.clear()
            self._origins.clear()


sessions = _SessionCounter()


async def _attach_if_client_seen(
    uid: str,
    conversation_id: str,
    source: Optional[str],
    started_at: datetime,
    *,
    first: bool = True,
    ended_at: Optional[datetime] = None,
) -> str:
    """Retained speech: open/join or advance activity, with no model call."""
    seen = await executors.run_blocking(executors.db_executor, client_gate.client_seen_cached, uid)
    if first:
        metrics.record_live_session(seen)
    if not seen:
        metrics.record_moment_skipped_no_client('attach')
        return 'skipped_no_client'
    from utils.episodes.service import attach_conversation

    if ended_at is None:
        return await executors.run_blocking(
            executors.db_executor, attach_conversation, uid, conversation_id, source, started_at=started_at
        )
    return await executors.run_blocking(
        executors.db_executor,
        attach_conversation,
        uid,
        conversation_id,
        source,
        started_at=started_at,
        ended_at=ended_at,
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


async def _flush_session_end_after_timeout(uid: str, conversation_id: str, generation: int) -> None:
    """Let same-session reconnects reuse the buffer, then commit an unclaimed tail as a moment."""
    await asyncio.sleep(MOMENT_PAUSE_SECONDS)
    if not episodes_enabled_for(uid) or not episode_carry_on_session_end_enabled():
        return
    moment = tracker.flush_session_end(uid, conversation_id, generation)
    if moment is not None:
        await _moment_if_client_seen(uid, moment)


async def on_realtime_segments(
    uid: str, segments: Sequence[Mapping[str, Any]], conversation_id: Optional[str], source: Optional[str] = None
) -> None:
    """Fire-and-forget: never blocks or fails the realtime fan-out."""
    try:
        if not episodes_enabled_for(uid):
            return
        recorded = None
        if recorded_episodes_enabled() and conversation_id:
            if not await executors.run_blocking(executors.db_executor, client_gate.client_seen_cached, uid):
                return
            row = sessions.recorded_origin(uid, conversation_id)
            if row is None:
                row = await executors.run_blocking(
                    executors.db_executor,
                    conversations_db.get_conversation_raw_snapshot,
                    uid,
                    conversation_id,
                    field_paths=['started_at', 'finished_at', 'last_speech_at', 'source', 'discarded', 'deleted'],
                )
                if row:
                    sessions.remember_origin(uid, conversation_id, row)
            if not row:
                return
            recorded = recorded_span(row.get('started_at'), segments)
            if recorded is None:
                return  # An unplaced transcript proves no timeline boundary.
            if is_late(recorded, datetime.now(timezone.utc)):
                # Pusher and listen share this guard, so transport cannot turn
                # a delayed batch into an arrival-timed live occasion.
                row = dict(row, transcript_segments=list(segments), finished_at=recorded[1])
                from utils.episodes.finalize import schedule_synced_intake_attach

                schedule_synced_intake_attach(uid, conversation_id, row)
                return
        spoken = any(str(s.get('text') or '').strip() for s in segments)
        if conversation_id and spoken:
            first = sessions.first_moment(uid, conversation_id)
            if sessions.activity_due(uid, conversation_id):
                executors.start_background_task(
                    _attach_if_client_seen(
                        uid,
                        conversation_id,
                        source,
                        recorded[0] if recorded else datetime.now(timezone.utc),
                        first=first,
                        ended_at=recorded[1] if recorded else None,
                    ),
                    name='episode_attach',
                )
        moments = tracker.observe(
            uid, segments, conversation_id, source, **({'now': recorded[1].timestamp()} if recorded else {})
        )
        if not moments:
            return
        for moment in moments:
            executors.start_background_task(_moment_if_client_seen(uid, moment), name='episode_moment')
    except Exception as error:
        logger.warning('event=episode_live outcome=error exception_type=%s', type(error).__name__)


async def on_session_end(uid: str, conversation_id: Optional[str]) -> None:
    """Carry speech across reconnects, then flush it if the session is gone for good."""
    try:
        if not episodes_enabled_for(uid):
            return
        generation = tracker.mark_session_end(uid, conversation_id)
        if generation is not None and episode_carry_on_session_end_enabled():
            executors.start_background_task(
                _flush_session_end_after_timeout(uid, str(conversation_id), generation),
                name='episode_session_end_flush',
            )
    except Exception as error:
        logger.warning('event=episode_live outcome=session_end_error exception_type=%s', type(error).__name__)
