# Auto-Generate Changelog

Automatically generate changelog entries from git commits and pull requests.

## Purpose

Generate formatted changelog entries from commit messages following conventional commits format. Categorizes changes and updates CHANGELOG.md.

## When to Use

Use this command when:
- On release or version bump
- When PR is merged
- Before creating release
- When preparing release notes
- When user requests changelog

## Process

1. **Get Commits**: Fetch commits since last release or tag
2. **Parse Messages**: Extract information from commit messages
   - Type (feat, fix, docs, refactor, etc.)
   - Scope (component/module)
   - Description
   - Breaking changes
   - Issue references (#123)
3. **Categorize**: Group changes by type
   - Features (feat)
   - Bug Fixes (fix)
   - Documentation (docs)
   - Refactoring (refactor)
   - Performance (perf)
   - Tests (test)
   - Chores (chore)
   - Breaking Changes
4. **Format**: Generate formatted changelog entry
5. **Update File**: Add entry to CHANGELOG.md at top
6. **Validate**: Check format and completeness

## Commit Message Format

Follows conventional commits:
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

## Related Cursor Resources

### Subagents
- `.cursor/agents/changelog-generator.md` - Changelog generation subagent

### Skills
- `.cursor/skills/changelog/SKILL.md` - Changelog generation workflows

### Rules
- `.cursor/rules/git-workflow.mdc` - Commit message format
- `.cursor/rules/documentation-standards.mdc` - Documentation standards
