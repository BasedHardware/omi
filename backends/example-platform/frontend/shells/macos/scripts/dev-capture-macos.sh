#!/bin/bash
# Offline native fixture capture for the macOS Omi shell.
#
# This is deliberately not the registered live launcher. Fixture captures
# must not write consumer evidence or talk to a backend. The live entry
# point remains scripts/dev-run-macos.sh.
#
#   ./scripts/dev-capture-macos.sh --fixture memories-platform \
#     --run-id fixture-mac-001 --capture-out /tmp/fixture.png
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
core="$(cd "$here/../.." && pwd)"

fixture=""
fixture_state="ready"
fixture_theme="light"
fixture_accessibility="none"
run_id_arg=""
capture_out=""
viewport_width=""
viewport_height=""

while (( $# )); do
  case "$1" in
    --fixture) fixture="${2:?--fixture needs a domain}"; shift 2 ;;
    --state) fixture_state="${2:?--state needs a lifecycle state}"; shift 2 ;;
    --theme) fixture_theme="${2:?--theme needs light or dark}"; shift 2 ;;
    --accessibility) fixture_accessibility="${2:?--accessibility needs a mode}"; shift 2 ;;
    --run-id) run_id_arg="${2:?--run-id needs a raw run id}"; shift 2 ;;
    --capture-out) capture_out="${2:?--capture-out needs a PNG path}"; shift 2 ;;
    --viewport-width) viewport_width="${2:?--viewport-width needs pixels}"; shift 2 ;;
    --viewport-height) viewport_height="${2:?--viewport-height needs pixels}"; shift 2 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "ERROR: unknown argument '$1'" >&2; exit 2 ;;
  esac
done

if [[ -z "$fixture" || -z "$capture_out" || -z "$run_id_arg" ]]; then
  echo "ERROR: fixture capture requires --fixture, --capture-out, and --run-id." >&2
  exit 2
fi
if [[ ! "$fixture" =~ ^(memories|memories-platform|tasks|conversations|folders|listen|chat|settings)$ ]]; then
  echo "ERROR: unknown fixture domain '$fixture'." >&2
  exit 2
fi
if [[ ! "$fixture_state" =~ ^(loading|empty|ready|error|offline|busy|complete|cancelled)$ ]]; then
  echo "ERROR: unknown fixture state '$fixture_state'." >&2
  exit 2
fi
if [[ "$fixture_theme" != "light" && "$fixture_theme" != "dark" ]]; then
  echo "ERROR: fixture theme must be light or dark." >&2
  exit 2
fi
if [[ ! "$fixture_accessibility" =~ ^(none|keyboard|voiceover|high_contrast|reduced_motion|reduced_transparency|rtl|text_scale_200)$ ]]; then
  echo "ERROR: unknown fixture accessibility mode '$fixture_accessibility'." >&2
  exit 2
fi
if [[ ! "$run_id_arg" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$ ]] ||
   [[ "$run_id_arg" == anonymous || "$run_id_arg" == overflow || "$run_id_arg" == __* || "$run_id_arg" == *::* ]]; then
  echo "ERROR: fixture capture run id is unsafe." >&2
  exit 2
fi
if [[ ! "$capture_out" = /* || ! -d "$(dirname "$capture_out")" ]]; then
  echo "ERROR: --capture-out must be an absolute path in an existing directory." >&2
  exit 2
fi
if [[ -n "$viewport_width" && ! "$viewport_width" =~ ^[0-9]+$ ]] ||
   [[ -n "$viewport_height" && ! "$viewport_height" =~ ^[0-9]+$ ]]; then
  echo "ERROR: fixture viewport dimensions must be integer pixels." >&2
  exit 2
fi
rm -f -- "$capture_out"

# Fixture captures are a deliberately separate branch: no API URL policy,
# credential lookup, backend reachability check, or live evidence writer.
# The shell serves the exact shared bundle and exits after WKWebView writes
# the requested PNG.
dist="${OMI_SURFACES_DIST:-$core/packages/surfaces/dist}"
if [[ ! -f "$dist/index.html" ]]; then
  echo "ERROR: surfaces dist missing; set OMI_SURFACES_DIST to a built bundle." >&2
  exit 1
fi
app_name="${OMI_APP_NAME:-omi-on-polish-fixture}"
if [[ ! "$app_name" =~ ^omi-on-[A-Za-z0-9][A-Za-z0-9.-]*$ ]]; then
  echo "ERROR: OMI_APP_NAME must look like omi-on-<scratch>." >&2
  exit 1
fi
port="${OMI_SURFACE_PORT:-5290}"
if [[ "$port" != "5290" ]]; then
  echo "ERROR: OMI_SURFACE_PORT must remain 5290 for fixture captures." >&2
  exit 1
fi
export OMI_BUILD_DIR="${OMI_BUILD_DIR:-$core/.build/polish-fixture}"
export OMI_APP_NAME="$app_name"
export OMI_SURFACES_DIST="$dist"
export OMI_SURFACE_PORT="$port"
unset OMI_API_BASE_URL OMI_API_TOKEN OMI_DEV_TOKEN_ISSUER_URL OMI_CONSUMER_EVIDENCE_PATH OMI_CONSUMER_EVIDENCE_EXIT OMI_SURFACE_URL OMI_SURFACE_PATH
export OMI_SURFACE_QUERY="qa=${fixture}&polish=1&state=${fixture_state}&theme=${fixture_theme}&platform=desktop&accessibility=${fixture_accessibility}"
export OMI_RUN_CLIENT_ID="$run_id_arg"
export OMI_SNAPSHOT_PATH="$capture_out"
export OMI_PROBE_EXIT=1
if [[ -n "$viewport_width" ]]; then export OMI_NATIVE_VIEWPORT_WIDTH="$viewport_width"; fi
if [[ -n "$viewport_height" ]]; then export OMI_NATIVE_VIEWPORT_HEIGHT="$viewport_height"; fi
echo "MODE: FIXTURE CAPTURE — domain=${fixture} state=${fixture_state} theme=${fixture_theme} accessibility=${fixture_accessibility} run=${run_id_arg}"
echo "      bridge disabled; no backend, credentials, or consumer evidence claim."
exec "$here/scripts/run-shell.sh"
