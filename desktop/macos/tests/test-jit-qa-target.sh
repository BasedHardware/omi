#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/jit-qa-target.sh"

expect_failure() {
    local output
    if output="$("$@" 2>&1)"; then
        echo "FAIL: expected command to fail: $*" >&2
        exit 1
    fi
    if grep -q 'Traceback' <<< "$output"; then
        echo "FAIL: expected controlled failure without traceback: $*" >&2
        exit 1
    fi
}

expect_launcher_failure_before_stop() {
    local output
    if output="$(env \
        -u OMI_JIT_QA_TARGET \
        -u OMI_PYTHON_API_URL \
        -u OMI_DESKTOP_API_URL \
        -u OMI_AUTH_API_URL \
        -u OMI_ENV_STAGE \
        -u OMI_DESKTOP_LOCAL_PROFILE \
        "$@" "$ROOT/run.sh" --no-wait 2>&1)"; then
        echo "FAIL: expected reserved launcher invocation to fail: $*" >&2
        exit 1
    fi
    if grep -q 'Killing existing instances' <<< "$output"; then
        echo "FAIL: reserved launcher reached pkill preparation before rejecting: $*" >&2
        exit 1
    fi
}

clear_target_env() {
    unset OMI_JIT_QA_TARGET OMI_PYTHON_API_URL OMI_DESKTOP_API_URL OMI_AUTH_API_URL OMI_ENV_STAGE
    unset OMI_JIT_QA_CLOUD_RECEIPT_PATH OMI_JIT_QA_CLOUD_PYTHON_URL OMI_JIT_QA_CLOUD_DESKTOP_URL
    unset FIREBASE_API_KEY
    unset OMI_SKIP_BACKEND OMI_SKIP_TUNNEL
    unset OMI_SKIP_REWIND_SEED OMI_FORCE_REWIND_SEED
}

clear_target_env
export OMI_JIT_QA_TARGET=local-dev-gcp
omi_preflight_jit_qa_launch_request omi-jit-qa "" 0 false
omi_prepare_jit_qa_target omi-jit-qa com.omi.omi-jit-qa 0 initial
test "$OMI_PYTHON_API_URL" = "http://127.0.0.1:18080"
test "$OMI_DESKTOP_API_URL" = "http://127.0.0.1:18081"
test "$OMI_AUTH_API_URL" = "http://127.0.0.1:18080"
test "$OMI_ENV_STAGE" = dev
test "$FIREBASE_API_KEY" = "$OMI_JIT_QA_FIREBASE_API_KEY"
test "$OMI_SKIP_BACKEND" = 1
test "$OMI_SKIP_TUNNEL" = 1
test "$OMI_SKIP_REWIND_SEED" = 1

local_env="$(mktemp)"
dev_env=""
bad_env=""
exact_config=""
duplicate_config=""
cloud_receipt=""
cloud_env=""
cloud_symlink=""
cleanup() {
    rm -f "$local_env"
    [ -z "$dev_env" ] || rm -f "$dev_env"
    [ -z "$bad_env" ] || rm -f "$bad_env"
    [ -z "$exact_config" ] || rm -f "$exact_config"
    [ -z "$duplicate_config" ] || rm -f "$duplicate_config"
    [ -z "$cloud_receipt" ] || rm -f "$cloud_receipt"
    [ -z "$cloud_env" ] || rm -f "$cloud_env"
    [ -z "$cloud_symlink" ] || rm -f "$cloud_symlink"
}
trap cleanup EXIT

exact_config="$(mktemp)"
printf '%s\n' \
    'OMI_PYTHON_API_URL=http://127.0.0.1:18080' \
    'export OMI_DESKTOP_API_URL="http://127.0.0.1:18081"' \
    "OMI_AUTH_API_URL='http://127.0.0.1:18080'" \
    'OMI_ENV_STAGE=dev' > "$exact_config"
omi_preflight_jit_qa_config_file "$exact_config"

