# Review Changes

Use Agent Review to analyze and catch bugs in your code changes before merging.

## Usage

### Review Agent-Generated Code

1. After agent response, click **Review**
2. Click **Find Issues** to analyze edits
3. Review flagged issues
4. Address critical issues
5. Accept changes when satisfied

### Review All Local Changes

1. Open Source Control tab
2. Run Agent Review on all changes
3. Review issues across all files
4. Fix issues before committing

## What It Catches

- Logic bugs and edge cases
- Security vulnerabilities
- Architecture violations
- Missing error handling
- Test coverage gaps
- Performance issues

## Best Practices

1. **Complete changes first**: Finish implementation
2. **Run tests**: Ensure tests pass
3. **Format code**: Use `/format` command
4. **Address critical issues**: Fix blocking bugs first
5. **Review suggestions**: Not all suggestions are correct
6. **Test fixes**: Verify fixes don't break functionality

## Integration

**Workflow:**
1. Use Agent Review locally
2. Create PR
3. Bugbot reviews PR automatically
4. Address any additional issues

## Related Resources

- Skill: `.cursor/skills/agent-review/SKILL.md`
- Rule: `.cursor/rules/agent-review.mdc`
- `.cursor/BUGBOT.md` - Bugbot review rules
