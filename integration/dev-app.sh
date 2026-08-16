#!/bin/bash
# One-command headed local demo: reuse or boot the existing stack with the
# demo persona, then launch the existing macOS shell. Does not fork a second
# service or shell launcher.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATHS="$(node "$HERE/lib/provenance.mjs" --paths 2>/dev/null || true)"
read -r CORE_REPO PLATFORM_REPO <<<"$(printf '%s' "$PATHS" | node -e '
  let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{try{const j=JSON.parse(s);console.log(`${j["core-foundation"]} ${j.platform}`)}catch{console.log("")}})')"
[[ -n "${CORE_REPO:-}" && -n "${PLATFORM_REPO:-}" ]] || { echo "ERROR: could not resolve core/platform roots." >&2; exit 1; }

STACK="$HERE/dev-stack.sh"
MACOS_LAUNCHER="$CORE_REPO/frontend/shells/macos/scripts/dev-run-macos.sh"
SERVICE_URL="http://127.0.0.1:4851"
GATEWAY_URL="http://127.0.0.1:8788"
# Pinned app origin. Verification runs lease 15290-15309 instead.
# Persistence across relaunch is a property only this path needs.
# Do not point this launcher at a leased port to "share code" with L3.
SURFACE_URL="http://127.0.0.1:5290"
RUNDIR="${OMI_DEV_STACK_RUNDIR:-/tmp/omi-dev-stack}"
OWNERFILE="$RUNDIR/service-owner.json"
case "${OMI_CHAT_MODEL:-}" in
  ""|test) ;;
  real)
    GATEWAY_URL="http://127.0.0.1:8791"
    ;;
  *)
    echo "ERROR: OMI_CHAT_MODEL must be unset, test, or real." >&2
    exit 2
    ;;
esac

MODE_ACCEPT=0
while (( $# )); do
  case "$1" in
    --accept) MODE_ACCEPT=1; shift ;;
    --help|-h)
      sed -n '2,8p' "$0"
      printf '%s\n' "usage: integration/dev-app.sh [--accept]"
      printf '%s\n' "  boots or reuses the local stack with OMI_SEED_PERSONA=demo and OMI_STT_ENGINE=mlx-whisper, then launches the macOS shell."
      printf '%s\n' "  OMI_CHAT_MODEL=real opts into the local real-model proxy (see integration/README.md)."
      printf '%s\n' "  stop the stack with: integration/dev-stack.sh --stop"
      exit 0
      ;;
    *) echo "ERROR: unknown option $1" >&2; exit 2 ;;
  esac
done

need() { command -v "$1" >/dev/null 2>&1 || { echo "ERROR: missing required tool $1" >&2; exit 1; }; }
for tool in bun node curl; do need "$tool"; done
[[ -x "$STACK" || -f "$STACK" ]] || { echo "ERROR: missing $STACK" >&2; exit 1; }
[[ -x "$MACOS_LAUNCHER" ]] || { echo "ERROR: macOS launcher is absent or not executable: $MACOS_LAUNCHER" >&2; exit 1; }

serving() { curl -fsS --max-time 1 "$1/ready" >/dev/null 2>&1; }

service_up=0
gateway_up=0
serving "$SERVICE_URL" && service_up=1
serving "$GATEWAY_URL" && gateway_up=1

if (( service_up == 1 && gateway_up == 0 )); then
  if [[ "${OMI_CHAT_MODEL:-}" == "real" ]]; then
    echo "ERROR: service is already on 4851 but the local model gateway is not on 8791." >&2
  else
    echo "ERROR: service is already on 4851 but the local test gateway is not on 8788." >&2
  fi
  echo "  Stop the partial stack: integration/dev-stack.sh --stop" >&2
  echo "  If 4851 is a stranger, find it: lsof -nP -iTCP:4851 -sTCP:LISTEN" >&2
  exit 1
fi
if (( service_up == 0 && gateway_up == 1 )); then
  if [[ "${OMI_CHAT_MODEL:-}" == "real" ]]; then
    echo "ERROR: local model gateway is already on 8791 but the service is not on 4851." >&2
  else
    echo "ERROR: local test gateway is already on 8788 but the service is not on 4851." >&2
  fi
  echo "  Stop the partial stack: integration/dev-stack.sh --stop" >&2
  exit 1
fi

booted=0
if (( service_up == 0 && gateway_up == 0 )); then
  OMI_SEED_PERSONA=demo OMI_STT_ENGINE=mlx-whisper "$STACK" --up
  booted=1
fi

[[ -f "$OWNERFILE" ]] || {
  echo "ERROR: no stack owner record at $OWNERFILE; cannot load the demo identity without printing secrets." >&2
  echo "  If a stranger holds 4851, stop it and rerun. Otherwise: integration/dev-stack.sh --stop" >&2
  exit 1
}

