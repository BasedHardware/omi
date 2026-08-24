#!/usr/bin/env bash

# Fail-closed endpoint authority for the single `omi-jit-qa` bundle. The
# launcher selects one complete tuple; callers cannot mix individual endpoint
# overrides or inherit production defaults from a copied .env file.

OMI_JIT_QA_APP_NAME="omi-jit-qa"
OMI_JIT_QA_BUNDLE_ID="com.omi.omi-jit-qa"
OMI_JIT_QA_LOCAL_PYTHON_URL="http://127.0.0.1:18080"
OMI_JIT_QA_LOCAL_DESKTOP_URL="http://127.0.0.1:18081"
OMI_JIT_QA_DEV_PYTHON_URL="https://api.omiapi.com"
OMI_JIT_QA_DEV_DESKTOP_URL="https://desktop-backend-dt5lrfkkoa-uc.a.run.app"

omi_jit_qa_fail() {
    printf 'ERROR: JIT QA target: %s\n' "$1" >&2
    return 2
}

omi_jit_qa_set_exact_tuple() {
    case "${OMI_JIT_QA_TARGET:-}" in
        local-dev-gcp)
            export OMI_PYTHON_API_URL="$OMI_JIT_QA_LOCAL_PYTHON_URL"
            export OMI_DESKTOP_API_URL="$OMI_JIT_QA_LOCAL_DESKTOP_URL"
            export OMI_AUTH_API_URL="$OMI_JIT_QA_LOCAL_PYTHON_URL"
            ;;
        deployed-dev)
            export OMI_PYTHON_API_URL="$OMI_JIT_QA_DEV_PYTHON_URL"
            export OMI_DESKTOP_API_URL="$OMI_JIT_QA_DEV_DESKTOP_URL"
            export OMI_AUTH_API_URL="$OMI_JIT_QA_DEV_PYTHON_URL"
            ;;
        *)
            omi_jit_qa_fail "OMI_JIT_QA_TARGET must be local-dev-gcp or deployed-dev"
            return $?
            ;;
    esac
    export OMI_ENV_STAGE="dev"
    export OMI_SKIP_BACKEND=1
    export OMI_SKIP_TUNNEL=1
    # The reserved bundle is dev-routed. Its exact tuple therefore includes
    # an empty Rewind profile for every entry point, not only the convenience
    # wrapper. Never copy production screenshots/history into it.
    export OMI_SKIP_REWIND_SEED=1
}

# Validate the raw invocation before dev-instance creates its scratch directory
# or the launcher acquires a build lock. The fully derived identity is checked
# again by omi_prepare_jit_qa_target below.
omi_preflight_jit_qa_launch_request() {
    local requested_app_name="${1:-}"
    local requested_bundle_id="${2:-}"
    local yolo_mode="${3:-0}"
    local local_profile="${4:-false}"
    local reserved=false
    local variable_name

    if [ "$requested_app_name" = "$OMI_JIT_QA_APP_NAME" ] \
        || [ "$requested_bundle_id" = "$OMI_JIT_QA_BUNDLE_ID" ]; then
        reserved=true
    fi
    if [ -z "${OMI_JIT_QA_TARGET:-}" ] && [ "$reserved" = false ]; then
        return 0
    fi
    if [ -z "${OMI_JIT_QA_TARGET:-}" ]; then
        omi_jit_qa_fail "the reserved $OMI_JIT_QA_APP_NAME bundle requires OMI_JIT_QA_TARGET"
        return $?
    fi
    if [ "$requested_app_name" != "$OMI_JIT_QA_APP_NAME" ]; then
        omi_jit_qa_fail "OMI_JIT_QA_TARGET requires app name $OMI_JIT_QA_APP_NAME"
        return $?
    fi
    if [ -n "$requested_bundle_id" ] && [ "$requested_bundle_id" != "$OMI_JIT_QA_BUNDLE_ID" ]; then
        omi_jit_qa_fail "OMI_JIT_QA_TARGET requires bundle id $OMI_JIT_QA_BUNDLE_ID"
        return $?
    fi
    if [ "$yolo_mode" != "0" ]; then
        omi_jit_qa_fail "OMI_JIT_QA_TARGET cannot be combined with --yolo"
        return $?
    fi
    if [ "$local_profile" = true ]; then
        omi_jit_qa_fail "the reserved JIT QA bundle cannot use OMI_DESKTOP_LOCAL_PROFILE=1"
        return $?
    fi
    if [ "${OMI_FORCE_REWIND_SEED:-0}" = "1" ]; then
        omi_jit_qa_fail "the reserved JIT QA bundle cannot seed Rewind history"
        return $?
    fi
    if [ -n "${OMI_SKIP_REWIND_SEED+x}" ] && [ "$OMI_SKIP_REWIND_SEED" != "1" ]; then
        omi_jit_qa_fail "OMI_SKIP_REWIND_SEED must be 1 for the reserved JIT QA bundle"
        return $?
    fi
    case "$OMI_JIT_QA_TARGET" in
        local-dev-gcp|deployed-dev) ;;
        *)
            omi_jit_qa_fail "OMI_JIT_QA_TARGET must be local-dev-gcp or deployed-dev"
            return $?
            ;;
    esac
    for variable_name in OMI_PYTHON_API_URL OMI_DESKTOP_API_URL OMI_AUTH_API_URL OMI_ENV_STAGE; do
        if [ -n "${!variable_name+x}" ]; then
            omi_jit_qa_fail "$variable_name cannot override the selected atomic tuple"
            return $?
        fi
    done
}

