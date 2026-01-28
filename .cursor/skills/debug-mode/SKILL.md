---
name: debug-mode
description: "Debug mode workflows and best practices for troubleshooting bugs, regressions, and performance issues. Use when debugging tricky issues that standard agent interactions struggle with."
---

# Debug Mode Skill

Specialized workflows for Debug Mode: hypothesis generation, log instrumentation, runtime analysis, and targeted fixes.

## When to Use

Use this skill when:
- Debugging tricky bugs that are hard to reproduce
- Investigating regressions
- Analyzing performance issues
- Troubleshooting race conditions
- Standard agent interactions aren't working

## Debug Mode Workflow

### 1. Exploration and Hypothesis

**Agent will:**
- Explore relevant code paths
- Generate hypotheses about root causes
- Identify potential failure points
- Plan instrumentation strategy

### 2. Instrumentation

**Agent adds:**
- Log statements at key points
- State tracking (variables, buffers, connections)
- Timing information
- Error condition checks

### 3. Reproduction

**You provide:**
- Detailed reproduction steps
- Expected vs actual behavior
- Error messages and stack traces
- Context about when bug occurs

### 4. Analysis

**Agent analyzes:**
- Collected logs
- State transitions
- Timing patterns
- Error conditions

### 5. Fix

**Agent makes:**
- Targeted fix based on evidence
- Minimal changes to address root cause
- Verification of fix
- Cleanup of instrumentation

## Best Practices

1. **Provide detailed context**: More information = better hypotheses
2. **Reproduce consistently**: Follow steps exactly
3. **Multiple reproductions**: For intermittent bugs
4. **Review fixes**: Ensure root cause addressed
5. **Clean up**: Remove instrumentation after fix

## Related Resources

- Rule: `.cursor/rules/agent-modes.mdc`
- Command: `/debug`
- Agent: `.cursor/skills/debug-mode/agents/debug-specialist.md`
