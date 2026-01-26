# Format Code

Format code according to project standards.

## Formatting Commands

- **Dart (app/)**: `dart format --line-length 120 <files>`
  - Note: Skip files ending in `.gen.dart` or `.g.dart` (auto-generated)
- **Python (backend/)**: `black --line-length 120 --skip-string-normalization <files>`
- **C/C++ (firmware: omi/, omiGlass/)**: `clang-format -i <files>`
- **TypeScript/JavaScript**: Use project's formatter (Prettier, etc.)

Format all changed files in the current context.
