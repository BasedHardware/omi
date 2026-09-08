# Silent failure detection — alerts that fire when a 2xx is a lie

**What these alerts mean:** a production path is failing in a way that HTTP
status codes and request counts cannot express, or the evidence a user-path
alert depends on has gone missing.

**Owner:** platform team.

## Why this runbook exists

On 2026-08-19 the desktop chat path was broken for roughly 19 hours and no
alert fired. Nothing was down in the sense any existing alert could observe:

- The SSE endpoint committed `HTTP 200` and its headers *before* the generator
  ran, then streamed an in-band error frame. Every status-code monitor read the
  turn as a success.
- The gateway rejected those requests during request validation, **before a
  route was selected**. Pre-route rejections are counted by
  `llm_gateway_request_rejections_total`, not by `llm_gateway_requests_total`.
  For the whole outage the chat lane's request counter showed
  **100% success**, because the failing requests never reached it.
- `omi-journey-chat-fail` already existed and is shaped correctly, but at the
  time `omi_journey_accepted_total{journey="chat_response"}` was emitted by the
  Cloud Run `backend` service, which Prometheus did not scrape. The counter
  had been flat at zero for its whole existence, so the rule could never fire.
  (Resolved since: the Cloud Run metrics bridge delivers these series today,
  and `chat_response` is covered by `omi-journey-signal-dead`.)
- Only one client population was affected. A second, larger population on the
  same endpoint stayed healthy and kept every aggregate ratio green.

Each of these is a general failure mode, not a one-off. The rules below exist
to make each of them observable.

## Where to look

All five rules link to **Grafana → Resilience / Fallbacks**:

| Panel | Shows |
|---|---|
| 12 — LLM gateway pre-route rejections | The rejection counter that lane success rate cannot see. |
| 13 — LLM gateway lane success rate | Per-lane success share, zero-filled so a never-successful lane plots at 0 rather than vanishing. |
| 14 — Journey signal liveness | Accepted attempts per journey. A flat zero line here means that journey's alerts are dead, not that the path is healthy. |

## The alerts

### LLM Gateway — clients rejected before routing

`omi-llm-gateway-invalid-requests`

```promql
sum(increase(llm_gateway_request_rejections_total{error_class="invalid_request"}[30m])) or vector(0)
```

Fires at `>= 2` sustained for 30m. A well-formed client does not send parameters
the gateway rejects. A non-zero, sustained count means some client population is
failing **every** attempt, while lanes and status codes stay green.

The threshold is deliberately low. During the 2026-08-19 outage the affected
population produced only 2–16 rejections per 30 minutes, because it was a small
fraction of total chat traffic. A rate-based threshold sized for the busy path
would not have fired.

**Verify:** split production request logs by client user agent. Look for a
population whose responses are uniformly small and fast — an error frame is
orders of magnitude smaller and faster than a real completion.

**Safe next action:** identify the rejected parameter and the client that sends
it. The gateway kill switch (`OMI_LLM_CHAT_AGENT_ROUTE=direct`) is the
documented mitigation while the client or the forwarding allowlist is fixed.

### LLM Gateway — lane failing a large share of real requests

`omi-llm-gateway-lane-failure-ratio` — per lane, `$A >= 20 && $B > 0.25` over 1h.

### LLM Gateway — lane has served no successful request

`omi-llm-gateway-lane-zero-success` — per lane, `$A >= 20 && $B < 1` over 6h.

```promql
sum by (lane_id) (increase(llm_gateway_requests_total{outcome="success"}[6h])) or sum by (lane_id) (increase(llm_gateway_requests_total[6h])) * 0
```

The `or ... * 0` term is load-bearing. A lane that has *never* succeeded has no
`outcome="success"` series at all, so a plain ratio produces no series and no
alert. The zero-fill is what makes total failure visible rather than invisible.

The six-hour window exists for bursty lanes. Several lanes are idle for most
hours of the day; a one-hour gate never accumulates enough attempts on those
lanes to evaluate. Both rules run together: the 1h rule detects quickly on busy
lanes, the 6h rule eventually catches quiet ones.

**Verify:** read the lane's `provider_rejection` and `error_class` labels before
touching configuration.

### Journey outcomes — a journey stopped reporting

`omi-journey-signal-dead`

