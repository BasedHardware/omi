# Auto-Update Documentation

Automatically detect code changes and update relevant documentation.

## Purpose

Keep documentation in sync with code changes automatically. Detects API endpoint changes, function modifications, and architecture updates, then updates relevant documentation files.

## When to Use

Use this command when:
- After making code changes that affect APIs or architecture
- Before committing changes
- When you want to ensure docs are up to date
- When working on API endpoints or core modules

## Process

1. **Detect Changes**: Analyze git diff or current changes
2. **Identify Impact**: Determine which documentation needs updating
   - API endpoint changes → Update API reference docs
   - Architecture changes → Update architecture docs
   - Function/class changes → Update code documentation
3. **Generate Updates**: Create or update relevant documentation files
4. **Validate**: Check documentation for completeness and accuracy
5. **Sync**: Ensure all documentation locations are in sync

## What Gets Updated

### API Documentation
- `.cursor/docs/API_REFERENCE.md` - Internal API reference
- `docs/api-reference/endpoint/*.mdx` - Public API docs
- `docs/doc/developer/api/*.mdx` - Developer API docs

### Architecture Documentation
- `.cursor/docs/ARCHITECTURE.md` - System architecture
- `.cursor/docs/DATA_FLOW.md` - Data flow diagrams
- `.cursor/docs/BACKEND_COMPONENTS.md` - Backend components
- `.cursor/docs/FLUTTER_COMPONENTS.md` - Flutter components

### Code Documentation
- Function/class docstrings
- README files in relevant directories
- Developer documentation

## Automation

This command uses the docs-generator subagent and docs-automation skill to:
- Automatically detect changes in `backend/routers/` for API updates
- Generate Mermaid diagrams from code structure
- Sync between `.cursor/` and `docs/` directories
- Validate documentation format and completeness

## Related Cursor Resources

### Subagents
- `.cursor/agents/docs-generator.md` - Documentation generation subagent

### Skills
- `.cursor/skills/docs-automation/SKILL.md` - Documentation automation workflows

### Commands
- `/update-api-docs` - Update API reference documentation specifically
- `/docs` - Generate or update documentation manually

### Rules
- `.cursor/rules/documentation-standards.mdc` - Documentation standards
- `.cursor/rules/auto-documentation.mdc` - Auto-documentation rules
