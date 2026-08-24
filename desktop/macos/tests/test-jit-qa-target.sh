#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/scripts/jit-qa-target.sh"

expect_failure() {
    if "$@" >/dev/null 2>&1; then
        echo "FAIL: expected command to fail: $*" >&2
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
test "$OMI_SKIP_BACKEND" = 1
test "$OMI_SKIP_TUNNEL" = 1
test "$OMI_SKIP_REWIND_SEED" = 1

local_env="$(mktemp)"
dev_env=""
bad_env=""
exact_config=""
duplicate_config=""
cleanup() {
    rm -f "$local_env"
    [ -z "$dev_env" ] || rm -f "$dev_env"
    [ -z "$bad_env" ] || rm -f "$bad_env"
    [ -z "$exact_config" ] || rm -f "$exact_config"
    [ -z "$duplicate_config" ] || rm -f "$duplicate_config"
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
if grep -q 'api\.omi\.me' "$dev_env"; then
    echo "FAIL: deployed-dev tuple retained the production API host" >&2
    exit 1
fi

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
