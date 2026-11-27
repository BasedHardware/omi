"""The live words a phone was showing when its user ended a conversation (reliability experiment
``live_words_cascade``, which needs ``vendor_recognizer_on_opened_app``).

Baseline: a user End closes the conversation at the End instant and its summary starts at once, from
the text stored so far. The last seconds before the End are still on the phone or in transcription, so
the first summary misses them, and the one-time rewrite rule writes a second summary when they land.

With the experiment on, the End request carries ``live_tail``: the words the phone's live-words layer
was showing for that conversation (its own recogniser's and the display stream's, by the cascade's
priority), with their times on the phone's capture clock. This module is everything the server does
with them:

* ``accept`` checks and bounds the payload on arrival (plain words, sane times, size caps);
* the result is kept, encrypted, with the stored End (``database/conversations_v3_manual_cuts``) and
  nowhere else. It is never written to a conversation, a recording row or the transcript;
* when the conversation that End closed is summarised, ``for_conversation`` drops every word a stored
  line already covers in time and ``in_prompt`` adds what is left to the notes prompt, after the
  transcript, marked as a draft;
* the number of those words the summary used, and when the first of them was spoken, are stamped on
  the conversation. The grouping pass takes stored words that land in that stretch to be the same
  speech (``rewrite_words``), so batch landing it does not write a second summary, while a landing
  that brings substantially more, or speech from before that stretch, still counts in full.

TRUST: this is a deliberate exception to the rule that client-authored text is display only
(``tests/unit/test_client_processing_trust_boundary.py`` proves that rule for ``client_processing``,
and stays as it is). Phone-authored words reach one model call, the notes prompt of the conversation
their End closed, so what those notes say (title, summary, the action items they propose) can
reflect them, and so can whatever reads the notes afterwards. The bounds: on only under the
experiment, at most ``MAX_WORDS`` words and ``MAX_CHARS`` characters, plain text with control
characters removed, only words timed inside the ended conversation and before the End, dropped where
stored text exists, never stored in the transcript, never read directly by anything but that prompt
(the discard and wake-word checks, memory extraction and search read the stored transcript), and
removed from the stored End once nothing of it is left uncovered or the End is a day old.

Off, nothing here runs: the field is dropped unread, nothing is stored, the prompt and the rewrite rule
are the baseline.
"""

import json
import logging
import math
import re
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone

from config import reliability_experiments
from database import conversations_v3_manual_cuts as cuts_db
from utils.conversations.v3.word_floor import text_word_count

logger = logging.getLogger(__name__)

EXPERIMENT = reliability_experiments.LIVE_WORDS_CASCADE_FLAG_KEY
BASE_EXPERIMENT = reliability_experiments.VENDOR_RECOGNIZER_ON_OPENED_APP_FLAG_KEY

VERSION = 1
MAX_WORDS = 600
MAX_CHARS = 6000
MAX_LINES = 200
MAX_ENTRY_CHARS = 600
# The raw field is refused unread above this many characters of JSON (a full payload is about 40 kB).
MAX_RAW_CHARS = 120_000
# A word is taken as "already stored" when its middle lies within this much of a stored line.
COVER_PAD = timedelta(seconds=2)
# Words older than this before the End are not part of what the phone could have been showing.
MAX_AGE = timedelta(hours=6)
# The rewrite rule looks back one day (planner.late_rewrite); the stored words are not kept longer.
KEEP = timedelta(days=1)
# On the conversation: how many tail words its last summary used and batch has not yet landed.
CREDIT_FIELD = 'v3_summary_tail_words'
# Two recognisers count the same speech a few words apart: a credit this small is spent.
SPENT_CREDIT = 5

# Control characters, and the brackets the prompt's own markers are written with: a recogniser emits
# neither, and without them a word cannot pose as a transcript marker or a section of the prompt.
_CONTROL = re.compile(r'[\x00-\x1f\x7f\[\]{}<>|`]')
_SPACE = re.compile(r'\s+')

PROMPT_HEADING = (
    '[Live draft of the most recent speech in this conversation. These words are not in the transcript '
    'above yet: they were heard by a faster, less exact recogniser on the phone, in order, without speaker '
    'labels. Treat them as what was said next; individual words may be mis-heard.]'
)


def enabled(uid) -> bool:
    """On for this account: its own rule and the display stream's rule both admit it."""
    return reliability_experiments.enabled(EXPERIMENT, uid) and reliability_experiments.enabled(BASE_EXPERIMENT, uid)


def _plain(text, limit) -> str:
    return _SPACE.sub(' ', _CONTROL.sub(' ', text)).strip()[:limit]


def accept(raw, *, cut_at: datetime, uid) -> list[list[list]] | None:
    """The payload as bounded lines of ``[text, start, end]`` (epoch seconds), or None.

    Never raises. Anything malformed is dropped piece by piece; the newest words are kept when the
    payload exceeds the caps, as the phone does. Words that start at or after the End, or implausibly
    long before it, are dropped: the tail is by definition speech before the End.
    """
    try:
        return _accept(raw, cut_at, uid)
    except Exception as error:  # A hostile or broken payload costs the tail, never the End.
        logger.warning('event=v3_live_tail outcome=refused exception_type=%s', type(error).__name__)
        return None


