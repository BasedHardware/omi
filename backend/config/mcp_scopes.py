"""Hosted MCP OAuth scope list shared by the authorization server and helpers.

Pure module (no imports) so both ``database`` and ``utils`` layers can consume
the same literal without a database -> utils dependency.
"""

# Granted automatically to every MCP API key, including legacy keys repaired on
# their next authentication. Corrections belong here: renaming a misrecognised
# person is safe and reversible in place.
MCP_DEFAULT_API_KEY_SCOPES = [
    "memories.read",
    "memories.write",
    "conversations.read",
    "action_items.read",
    "action_items.write",
    "goals.read",
    "chat.read",
    "screen_activity.read",
    "people.read",
    "people.rename",
]

# Never granted implicitly -- not to legacy keys, not to newly created keys, not
# by default. Dismissal is reversible in storage but removes a record from normal
# product reads, so it requires an explicit request at key/consent time.
MCP_OPT_IN_SCOPES = ["people.cleanup"]

# Everything a caller may legitimately ask for.
MCP_SUPPORTED_SCOPES = MCP_DEFAULT_API_KEY_SCOPES + MCP_OPT_IN_SCOPES

# Backward-compatible export. "Full access" historically meant the automatically
# granted key capabilities, so it stays aliased to the default grant -- risky new
# scopes are deliberately outside it.
MCP_FULL_ACCESS_SCOPES = list(MCP_DEFAULT_API_KEY_SCOPES)
