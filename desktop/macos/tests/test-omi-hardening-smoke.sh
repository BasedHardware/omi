#!/usr/bin/env bash
# Hermetic tests for scripts/omi-hardening-smoke.sh — no live app, no bridge,
# no defaults writes. Verifies CLI contract, prod refusal (with proof of zero
# side effects), dry-run summary schema, and the credential scanner.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MACOS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SMOKE="$MACOS_DIR/scripts/omi-hardening-smoke.sh"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

TMP="$(mktemp -d)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

# 1. Syntax + help + unknown command exits.
bash -n "$SMOKE" || fail "bash -n rejected the script"
"$SMOKE" help >"$TMP/help.out" 2>&1 || fail "help exited nonzero"
for word in run list scan help; do
  grep -q "$word" "$TMP/help.out" || fail "help does not mention '$word'"
done
if "$SMOKE" definitely-not-a-command >/dev/null 2>&1; then
  fail "unknown command unexpectedly succeeded"
fi

# 2. list emits the canonical destructive-last probe order.
"$SMOKE" list >"$TMP/list.out"
printf 'auth-06\nset-04\nset-01\nmic-06\nchat-03\nauth-03\nlnch-07\nself-hygiene\n' >"$TMP/list.want"
diff -u "$TMP/list.want" "$TMP/list.out" >/dev/null || fail "probe list/order drifted from canonical"

# 3. Prod refusal, and proof it happens BEFORE any side effect: stub every
#    side-effectful binary so touching one leaves a sentinel.
mkdir -p "$TMP/stubs"
for tool in defaults curl nc sqlite3 pgrep; do
  cat >"$TMP/stubs/$tool" <<EOF
#!/bin/bash
touch "$TMP/side-effect-$tool"
exit 0
EOF
  chmod +x "$TMP/stubs/$tool"
done
if PATH="$TMP/stubs:$PATH" "$SMOKE" run --bundle-id com.omi.computer-macos >"$TMP/prod.out" 2>&1; then
  fail "production bundle was not refused"
fi
grep -q "refusing" "$TMP/prod.out" || fail "prod refusal did not print a refusal message"
ls "$TMP"/side-effect-* >/dev/null 2>&1 && fail "prod refusal touched a side-effectful tool before exiting"
# Non-omi-* test bundles (incl. the shared dev profile) are refused too.
if "$SMOKE" run --bundle-id com.omi.desktop-dev >/dev/null 2>&1; then
  fail "non omi-* bundle was not refused"
fi

# 4. Unknown probe id → usage error (exit 2).
set +e
"$SMOKE" run --only bogus-probe >/dev/null 2>&1
rc=$?
set -e
[ "$rc" -eq 2 ] || fail "unknown --only probe returned $rc, want 2"

# 5. Dry-run: no launch, summary JSON with schema, canonical order, all SKIP.
"$SMOKE" run --dry-run --report-dir "$TMP/report" >/dev/null 2>&1 || fail "dry-run exited nonzero"
[ -f "$TMP/report/smoke-summary.json" ] || fail "dry-run wrote no summary JSON"
python3 - "$TMP/report/smoke-summary.json" <<'PY' || fail "summary JSON schema check failed"
import json, sys
d = json.load(open(sys.argv[1]))
required = {"started", "finished", "bundle", "port", "git_sha", "exit_code", "probes"}
missing = required - set(d)
assert not missing, f"missing keys: {missing}"
ids = [p["id"] for p in d["probes"]]
want = ["auth-06", "set-04", "set-01", "mic-06", "chat-03", "auth-03", "lnch-07", "self-hygiene"]
assert ids == want, f"probe order drifted: {ids}"
assert all(p["status"] == "SKIP" for p in d["probes"]), "dry-run probes must all be SKIP"
assert all(set(p) >= {"id", "status", "duration_s", "reason"} for p in d["probes"])
PY

# 6. scan: clean dir passes; each credential pattern is detected.
mkdir -p "$TMP/clean"
echo "nothing sensitive here" >"$TMP/clean/note.txt"
"$SMOKE" scan "$TMP/clean" >/dev/null 2>&1 || fail "scan flagged a clean directory"

i=0
while IFS= read -r pattern; do
  i=$((i + 1))
  dir="$TMP/dirty-$i"
  mkdir -p "$dir"
  printf 'leaked %s end\n' "$pattern" >"$dir/evidence.log"
  set +e
  "$SMOKE" scan "$dir" >/dev/null 2>&1
  rc=$?
  set -e
  [ "$rc" -eq 1 ] || fail "scan missed planted credential pattern #$i (rc=$rc)"
done <<'PATTERNS'
eyJhbGciOiJSUzI1NiIsImtpZCI6IjEyMzQ1Njc4OTAxMjM0NTY3ODkwIn0
AIzaSyA1234567890abcdefghijklmnopqrstu
Bearer abcdefghijklmnopqrstuvwx
omi_mcp_abcdef12345678
omi_auto_abcdef1234567890abcd
AMf-abcdefghijklmnopqrstuv
refreshToken: abcdefghijklmnopqrstu/+123
PATTERNS
[ "$i" -eq 7 ] || fail "expected 7 planted patterns, tested $i"

echo "omi-hardening-smoke hermetic tests passed"
