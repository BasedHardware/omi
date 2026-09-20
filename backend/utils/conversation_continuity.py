"""Shared boundary arithmetic; callers supply their observed timeline coverage."""

DEFAULT_GAP_SECONDS = 120


def gap_splits(seconds: float, timeout: float = DEFAULT_GAP_SECONDS) -> bool:
    return seconds >= timeout


def intervals_connect(start: float, end: float, other_start: float, other_end: float) -> bool:
    return not gap_splits(max(start - other_end, other_start - end))
