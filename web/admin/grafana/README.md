The `/dashboard` page embeds Grafana uid `omi-tv` (`/grafana/d/omi-tv/omi-tv`).
The live board used to live only in Grafana's database. The checked-in copies
are `dashboards/*.json` — three boards linked by the All / macOS / Mobile
switcher at the top of each:

| uid | scope |
|---|---|
| `omi-tv` | all platforms combined (source of truth, edit this one) |
| `omi-tv-macos` | macOS-native panels + desktop series from `profitability` |
| `omi-tv-mobile` | the honestly-available mobile view (mobile DAU/retention are not instrumented; the board says so) |

## Build

`omi-tv.json` is the only hand-edited board. After changing it, run

```bash
python3 web/admin/grafana/build_dashboards.py
```

which derives `omi-tv-macos.json` / `omi-tv-mobile.json` and re-applies the
shared contract to all three: timezone pinned to `America/New_York`, switcher
links, and every daily/weekly/monthly date column routed through the proxy's
`_tzdates` rewrite (bare `YYYY-MM-DD` strings parse as UTC midnight, which
renders as 8 pm the previous NYC day and hides the latest day). The builder is
idempotent; commit all three outputs. `test_build_dashboards.py` (manifest
check `grafana-dashboard-build`) enforces the contract.

## Activation panels

Those two panels read Firestore-backed activation, not PostHog `Memory Created`:

| Panel | URL | Selector |
|---|---|---|
| Activation rate | `/api/omi/stats/activation?days=60` | `rate` |
| Activation (signup → activated) | `/api/omi/stats/activation?days=60` | `weeks[]` (`week`/`date`, `signups`, `activated`, `rate`) |

macOS signup is activated iff a conversation exists in the first 7 days.
PostHog coverage stays on viral-metrics as `summary.activationTelemetryCoverage`.

## Apply

`apply_omi_tv_dashboard.py` POSTs every `dashboards/*.json` (uids restricted
to the three boards above) to the Grafana HTTP API. It no-ops when
`GRAFANA_TOKEN` is unset — do not invent a write token.

```bash
export GRAFANA_URL="https://admin.omi.me/grafana"   # optional
export GRAFANA_TOKEN="..."                         # Grafana service-account token
python3 web/admin/grafana/apply_omi_tv_dashboard.py
```

`gcp_admin.yml` runs the same script after a successful admin deploy. If the
workflow secret `GRAFANA_TOKEN` is absent, apply is skipped and the Cloud Run
ship still succeeds. Until the JSON is applied, `viral-metrics` overlays the
Firestore activation cache onto `summary.activationRate` and `activation[]`.
