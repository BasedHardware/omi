#!/usr/bin/env bash
# Generate envied outputs (app/lib/env/*.g.dart) without deleting other tracked files.
#
# Why this is a dedicated step: a V2 sim-boot spike ran
#   flutter pub run build_runner build --delete-conflicting-outputs --build-filter=lib/env/*
# and the tracked file app/lib/utils/manifest/manifest.g.dart disappeared, costing
# a 301 s failed iOS build. --delete-conflicting-outputs was reported ignored by
# this SDK, so the destructive part is build_runner's filtered output graph, not
# a harness wrapper around an otherwise safe flag. Never pass either option.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APP="$ROOT/app"

if [[ -f "$APP/lib/env/dev_env.g.dart" && -f "$APP/lib/env/prod_env.g.dart" ]]; then
  echo "generate-app-env: envied outputs already present"
  exit 0
fi

echo "generate-app-env: running build_runner (no --delete-conflicting-outputs, no --build-filter)"
(
  cd "$APP"
  flutter pub run build_runner build
)

# If build_runner still unlinks a tracked file, put it back. gitignored envied
# outputs are not in ls-files -d, so this cannot clobber the files we just wrote.
restored=0
while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  git -C "$ROOT" checkout -- "$path"
  echo "generate-app-env: restored tracked $path"
  restored=1
done < <(git -C "$ROOT" ls-files -d)
if [[ "$restored" -eq 0 ]]; then
  echo "generate-app-env: no tracked files were deleted"
fi
