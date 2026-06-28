#!/usr/bin/env bash
#
# Mixpanel raw-event export, resumable.
#
# Streams /api/2.0/export one UTC day at a time into gzipped JSONL files.
# Re-running the script skips days already on disk; it is safe to interrupt
# (Ctrl+C, kill, VM reboot) and re-launch — at most one in-flight day is
# redone. See scripts/migration/README.md for the full plan.
#
# Required env:
#   MP_SERVICE_USER   — Mixpanel service account username (<name>.<rand>.mp-service-account)
#   MP_SERVICE_SECRET — service account secret
#   MP_PROJECT_ID     — Mixpanel project id (e.g. 3314908 for Based Hardware)
#
# Optional env:
#   MP_START          — first UTC day, YYYY-MM-DD (default: 2024-03-01)
#   MP_END            — last UTC day inclusive (default: yesterday UTC)
#   MP_OUT            — output directory (default: $HOME/mp-export)
#   MP_GCS_BUCKET     — if set, gsutil-mirror each chunk to gs://$BUCKET/mixpanel/<project>/
#   MP_MIN_DISK_GB    — refuse to start if free space below this (default: 20)
#   MP_PACE_SECONDS   — target seconds between request starts (default: 65; ≈55 req/hr)

set -uo pipefail

: "${MP_SERVICE_USER:?MP_SERVICE_USER not set}"
: "${MP_SERVICE_SECRET:?MP_SERVICE_SECRET not set}"
: "${MP_PROJECT_ID:?MP_PROJECT_ID not set}"

MP_START="${MP_START:-2024-03-01}"
MP_END="${MP_END:-$(date -u -d 'yesterday' +%Y-%m-%d)}"
MP_OUT="${MP_OUT:-$HOME/mp-export}"
MP_GCS_BUCKET="${MP_GCS_BUCKET:-}"
MP_MIN_DISK_GB="${MP_MIN_DISK_GB:-20}"
MP_PACE_SECONDS="${MP_PACE_SECONDS:-65}"

CHUNKS="$MP_OUT/chunks"
MANIFEST="$MP_OUT/manifest.jsonl"
FAILURES="$MP_OUT/failures.jsonl"
RUN_LOG="$MP_OUT/run.log"
LOCK="$MP_OUT/.lock"

mkdir -p "$CHUNKS"
touch "$MANIFEST" "$FAILURES" "$RUN_LOG"

# Single-instance guard. flock holds for the lifetime of FD 9.
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "another instance is running on $LOCK; abort" >&2
  exit 1
fi

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$RUN_LOG" >&2
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { log "FATAL: missing required command: $1"; exit 1; }
}
require_cmd curl
require_cmd gzip
require_cmd jq
require_cmd flock
require_cmd sha256sum

# ---- Pre-flight: disk space ----
free_gb=$(df -P "$MP_OUT" | awk 'NR==2 {print int($4/1024/1024)}')
if (( free_gb < MP_MIN_DISK_GB )); then
  log "FATAL: only ${free_gb}GB free in $MP_OUT, need ${MP_MIN_DISK_GB}GB"
  exit 1
fi

# ---- Pre-flight: auth probe ----
probe_day=$(date -u -d 'yesterday' +%Y-%m-%d)
log "auth probe day=$probe_day project=$MP_PROJECT_ID"
probe_status=$(curl -sG -o /dev/null -w '%{http_code}' --max-time 60 \
  -u "$MP_SERVICE_USER:$MP_SERVICE_SECRET" \
  'https://data.mixpanel.com/api/2.0/export' \
  --data-urlencode "from_date=$probe_day" \
  --data-urlencode "to_date=$probe_day" \
  --data-urlencode "project_id=$MP_PROJECT_ID" \
  --data-urlencode 'limit=1' || true)
if [[ "$probe_status" != "200" ]]; then
  log "FATAL: auth probe returned HTTP $probe_status"
  exit 1
fi
log "auth probe OK"

# ---- Decide what to fetch ----
# Source of truth is the disk: a day is "done" iff its file exists and is a
# valid gzip (or a 0-byte sentinel for legitimately empty days). The manifest
# is informational. This makes resume robust against any partial-write or
# crash-after-rename-before-manifest race.
is_day_done() {
  local d=$1
  local f="$CHUNKS/events-$d.jsonl.gz"
  [[ -f "$f" ]] || return 1
  [[ ! -s "$f" ]] && return 0
  gzip -t "$f" 2>/dev/null
}

all_dates=()
d="$MP_START"
while [[ "$d" < "$MP_END" || "$d" == "$MP_END" ]]; do
  all_dates+=("$d")
  d=$(date -u -d "$d + 1 day" +%Y-%m-%d)
done

todo=()
done_count=0
for d in "${all_dates[@]}"; do
  if is_day_done "$d"; then
    done_count=$((done_count + 1))
  else
    todo+=("$d")
  fi
done

