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

## Testing

- Always run tests before committing:
  - Backend changes: run `backend/test.sh`
  - App changes: run `app/test.sh`
