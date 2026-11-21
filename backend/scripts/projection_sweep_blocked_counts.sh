#!/usr/bin/env bash
# Aggregate the last 30 minutes of reader sweep summaries for one serving revision.
set -euo pipefail

project=${1:?usage: projection_sweep_blocked_counts.sh PROJECT REVISION}
revision=${2:?usage: projection_sweep_blocked_counts.sh PROJECT REVISION}
[[ "$revision" =~ ^backend-integration-[a-z0-9-]+$ ]] || { echo "expected a backend-integration revision" >&2; exit 2; }

filter="resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"backend-integration\" AND resource.labels.revision_name=\"$revision\" AND (jsonPayload.message=~\"event=batch_projection action=sweep(_blocked)? outcome=summary \" OR textPayload=~\"event=batch_projection action=sweep(_blocked)? outcome=summary \")"
gcloud logging read "$filter" --project="$project" --freshness=30m --format=json |
  jq -e --arg revision "$revision" '
    if length == 0 then error("no sweep summaries in the window") else . end
    | map((.jsonPayload.message // .textPayload)
        | (capture(" blocked=(?<blocked>[0-9]+) error=[0-9]+ blocked_groups=(?<groups>.+)$") // error("summary lacks attribution"))
        | (.groups | fromjson) as $groups
        | if ($groups | type) != "array" then error("blocked groups must be an array")
          elif (([$groups[][2]] | add) // 0) == (.blocked | tonumber) then $groups
          else error("blocked groups differ from sweep total") end)
    | {revision: $revision, summaries: length,
       blocked: ([.[][][2]] | add // 0),
       groups: ([.[][]] | group_by(.[0:2])
         | map({reason: .[0][0], worker_image_digest: .[0][1], blocked: (map(.[2]) | add)}))}
  '
