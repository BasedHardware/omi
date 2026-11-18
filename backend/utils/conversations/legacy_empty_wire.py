"""Read-only compatibility for released clients that infer STT from empty titles."""

from typing import Any, Mapping

from config.episode_composition import legacy_empty_wire_enabled
from utils.episodes.compose_wait import empty_terminal_result
from utils.summary_quality import valid_title

TERMINAL_TITLE = 'No summary'


def terminal_noise(row: Mapping[str, Any]) -> bool:
    return legacy_empty_wire_enabled() and empty_terminal_result(row)


def project(row: dict[str, Any], *, noise: bool) -> dict[str, Any]:
    """Keep authoritative noise metadata, but prevent the old empty-text fallback.

    Do not invent a summary, transcript or lifecycle result. A terminal caption
    is used only on affirmative noise, and never replaces a nonempty title.
    Both list rows and episode metadata need it: old clients merge them by ID.
    """
    if not noise or not legacy_empty_wire_enabled() or not empty_terminal_result(row):
        return row
    structured = row.get('structured') or {}
    if valid_title(structured.get('title')):
        return row
    return {**row, 'structured': {**structured, 'title': TERMINAL_TITLE}}
