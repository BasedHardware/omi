# Debug Mode

Use Debug Mode for tricky bugs, regressions, and issues that standard Agent interactions struggle with.

## When to Use Debug Mode

Use Debug Mode when:
- Bugs you can reproduce but can't figure out
- Race conditions and timing issues
- Performance problems and memory leaks
- Regressions where something used to work
- Standard Agent interactions struggle with the bug

## How to Use

1. Switch to Debug Mode (mode picker or `Cmd+.` / `Ctrl+.`)
2. Describe the bug with detailed context
3. Provide reproduction steps
4. Agent explores, hypothesizes, and adds instrumentation
5. Reproduce bug with provided steps
6. Agent analyzes logs and makes targeted fix

## Debug Mode Workflow

**Agent will:**
1. Explore and hypothesize about root causes
2. Add instrumentation (log statements)
3. Reproduce bug with your steps
4. Analyze collected logs
5. Make targeted fix based on evidence
6. Verify fix and clean up instrumentation

**You should:**
- Provide detailed context about the bug
- Include error messages and stack traces
- Follow reproduction steps exactly
- Reproduce multiple times if needed
- Be specific about expected vs actual behavior

## Example

```
User: Audio streaming stops after 30 seconds

Agent:
- Explores audio streaming code
- Hypothesizes: buffer underrun, timeout, connection issue
- Adds logging: buffer state, connection status, timestamps
- Asks: Can you reproduce with these steps?

User: [reproduces bug]

Agent:
- Analyzes logs
- Finds: Connection timeout after 30s
- Fixes: Increase timeout, add reconnection logic
- Verifies fix
- Removes instrumentation
```

## Best Practices

1. **Provide context**: Error messages, stack traces, reproduction steps
2. **Be specific**: Expected vs actual behavior
3. **Reproduce consistently**: Follow steps exactly
4. **Multiple reproductions**: If bug is intermittent
5. **Review fixes**: Verify fix addresses root cause

## Related Resources

- Rule: `.cursor/rules/agent-modes.mdc`
- Skill: `.cursor/skills/debug-mode/SKILL.md`
- Agent: `.cursor/skills/debug-mode/agents/debug-specialist.md`
