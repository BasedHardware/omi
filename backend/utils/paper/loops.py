"""Open Loops — questions you raised and never answered.

Omi already surfaces a day's unresolved questions. What it does not do is carry them
across days: a question asked on Monday is gone by Tuesday's summary, even though nobody
answered it. Aging those questions is the block, and the age is the editorial judgment —
the thing you have been avoiding longest is the thing worth printing.
"""

from datetime import date

from models.paper import OpenLoop

from .text import days_between, overlap

# A later decision or nugget must cover this fraction of a question's content words
# before we treat the question as answered.
RESOLVED_THRESHOLD = 0.6

# Two questions this similar are the same question asked twice; keep the earlier one so
# the age reflects when it was first raised.
DUPLICATE_THRESHOLD = 0.7

# Nothing under a day old is a loop — it is just today.
MIN_AGE_DAYS = 1


def _resolutions_after(summaries: list[dict], raised_on: str) -> list[str]:
    """Every decision and nugget recorded strictly after ``raised_on``."""
    out: list[str] = []
    for summary in summaries:
        if str(summary.get('date') or '') <= raised_on:
            continue
        for decision in summary.get('decisions_made') or []:
            text = (decision or {}).get('decision')
            if text:
                out.append(text)
        for nugget in summary.get('knowledge_nuggets') or []:
            text = (nugget or {}).get('insight')
            if text:
                out.append(text)
    return out


def find_open_loops(summaries: list[dict], today: date, limit: int = 3) -> list[OpenLoop]:
    """Questions still unanswered, oldest first.

    ``summaries`` is the stored daily-summary window in any order. A question is dropped
    when a later day's decision or knowledge nugget covers it, and deduped against
    questions already carried so re-asking does not reset the clock.
    """
    ordered = sorted(summaries, key=lambda s: str(s.get('date') or ''))

    carried: list[OpenLoop] = []
    for summary in ordered:
        raised_on = str(summary.get('date') or '')
        if not raised_on:
            continue

        resolutions = _resolutions_after(ordered, raised_on)
        for entry in summary.get('unresolved_questions') or []:
            question = ((entry or {}).get('question') or '').strip()
            if not question:
                continue
            if any(overlap(question, answer) >= RESOLVED_THRESHOLD for answer in resolutions):
                continue
            if any(overlap(question, seen.question) >= DUPLICATE_THRESHOLD for seen in carried):
                continue
            carried.append(
                OpenLoop(
                    question=question,
                    first_raised=raised_on,
                    days_open=days_between(raised_on, today),
                )
            )

    aged = [loop for loop in carried if loop.days_open >= MIN_AGE_DAYS]
    aged.sort(key=lambda loop: (-loop.days_open, loop.first_raised))
    return aged[:limit]
