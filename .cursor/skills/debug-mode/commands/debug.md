# Debug

Use Debug Mode to troubleshoot tricky bugs, regressions, and performance issues.

## Usage

Switch to Debug Mode and describe your bug:

```
The audio streaming stops after 30 seconds. 
Error: Connection timeout
Reproduction: Start streaming, wait 30 seconds
Expected: Continuous streaming
Actual: Stops after 30 seconds
```

## Workflow

1. Agent explores code and generates hypotheses
2. Agent adds instrumentation (logs)
3. You reproduce bug with provided steps
4. Agent analyzes logs
5. Agent makes targeted fix
6. Agent verifies and cleans up

## Best Practices

- Provide detailed context (errors, stack traces)
- Be specific about expected vs actual
- Follow reproduction steps exactly
- Reproduce multiple times if intermittent

## Related Resources

- Skill: `.cursor/skills/debug-mode/SKILL.md`
- Agent: `.cursor/skills/debug-mode/agents/debug-specialist.md`