omi_prepare_jit_qa_target() {
    local app_name="$1"
    local bundle_id="$2"
    local yolo_mode="$3"
    local phase="${4:-initial}"
    local local_profile="${5:-false}"
    local reserved=false

    if [ "$app_name" = "$OMI_JIT_QA_APP_NAME" ] || [ "$bundle_id" = "$OMI_JIT_QA_BUNDLE_ID" ]; then
        reserved=true
    fi

    if [ -z "${OMI_JIT_QA_TARGET:-}" ]; then
        if [ "$reserved" = true ]; then
            omi_jit_qa_fail "the reserved $OMI_JIT_QA_APP_NAME bundle requires OMI_JIT_QA_TARGET"
            return $?
        fi
        return 0
    fi
    if [ "$app_name" != "$OMI_JIT_QA_APP_NAME" ]; then
        omi_jit_qa_fail "OMI_JIT_QA_TARGET requires app name $OMI_JIT_QA_APP_NAME"
        return $?
    fi
    if [ "$bundle_id" != "$OMI_JIT_QA_BUNDLE_ID" ]; then
        omi_jit_qa_fail "OMI_JIT_QA_TARGET requires bundle id $OMI_JIT_QA_BUNDLE_ID"
        return $?
    fi
    if [ "$yolo_mode" != "0" ]; then
        omi_jit_qa_fail "OMI_JIT_QA_TARGET cannot be combined with --yolo"
        return $?
    fi
    if [ "$local_profile" = true ]; then
        omi_jit_qa_fail "the reserved JIT QA bundle cannot use OMI_DESKTOP_LOCAL_PROFILE=1"
        return $?
    fi
    if [ "${OMI_FORCE_REWIND_SEED:-0}" = "1" ]; then
        omi_jit_qa_fail "the reserved JIT QA bundle cannot seed Rewind history"
        return $?
    fi
    if [ "$phase" = "initial" ] \
        && [ -n "${OMI_SKIP_REWIND_SEED+x}" ] \
        && [ "$OMI_SKIP_REWIND_SEED" != "1" ]; then
        omi_jit_qa_fail "OMI_SKIP_REWIND_SEED must be 1 for the reserved JIT QA bundle"
        return $?
    fi

    if [ "$phase" = "initial" ]; then
        local variable_name
        for variable_name in OMI_PYTHON_API_URL OMI_DESKTOP_API_URL OMI_AUTH_API_URL OMI_ENV_STAGE; do
            if [ -n "${!variable_name+x}" ]; then
                omi_jit_qa_fail "$variable_name cannot override the selected atomic tuple"
                return $?
            fi
        done
    fi

    omi_jit_qa_set_exact_tuple
}

omi_jit_qa_expected_value() {
    case "$1" in
        OMI_PYTHON_API_URL) printf '%s\n' "$OMI_PYTHON_API_URL" ;;
        OMI_DESKTOP_API_URL) printf '%s\n' "$OMI_DESKTOP_API_URL" ;;
        OMI_AUTH_API_URL) printf '%s\n' "$OMI_AUTH_API_URL" ;;
        OMI_ENV_STAGE) printf '%s\n' "$OMI_ENV_STAGE" ;;
        *) return 1 ;;
    esac
}

