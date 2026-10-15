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

## Omi TV v2 — isolated Direction A board

`omi-tv-v2` is a separate UID. Its source is `build_wall_dashboard.py`, called
by `build_dashboards.py`; the three legacy board files retain their existing
contract. `apply_omi_tv_dashboard.py` accepts the new UID and still preserves
live layout on subsequent applies. This slice does not switch `/dashboard`.

The admin-authenticated `/api/omi/stats/wall` returns the 22 contract IDs plus
explicit capture-week-1 and plan-prepay-cash lines. Definitions, UTC cutoffs,
primary/entry attribution and qualification come from `lib/qualified-activity.ts`.
A coalesced 15-minute in-process cache preserves source refresh stamps. Expired
and previous-UTC-day payloads (at most 24h old) are served while one refresh runs;
previous-day or failed-refresh payloads dim. A cold process returns loading cards
within five seconds and retains the computation with Next's `after()`. The board
polls every 30s, so results appear without a manual reload. All-source failure
cannot replace the last good payload; failed refreshes have a 30s retry cooldown.
A partial payload with exhausted transient queries is retried on the next poll,
rather than holding its nulls for 15 minutes. PostHog carries its upstream `last_refresh`, or the
execution completion time of our live HogQL aggregate when the API omits it.
A cached upstream result without a refresh receipt stays unknown. Payload-cache
reads never advance source refresh timestamps.
Production background progress requires instance-based CPU: the existing admin
Cloud Run deploy contract (`config/public-build-contract.json`, prod flags) pins
`--no-cpu-throttling`. Next's `after()` retains work but does not allocate host CPU.
Minimum instances remain zero, and caches remain disposable/per-instance; restarts
or new instances return loading cards again. The 30s poll discovers their results.
The change takes effect only through the normal authorized deployment.

It performs no Firestore cache writes. Bounded last-good reads are an explicit
wall-only exception to the general stale-data rule. Source timestamps never advance
on a cache read. Each PostHog query has classified, secret-safe failure telemetry
and bounded retries. Six-period cohort/established trends use two-period reads,
splitting time-limited pairs into single periods; MAU uses separate 30-day reads.
The 180-day lookback, denominator and observation windows remain unchanged. Counts use primary qualified platform; cohort rates use
entry platform and include the full denominator. Rates do not add across splits:
the split numerators and denominators do. Missing sources remain null.

Each metric is one native **Canvas** panel, backed by Infinity as the only
external plugin. Canvas's SVG-icon element renders a data-only card through
Grafana's built-in SVG sanitizer. The card's background/border encloses the
label, scope chip, value, delta, platform splits, complete-period sparkline and
footnote. There are no floating subpanels, HTML overrides or custom JavaScript.
Responsive constraints keep the complete card inside narrow laptop columns.

Healthy live aggregates use full contrast. Stale, partial, explicitly material-gap
proxies and all synthetic fixtures are dimmed. A proxy label alone does not dim
an otherwise healthy audited aggregate. Fixture cards always say **FIXTURE**.
Cohort-rate deltas use percentage points; count and monetary deltas use relative
percent change. Scope chips say all or macOS; entry/primary attribution is in the
panel description and diagnostics. Money is compact at thousands, without cents
above $100. Full source reasons and versions remain in the diagnostics table.

MAU keeps two completed 30-day periods to stay within PostHog's query budget;
other usage/cohort trends retain six completed periods. Cohort anchors are still
first-seen proxies, with a bounded 180-day history check, not Firebase signups.
MCP, Windows/web foreground coverage and strict saved-state/source joins remain
incomplete and are disclosed. A bare MCP marker never qualifies.

Local verification (no production Firebase/Stripe key, token minting or Grafana):

```bash
hostctl context
# Follow machine-config's local-container guide; the env command only selects its socket.
~/machine-config/scripts/container-runtime.zsh start
eval "$(~/machine-config/scripts/container-runtime.zsh env)"
source ~/.local/bin/gcp-agent-env.sh ro-prod
python3 web/admin/grafana/verify_wall_local.py serve  # keep foreground in one terminal
python3 web/admin/grafana/verify_wall_local.py provision  # another terminal, same Docker env
# Python environment with playwright + Chromium installed:
python3 web/admin/grafana/verify_wall_local.py screens
```

`serve` reads only the authorized PostHog key and Shopify fields from the supplied
local files, uses the existing development admin bypass, binds localhost:3107,
and disables Firebase and real Stripe credentials. Stripe uses the clearly
labeled synthetic fixture at `lib/__fixtures__/wall-stripe.json`. Fixture dates
are fixed; when old, they correctly dim. `--replay /absolute/aggregate.json`
replays a locally saved wall response without changing its source timestamps;
this requires non-production mode and `DEV_BYPASS_AUTH=1`. Production rejects
both fixture modes. Local Grafana binds localhost:3207; the helper intentionally
fails if its container name exists rather than replacing an unrelated instance.
The provisioned board rewrites the proxy URL only in its local copy.

