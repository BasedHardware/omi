"""Webhook parsing helpers for Omi plugin apps."""

from typing import Any

from omi_plugin_sdk.models import Conversation


def parse_conversation(payload: dict[str, Any]) -> Conversation:
    """Parse an Omi conversation webhook payload with the shared SDK model."""
    return Conversation.model_validate(payload)