# Repository configuration is shell-sourced later in run.sh. Inspect every
# endpoint/stage assignment before run.sh removes a log, stops an app, or
# starts a service. A selected JIT QA target may not silently repair a stale,
# mixed, or production tuple from one of those files.
omi_preflight_jit_qa_config_file() {
    local env_file="$1"
    local raw_line
    local line
    local key
    local value
    local expected
    local seen_keys=" "

    [ -n "${OMI_JIT_QA_TARGET:-}" ] || return 0
    [ -f "$env_file" ] || return 0

    while IFS= read -r raw_line || [ -n "$raw_line" ]; do
        line="${raw_line#"${raw_line%%[![:space:]]*}"}"
        case "$line" in
            ""|\#*) continue ;;
        esac
        if [[ ! "$line" =~ ^(export[[:space:]]+)?(OMI_PYTHON_API_URL|OMI_DESKTOP_API_URL|OMI_AUTH_API_URL|OMI_ENV_STAGE)[[:space:]]*=(.*)$ ]]; then
            continue
        fi

        key="${BASH_REMATCH[2]}"
        value="${BASH_REMATCH[3]}"
        value="${value#"${value%%[![:space:]]*}"}"
        value="${value%"${value##*[![:space:]]}"}"
        if [[ "$value" =~ ^\"(.*)\"$ ]] || [[ "$value" =~ ^\'(.*)\'$ ]]; then
            value="${BASH_REMATCH[1]}"
        fi
        expected="$(omi_jit_qa_expected_value "$key")" || return 2

        if [[ "$seen_keys" == *" $key "* ]]; then
            omi_jit_qa_fail "$env_file contains duplicate $key assignments"
            return $?
        fi
        seen_keys+="$key "
        if [ "$value" != "$expected" ]; then
            omi_jit_qa_fail "$env_file contains a stale or mixed $key assignment"
            return $?
        fi
    done < "$env_file"
}

omi_jit_qa_write_env_value() {
    local env_file="$1"
    local key="$2"
    local value="$3"
    local escaped_value="${value//&/\\&}"

    if grep -q "^${key}=" "$env_file"; then
        sed -i '' "s|^${key}=.*|${key}=${escaped_value}|" "$env_file"
    else
        printf '%s=%s\n' "$key" "$value" >> "$env_file"
    fi
}

omi_jit_qa_assert_env_value() {
    local env_file="$1"
    local key="$2"
    local expected="$3"
    local count
    local actual

    count="$(grep -c "^${key}=" "$env_file" || true)"
    if [ "$count" != "1" ]; then
        omi_jit_qa_fail "$env_file must contain exactly one $key"
        return $?
    fi
    actual="$(grep "^${key}=" "$env_file" | cut -d= -f2-)"
    if [ "$actual" != "$expected" ]; then
        omi_jit_qa_fail "$env_file has unexpected $key"
        return $?
    fi
}

omi_write_jit_qa_bundle_env() {
    local env_file="$1"
    [ -n "${OMI_JIT_QA_TARGET:-}" ] || return 0

    omi_jit_qa_set_exact_tuple
    omi_jit_qa_write_env_value "$env_file" OMI_PYTHON_API_URL "$OMI_PYTHON_API_URL"
    omi_jit_qa_write_env_value "$env_file" OMI_DESKTOP_API_URL "$OMI_DESKTOP_API_URL"
    omi_jit_qa_write_env_value "$env_file" OMI_AUTH_API_URL "$OMI_AUTH_API_URL"
    omi_jit_qa_write_env_value "$env_file" OMI_ENV_STAGE "$OMI_ENV_STAGE"

    omi_jit_qa_assert_env_value "$env_file" OMI_PYTHON_API_URL "$OMI_PYTHON_API_URL"
    omi_jit_qa_assert_env_value "$env_file" OMI_DESKTOP_API_URL "$OMI_DESKTOP_API_URL"
    omi_jit_qa_assert_env_value "$env_file" OMI_AUTH_API_URL "$OMI_AUTH_API_URL"
    omi_jit_qa_assert_env_value "$env_file" OMI_ENV_STAGE "$OMI_ENV_STAGE"

    if grep -Eq '(^|[=/])api\.omi\.me([/:]|$)' "$env_file"; then
        omi_jit_qa_fail "$env_file contains the prohibited production API host"
        return $?
    fi
}
