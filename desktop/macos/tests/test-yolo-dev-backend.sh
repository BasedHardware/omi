#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$ROOT/run.sh"
BACKEND_MAIN="$ROOT/Backend-Rust/src/main.rs"

YOLO_FUNCTION="$(sed -n '/^apply_yolo_env()/,/^}/p' "$RUN")"
NAMED_DEFAULT_FUNCTION="$(sed -n '/^should_default_named_bundle_to_dev_backend()/,/^}/p' "$RUN")"

if [[ -z "$YOLO_FUNCTION" ]]; then
  echo "FAIL: apply_yolo_env is missing from $RUN" >&2
  exit 1
fi

if [[ -z "$NAMED_DEFAULT_FUNCTION" ]]; then
  echo "FAIL: should_default_named_bundle_to_dev_backend is missing from $RUN" >&2
  exit 1
fi

(
  unset OMI_SKIP_BACKEND OMI_SKIP_TUNNEL OMI_DESKTOP_API_URL OMI_PYTHON_API_URL FIREBASE_API_KEY
  eval "$YOLO_FUNCTION"
  apply_yolo_env

  test "$OMI_SKIP_BACKEND" = "1"
  test "$OMI_SKIP_TUNNEL" = "1"
  test "$OMI_DESKTOP_API_URL" = "https://desktop-backend-dt5lrfkkoa-uc.a.run.app"
  test "$OMI_PYTHON_API_URL" = "https://api.omiapi.com"
  test -n "$FIREBASE_API_KEY"
)

(
  export IS_NAMED_BUNDLE=true LOCAL_PROFILE=false
  unset OMI_SKIP_BACKEND OMI_SKIP_TUNNEL OMI_DESKTOP_API_URL OMI_PYTHON_API_URL
  eval "$NAMED_DEFAULT_FUNCTION"

  should_default_named_bundle_to_dev_backend

  OMI_SKIP_BACKEND=0
  ! should_default_named_bundle_to_dev_backend
  unset OMI_SKIP_BACKEND

  OMI_DESKTOP_API_URL="http://127.0.0.1:10343"
  ! should_default_named_bundle_to_dev_backend
  unset OMI_DESKTOP_API_URL

  OMI_PYTHON_API_URL="http://127.0.0.1:8080"
  ! should_default_named_bundle_to_dev_backend
)

bash "$RUN" --help | grep -q 'Quick start: use dev backend, no local services'

# Static tripwire: app and backend diagnostics must never converge on a
# machine-global developer log. The launcher's private per-launch directory
# is the ownership boundary for a local backend started by run.sh.
if grep -qE '/private/tmp/omi-dev\.log|/tmp/omi-dev\.log' "$RUN" "$BACKEND_MAIN"; then
  echo "FAIL: named-bundle launcher or Rust backend still uses the shared developer log" >&2
  exit 1
fi
grep -q 'BACKEND_LOG_FILE' "$RUN"
grep -q 'mktemp -d' "$RUN"
grep -q '>>"$BACKEND_LOG_FILE" 2>&1' "$RUN"

# Backend-Rust/.env commonly carries the template PORT=10201. The launcher
# must reassert its worktree-derived port after loading it so child/backend
# ownership state cannot diverge.
ENV_LOAD_LINE="$(grep -n 'set -a; source "\$BACKEND_DIR/.env"; set +a' "$RUN" | cut -d: -f1)"
PORT_REASSERT_LINE="$(grep -n 'export PORT="\$BACKEND_PORT"' "$RUN" | tail -1 | cut -d: -f1)"
if [[ -z "$ENV_LOAD_LINE" || -z "$PORT_REASSERT_LINE" || "$PORT_REASSERT_LINE" -le "$ENV_LOAD_LINE" ]]; then
  echo "FAIL: run.sh must reassert its derived backend PORT after sourcing .env" >&2
  exit 1
fi

echo "PASS: --yolo and implicit named bundles target development backends"
