---
name: agent-review
description: "Agent Review workflows and best practices for catching bugs before merging. Use for reviewing agent-generated code and local changes."
---

# Agent Review Skill

Workflows and best practices for using Agent Review to catch bugs before merging.

## When to Use

Use this skill when:
- Agent has generated code changes
- You have local changes to review
- Before creating a PR
- After significant refactoring
- When you want a second opinion on code

## Capabilities

### Review Agent-Generated Code

- Click "Review" in agent diff
- Click "Find Issues" to analyze edits
- Review flagged issues
- Address critical issues
- Accept changes when satisfied

### Review All Local Changes

- Open Source Control tab
- Run Agent Review on all changes
- Review issues across all files
- Fix issues before committing

## What Agent Review Catches

- Logic bugs and edge cases
- Security vulnerabilities
- Architecture violations
- Missing error handling
- Test coverage gaps
- Performance issues

## Best Practices

### Before Review

1. Complete your changes
2. Run tests
3. Format code
4. Quick manual review

### During Review

1. Address critical issues first
2. Review suggestions carefully
3. Test fixes
4. Use selective acceptance

### After Review

1. Re-run tests
2. Re-review if needed
3. Create PR

## Integration

**Workflow:**
1. Use Agent Review locally
2. Create PR
3. Bugbot reviews PR automatically
4. Address any additional issues

## Related Resources

- Rule: `.cursor/rules/agent-review.mdc`
- Command: `/review-changes`
- `.cursor/BUGBOT.md` - Bugbot review rules
