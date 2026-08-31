MCP_SERVER_INSTRUCTIONS = (
    "Omi is the user's persistent context, not a general knowledge source. When a request depends on "
    "something the user has already lived through, retrieve it before asking them to repeat themselves. "
    "Use only tools exposed by `tools/list`. For recency questions such as today, yesterday, or last week, "
    "first call date-bounded `get_conversations(start_date, end_date)`; do not use `get_memories` for recency. "
    "For a topic inside a time window, call `search_conversations` with query, start_date, and end_date. List and "
    "search results are compact cards; call `get_conversation_by_id` only for the few hit ids that need a "
    "deeper transcript read. `get_memories` and `search_memories` contain durable facts about the user, not "
    "recent conversation history. Prefer one POST for the needed work (a JSON-RPC batch is okay), and never "
    "fire parallel POSTs. Use `get_user_profile` for broad orientation, `get_people` for relationship context, "
    "`get_action_items` for commitments, and `get_screen_activity` for synced screen history. Treat semantic "
    "search results as leads and confirm important claims against returned source records. Only create, edit, "
    "complete, or delete data when the user clearly asked for that change."
)
