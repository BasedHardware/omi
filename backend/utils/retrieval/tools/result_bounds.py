"""Shared size bounds for agentic retrieval tool results.

A chat tool that formats every matched row into one string can flood the model's context when
a broad query matches a huge set ("what do you know about me" pulls every memory; "analyze my
last 30 days" pulls every conversation). The oversized tool result then makes the model freeze
or refuse with "that's quite a bit of information to process at once" (issue #4927). These
helpers cap the row count and the raw character size, and append a note telling the model to
summarize what it has and offer to narrow.
"""

from typing import List, Optional, Tuple, TypeVar

from utils.model_text import truncation_note

T = TypeVar("T")

MAX_RESULT_CHARS = 60000


def cap_items_for_llm(items: Optional[List[T]], max_items: int) -> Tuple[List[T], int, bool]:
    """Keep at most ``max_items`` rows for the chat model.

    Callers pass rows in their chosen order, so this keeps a prefix without inferring relevance.
    Returns ``(capped_list, total_found, truncated)`` where ``truncated`` is True when some rows
    were dropped.
    """
    safe_items: List[T] = list(items) if items is not None else []
    total_found = len(safe_items)
    try:
        limit = max(0, int(max_items))
    except (TypeError, ValueError):
        limit = 0

    if total_found > limit:
        return safe_items[:limit], total_found, True
    return safe_items, total_found, False


def bounded_result(
    result: Optional[str],
    truncated: bool,
    noun: str = "results",
    *,
    order: Optional[str] = None,
    shown: Optional[int] = None,
) -> str:
    """Apply a hard character budget and, when the set was truncated, append a note telling the
    model to summarize what it has and to offer to narrow, so it answers instead of freezing.

    The note deliberately does not state a total count: callers may pass an already-paginated
    page whose length is not the true total, so claiming a total would mislead (cubic on #8527).
    """
    safe_result: str = "" if result is None else str(result)
    safe_noun: str = str(noun) if noun is not None else "results"

    if len(safe_result) > MAX_RESULT_CHARS:
        safe_result = safe_result[:MAX_RESULT_CHARS]
        truncated = True
    if truncated:
        # Generic callers may not know the row count, so report the number of rendered lines.
        # Callers that do know how many records survived the cap should pass that count.
        shown_count = shown if shown is not None else len(safe_result.splitlines())
        unit = safe_noun if shown is not None else "result lines"
        next_step = "Ask for a narrower topic or date range, or page with the offset, for the rest."
        if order:
            next_step = f"Rows are ordered {order}. {next_step}"
        note = truncation_note(
            shown=shown_count,
            total=None,
            unit=unit,
            how_to_get_more=next_step,
            cut=True,
        )
        if order is None:
            note = note.replace(
                "more were omitted, not absent.", "more may exist; omitted data is not evidence of absence."
            )
        safe_result += "\n\n" + note
    return safe_result
