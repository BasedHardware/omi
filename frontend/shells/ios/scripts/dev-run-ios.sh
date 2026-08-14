#!/bin/bash
# ONE-COMMAND local launch of the iOS Omi shell in the Simulator against a
# local backend. Stable entry point for the top-level dev stack launcher.
#
#   ./scripts/dev-run-ios.sh                      # LIVE against registered local production
#   ./scripts/dev-run-ios.sh --api http://127.0.0.1:4851
#   ./scripts/dev-run-ios.sh --route chat
#   ./scripts/dev-run-ios.sh --generation legacy  # LIVE against the legacy Memories UI
#   ./scripts/dev-run-ios.sh --fixture conversations   # FIXTURE, bridge bypassed
#   ./scripts/dev-run-ios.sh --device <udid>
#
# Env (all overridable, local-sane defaults):
#   OMI_API_BASE_URL   default http://127.0.0.1:4851 (registered local production)
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

api_base="${OMI_API_BASE_URL:-http://127.0.0.1:4851}"
fixture=""
fixture_state="normal"
fixture_theme="light"
fixture_accessibility="none"
device=""
accept=0
route="home"
generation="platform"
evidence_out=""
run_id_arg=""
capture_out=""
launched=0
bundle_id="me.omi.proto.omiWebviewProto"
evidence_tmp=""
container_result=""

cleanup() {
  if (( launched )); then
    xcrun simctl terminate "$device" "$bundle_id" >/dev/null 2>&1 || true
  fi
  [[ -n "$container_result" ]] && rm -f -- "$container_result"
  [[ -n "$evidence_tmp" ]] && rm -f -- "$evidence_tmp"
  return 0
}
trap cleanup EXIT

while (( $# )); do
  case "$1" in
    --api) api_base="${2:?--api needs a URL}"; shift 2 ;;
    --fixture) fixture="${2:?--fixture needs a name}"; shift 2 ;;
    --state) fixture_state="${2:?--state needs a lifecycle state}"; shift 2 ;;
    --theme) fixture_theme="${2:?--theme needs light or dark}"; shift 2 ;;
    --accessibility) fixture_accessibility="${2:?--accessibility needs a mode}"; shift 2 ;;
    --device) device="${2:?--device needs a udid}"; shift 2 ;;
    --route) route="${2:?--route needs a production route}"; shift 2 ;;
    --generation) generation="${2:?--generation needs legacy or platform}"; shift 2 ;;
    --evidence-out) evidence_out="${2:?--evidence-out needs a host path}"; shift 2 ;;
    --run-id) run_id_arg="${2:?--run-id needs a raw run id}"; shift 2 ;;
    --capture-out) capture_out="${2:?--capture-out needs a PNG path}"; shift 2 ;;
    --accept) accept=1; shift ;;
    -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
    *) echo "ERROR: unknown argument '$1'" >&2; exit 2 ;;
  esac
done

# A prior host success must be gone even when a later route, URL, toolchain,
# build, install, gate, or launch check fails.
if [[ -n "$evidence_out" ]]; then
  if [[ -d "$evidence_out" ]]; then
    echo "ERROR: --evidence-out must name a file, not a directory." >&2
    exit 2
  fi
  rm -f -- "$evidence_out"
  evidence_tmp="$evidence_out.tmp.$$"
  rm -f -- "$evidence_tmp"
  [[ -d "$(dirname "$evidence_out")" ]] || {
    echo "ERROR: --evidence-out parent directory does not exist." >&2
    exit 2
  }
fi
if [[ -n "$evidence_out" && -z "$run_id_arg" ]] || [[ -z "$evidence_out" && -n "$run_id_arg" ]]; then
  if [[ -z "$fixture" || -z "$capture_out" ]]; then
    echo "ERROR: --evidence-out and --run-id must be supplied together." >&2
    exit 2
  fi
fi

capture_mode=0
if [[ -n "$capture_out" ]]; then
  capture_mode=1
