# Ask

Use Ask Mode for learning, planning, and read-only exploration of the codebase.

## When to Use

Use Ask Mode when:
- Learning about unfamiliar code
- Understanding how systems work
- Planning before implementation
- Exploring codebase structure
- You want read-only exploration (no changes)

## How to Use

1. Switch to Ask Mode (mode picker or `Cmd+.` / `Ctrl+.`)
2. Ask questions about the codebase
3. Agent searches and provides answers
4. No code changes are made automatically

## Example Questions

**Architecture:**
- "How does authentication work in this codebase?"
- "Explain the memory extraction flow"
- "What happens when a user submits the login form?"

**Implementation:**
- "Where is conversation processing handled?"
- "How are BLE devices connected?"
- "Show me the API endpoint patterns"

**Understanding:**
- "Why does this function check for null here?"
- "What edge cases does CustomerOnboardingFlow handle?"
- "Walk me through the chat system"

## Best Practices

1. **Start broad**: "Give me high-level overview"
2. **Narrow down**: "How does authentication work?"
3. **Get specific**: "Show me token refresh flow"
4. **Build incrementally**: Each question builds on previous

## Workflow

**Example progression:**
1. "Overview of Omi architecture"
2. "How does the authentication system work?"
3. "Show me the token refresh flow"
4. "Why does this function check for null here?"

## Related Resources

- Rule: `.cursor/rules/agent-modes.mdc`
- Skill: `.cursor/skills/agent-modes/SKILL.md`
- Command: `.cursor/skills/agent-modes/commands/ask.md`
