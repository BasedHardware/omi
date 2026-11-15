"""Affirmative terminal evidence is distinct from an empty transcript still in flight."""

from typing import Any, Mapping

from config.episode_composition import settled_terminal_enabled
from utils.conversations.fragment_visibility import is_completed_below_floor
from utils.conversations.home_titles import summary_owed
from utils.conversations.summary_delivery import EMPTY_BLOCKED_REASONS, present


def empty_terminal_result(row: Mapping[str, Any]) -> bool:
    """The Home noise contract, independent of presentation feature switches.

    Emptiness alone never qualifies. A durable exhausted-output/below-floor
    decision must exist, and renewed summary debt or a recovered receipt wins.
    Late speech is evaluated by the normal evidence/fingerprint path.
    """
    return bool(
        row.get('status') == 'completed'
        and not present(row.get('structured') or {})
        and not row.get('summary_output_present')
        and not row.get('summary_completed_at')
        and not summary_owed(row)
        and (row.get('summary_blocked_reason') in EMPTY_BLOCKED_REASONS or is_completed_below_floor(row))
    )


def settled_terminal(row: Mapping[str, Any]) -> bool:
    return settled_terminal_enabled() and empty_terminal_result(row)
