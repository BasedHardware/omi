"""Reliability experiments: candidate behaviour changes that stay off unless switched on.

Production's behaviour is the baseline. A proposed change to it lives in the same function it
changes, behind ``enabled('<name>', uid)``, and does nothing for an account until that account is
admitted. Each name is one rule in the Omi flag store (``kind: posthog`` rows in
``config/feature-flags.yaml``); the mobile app reads the same rule through ``GET /v1/flags``
(app/lib/services/experiments/reliability_flags.dart), so one rule switches both sides for an account:

    python scripts/omi_flags.py --project <project> set fast_end_feedback --active --allow <uid> --reason "..."

No rule, an inactive rule, an unreadable store or no account id all read as off.

``OMI_RELIABILITY_EXPERIMENTS`` is a development override for a local stack, where there is no flag
store: a comma list of names (or ``all``) that are on for every account. No deployed environment sets
it. It is read per call, so tests toggle it with monkeypatch.setenv.

The store is read through a resolver bound at process start (``utils.rollout_cohorts``), because this
module sits below ``utils``. On an event loop the resolver never reads the store inline: it answers
from what it last learned for that account and refreshes on a worker thread, so the first check for an
account in a process may read off for a moment. An async caller that must not miss that first check
calls ``await warm(uid)`` first.
"""

from __future__ import annotations

import os
from typing import Any, Awaitable, Callable

ENV = 'OMI_RELIABILITY_EXPERIMENTS'

# Flag store keys. The names double as the experiment names used at call sites.
RECEIPT_LONG_POLL_FLAG_KEY = 'receipt_long_poll'
RECEIPT_FINISHED_NOTE_FLAG_KEY = 'receipt_finished_note'
BATCH_FRAME_OUTCOMES_FLAG_KEY = 'batch_frame_outcomes'
END_OPEN_CONVERSATION_FLAG_KEY = 'end_open_conversation'
FAST_END_FEEDBACK_FLAG_KEY = 'fast_end_feedback'
END_BUTTON_BY_DEVICE_FLAG_KEY = 'end_button_by_device'
INSTANT_LIVE_TEXT_FLAG_KEY = 'instant_live_text'
COMMIT_WAKE_FLAG_KEY = 'commit_wake'
VENDOR_RECOGNIZER_ON_OPENED_APP_FLAG_KEY = 'vendor_recognizer_on_opened_app'
TITLE_AT_END_FLAG_KEY = 'title_at_end'
LIVE_WORDS_CASCADE_FLAG_KEY = 'live_words_cascade'

