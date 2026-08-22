#!/usr/bin/env bash
# Run the enforced backend ty typecheck lane on the enrolled path surface.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -x .venv/bin/ty ]]; then
  TY_BIN=(.venv/bin/ty)
elif command -v ty >/dev/null 2>&1; then
  TY_BIN=(ty)
elif command -v uv >/dev/null 2>&1; then
  TY_BIN=(uv run ty)
else
  echo "ty is required. Sync backend deps: ./scripts/sync-python-deps.sh" >&2
  exit 1
fi

PATHS_FILE="${TYPECHECK_PATHS_FILE:-typecheck-paths.json}"
if [[ ! -f "$PATHS_FILE" ]]; then
  echo "Missing $PATHS_FILE (enrolled typecheck surface)." >&2
  exit 1
fi

PYTHON_BIN=".venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

ARGS_FILE="$(mktemp)"
trap 'rm -f "$ARGS_FILE"' EXIT
"$PYTHON_BIN" - "$PATHS_FILE" "$ARGS_FILE" <<'PY'
import fnmatch
import json
import sys
from pathlib import Path

cfg = json.loads(Path(sys.argv[1]).read_text())
excludes = cfg.get("exclude", [])

def is_excluded(path: Path) -> bool:
    s = path.as_posix()
    for ex in excludes:
        if s == ex or s.startswith(ex.rstrip("/") + "/"):
            return True
        if fnmatch.fnmatch(s, ex):
            return True
    return False

files: list[str] = []
for inc in cfg.get("include", []):
    p = Path(inc)
    if not p.exists():
        continue
    if p.is_file():
        if p.suffix == ".py" and not is_excluded(p):
            files.append(str(p))
        continue
    for f in p.rglob("*.py"):
        if "__pycache__" in f.parts:
            continue
        if not is_excluded(f):
            files.append(str(f))

if not files:
    raise SystemExit("No enrolled typecheck paths found")
Path(sys.argv[2]).write_bytes(b"\0".join(f.encode() for f in files) + b"\0")
PY

CHECK_ARGS=()
while IFS= read -r -d '' arg; do
  CHECK_ARGS+=("$arg")
done <"$ARGS_FILE"

exec "${TY_BIN[@]}" check --python .venv "${CHECK_ARGS[@]}"
