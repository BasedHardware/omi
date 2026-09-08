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

! grep -En -- '--request[[:space:]]+POST|gh[[:space:]]+release|gh[[:space:]]+workflow[[:space:]]+run' "$REHEARSAL"
grep -Eq '\[\[ "\$provider_status" == "failed" \]\]' "$REHEARSAL"
grep -Fq 'storage[.]googleapis[.]com/codemagic-build-artifacts' "$REHEARSAL"
grep -Eq 'expected exactly one failed Codemagic step' "$REHEARSAL"
grep -Eq 'expected exactly one \$artifact_name artifact' "$REHEARSAL"
grep -Eq -- '--expected-bundle-id com.omi.computer-macos.beta' "$REHEARSAL"
grep -Eq -- '--expected-feed-url.*identity=beta' "$REHEARSAL"
grep -Eq -- '--expected-python-api-url.*api.omiapi.com' "$REHEARSAL"
grep -Eq 'CODEMAGIC_API_TOKEN.*unsupported characters' "$REHEARSAL"
grep -Eq 'artifact_name="Omi.app.zip"' "$REHEARSAL"
grep -Eq 'audit-desktop-bundle-deps.sh' "$REHEARSAL"
grep -Fq '10#$clean_timeout_seconds' "$REHEARSAL"

echo "PASS: desktop release rehearsal is manual, fail-closed, and non-publishing"
