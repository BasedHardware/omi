#!/usr/bin/env bash
# PR #6946 Per-Router Auth — Batch API Test Suite
# Tests all endpoints affected by the per-router auth migration.
#
# Uses rfsh (runflow) CSV format for endpoint definitions,
# and parallel execution via bash for compatibility.
#
# Usage:
#   ./test_pr6946_auth.sh [BASE_URL] [ADMIN_KEY]
#
# Defaults:
#   BASE_URL=http://localhost:10160
#   ADMIN_KEY=123

set -euo pipefail

BASE_URL="${1:-http://localhost:10160}"
ADMIN_KEY="${2:-123}"
TEST_UID="testuser"
RESULTS_DIR="/tmp/pr6946-test-results"
CONCURRENT="${CONCURRENT:-16}"

mkdir -p "$RESULTS_DIR"
rm -f "$RESULTS_DIR"/result_*.log

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  PR #6946 Per-Router Auth — Batch API Test                  ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Base URL:    $BASE_URL"
echo "║  Admin Key:   ${ADMIN_KEY:0:3}***"
echo "║  Concurrency: $CONCURRENT"
echo "╚══════════════════════════════════════════════════════════════╝"
echo

# ─── Phase 1: Extract endpoints from OpenAPI ────────────────────────────────

echo "▶ Phase 1: Extracting endpoints from OpenAPI spec..."

curl -sf "$BASE_URL/openapi.json" > "$RESULTS_DIR/openapi.json" || {
    echo "ERROR: Cannot reach $BASE_URL — is the backend running?"
    exit 1
}

python3 - "$RESULTS_DIR" "$BASE_URL" << 'PYEOF'
import json, csv, re, sys

results_dir = sys.argv[1]
base_url = sys.argv[2]

with open(f"{results_dir}/openapi.json") as f:
    spec = json.load(f)

# Known public endpoints (no auth deps in per-router pattern)
known_public_prefixes = [
    '/v1/approved-apps', '/v1/firmware/', '/v2/firmware/',
    '/v1/updates/', '/v1/auth/',
    '/v1/apps/{app_id}/reviews',
    '/v1/app-categories', '/v1/app-capabilities', '/v1/app/payment-plans',
    '/v1/app/proactive-notification-scopes',
    '/v1/apps/popular', '/v1/apps/public/',
    '/v2/apps', '/v2/apps/',
    '/v1/conversations/{conversation_id}/shared',
    '/v1/fair-use/case/',
    '/v1/payments/cancel', '/v1/payments/success', '/v1/payments/portal-return',
    '/v1/summary-app-ids',
    '/v1/trends', '/v2/desktop/',
    '/v1/announcements',
]

# Mixed-mode endpoints: skip from both tests (some routes public, some authed)
mixed_mode_skip = [
    '/v1/personas/',
]

# Endpoints that use non-Firebase auth (API keys, admin tokens, webhooks)
# These should be excluded from both "expect 401" and "expect Firebase pass" tests
non_firebase_auth = [
    '/v1/dev/',          # API key auth (X-API-Key header)
    '/v1/mcp/',          # MCP key auth
    '/v2/integrations/', # App integration API key auth
    '/v1/admin/',        # Admin key auth
    '/v1/apps/{app_id}/approve', '/v1/apps/{app_id}/reject',
    '/v1/apps/{app_id}/popular', '/v1/apps/tester',
    '/v1/summary-app-ids/', '/v2/desktop/clear-cache',
    '/v1/notification', '/v1/integrations/notification',
    '/v1/agents/', '/v1/phone/twiml',
    '/v1/action-items/shared/', # Token-based sharing
    '/metrics', '/token', '/authorize',
    '/v1/health',
    '/v1/oauth/',         # OAuth callbacks (no Firebase)
    '/v1/stripe/',        # Stripe webhooks
    '/v1/users/developer/webhook', # Developer webhooks (Firebase auth)
    '/v1/announcements/', # Actually Firebase-authed (dismiss, pending)
]

