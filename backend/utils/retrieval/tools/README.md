# Chat Tools for Agentic System

This directory contains tool definitions for the LangGraph agentic chat system.

## Philosophy

The tools here are **raw functions** that provide direct access to data:
- `get_conversations_tool`: Retrieve conversations by date range
- `search_conversations_tool`: Semantic search through conversations  
- `get_memories_tool`: Access user memories/facts
- `get_user_facts_tool`: Get concise user summary

The LLM autonomously decides:
1. Which tools to use
2. What parameters to pass
3. How to synthesize the information

## Adding New Tools

When adding new tools:

1. **Keep them simple**: Tools should be thin wrappers around database/API calls
2. **Be descriptive**: Docstrings tell the LLM when and how to use the tool
3. **Use type hints**: Help the LLM understand parameter types
4. **Return strings**: LLMs work best with text responses
5. **Handle errors gracefully**: Return error messages as strings, don't raise exceptions

Example:

```python
@tool
def get_user_habits_tool(
    category: Optional[str] = None,
    limit: int = 10,
    config: Optional[RunnableConfig] = None,
) -> str:
    """
    Get user habits and patterns.
    
    Use this when you need to understand user behaviors, routines,
    or patterns. Can filter by category (e.g., 'sleep', 'exercise', 'work').
    
    Args:
        category: Optional category filter
        limit: Max habits to return
    
    Returns:
        String describing user habits
    """
    # Implementation
    pass
```

## Tool Categories

Organize tools by domain:
- `conversation_tools.py`: Conversation access and search
- `memory_tools.py`: User memories and facts
- `integration_tools.py`: External integrations (future)
- `analytics_tools.py`: User analytics and insights (future)

## Context Access

Tools can access context via:
- `config: RunnableConfig`: For user_id and other runtime config
- `InjectedState`: For graph state (if using custom graphs)
- `get_store()`: For long-term memory store

Example with config:
```python
def my_tool(config: Optional[RunnableConfig] = None) -> str:
    uid = config['configurable'].get('user_id')
    # Use uid to fetch data
```
