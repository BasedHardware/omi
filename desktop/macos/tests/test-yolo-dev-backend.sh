#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$ROOT/run.sh"

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
  export OMI_DESKTOP_API_URL="https://desktop-override.test"
  export OMI_PYTHON_API_URL="https://python-override.test"
  eval "$YOLO_FUNCTION"
  apply_yolo_env

  test "$OMI_SKIP_BACKEND" = "1"
  test "$OMI_SKIP_TUNNEL" = "1"
  test "$OMI_DESKTOP_API_URL" = "https://desktop-override.test"
  test "$OMI_PYTHON_API_URL" = "https://python-override.test"
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

echo "PASS: --yolo and implicit named bundles target development backends"
