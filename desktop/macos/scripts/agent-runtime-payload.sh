#!/usr/bin/env bash
# The packaged runtime payload a desktop bundle needs before it can answer one
# chat turn. Side-effect-free: source it and call the predicates.
#
# Why this exists as its own contract: the Swift app spawns
# `Contents/Resources/agent/dist/index.js`, and the pi-mono adapter inside it
# resolves `../../../pi-mono-extension/index.ts` from its own module URL. That
# extension is what registers the `omi` provider, so a bundle missing it cannot
# resolve a model and pi-mono exits 1 on *every* turn while the app happily
# accepts the message first. Packaging is the only place that can tell the
# difference between "this bundle is incomplete" and "this turn failed", so a
# bundle that cannot run chat must never be built, installed, or reused.

# Bundle-relative files that must exist and be non-empty.
OMI_AGENT_RUNTIME_REQUIRED_FILES=(
  "Contents/Resources/agent/dist/index.js"
  "Contents/Resources/agent/dist/runtime/omi-tool-manifest.js"
  "Contents/Resources/agent/package.json"
  "Contents/Resources/pi-mono-extension/index.ts"
  "Contents/Resources/pi-mono-extension/package.json"
)

# Bundle-relative directories that must exist and be non-empty. An empty
# dependency tree fails at spawn exactly like a missing one.
OMI_AGENT_RUNTIME_REQUIRED_DIRS=(
  "Contents/Resources/agent/dist"
  "Contents/Resources/agent/node_modules"
  "Contents/Resources/pi-mono-extension/node_modules"
)

# Print every missing/empty required component for an app bundle, one
# bundle-relative path per line. Prints nothing when the payload is complete.
omi_agent_runtime_payload_missing() {
  local app_bundle="$1"
  local relative

  for relative in "${OMI_AGENT_RUNTIME_REQUIRED_FILES[@]}"; do
    if [ ! -s "$app_bundle/$relative" ]; then
      printf '%s\n' "$relative"
    fi
  done

  for relative in "${OMI_AGENT_RUNTIME_REQUIRED_DIRS[@]}"; do
    if [ ! -d "$app_bundle/$relative" ]; then
      printf '%s\n' "$relative"
    elif [ -z "$(ls -A "$app_bundle/$relative" 2>/dev/null)" ]; then
      printf '%s\n' "$relative"
    fi
  done
}

omi_agent_runtime_payload_complete() {
  [ -z "$(omi_agent_runtime_payload_missing "$1")" ]
}

# Fail the caller with the exact missing components. `stage` names where the
# payload went missing so the failure points at a build step, not at chat.
omi_assert_agent_runtime_payload() {
  local app_bundle="$1"
  local stage="${2:-bundle}"
  local missing relative
  missing="$(omi_agent_runtime_payload_missing "$app_bundle")"
  [ -n "$missing" ] || return 0

  {
    echo "ERROR: agent runtime payload incomplete after $stage: $app_bundle"
    while IFS= read -r relative; do
      [ -n "$relative" ] && echo "       missing: $relative"
    done <<< "$missing"
    echo "       This bundle cannot answer a chat turn — pi-mono would exit 1 on every query."
    echo "       Rebuild the full bundle: OMI_FORCE_FULL_BUNDLE=1 ./run.sh (or ./run.sh --full)."
  } >&2
  return 1
}
