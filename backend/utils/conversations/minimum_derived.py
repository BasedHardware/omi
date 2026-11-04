"""Server minimums retain capture/webhooks but never request derived intelligence.

Use the persisted output marker rather than re-evaluating flags or thresholds:
deferred consumers must agree with the notes decision that actually served.
A later enriched replacement naturally removes this restriction.
"""

from collections.abc import Mapping
from typing import Any


def is_server_minimum(conversation: Any) -> bool:
    structured = (
        conversation.get('structured')
        if isinstance(conversation, Mapping)
        else getattr(conversation, 'structured', None)
    )
    provenance = (
        structured.get('title_provenance')
        if isinstance(structured, Mapping)
        else getattr(structured, 'title_provenance', None)
    )
    return provenance == 'server_minimum'


def intentional_short_clip_minimum(row: Mapping[str, Any]) -> bool:
    """Only the server's floor decision waives a summary; provider faults still owe one."""
    decision = row.get('relevance_decision') or {}
    return (
        is_server_minimum(row)
        and isinstance(decision, Mapping)
        and decision.get('verdict') == 'keep'
        and decision.get('decided_by') == 'rule'
        and decision.get('reason') == 'content_below_floor'
    )


def waive_short_clip_summary_debt(write: dict[str, Any], context: dict[str, Any] | None) -> None:
    """Retire summary debt without the terminal marker that suppresses creation delivery."""
    write['summary_due_at'] = None
    write['summary_processing_lease_until'] = 0
    write['summary_blocked_reason'] = 'content_below_floor'
    if context is not None:
        context['blocked_reason'] = 'content_below_floor'
