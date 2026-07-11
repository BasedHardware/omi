#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$ROOT/run.sh"

YOLO_FUNCTION="$(sed -n '/^apply_yolo_env()/,/^}/p' "$RUN")"

if [[ -z "$YOLO_FUNCTION" ]]; then
  echo "FAIL: apply_yolo_env is missing from $RUN" >&2
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

bash "$RUN" --help | grep -q 'Quick start: use dev backend, no local services'

echo "PASS: --yolo targets the development backends"