```promql
(sum by (journey) (increase(omi_journey_accepted_total{journey=~"pusher_session|capture_finalization"}[1h])) < bool 1) * on() group_left() (sum(increase(llm_gateway_requests_total[1h])) > bool 100) or (sum by (journey) (increase(omi_journey_accepted_total{journey="chat_response"}[1h])) < bool 1) * on() group_left() (sum(increase(llm_gateway_requests_total{lane_id="omi:auto:chat-agent"}[1h])) > bool 20)
```

This is the alert for the alerts. Every real-traffic journey rule assumes its
journey counter is being scraped. When that assumption breaks, the rule does not
fail loudly — it goes quiet, which looks exactly like health.

The first arm covers the backend-listen journeys (`pusher_session`,
`capture_finalization`) and gates on total gateway traffic. The second arm
covers `chat_response`, whose counter arrives through the Cloud Run metrics
bridge, and gates on the chat-agent lane instead: that lane measured min 9,
p01 15, p05 23 requests/hour over 7 production days, so `> 20` demands
liveness only at above-p05 chat demand and stays silent in quiet hours.

The rule fires when a journey reports **zero** accepted attempts in an hour
while its own traffic gate proves demand exists. `noDataState` is `Alerting`:
if the series vanish entirely, that is the failure, not the absence of one.

**Verify:** check whether the emitting service is still running *and* still
scraped, in that order. Do not treat a missing journey signal as evidence that
the user path is working.

**Safe next action:** restore the metrics path first. A journey whose counter is
dead has no alerting coverage at all until it is scraped again.

### AI chat — agent lane traffic dropped to zero

`tz_chat_agent_requests_zero` — `< 5` requests in 1h, sustained 30m.

## What these alerts still cannot see

Anything emitted only by a Cloud Run service and not covered by the bridge
alerts. `backend` and `desktop-backend` application metrics now arrive through
the Cloud Run GMP sidecar → Cloud Monitoring → isolated exporter path
(`job="cloud-run-application-metrics"`), verified live at ~28MB / 52,662
`omi_*` series per prod scrape (#12146). That bridge is itself guarded:
`omi-cloud-run-egress-down`, `omi-cloud-run-egress-query-rejected`, and
`omi-cloud-run-metric-names-unnormalized` page when it breaks, and
`chat_response` is inside `omi-journey-signal-dead`'s selector, so a bridge
regression that silences the chat counters pages on its own. `backend-sync`
and `backend-integration` still have no application-metrics path; alerts that
would read their in-process counters do not exist.

## Adding a journey alert later

Every alert that reads a journey counter inherits that counter's failure mode: if the
counter dies, the alert does not fail — it goes quiet, and quiet is indistinguishable
from healthy. `omi-journey-chat-fail` sat armed and unfirable for its entire existence
for exactly this reason.

`test_every_alerted_journey_is_covered_by_the_liveness_rule` makes that impossible to
ship again. Any rule whose expression selects `journey="..."` on an `omi_journey_*` or
`omi_client_journey_*` metric must have that journey inside `omi-journey-signal-dead`'s
selector, so a dead counter pages on its own.

The only escape is `LIVENESS_EXEMPT_JOURNEYS` in the contract test, which
requires a written reason. It is empty as of 2026-08-30: the last entry
(`chat_response`, kept while its counter could not arrive) was deleted in the
same change that added `chat_response` to the liveness rule behind a
chat-agent-lane traffic gate. The test asserts a journey is never both exempt
and covered, so the two cannot silently disagree.

## Backtest

Every rule was replayed against seven days of production data at 15-minute resolution
before it was merged. A rule that would have been noisy in the past week is not ready
to page anyone.

| Rule | Breaching evaluations | What it caught |
|---|---|---|
| `omi-llm-gateway-invalid-requests` | 58 / 673 (8.6%) | The desktop chat outage window, and nothing after the fix deployed. |
| `omi-llm-gateway-lane-failure-ratio` | 100 / 21,314 (0.47%) | `omi:auto:translation` only. |
| `omi-llm-gateway-lane-zero-success` | 350 / 21,472 (1.6%) | `omi:auto:translation` and `omi:auto:web-search`. |
| `omi-journey-signal-dead` | 0 / 1,346 | No false positives on the two journeys that do report. |
| `tz_chat_agent_requests_zero` | 0 / 673 | No false positives; floor was 9 against a threshold of 5. |

Every breach in that table is a real defect, not noise. Re-run the backtest when changing
a threshold — a rule that fires on healthy weeks gets muted, and a muted rule is worse
than no rule.