TOKEN_PATH="$(mktemp "${TMPDIR:-/tmp}/omi-dev-app-token.XXXXXX")"
chmod 600 "$TOKEN_PATH"
cleanup_token() { rm -f -- "$TOKEN_PATH"; }
trap cleanup_token EXIT

node -e '
  const fs = require("fs");
  const owner = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
  const ready = JSON.parse(fs.readFileSync(owner.readinessPath, "utf8"));
  if (typeof ready.devToken !== "string" || ready.devToken.length === 0) process.exit(2);
  fs.writeFileSync(process.argv[2], ready.devToken, { encoding: "utf8", mode: 0o600 });
' "$OWNERFILE" "$TOKEN_PATH" || {
  echo "ERROR: stack owner record did not yield a readiness token." >&2
  exit 1
}
DEV_TOKEN="$(read -r value < "$TOKEN_PATH"; printf '%s' "$value")"
rm -f -- "$TOKEN_PATH"
trap - EXIT
[[ -n "$DEV_TOKEN" ]] || { echo "ERROR: readiness token was empty." >&2; exit 1; }

SETTINGS_JSON="$(curl -fsS --max-time 3 -H "Authorization: Bearer ${DEV_TOKEN}" "$SERVICE_URL/v1/settings")"
STATUS_JSON="$(curl -fsS --max-time 3 "$SERVICE_URL/v1/qa/status")"
IDENTITY="$(SETTINGS_JSON="$SETTINGS_JSON" STATUS_JSON="$STATUS_JSON" node -e '
  const settings = JSON.parse(process.env.SETTINGS_JSON);
  const status = JSON.parse(process.env.STATUS_JSON);
  const name = settings?.identity?.displayName;
  const owner = status?.seed?.owner_account_id;
  const persona = status?.seed?.persona;
  if (typeof name !== "string" || typeof owner !== "string") process.exit(2);
  process.stdout.write(persona ? `${name} (owner ${owner}, persona ${persona})` : `${name} (owner ${owner})`);
')" || {
  echo "ERROR: could not read demo identity from the running service." >&2
  exit 1
}

stt_engine="$(STATUS_JSON="$STATUS_JSON" node -e '
  try {
    const status = JSON.parse(process.env.STATUS_JSON);
    if (typeof status?.stt_engine === "string") process.stdout.write(status.stt_engine);
  } catch {}
')"

printf 'omi local demo app\n\n'
printf '  base URL   %s\n' "$SERVICE_URL"
if [[ "${OMI_CHAT_MODEL:-}" == "real" ]]; then
  printf '  gateway    %s  (local real-model proxy — Chat UI says External model response; attachments still fail closed)\n' "$GATEWAY_URL"
else
  printf '  gateway    %s  (local test gateway — chat generation is not a real model)\n' "$GATEWAY_URL"
fi
printf '  identity   %s\n' "$IDENTITY"
printf '  surface    %s\n' "$SURFACE_URL"
if [[ "$stt_engine" == "mlx-whisper" ]]; then
  printf '  stt        mlx-whisper (on-device; your speech should appear in Listen)\n'
else
  printf 'ERROR: this stack is not transcribing real speech (stt=%s).\n' "${stt_engine:-missing}" >&2
  printf '       Listen will show canned "Local transcription is connected." rows instead of what you say.\n' >&2
  printf '       Stop it and boot the headed path: integration/dev-stack.sh --stop\n' >&2
  printf '       then: OMI_SEED_PERSONA=demo OMI_STT_ENGINE=mlx-whisper integration/dev-stack.sh --up\n' >&2
  printf '       after scripts/stt-bootstrap.sh if the on-device engine is not on this machine.\n' >&2
  exit 1
fi
if (( booted )); then
  printf '  stack      booted with the demo persona for this process\n'
elif [[ "${OMI_CHAT_MODEL:-}" == "real" ]]; then
  printf '  stack      reused the listeners already serving 4851 and 8791\n'
else
  printf '  stack      reused the listeners already serving 4851 and 8788\n'
fi
printf '\n  stop the stack with:  integration/dev-stack.sh --stop\n\n'

macos_args=(--api "$SERVICE_URL" --route home)
(( MODE_ACCEPT )) && macos_args+=(--accept)

# Human demo is headed. --accept is the headless-safe check and must not
# inherit a Dock icon or steal focus from a headed parent.
if (( MODE_ACCEPT )); then
  unset OMI_HEADED
else
  export OMI_HEADED=1
fi

OMI_API_TOKEN="$DEV_TOKEN" \
OMI_SURFACE_PORT=5290 \
OMI_APP_NAME="${OMI_APP_NAME:-omi-on-local-demo}" \
exec "$MACOS_LAUNCHER" "${macos_args[@]}"
