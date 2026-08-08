#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REHEARSAL="$SCRIPT_DIR/../scripts/rehearse-desktop-release.sh"

bash -n "$REHEARSAL"
help_output="$("$REHEARSAL" --help)"
[[ "$help_output" == *"intentionally manual"* ]]
[[ "$help_output" == *"never dispatches Codemagic"* ]]

set +e
invalid_output="$("$REHEARSAL" --codemagic-build-id invalid 2>&1)"
invalid_status=$?
set -e
[[ "$invalid_status" -ne 0 ]]
[[ "$invalid_output" == *"must be 24 lowercase hexadecimal characters"* ]]

! rg -n -- '--request[[:space:]]+POST|gh[[:space:]]+release|gh[[:space:]]+workflow[[:space:]]+run' "$REHEARSAL"
rg -q '\[\[ "\$provider_status" == "failed" \]\]' "$REHEARSAL"
rg -Fq 'storage[.]googleapis[.]com/codemagic-build-artifacts' "$REHEARSAL"
rg -q 'expected exactly one failed Codemagic step' "$REHEARSAL"
rg -q 'expected exactly one \$artifact_name artifact' "$REHEARSAL"
rg -q -- '--expected-bundle-id com.omi.computer-macos.beta' "$REHEARSAL"
rg -q -- '--expected-feed-url.*identity=beta' "$REHEARSAL"
rg -q -- '--expected-python-api-url.*api.omiapi.com' "$REHEARSAL"
rg -q 'CODEMAGIC_API_TOKEN.*unsupported characters' "$REHEARSAL"
rg -q 'artifact_name="Omi.app.zip"' "$REHEARSAL"
rg -q 'audit-desktop-bundle-deps.sh' "$REHEARSAL"

echo "PASS: desktop release rehearsal is manual, fail-closed, and non-publishing"
