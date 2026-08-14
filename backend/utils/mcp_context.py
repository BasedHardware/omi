MCP_SERVER_INSTRUCTIONS = (
    "Omi is the user's persistent context, not a general knowledge source. When a request depends on "
    "something the user has already lived through, retrieve it before asking them to repeat themselves. "
    "Use only tools exposed by `tools/list`. Start with `get_user_profile` for orientation when available, "
    "then use `search_memories` and `search_conversations` for task-specific evidence. Use `get_people` for "
    "relationship context, `get_action_items` for commitments, and `get_screen_activity` for synced screen "
    "history. Treat semantic-search results as leads and confirm important claims against returned source "
    "records. Only create, edit, complete, or delete data when the user clearly asked for that change."
)