est_hours=$(( (${#todo[@]} * MP_PACE_SECONDS + 3599) / 3600 ))
log "plan: ${#all_dates[@]} total days, $done_count already done, ${#todo[@]} to fetch"
log "estimated wallclock: ~${est_hours}h at pace ${MP_PACE_SECONDS}s/req"

if (( ${#todo[@]} == 0 )); then
  log "nothing to fetch; exiting"
  exit 0
fi

# ---- Fetch one day with retries ----
fetch_one() {
  local d=$1
  local f="$CHUNKS/events-$d.jsonl.gz"
  local raw="$f.raw.tmp"
  local gz="$f.gz.tmp"
  local attempts=0
  local backoff=60
  local http_status="000"

  while (( attempts < 5 )); do
    attempts=$((attempts + 1))
    rm -f "$raw" "$gz"
    local start_epoch
    start_epoch=$(date +%s)

    http_status=$(curl -sG -o "$raw" -w '%{http_code}' --max-time 1800 \
      -u "$MP_SERVICE_USER:$MP_SERVICE_SECRET" \
      'https://data.mixpanel.com/api/2.0/export' \
      --data-urlencode "from_date=$d" \
      --data-urlencode "to_date=$d" \
      --data-urlencode "project_id=$MP_PROJECT_ID" \
      2>>"$RUN_LOG" || echo "000")

    case "$http_status" in
      200)
        if [[ ! -s "$raw" ]]; then
          # Legitimate empty day: write 0-byte sentinel.
          : > "$f"
          rm -f "$raw"
          local elapsed=$(( $(date +%s) - start_epoch ))
          printf '{"date":"%s","bytes":0,"sha256":"","lines":0,"http_status":200,"empty":true,"attempts":%d,"elapsed_s":%d,"finished_at":"%s"}\n' \
            "$d" "$attempts" "$elapsed" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$MANIFEST"
          log "OK $d empty attempts=$attempts elapsed=${elapsed}s"
          return 0
        fi
        if ! gzip < "$raw" > "$gz"; then
          log "FAIL $d gzip error (attempt $attempts/5)"
          rm -f "$raw" "$gz"
          sleep "$backoff"; backoff=$((backoff * 2))
          continue
        fi
        rm -f "$raw"
        mv "$gz" "$f"
        local bytes
        bytes=$(stat -c %s "$f")
        local sha
        sha=$(sha256sum "$f" | awk '{print $1}')
        local lines
        lines=$(zcat "$f" | wc -l)
        local elapsed=$(( $(date +%s) - start_epoch ))
        printf '{"date":"%s","bytes":%d,"sha256":"%s","lines":%d,"http_status":200,"empty":false,"attempts":%d,"elapsed_s":%d,"finished_at":"%s"}\n' \
          "$d" "$bytes" "$sha" "$lines" "$attempts" "$elapsed" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$MANIFEST"
        log "OK $d lines=$lines bytes=$bytes attempts=$attempts elapsed=${elapsed}s"
        return 0
        ;;
      401|403)
        log "FATAL: HTTP $http_status on $d — service account creds rejected"
        rm -f "$raw" "$gz"
        exit 2
        ;;
      429)
        log "429 $d — backing off ${backoff}s (does not count against retry budget)"
        rm -f "$raw" "$gz"
        sleep "$backoff"
        backoff=$((backoff * 2))
        attempts=$((attempts - 1))
        ;;
      *)
        log "FAIL $d HTTP $http_status (attempt $attempts/5), sleeping ${backoff}s"
        rm -f "$raw" "$gz"
        sleep "$backoff"
        backoff=$((backoff * 2))
        ;;
    esac
  done

  log "GIVEUP $d after 5 attempts (last_status=$http_status)"
  printf '{"date":"%s","last_status":"%s","finished_at":"%s"}\n' \
    "$d" "$http_status" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$FAILURES"
  rm -f "$raw" "$gz"
  return 1
}

# ---- Main loop with rate-limit pacing ----
fetched=0
failed=0
trap 'log "interrupted; safe to re-run to resume"; exit 130' INT TERM

for d in "${todo[@]}"; do
  cycle_start=$(date +%s)

  if fetch_one "$d"; then
    fetched=$((fetched + 1))
    if [[ -n "$MP_GCS_BUCKET" ]]; then
      f="$CHUNKS/events-$d.jsonl.gz"
      if [[ -f "$f" ]]; then
        gsutil -q cp "$f" "gs://$MP_GCS_BUCKET/mixpanel/$MP_PROJECT_ID/$(basename "$f")" \
          || log "WARN gcs upload failed for $d (file is on disk locally)"
      fi
    fi
  else
    failed=$((failed + 1))
  fi

  cycle_elapsed=$(( $(date +%s) - cycle_start ))
  remaining=$(( MP_PACE_SECONDS - cycle_elapsed ))
  if (( remaining > 0 )); then
    sleep "$remaining"
  fi
done

# ---- Summary ----
total_lines=$(jq -s 'map(select(.lines != null) | .lines) | add // 0' "$MANIFEST")
total_bytes=$(jq -s 'map(select(.bytes != null) | .bytes) | add // 0' "$MANIFEST")
fail_recorded=$(wc -l < "$FAILURES" | tr -d ' ')

log "DONE fetched_this_run=$fetched failed_this_run=$failed manifest_lines=$total_lines manifest_bytes=$total_bytes total_failures=$fail_recorded"

if (( failed > 0 )); then
  log "$failed days failed this run; re-run to retry (resume is automatic)"
  exit 1
fi
