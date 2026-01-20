# Codex Agent Rules

These rules apply to Codex when working in this repository.

## Coding Guidelines

### Backend

- No in-function imports. All imports must be at the module top level.
- Follow the module hierarchy when importing. Higher-level modules import from lower-level modules, never the reverse.

Module hierarchy (lowest to highest):
1. `database/`
2. `utils/`
3. `routers/`
4. `main.py`

- Memory management: free large objects immediately after use. E.g., `del` for byte arrays after processing, `.clear()` for dicts/lists holding data.

### App (Flutter)

- After modifying ARB files in `app/lib/l10n/`, regenerate localizations: `cd app && flutter gen-l10n`

## Formatting

Always format code after making changes. The pre-commit hook handles this automatically, but you can also run manually:

- **Dart (app/)**: `dart format --line-length 120 <files>`
  - Files ending in `.gen.dart` or `.g.dart` are auto-generated and should not be formatted manually.
- **Python (backend/)**: `black --line-length 120 --skip-string-normalization <files>`
- **C/C++ (firmware: omi/, omiGlass/)**: `clang-format -i <files>`

## Testing

- Always run tests before committing:
  - Backend changes: run `backend/test.sh`
  - App changes: run `app/test.sh`

## Setup

- Install pre-commit hook: `ln -s -f ../../scripts/pre-commit .git/hooks/pre-commit`
