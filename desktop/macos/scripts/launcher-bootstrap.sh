#!/usr/bin/env bash

# Keep the launcher bootstrap logic small and independently testable. The
# optional prefix arguments let the hermetic test use disposable Homebrew-like
# directories without changing the production paths.
omi_configure_homebrew_path() {
    local architecture="${1:-$(uname -m)}"
    local arm_prefix="${2:-/opt/homebrew}"
    local intel_prefix="${3:-/usr/local}"
    local -a homebrew_bins
    local -a path_entries=()
    local existing_path="${PATH:-}"
    local filtered_path=""
    local homebrew_path=""
    local homebrew_bin
    local path_entry

    # PATH is assembled by appending these entries below, so list the native
    # prefix first to give native tools precedence.
    if [ "$architecture" = "arm64" ]; then
        homebrew_bins=("$arm_prefix/bin" "$intel_prefix/bin")
    else
        homebrew_bins=("$intel_prefix/bin" "$arm_prefix/bin")
    fi

    IFS=: read -r -a path_entries <<< "$existing_path"
    for path_entry in "${path_entries[@]}"; do
        case "$path_entry" in
            "$arm_prefix/bin"|"$intel_prefix/bin")
                ;;
            *)
                if [ -n "$filtered_path" ]; then
                    filtered_path="$filtered_path:$path_entry"
                else
                    filtered_path="$path_entry"
                fi
                ;;
        esac
    done

    for homebrew_bin in "${homebrew_bins[@]}"; do
        if [ -d "$homebrew_bin" ]; then
            if [ -n "$homebrew_path" ]; then
                homebrew_path="$homebrew_path:$homebrew_bin"
            else
                homebrew_path="$homebrew_bin"
            fi
        fi
    done

    if [ -n "$homebrew_path" ] && [ -n "$filtered_path" ]; then
        PATH="$homebrew_path:$filtered_path"
    elif [ -n "$homebrew_path" ]; then
        PATH="$homebrew_path"
    else
        PATH="$filtered_path"
    fi
    export PATH
}

omi_normalize_packaged_resource_bundle() {
    local packaged_resource_bundle="$1"
    local packaged_node="$packaged_resource_bundle/node"
    local nested_packaged_node="$packaged_resource_bundle/Contents/Resources/node"

    if [ -x "$packaged_node" ] && [ ! -e "$nested_packaged_node" ]; then
        mkdir -p "$(dirname "$nested_packaged_node")"
        mv "$packaged_node" "$nested_packaged_node"
    fi
}
