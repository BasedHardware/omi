"""What End answers once its cut is stored (reliability experiment ``end_open_conversation``).

Baseline: with a phone connected, ``POST /v1/conversations`` finds the listening session's own
recording, which in upload mode is empty, has nothing to process and answers with that recording,
still ``in_progress``. The app reads that as "the audio has not arrived" and says so, although with
the experiment on the open conversation has just been cut and its summary is starting.

With the experiment on and the cut stored, an answer that would be "this recording is still in
progress" is replaced by what actually happened:

* the open conversation the cut ends, shown as being summarised (``processing`` / ``writing``); or
* when no conversation has landed yet, the same body with ``X-Omi-End-Accepted: pending``: the cut is
  stored and the conversation is ended and summarised as soon as its audio lands.

Every other answer (the baseline path processed something, refused, or the cut was not stored) is
returned untouched. Off, nothing here runs.
"""

from datetime import datetime, timezone

from database import conversations_v3_live
from models.conversation import CreateConversationResponse
from models.conversation_enums import ConversationStatus
from utils.conversations.factory import deserialize_conversation
from utils.conversations.v3 import live

# ``conversation``: the body is the conversation this End closed. ``pending``: the End is stored and its
# conversation does not exist yet. Absent: the baseline answer, whatever it says.
ACCEPTED_HEADER = 'X-Omi-End-Accepted'


def _status(conversation) -> str | None:
    status = getattr(conversation, 'status', None)
    return getattr(status, 'value', status)


def unprocessed(baseline) -> bool:
    """Whether the baseline answered with a conversation it left in progress: it processed nothing."""
    conversation = getattr(baseline, 'conversation', None)
    return conversation is not None and _status(conversation) == ConversationStatus.in_progress.value


def ended_conversation(uid: str, live_conversation_id: str | None, *, now: datetime | None = None):
    """The open conversation the stored cut ends, as the app shows one being summarised; None when none landed."""
    now = now or datetime.now(timezone.utc)
    window = None
    if live_conversation_id:
        window = conversations_v3_live.live_window_by_id(uid, live_conversation_id, now=now)
    if window is None:
        window = conversations_v3_live.live_window(uid, now=now, max_idle=live.MAX_IDLE, pick=live.active)
    if window is None:
        return None
    conversation = deserialize_conversation(window)
    conversation.status = ConversationStatus.processing
    conversation.tile_state = 'writing'
    return CreateConversationResponse(conversation=conversation, messages=[])


def answer(uid: str, cut_id, baseline, live_conversation_id: str | None = None, *, response=None, now=None):
    """The End answer for a stored cut. ``baseline`` is what the request would have answered without it.

    Never raises: any fault while looking up the open conversation returns the baseline answer.
    """
    if not cut_id or not unprocessed(baseline):
        return baseline
    try:
        ended = ended_conversation(uid, live_conversation_id, now=now)
    except Exception:
        return baseline
    if response is not None:
        response.headers[ACCEPTED_HEADER] = 'conversation' if ended is not None else 'pending'
    return ended if ended is not None else baseline
