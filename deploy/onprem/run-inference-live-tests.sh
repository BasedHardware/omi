#!/usr/bin/env bash
#
# Reproducible live tests for the on-prem inference services, run against the services
# exactly as declared in docker-compose.yml (profile `inference`) — no ad-hoc `docker run`
# servers. This is the codified version of the manual live-test recipes in SELFHOST_NOTES:
# it brings the compose profile up, waits for health, then runs each backend live test
# against its compose service.
#
#   diarizer  -> tests/contract/test_speaker_embedding_live_contract.py   (2 tests)
#   nllb      -> tests/contract/test_translation_nllb_live_contract.py     (4 tests)
#   parakeet  -> tests/container/test_parakeet_wer_gate.py                 (4 tests)
#
# Why each test still runs in a throwaway pytest container: the live tests are pytest suites
# that need the backend's own client code + deps, and they enforce a hermetic network guard
# that only allows loopback. We therefore join each compose service's network namespace
# (`--network container:<svc>`) so the server is reachable on 127.0.0.1 — the service itself
# is the one declared in the compose file, which is the point.
#
# Prerequisites (see SELFHOST_NOTES "Local inference (WP5)"):
#   - Inference model weights already provisioned into the `inference-models` volume
#     (the services won't reach HuggingFace on the internal network). If a service never
#     turns healthy, that provisioning is missing.
#   - The offline test image (default omi-onprem-backend-test:v2); built here if absent.
#   - LibriSpeech test-clean.tar.gz for the Parakeet WER gate; downloaded on the host
#     (outside the guard) into $LIBRISPEECH_CACHE if absent.
#
# Usage:  deploy/onprem/run-inference-live-tests.sh [diarizer|nllb|parakeet ...]
#   (no args = all three). Override defaults via env: COMPOSE_PROJECT, TEST_IMAGE,
#   LIBRISPEECH_CACHE, ENCRYPTION_SECRET.
set -euo pipefail

PROJECT="${COMPOSE_PROJECT:-omi-onprem}"
COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$COMPOSE_DIR/../.." && pwd)"
TEST_IMAGE="${TEST_IMAGE:-omi-onprem-backend-test:v2}"
LIBRISPEECH_CACHE="${LIBRISPEECH_CACHE:-$HOME/.cache/omi-onprem/librispeech}"
# Dev-only test secret; the live tests only need a non-empty, well-formed value.
ENC_SECRET="${ENCRYPTION_SECRET:-omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv}"
LIBRISPEECH_URL="https://www.openslr.org/resources/12/test-clean.tar.gz"

SERVICES=("$@"); [ ${#SERVICES[@]} -eq 0 ] && SERVICES=(diarizer nllb parakeet)

compose() { docker compose -p "$PROJECT" -f "$COMPOSE_DIR/docker-compose.yml" "$@"; }
cid() { echo "${PROJECT}-$1-1"; }

log() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }

# Run a python one-liner inside a service container (both python/python3 exist across images).
in_svc() { docker exec "$(cid "$1")" sh -c "python3 -c \"$2\" 2>/dev/null || python -c \"$2\""; }

wait_health() {
  local svc="$1" tries="${2:-90}" i
  for ((i=1; i<=tries; i++)); do
    if in_svc "$svc" "import urllib.request;urllib.request.urlopen('http://localhost:8080/health',timeout=3)" >/dev/null 2>&1; then
      echo "  $svc healthy (~$((i*4))s)"; return 0
    fi
    sleep 4
  done
  echo "  ERROR: $svc not healthy after $((tries*4))s — are model weights provisioned into the volume?" >&2
  return 1
}

# pytest in a throwaway container joined to the service's net namespace (loopback = the service).
svc_pytest() { # svc, target, extra -e args...
  local svc="$1" target="$2"; shift 2
  docker run --rm --network "container:$(cid "$svc")" \
    -e ENCRYPTION_SECRET="$ENC_SECRET" -e OPENAI_API_KEY=test -e LOCAL_DEVELOPMENT=true \
    "$@" \
    -v "$REPO_ROOT":/repo -w /repo/backend "$TEST_IMAGE" \
    /opt/venv/bin/python -m pytest "$target" -o addopts="" -p no:cacheprovider -q
}

# --- 0. offline test image -------------------------------------------------------------
if ! docker image inspect "$TEST_IMAGE" >/dev/null 2>&1; then
  log "Building offline test image $TEST_IMAGE"
  compose build backend
  docker build -f "$COMPOSE_DIR/Dockerfile.test" -t "$TEST_IMAGE" "$REPO_ROOT"
fi

# --- 1. bring the declared services up -------------------------------------------------
log "Bringing up compose inference profile: ${SERVICES[*]}"
compose --profile inference up -d "${SERVICES[@]}"
for svc in "${SERVICES[@]}"; do wait_health "$svc"; done

declare -A RESULT

# --- 2. per-service live tests ---------------------------------------------------------
for svc in "${SERVICES[@]}"; do
  case "$svc" in
    diarizer)
      log "diarizer: speaker-embedding live contract"
      if svc_pytest diarizer tests/contract/test_speaker_embedding_live_contract.py \
           -e HOSTED_SPEAKER_EMBEDDING_API_URL=http://127.0.0.1:8080; then
        RESULT[diarizer]=PASS; else RESULT[diarizer]=FAIL; fi
      ;;
    nllb)
      log "nllb: warm the model (first GPU inference compiles kernels; a cold call can exceed the client timeout and fail open to the source text)"
      in_svc nllb "import urllib.request,json;urllib.request.urlopen(urllib.request.Request('http://localhost:8080/v1/translate',data=json.dumps({'contents':['warmup'],'target_language_code':'it','source_language_code':'en'}).encode(),headers={'Content-Type':'application/json'}),timeout=60)" || true
      log "nllb: translation live contract"
      if svc_pytest nllb tests/contract/test_translation_nllb_live_contract.py \
           -e HOSTED_TRANSLATION_API_URL=http://127.0.0.1:8080 -e TRANSLATION_SERVICE_MODELS=nllb; then
        RESULT[nllb]=PASS; else RESULT[nllb]=FAIL; fi
      ;;
    parakeet)
      if [ ! -f "$LIBRISPEECH_CACHE/test-clean.tar.gz" ]; then
        log "parakeet: fetching LibriSpeech test-clean on the host (outside the guard) -> $LIBRISPEECH_CACHE"
        mkdir -p "$LIBRISPEECH_CACHE"
        curl -fL --retry 3 --retry-delay 2 -o "$LIBRISPEECH_CACHE/test-clean.tar.gz" "$LIBRISPEECH_URL"
      fi
      log "parakeet: WER regression gate (LibriSpeech test-clean)"
      if svc_pytest parakeet tests/container/test_parakeet_wer_gate.py \
           -e PARAKEET_URL=http://127.0.0.1:8080 -e LIBRISPEECH_CACHE=/cache -e WER_MAX_SAMPLES=10 \
           -v "$LIBRISPEECH_CACHE":/cache; then
        RESULT[parakeet]=PASS; else RESULT[parakeet]=FAIL; fi
      ;;
    *) echo "unknown service: $svc" >&2; exit 2 ;;
  esac
done

# --- 3. summary ------------------------------------------------------------------------
log "Summary"
rc=0
for svc in "${SERVICES[@]}"; do
  printf '  %-10s %s\n' "$svc" "${RESULT[$svc]:-?}"
  [ "${RESULT[$svc]:-FAIL}" = PASS ] || rc=1
done
exit "$rc"
