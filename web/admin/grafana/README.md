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

## Plan cost and per-user economics

The All platforms board has three account-level panels backed by the admin-authenticated
`/api/omi/stats/plan-economics` route. They read only aggregate tables in
`based-hardware.omi_finops`; the cost producer and allocation contract are documented in
`backend/scripts/finops/README.md`. They are deliberately absent from the platform boards:
the producer does not attribute every request to a platform.

- Cost is the mean of seven consecutive settled usage days, multiplied by 30. The table
  separates allocated billed cost (including fixed Vertex PT) from estimated vendor STT.
  Margin includes the low STT estimate; the high-STT sensitivity appears alongside it.
  One-time charges and SaaS without a feed are excluded, so this is an estimated contribution
  view, not complete accounting profit.
- Revenue and paying-subscription counts come from the producer's Stripe snapshot for the
  last cost day. The coverage panel shows the actual snapshot date separately. These can
  differ from the live product MRR donut (different timestamp, coupon treatment, and grouping).
- Subscriber units divide by active/past-due subscriptions, not unique people. Active-user
  cost divides total window cost by the sum of daily cost-active users, not WAU or MAU.
  Free users keep their cost row; subscriber units and margin are N/A with no denominator.
  The per-user table puts active-user cost first and explains the subscriber basis per row,
  distinguishing Free's lack of paid subscriptions from an unavailable revenue mapping.
- The producer joins on the backend plan, so Omi Unlimited and Neo are one row. Unmapped
  plans remain visible with unavailable revenue; the reader never invents a split or $0.
- Latest usage must be D−2 or D−3 (one daily-job scheduling grace day), with all seven days,
  complete plan components, matching run IDs, plan/total conservation and all reconciliation
  checks within 0.5%. Otherwise monetary figures are N/A and the coverage panel explains why.
  Missing/stale revenue leaves valid costs visible but removes revenue and margins.
- A 30-minute in-process cache coalesces panel reads. It has no stale-on-error fallback and
  expires at UTC midnight. Queries are capped at 100 MB and never read user-level tables.

Deployment prerequisite: the existing `GCP_BILLING_SA_JSON` identity (or explicitly selected
ADC identity) needs BigQuery jobUser and read access to the three aggregate tables
`omi_finops.unit_cost_daily`, `omi_finops.unit_cost_reconciliation`, and
`omi_finops.plan_revenue_daily`, in addition to its existing billing-export access.
Prefer table-scoped `roles/bigquery.dataViewer`; it needs neither write access nor access
to `unit_cost_user_day`. The daily FinOps producer must also be
running and current; a dashboard deployment cannot refresh its source tables.

Validation: `npm test` and `npm run typecheck` in `web/admin`, plus
`python3 web/admin/grafana/test_build_dashboards.py` from the repository root.

## Apply dashboards

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
