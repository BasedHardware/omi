#!/bin/bash
# ONE-COMMAND local launch of the iOS Omi shell in the Simulator against a
# local backend. Stable entry point for the top-level dev stack launcher.
#
#   ./scripts/dev-run-ios.sh                      # LIVE against the default backend
#   ./scripts/dev-run-ios.sh --api http://127.0.0.1:4747
#   ./scripts/dev-run-ios.sh --route chat
#   ./scripts/dev-run-ios.sh --fixture conversations   # FIXTURE, bridge bypassed
#   ./scripts/dev-run-ios.sh --device <udid>
#
# Env (all overridable, local-sane defaults):
#   OMI_API_BASE_URL   default http://127.0.0.1:4801
#   OMI_API_TOKEN      dev token; fetched from the issuer when unset
#   OMI_DEV_TOKEN_ISSUER_URL   optional dev-mode token issuer
#   FLUTTER_BIN        default: whichever `flutter` resolves to
#
# THE ORIGIN IS FROZEN at omi-ui://local (ADR-009) and is NOT configurable here
# on purpose. IndexedDB is origin-keyed, so a per-launch origin silently wipes
# local surface storage. Only the BACKEND is repointable; the origin is not.
#
# NOTE ON REPOINTING: Dart's String.fromEnvironment is resolved at compile
# time, so --api is applied by this script as a --dart-define on each
# `flutter run`. That is fine for the dev loop (every run compiles anyway), but
# a shipped build cannot be repointed without a rebuild. Flagged, not hidden.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
app="$here/app"

api_base="${OMI_API_BASE_URL:-http://127.0.0.1:4801}"
fixture=""
device=""
accept=0
route="home"

while (( $# )); do
  case "$1" in
    --api) api_base="${2:?--api needs a URL}"; shift 2 ;;
    --fixture) fixture="${2:?--fixture needs a name}"; shift 2 ;;
    --device) device="${2:?--device needs a udid}"; shift 2 ;;
    --route) route="${2:?--route needs a production route}"; shift 2 ;;
    --accept) accept=1; shift ;;
    -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
    *) echo "ERROR: unknown argument '$1'" >&2; exit 2 ;;
  esac
done

case "$route" in
  home|memories|conversations|tasks|chat|settings|listen) ;;
  *) echo "ERROR: --route must be one of home|memories|conversations|tasks|chat|settings|listen." >&2; exit 2 ;;
esac
case "$api_base" in
  https://api.omi.me|https://api.omi.me/) echo "ERROR: production api.omi.me is forbidden in the iOS QA launcher." >&2; exit 2 ;;
esac

flutter_bin="${FLUTTER_BIN:-$(command -v flutter || true)}"
if [[ -z "$flutter_bin" ]]; then
  echo "ERROR: no flutter on PATH; set FLUTTER_BIN." >&2
  exit 1
fi
# This shell's pubspec requires Dart SDK ^3.12.2 (Flutter 3.44+). An older
# Flutter fails with a confusing version-solve error, so say so plainly.
fv="$("$flutter_bin" --version 2>/dev/null | head -1 || true)"
echo "flutter: $fv"
case "$fv" in
  *" 3.4"[4-9]*|*" 3."[5-9][0-9]*) : ;;
  *) echo "WARNING: this shell needs Flutter >= 3.44 (Dart ^3.12.2)." >&2
     echo "         Older Flutter fails with 'version solving failed'." >&2 ;;
esac

if [[ -z "$device" ]]; then
  device="$(xcrun simctl list devices booted -j 2>/dev/null \
    | /usr/bin/python3 -c 'import json,sys
d=json.load(sys.stdin)["devices"]
for rt,ds in d.items():
    for x in ds:
        if x.get("state")=="Booted":
            print(x["udid"]); raise SystemExit' 2>/dev/null || true)"
fi
if [[ -z "$device" ]]; then
  echo "ERROR: no booted simulator found. Boot one, or pass --device <udid>." >&2
  echo "  xcrun simctl list devices available" >&2
  exit 1
fi
echo "device: $device"

defines=(
  --dart-define=SURFACE_MODE=scheme
  --dart-define=SCHEME_BUNDLE=surfaces
)

# ---- LIVE vs FIXTURE is an explicit, visible fork, never an accident --------
# A qa= fixture route selects an in-page fixture store and does NOT traverse the
# privileged HTTP bridge. It can never support a backend claim or a served count.
if [[ -n "$fixture" ]]; then
  defines+=( --dart-define=SURFACE_QUERY="qa=${fixture}&state=normal&platform=mobile" )
  echo "MODE: FIXTURE (qa=${fixture}) — bridge is NOT exercised; no backend traffic."
  echo "      Nothing seen in this mode is evidence about the backend."
else
  run_id="${OMI_RUN_CLIENT_ID:-run-ios-$(date -u +%Y%m%dT%H%M%SZ)-$$}"
  if [[ ! "$run_id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$ ]] || [[ "$run_id" == anonymous || "$run_id" == overflow || "$run_id" == __* ]]; then
    echo "ERROR: OMI_RUN_CLIENT_ID is not a bounded producer-evidence run id." >&2
    exit 2
  fi
  token="${OMI_API_TOKEN:-}"
  if [[ -z "$token" && -n "${OMI_DEV_TOKEN_ISSUER_URL:-}" ]]; then
    echo "MODE: LIVE — no OMI_API_TOKEN set; requesting one from the dev issuer."
    token="$(curl -fsS --max-time 5 -X POST "$OMI_DEV_TOKEN_ISSUER_URL" || true)"
  fi
  if [[ -z "$token" ]]; then
    echo "ERROR: LIVE mode needs a credential." >&2
    echo "  Set OMI_API_TOKEN=<dev token>, or OMI_DEV_TOKEN_ISSUER_URL=<issuer>." >&2
    echo "  Refusing to launch a shell that would silently show an empty app." >&2
    exit 1
  fi

  # Same fail-open trap as the macOS launcher: curl -w prints "000" on a refused
  # connection AND exits nonzero, so keep the exit status in its own variable.
  curl_rc=0
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$api_base/" 2>/dev/null)" || curl_rc=$?
  if (( curl_rc != 0 )) || [[ "$code" == "000" ]]; then
    echo "ERROR: no backend reachable at $api_base" >&2
    echo "  Start the backend first, or pass --api <url>." >&2
    exit 1
  fi
  # The simulator shares the host network stack, so 127.0.0.1 reaches the host.
  defines+=(
    --dart-define=SURFACE_QUERY="route=${route}&platform=mobile"
    --dart-define=OMI_API_BASE_URL="$api_base"
    --dart-define=OMI_API_TOKEN="$token"
    --dart-define=OMI_RUN_CLIENT_ID="$run_id"
  )
  echo "MODE: LIVE — route $route, backend $api_base (reachable, HTTP $code), credential held by the shell."
  echo "PRODUCER: x-omi-client-id=${run_id}::ios"
fi

if (( accept )); then
  defines+=( --dart-define=OMI_ACCEPTANCE=true --dart-define=OMI_ACCEPTANCE_EXIT=true )
fi

# Build the shared surfaces bundle the scheme host serves from omi-ui://local.
# Deliberately AFTER the credential/reachability gates: never spend a bundle
# build only to refuse at launch.
node_bin="${NODE_BIN:-$(command -v node || true)}"
if [[ -z "$node_bin" ]]; then
  echo "ERROR: no node on PATH; set NODE_BIN." >&2
  exit 1
fi
( cd "$here" && "$node_bin" tools/build-surfaces-bundle.mjs )

cd "$app"
exec "$flutter_bin" run -d "$device" "${defines[@]}"
