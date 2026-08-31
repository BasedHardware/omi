# Fallback / Resilience Telemetry

Cross-component contract for instrumenting fallback and fail-open branches (Python, Swift, Rust). The one-line rule lives in the root `AGENTS.md`; this file is the full prescription.

Silent UX healing is allowed; **silent ops is not**. When a branch changes provider, mode, correctness, or takes a fail-open path, call the shared helper — do **not** invent a new `*_fallback_total` counter or one-off PostHog event.

```
IF branch changes provider OR mode OR correctness OR fail-open taken:
  MUST call record_fallback / recordFallback with outcome
ELSE IF hard failure (no continue):
  error metric / Sentry / HTTP — NOT the fallback helper
ELSE (pure cache miss, expected soft path with no mode change):
  existing domain metric OR nothing — NOT fallback helper
```

| Field | Values |
|-------|--------|
| `component` / `area` | closed enum (`sync_dispatch`, `pusher`, `realtime_hub`, `ptt_cascade`, …) → else `other` |
| `from` / `to` | closed enums or `none` |
| `reason` | shared bounded set (`enqueue_failed`, `circuit_open`, `byok`, …) → else `other` |
| `outcome` | `recovered` (full UX restored) \| `degraded` (continues with hit) \| `exhausted` (no path left) |

Emitters:

- Python: `utils.observability.fallback.record_fallback` → `omi_fallback_total`
- Swift: `DesktopDiagnosticsManager.recordFallback` → `desktop_health_event`/`fallback_triggered`
- Rust: `fallback::record_fallback` → fixed-field `tracing` (`event=fallback`)

Legacy metrics (`llm_gateway_*`, `pusher_sessions_degraded`) stay — do not copy their fat label sets onto new sites. Alert on rates with denominators or dwell gauges; never page on raw absolute counts or successful `recovered` heals.

Optional ratchet (not CI): `python backend/scripts/check_fallback_instrumentation.py <touched files>` warns when a diff hunk adds fallback/fail-open/degraded branches without `record_fallback`/`recordFallback`.
