#!/usr/bin/env bash
# Aggregate-only read-only counterpart of the incident measure.sh.
# Usage: measure-request-storm-alerts.sh [start-UTC] [end-UTC] [output-directory]
set -euo pipefail
source ~/.local/bin/gcp-agent-env.sh ro-prod
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
START="${1:-2026-09-21T04:00:00Z}"
END="${2:-2026-10-12T04:00:00Z}"
OUT="${3:-$(mktemp -d -t omi-request-storm)}"
mkdir -p "$OUT"
metric='metric.type="loadbalancing.googleapis.com/https/request_count" AND resource.type="https_lb_rule" AND resource.labels.project_id="based-hardware"'
edge="$metric AND metric.labels.response_code=\"429\" AND (resource.labels.backend_target_name=\"custom-domains-api-omi-me-backend-49a4-be\" OR resource.labels.backend_target_name=\"custom-domains-api-omi-me-backend-sync-49a4-be\" OR resource.labels.backend_target_name=\"custom-domains-api-omi-me-backend-listen-49a4-be\")"
sync="$metric AND resource.labels.backend_target_name=\"custom-domains-api-omi-me-backend-sync-49a4-be\""
fetch() {
  # Feed Authorization through stdin config: never print tokens or place them in argv.
  gcloud auth print-access-token |
    awk '{print "header = \"Authorization: Bearer " $0 "\""}' |
    curl --fail-with-body --silent --show-error --config /dev/stdin --get \
      'https://monitoring.googleapis.com/v3/projects/based-hardware/timeSeries' \
      --data-urlencode "filter=$1" \
      --data-urlencode "interval.startTime=$START" --data-urlencode "interval.endTime=$END" \
      --data-urlencode 'aggregation.alignmentPeriod=300s' \
      --data-urlencode "aggregation.perSeriesAligner=$2" \
      --data-urlencode 'aggregation.crossSeriesReducer=REDUCE_SUM' \
      --data-urlencode "aggregation.groupByFields=$3" \
      --data-urlencode 'pageSize=100000' -o "$4"
}
fetch "$edge" ALIGN_RATE resource.labels.backend_target_name "$OUT/edge.json"
fetch "$sync" ALIGN_SUM metric.labels.response_code "$OUT/sync.json"
python3 "$ROOT/.github/scripts/replay_request_storm_alerts.py" --edge "$OUT/edge.json" --sync "$OUT/sync.json" --start "$START" --end "$END"
echo "Aggregate evidence: $OUT"
