#!/bin/bash
# ONE-COMMAND local launch of the macOS Omi shell against a local backend.
#
# This is the stable entry point for the top-level dev stack launcher. Its
# contract (flags, env, exit codes, verdict lines) is meant to be called by
# scripts/dev-stack.sh, not just by a human.
#
#   ./scripts/dev-run-macos.sh --route chat        # LIVE Chat against the local backend
#   ./scripts/dev-run-macos.sh --api http://127.0.0.1:4747 --route home
#   ./scripts/dev-run-macos.sh --accept            # headless acceptance, exits nonzero on zero traffic
#
# Env (all overridable, all with local-sane defaults — nothing is hardcoded at
# a build step, so repointing at another backend never needs a recompile):
#   OMI_API_BASE_URL   default http://127.0.0.1:4801   (new backend)
#   OMI_API_TOKEN      dev token; if unset and an issuer is set, it is fetched
#   OMI_DEV_TOKEN_ISSUER_URL   optional dev-mode token issuer
#   OMI_SURFACE_PORT   fixed 5290
#   OMI_SURFACES_DIST  default ../../packages/surfaces/dist
#   OMI_BUILD_DIR / OMI_APP_NAME   scratch bundle location and name
#
# THE PORT IS AN ORIGIN, NOT A PREFERENCE. The surface's IndexedDB is keyed by
# origin including the port. Changing OMI_SURFACE_PORT between launches is a
# silent wipe of local surface storage, so this script refuses to pick an
# ephemeral one and warns loudly if you override it.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
core="$(cd "$here/../.." && pwd)"

api_base="${OMI_API_BASE_URL:-http://127.0.0.1:4801}"
accept=0
route="home"

while (( $# )); do
  case "$1" in
    --api) api_base="${2:?--api needs a URL}"; shift 2 ;;
    --route) route="${2:?--route needs a name}"; shift 2 ;;
    --accept) accept=1; shift ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "ERROR: unknown argument '$1'" >&2; exit 2 ;;
  esac
done

case "$route" in
  home|memories|conversations|tasks|folders|chat|settings|listen) ;;
  *)
    echo "ERROR: --route must be one of home|memories|conversations|tasks|folders|chat|settings|listen" >&2
    exit 2
    ;;
esac

if normalized_api_base="$(node "$here/scripts/qa-url-policy.mjs" api "$api_base" 2>/dev/null)"; then
  api_base="$normalized_api_base"
else
  echo "ERROR: API base URL is invalid or forbidden for this QA launcher." >&2
  exit 1
fi

token_issuer="${OMI_DEV_TOKEN_ISSUER_URL:-}"
if [[ -n "$token_issuer" ]]; then
  if normalized_token_issuer="$(node "$here/scripts/qa-url-policy.mjs" issuer "$token_issuer" 2>/dev/null)"; then
    token_issuer="$normalized_token_issuer"
  else
    echo "ERROR: dev token issuer URL is invalid or forbidden for this QA launcher." >&2
    exit 1
  fi
fi

app_name="${OMI_APP_NAME:-omi-on-fe-shells}"
# Never, ever collide with a shipping bundle. Scratch names only.
if [[ ! "$app_name" =~ ^omi-on-[A-Za-z0-9][A-Za-z0-9.-]*$ ]]; then
  echo "ERROR: OMI_APP_NAME must look like omi-on-<scratch> (got '$app_name')." >&2
  echo "       A shipping 'Omi' or 'Omi Beta' bundle must never be touched." >&2
  exit 1
fi

port="${OMI_SURFACE_PORT:-5290}"
if [[ "$port" != "5290" ]]; then
  echo "ERROR: OMI_SURFACE_PORT must remain 5290 for the production-shaped macOS origin." >&2
  echo "       IndexedDB is origin-keyed; another port is a different product store." >&2
  exit 1
fi