bad_env="$(mktemp)"
printf '%s\n' 'OMI_PYTHON_API_URL=https://api.omi.me' > "$bad_env"
expect_failure omi_preflight_jit_qa_config_file "$bad_env"
printf '%s\n' 'FIREBASE_API_KEY=wrong-client-key' > "$bad_env"
expect_failure omi_preflight_jit_qa_config_file "$bad_env"

duplicate_config="$(mktemp)"
printf '%s\n' \
    'OMI_ENV_STAGE=dev' \
    'export OMI_ENV_STAGE=dev' > "$duplicate_config"
expect_failure omi_preflight_jit_qa_config_file "$duplicate_config"

printf '%s\n' 'OMI_PYTHON_API_URL=https://api.omi.me' 'OMI_AUTH_API_URL=https://api.omi.me' > "$local_env"
omi_write_jit_qa_bundle_env "$local_env"
grep -Fqx 'OMI_PYTHON_API_URL=http://127.0.0.1:18080' "$local_env"
grep -Fqx 'OMI_DESKTOP_API_URL=http://127.0.0.1:18081' "$local_env"
grep -Fqx 'OMI_AUTH_API_URL=http://127.0.0.1:18080' "$local_env"
grep -Fqx 'OMI_ENV_STAGE=dev' "$local_env"
grep -Fqx "FIREBASE_API_KEY=$OMI_JIT_QA_FIREBASE_API_KEY" "$local_env"
if grep -q 'api\.omi\.me' "$local_env"; then
    echo "FAIL: local tuple retained the production API host" >&2
    exit 1
fi

clear_target_env
export OMI_JIT_QA_TARGET=deployed-dev
omi_prepare_jit_qa_target omi-jit-qa com.omi.omi-jit-qa 0 initial
test "$OMI_PYTHON_API_URL" = "https://api.omiapi.com"
test "$OMI_DESKTOP_API_URL" = "https://desktop-backend-dt5lrfkkoa-uc.a.run.app"
test "$OMI_AUTH_API_URL" = "https://api.omiapi.com"

dev_env="$(mktemp)"
: > "$dev_env"
omi_write_jit_qa_bundle_env "$dev_env"
grep -Fqx 'OMI_PYTHON_API_URL=https://api.omiapi.com' "$dev_env"
grep -Fqx 'OMI_DESKTOP_API_URL=https://desktop-backend-dt5lrfkkoa-uc.a.run.app' "$dev_env"
grep -Fqx 'OMI_AUTH_API_URL=https://api.omiapi.com' "$dev_env"
grep -Fqx "FIREBASE_API_KEY=$OMI_JIT_QA_FIREBASE_API_KEY" "$dev_env"
if grep -q 'api\.omi\.me' "$dev_env"; then
    echo "FAIL: deployed-dev tuple retained the production API host" >&2
    exit 1
fi

cloud_receipt="$(mktemp)"
cp "$ROOT/tests/fixtures/jit-qa/cloud-receipt-v1.json" "$cloud_receipt"
clear_target_env
export OMI_JIT_QA_TARGET=cloud-qa
export OMI_JIT_QA_CLOUD_RECEIPT_PATH="$cloud_receipt"
export OMI_JIT_QA_CLOUD_PYTHON_URL="https://backend-jit-qa-rev123-uc.a.run.app"
export OMI_JIT_QA_CLOUD_DESKTOP_URL="https://desktop-backend-jit-qa-rev123-uc.a.run.app"
omi_preflight_jit_qa_launch_request omi-jit-qa "" 0 false
omi_prepare_jit_qa_target omi-jit-qa com.omi.omi-jit-qa 0 initial
test "$OMI_PYTHON_API_URL" = "$OMI_JIT_QA_CLOUD_PYTHON_URL"
test "$OMI_DESKTOP_API_URL" = "$OMI_JIT_QA_CLOUD_DESKTOP_URL"
test "$OMI_AUTH_API_URL" = "$OMI_JIT_QA_CLOUD_PYTHON_URL"
test "$OMI_ENV_STAGE" = dev
test "$OMI_SKIP_BACKEND" = 1
test "$OMI_SKIP_TUNNEL" = 1
test "$OMI_SKIP_REWIND_SEED" = 1

