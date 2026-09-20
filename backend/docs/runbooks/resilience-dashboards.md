# Resilience / fallback observability

Cross-platform view of backend Prometheus fallbacks, desktop PostHog heals, and Phase 1 paging policy.

## Grafana dashboard

| Field | Value |
|-------|-------|
| Title | Resilience / Fallbacks |
| UID | `omi-resilience-fallbacks` |
| Folder | Omi Services |
| Repo path | `backend/charts/monitoring/dashboards/omi-services/resilience-fallbacks.json` |
| Prod URL | `https://monitor.omi.me/` → Omi Services → Resilience / Fallbacks |

### Panels

| Panel | PromQL / source | Alert tier |
|-------|-----------------|------------|
| Fallback rate by component & outcome | `sum by (component, outcome) (rate(omi_fallback_total[5m]))` | Dashboard only (`recovered` is expected) |
| Sync enqueue uncertainty share | `sum(rate(omi_sync_dispatch_attempts_total{mode="enqueue_uncertain"}[10m])) / clamp_min(sum(rate(omi_sync_dispatch_attempts_total[10m])), 1e-9)` | Dashboard only until Cloud Run scrape — see [sync-dispatch-fallback.md](./sync-dispatch-fallback.md) |
| Pusher degraded sessions & ratio | `pusher_sessions_degraded`, `pusher_active_ws_connections`, ratio | **PAGE** — see [pusher-degraded.md](./pusher-degraded.md) |
| Real-traffic journey outcomes | `omi_journey_*`, `omi_capture_finalization_reconciliations_total`, `listen_finalization_durable_jobs`, `listen_finalization_oldest_nonterminal_age_seconds` | Traffic-gated product alerts plus separate scrape-source health — see [real-traffic-journeys.md](./real-traffic-journeys.md) |
| LLM gateway actual fallback rate | `sum(rate(llm_gateway_requests_total{route_serving_class="actual_fallback",fallback_used="true",fallback_reason!="none",outcome="success"}[30m])) / clamp_min(sum(rate(llm_gateway_requests_total{outcome=~"success|error"}[30m])), 1e-9)` | **Ticket** — see [llm-gateway-fallback.md](./llm-gateway-fallback.md) |
| LLM gateway ordinary LKG serving share | `sum(rate(llm_gateway_requests_total{route_serving_class="lkg",outcome="success"}[30m])) / clamp_min(sum(rate(llm_gateway_requests_total{outcome="success"}[30m])), 1e-9)` | Dashboard-only rollout exposure |
| 15 — Live STT chain exhaustion ratio | `omi_fallback_total{component="stt_selection",outcome="exhausted"} / omi_listen_accepted_total` on `job=backend-listen-metrics` | **WARN** at 0.35 / **PAGE** at 0.60 — see below |
| 16 — Live STT fallback-leg recovery by to_mode | recovered / attempts per `to_mode`, zero-filled, `stt_selection` + `stt_live_session` | **WARN** — a leg with ≥50 attempts and 0 recovered in 6h |
| 17 — Sync intake created share | `omi_sync_intake_total` created / (created+merged) | **WARN** via Cloud Logging until backend-sync is scraped |
| 18 — Live STT provider stream closes | `omi_stt_stream_close_total` by provider, reason | **PAGE** at ≥5 `provider_budget_exhausted` closes in 5m |

The dashboard text panel repeats paging policy: page only on exhausted outcomes, sync enqueue uncertainty, and pusher degraded ratio. Successful `outcome=recovered` heals are dashboard-only.

## Live STT chain exhaustion (2026-09-19)

`omi-stt-chain-exhausted-warn` / `omi-stt-chain-exhausted-page`

Sessions that die in `initialize_stt()` never construct a `LiveSTTAttempt`, so
`omi_live_stt_terminal_total{outcome="failure"} / omi_live_stt_accepted_total`
stays at zero even while the fleet is reconnecting. The dedicated rules divide
`omi_fallback_total{component="stt_selection",outcome="exhausted"}` by
`omi_listen_accepted_total` (the socket-accept counter). Both are Prometheus
Counters scraped as `job=backend-listen-metrics`; `increase()` is the correct
function (not a Stackdriver gauge).

Thresholds are from measured 2-minute fleet samples, not a remembered SLO:

| window (UTC) | accepts | exhausted | ratio | vs warn 0.35 / page 0.60 |
|---|---|---|---|---|
| 2026-09-18 09:00 (tolerable) | 227 | 57 | 0.251 | below both |
| 2026-09-19 04:40 (incident) | 688 | 562 | 0.817 | pages |
| 2026-09-19 09:30 (incident) | 913 | 811 | 0.888 | pages |
| 2026-09-20 14:30 (recovered) | 347 | 57 | 0.164 | below both |

Evidence layer for those numbers is Cloud Logging counts of
`omi_fallback_event component=stt_selection outcome=exhausted` on
backend-listen, divided by the measured accept counts. Prometheus evaluation
of the exact `increase()` expression is still owed by whoever can query prod
Prometheus/Grafana read-only.

The 16–25% recovered/tolerable ratio is itself standing degradation. Closing
the `initialize_stt()` blind spot also feeds the existing 10% live-STT warning
(`omi-journey-live-transcription-fail`) so that baseline becomes visible there.

**Safe next action:** confirm panel 15, then panel 16 for which `to_mode` is
dead, then Deepgram/Parakeet credentials or capacity. Do not rotate unrelated
keys.

## Live STT fallback-leg dead

