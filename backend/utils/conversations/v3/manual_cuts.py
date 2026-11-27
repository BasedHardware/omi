"""End the v3 conversation in progress at an instant (reliability experiment ``end_open_conversation``).

Baseline: End and the pendant double-tap finalize the recording the listen
socket owns, and the builder cuts at that recording's end. On the mobile batch
route the speech travels as uploaded files, the socket recording is empty or
handed to batch without the manual-end mark, and the conversation stays open.

With the experiment on, the same request also stores an owner-level cut and
wakes the builder at once, whatever the state of the listening session's own
recording. The cut is the End time the app sent (the clock that stamps its
recordings) when that is plausible, else the time the request arrived. Speech
that starts at or after the cut opens a new conversation whichever recording
carries it; speech from before the cut that lands later joins the ended
conversation (``planner.Ownership``) and the ordinary late-speech rule decides
whether its summary is rewritten. Off, nothing is written or read.
"""

import logging
from datetime import datetime, timedelta, timezone

from config import reliability_experiments
from config.conversations_v3 import conversations_v3_enabled, v3_intake_held_out
from database import conversations_v3_manual_cuts as cuts_db
from utils.conversations.v3 import live_tail as tail_lines
from utils.conversations.v3 import triggers
from utils.conversations.v3.end_sides import ATTACH_KEY

__all__ = ['ATTACH_KEY']  # Re-exported: the batch projection names the key through this module.

logger = logging.getLogger(__name__)

EXPERIMENT = 'end_open_conversation'
# Experiment fast_end_feedback: a builder pass that loses a race (speech landed while it worked) commits
# nothing and is otherwise retried at the owner's next minute wake, so an End pressed mid-speech could
# take a minute to show. These extra wakes shortly after End apply the stored cut sooner; a wake that
# finds the first pass still running, or nothing left to do, returns at once.
RETRY_EXPERIMENT = 'fast_end_feedback'
RETRY_WAKES_SECONDS = (15, 35)


def enabled(uid: str | None) -> bool:
    return reliability_experiments.enabled(EXPERIMENT, uid)


# The app sends its End time here, as seconds since the epoch; only this experiment reads it.
ENDED_AT_HEADER = 'X-Omi-Ended-At'


