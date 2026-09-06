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
# Cloud QA is an isolated pair of Cloud Run services. Their generated host
# suffixes are deliberately supplied by the deployment receipt rather than
# guessed here; accepting a service-shaped value without that receipt would
# make an arbitrary endpoint look like the isolated data plane.
OMI_JIT_QA_CLOUD_PROJECT="based-hardware-dev"
OMI_JIT_QA_CLOUD_REGION="us-central1"
OMI_JIT_QA_CLOUD_AUTH_PROJECT="based-hardware"
OMI_JIT_QA_CLOUD_DATA_PLANE_PROJECT="based-hardware-dev"
OMI_JIT_QA_CLOUD_FIRESTORE_DATABASE="jit-qa"
OMI_JIT_QA_CLOUD_PYTHON_SERVICE="backend-jit-qa"
OMI_JIT_QA_CLOUD_DESKTOP_SERVICE="desktop-backend-jit-qa"
OMI_JIT_QA_CLOUD_GATEWAY_SERVICE="llm-gateway-jit-qa"
OMI_JIT_QA_CLOUD_RECEIPT_ENV="OMI_JIT_QA_CLOUD_RECEIPT_PATH"
# Firebase web API keys identify a client/project; they are not credentials.
# The dev services intentionally validate the same production Firebase identity
# described by run.sh's --yolo contract, so the reserved QA tuple must carry the
# matching public client key on both deployed-dev and local-dev-gcp launches.
OMI_JIT_QA_FIREBASE_API_KEY="AIzaSyD9dzBdglc7IO9pPDIOvqnCoTis_xKkkC8"

omi_jit_qa_fail() {
    printf 'ERROR: JIT QA target: %s\n' "$1" >&2
    return 2
}

omi_jit_qa_validate_cloud_url() {
    local value="$1"
    local service="$2"
    local pattern

    case "$service" in
        "$OMI_JIT_QA_CLOUD_PYTHON_SERVICE")
            # Cloud Run currently exposes both the legacy hashed endpoint
            # (…-uc.a.run.app) and the deterministic regional endpoint
            # (…-PROJECT_NUMBER.us-central1.run.app). Accept only these
            # forms for this fixed service and region.
            pattern='^https://backend-jit-qa-([a-z0-9-]+-uc\.a\.run\.app|[0-9]+\.us-central1\.run\.app)$'
            ;;
        "$OMI_JIT_QA_CLOUD_DESKTOP_SERVICE")
            pattern='^https://desktop-backend-jit-qa-([a-z0-9-]+-uc\.a\.run\.app|[0-9]+\.us-central1\.run\.app)$'
            ;;
        "$OMI_JIT_QA_CLOUD_GATEWAY_SERVICE")
            pattern='^https://llm-gateway-jit-qa-([a-z0-9-]+-uc\.a\.run\.app|[0-9]+\.us-central1\.run\.app)$'
            ;;
        *)
            omi_jit_qa_fail "unknown cloud QA service $service"
            return $?
            ;;
    esac

    if [[ ! "$value" =~ $pattern ]]; then
        omi_jit_qa_fail "$service URL must be the HTTPS Cloud Run URL for the isolated QA service"
        return $?
    fi
}

