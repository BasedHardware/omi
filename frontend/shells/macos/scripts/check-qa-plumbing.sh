#!/bin/bash
# Install-free red proofs for the shell acceptance and profile plumbing.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
build="$here/scripts/build-shell.sh"
run="$here/scripts/run-shell.sh"
swift="$here/shell/Sources/OmiShell/main.swift"
dart="$here/../flutter-webview/app/lib/main.dart"

bash -n "$build" "$run"
if OMI_APP_NAME='unsafe/name' OMI_BUILD_DIR="${TMPDIR:-/tmp}/omi-qa-invalid" "$build" >/dev/null 2>&1; then
  echo 'red proof failed: unsafe OMI_APP_NAME was accepted' >&2
  exit 1
fi
if OMI_APP_NAME='unsafe/name' OMI_BUILD_DIR="${TMPDIR:-/tmp}/omi-qa-invalid" "$run" >/dev/null 2>&1; then
  echo 'red proof failed: run-shell accepted unsafe OMI_APP_NAME' >&2
  exit 1
fi
if rg -n '/Users/|rm -rf|rm -r' "$build" "$run"; then
  echo 'red proof failed: machine path or destructive profile cleanup remains' >&2
  exit 1
fi

for marker in configuredSurfaceURL redactedURL 'components.user = nil' 'components.password = nil' OMI_SURFACE_QUERY OMI_SURFACE_PROFILE "removeAll { \$0.name == \"profile\" }" 'served > 0' 'phase != "ready-timeout"' Darwin.exit; do
  rg -F -q "$marker" "$swift"
done
for marker in SURFACE_QUERY SURFACE_PROFILE "userInfo: ''" OMI_ACCEPTANCE_EXIT 'served > 0' 'ready-timeout' data-production-shell data-route data-surface-state; do
  rg -F -q "$marker" "$dart"
done
for marker in OMI_READY_TIMEOUT_SECONDS OMI_ACCEPTANCE_WAIT_SECONDS acceptance_wait_timeout 'curl --fail' '127.0.0.1' "\"\$executable\"" "wait \"\$pid\"" "exit \"\$child_status\"" timeout_marker watchdog_pid '.run.log'; do
  rg -F -q "$marker" "$run"
done
if rg -n 'kill[[:space:]]+(-9|-TERM)[[:space:]]+-1|pkill.*\$app_name' "$run"; then
  echo 'red proof failed: acceptance cleanup can target processes beyond the launched child' >&2
  exit 1
fi
if rg -n '(^|[[:space:]])open -n' "$run"; then
  echo 'red proof failed: LaunchServices open would drop shell environment' >&2
  exit 1
fi
# Token values may be used for privileged custody, but never appear in
# acceptance/profile output or shell status lines.
if rg -n 'ACCEPTANCE.*(_apiToken|OMI_API_TOKEN|token=)' "$swift" "$dart"; then
  echo 'red proof failed: acceptance output may leak a credential' >&2
  exit 1
fi

echo 'qa-plumbing: PASS (safe app name, query/profile namespace, acceptance exit, generic selectors)'