# The same producer receipt also round-trips through Cloud Run's newer
# deterministic regional URL form.
sed -i '' \
    -e 's|https://backend-jit-qa-rev123-uc.a.run.app|https://backend-jit-qa-123456789012.us-central1.run.app|g' \
    -e 's|https://desktop-backend-jit-qa-rev123-uc.a.run.app|https://desktop-backend-jit-qa-123456789012.us-central1.run.app|g' \
    -e 's|https://llm-gateway-jit-qa-rev123-uc.a.run.app|https://llm-gateway-jit-qa-123456789012.us-central1.run.app|g' \
    "$cloud_receipt"
clear_target_env
export OMI_JIT_QA_TARGET=cloud-qa
export OMI_JIT_QA_CLOUD_RECEIPT_PATH="$cloud_receipt"
export OMI_JIT_QA_CLOUD_PYTHON_URL="https://backend-jit-qa-123456789012.us-central1.run.app"
export OMI_JIT_QA_CLOUD_DESKTOP_URL="https://desktop-backend-jit-qa-123456789012.us-central1.run.app"
omi_preflight_jit_qa_launch_request omi-jit-qa "" 0 false
omi_prepare_jit_qa_target omi-jit-qa com.omi.omi-jit-qa 0 initial
test "$OMI_PYTHON_API_URL" = "$OMI_JIT_QA_CLOUD_PYTHON_URL"
test "$OMI_DESKTOP_API_URL" = "$OMI_JIT_QA_CLOUD_DESKTOP_URL"

# Restore the legacy deterministic fixture values for the negative cases below.
sed -i '' \
    -e 's|https://backend-jit-qa-123456789012.us-central1.run.app|https://backend-jit-qa-rev123-uc.a.run.app|g' \
    -e 's|https://desktop-backend-jit-qa-123456789012.us-central1.run.app|https://desktop-backend-jit-qa-rev123-uc.a.run.app|g' \
    -e 's|https://llm-gateway-jit-qa-123456789012.us-central1.run.app|https://llm-gateway-jit-qa-rev123-uc.a.run.app|g' \
    "$cloud_receipt"
export OMI_JIT_QA_CLOUD_PYTHON_URL="https://backend-jit-qa-rev123-uc.a.run.app"
export OMI_JIT_QA_CLOUD_DESKTOP_URL="https://desktop-backend-jit-qa-rev123-uc.a.run.app"

cloud_env="$(mktemp)"
printf '%s\n' \
    'OMI_PYTHON_API_URL=https://api.omiapi.com' \
    'OMI_DESKTOP_API_URL=https://desktop-backend-dt5lrfkkoa-uc.a.run.app' \
    'OMI_AUTH_API_URL=https://api.omiapi.com' > "$cloud_env"
omi_write_jit_qa_bundle_env "$cloud_env"
grep -Fqx "OMI_PYTHON_API_URL=$OMI_JIT_QA_CLOUD_PYTHON_URL" "$cloud_env"
grep -Fqx "OMI_DESKTOP_API_URL=$OMI_JIT_QA_CLOUD_DESKTOP_URL" "$cloud_env"
grep -Fqx "OMI_AUTH_API_URL=$OMI_JIT_QA_CLOUD_PYTHON_URL" "$cloud_env"

