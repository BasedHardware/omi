# Format Code

Format code according to project standards.

## Formatting Commands

- **Dart (app/)**: `dart format --line-length 120 <files>`
  - Note: Skip files ending in `.gen.dart` or `.g.dart` (auto-generated)
- **Python (backend/)**: `black --line-length 120 <files>`
  - Note: String normalization settings come from `backend/pyproject.toml`
- **C/C++ (firmware: omi/, omiGlass/)**: `clang-format -i <files>`
- **TypeScript/JavaScript**: Use project's formatter (Prettier, etc.)

Format all changed files in the current context.

## Related Cursor Resources

### Rules
- `.cursor/rules/formatting.mdc` - Code formatting standards

### Commands
- `/lint-and-fix` - Lint and fix issues
