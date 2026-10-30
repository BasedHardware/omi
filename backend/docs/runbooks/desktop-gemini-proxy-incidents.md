# Desktop Gemini proxy incidents

Use this runbook for `/v1/proxy/gemini/*` and `/v1/proxy/gemini-stream/*` failures on the Desktop Cloud Run backend. Do not combine `/v2/agent/status/provision`, `/screen-activity/sync`, GKE, or mobile backend errors with this signal: they have different owners and failure contracts.

## Establish the serving runtime first

Cloud Run revisions are immutable. Record the service, revision, image digest, traffic percentage, and release SHA before changing code or configuration. The health response for the Python backend must contain:

```json
{"service":"omi-desktop-backend","runtime_implementation":"python","backend_release_sha":"<40-char SHA>"}
```

The production revision implicated in SCA-286, `desktop-backend-6e319bade93b-30295602320-1`, was built from `desktop/macos/Backend-Rust/Dockerfile` at source `6e319…`; it cannot emit the Python event below. At that revision the Rust proxy used a 235-second attempt timeout inside a 240-second logical deadline, matching the observed 234–240-second tail. That match identifies the deadline that amplified the incident, but does not prove whether the provider stalled before headers, during request write, during body read, or returned its own 504.

The candidate release probe must pass the runtime marker and a real, bounded Gemini `generateContent` request before traffic promotion. Its evidence records only provider route, duration, and status—not generated content.

## Privacy-safe terminal evidence

The Python proxy writes exactly one `desktop_gemini_proxy_terminal` JSON event for each accepted request. Allowed dimensions are canonical UUID request ID, bounded lane/workload/client platform, trace, release/revision, provider route, credential source, model allowlist value, region, action, attempt, phase, outcome, status classes, retryability, payload-size/part-count buckets, and elapsed milliseconds.

Desktop transports send `X-Omi-Client-Platform` for telemetry only; they must not
send `X-App-Platform`, which activates auth-side platform persistence. The proxy
normalizes Linux to `other`, invalid values to `unknown`, and falls back to the
existing client-kind resolver when the telemetry header is absent. Accepted
`X-Omi-Request-Id` / `X-Request-Id` values must be canonical UUIDs; other values
are replaced with a generated UUID before logging or forwarding.

The gateway receives that request ID plus the generated lane/platform enums.
Both gateway and direct provider attempts persist `product_lane` and
`client_platform` in `llm_gateway_attempts`, alongside the existing
`feature=desktop_proactivity` and `app_platform=desktop` dimensions. The enum
vocabulary is owned by `backend/config/desktop_gemini_attribution.json`; keep it
stable for later per-user lane budgets. Join terminal events to attempt rows by
`request_id` for actual served model, payer, retry usage and rate-card cost;
terminal request counts alone do not establish lane spend. Missing tags on
older ledger rows remain unattributed; this change does not backfill them.

Never log Firebase UID, prompts, system instructions, inline media, generated text, URLs, headers, API keys, bearer tokens, raw exceptions, or provider response bodies.

Recent Python terminal outcomes:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="desktop-backend"
jsonPayload.event="desktop_gemini_proxy_terminal"
timestamp>="-30m"
```

Group in Log Analytics by `jsonPayload.provider_route`, `jsonPayload.phase`, `jsonPayload.outcome`, `jsonPayload.payload_size_bucket`, and `resource.labels.revision_name`. A request is terminal when one event exists for its `jsonPayload.request_id`; investigate duplicate or missing terminal events before trusting ratios.

Legacy Rust evidence for pre-Python revisions:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="desktop-backend"
(textPayload:"gemini_provider_request" OR jsonPayload.message:"gemini_provider_request")
timestamp>="-30m"
```

Legacy text logs do not provide equivalent phase attribution. Do not infer a Google outage, request-size cause, or cancellation behavior from latency alone.

## Classify before acting

| Signal | Meaning | First check |
|---|---|---|
| `phase=credential` or `phase=routing`, HTTP 503 | Omi route/identity failure before dispatch | ADC, project/location, secret presence, revision env |
| `phase=connect`, HTTP 504 | Provider connection was not established in 10s | egress/DNS/provider endpoint and region |
| `phase=write`, HTTP 504 | Request upload stalled | payload buckets, egress, provider endpoint |
| `phase=read` or `first_byte`, HTTP 504 | Dispatched request exceeded bounded wait | provider route/status, model, region, Cloud Run health |
| `outcome=provider_timeout`, HTTP 504 | Provider returned 408/504 | upstream status and provider status page |
| `outcome=provider_unavailable`, HTTP 502 | Provider returned another 5xx | upstream status class and provider route |
| `outcome=client_cancelled`, HTTP 499 | Caller disconnected; upstream work was cancelled | client lifecycle and request correlation |
| `phase=validation` or `metering` | Request rejected before provider work | allowlist, size/complexity, quota |