clear_target_env
export OMI_JIT_QA_TARGET=cloud-qa
export OMI_JIT_QA_CLOUD_RECEIPT_PATH="$cloud_receipt"
export OMI_JIT_QA_CLOUD_PYTHON_URL="https://api.omiapi.com"
export OMI_JIT_QA_CLOUD_DESKTOP_URL="https://desktop-backend-jit-qa-rev123-uc.a.run.app"
expect_failure omi_preflight_jit_qa_launch_request omi-jit-qa "" 0 false
export OMI_JIT_QA_CLOUD_PYTHON_URL="https://backend-jit-qa-rev123-uc.a.run.app"
export OMI_JIT_QA_CLOUD_DESKTOP_URL="https://desktop-backend-dt5lrfkkoa-uc.a.run.app"
expect_failure omi_preflight_jit_qa_launch_request omi-jit-qa "" 0 false
export OMI_JIT_QA_CLOUD_DESKTOP_URL="https://desktop-backend-jit-qa-rev123-uc.a.run.app"
unset OMI_JIT_QA_CLOUD_RECEIPT_PATH
expect_failure omi_preflight_jit_qa_launch_request omi-jit-qa "" 0 false
export OMI_JIT_QA_CLOUD_RECEIPT_PATH="$cloud_receipt"
export OMI_JIT_QA_CLOUD_PYTHON_URL="https://backend-jit-qa-rev456-uc.a.run.app"
expect_failure omi_preflight_jit_qa_launch_request omi-jit-qa "" 0 false
export OMI_JIT_QA_CLOUD_PYTHON_URL="https://backend-jit-qa-rev123-uc.a.run.app"
export OMI_JIT_QA_CLOUD_DESKTOP_URL="https://desktop-backend-jit-qa-rev456-uc.a.run.app"
expect_failure omi_preflight_jit_qa_launch_request omi-jit-qa "" 0 false
export OMI_JIT_QA_CLOUD_DESKTOP_URL="https://desktop-backend-jit-qa-rev123-uc.a.run.app"
for dependency in firestore redis gateway typesense firebase_auth storage pubsub scheduler; do
    cp "$ROOT/tests/fixtures/jit-qa/cloud-receipt-v1.json" "$cloud_receipt"
    python3 - "$cloud_receipt" "$dependency" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
receipt = json.loads(path.read_text())
receipt["dependency_vector"][sys.argv[2]] = "shared-production-dependency"
path.write_text(json.dumps(receipt))
PY
    expect_failure omi_preflight_jit_qa_launch_request omi-jit-qa "" 0 false
done
cp "$ROOT/tests/fixtures/jit-qa/cloud-receipt-v1.json" "$cloud_receipt"
export OMI_JIT_QA_CLOUD_RECEIPT_PATH="${cloud_receipt}.missing"
expect_failure omi_preflight_jit_qa_launch_request omi-jit-qa "" 0 false
cloud_symlink="${cloud_receipt}.link"
ln -s "$cloud_receipt" "$cloud_symlink"
export OMI_JIT_QA_CLOUD_RECEIPT_PATH="$cloud_symlink"
expect_failure omi_preflight_jit_qa_launch_request omi-jit-qa "" 0 false
export OMI_JIT_QA_CLOUD_RECEIPT_PATH="$cloud_receipt"
sed -i '' 's/"project": "based-hardware-dev"/"project": "based-hardware"/' "$cloud_receipt"
expect_failure omi_preflight_jit_qa_launch_request omi-jit-qa "" 0 false
sed -i '' 's/"project": "based-hardware"/"project": "based-hardware-dev"/' "$cloud_receipt"
sed -i '' 's/"reviewed": true/"reviewed": false/' "$cloud_receipt"
expect_failure omi_preflight_jit_qa_launch_request omi-jit-qa "" 0 false
sed -i '' 's/"reviewed": false/"reviewed": true/' "$cloud_receipt"
sed -i '' 's/"full_source_sha": "[^"]*"/"full_source_sha": "not-a-commit"/' "$cloud_receipt"
expect_failure omi_preflight_jit_qa_launch_request omi-jit-qa "" 0 false
sed -i '' 's/"full_source_sha": "not-a-commit"/"full_source_sha": "60635449cf595ea6078cd0f716989a0d15d45c13"/' "$cloud_receipt"
sed -i '' 's/"firestore_database_id": "jit-qa"/"firestore_database_id": "wrong"/' "$cloud_receipt"
expect_failure omi_preflight_jit_qa_launch_request omi-jit-qa "" 0 false
sed -i '' 's/"firestore_database_id": "wrong"/"firestore_database_id": "jit-qa"/' "$cloud_receipt"
sed -i '' 's/"exact_gateway_url": "[^"]*"/"exact_gateway_url": "https:\/\/gateway.example"/' "$cloud_receipt"
expect_failure omi_preflight_jit_qa_launch_request omi-jit-qa "" 0 false
sed -i '' 's|"exact_gateway_url": "https://gateway.example"|"exact_gateway_url": "https://llm-gateway-jit-qa-rev123-uc.a.run.app"|' "$cloud_receipt"
printf '%s\n' '[]' > "$cloud_receipt"
expect_failure omi_preflight_jit_qa_launch_request omi-jit-qa "" 0 false