# name -> what turning it on changes. Register here before using a name.
EXPERIMENTS = {
    RECEIPT_LONG_POLL_FLAG_KEY: (
        'POST /v2/sync-local-files/receipts/wait exists: a client waits up to 20 s on several upload jobs and '
        'gets the finished ones together; a finished legacy job and a batch upload whose ledger just completed '
        'publish a wake. Off, the path is a 404 and nothing is published.'
    ),
    RECEIPT_FINISHED_NOTE_FLAG_KEY: (
        'With receipt_long_poll. A finished upload job also leaves a note in Redis for an hour, written before '
        'the wake. The receipts wait reads job state only for jobs that have a note (checked once when the '
        'request starts) or that a wake names, one job at a time, and answers an expired wait without reading '
        'anything; a noted job whose state is not final is returned as fallback. Jobs without a note are left to '
        'the client\'s paced status polls. Off, every start, wake and expiry of a wait re-reads every listed job.'
    ),
    BATCH_FRAME_OUTCOMES_FLAG_KEY: (
        'A completed batch upload that carried capture-evidence claims reports frame_outcomes_v1 in its status '
        'result: text or empty per source-frame range, no verdict for a held, failed or unattributable unit. '
        'Intake and projection record the two small inputs on the intake row. Off, nothing is written or added.'
    ),
    END_OPEN_CONVERSATION_FLAG_KEY: (
        'POST /v1/conversations (every way of ending) also stores an owner-level cut for a v3 owner, at the End '
        'time the app sent (X-Omi-Ended-At) when plausible, else at arrival, and wakes the builder at once; the live '
        'builder starts a new conversation at each cut, whichever recording carries the speech, and speech from '
        'before the cut that lands later joins the ended conversation. An End also closes the recording row to '
        'later audio: the batch projection reads the Ends around an uploaded unit\'s first speech '
        '(manual_cuts.ends_around, two one-row reads) and the attach step leaves alone a recording row that began '
        'on the other side of an End, so audio recorded after the End starts a new recording row and audio '
        'recorded before it still joins the old one. Off, End cuts only through the recording it finalizes or '
        'the last recording that already landed, later audio becomes its own conversation, and an uploaded unit '
        'joins the nearest recording row whatever Ends lie between. The conversation an End closed carries that '
        'End\'s instant (v3_manual_cut_at) and the conversation reads serve it, so the app can find the result of '
        'an End that was answered before its conversation existed; off, the field is never stamped.'
    ),
    FAST_END_FEEDBACK_FLAG_KEY: (
        'A v3 conversation is shown as done (tile_state) as soon as its summary is stored, before folder '
        'assignment, memory extraction and the other derived effects of the same pass; those still run and '
        'still settle the processing obligation. The builder also publishes a wake when it commits an ended '
        'conversation with its outline and when the summary shows, and GET /v1/conversations/{id}/summary/wait '
        'holds a request until the step asked for (until=outline or until=summary) and answers with the '
        'conversation. Off, the row stays writing until the whole pass ends, nothing is published and the '
        'path is a 404.'
    ),
    END_BUTTON_BY_DEVICE_FLAG_KEY: (
        'The live builder stamps an open v3 conversation with the app install behind its latest speech '
        '(v3_capture_device_id, copied from that recording\'s client_device_id) and GET /v1/conversations/live '
        'serves it to the owner, so the app can offer End on a conversation this phone feeds whatever its '
        'listening connection carries. Off, the field is neither written nor served.'
    ),
    INSTANT_LIVE_TEXT_FLAG_KEY: (
        'Two server parts of showing new speech at once. (1) A speech write whose grouping wake is refused '
        'because this minute\'s task name is already taken (the task ran, is running, or is scheduled later in '
        'the minute) also enqueues one follow-up task at the end of its 15 s slot, so the text is grouped '
        'within about 15 s instead of at the owner\'s next scheduled wake. (2) The open conversation carries '
        'v3_capture_device_id, as under end_button_by_device, so the app can show its own speech recognition '
        'under a conversation this phone feeds. Off, a refused wake enqueues nothing more. (3) A batch-only '
        'phone session whose audio arrives on the listen socket also streams it to Soniox from the moment the '
        'app reports its transcript on screen until it reports otherwise, with no dwell '
        '(routers/listen/watched_stream.py); the lines are sent to the phone only and never stored, so the '
        'record stays what batch makes of the audio. Off, a batch-only session opens no provider stream.'
    ),
    COMMIT_WAKE_FLAG_KEY: (
        'A GPU worker that commits a result to an owner\'s log tells the serving backend at once which owner it '
        'was (POST /v2/batch-pipeline/commit-wake, owner ids only, over the worker\'s existing OIDC channel), and '
        'the backend walks that owner\'s log and writes the result into the conversation without waiting for the '
        'next serving sweep (10 s tick). The wake is a hint held in memory: a lost one is found by the sweep as '
        'before, and every fence of the projection is unchanged. Off, the worker sends nothing and the endpoint '
        'accepts nothing.'
    ),
    VENDOR_RECOGNIZER_ON_OPENED_APP_FLAG_KEY: (
        'WebSocket /v4/live-words exists (routers/listen/live_words.py): while the phone app is in front and '
        'capturing, it sends a copy of the audio there, the audio goes to Soniox and the words come back as '
        'lines for display, timed in seconds of audio from the connection\'s first frame. Nothing is stored, no '
        'text is logged, no conversation, recording row or plan allowance is touched; one connection per account '
        'and app install. Silence keeps the connection: after 20 s without audio only the provider stream is '
        'closed and the next audio dials a new one, and the connection itself closes after 10 minutes without '
        'audio. The page-only stream of instant_live_text part 3 '
        '(watched_stream.admitted) answers no while this is on, so one phone never has two provider streams. '
        'The open conversation also carries v3_capture_device_id, as under end_button_by_device, so the app can '
        'show the merged live words under a conversation this phone feeds. Off, the endpoint refuses every '
        'connection.'
    ),
    TITLE_AT_END_FLAG_KEY: (
        'An open conversation is not named before it ends: the live-title step (one model call once an open '
        'conversation holds three minutes of speech) is skipped, nothing is claimed or written for it, and the '
        'conversation gets its title from the outline when it ends. A title already published on an open row is '
        'left as it is. Off, CONVERSATIONS_V3_LIVE_TITLE alone decides, as on main.'
    ),
    LIVE_WORDS_CASCADE_FLAG_KEY: (
        'Needs vendor_recognizer_on_opened_app, and end_open_conversation for parts 2 and 3 (the tail is kept '
        'with the End that experiment stores). (1) /v4/live-words accepts a text message {"type":"end"} and '
        'starts a new line at that point of the audio, so one display line never spans a user End. (2) POST '
        '/v1/conversations accepts live_tail: the live words the phone was showing for the '
        'conversation being ended (words with times, plain text, at most 600 words and 6,000 characters, checked '
        'and bounded on arrival). It is kept, encrypted, with the stored End (end_open_conversation) and nowhere '
        'else: never in a conversation, a recording row or the transcript. (3) When the conversation that End '
        'closed is summarised, the notes prompt gets the stored transcript plus the tail words no stored line '
        'covers in time, and the number of tail words used is stamped on the conversation before the notes are '
        'written (v3_summary_tail_words); the late-speech rewrite rule counts new stored words only beyond that '
        'number, and a summary pass still running when such speech lands settles instead of starting again '
        '(v3_tail_absorbed), so batch landing the same speech does not write a second summary. This is a deliberate, bounded '
        'exception to "client-authored text is display only": phone-authored words reach the summary prompt, '
        'and only there. Off, the message is ignored, live_tail is dropped unread, nothing is stored and the '
        'summary and the rewrite rule are the baseline.'
    ),
}


