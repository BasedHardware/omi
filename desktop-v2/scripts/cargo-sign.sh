#!/usr/bin/env bash
# Cargo wrapper that signs the dev binary after each `cargo build`/`run`
# so the embedded Info.plist and audio-capture entitlement are bound to
# the signature — required for macOS TCC to grant Core Audio tap
# permission.
#
# Invoked by `tauri dev --runner ../scripts/cargo-sign.sh` (tauri cd's
# into `src-tauri/` before invoking, so the `--runner` arg is a path
# relative to `src-tauri/`).

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd -- "$here/.." && pwd)"

# For `run`, tauri wants cargo to BUILD then EXEC the binary. If we let
# cargo run the binary, we can't re-sign first — so we split:
#   cargo run ARGS...  →  cargo build ARGS... ; sign ; exec binary ARGS_AFTER_--
needs_sign_then_exec=0
is_build=0
for arg in "$@"; do
    case "$arg" in
        run) needs_sign_then_exec=1 ;;
        build|rustc) is_build=1 ;;
    esac
done

if [ "$needs_sign_then_exec" = "1" ]; then
    # Split argv at the `--` separator: args before go to `cargo build`,
    # args after are forwarded to the final binary.
    cargo_args=()
    bin_args=()
    seen_sep=0
    for arg in "$@"; do
        if [ "$arg" = "--" ]; then
            seen_sep=1
            continue
        fi
        if [ "$seen_sep" = "1" ]; then
            bin_args+=("$arg")
        elif [ "$arg" != "run" ]; then
            cargo_args+=("$arg")
        fi
    done

    cargo build "${cargo_args[@]}"
    status=$?
    if [ "$status" -ne 0 ]; then
        exit "$status"
    fi

    # Build the Swift system-audio helper (skips if already up-to-date).
    "$here/build-sys-audio-helper.sh" > /dev/null 2>&1 || true

    if [ -x "$root/src-tauri/target/debug/nooto-desktop-v2" ]; then
        "$here/dev-sign.sh" > /dev/null 2>&1 || true
    fi

    exec "$root/src-tauri/target/debug/nooto-desktop-v2" "${bin_args[@]}"
fi

cargo "$@"
status=$?

if [ "$is_build" = "1" ] && [ "$status" -eq 0 ]; then
    if [ -x "$root/src-tauri/target/debug/nooto-desktop-v2" ]; then
        "$here/dev-sign.sh" > /dev/null 2>&1 || true
    fi
fi

exit $status
