The `/dashboard` page embeds Grafana uid `omi-tv` (`/grafana/d/omi-tv/omi-tv`).
The live board used to live only in Grafana's database. The checked-in copy is
`dashboards/omi-tv.json`.

## Activation panels

Those two panels read Firestore-backed activation, not PostHog `Memory Created`:

| Panel | URL | Selector |
|---|---|---|
| Activation rate | `/api/omi/stats/activation?days=60` | `rate` |
| Activation (signup → activated) | `/api/omi/stats/activation?days=60` | `weeks[]` (`week`/`date`, `signups`, `activated`, `rate`) |

macOS signup is activated iff a conversation exists in the first 7 days.
PostHog coverage stays on viral-metrics as `summary.activationTelemetryCoverage`.

## Apply

`apply_omi_tv_dashboard.py` POSTs the JSON to the Grafana HTTP API. It no-ops
when `GRAFANA_TOKEN` is unset — do not invent a write token.

```bash
export GRAFANA_URL="https://admin.omi.me/grafana"   # optional
export GRAFANA_TOKEN="..."                         # Grafana service-account token
python3 web/admin/grafana/apply_omi_tv_dashboard.py
```

`gcp_admin.yml` runs the same script after a successful admin deploy. If the
workflow secret `GRAFANA_TOKEN` is absent, apply is skipped and the Cloud Run
ship still succeeds. Until the JSON is applied, `viral-metrics` overlays the
Firestore activation cache onto `summary.activationRate` and `activation[]`.
