"""Account-level daily recap depth contract shared by settings and generation."""

from typing import Literal, cast, get_args

DailySummaryDepth = Literal['brief', 'normal', 'deep']
DEFAULT_DAILY_SUMMARY_DEPTH: DailySummaryDepth = 'brief'
VALID_DAILY_SUMMARY_DEPTHS = get_args(DailySummaryDepth)


def normalize_daily_summary_depth(value: object) -> DailySummaryDepth:
    """Treat absent or malformed legacy profile values as the unchanged brief default."""
    if isinstance(value, str) and value in VALID_DAILY_SUMMARY_DEPTHS:
        return cast(DailySummaryDepth, value)
    return DEFAULT_DAILY_SUMMARY_DEPTH