`omi-stt-fallback-leg-dead` — warning, not a page. Watches
`component=~"stt_selection|stt_live_session"` grouped by `to_mode`. Deepgram
recovered 0 sessions in both the 2026-09-18 tolerable window and the 6h
incident window (handshake payment errors since 2026-09-14). Soniox recovered
at connect during 2026-09-19/20 monthly-budget exhaustion, so a 100% dead
mid-session hop looked healthy; recovered now waits for the first transcript.
A dead fallback leg is standing failure; paging waits for the chain-exhaustion
ratio or for provider-budget PAGE.

## Provider budget exhausted

`omi-stt-provider-budget` — **PAGE**. A vendor closing streams for
budget/quota/payment is never transient. It needs a human with a credit card
(or console access to raise a monthly cap). The cap is monthly and can trip
again before month end.

| What it looks like | Where |
|---|---|
| `Soniox stream closed: … organization_monthly_budget_exhausted` / `organization_balance_exhausted` / HTTP 402 | Soniox Console → organization or project limits (`monthly_budget_usd`). Resets at UTC month start. |
| Deepgram WebSocket upgrade HTTP 402 | Deepgram Console billing / project balances. |
| Velma `Monthly usage limit reached.` | Modulate Usage dashboard / Organization settings (monthly usage quota is set by Modulate support; optional monthly credit limit is admin-controlled). |

Evidence layer for the first evaluation is Cloud Logging counts of the Soniox
budget-close line on `backend-listen` (the incident logged that WARNING
because monthly budget was untyped as `connection_lost`). 5-minute samples:
2026-09-19 03:00Z=64, 04:40Z=87, 16:00Z=106 vs 2026-09-18 09:00Z=0 and
2026-09-20 07:30Z=0. Series `omi_stt_stream_close_total` is new: Prometheus
evaluation of the exact `increase()` expression is still owed.

**Safe next action:** confirm panel 18, raise the vendor cap, then confirm
panel 16 that `to_mode` recovered share is no longer zero.

## Sync intake fragmentation

`omi-sync-intake-fragmented`

`ingest_sync_conversation` increments `omi_sync_intake_total{outcome="created|merged"}`
and logs `omi_sync_intake outcome=…`. Prometheus does not scrape Cloud Run
`backend-sync` today (exporter allowlist is `backend` + `desktop-backend`),
so the alert evaluates Cloud Logging counts of that line. Brand-new series:
no production history. Expected created share ~1.0 in a per-chunk storm
(2026-09-19: 107 shards / 121 conversations for one account) versus `1/N`
for an N-chunk continuous recording. Assignment continuity is a separate PR;
this alert only makes the symptom visible.

## PostHog — desktop fallback insight

Desktop emits fallback telemetry via `DesktopDiagnosticsManager.recordFallback` → `AnalyticsManager.desktopHealthEvent`.

| Field | Value |
|-------|-------|
| Event name | `desktop_health_event` |
| Health event property | `health_event` = `fallback_triggered` (also duplicated as property `event`) |
| Dimensions | `area`, `from`, `to`, `reason`, `outcome` (`recovered` \| `degraded` \| `exhausted`) |

### Create the insight

1. Open PostHog → **Insights** → **New insight** → **Trends**.
2. **Event:** `desktop_health_event`.
3. **Filter:** `health_event` equals `fallback_triggered`.
4. **Default filter (primary view):** `outcome` equals `exhausted` — these are user-visible failures worth triage.
5. **Breakdown:** property `area` — compare `realtime_hub`, `ptt_cascade`, and bucketed `other`.
6. **Secondary views (duplicate insight or add series):**
   - `outcome` = `recovered` — silent heals; trend only, do not page.
   - `outcome` = `degraded` — partial fallback; correlate with backend panels above.
7. Save as **Desktop fallback triggered** and pin to the on-call dashboard next to Grafana.

Optional filters: `reason`, `from`, `to` for drill-down after an `exhausted` spike.

## Noise budget (first 2 weeks)

After Phase 1 deploy, cap **new PAGE alerts** at **≤2** for the first two weeks:

| Alert | Tier | Runbook |
|-------|------|---------|
| Pusher degraded session ratio | PAGE | [pusher-degraded.md](./pusher-degraded.md) |
| Live STT provider chain exhaustion | PAGE at 0.60 (warn at 0.35) | this runbook, panel 15 |
| Live STT provider budget exhausted | PAGE at ≥5 closes / 5m | this runbook, panel 18 |
| Sync dispatch enqueue uncertainty share | Paused (Cloud Run scrape gap) — use Cloud Logging | [sync-dispatch-fallback.md](./sync-dispatch-fallback.md) |
| LLM gateway fallback rate | Ticket (Slack / Linear) | [llm-gateway-fallback.md](./llm-gateway-fallback.md) |

Before adding a third PAGE alert:

1. Review false-positive rate on the two existing pages.
2. Reclassify noisy rules to ticket tier or dashboard-only.
3. Document the change in this runbook and the dashboard text panel.

Desktop PostHog `fallback_triggered` insights are **never** wired to paging in Phase 1–2.

## Deferred instrumentation (Phase 2+)

Not in this PR; track before adding PAGE alerts:

| Component | Fallback path | Current signal | Next step |
|-----------|---------------|----------------|-----------|
| `audio_merge` | Cloud Tasks enqueue failure → inline merge on backend-sync | Logs only (`audio_merge:` prefix) | `record_fallback` on inline fallback plus a dedicated rate alert; do not reuse sync enqueue-uncertainty semantics |
| `webhook` | Circuit breaker open → drop or defer partner delivery | `get_webhook_circuit_breaker` state per URL | `record_fallback` with `reason=circuit_open`, bounded URL host label; ticket-tier alert on open-share |

`audio_merge` and `webhook` are in the shared component allowlist so call sites can adopt the helper without schema churn later.
