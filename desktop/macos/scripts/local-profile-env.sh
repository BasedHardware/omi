#!/usr/bin/env bash
# Shared writer for the disposable local-harness profile embedded in a named
# development bundle. Keep the profile material at the bundle boundary: the
# fast executable-patch lane must refresh it on every launch rather than cache
# credentials in a reusable-bundle fingerprint.

omi_write_local_profile_env() {
    local env_file="$1"

    : > "$env_file"
    {
        printf '%s\n' "OMI_DESKTOP_LOCAL_PROFILE=1"
        printf '%s\n' "OMI_DESKTOP_API_URL=${OMI_DESKTOP_API_URL:-}"
        printf '%s\n' "OMI_PYTHON_API_URL=${OMI_PYTHON_API_URL:-}"
        printf '%s\n' "OMI_LOCAL_PROFILE_STORAGE_NAME=${OMI_LOCAL_PROFILE_STORAGE_NAME:-Omi}"
        printf '%s\n' "OMI_LOCAL_AUTH_USER=${OMI_LOCAL_AUTH_USER:-}"
        printf '%s\n' "OMI_LOCAL_AUTH_EMAIL=${OMI_LOCAL_AUTH_EMAIL:-}"
        printf '%s\n' "OMI_LOCAL_AUTH_PASSWORD=${OMI_LOCAL_AUTH_PASSWORD:-}"
        printf '%s\n' "OMI_LOCAL_AUTH_DISPLAY_NAME=${OMI_LOCAL_AUTH_DISPLAY_NAME:-}"
        printf '%s\n' "FIREBASE_AUTH_EMULATOR_HOST=${FIREBASE_AUTH_EMULATOR_HOST:-}"
        printf '%s\n' "FIREBASE_PROJECT_ID=${FIREBASE_PROJECT_ID:-}"
        printf '%s\n' "FIREBASE_AUTH_PROJECT_ID=${FIREBASE_AUTH_PROJECT_ID:-${FIREBASE_PROJECT_ID:-}}"
        printf '%s\n' "FIRESTORE_DATABASE_ID=${FIRESTORE_DATABASE_ID:-(default)}"
        printf '%s\n' "FIREBASE_API_KEY=${FIREBASE_API_KEY:-}"
    } >> "$env_file"
}
