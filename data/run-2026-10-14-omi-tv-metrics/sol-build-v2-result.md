# Omi TV v2 — slice 1 builder result

Repository: `BasedHardware/omi`, task worktree `/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-omi-tv-v2-upstream-keep-clean`, branch `lane/omi-tv-v2`. Prepared base: `origin/main` `7787982bcc3937f9d9add0fdccedde124bf5f9fd`. No sync/fetch was needed for the parent-prepared branch. No push, PR creation, production deployment, production Grafana access, Firestore writes, Secret Manager, IAM, production Firebase credentials, or `api.omi.me` calls.

## Delivered

- Shared audited allowlist v2 as platform data, SQL fragments, exclusions, UTC complete-day/week windows, capture-day proxies, primary attribution and entry attribution. Windows/web/MCP coverage stays explicitly incomplete. Entry cohorts include zero-qualified-day people. Established retention freezes primary platform over both denominator weeks.
- Authenticated `/api/omi/stats/wall`: all 22 contract IDs, plus `activation.capture_week1_share` and `revenue.plan_prepay_usd_week`. Values include previous periods, splits, numerator/denominator counts, windows, status/reason, data-through, upstream refresh and definition version. Missing sources are null, including an unsupported Stripe book that cannot support even a partial USD amount.
- Coalesced 15-minute in-process payload cache, invalidated at UTC midnight, with no Firestore writes or stale-on-error fallback. PostHog upstream `last_refresh` is preserved; absent watermark means dimmed/unknown freshness, not reader-time freshness. Derived units inherit missing denominator freshness.
- Status/product-scoped Stripe book audit; no price-ID listing, no dropped prices within allowed plan products, correct zero-decimal JPY major units, no implicit FX, visible unmapped/tiered coverage. Shopify paginates orders and rejects incomplete nested line/refund data, excludes unpaid/test/cancelled orders, restates refunds into sale weeks, and separates plan-prepay cash from hardware/MRR.
- Billing-mode aggregate reader reuses `infra-costs`, explicitly skips Firebase/user-ledger diagnostics, and never falls back to estimated costs. Cost/MAU uses the matching 30 settled days through D−2.
- Separate `omi-tv-v2` UID, five Direction A columns, native core stat/time-series/table panels with the existing Infinity datasource UID. Blue better / orange worse / grey flat; fixed macOS → Mobile → Other split line; native value mappings dim stale/partial data. Hardware units share the sales tile. Diagnostics stay below the wall. No sanitizer override or extra panel plugin. The three old board JSON files are byte-for-byte unchanged against the supplied base; `/dashboard` still embeds the old UID.
- Local verification helper and deployment/source limits documented in `web/admin/grafana/README.md`. Dev fixture/replay modes require non-production mode and the existing explicit development auth bypass; production rejects them.

## Commits

Every commit ends with `Co-Authored-By: Codex Sol <noreply@openai.com>`.

| Commit | Change |
|---|---|
| `de391e9950e98` | Qualified activity v2 and UTC cohort queries |
| `8fd2276f2edd9` | Read-only wall route, sources, fixtures and tests |
| `1c11662100e43` | Isolated Direction A board, build/apply hooks, local verifier and docs |
| `951704aeb4e00` | Shared hardware tile and aggregate-only acceptance guards |
| `963adc5830633` | Unsupported revenue remains null |
| `0eaa42d074136` | Tracked laptop/TV UI evidence |
| `725b23e99dba7` | Upstream freshness propagation; no reader restamping |

A final documentation/evidence commit records this result and the refreshed screenshots.

## Verification layers

Final command results are recorded below after completion. Raw command logs are retained locally as ignored `verification-*.log` files beside this report.

| Command / layer | Result |
|---|---|
| `npm test` in `web/admin` | 392 passed; 2 opt-in live checks skipped (passed separately) |
| `npm run typecheck` | Passed |
| `npm run lint` | Passed: 0 errors, 20 existing warnings |
| `python3 web/admin/grafana/test_build_dashboards.py` | 34 tests passed |
| `python3 web/admin/grafana/build_dashboards.py` + legacy-file diff | Generated v2; no changes to the three legacy boards |
| `OMI_PR_BODY_FILE=<run>/sol-build-v2-pr-draft.md make preflight` | 20 checks passed in 68.72s with the local draft body |
| Opt-in `OMI_TV_LIVE_CHECK=1 npm test -- lib/__tests__/wall-live.test.ts` | 2 live read-only checks passed; active/MAU/cohort/established-retention query shapes and Shopify orders exercised |
| Complete local Next route | HTTP 200 with real PostHog/Shopify/BQ aggregates and explicit synthetic Stripe fixture |
| Local Grafana | Stock 13.1.3, Infinity 4.1.1, native panels visually reviewed at both required widths |

The bare final preflight initially failed its UI-evidence gate because there was no PR body with tracked screenshots. Added canonical screenshot copies and a local draft body; no exemption/bypass was used. No PR exists. The draft is review material only; pin its relative screenshot references to the final evidence commit before publishing a real PR.