# A deployment receipt is the authority for a cloud-QA launch. It is emitted
# by the reviewed deployment workflow after both services are ready, and is
# checked against the endpoint values before run.sh can stop or relaunch an
# app. Keep this parser dependency-free: macOS's Python 3 is already required
# by the desktop launcher.
omi_jit_qa_validate_cloud_receipt() {
    local receipt_path="${OMI_JIT_QA_CLOUD_RECEIPT_PATH:-}"
    local python_url="${OMI_JIT_QA_CLOUD_PYTHON_URL:-}"
    local desktop_url="${OMI_JIT_QA_CLOUD_DESKTOP_URL:-}"

    if [ -z "$receipt_path" ]; then
        omi_jit_qa_fail "$OMI_JIT_QA_CLOUD_RECEIPT_ENV is required for cloud-qa"
        return $?
    fi
    if [ ! -f "$receipt_path" ] || [ -L "$receipt_path" ]; then
        omi_jit_qa_fail "$OMI_JIT_QA_CLOUD_RECEIPT_ENV must name a regular deployment receipt file"
        return $?
    fi
    omi_jit_qa_validate_cloud_url "$python_url" "$OMI_JIT_QA_CLOUD_PYTHON_SERVICE" || return $?
    omi_jit_qa_validate_cloud_url "$desktop_url" "$OMI_JIT_QA_CLOUD_DESKTOP_SERVICE" || return $?

    python3 - "$receipt_path" "$python_url" "$desktop_url" \
        "$OMI_JIT_QA_CLOUD_PROJECT" "$OMI_JIT_QA_CLOUD_REGION" \
        "$OMI_JIT_QA_CLOUD_AUTH_PROJECT" "$OMI_JIT_QA_CLOUD_DATA_PLANE_PROJECT" \
        "$OMI_JIT_QA_CLOUD_FIRESTORE_DATABASE" "$OMI_JIT_QA_CLOUD_PYTHON_SERVICE" \
        "$OMI_JIT_QA_CLOUD_DESKTOP_SERVICE" "$OMI_JIT_QA_CLOUD_GATEWAY_SERVICE" <<'PY'
import json
import pathlib
import re
import sys

(
    receipt_path,
    python_url,
    desktop_url,
    project,
    region,
    auth_project,
    data_plane_project,
    firestore_database,
    python_service,
    desktop_service,
    gateway_service,
) = sys.argv[1:]

try:
    receipt = json.loads(pathlib.Path(receipt_path).read_text(encoding="utf-8"))
except (OSError, ValueError) as exc:
    print(f"ERROR: JIT QA target: invalid cloud deployment receipt: {exc}", file=sys.stderr)
    raise SystemExit(2)
if not isinstance(receipt, dict):
    print("ERROR: JIT QA target: cloud deployment receipt must be a JSON object", file=sys.stderr)
    raise SystemExit(2)

required = {
    "schema_version": "omi.jit.qa.cloud.v1",
    "status": "ready",
    "project": project,
    "region": region,
    "auth_project": auth_project,
    "data_plane_project": data_plane_project,
    "python_service": python_service,
    "desktop_service": desktop_service,
    "exact_python_url": python_url,
    "exact_desktop_url": desktop_url,
    "firestore_database_id": firestore_database,
    "gateway_service": gateway_service,
}
for key, expected in required.items():
    if receipt.get(key) != expected:
        print(f"ERROR: JIT QA target: cloud receipt {key} does not match the reviewed QA tuple", file=sys.stderr)
        raise SystemExit(2)
if receipt.get("reviewed") is not True:
    print("ERROR: JIT QA target: cloud deployment receipt is not marked reviewed", file=sys.stderr)
    raise SystemExit(2)
gateway_url = receipt.get("exact_gateway_url")
if not isinstance(gateway_url, str):
    print("ERROR: JIT QA target: cloud receipt exact_gateway_url is required", file=sys.stderr)
    raise SystemExit(2)
gateway_pattern = re.compile(
    r"^https://" + re.escape(gateway_service) + r"-([a-z0-9-]+-uc\.a\.run\.app|[0-9]+\.us-central1\.run\.app)$"
)
if not gateway_pattern.fullmatch(gateway_url):
    print("ERROR: JIT QA target: cloud receipt exact_gateway_url is not the isolated QA gateway URL", file=sys.stderr)
    raise SystemExit(2)
source_sha = receipt.get("full_source_sha")
if not isinstance(source_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", source_sha):
    print("ERROR: JIT QA target: cloud receipt must pin a full lowercase source SHA", file=sys.stderr)
    raise SystemExit(2)
for key, service in (
    ("python_revision", python_service),
    ("desktop_revision", desktop_service),
):
    revision = receipt.get(key)
    if not isinstance(revision, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", revision) \
            or not revision.startswith(service + "-"):
        print(f"ERROR: JIT QA target: cloud receipt {key} is not a revision of {service}", file=sys.stderr)
        raise SystemExit(2)
for key in ("python_image_digest", "desktop_image_digest"):
    digest = receipt.get(key)
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        print(f"ERROR: JIT QA target: cloud receipt {key} must be a sha256 image digest", file=sys.stderr)
        raise SystemExit(2)
dependency_vector = receipt.get("dependency_vector")
expected_dependencies = {
    "firestore": "based-hardware-dev",
    "redis": "jit-qa-redis:basic-1GiB",
    "gateway": "llm-gateway-jit-qa:service-token",
    "typesense": "typesense-jit-qa:api-key",
    "firebase_auth": "based-hardware:verify-only",
    "storage": "none",
    "pubsub": "none",
    "scheduler": "none",
}
if dependency_vector != expected_dependencies:
    print("ERROR: JIT QA target: cloud receipt dependencies do not match the isolated QA contract", file=sys.stderr)
    raise SystemExit(2)
PY
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
        cloud-qa)
            omi_jit_qa_validate_cloud_receipt || return $?
            export OMI_PYTHON_API_URL="$OMI_JIT_QA_CLOUD_PYTHON_URL"
            export OMI_DESKTOP_API_URL="$OMI_JIT_QA_CLOUD_DESKTOP_URL"
            export OMI_AUTH_API_URL="$OMI_JIT_QA_CLOUD_PYTHON_URL"
            ;;
        *)
            omi_jit_qa_fail "OMI_JIT_QA_TARGET must be local-dev-gcp, deployed-dev, or cloud-qa"
            return $?
            ;;
    esac
    export OMI_ENV_STAGE="dev"
    export FIREBASE_API_KEY="$OMI_JIT_QA_FIREBASE_API_KEY"
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
        local-dev-gcp|deployed-dev|cloud-qa) ;;
        *)
            omi_jit_qa_fail "OMI_JIT_QA_TARGET must be local-dev-gcp, deployed-dev, or cloud-qa"
            return $?
            ;;
    esac
    if [ "$OMI_JIT_QA_TARGET" = "cloud-qa" ]; then
        omi_jit_qa_validate_cloud_receipt || return $?
    fi
    for variable_name in OMI_PYTHON_API_URL OMI_DESKTOP_API_URL OMI_AUTH_API_URL OMI_ENV_STAGE FIREBASE_API_KEY; do
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
        for variable_name in OMI_PYTHON_API_URL OMI_DESKTOP_API_URL OMI_AUTH_API_URL OMI_ENV_STAGE FIREBASE_API_KEY; do
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
        FIREBASE_API_KEY) printf '%s\n' "$FIREBASE_API_KEY" ;;
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
        if [[ ! "$line" =~ ^(export[[:space:]]+)?(OMI_PYTHON_API_URL|OMI_DESKTOP_API_URL|OMI_AUTH_API_URL|OMI_ENV_STAGE|FIREBASE_API_KEY)[[:space:]]*=(.*)$ ]]; then
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
    omi_jit_qa_write_env_value "$env_file" FIREBASE_API_KEY "$FIREBASE_API_KEY"

    omi_jit_qa_assert_env_value "$env_file" OMI_PYTHON_API_URL "$OMI_PYTHON_API_URL"
    omi_jit_qa_assert_env_value "$env_file" OMI_DESKTOP_API_URL "$OMI_DESKTOP_API_URL"
    omi_jit_qa_assert_env_value "$env_file" OMI_AUTH_API_URL "$OMI_AUTH_API_URL"
    omi_jit_qa_assert_env_value "$env_file" OMI_ENV_STAGE "$OMI_ENV_STAGE"
    omi_jit_qa_assert_env_value "$env_file" FIREBASE_API_KEY "$FIREBASE_API_KEY"

    if grep -Eq '(^|[=/])api\.omi\.me([/:]|$)' "$env_file"; then
        omi_jit_qa_fail "$env_file contains the prohibited production API host"
        return $?
    fi
}
