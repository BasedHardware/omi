# Lint and Fix

Run the linter for the changed code, auto-fix issues where possible, and report remaining issues.

## Process

1. Identify which linter to run based on file types:
   - Python: `black`, `flake8`, `pylint` (as configured)
   - Dart: `dart analyze`
   - TypeScript/JavaScript: ESLint (as configured)
   - C/C++: clang-tidy (if configured)
2. Run the linter
3. Auto-fix issues where possible
4. Report remaining issues that require manual fixes
5. Format code according to project standards

## Related Cursor Resources

### Rules
- `.cursor/rules/formatting.mdc` - Code formatting standards
- `.cursor/rules/backend-imports.mdc` - Backend import rules

### Commands
- `/format` - Format code
- `/code-review` - Review code after linting
