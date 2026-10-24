"""Shared size bounds for agentic retrieval tool results.

A chat tool that formats every matched row into one string can flood the model's context when
a broad query matches a huge set ("what do you know about me" pulls every memory; "analyze my
last 30 days" pulls every conversation). The oversized tool result then makes the model freeze
or refuse with "that's quite a bit of information to process at once" (issue #4927). These
helpers cap the row count and the raw character size, and append a note telling the model to
summarize what it has and offer to narrow.
"""

from typing import List, Tuple, TypeVar

try:
    from utils.model_text import truncation_note
except ModuleNotFoundError:
    import importlib.util as _importlib_util
    from pathlib import Path as _Path
    import sys as _sys

    _mt_spec = _importlib_util.spec_from_file_location(
        "utils.model_text",
        str(_Path(__file__).resolve().parents[2] / "model_text.py"),
    )
    assert _mt_spec is not None and _mt_spec.loader is not None
    _mt_mod = _importlib_util.module_from_spec(_mt_spec)
    # Register before exec: model_text's dataclasses resolve their string
    # annotations through sys.modules[cls.__module__], which is None otherwise.
    _sys.modules[_mt_spec.name] = _mt_mod
    _mt_spec.loader.exec_module(_mt_mod)
    truncation_note = _mt_mod.truncation_note

T = TypeVar("T")

MAX_RESULT_CHARS = 60000


def cap_items_for_llm(items: List[T] | None, max_items: int) -> Tuple[List[T], int, bool]:
    """Keep at most ``max_items`` rows for the chat model.

    Callers pass rows in their chosen order, so this keeps a prefix without inferring relevance.
    Returns ``(capped_list, total_found, truncated)`` where ``truncated`` is True when some rows
    were dropped.
    """
    if items is None:
        return [], 0, False
    items_list = list(items)
    total_found = len(items_list)
    if max_items <= 0:
        return [], total_found, total_found > 0
    if total_found > max_items:
        return items_list[:max_items], total_found, True
    return items_list, total_found, False


def bounded_result(
    result: object,
    truncated: bool,
    noun: str = "results",
    *,
    order: str | None = None,
    shown: int | None = None,
) -> str:
    """Apply a hard character budget and, when the set was truncated, append a note telling the
    model to summarize what it has and to offer to narrow, so it answers instead of freezing.

    The note deliberately does not state a total count: callers may pass an already-paginated
    page whose length is not the true total, so claiming a total would mislead (cubic on #8527).
    """
    text = result if isinstance(result, str) else ("" if result is None else str(result))

    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS]
        truncated = True
    if truncated:
        # Generic callers may not know the row count, so report the number of rendered lines.
        # Callers that do know how many records survived the cap should pass that count.
        shown_count = max(0, int(shown)) if shown is not None else len(text.splitlines())
        unit = noun if shown is not None else "result lines"
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
        text += "\n\n" + note
    return text
