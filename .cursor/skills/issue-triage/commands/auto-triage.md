# Auto-Triage Issue

Automatically triage GitHub issues using the Omi Issue Triage Guide.

## Purpose

Score and prioritize GitHub issues using the triage formula from ISSUE_TRIAGE_GUIDE.MD. Assigns priority levels and suggests lane assignment.

## When to Use

Use this command when:
- Analyzing new GitHub issues
- When user requests issue triage
- When reviewing issue backlog
- When prioritizing issues
- When assigning issues to lanes

## Process

1. **Read Issue**: Analyze issue description, labels, comments
2. **Map to Layer**: Identify primary Omi layer affected
   - Capture (Weight: 5)
   - Understand (Weight: 4)
   - Memory (Weight: 4)
   - Intelligence (Weight: 3)
   - Retrieval / Action (Weight: 3)
   - UX / Polish (Weight: 1)
   - Docs / Tooling (Weight: 1)
3. **Evaluate Factors**: Score each factor (1-5)
   - Failure Severity
   - Trust Impact
   - Frequency
   - Maintenance Leverage
   - Cost & Risk (subtracted)
4. **Calculate Score**: Apply triage formula
   - Priority Score = (Core Layer Weight × Failure Severity) + Trust Impact + Frequency + Maintenance Leverage - Cost & Risk
5. **Assign Priority**: Map score to priority level
   - >= 30: P0 - Existential / must fix immediately
   - 22-29: P1 - Critical
   - 14-21: P2 - Important
   - < 14: P3 - Backlog
6. **Suggest Lane**: Recommend lane assignment
   - Maintainer Now
   - Community Ready
   - Needs Info
   - Park
7. **Report**: Provide triage summary with reasoning

## Triage Rules

Follow these principles:
- Issues are signals, not commands
- Popularity does not determine urgency
- Data loss outranks feature requests
- Capture failures outrank intelligence improvements
- Memory-first principle: If Omi fails to capture or preserve memory, nothing else matters

## Related Cursor Resources

### Skills
- `.cursor/skills/issue-triage/SKILL.md` - Issue triage workflows

### Documentation
- `ISSUE_TRIAGE_GUIDE.MD` - Complete triage guide and formula

### Rules
- `.cursor/rules/omi-specific-patterns.mdc` - Omi architecture and priorities