clear_target_env
expect_failure omi_preflight_jit_qa_launch_request omi-jit-qa "" 0 false
expect_failure omi_preflight_jit_qa_launch_request omi-other com.omi.omi-jit-qa 0 false
export OMI_JIT_QA_TARGET=deployed-dev
expect_failure omi_preflight_jit_qa_launch_request omi-other "" 0 false
expect_failure omi_preflight_jit_qa_launch_request omi-jit-qa com.example.wrong 0 false
expect_failure omi_preflight_jit_qa_launch_request omi-jit-qa "" 1 false
expect_failure omi_preflight_jit_qa_launch_request omi-jit-qa "" 0 true
clear_target_env
export OMI_JIT_QA_TARGET=local-dev-gcp OMI_SKIP_REWIND_SEED=0
expect_failure omi_preflight_jit_qa_launch_request omi-jit-qa "" 0 false
clear_target_env
export OMI_JIT_QA_TARGET=local-dev-gcp OMI_FORCE_REWIND_SEED=1
expect_failure omi_preflight_jit_qa_launch_request omi-jit-qa "" 0 false
clear_target_env
export OMI_JIT_QA_TARGET=deployed-dev OMI_PYTHON_API_URL=https://api.omi.me
expect_failure omi_preflight_jit_qa_launch_request omi-jit-qa "" 0 false
expect_failure omi_prepare_jit_qa_target omi-jit-qa com.omi.omi-jit-qa 0 initial
clear_target_env
export OMI_JIT_QA_TARGET=deployed-dev FIREBASE_API_KEY=wrong-client-key
expect_failure omi_preflight_jit_qa_launch_request omi-jit-qa "" 0 false
expect_failure omi_prepare_jit_qa_target omi-jit-qa com.omi.omi-jit-qa 0 initial
clear_target_env
expect_failure omi_prepare_jit_qa_target omi-jit-qa com.omi.omi-jit-qa 0 initial
expect_failure omi_prepare_jit_qa_target omi-other com.omi.omi-jit-qa 0 initial
export OMI_JIT_QA_TARGET=deployed-dev
expect_failure omi_prepare_jit_qa_target omi-other com.omi.omi-other 0 initial
expect_failure omi_prepare_jit_qa_target omi-jit-qa com.omi.omi-jit-qa 1 initial
expect_failure omi_prepare_jit_qa_target omi-jit-qa com.omi.omi-jit-qa 0 initial true
clear_target_env
export OMI_JIT_QA_TARGET=unknown
expect_failure omi_prepare_jit_qa_target omi-jit-qa com.omi.omi-jit-qa 0 initial

printf '%s\n' 'OMI_PYTHON_API_URL=https://api.omi.me' > "$bad_env"
export OMI_JIT_QA_TARGET=deployed-dev
omi_write_jit_qa_bundle_env "$bad_env"
if grep -q 'api\.omi\.me' "$bad_env"; then
    echo "FAIL: tuple rewrite retained a stale production API host" >&2
    exit 1
fi

