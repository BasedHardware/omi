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
| Sync enqueue_failed share | `sum(rate(omi_fallback_total{component="sync_dispatch",reason="enqueue_failed"}[10m])) / clamp_min(sum(rate(omi_sync_dispatch_attempts_total[10m])), 1e-9)` | Dashboard only until Cloud Run scrape — see [sync-dispatch-fallback.md](./sync-dispatch-fallback.md) |
| Pusher degraded sessions & ratio | `pusher_sessions_degraded`, `pusher_active_ws_connections`, ratio | **PAGE** — see [pusher-degraded.md](./pusher-degraded.md) |
| LLM gateway fallback rate | `sum(rate(llm_gateway_requests_total{fallback_used="true"}[30m])) / clamp_min(sum(rate(llm_gateway_requests_total[30m])), 1e-9)` | **Ticket** — see [llm-gateway-fallback.md](./llm-gateway-fallback.md) |

The dashboard text panel repeats paging policy: page only on exhausted outcomes, sync `enqueue_failed`, and pusher degraded ratio. Successful `outcome=recovered` heals are dashboard-only.

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
| Sync dispatch enqueue_failed share | Paused (Cloud Run scrape gap) — use Cloud Logging | [sync-dispatch-fallback.md](./sync-dispatch-fallback.md) |
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
| `audio_merge` | Cloud Tasks enqueue failure → inline merge on backend-sync | Logs only (`audio_merge:` prefix) | `record_fallback` on inline fallback + enqueue_failed share alert (mirror sync_dispatch) |
| `webhook` | Circuit breaker open → drop or defer partner delivery | `get_webhook_circuit_breaker` state per URL | `record_fallback` with `reason=circuit_open`, bounded URL host label; ticket-tier alert on open-share |

`audio_merge` and `webhook` are in the shared component allowlist so call sites can adopt the helper without schema churn later.