Compare Cloud Run request count, latency, container CPU, memory, concurrent requests, instance count, startup latency, and 5xx by exact revision. Saturation plus `pool` outcomes indicates local concurrency pressure; normal service metrics plus provider-phase outcomes indicates the stall is beyond local dispatch. Treat this as attribution, not proof of a vendor-wide incident.

Cloud Run maximum-request-timeout terminations carry no terminal event. Bind such an error group to `/v1/proxy/gemini/` or `/v1/proxy/gemini-stream/` with `requestUrl` evidence before attributing it to proxy streaming: on revisions carrying the 90-second owner described under Mitigation and rollback, those routes — streaming bodies and downstream sends included — cannot reach the platform timeout, so a genuine kill points at a route outside this proxy or a revision predating the owner (as in the October 8 lifetime incident below).

## Alerting

Create log-based counters from the terminal event and scope every policy to service `desktop-backend` and runtime `python`.

- Page on routing/credential failures when at least 3 occur in 5 minutes; these are operator-actionable and should never silently fall back to another credential path.
- Page on `(connect_timeout + write_timeout + read_timeout + provider_deadline_exceeded + provider_timeout) / accepted requests > 5%` for 10 minutes with at least 20 accepted requests. Do not page on raw timeout count at low traffic.
- Ticket when terminal events are missing or duplicated by request ID, or the release probe sees a missing/wrong runtime marker.
- Dashboard terminal outcome ratio by revision/provider/phase and the Cloud Run saturation metrics above.

## Mitigation and rollback

The route contract is one 90-second monotonic deadline from the outer ASGI entry (shared with the route), including upload, authentication/plan checks, reservations, metering, provider dispatch, response consumption and outward sends through BYOK middleware. Terminal events are queued until this outer owner observes delivery or cancellation, so a provider success cannot hide a later delivery deadline. Uploads have a 30-second total and 10-second idle limit plus the existing 5 MiB size cap. The provider retains its 75-second ceiling (and shorter connect/write/read/pool limits); it never extends the route budget. Cancellation cleanup has a one-second grace per task group. Non-stream deadline failures return a typed, non-retryable 504; after SSE headers commit, the same deadline emits a typed SSE error when delivery remains possible. An incomplete fixed-length response is aborted rather than falsely completed; HTTP status cannot be rewritten after headers commit. macOS generation uses a 100-second timeout; embedding retains 60 seconds. Client changes ship on the normal desktop train. Do not lengthen these values based only on temporal correlation. Clients must not replay local timeouts, HTTP 504s, ambiguous transport failures, or responses marked `X-Omi-Retryable: false`.

If a new Python revision regresses, move traffic back to the previously verified image digest using the normal production workflow. Do not rebuild an old SHA and call it a rollback. Preserve the failed revision's logs and candidate evidence. A code revert is separate from traffic movement; this runbook does not authorize deployment or production configuration changes.


## October 8, 2026 lifetime incident

The first affected revision, `9c5a7a077332` (created October 8 at 14:24Z), installed BYOKMiddleware, which inherits Starlette BaseHTTPMiddleware. The interval to `4ea5c83faba8` also contains reserved-capacity routing change `5a44037d64543`; `4ea5c83faba8` itself enabled Review routes. The provider's 75-second HTTP deadline already existed before this interval (`74d7b2d5cb450`).

The cancellation defect is reproducible locally with real ASGI receives and BYOK middleware: `Request.is_disconnected()` cancels its receive before BaseHTTPMiddleware's task-group checkpoint delivers a disconnect. A cancellation arriving during that poll can also be swallowed, so awaiting the cancelled watcher in `_cancel_on_disconnect` cleanup can hang even after an immediately successful provider call. The gateway's HTTP deadline is inside this cleanup boundary. This leaves no terminal event and permits Cloud Run to hit its 300-second timeout. The regression tests in `backend/tests/unit/test_desktop_proxy_lifetime.py` exercise both completed-call cleanup and actual disconnect delivery through middleware; fake `is_disconnected()` methods missed this interaction.

Five October 14 23:00–24:00Z proxy 504 request traces measured 299.999–300.001 seconds and had no application phase/terminal records. Those logs cannot prove the phase of each historical request. The reproduced cleanup hang and the independently verified unbounded upload/admission awaits establish concrete lifetime defects; do not attribute every historical 504 to uploads. The replacement blocks on ASGI receive only after draining the bounded upload, supervises the entire dependency/provider call, and classifies the route deadline before cancelling child work so it cannot be mislabeled as client cancellation.

Gateway Gemini embedding error terminals in October 13 12:00Z–October 15 12:00Z (the last hour was partial at read time) numbered 730: 724 `timeout_before_output` without an upstream HTTP status, three upstream 500s, two upstream 503s and one upstream 429. This is not evidence of dominant Vertex quota exhaustion. The BFF now preserves the typed timeout as non-retryable 504 instead of amplifying it into retryable `provider_unavailable` 503. Capacity/configuration changes require separate evidence. Desktop disconnect cancellation closes its active outbound HTTP call; it does not prove Vertex has stopped remote computation after gateway acceptance. No gateway deployment or Vertex quota change is part of this desktop-backend rollout.
