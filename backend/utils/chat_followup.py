"""Grounded closing question for a typed chat answer.

The on-device realtime voice lane already ends about two thirds of its answers
with a grounded question, and those sessions run roughly four turns. The typed
lanes end with a question 4-9% of the time, and recall answers ("what did X
say", "when did we...") never do, even though most of them have an obvious next
hop into the same source. This module is the typed lane's half of closing that
gap: the model appends one question after a delimiter on its own final line,
and the backend lifts it off the visible text into a structured
``followUp`` content block the clients render as one tappable chip.

The delimiter, not a heuristic, is what makes the tail separable. Guessing which
trailing sentence of a free-form answer was "the follow-up" would mis-fire on
answers that legitimately end in a question, and would leave the chip and the
prose saying the same thing twice.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# Chosen so it cannot occur in prose, Markdown, or code the model might quote.
FOLLOWUP_DELIMITER = '<<<FOLLOWUP>>>'
FOLLOWUP_BLOCK_TYPE = 'followUp'

# A chip has to read in one glance. The prompt asks for under ~15 words; these
# are the outer bounds a malformed generation cannot cross.
MAX_FOLLOWUP_WORDS = 18
MAX_FOLLOWUP_CHARS = 160

# A generic tail is worse than no tail: it teaches the user the chip is filler.
# Matched against the lowercased, punctuation-stripped question.
_GENERIC_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r'^anything else\b',
        r'^is there anything else\b',
        r'^(do you )?want (more|any more|additional|further) (detail|details|info|information|context)\b',
        r'^want me to (go on|continue|keep going|elaborate|explain more)\b',
        r'^(would you like|do you want) (me )?to (know more|hear more|continue|elaborate)\b',
        r'^(does|did) that (help|make sense|answer)\b',
        r'^(any|got any) (other )?questions\b',
        r'^let me know\b',
        r'^(can|could) i help\b',
        r'^(sound|sounds) good\b',
        r'^shall i (continue|go on)\b',
        r'^(need|want) anything else\b',
        r'^how can i help\b',
        r'^what else\??$',
    )
]

_WHITESPACE = re.compile(r'\s+')

# One chip carries one question. A tail that packs a second question, or a
# statement in front of the question, is a contract violation rather than a
# chip: the user would be shown several prompts on one tappable surface. The
# period arm only fires on a real sentence boundary (". W"), so decimals and
# lowercase abbreviations ("3.5", "10 a.m. standup") stay legal.
_INTERNAL_TERMINATOR = re.compile(r'[?!]|\.\s+["\'(\[]*[A-Z0-9]')

# A turn cut short mid-marker leaves residue like ``<<<`` or ``<<<FOLL``. One
# stray ``<`` is far more likely to be real text than marker residue, so the
# transcript keeps it; two or more is only ever the delimiter starting.
_MIN_MARKER_RESIDUE = 2


def _partial_delimiter_suffix_length(text: str, delimiter: str) -> int:
    """Length of the trailing run of ``text`` that could still become ``delimiter``."""
    for length in range(min(len(text), len(delimiter) - 1), 0, -1):
        if delimiter.startswith(text[len(text) - length :]):
            return length
    return 0


def strip_partial_followup_delimiter(text: str) -> str:
    """Drop a half-written delimiter left at the end of a cut-short answer."""
    held = _partial_delimiter_suffix_length(text, FOLLOWUP_DELIMITER)
    if held < _MIN_MARKER_RESIDUE:
        return text
    return text[: len(text) - held]


def _normalize_question(question: str) -> str:
    collapsed = _WHITESPACE.sub(' ', question).strip()
    return collapsed


def _is_generic(question: str) -> bool:
    probe = _normalize_question(question).lower().rstrip('?!. ')
    if not probe:
        return True
    return any(pattern.search(probe) for pattern in _GENERIC_PATTERNS)


def split_followup_tail(text: Optional[str]) -> Tuple[str, Optional[str]]:
    """Split a raw model answer into its visible text and its follow-up question.

    Returns ``(visible_text, question)``. ``question`` is ``None`` when the model
    emitted no tail, or emitted one that cannot be shown as a chip (empty, not a
    question, multi-sentence, over-long, or generic). The delimiter and anything
    after it are removed from ``visible_text`` either way — a half-formed tail
    must never leak into the transcript.
    """
    if not text:
        return '', None
    index = text.find(FOLLOWUP_DELIMITER)
    if index < 0:
        # A timed-out or cut-short turn can stop part-way through the marker.
        # A half-formed tail must never leak into the transcript either.
        return strip_partial_followup_delimiter(text), None
    visible = text[:index].rstrip()
    raw_tail = text[index + len(FOLLOWUP_DELIMITER) :]
    # Only the first line of the tail is the question; a model that keeps
    # writing after it has already left the contract.
    question = _normalize_question(raw_tail.split('\n', 1)[0])
    if not question:
        return visible, None
    if not question.endswith('?'):
        return visible, None
    if _INTERNAL_TERMINATOR.search(question[:-1]):
        return visible, None
    if len(question) > MAX_FOLLOWUP_CHARS or len(question.split()) > MAX_FOLLOWUP_WORDS:
        return visible, None
    if _is_generic(question):
        return visible, None
    return visible, question


def _answer_is_itself_a_question(visible_text: str) -> bool:
    """True when the answer already ends by asking the user something.

    A clarifying answer plus a chip asks two questions at once, and the chip is
    the one the user did not need.
    """
    for line in reversed(visible_text.strip().splitlines()):
        stripped = line.strip()
        if stripped:
            return stripped.endswith('?')
    return False


def build_followup_block(message_id: str, question: str) -> Dict[str, Any]:
    """The wire shape both shells render as one tappable chip."""
    return {
        'type': FOLLOWUP_BLOCK_TYPE,
        'id': f'{message_id}:followup',
        'text': question,
    }


def followup_content_blocks(
    message_id: str,
    question: Optional[str],
    *,
    visible_text: str,
    failed: bool,
) -> List[Dict[str, Any]]:
    """The ``content_blocks`` a finished assistant turn should carry.

    Empty for every turn that must not invite a next question: a failed,
    errored, or timed-out turn, an empty answer, or an answer that is itself a
    clarifying question.
    """
    if failed or not question:
        return []
    if not visible_text or not visible_text.strip():
        return []
    if _answer_is_itself_a_question(visible_text):
        return []
    return [build_followup_block(message_id, question)]


class FollowUpTailStreamFilter:
    """Withhold the follow-up tail from the token stream the user watches.

    The tail is model output like any other token, so it would otherwise stream
    into the visible answer and then be removed when the terminal frame lands —
    the chip's text flashing in the prose first. This filter buffers only the
    trailing characters that could still turn out to be the delimiter, so normal
    text is emitted with no added latency.
    """

    def __init__(self, delimiter: str = FOLLOWUP_DELIMITER) -> None:
        self._delimiter = delimiter
        self._pending = ''
        self._suppressing = False

    @property
    def suppressing(self) -> bool:
        """Whether the delimiter has been seen and the rest is being swallowed."""
        return self._suppressing

    def push(self, chunk: str) -> str:
        """Feed one streamed chunk; return the part safe to show now."""
        if self._suppressing:
            return ''
        buffer = self._pending + chunk
        index = buffer.find(self._delimiter)
        if index >= 0:
            self._suppressing = True
            self._pending = ''
            return buffer[:index]
        hold = _partial_delimiter_suffix_length(buffer, self._delimiter)
        if hold:
            self._pending = buffer[len(buffer) - hold :]
            return buffer[: len(buffer) - hold]
        self._pending = ''
        return buffer

    def flush(self) -> str:
        """Release anything still held once the stream ends without a tail."""
        if self._suppressing:
            self._pending = ''
            return ''
        remaining = self._pending
        self._pending = ''
        return remaining


FOLLOWUP_PROMPT_SECTION = f"""
<closing_question>
End a grounded answer with exactly one follow-up question, on its own final line, after the marker {FOLLOWUP_DELIMITER}.

Format (the marker and question are the last thing you write):
{FOLLOWUP_DELIMITER} <one question>

Rules for that question:
- Specific to what you just said or to the conversations/memories you cited. Never generic — never "anything else?", "want more detail?", "does that help?".
- Answerable by you from data you can reach (their recall, people, tasks, screen activity). Never a question only they could answer from outside Omi.
- Under 15 words, one sentence, ends with a question mark.
- For a recall answer, go one hop further into the same source: who else was there, what was decided next, when it is due, what happened after.

Write NO marker and NO question when:
- The turn failed, errored, timed out, or you are refusing or saying you cannot do something.
- You could not verify or find what was asked ("I don't have anything about that").
- The question was general knowledge rather than about this user.
- Your answer is itself a clarifying question back to the user.

The marker line is stripped from the visible answer and shown as a tappable chip, so never repeat the question in the answer text itself.
</closing_question>"""
