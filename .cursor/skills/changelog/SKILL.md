---
name: changelog
description: "Generate changelog entries. Use on releases or PR merges. Parses git commits, categorizes changes, formats changelog entries, and updates CHANGELOG.md."
---

# Changelog Skill

Automate changelog generation from git commits and pull requests.

## When to Use

Use this skill when:
- On release or version bump
- When PR is merged
- When user requests changelog
- Before creating release
- When preparing release notes

## Capabilities

### 1. Parse Git Commits

Extract information from commits:
- Parse commit messages following conventional commits format
- Extract type (feat, fix, docs, refactor, etc.)
- Extract scope (component/module)
- Extract description
- Extract breaking changes
- Extract issue references (#123)

### 2. Categorize Changes

Organize changes by category:
- **Features** (`feat`): New functionality
- **Bug Fixes** (`fix`): Bug fixes
- **Documentation** (`docs`): Documentation changes
- **Refactoring** (`refactor`): Code refactoring
- **Performance** (`perf`): Performance improvements
- **Tests** (`test`): Test additions/changes
- **Chores** (`chore`): Maintenance tasks
- **Breaking Changes** (`BREAKING CHANGE`): Breaking changes

### 3. Format Changelog Entries

Create formatted changelog entry:
- Use standard changelog format
- Group by category
- Include issue references
- Highlight breaking changes
- Include contributor credits if available

### 4. Update CHANGELOG.md

Update changelog file:
- Add new entry at top
- Follow existing format
- Include version number
- Include release date
- Maintain chronological order

## Commit Message Format

Follows conventional commits (from `.cursor/rules/git-workflow.mdc`):
```
type(scope): subject

body (optional)

footer (optional)
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Formatting
- `refactor`: Code refactoring
- `test`: Tests
- `chore`: Maintenance

## Changelog Format

```markdown
## [Version] - YYYY-MM-DD

### Added
- New feature description (#123)

### Changed
- Change description (#456)

### Fixed
- Bug fix description (#789)

### Breaking Changes
- Breaking change description (#999)
```

## Workflow

1. **Get Commits**: Fetch commits since last release or tag
2. **Parse Messages**: Extract information from commit messages
3. **Categorize**: Group changes by type
4. **Format**: Generate formatted changelog entry
5. **Update File**: Add entry to CHANGELOG.md
6. **Validate**: Check format and completeness

## Related Resources

### Rules
- `.cursor/rules/git-workflow.mdc` - Commit message format
- `.cursor/rules/documentation-standards.mdc` - Documentation standards

### Subagents
- `.cursor/agents/changelog-generator.md` - Changelog generation subagent

### Commands
- `/auto-changelog` - Generate changelog automatically
