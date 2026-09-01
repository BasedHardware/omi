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

The Python proxy writes exactly one `desktop_gemini_proxy_terminal` JSON event for each accepted request. Allowed dimensions are request ID, trace, release/revision, provider route, credential source, model allowlist value, region, action, attempt, phase, outcome, status classes, retryability, payload-size/part-count buckets, and elapsed milliseconds.

Never log Firebase UID, prompts, system instructions, inline media, generated text, URLs, headers, API keys, bearer tokens, raw exceptions, or provider response bodies.

Recent Python terminal outcomes:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="omi-desktop-backend"
jsonPayload.event="desktop_gemini_proxy_terminal"
timestamp>="-30m"
```

Group in Log Analytics by `jsonPayload.provider_route`, `jsonPayload.phase`, `jsonPayload.outcome`, `jsonPayload.payload_size_bucket`, and `resource.labels.revision_name`. A request is terminal when one event exists for its `jsonPayload.request_id`; investigate duplicate or missing terminal events before trusting ratios.

Legacy Rust evidence for pre-Python revisions:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="omi-desktop-backend"
textPayload:"gemini_provider_request"
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

## Alerting

Create log-based counters from the terminal event and scope every policy to service `omi-desktop-backend` and runtime `python`.

- Page on routing/credential failures when at least 3 occur in 5 minutes; these are operator-actionable and should never silently fall back to another credential path.
- Page on `(connect_timeout + write_timeout + read_timeout + provider_deadline_exceeded + provider_timeout) / accepted requests > 5%` for 10 minutes with at least 20 accepted requests. Do not page on raw timeout count at low traffic.
- Ticket when terminal events are missing or duplicated by request ID, or the release probe sees a missing/wrong runtime marker.
- Dashboard terminal outcome ratio by revision/provider/phase and the Cloud Run saturation metrics above.

## Mitigation and rollback

The bounded contract is one provider dispatch, a 75-second non-stream logical deadline, 10-second connect, 15-second write, 70-second read, 5-second pool wait, and 30-second streaming idle-gap timeout. Do not lengthen these values based only on temporal correlation. Clients must not replay local timeouts, HTTP 504s, ambiguous transport failures, or responses marked `X-Omi-Retryable: false`.

If a new Python revision regresses, move traffic back to the previously verified image digest using the normal production workflow. Do not rebuild an old SHA and call it a rollback. Preserve the failed revision's logs and candidate evidence. A code revert is separate from traffic movement; this runbook does not authorize deployment or production configuration changes.
