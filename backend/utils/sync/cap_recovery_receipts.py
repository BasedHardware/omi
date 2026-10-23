"""Existing provider-empty reconciliation receipt, separate from coverage proof."""

from typing import Any


def settled_empty(receipt: dict[str, Any] | None) -> dict[str, Any] | None:
    """A dispatch whose provider reply completed with no words is terminal.

    The fenced result checkpoint proves the call finished, so there is nothing
    to reconcile and nothing to charge; only a dispatch with no completion
    checkpoint stays ambiguous.
    """
    if (
        not receipt
        or receipt.get('state') != 'dispatched'
        or receipt.get('provider_result')
        or not receipt.get('provider_empty')
        or not receipt.get('provider_completed_at')
    ):
        return None
    return {
        **receipt,
        'state': 'transcribed',
        'has_content': False,
        'seconds': 0,
        'response': {'new_memories': [], 'updated_memories': []},
    }