def _accept(raw, cut_at: datetime, uid) -> list[list[list]] | None:
    if not enabled(uid) or not isinstance(raw, dict) or raw.get('v') != VERSION:
        return None
    lines = raw.get('lines')
    if not isinstance(lines, list):
        return None
    try:
        if len(json.dumps(lines)) > MAX_RAW_CHARS:
            return None
    except (TypeError, ValueError):
        return None
    cut = cut_at.timestamp()
    oldest = cut - MAX_AGE.total_seconds()
    kept: list[list[list]] = []
    words = chars = 0
    for line in reversed(lines[-MAX_LINES:]):
        if not isinstance(line, list):
            continue
        entries: list[list] = []
        full = False
        for entry in reversed(line):
            if not isinstance(entry, list) or len(entry) != 3:
                continue
            text, start, end = entry
            if not isinstance(text, str) or isinstance(start, bool) or isinstance(end, bool):
                continue
            if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
                continue
            if not math.isfinite(start) or not math.isfinite(end) or not oldest <= start < cut:
                continue
            text = _plain(text, MAX_ENTRY_CHARS)
            count = text_word_count(text)
            if not count:
                continue
            if words + count > MAX_WORDS or chars + len(text) > MAX_CHARS:
                full = True
                break
            words += count
            chars += len(text)
            entries.append([text, round(float(start), 3), round(min(max(float(end), start), start + 60.0), 3)])
        if entries:
            kept.append(entries[::-1])
        if full:
            break
    kept.reverse()
    kept.sort(key=lambda line: line[0][1])
    return kept or None


def word_count(lines) -> int:
    return sum(text_word_count(entry[0]) for line in lines or () for entry in line)


def uncovered(lines, row) -> list[list[list]]:
    """``lines`` without the words stored text of ``row`` already covers, and without words from outside it.

    Stored lines are timed in seconds from the conversation's start; tail words carry the phone's capture
    time, the same clock that stamps its recordings. A word counts as stored when its middle lies within
    ``COVER_PAD`` of a stored line, and as foreign when it starts more than that before the conversation.
    """
    started = row.get('started_at')
    if not isinstance(started, datetime):
        return []
    origin = (started if started.tzinfo else started.replace(tzinfo=timezone.utc)).timestamp()
    pad = COVER_PAD.total_seconds()
    spans = []
    for segment in row.get('transcript_segments') or []:
        start, end = segment.get('start'), segment.get('end')
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            continue
        if not str(segment.get('text') or '').strip():
            continue
        spans.append((origin + start - pad, origin + max(end, start) + pad))
    spans.sort()
    merged: list[tuple[float, float]] = []
    for span in spans:
        if merged and span[0] <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], span[1]))
        else:
            merged.append(span)

    def stored(at) -> bool:
        low, high = 0, len(merged)
        while low < high:
            mid = (low + high) // 2
            if merged[mid][1] < at:
                low = mid + 1
            else:
                high = mid
        return low < len(merged) and merged[low][0] <= at

    out = []
    for line in lines or ():
        rest = [e for e in line if e[1] >= origin - pad and not stored((e[1] + e[2]) / 2)]
        if rest:
            out.append(rest)
    return out


def text(lines) -> str:
    """The words as plain lines, in order; empty when there are none."""
    return '\n'.join(' '.join(entry[0] for entry in line) for line in lines or () if line)


def for_conversation(uid, row, *, now=None) -> tuple[str, int | None, datetime | None]:
    """What the summary of ``row`` gets from the tail of the End that closed it: (text, words, since).

    ``since`` is when the first of those words was spoken: stored speech from that moment on is the
    speech the summary read as tail. ('', None, None) when the experiment is off or no End closed this
    conversation: nothing is read and nothing is to be recorded. ('', 0, None) when that End carried no
    words or stored text covers them all. Reads the one stored End; removes its words once none is left
    uncovered or the End is older than ``KEEP``. Never raises: on any fault the summary is the baseline.
    """
    if not enabled(uid):
        return '', None, None
    cut_at = row.get('v3_manual_cut_at')
    if not isinstance(cut_at, datetime):
        return '', None, None
    try:
        lines = cuts_db.tail(uid, cut_at)
        if not lines:
            return '', 0, None
        now = now or datetime.now(timezone.utc)
        cut = cut_at if cut_at.tzinfo else cut_at.replace(tzinfo=timezone.utc)
        left = [] if now - cut > KEEP else uncovered(lines, row)
        if not left:
            cuts_db.clear_tail(uid, cut_at)
            logger.info('event=v3_live_tail outcome=covered tail_words=%d', word_count(lines))
            return '', 0, None
        used = word_count(left)
        since = datetime.fromtimestamp(min(entry[1] for line in left for entry in line), timezone.utc)
        # Counts only: the words themselves are never logged.
        logger.info(
            'event=v3_live_tail outcome=used tail_words=%d used_words=%d stored_lines=%d',
            word_count(lines),
            used,
            len(row.get('transcript_segments') or []),
        )
        return text(left), used, since
    except Exception as error:
        logger.warning('event=v3_live_tail outcome=error exception_type=%s', type(error).__name__)
        return '', 0, None


