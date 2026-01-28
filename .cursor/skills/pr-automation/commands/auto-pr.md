# Auto-Generate PR

Automatically generate pull request with comprehensive description and validation.

## Purpose

Streamline PR creation by automatically generating PR descriptions, validating requirements, checking for missing tests/docs, and linking related issues.

## When to Use

Use this command when:
- Before creating a PR
- When code is ready for review
- After completing a feature or fix
- When you want to ensure PR meets all requirements

## Process

1. **Analyze Changes**: Review git diff and commit history
2. **Generate Description**: Create comprehensive PR description following template
3. **Run Validation**: Check all PR requirements
   - Tests exist and pass
   - Documentation is updated
   - Code follows conventions
   - No linting errors
   - Formatting is correct
   - No secrets committed
4. **Fix Issues**: Address any validation failures automatically
5. **Link Issues**: Automatically link related issues from commits
6. **Suggest Reviewers**: Recommend reviewers based on changed files
7. **Create PR**: Generate PR with all information

## PR Description Includes

- Clear title and description
- List of changes and files modified
- Related issue links
- How changes were verified
- Testing performed
- Breaking changes (if any)
- Checklist items

## Validation Checks

- [ ] Tests exist for new features
- [ ] Tests pass
- [ ] Documentation updated
- [ ] Code follows project conventions
- [ ] No linting errors
- [ ] Formatting correct
- [ ] No secrets or credentials

## Automation

This command uses multiple subagents:
- **PR Manager**: Generates PR description and validates requirements
- **Code Reviewer**: Reviews code before PR
- **Test Runner**: Runs tests and fixes failures
- **Verifier**: Verifies completeness

## Related Cursor Resources

### Subagents
- `.cursor/agents/pr-manager.md` - PR management subagent
- `.cursor/agents/code-reviewer.md` - Code review subagent
- `.cursor/agents/test-runner.md` - Test runner subagent
- `.cursor/agents/verifier.md` - Verification subagent

### Skills
- `.cursor/skills/pr-automation/SKILL.md` - PR automation workflows

### Commands
- `/pr` - Create pull request with proper description
- `/code-review` - Review code before PR

### Rules
- `.cursor/rules/git-workflow.mdc` - Git workflow and PR process
- `.cursor/rules/context-communication.mdc` - PR description best practices