grep -q 'OMI_JIT_QA_TARGET' "$ROOT/run.sh"
grep -q 'omi_write_jit_qa_bundle_env' "$ROOT/run.sh"
grep -q 'OMI_AUTH_API_URL' "$ROOT/run.sh"
grep -Fq 'cd "$MACOS_ROOT"' "$ROOT/scripts/omi-jit-qa"
grep -Fq 'export OMI_SKIP_REWIND_SEED=1' "$ROOT/scripts/omi-jit-qa"
prepare_line="$(grep -n 'omi_prepare_jit_qa_target.*derived' "$ROOT/run.sh" | head -1 | cut -d: -f1)"
request_preflight_line="$(grep -n '^omi_preflight_jit_qa_launch_request' "$ROOT/run.sh" | head -1 | cut -d: -f1)"
dev_instance_line="$(grep -n 'source .*scripts/dev-instance.sh' "$ROOT/run.sh" | head -1 | cut -d: -f1)"
preflight_line="$(grep -n 'omi_preflight_jit_qa_config_file.*EARLY_BACKEND_DIR' "$ROOT/run.sh" | head -1 | cut -d: -f1)"
# shellcheck disable=SC2016
stop_line="$(grep -n '^pkill -f "\$APP_NAME.app"' "$ROOT/run.sh" | head -1 | cut -d: -f1)"
if [ -z "$request_preflight_line" ] || [ -z "$dev_instance_line" ] \
    || [ -z "$preflight_line" ] \
    || [ "$request_preflight_line" -ge "$dev_instance_line" ] \
    || [ "$preflight_line" -ge "$dev_instance_line" ]; then
    echo "FAIL: raw request and repo-config validation must happen before dev-instance mutation" >&2
    exit 1
fi
if [ -z "$prepare_line" ] || [ -z "$preflight_line" ] || [ -z "$stop_line" ] \
    || [ "$prepare_line" -ge "$stop_line" ] || [ "$preflight_line" -ge "$stop_line" ]; then
    echo "FAIL: JIT QA tuple and config validation must happen before stopping any running bundle" >&2
    exit 1
fi
if [ "$(grep -c 'omi_write_jit_qa_bundle_env' "$ROOT/run.sh")" -lt 2 ]; then
    echo "FAIL: both full and fast bundle paths must rewrite the exact JIT QA tuple" >&2
    exit 1
fi
for launch_key in OMI_PYTHON_API_URL OMI_DESKTOP_API_URL OMI_AUTH_API_URL OMI_ENV_STAGE; do
    if ! grep -q -- "--env \"${launch_key}=\$${launch_key}\"" "$ROOT/run.sh"; then
        echo "FAIL: open launch does not forward $launch_key" >&2
        exit 1
    fi
done

expect_launcher_failure_before_stop OMI_APP_NAME=omi-jit-qa
expect_launcher_failure_before_stop \
    OMI_APP_NAME=omi-jit-qa OMI_JIT_QA_TARGET=local-dev-gcp OMI_DESKTOP_LOCAL_PROFILE=1
expect_launcher_failure_before_stop \
    OMI_APP_NAME=omi-jit-qa OMI_JIT_QA_TARGET=deployed-dev OMI_PYTHON_API_URL=https://api.omi.me
expect_launcher_failure_before_stop \
    OMI_APP_NAME=omi-jit-qa OMI_JIT_QA_TARGET=local-dev-gcp OMI_FORCE_REWIND_SEED=1

# Direct run.sh entry (without scripts/omi-jit-qa) must derive the same
# privacy tuple before any bundle/profile mutation.
clear_target_env
export OMI_JIT_QA_TARGET=local-dev-gcp
omi_preflight_jit_qa_launch_request omi-jit-qa "" 0 false
omi_jit_qa_set_exact_tuple
test "$OMI_SKIP_REWIND_SEED" = 1

echo "PASS: JIT QA bundle target selection is atomic and production-host fail-closed"