# --- the notes prompt -----------------------------------------------------------------------------

_for_summary: ContextVar[str | None] = ContextVar('v3_live_tail', default=None)


@contextmanager
def summarising(tail_text: str):
    """While one conversation's notes are written, ``in_prompt`` appends its tail; '' appends nothing."""
    token = _for_summary.set(tail_text or None)
    try:
        yield
    finally:
        _for_summary.reset(token)


def in_prompt(transcript: str) -> str:
    """The transcript a notes prompt reads, with the draft tail after it. Unchanged outside ``summarising``."""
    tail_text = _for_summary.get()
    if not tail_text:
        return transcript
    return f'{transcript}\n\n{PROMPT_HEADING}\n{tail_text}'


# --- the rewrite rule -----------------------------------------------------------------------------


SINCE_FIELD = 'v3_summary_tail_since'


def _words_from(conversation, since: datetime) -> int:
    """Stored words of ``conversation`` spoken at or after ``since`` (less the coverage reach)."""
    started = conversation.get('started_at')
    if not isinstance(started, datetime):
        return 0
    origin = started if started.tzinfo else started.replace(tzinfo=timezone.utc)
    floor = (since if since.tzinfo else since.replace(tzinfo=timezone.utc)) - COVER_PAD
    count = 0
    for segment in conversation.get('transcript_segments') or []:
        start = segment.get('start')
        if isinstance(start, (int, float)) and origin + timedelta(seconds=start) >= floor:
            count += text_word_count(segment.get('text') or '')
    return count


def rewrite_words(prior, row, new_words: int, uid) -> tuple[int, int]:
    """New stored words the last summary has not seen, and the credit left: (words, credit).

    ``prior`` is the stored conversation and ``row`` the same conversation as this pass builds it. The
    credit is the number of tail words the summary read; only stored words that landed in the stretch
    the tail covered (from ``v3_summary_tail_since`` on) are taken to be that same speech. Speech from
    before it that lands late counts in full, as it always did. With no credit (always, when the
    experiment is off) the count is unchanged.
    """
    credit = int((prior or {}).get(CREDIT_FIELD) or 0)
    if credit <= 0 or not enabled(uid):
        return new_words, credit
    in_tail = new_words
    since = prior.get(SINCE_FIELD)
    if isinstance(since, datetime):
        in_tail = max(0, _words_from(row, since) - _words_from(prior, since))
    seen = min(credit, in_tail, new_words)
    return new_words - seen, credit - seen


ABSORBED_FIELD = 'v3_tail_absorbed'


def mark_absorbed(row, prior, unseen_words: int) -> None:
    """Record on ``row`` that this landing brought only speech the notes had read as tail, or that it did not.

    ``{from, to}``: the content revisions that differ only by such landings. The summary pass's settle
    (``database/conversations_v3_processing.settle_processing``) accepts a conversation that changed under
    it when the revision it read lies in that range and ``to`` is the current one.
    """
    before, after = prior.get('sync_content_revision'), row.get('sync_content_revision')
    if unseen_words > 0 or not isinstance(before, int) or not isinstance(after, int):
        row.pop(ABSORBED_FIELD, None)
        return
    mark = prior.get(ABSORBED_FIELD)
    chained = isinstance(mark, dict) and mark.get('to') == before and isinstance(mark.get('from'), int)
    row[ABSORBED_FIELD] = {'from': mark['from'] if chained else before, 'to': after}


# --- letting go of the stored words ---------------------------------------------------------------


def forget(uid, cut_at) -> None:
    """Remove the stored words of the End at ``cut_at``. Never raises."""
    if not isinstance(cut_at, datetime):
        return
    try:
        cuts_db.clear_tail(uid, cut_at)
        logger.info('event=v3_live_tail outcome=forgotten')
    except Exception as error:
        logger.warning('event=v3_live_tail outcome=forget_error exception_type=%s', type(error).__name__)


def forget_old(uid, now) -> None:
    """Remove the stored words of this owner's recent Ends older than ``KEEP``. Never raises.

    Called when a new End with a tail is stored, so an owner's old tails go at their next End even when no
    summary pass read them again. One small read, only with the experiment on.
    """
    try:
        cleared = cuts_db.clear_tails_before(uid, now - KEEP)
        if cleared:
            logger.info('event=v3_live_tail outcome=expired count=%d', cleared)
    except Exception as error:
        logger.warning('event=v3_live_tail outcome=expire_error exception_type=%s', type(error).__name__)