Six-period/180-day MAU exceeded PostHog execution time (504); the shipped MAU query uses two complete 30-day periods, verified live. Other usage/cohort trends retain six periods. Live-source failures never become zeros or stale cached successes.

## Recorded aggregate acceptance

These are local read-only aggregates from the 2026-10-15 run, not a production deployment or comparisons to the differently dated evidence snapshot:

| Metric | Recorded value |
|---|---:|
| WAU through Oct 14 UTC | 4,424 (macOS 610 / Mobile 3,814 / Other 0) |
| DAU, Oct 14 UTC | 1,878 |
| MAU through Oct 14 UTC | 9,768 |
| Matured activation proxy | 304 / 1,407 = 21.6063% |
| Retained if activated proxy | 257 / 462 = 55.6277% |
| Hardware, complete Oct 5–11 UTC week | 1,104 devices / $147,953.69 net sales |
| Plan-prepay cash, same week | $41,812.82, separate from MRR |
| D−2 billed GCP component | $2,039.01, partial provider coverage |
| Settled 30-day cost / matching MAU | $4.9074 / person; denominator 9,667; partial cost coverage |

First-seen cohorts remain signup proxies; saved capture/platform provenance, late arrivals, internal roster and client coverage are incomplete. Native query compilation and aggregate arithmetic do not validate these missing emitters/identity joins. The local replay explicitly marks unrecorded upstream freshness unknown, retaining reader evaluation times separately. It never substitutes reader time for a source watermark.

**Stripe was fixture-only locally.** No real Stripe key was used. Synthetic MRR is $39.98 and the synthetic same-cutoff ARPMAU is about $0.0041; neither is a production revenue claim. The screenshots clearly label the fixture. Production ARPMAU stays null until a corrected same-cutoff source is wired. The corrupt historic FinOps aggregate cannot recover dropped products or misbooked JPY from totals alone.

## Screenshots and reproduction

Requested run-folder artifacts (local, ignored):

- `build-screens/omi-tv-v2-1440.png` — 1440×1000 laptop viewport.
- `build-screens/omi-tv-v2-1920.png` — 1920×1080 TV viewport.

Canonical tracked UI-evidence copies and manifest:

- `.agent-artifacts/ui-evidence/omi-tv-v2/001-web-direction-a-laptop.png`
- `.agent-artifacts/ui-evidence/omi-tv-v2/002-web-direction-a-tv.png`
- `.agent-artifacts/ui-evidence/omi-tv-v2/evidence.json`

Screens replay the recorded local live aggregate response and synthetic Stripe leg with original/unknown source freshness retained. They are not production screenshots. Use `verify_wall_local.py serve` for live read-only sources or `serve --replay <aggregate.json>` for the local replay; `provision` installs a fresh isolated local container; `screens` captures both sizes. See the Grafana README for selected ro-prod ADC and managed Docker environment commands.

Local image digest: `grafana/grafana:13.1.3@sha256:ab5cb380e3ff3172d6c8bd2e7cfd31cce977d2881b260e1f5bc089bf0b759b43`. Actual container for this run: `omi-tv-v2-grafana`, loopback port 3207; helper's fresh-run name is `omi-tv-v2-local`. Next used loopback port 3107. No global Docker context was changed. Local task server/container are stopped after capture; the managed shared Colima runtime is left available.

## Deployment prerequisites and open source questions

1. Bind PostHog read credentials/project and the existing admin/Infinity auth proxy to the new route. Source refresh watermarks must come from upstream; missing ones dim rather than assert an hourly SLA.
2. Bind existing `SHOPIFY_STORE` / `SHOPIFY_ACCESS_TOKEN`, or client ID/secret for exchange; the app needs **read_orders**. Approve the canonical device SKU/bundle mapping (`OMI_TV_DEVICE_SKUS` extends it) and FX for non-USD shop currency. The shipped title fallback is an explicit partial proxy; mixed device+plan bundles need an approved allocation.
3. Select a restricted Stripe read key/runtime binding, approve extra enterprise product IDs (`OMI_TV_PLAN_PRODUCT_IDS`), provide approved FX/tiered-price amounts and a corrected historical snapshot at the MAU cutoff. Unknown products/test products are not silently reclassified. Live Stripe can populate an audited live book but cannot invent historical closes, prior MRR or recognized revenue.
4. Billing runtime needs its existing read-only BigQuery job/export access and provider invoice bindings. Complete STT/fee/provider coverage and recognized subscription revenue are prerequisites for gross margin; it remains null. Allocation to platform is unavailable and is not fabricated.
5. Identity owners still need Firebase signup↔PostHog person linkage, full approved staff/test/bot exclusions, saved-state/capture-source joins, late-arrival coverage and verified Windows/web/MCP emitters. No eligibility ruling was changed. Clock-boundary decisions remain as noted by the authoritative contract.
6. Distinct-payer month snapshots/effective lapse history, activated-person paid-start joins, message-rating aggregates and trustworthy macOS crash reporting are missing sources. Those wall metrics remain null with reasons; zero observed crashes never becomes 100% crash-free.

Parent review is still required before publication. CI, merge, deployment and real office-TV acceptance are not claimed.
