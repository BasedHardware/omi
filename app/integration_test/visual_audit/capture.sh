#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
if [[ $# -gt 1 || "${1:-}" == --help ]]; then
  echo 'Usage: bash integration_test/visual_audit/capture.sh [OUTPUT_DIRECTORY]'
  exit 0
fi
bash scripts/check_hermetic_test_env.sh --app-dir "$PWD"
export OMI_AUDIT_OUTPUT="${1:-$(mktemp -d /tmp/omi-mobile-visual-XXXXXX)}"
if [[ -d "$OMI_AUDIT_OUTPUT" ]] && [[ -n "$(ls -A "$OMI_AUDIT_OUTPUT")" ]]; then
  echo "Output directory must be empty (prevents stale screenshot evidence): $OMI_AUDIT_OUTPUT" >&2
  exit 2
fi
mkdir -p "$OMI_AUDIT_OUTPUT"
OMI_AUDIT_OUTPUT="$(cd "$OMI_AUDIT_OUTPUT" && pwd)"
export OMI_AUDIT_OUTPUT
flutter_sdk="$(flutter --version --machine | python3 -c 'import json,sys; print(json.load(sys.stdin)["flutterRoot"])')"
export OMI_AUDIT_FONTS="$flutter_sdk/bin/cache/artifacts/material_fonts"
git rev-parse HEAD > "$OMI_AUDIT_OUTPUT/source-sha.txt"
git diff --stat > "$OMI_AUDIT_OUTPUT/source-diff.txt"
git status --short > "$OMI_AUDIT_OUTPUT/source-status.txt"
python3 - <<'SOURCE'
import hashlib, json, os, subprocess
from pathlib import Path
root = Path(subprocess.check_output(['git', 'rev-parse', '--show-toplevel'], text=True).strip())
paths = set()
for args in [['diff', '--name-only', 'HEAD', '-z'], ['ls-files', '--others', '--exclude-standard', '-z']]:
    paths.update(subprocess.check_output(['git', '-C', str(root), *args]).decode().split('\0'))
manifest = {p: hashlib.sha256((root / p).read_bytes()).hexdigest()
            for p in sorted(paths) if p and (root / p).is_file()}
(Path(os.environ['OMI_AUDIT_OUTPUT']) / 'source-hashes.json').write_text(json.dumps(manifest, indent=2))
SOURCE
flutter test -d flutter-tester --concurrency=1 integration_test/visual_audit/capture_test.dart --reporter expanded 2>&1 | tee "$OMI_AUDIT_OUTPUT/capture.log"
python3 integration_test/visual_audit/write_gallery.py
echo "Screenshots and state manifest: $OMI_AUDIT_OUTPUT"
