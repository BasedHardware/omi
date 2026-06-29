"""Shared size bounds for agentic retrieval tool results.

A chat tool that formats every matched row into one string can flood the model's context when
a broad query matches a huge set ("what do you know about me" pulls every memory; "analyze my
last 30 days" pulls every conversation). The oversized tool result then makes the model freeze
or refuse with "that's quite a bit of information to process at once" (issue #4927). These
helpers cap the row count and the raw character size, and append a note telling the model to
summarize what it has and offer to narrow.
"""

MAX_RESULT_CHARS = 60000


def cap_items_for_llm(items: list, max_items: int):
    """Keep at most ``max_items`` rows for the chat model.

    Callers pass rows already ordered most-relevant- or most-recent-first, so this keeps the
    ones that matter. Returns ``(capped_list, total_found, truncated)`` where ``truncated`` is
    True when some rows were dropped.
    """
    total_found = len(items)
    if total_found > max_items:
        return items[:max_items], total_found, True
    return list(items), total_found, False


def bounded_result(result: str, total_found: int, truncated: bool, noun: str = "results") -> str:
    """Apply a hard character budget and, when the set was truncated, append a note telling the
    model to summarize what it has and to offer to narrow, so it answers instead of freezing."""
    if len(result) > MAX_RESULT_CHARS:
        result = result[:MAX_RESULT_CHARS]
        truncated = True
    if truncated:
        result += (
            f"\n\n[This query matched {total_found} {noun}; only the most relevant are shown to stay "
            f"within limits. Summarize what is shown and tell the user they can ask about a narrower "
            f"topic or date range for complete detail.]"
        )
    return result
