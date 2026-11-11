#!/usr/bin/env bash
# Lane-worktree bootstrap (V4): one idempotent command that takes a fresh
# linked worktree to "pre-push cheap gates can run" and "bash app/test.sh can
# run" without `uv pip sync` of the full backend lock (llvmlite/scipy/av/pyarrow).
#
# Never touches another worktree. Never rewrites a pre-existing app/.dev.env.
set -euo pipefail

STARTED=$SECONDS
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

# shellcheck source=_resolve_python.sh
source "$(dirname "$0")/_resolve_python.sh"

FLUTTER_PIN="3.44.5"
CHEAP_PACKAGES="$ROOT/scripts/dev-harness/cheap-gate-python-packages.txt"
HERMETIC_CHECK="$ROOT/app/scripts/check_hermetic_test_env.sh"

# Shared caches — never a per-worktree copy.
export PUB_CACHE="${PUB_CACHE:-$HOME/.pub-cache}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/uv}"

echo "lane-bootstrap: worktree $ROOT"
echo "lane-bootstrap: PUB_CACHE=$PUB_CACHE (shared; this command never relocates it into the worktree)"
echo "lane-bootstrap: UV_CACHE_DIR=$UV_CACHE_DIR"

if ! command -v flutter >/dev/null 2>&1; then
  echo "FAIL: flutter is not on PATH. Install Flutter $FLUTTER_PIN (mise/repo pin, not latest)." >&2
  exit 1
fi
flutter_ver="$(flutter --version 2>/dev/null | head -n 1 || true)"
if [[ "$flutter_ver" != *" $FLUTTER_PIN "* && "$flutter_ver" != Flutter\ $FLUTTER_PIN* ]]; then
  echo "FAIL: $flutter_ver — expected Flutter $FLUTTER_PIN on PATH." >&2
  exit 1
fi
echo "lane-bootstrap: $flutter_ver"

if ! command -v uv >/dev/null 2>&1; then
  echo "FAIL: uv is required to create the Python 3.11 backend/.venv. Install: https://docs.astral.sh/uv/" >&2
  exit 1
fi

uv python install 3.11
uv venv --allow-existing --python 3.11 backend/.venv
VENV_PY="$ROOT/backend/.venv/bin/python"
if [[ ! -x "$VENV_PY" ]]; then
  echo "FAIL: backend/.venv/bin/python was not created." >&2
  exit 1
fi
py_ver="$("$VENV_PY" --version 2>&1 || true)"
if [[ "$py_ver" != *3.11.* ]]; then
  echo "FAIL: $VENV_PY is not Python 3.11 ($py_ver). Never use the system 3.14 runtime." >&2
  exit 1
fi
echo "lane-bootstrap: $py_ver at backend/.venv"

if ! dev_harness_venv_covers_cheap_gates "$VENV_PY"; then
  echo "lane-bootstrap: venv incomplete — installing cheap-gate packages only (not pylock.macos.toml)"
  uv pip install --python "$VENV_PY" -r "$CHEAP_PACKAGES"
  if ! dev_harness_venv_covers_cheap_gates "$VENV_PY"; then
    echo "FAIL: $VENV_PY still cannot import yaml and dotenv after the cheap-gate install." >&2
    exit 1
  fi
else
  echo "lane-bootstrap: cheap-gate imports (yaml, dotenv) already succeed — skipping pip"
fi

echo "lane-bootstrap: skipping full backend install (make lane-backend / make setup-backend)."
echo "lane-bootstrap: PRs that touch backend/ need 'make lane-backend' before git push —"
echo "lane-bootstrap:   otherwise check_backend_typecheck_if_needed fails (pyright missing)."
echo "lane-bootstrap:   (make lane-backend is the wheel install; make setup-backend is the locked pylock sync.)"
echo "lane-bootstrap: the Flutter generated-output gate needs 'flutter pub get' in app/"
echo "lane-bootstrap:   (this command already ran it; re-run after adding Dart deps)."

if [[ ! -x "$(git rev-parse --git-path hooks)/pre-commit" ]]; then
  bash scripts/install-git-hooks.sh
else
  echo "lane-bootstrap: git hooks already installed"
fi

# Git-ignored mobile build inputs (same copies as app/test.sh). Never rewrite
# an existing .dev.env — refuse a remote API instead.
mkdir -p app/android/app/src/dev app/ios/Config/Dev app/ios/Runner app/macos/Config/Dev
mkdir -p app/android/app/src/prod app/ios/Config/Prod app/macos/Config/Prod
copy_if_missing() {
  local src="$1" dest="$2"
  if [[ ! -f "$dest" ]]; then
    cp "$src" "$dest"
  fi
}
copy_if_missing app/lib/firebase_options_local.dart app/lib/firebase_options_dev.dart
copy_if_missing app/lib/firebase_options_local.dart app/lib/firebase_options_prod.dart
copy_if_missing app/setup/prebuilt/google-services-local.json app/android/app/src/dev/google-services.json
copy_if_missing app/setup/prebuilt/google-services-local.json app/android/app/src/prod/google-services.json
copy_if_missing app/setup/prebuilt/GoogleService-Info-Local.plist app/ios/Config/Dev/GoogleService-Info.plist
copy_if_missing app/setup/prebuilt/GoogleService-Info-Local.plist app/ios/Runner/GoogleService-Info.plist
copy_if_missing app/setup/prebuilt/GoogleService-Info-Local.plist app/macos/GoogleService-Info.plist
copy_if_missing app/setup/prebuilt/GoogleService-Info-Local.plist app/macos/Config/Dev/GoogleService-Info.plist
copy_if_missing app/setup/prebuilt/GoogleService-Info-Local.plist app/ios/Config/Prod/GoogleService-Info.plist
copy_if_missing app/setup/prebuilt/GoogleService-Info-Local.plist app/macos/Config/Prod/GoogleService-Info.plist

if [[ -f app/.dev.env ]]; then
  bash "$HERMETIC_CHECK" --app-dir "$ROOT/app"
else
  printf '%s\n' 'API_BASE_URL=' 'USE_WEB_AUTH=true' 'USE_AUTH_CUSTOM_TOKEN=true' >app/.dev.env
  echo "lane-bootstrap: wrote hermetic app/.dev.env (empty API_BASE_URL)"
fi

(
  cd app
  flutter pub get
)
bash scripts/dev-harness/generate-app-env.sh

elapsed=$((SECONDS - STARTED))
echo "lane-bootstrap: done in ${elapsed}s"
echo "lane-bootstrap: next: bash app/test.sh   # or scripts/pre-push for cheap gates"
echo "lane-bootstrap: full backend (uvicorn/pyright) remains opt-in: make lane-backend"
