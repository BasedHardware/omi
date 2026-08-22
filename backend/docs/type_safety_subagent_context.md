# Type-safety fix context for agents

Fix every enrolled file to **0 ty errors**, using `typecheck-paths.json` as the
path surface.

## Single-file check

```bash
cd $(git rev-parse --show-toplevel)/backend
.venv/bin/ty check --python .venv <path>
```

## Full typecheck

```bash
cd $(git rev-parse --show-toplevel)/backend && bash scripts/typecheck.sh
```

## Rules of engagement

1. Prefer fixing types (annotations, narrowing, adapters). Do not change
   runtime logic only to satisfy the typechecker.
2. Use `# ty: ignore[<rule>]` only when the false positive is in third-party
   stubs or FastAPI injection patterns that cannot be typed cleanly.
3. After a file is clean, enroll it in `typecheck-paths.json` (remove from
   `exclude` / add to `include`) if it was previously out of the gate.
