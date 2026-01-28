---
name: pr-automation
description: "Automate PR workflows. Use before creating PRs. Generates PR descriptions, validates PR requirements, checks for missing tests/docs, and links issues automatically."
---

# PR Automation Skill

Automate pull request workflows to streamline PR creation and validation.

## When to Use

Use this skill when:
- Before creating a PR
- When user requests PR creation
- Before pushing code to remote
- After completing a feature or fix

## Capabilities

### 1. Generate PR Descriptions

Automatically generate comprehensive PR descriptions:
- Analyze git diff to understand changes
- Extract commit messages for context
- Identify changed files and their purposes
- Generate structured PR description following template
- Include all required sections (description, changes, testing, etc.)

### 2. Validate PR Requirements

Check PR requirements before creation:
- Verify tests exist for new features
- Check that tests pass
- Verify documentation is updated
- Validate code follows project conventions
- Check for linting errors
- Verify formatting is correct
- Ensure no secrets or credentials are committed

### 3. Check for Missing Tests/Docs

Identify missing requirements:
- Check if new features have tests
- Verify documentation is updated
- Check for missing type hints (Python)
- Verify error handling is documented
- Check for missing API documentation

### 4. Link Issues Automatically

Automatically link related issues:
- Parse commit messages for issue references (#123)
- Search for related issues based on changes
- Add "Closes #123" or "Related to #123" to PR description
- Link to parent issues or epics

### 5. Suggest Reviewers

Suggest appropriate reviewers:
- Based on files changed (domain expertise)
- Based on previous reviewers of similar changes
- Based on code owners (if CODEOWNERS file exists)
- Based on team structure

## Workflow

1. **Analyze Changes**: Review git diff and commit history
2. **Generate Description**: Create comprehensive PR description
3. **Run Validation**: Check all PR requirements
4. **Fix Issues**: Address any validation failures
5. **Create PR**: Generate PR with all information
6. **Post-Creation**: Add labels, assign reviewers, link issues

## PR Description Template

Follows the template from `.cursor/rules/context-communication.mdc`:
- Description of what changed and why
- Related issue links
- List of changes
- How it was verified
- Related code references
- Assumptions made
- Breaking changes (if any)
- Testing checklist

## Related Resources

### Rules
- `.cursor/rules/git-workflow.mdc` - Git workflow and PR process
- `.cursor/rules/context-communication.mdc` - PR description best practices
- `.cursor/rules/testing.mdc` - Testing requirements

### Subagents
- `.cursor/agents/pr-manager.md` - PR management subagent
- `.cursor/agents/code-reviewer.md` - Code review subagent
- `.cursor/agents/test-runner.md` - Test runner subagent

### Commands
- `/auto-pr` - Generate PR with automation
- `/pr` - Create pull request with proper description
- `/code-review` - Review code before PR
