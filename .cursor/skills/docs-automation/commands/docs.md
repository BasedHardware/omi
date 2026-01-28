# Generate Documentation

Generate or update documentation for the @-mentioned code or current feature.

**The `docs/` folder is the single source of truth for all user-facing documentation, deployed at [docs.omi.me](https://docs.omi.me/).**

## Process

1. Identify what needs documentation:
   - If code is @-mentioned, document that
   - If working on a feature, document the feature
2. Check existing documentation structure in `docs/` folder
3. Generate or update in `docs/` folder:
   - API documentation (`docs/api-reference/` and `docs/doc/developer/api/`)
   - Backend documentation (`docs/doc/developer/backend/`)
   - Function/class docstrings in code
   - Architecture diagrams (Mermaid if appropriate)
4. Ensure documentation is clear, accurate, and follows project conventions
5. Verify paths match docs.omi.me URL structure

## Related Cursor Resources

### Rules
- `.cursor/rules/documentation-standards.mdc` - Documentation standards
- `.cursor/rules/backend-architecture.mdc` - Backend architecture
- `.cursor/rules/flutter-architecture.mdc` - Flutter architecture

### Commands
- `/update-api-docs` - Update API documentation
- `/validate-docs` - Validate documentation