dist="${OMI_SURFACES_DIST:-$core/packages/surfaces/dist}"
if [[ ! -f "$dist/index.html" ]]; then
  echo "surfaces dist missing — building it (cold checkout path)..."
  ( cd "$core" && corepack pnpm install && corepack pnpm --filter @omi-core/surfaces build )
fi
if [[ ! -f "$dist/index.html" ]]; then
  echo "ERROR: still no surfaces dist at $dist" >&2
  exit 1
fi

export OMI_BUILD_DIR="${OMI_BUILD_DIR:-$core/.build/on-fe-shells}"
export OMI_APP_NAME="$app_name"
export OMI_SURFACES_DIST="$dist"
export OMI_SURFACE_PORT="$port"

# Inherited overrides would let main.swift bypass the frozen candidate origin
# or load stale/remote content. The QA launcher owns the surface selection.
unset OMI_SURFACE_URL OMI_SURFACE_PATH
export OMI_SURFACE_QUERY="route=${route}&platform=desktop"
export OMI_API_BASE_URL="$api_base"

token="${OMI_API_TOKEN:-}"
if [[ -z "$token" && -n "$token_issuer" ]]; then
  echo "MODE: LIVE — no OMI_API_TOKEN set; requesting one from the dev issuer."
  token="$(curl -fsS --max-time 5 -X POST "$token_issuer" || true)"
  if [[ -z "$token" ]]; then
    echo "ERROR: dev token issuer returned no token." >&2
    exit 1
  fi
fi
# The shell has its own Keychain custody, so "no env token" is not the same as
# "no credential". Only the item's existence is checked; the secret is never
# read out here.
keychain_has_credential=0
if [[ -z "$token" ]]; then
  kc_account="api@${api_base%/}"
  if security find-generic-password \
      -s "scratch.${app_name}.credential" -a "$kc_account" >/dev/null 2>&1; then
    keychain_has_credential=1
    echo "MODE: LIVE — no OMI_API_TOKEN set; the shell holds Keychain custody for this backend."
  fi
fi

if [[ -z "$token" && $keychain_has_credential -eq 0 ]]; then
  echo "ERROR: LIVE mode needs a credential." >&2
  echo "  Set OMI_API_TOKEN=<dev token>, or OMI_DEV_TOKEN_ISSUER_URL=<issuer>." >&2
  echo "  (No Keychain custody exists yet for $api_base either.)" >&2
  echo "  Refusing to launch a shell that would silently show an empty app." >&2
  exit 1
fi
if [[ -n "$token" ]]; then
  export OMI_API_TOKEN="$token"
fi

# Fail fast and legibly if the backend simply is not up. The curl status and
# HTTP code remain separate so a refused connection cannot fail open.
curl_rc=0
code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$api_base/" 2>/dev/null)" || curl_rc=$?
if (( curl_rc != 0 )) || [[ "$code" == "000" ]]; then
  echo "ERROR: no backend reachable at $api_base" >&2
  echo "  Start the backend first, or pass --api <url>." >&2
  exit 1
fi
# The token is never echoed, never placed in argv, never in the URL.
echo "MODE: LIVE — route $route on backend $api_base (reachable, HTTP $code), credential held by the shell."

if (( accept )); then
  export OMI_ACCEPTANCE=1 OMI_ACCEPTANCE_EXIT=1
  export OMI_SNAPSHOT_PATH="${OMI_SNAPSHOT_PATH:-$OMI_BUILD_DIR/acceptance.png}"
  # run-shell.sh's 15s watchdog is tuned for a probe, not for an acceptance run
  # that must wait for the surface's async refresh to actually reach the host.
  # Too short a bound turns a slow-but-passing run into a timeout, which is the
  # kind of flake that gets a real gate disabled.
  export OMI_ACCEPTANCE_WAIT_SECONDS="${OMI_ACCEPTANCE_WAIT_SECONDS:-45}"
fi

exec "$here/scripts/run-shell.sh"
