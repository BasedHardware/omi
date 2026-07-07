#!/usr/bin/env bash
# Derive the macOS desktop dev app identity from OMI_APP_NAME.
# Sourced by run.sh and by tests; keep this file side-effect-light.

slugify_identifier() {
    printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//; s/-+/-/g'
}

derive_omi_app_config() {
    local app_name="${1:-Omi Dev}"
    local is_named_bundle="false"
    local app_slug=""
    local expected_bundle_id
    local expected_url_scheme
    local bundle_id
    local url_scheme

    if [ "$app_name" != "Omi Dev" ]; then
        is_named_bundle="true"
    fi

    if [ "$is_named_bundle" = "false" ]; then
        expected_bundle_id="com.omi.desktop-dev"
        expected_url_scheme="omi-computer-dev"
    else
        app_slug="$(slugify_identifier "$app_name")"
        if [ -z "$app_slug" ]; then
            echo "ERROR: OMI_APP_NAME must contain at least one letter or number" >&2
            return 1
        fi
        expected_bundle_id="com.omi.$app_slug"
        expected_url_scheme="omi-$app_slug"
    fi

    bundle_id="${OMI_BUNDLE_ID:-$expected_bundle_id}"
    url_scheme="${OMI_URL_SCHEME:-$expected_url_scheme}"

    if [ "$bundle_id" != "$expected_bundle_id" ]; then
        echo "ERROR: APP_NAME '$app_name' must use bundle ID '$expected_bundle_id' (got '$bundle_id')" >&2
        return 1
    fi

    if [ "$url_scheme" != "$expected_url_scheme" ]; then
        echo "ERROR: APP_NAME '$app_name' must use URL scheme '$expected_url_scheme' (got '$url_scheme')" >&2
        return 1
    fi

    APP_NAME="$app_name"
    IS_NAMED_BUNDLE="$is_named_bundle"
    APP_SLUG="$app_slug"
    EXPECTED_BUNDLE_ID="$expected_bundle_id"
    EXPECTED_URL_SCHEME="$expected_url_scheme"
    BUNDLE_ID="$bundle_id"
    URL_SCHEME="$url_scheme"
}