# Skip WebSocket/streaming endpoints (not testable with curl)
skip_patterns = ['/listen', '/messages', '/v1/pusher/', '/v2/listen', '/v4/listen']

def resolve_path(path):
    """Replace path params with test values."""
    replacements = {
        '{app_id}': 'test-app-id',
        '{conversation_id}': 'test-conv-id',
        '{memory_id}': 'test-mem-id',
        '{action_item_id}': 'test-ai-id',
        '{uid}': 'testuser',
        '{folder_id}': 'test-folder-id',
        '{goal_id}': 'test-goal-id',
        '{session_id}': 'test-session-id',
        '{job_id}': 'test-job-id',
        '{person_id}': 'test-person-id',
        '{notification_id}': 'test-notif-id',
        '{meeting_id}': 'test-meeting-id',
        '{call_id}': 'test-call-id',
    }
    result = path
    for k, v in replacements.items():
        result = result.replace(k, v)
    result = re.sub(r'\{[^}]+\}', 'test-param', result)
    return result

public_endpoints = []
auth_endpoints = []

for path, methods in sorted(spec['paths'].items()):
    for method, details in methods.items():
        if method in ('parameters', 'servers'):
            continue
        if any(s in path for s in skip_patterns):
            continue

        tags = details.get('tags', ['unknown'])
        tag = tags[0] if tags else 'unknown'
        test_path = resolve_path(path)
        # Exceptions: these look public by prefix but are actually authed
        auth_exceptions = ['/v2/apps/search']
        is_auth_exception = path in auth_exceptions
        is_mixed = any(path.startswith(p) or p in path for p in mixed_mode_skip)
        is_public = (not is_auth_exception) and (not is_mixed) and any(path.startswith(p) or p in path for p in known_public_prefixes)
        is_non_firebase = is_mixed or any(path.startswith(p) or p in path for p in non_firebase_auth)

        entry = {
            'method': method.upper(),
            'url': f"{base_url}{test_path}",
            'path': path,
            'tag': tag,
        }

        if is_non_firebase:
            pass  # Skip: uses different auth (API key, admin, webhook)
        elif is_public:
            public_endpoints.append(entry)
        else:
            auth_endpoints.append(entry)

# Write rfsh-compatible CSVs
def write_csv(filename, rows):
    with open(f"{results_dir}/{filename}", 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['method', 'url', 'path', 'tag'])
        w.writeheader()
        w.writerows(rows)

write_csv('endpoints_public.csv', public_endpoints)
write_csv('endpoints_auth.csv', auth_endpoints)

print(f"  Auth-required endpoints: {len(auth_endpoints)}")
print(f"  Public endpoints: {len(public_endpoints)}")
print(f"  Total: {len(auth_endpoints) + len(public_endpoints)}")
PYEOF

# ─── Phase 2: Test functions ────────────────────────────────────────────────

PASS=0
FAIL=0
TOTAL=0

test_endpoint() {
    local method="$1" url="$2" path="$3" tag="$4"
    local expected_code="$5" auth_header="$6" label="$7"

    local args=(-s -o /dev/null -w "%{http_code}" -X "$method")
    if [ -n "$auth_header" ]; then
        args+=(-H "Authorization: $auth_header")
    fi
    # Add empty body for POST/PUT/PATCH to avoid 422
    if [[ "$method" == "POST" || "$method" == "PUT" || "$method" == "PATCH" ]]; then
        args+=(-H "Content-Type: application/json" -d '{}')
    fi

    local code
    code=$(curl "${args[@]}" "$url" 2>/dev/null) || code="000"

    local result
    if [ "$expected_code" = "401" ]; then
        if [ "$code" = "401" ]; then
            result="PASS"
        else
            result="FAIL"
        fi
    elif [ "$expected_code" = "!401" ]; then
        if [ "$code" != "401" ]; then
            result="PASS"
        else
            result="FAIL"
        fi
    fi

    echo "$result|$label|$method|$path|$tag|expected=$expected_code|got=$code"
}

