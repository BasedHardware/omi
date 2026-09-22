# Shared macOS automation-token path resolution for shell harnesses.
# Source from scripts that need the same path the Swift bridge writes:
#   NSTemporaryDirectory()/omi-automation-{port}.token
# which equals $(getconf DARWIN_USER_TEMP_DIR) for non-sandboxed local bundles.
#
# Usage:
#   # shellcheck source=automation-token-path.sh
#   source "$(dirname "$0")/automation-token-path.sh"
#   TOKEN_FILE="$(omi_automation_token_file "$PORT")"

omi_automation_token_file() {
  local port="${1:?port required}"
  if [[ -n "${OMI_AUTOMATION_TOKEN_FILE:-}" ]]; then
    printf '%s\n' "$OMI_AUTOMATION_TOKEN_FILE"
    return 0
  fi
  local darwin_tmp=""
  if darwin_tmp="$(getconf DARWIN_USER_TEMP_DIR 2>/dev/null)" && [[ -n "$darwin_tmp" ]]; then
    printf '%s\n' "${darwin_tmp%/}/omi-automation-${port}.token"
    return 0
  fi
  printf '%s\n' "${TMPDIR:-/tmp}/omi-automation-${port}.token"
}
