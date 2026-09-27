"""Hosted MCP OAuth scope list shared by the authorization server and helpers.

Pure module (no imports) so both ``database`` and ``utils`` layers can consume
the same literal without a database -> utils dependency.
"""

MCP_FULL_ACCESS_SCOPES = [
    "memories.read",
    "memories.write",
    "conversations.read",
    "action_items.read",
    "action_items.write",
    "goals.read",
    "chat.read",
    "screen_activity.read",
    "people.read",
]