Run records and screenshots are written only to
`/Users/dazheng/workspace/omi/data/run-2026-10-14-omi-tv-metrics/`;
never commit that workspace run directory in the public repository. The local
verifier uses the `omi-tv-v2-prod-fix-rev1-1440.png` / `-1920.png` screenshot names.
Tracked UI-evidence copies belong under `.agent-artifacts/ui-evidence/`.

Deploy prerequisites and limits:

- Existing admin auth/proxy and Infinity datasource `omi-admin-api` must reach the
  new route. PostHog needs `POSTHOG_PERSONAL_API_KEY`, `POSTHOG_PROJECT_ID` and
  optionally `POSTHOG_HOST`. No production Firebase key is needed by the wall.
- Shopify reuses `SHOPIFY_STORE` and `SHOPIFY_ACCESS_TOKEN`; alternatively supply
  `SHOPIFY_CLIENT_ID`/`SHOPIFY_CLIENT_SECRET` for a client-credentials exchange.
  The app needs **read_orders**. Older history beyond 60 days needs the separate
  approved history scope. Order/line/refund pagination is checked; truncation
  returns null. USD shop-money is required until an approved FX mapping exists.
  `OMI_TV_DEVICE_SKUS` adds approved device SKUs; conservative audited titles are
  a proxy until the SKU/bundle mapping is signed off. Refunds restate sale weeks.
- Stripe uses the existing library's active/past-due status pagination, excludes
  marketplace apps, and includes every price of allowed Omi products. Explicit
  extra enterprise product IDs use `OMI_TV_PLAN_PRODUCT_IDS`; unknown products and
  tiered prices remain coverage gaps. JPY is zero-decimal and never treated as
  USD cents. Non-USD amounts need approved FX; otherwise they are excluded and
  the book is partial. The live book has no fabricated prior/trend. ARPMAU divides available MRR by qualified MAU. Live MRR over completed MAU is
  explicitly dimmed and labeled as a cutoff-mismatched proxy; the contract's
  same-cutoff close still needs a corrected MRR snapshot. Historic corrupt FinOps
  aggregates cannot repair dropped products/JPY from totals alone. Synthetic
  same-cutoff fixtures exercise the strict snapshot arithmetic.
- Billing reuses `infra-costs` billing mode with aggregate-only reads, skipping
  Firestore/ledger diagnostics and the estimated fallback. Select ro-prod ADC
  locally; the runtime billing identity needs its existing BigQuery read/job
  permissions and provider invoice bindings. Missing provider/STT coverage is
  partial and dim; gross margin is null until recognized revenue and complete
  variable cost coverage are available. Cost/MAU uses the matching 30 days through D−2.
- Payer churn, activated-to-paid, message ratings and trustworthy crash coverage
  need their missing aggregate sources. Zero crash events never produce 100%.

Validation: `npm test`, `npm run typecheck`, `npm run lint` in `web/admin`,
`python3 web/admin/grafana/test_build_dashboards.py`, and `make preflight`.
Opt-in live aggregate smoke checks: `OMI_TV_LIVE_CHECK=1 npm test --
lib/__tests__/wall-live.test.ts` with the authorized read-only source env loaded.


### MCP activity split (2026-10-15 threshold ruling)

WAU, DAU and MAU include UTC days with at least two `MCP Tool Use Succeeded`
events (per-success, unsampled `schema_version=2`), `initiator=user|unknown`.
`scheduled_agent`, legacy sampled `MCP Tool Call`, and bare `MCP Active` never count.
MCP days deduplicate by the same resolved actor key as app activity. The additive
**MCP-only** split contains people with no qualified app activity in that metric's
window. People who use both retain their primary app platform, so app + MCP-only
splits sum to the headline and nobody is counted twice. ARPMAU and cost/MAU use the
corresponding MCP-inclusive MAU. Cohort, established-retention, saved-creator and
assistant definitions are unchanged/app-scoped; MCP is not silently added there.

Marker availability is observed independently of qualifying days. Before any v2
marker rows are present in the bounded observation history the split is **—**,
with **MCP marker not deployed** in the card and diagnostics. Observed marker rows
with no qualifying people produce **0**, not an unavailable split. A metadata row
carries availability even for an empty qualified result and never enters counts.

A bounded daily cadence screen excludes person/client/UTC-day streams with ≥10
calls, ≥8 positive gaps, ≥2h span, ≥80% one tool, a mean gap of 60–86,400 seconds,
and gap CV ≤0.15. Calls from unflagged clients may still qualify that person.
Regularity statistics remain inside HogQL; no raw identities leave the aggregate.
This is a daily approximation of the threshold evidence. **Cross-day and separated
burst regularity detection is deferred**; client names alone never establish intent.
Activity metrics and derived MAU units carry the MCP schema-2 definition revision.
