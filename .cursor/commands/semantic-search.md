# Semantic Search

Use semantic search to find code by understanding its meaning, not just matching text.

## Usage

Ask natural language questions:

```
How does authentication work in this codebase?
Where is memory extraction handled?
How are WebSocket connections managed?
```

## How It Works

Semantic search uses AI to understand code meaning:
1. Files are indexed with embeddings
2. Your query is converted to vector
3. System finds semantically similar code
4. Results ranked by relevance

## When to Use

**Use semantic search for:**
- Finding code by functionality
- Discovering related code
- Understanding implementations
- Finding similar patterns
- Exploring unfamiliar code

**Use grep for:**
- Exact string matches
- Specific function names
- Exact error messages
- File patterns

## Best Practices

1. **Use natural language**: Ask questions as you would ask a colleague
2. **Be specific about context**: "authentication in backend" vs just "authentication"
3. **Start broad, narrow down**: Build understanding incrementally
4. **Combine with grep**: Use both for best results
5. **Review multiple results**: Check several results for full picture

## Query Examples

**Backend:**
- "How are conversations processed?"
- "Where is memory extraction implemented?"
- "How does the chat system route requests?"

**Flutter:**
- "How does BLE device connection work?"
- "Where is audio streaming handled?"
- "How is state managed in the app?"

## Related Resources

- Skill: `.cursor/skills/context-optimization/SKILL.md`
- Agent: `.cursor/skills/context-optimization/agents/context-manager.md`
- Rule: `.cursor/rules/semantic-search.mdc`
