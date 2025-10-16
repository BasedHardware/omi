# Migration from Graph-Based to Agentic Chat

## Overview

The new agentic system (`agentic.py`) replaces the manual graph-based approach (`graph.py`) with an autonomous tool-calling agent.

## Key Differences

### Old System (graph.py)
- **Manual context building**: Pre-determined flow with nodes for filtering, searching, etc.
- **Fixed logic**: Conditional edges decide the path
- **Limited flexibility**: Hard-coded decision points
- **Complex maintenance**: Changes require modifying graph structure

### New System (agentic.py)  
- **Autonomous decisions**: LLM decides which tools to use
- **Dynamic context**: Tools called as needed based on query
- **Simple tools**: Raw data access functions
- **Easy to extend**: Just add new tools

## How to Switch

In `routers/chat.py`, replace:

```python
# Old
async for chunk in execute_graph_chat_stream(
    uid, messages, app, cited=True, callback_data=callback_data, chat_session=chat_session
):
```

With:

```python
# New
async for chunk in execute_agentic_chat_stream(
    uid, messages, app, callback_data=callback_data, chat_session=chat_session
):
```

## Testing the New System

1. **Simple questions** (no tools needed):
   - "Hi, how are you?"
   - "What's your name?"

2. **Memory queries** (uses get_memories_tool):
   - "What do you know about me?"
   - "What are my preferences?"

3. **Conversation searches** (uses search_conversations_tool):
   - "What did I discuss about work yesterday?"
   - "Find conversations about machine learning"

4. **Time-based queries** (uses get_conversations_tool):
   - "What happened last week?"
   - "Show me conversations from Monday"

## Adding New Tools

To add a new tool:

1. Create it in `tools/` directory
2. Export it from `tools/__init__.py`
3. Add it to the tools list in `agentic.py`

Example:
```python
# In tools/analytics_tools.py
@tool
def get_conversation_stats_tool(
    days: int = 7,
    config: Optional[RunnableConfig] = None,
) -> str:
    """Get statistics about user's conversations."""
    uid = config['configurable'].get('user_id')
    # Implement stats calculation
    return f"Stats for last {days} days: ..."

# In agentic.py
from utils.retrieval.tools import (
    get_conversations_tool,
    get_conversation_stats_tool,  # Add new tool
)

tools = [
    get_conversations_tool,
    search_conversations_tool,
    get_memories_tool,
    get_user_facts_tool,
    get_conversation_stats_tool,  # Add to list
]
```

## Benefits

1. **Simpler code**: No complex graph logic
2. **More intelligent**: LLM makes smart decisions
3. **Easy to extend**: Just add tools
4. **Better context**: Tools called only when needed
5. **Maintainable**: Tools are independent and testable

## Gradual Migration

You can run both systems in parallel:
- Keep graph.py for existing users
- Test agentic.py with beta users
- Monitor performance and accuracy
- Switch gradually with feature flags