fi
if [[ -n "$capture_out" && -z "$fixture" ]]; then
  echo "ERROR: --capture-out is fixture-only; supply --fixture." >&2
  exit 2
fi
if (( capture_mode )); then
  if [[ -z "$fixture" || -z "$capture_out" || -z "$run_id_arg" ]]; then
    echo "ERROR: fixture capture requires --fixture, --capture-out, and --run-id." >&2
    exit 2
  fi
  if [[ -n "$evidence_out" || $accept -eq 1 ]]; then
    echo "ERROR: fixture capture cannot be combined with consumer evidence or --accept." >&2
    exit 2
  fi
  if [[ ! "$fixture" =~ ^(memories|tasks|conversations|folders|listen|chat|settings)$ ]]; then
    echo "ERROR: unknown fixture domain '$fixture'." >&2
    exit 2
  fi
  if [[ ! "$fixture_state" =~ ^(loading|empty|ready|error|offline|busy|complete|cancelled|normal)$ ]]; then
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
  if [[ ! "$run_id_arg" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$ ]]; then
    echo "ERROR: fixture capture run id is unsafe." >&2
    exit 2
  fi
  if [[ ! "$capture_out" = /* || ! -d "$(dirname "$capture_out")" ]]; then
    echo "ERROR: --capture-out must be an absolute path in an existing directory." >&2
    exit 2
  fi
  rm -f -- "$capture_out"
fi

case "$route" in
  home|memories|conversations|tasks|folders|chat|settings|listen) ;;
  *) echo "ERROR: --route must be one of home|memories|conversations|tasks|folders|chat|settings|listen." >&2; exit 2 ;;
esac
case "$generation" in
  legacy|platform) ;;
  *) echo "ERROR: --generation must be legacy or platform." >&2; exit 2 ;;
esac
api_host="$(/usr/bin/python3 -c 'import sys, urllib.parse
try:
    parsed = urllib.parse.urlsplit(sys.argv[1])
    print((parsed.hostname or "").rstrip(".").lower())
except ValueError:
    raise SystemExit(2)' "$api_base")" || {
  echo "ERROR: --api must be a parseable URL." >&2
  exit 2
}
if [[ "$api_host" == "api.omi.me" ]]; then
  echo "ERROR: production api.omi.me is forbidden in the iOS QA launcher." >&2
  exit 2
fi

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
# A qa= fixture route is visual QA only: it selects an in-page fixture store and
# does NOT traverse the privileged HTTP bridge. It is outside registered/local-
# production evidence and can never support a backend claim or served count.
if [[ -n "$fixture" ]]; then
  if [[ -n "$evidence_out" ]]; then
    echo "ERROR: consumer evidence requires LIVE mode; --fixture is forbidden." >&2
    exit 2
  fi
  if (( capture_mode )); then
    defines+=( --dart-define=SURFACE_QUERY="qa=${fixture}&polish=1&state=${fixture_state}&theme=${fixture_theme}&platform=mobile&accessibility=${fixture_accessibility}" )
  else
    # Preserve the established interactive fixture contract; polished matrix
    # coordinates are explicit capture-only inputs.
    defines+=( --dart-define=SURFACE_QUERY="qa=${fixture}&state=normal&platform=mobile" )
  fi
  echo "MODE: FIXTURE (qa=${fixture}, state=${fixture_state}) — bridge is NOT exercised; no backend traffic."
  echo "      Nothing seen in this mode is evidence about the backend."
else
  run_id="${run_id_arg:-${OMI_RUN_CLIENT_ID:-run-ios-$(date -u +%Y%m%dT%H%M%SZ)-$$}}"
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
  # Live local production talks to the platform Memories door. Legacy stays
  # reachable with `--generation legacy`.
  surface_query="route=${route}&platform=mobile&generation=${generation}"
  defines+=(
    --dart-define=SURFACE_QUERY="$surface_query"
    --dart-define=OMI_API_BASE_URL="$api_base"
    --dart-define=OMI_API_TOKEN="$token"
    --dart-define=OMI_RUN_CLIENT_ID="$run_id"
  )
  if [[ -n "$evidence_out" ]]; then
    evidence_filename="omi-c3b3-consumer-${run_id}.json"
    defines+=(
      --dart-define=OMI_CONSUMER_EVIDENCE_FILENAME="$evidence_filename"
      --dart-define=OMI_CONSUMER_EVIDENCE_EXIT=true
    )
  fi
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
if [[ -z "$evidence_out" && -z "$capture_out" ]]; then
  exec "$flutter_bin" run -d "$device" "${defines[@]}"
fi

if [[ -n "$capture_out" ]]; then
  echo "CAPTURE: build -> install -> launch -> simulator screenshot"
  "$flutter_bin" build ios --simulator --debug "${defines[@]}"
  app_bundle="$app/build/ios/iphonesimulator/Runner.app"
  if [[ ! -d "$app_bundle" ]]; then
    echo "ERROR: Flutter build did not produce $app_bundle" >&2
    exit 1
  fi
  xcrun simctl install "$device" "$app_bundle"
  xcrun simctl launch "$device" "$bundle_id" >/dev/null
  launched=1
  wait_seconds="${OMI_FIXTURE_CAPTURE_WAIT_SECONDS:-5}"
  if [[ ! "$wait_seconds" =~ ^[0-9]+$ ]] || (( wait_seconds < 1 || wait_seconds > 30 )); then
    echo "ERROR: OMI_FIXTURE_CAPTURE_WAIT_SECONDS must be 1..30." >&2
    exit 2
  fi
  sleep "$wait_seconds"
  xcrun simctl io "$device" screenshot "$capture_out" >/dev/null
  [[ -s "$capture_out" ]] || { echo "ERROR: simulator did not write $capture_out" >&2; exit 1; }
  echo "CAPTURE: wrote $capture_out"
  exit 0
fi

echo "EVIDENCE: build -> install -> launch -> collect native result"
"$flutter_bin" build ios --simulator --debug "${defines[@]}"
app_bundle="$app/build/ios/iphonesimulator/Runner.app"
if [[ ! -d "$app_bundle" ]]; then
  echo "ERROR: Flutter build did not produce $app_bundle" >&2
  exit 1
fi
xcrun simctl install "$device" "$app_bundle"
container="$(xcrun simctl get_app_container "$device" "$bundle_id" data)"
if [[ -z "$container" || ! -d "$container/Documents" ]]; then
  echo "ERROR: could not resolve the installed app's data container." >&2
  exit 1
fi
container_result="$container/Documents/$evidence_filename"
rm -f -- "$container_result"
xcrun simctl launch "$device" "$bundle_id" >/dev/null
launched=1

evidence_wait_seconds="${OMI_CONSUMER_EVIDENCE_WAIT_SECONDS:-180}"
if [[ ! "$evidence_wait_seconds" =~ ^[0-9]+$ ]] || (( evidence_wait_seconds < 1 || evidence_wait_seconds > 300 )); then
  echo "ERROR: OMI_CONSUMER_EVIDENCE_WAIT_SECONDS must be 1..300." >&2
  exit 2
fi
for ((second = 0; second < evidence_wait_seconds; second++)); do
  [[ -s "$container_result" ]] && break
  sleep 1
done
if [[ ! -s "$container_result" ]]; then
  echo "ERROR: native iOS result was not written within ${evidence_wait_seconds}s." >&2
  exit 124
fi
cp "$container_result" "$evidence_tmp"
"$node_bin" "$here/../tools/validate-consumer-evidence.mjs" \
  --file "$evidence_tmp" --run-id "$run_id" --shell ios
mv -f -- "$evidence_tmp" "$evidence_out"
echo "EVIDENCE: native iOS consumer document collected at $evidence_out"