def parse_ended_at(value):
    """The header as a UTC instant, or None when absent or malformed."""
    try:
        return datetime.fromtimestamp(float(value), timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


# The cut is compared with speech times, which the phone's clock stamps, so the phone's own End time is the
# right instant when it is plausible: not ahead of the server, and no older than a slow or retried request.
ENDED_AT_MAX_AHEAD = timedelta(seconds=5)
ENDED_AT_MAX_BEHIND = timedelta(minutes=10)


def cut_instant(ended_at, now) -> datetime:
    """The client's End time when it is within bounds of the server clock, else the server's arrival time."""
    if not isinstance(ended_at, datetime):
        return now
    at = ended_at if ended_at.tzinfo else ended_at.replace(tzinfo=timezone.utc)
    return at if now - ENDED_AT_MAX_BEHIND <= at <= now + ENDED_AT_MAX_AHEAD else now


def record_end(uid, *, ended_at=None, now=None, live_tail=None):
    """Store the cut for an admitted owner and return its id; None when off, not admitted or on any fault.

    Never raises: End keeps its baseline path. Does not wake the builder: the caller does, once it
    knows whether the baseline path already woke it for this End (two wakes at once collide).

    Reliability experiment ``live_words_cascade``: ``live_tail`` is the raw request field with the live
    words the phone was showing for the conversation being ended. It is checked, bounded and kept with
    the cut for that conversation's summary; a malformed one is dropped and the End is stored without
    it. Off (or None), the cut is stored exactly as before.
    """
    if not enabled(uid):
        return None
    try:
        # A held-out owner keeps experiment-off End handling, paired with mark_new (SCA-2918).
        if not conversations_v3_enabled(uid) or v3_intake_held_out(uid):
            return None
        at = cut_instant(ended_at, now or datetime.now(timezone.utc))
        tail = tail_lines.accept(live_tail, cut_at=at, uid=uid) if live_tail is not None else None
        if tail:
            try:
                words = tail_lines.word_count(tail)
                cut_id = cuts_db.record(uid, at, tail=tail, tail_words=words)
            except Exception as error:
                # The words could not be kept (encryption, size): the End is stored without them, below.
                logger.warning('event=v3_manual_cut outcome=tail_error exception_type=%s', type(error).__name__)
            else:
                # The stored words of this owner's Ends from more than a day ago go now.
                tail_lines.forget_old(uid, at)
                # Counts only: the words themselves are never logged.
                logger.info('event=v3_manual_cut outcome=recorded tail_words=%d tail_lines=%d', words, len(tail))
                return cut_id
        cut_id = cuts_db.record(uid, at)
        logger.info('event=v3_manual_cut outcome=recorded')
        return cut_id
    except Exception as error:
        logger.warning('event=v3_manual_cut outcome=error exception_type=%s', type(error).__name__)
        return None


def wake(uid, cut_id, *, now=None) -> bool:
    """Wake the builder for a stored cut, at once. Never raises."""
    if not cut_id:
        return False
    try:
        triggers.enqueue(uid, manual_end_id=cut_id)
        if reliability_experiments.enabled(RETRY_EXPERIMENT, uid):
            at = now or datetime.now(timezone.utc)
            for index, delay in enumerate(RETRY_WAKES_SECONDS, 1):
                triggers.enqueue(uid, at=at + timedelta(seconds=delay), manual_end_id=f'{cut_id}:retry{index}')
        return True
    except Exception as error:
        logger.warning('event=v3_manual_cut outcome=wake_error exception_type=%s', type(error).__name__)
        return False


def request_end(uid, *, ended_at=None, now=None) -> bool:
    """Record a cut and wake the builder. Never raises: End keeps its baseline path."""
    cut_id = record_end(uid, ended_at=ended_at, now=now)
    if cut_id is None:
        return False
    wake(uid, cut_id, now=cut_instant(ended_at, now or datetime.now(timezone.utc)))
    return True


def ends_around(uid, incoming, *, firestore_client=None):
    """The last End at or before an uploaded unit's first speech and the first End after it.

    The attach step uses the pair to keep a recording row on one side of every End: a unit may join a
    row only when no End lies between the row's start and the unit's first speech, so audio recorded
    after an End starts a new recording row and audio recorded before it that lands late still joins
    the row it belongs to. None when the experiment is off, the owner is not on v3, the unit has no
    timed speech, there is no End on either side, or on any fault: the attach step then behaves as before.
    """
    if not enabled(uid):
        return None
    try:
        # A held-out owner keeps experiment-off End handling, paired with mark_new (SCA-2918).
        if not conversations_v3_enabled(uid) or v3_intake_held_out(uid):
            return None
        started = incoming.get('started_at')
        starts = [s.get('start') for s in incoming.get('transcript_segments') or [] if isinstance(s, dict)]
        starts = [float(s) for s in starts if isinstance(s, (int, float))]
        if not isinstance(started, datetime) or not starts:
            return None
        at = (started if started.tzinfo else started.replace(tzinfo=timezone.utc)) + timedelta(seconds=min(starts))
        before, after = cuts_db.around(uid, at, firestore_client=firestore_client)
        return (before, after) if before is not None or after is not None else None
    except Exception as error:
        logger.warning('event=v3_manual_cut outcome=attach_read_error exception_type=%s', type(error).__name__)
        return None


def load(uid, recordings) -> list[datetime]:
    """Cuts inside the span of the loaded recordings; empty when the experiment is off."""
    if not enabled(uid):
        return []
    starts = [r.get('started_at') or r.get('recorded_start') for r in recordings]
    starts = [s if s.tzinfo else s.replace(tzinfo=timezone.utc) for s in starts if isinstance(s, datetime)]
    if not starts:
        return []
    return cuts_db.load(uid, min(starts))
