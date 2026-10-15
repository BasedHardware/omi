# Route-error preparation: held

These definitions are candidates, outside the canonical alert sources. No metric
creation, alert import, suppression or application rollout is performed by these
files. User authorization to create log metrics does not establish semantic
coverage or admit the proposed thresholds.

The platform-request counter covers every Cloud Run service through the monitored
resource's service label. Its finite extractors recognize only the two Gemini
route families and four actions; other routes/actions remain unclassified. It
must not be described as complete framework route-template coverage. No URL,
model identifier, user identifier or arbitrary action becomes a metric label.

A read-only inventory on 2026-10-15 found 29 production Cloud Run services. Ten
map to source here (six FastAPI, three Next.js, one Bun); nineteen require producer
owner/source handoffs. `structured-route-contract.json` describes the required
finite route registry and terminal-event adapters. Platform timeouts, process
loss, streaming failures after HTTP200 and missing request logs require separate
coverage evidence; application events must never be added to platform counts.

`grafana-candidates.json` keeps all proposals paused: desktop-backend 10-minute
5xx ratio >5% with at least100 requests, long504 volume, and an uncalibrated Armor
escalation. `admission-holds.json` records the missing metric/label/replay proofs.
The existing broad4xx and Armor rules remain active. There is no blanket mute or
storm inhibition: a Cloud Run polling counter alone cannot prove which sampled
load-balancer/Armor requests belong to the same route.

Run `python3 backend/scripts/check_route_error_preparation.py` offline.
`--verify-live` reads descriptor metadata with the active service account and
prints only statuses. Before creation, verify log coverage, latency units,
bounded classification, current metric absence/ownership, actual increments,
per-service templates and consumer-specific replay. Creating a metric requires
the brief's scoped production operator or the parent; no human login is needed.