_resolver: Callable[[str, str], bool] | None = None
_warmer: Callable[[str], Awaitable[Any]] | None = None


def configure_resolver(
    resolver: Callable[[str, str], bool] | None, warmer: Callable[[str], Awaitable[Any]] | None = None
) -> None:
    """Bind the flag store read: ``resolver(key, uid)`` answers whether the rule admits the account."""
    global _resolver, _warmer
    _resolver, _warmer = resolver, warmer


def selected() -> frozenset[str]:
    return frozenset(item.strip() for item in os.getenv(ENV, '').split(',') if item.strip())


def _check(name: str) -> None:
    if name not in EXPERIMENTS:
        raise KeyError(f'unregistered reliability experiment: {name}')


def enabled(name: str, uid: str | None = None) -> bool:
    """True when ``name`` is on for ``uid``: its flag store rule admits the account, or the local override names it."""
    _check(name)
    names = selected()
    if name in names or 'all' in names:
        return True
    if not uid or _resolver is None:
        return False
    try:
        return _resolver(name, uid) is True
    except Exception:
        return False  # A switch never fails the path it guards.


def any_enabled(uid: str | None, *names: str) -> bool:
    """True when at least one of several registered experiments that share a code path is on for ``uid``."""
    return any([enabled(name, uid) for name in names])


async def warm(uid: str | None) -> None:
    """Learn the account's rules off the event loop, so the checks that follow do not miss a first read."""
    if uid and _warmer is not None and 'all' not in selected():
        try:
            await _warmer(uid)
        except Exception:
            pass


def unknown() -> frozenset[str]:
    """Selected names that no code reads: a typo would otherwise silently test the baseline."""
    return selected() - set(EXPERIMENTS) - {'all'}
