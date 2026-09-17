The `/dashboard` page embeds Grafana uid `omi-tv` (`/grafana/d/omi-tv/omi-tv`).
The checked-in copies are `dashboards/*.json` — three boards linked by the
All / macOS / Mobile switcher at the top of each:

| uid | scope |
|---|---|
| `omi-tv` | all platforms combined (source of truth, edit this one) |
| `omi-tv-macos` | the same board scoped to macOS (`platform=macos` on the PostHog routes; desktop series of `profitability`) |
| `omi-tv-mobile` | the same board scoped to iOS/Android/iPadOS (`platform=mobile`; mobile series of `profitability`). Mobile is fully instrumented in PostHog for usage metrics (iOS since 2025-03, Android since 2026-05) but emits no `Sign In Completed`, so its cohorts anchor on first-seen-any-event. Desktop-only surfaces (floating bar, crash telemetry, the desktop notifications toggle) are explicit placeholders. |

Account-level metrics with no platform dimension (mentor "Omi says" volumes,
the notifications-enabled gauge) live on the All board only — see
`ACCOUNT_LEVEL_TITLES` in the builder.

The viral metrics route uses one person key (`COALESCE(person_id, distinct_id)`)
for all user counts. `growthAccounting` and `stickinessTrend` contain complete
UTC calendar weeks only; the current trailing seven-day view is exposed
separately as top-level `rollingGrowth` (with current values mirrored under
`summary` for tile compatibility) and powers the explicitly labeled
"Last 7 days (rolling)" tile. Growth points expose positive `inactive`, its
`priorActive` denominator, `inactiveRate`, and `netActiveChange`; `inactiveLoss`
is the negative chart projection used by the stacked growth chart. The
`establishedRetention` series measures people active in both preceding complete
weeks and reports the current-week numerator, denominator, and rate.

The "Successful usage / capture output" panel keeps event families separate:
saved/reconciled `Memory Created` conversation creators, macOS transcribed
speech (`Desktop Recording Stopped` with positive `word_count`), and macOS
completed assistant users (`chat_agent_query_completed`). `Recording Started`
is intentionally not treated as successful usage; the mobile board shows only
the saved-conversation series because the other two events have no mobile
equivalent.

## Build

`omi-tv.json` is the only hand-edited board. After changing it, run

```bash
python3 web/admin/grafana/build_dashboards.py
```

which derives `omi-tv-macos.json` / `omi-tv-mobile.json` and re-applies the
shared contract to all three: timezone pinned to `America/New_York`, hourly
auto-refresh, switcher links, `platform=` pinned on every PostHog-backed
query (viral-metrics, dau-trends, retention, k-factor — behavioral coverage
in `web/admin/lib/__tests__/platform-scope-routes.test.ts`), exact-attribution
revenue fields on the platform boards, and every daily/weekly/monthly date
column routed through the proxy's `_tzdates` rewrite (bare `YYYY-MM-DD`
strings parse as UTC midnight, which renders as 8 pm the previous NYC day and
hides the latest day). The builder is idempotent; commit all three outputs.
`test_build_dashboards.py` (manifest check `grafana-dashboard-build`) enforces
the contract.

## Activation panels

Activation sources differ by board:

| Board | Source | Definition |
|---|---|---|
| All, macOS | `/api/omi/stats/activation?days=60` (Firestore) | macOS signup activated iff a conversation exists in the first 7 days (`rate`, `weeks[]`) |
| Mobile | `viral-metrics?platform=mobile` (PostHog telemetry) | first-seen mobile user with `Memory Created` within 7 days (`activation[]`, `summary.activationRate`) |

PostHog coverage for the macOS telemetry path stays on viral-metrics as
`summary.activationTelemetryCoverage`; the Firestore compat overlay applies
only to the macOS scope.

## Apply

Grafana's database is the layout master — drag/resize edits made in the UI
persist there **and survive applies**: `apply_omi_tv_dashboard.py` fetches the
live board first and keeps its gridPos for every panel that already exists
(matched by id), so a dashboards-diff merge updates panel content without
reverting manual arrangement. Only brand-new panels land at their authored
position. It runs when a push changes `dashboards/*.json` (see the gated step
in `gcp_admin.yml`) or on `workflow_dispatch`. It no-ops when `GRAFANA_TOKEN` is
unset — do not invent a write token.

```bash
export GRAFANA_URL="https://admin.omi.me/grafana"   # optional
export GRAFANA_TOKEN="..."                         # Grafana service-account token
python3 web/admin/grafana/apply_omi_tv_dashboard.py
```

Note: large POSTs through the admin.omi.me rewrite get dropped — CI uses the
repo variable `GRAFANA_URL` pointing at the direct Cloud Run URL.