run_batch() {
    local label="$1" csv_file="$2" expected="$3" auth_header="$4"
    local log_file="$RESULTS_DIR/result_${label}.log"
    local count=0
    local batch_pass=0 batch_fail=0

    # Read CSV (skip header)
    local endpoints=()
    while IFS=',' read -r method url path tag; do
        endpoints+=("$method|$url|$path|$tag")
        count=$((count + 1))
    done < <(tail -n +2 "$csv_file")

    echo "─── $label ($count endpoints, concurrency=$CONCURRENT) ───"

    # Run in parallel batches
    local pids=() results_file
    results_file=$(mktemp)

    for entry in "${endpoints[@]}"; do
        IFS='|' read -r method url path tag <<< "$entry"
        (
            test_endpoint "$method" "$url" "$path" "$tag" "$expected" "$auth_header" "$label"
        ) >> "$results_file" &
        pids+=($!)

        # Limit concurrency
        if [ ${#pids[@]} -ge "$CONCURRENT" ]; then
            wait "${pids[0]}" 2>/dev/null || true
            pids=("${pids[@]:1}")
        fi
    done

    # Wait for remaining
    for pid in "${pids[@]}"; do
        wait "$pid" 2>/dev/null || true
    done

    # Count results
    cp "$results_file" "$log_file"
    batch_pass=$(grep -c "^PASS" "$log_file" || true)
    batch_fail=$(grep -c "^FAIL" "$log_file" || true)
    batch_pass=${batch_pass:-0}
    batch_fail=${batch_fail:-0}
    PASS=$((PASS + batch_pass))
    FAIL=$((FAIL + batch_fail))
    TOTAL=$((TOTAL + count))

    echo "  ✓ $batch_pass PASS  ✗ $batch_fail FAIL"

    if [ "$batch_fail" -gt 0 ]; then
        echo "  Failures:"
        grep "^FAIL" "$log_file" | head -10 | while IFS='|' read -r _ lbl method path tag exp got; do
            echo "    $method $path ($exp $got)"
        done
    fi
    echo
    rm -f "$results_file"
}

# ─── Phase 3: Execute tests ─────────────────────────────────────────────────

echo
echo "▶ Phase 3: Running batch tests..."
echo

# Test 1: Auth-required endpoints WITHOUT auth → must return 401
run_batch "noauth_expect_401" "$RESULTS_DIR/endpoints_auth.csv" "401" ""

# Test 2: Auth-required endpoints WITH valid auth → must NOT return 401
run_batch "auth_expect_pass" "$RESULTS_DIR/endpoints_auth.csv" "!401" "Bearer ${ADMIN_KEY}${TEST_UID}"

# Test 3: Public endpoints WITHOUT auth → must NOT return 401
run_batch "public_no_auth" "$RESULTS_DIR/endpoints_public.csv" "!401" ""

# ─── Phase 4: Summary ──────────────────────────────────────────────────────

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  SUMMARY                                                     ║"
echo "╠══════════════════════════════════════════════════════════════╣"
printf "║  Total tests:  %d\n" "$TOTAL"
printf "║  Passed:       %d\n" "$PASS"
printf "║  Failed:       %d\n" "$FAIL"

if [ "$FAIL" -gt 0 ]; then
    echo "║  Status:       FAILURES DETECTED"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo
    echo "All failures:"
    grep "^FAIL" "$RESULTS_DIR"/result_*.log 2>/dev/null | sort
    exit 1
else
    echo "║  Status:       ALL PASS"
    echo "╚══════════════════════════════════════════════════════════════╝"
fi

# ─── Phase 5: rfsh-compatible export ───────────────────────────────────────

# Generate combined CSV report (rfsh output format)
echo
echo "Results saved to: $RESULTS_DIR/"
echo "  endpoints_auth.csv    — rfsh input (auth-required endpoints)"
echo "  endpoints_public.csv  — rfsh input (public endpoints)"
echo "  result_*.log          — per-batch results"
