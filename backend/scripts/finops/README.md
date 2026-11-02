# Omi finops: daily true user unit cost

One command turns a settled usage day into per-user cost by platform cohort and plan, and
loads it into BigQuery `based-hardware.omi_finops`. It has **no runtime effect**: nothing here
is imported by the backend, and every source is read-only except the BigQuery load.

```bash
# one settled day, loaded
python3 backend/scripts/finops/run_unit_cost.py --date 2026-09-07 --load

# a window (one users snapshot, one GCP query, one ledger pull per date)
python3 backend/scripts/finops/run_unit_cost.py --date 2026-09-07 --backfill-from 2026-09-01 --load

# recompute one date from raw inputs already on disk, without re-pulling
python3 backend/scripts/finops/run_unit_cost.py --date 2026-09-07 --reuse-raw \
    --run-dir /Volumes/scratch/finops-runs/2026-09-01_2026-09-07
```

## What "settled" means

The GCP billing export keeps landing rows for a usage day for roughly 48 hours after it ends.
A usage day is treated as **settled at D-2**, which is what `--date` defaults to. Anything later
is refused unless you pass `--allow-unsettled`, and rows computed that way carry
`inputs_settled = false` in every BigQuery table so a number can never quietly be half a day.
`run_manifest.json` also records `settlement_frontier_export`: the maximum `usage_end_time`
actually present in the export at pull time, which is the empirical version of the same claim.

## Inputs

| Input | Source | Identity | Used for |
|---|---|---|---|
| GCP billing export | `gcp_billing_export_resource_v1_01B287_9348DC_02D256` | read-only bot | every GCP component; the pools |
| LLM gateway ledger | Firestore `llm_gateway_attempts` | read-only bot | measured OpenAI cost per user, Gemini/desktop drivers |
| LLM gateway user-day rollup | Firestore `llm_gateway_user_days` (hashed uid, dual-written at attempt-record time; attempts without a uid are not rolled up, so the `anonymous` bucket comes only from `llm_gateway_attempts`) | read-only bot | will replace the `llm_gateway_attempts` paging in `pull_ledger.py` for attributed users; fields mirror `ledger_user_daily.csv` |
| Users projection | Firestore `users` (field mask) | read-only bot | platform cohort, plan |
| Transcription seconds | Firestore collection group `hourly_usage` | read-only bot | audio-pipeline driver |
| VAD-forwarded audio hours | Prometheus via the Grafana proxy on monitor.omi.me | Grafana token | modelled STT vendor volume |
| OpenAI invoice | OpenAI admin costs API | org admin key | the LLM residual and the reconciliation |
| Anthropic invoice | Anthropic admin cost API | org admin key | same |
| Soniox invoice (optional) | Soniox usage summary | project key | measured company STT total |
| Deepgram invoice (optional) | Deepgram billing breakdown | company project/key | measured company STT total |
| Subscription book | Stripe (read-only key) | Stripe key | `plan_revenue_daily` |
| DAU by platform | PostHog project 302298 | PostHog MCP | alternative denominators only |

The billing export table is partitioned on `_PARTITIONTIME`; every query filters that **and**
`usage_start_time`, and runs with `--maximum_bytes_billed=2147483648`. `net = cost + credits`.
The `..._01B896_918303_539138` table is the predecessor billing account and is never summed in.
Firestore reads bill under service `App Engine`, so Firestore is matched by SKU, never by service.

## Identities

* Every **read** runs as `read-only-bot-account@based-hardware.iam.gserviceaccount.com`, sourced
  from `~/.hermes/scripts/omi-prod-gcp-read-only-env.sh`. The documented `~/.hermes/profiles`
  path does not exist on this host and falls through **silently** to owner credentials, so
  `gcpauth.assert_readonly_identity()` re-checks `gcloud config get-value account` after
  sourcing and refuses to pull under any other account.
* The **BigQuery load** runs as `finops-writer@based-hardware.iam.gserviceaccount.com`
  (dataset `omi_finops` WRITER + project `roles/bigquery.jobUser`) and refuses to run
  under any other account (`gcpauth.assert_writer_identity()`): it verifies the
  key's `client_email` directly (ADC's credential) and activates the key into the
  dedicated `WRITER_GCLOUD` config so `bq` uses the same identity. The read-only bot
  stays read-only. Human ADC is not the cron writer.
* No token, key or secret is ever printed or written to disk.
* **No raw uid ever reaches disk.** Uids are hashed `sha256(uid)[:16]` in flight, and
  `run_unit_cost.validate()` scans the outputs for any hex run of 20+ characters before a load.

## Allocation method

Every dollar lands on a `(day, uid)` row by one of six methods, then rolls up. Component names
are stable: they are the contract with the 2026-09-09 evidence record and with BigQuery.

| method | components | how |
|---|---|---|
| `measured` | `llm_openai_measured` | per-attempt ledger cost joined to the uid |
| `driver-allocated` | `llm_direct_residual`, `vertex_paygo`, `audio_pipeline_gcp`, `desktop_pools`, `shared_activity` | pool × that user's share of a measured driver (OpenAI ledger $, Gemini ledger $, transcription seconds, desktop-feature ledger $) |
| `headcount` | `shared_headcount` | pool ÷ that day's cost-active users. Used for the pools no user measurably causes (Firestore, backend Cloud Run, logging, network, Pub/Sub) |
| `fixed` | `vertex_pt_fixed` | the Vertex provisioned-throughput reservation; excluded from variable cost, present in the fully-loaded view |
| `modelled` | `stt_vendor_low`, `stt_vendor_high`, `llm_gemini_list_memo`, `gross_total` | no invoice feed exists |
| `one_time` | `one_time_*` | dated one-off charges. Reported at the day level only, **never** allocated to a user, never in a run rate |

Aggregates (`variable_total`, `variable_total_activity`, `fully_loaded`) carry the weakest method
they contain, so `gross_total` is `modelled` because it includes the modelled STT vendor line.

"Cost-active user" = at least one ledger row or one transcription-usage row that day. Platform
cohort is `dual` / `desktop_only` / `mobile_only` / `web_only` / `inactive_7d` from the users
snapshot's `last_active_at_*`; **dual users are their own segment and are never split**. The
`platform_union` segment type counts a dual user in *both* `desktop_incl_dual` and
`mobile_incl_dual`, so those two segments deliberately overlap and must not be added together.

### `one_time`: what it is for

`one_time_events.json` is a dated registry of one-off charges. Each entry is injected as the
first branch of the component CASE by `pull_gcp.py`, so a matching row gets its own component,
is reported with `method='one_time'` at `segment_type='total'`, and is excluded from every pool.
The registered example is the Coldline@30d lifecycle transition of the audio bucket (PR #12631):
**$13,818.35 on 2026-09-07** on `omi-private-cloud-sync` plus $103.86 on 2026-09-05 on the dev
bucket — 345M Class A operations in one sweep. Without the rule that single day would put
roughly **+$6.50 on every cost-active user's day**, an eleven-fold overstatement of run rate.
Add a rule only with a date bound, a resource or SKU scope, a reason and an owner. Never widen a
rule to a whole SKU with no date bound: that would hide a real, recurring regression.

### Cohort window

A cohort needs a date from which a snapshot `last_active_at_*` counts as "active on that platform".
By default that is a **trailing 7-day window ending on the usage day** (`--cohort-lookback-days`),
evaluated per date. That matters: it makes a date's cohorts identical whether the date is computed
alone by the daily cron or inside a backfill, so the series does not shift under you. Pass
`--cohort-window-start` to pin one explicit date instead, which is what reproducing an older report
needs.

`users.last_active_at_*` are **overwritten in place**, so the snapshot is not replayable:
`_users_snapshot.json` records `snapshot_at` and the run manifest carries it into BigQuery via
`run_id`. A rerun of an old date with a fresher snapshot will produce slightly different cohorts,
and that is a property of the source, not a bug. Plan is unaffected either way.

## Outputs

`derived/` holds `unit_cost_long.csv` (what BigQuery gets), `unit_cost_reconciliation.csv`,
`user_day_allocated.csv`, the five `unit_cost_by_*.csv` roll-ups, `platform_alt_denominators.csv`
and `day_summary.json`. `assembly_output.md` is the human report.

BigQuery `based-hardware.omi_finops` (location US, same as the billing export, so the two join):

| table | grain | notes |
|---|---|---|
| `unit_cost_daily` | date × segment_type × segment × component × method | `segment_type ∈ {cohort, plan, cohort_plan, platform_union, total}` |
| `unit_cost_reconciliation` | date × pool | `pool_usd` vs `allocated_usd` vs `delta_pct` |
| `plan_revenue_daily` | date × plan | Stripe **snapshot**; carries `snapshot_date` because Stripe is not replayable per historical day |
| `unit_cost_user_day` | date × `uid_hash` | hashed uids only (`sha256[:16]`) |
| `mercury_vendor_spend_daily`, `mercury_saas_daily`, `mercury_infra_non_gcp_daily` | date × vendor / date | Mercury aggregates (`load_mercury`; dark while Mercury is off) |
| `stripe_fee_daily` | date | measured Stripe processing fees (dark while the fee scope is missing) |
| `vendor_balance_snapshot` | ts × vendor | Soniox prepaid-balance snapshots (dark while the org key is off) |
| `vendor_balance_spend_daily` | date × vendor | daily spend derived from consecutive snapshots (gap/reset flagged) |
| `stt_modulate_modelled_daily` | date | modelled Modulate STT cost: Prometheus seconds × committed rate-card price |

All four are partitioned by `date` and clustered. Loads are **idempotent per date**: the run's
dates are deleted and re-inserted inside one BigQuery transaction, so re-running a date replaces
it rather than doubling it. A column added to a loader's `SCHEMAS` is added to the live table
automatically (nullable, before the load); any other schema change needs a migration.

## Validation

`run_unit_cost.py` refuses to load unless:

1. every variable pool reconciles within `--recon-tolerance-pct` (default **0.5%**) — including
   `gcp_total_export`, which is the check that the component classifier loses nothing;
2. every requested date produced allocated rows;
3. no output contains a hex run long enough to be a raw uid.

`llm_openai_ledger_coverage` is a **diagnostic** row, not an allocation check: it reports how much
of the OpenAI invoice the per-attempt ledger explains (the rest becomes `llm_direct_residual`).
It is excluded from the tolerance gate on purpose.

## Cost of a run

Measured on the 2026-09-01..09-07 backfill:

| item | cost |
|---|---|
| BigQuery billing-export queries | 0.35 GiB billed ≈ **$0.002** per window (4 queries; the last three hit cache on a rerun) |
| Gateway ledger pull | ~560k document reads/day ≈ **$0.27/day** (field-masked, paged, ~90–140 s/day) |
| Users snapshot (17.2k users, 4 ordered passes) | ≈ **$0.02** |
| `hourly_usage` collection-group scan | 85k documents for a 7-day window in one month ≈ **$0.04** |
| Prometheus, PostHog, OpenAI, Anthropic, Stripe | free |
| BigQuery storage + load DML | < 10 MB, negligible |

**A daily run costs about $0.30**, dominated by the ledger read. A 7-day backfill costs about $2
and takes ~20 minutes, almost all of it the ledger.

## Backfilling

```bash
python3 backend/scripts/finops/run_unit_cost.py \
    --backfill-from 2026-09-01 --date 2026-09-07 --load
```

Do **not** backfill before **2026-09-01**: desktop ledger attribution rolled out on 09-01, so
2026-08-31 has no desktop ledger rows and its plan/cohort split is not comparable.

The window is assembled as one run so it shares a single users snapshot; the per-`(day, uid)`
allocation itself is day-local, so a date computed inside a window and the same date computed
alone are identical for the same inputs and the same `--cohort-window-start`.

## Accuracy against the 2026-09-09 evidence record

Replaying the record's own raw pulls through this code
(`assemble_unit_cost.py <raw> <out> 2026-09-01 2026-09-06 2026-08-31`) reproduces
`derived6/unit_cost_by_{plan,cohort,cohort_plan,platform_union}.csv` and
`platform_alt_denominators.csv` with **zero value differences** on every shared column.

Two deliberate differences from the code that produced the record:

1. **A new column `shared_activity_per_day`** appears in the roll-up CSVs. `shared_activity` was
   always computed per user-day and always fed `variable_total_activity`; it simply had no column
   of its own. No existing value changed.
2. **`byok_active` parsing.** The old code compared the CSV value to `"True"` while the puller
   writes `"true"`, so `byok` was always `False`. It is now compared case-insensitively. The field
   is not used by any allocation, so no number moved.

Re-pulling the same window today gives slightly different figures, for reasons that are data,
not code. Assembling **today's** pulls over 2026-09-01..09-06 against the record:

| metric | record | re-pulled | Δ |
|---|---:|---:|---:|
| variable $/day, five plans | 1,846.77 | 1,829.62 | −17.15/day |
| audio pipeline $/day, five plans | 406.02 | 388.79 | −17.23/day |
| `basic` variable $/user-day | 0.6503 | 0.6470 | −0.51% |
| `unlimited_v2` variable $/user-day | 1.2600 | 1.2409 | −1.52% |
| mean users/day, `basic` | 1,169.5 | 1,169.7 | +0.02% |

−17.23/day × 6 days = **−$103.4**, which is the dev bucket's $103.86 Coldline transition on
2026-09-05 that `one_time_storage_lifecycle` now lifts out of `storage_audio`. The residue
(≈ $1 over six days, and the 0.02% user-count drift) is the users snapshot being three hours
fresher and the billing export continuing to settle. No allocation logic changed.

## Files

| file | role |
|---|---|
| `run_unit_cost.py` | the entrypoint: pull → assemble → validate → load |
| `assemble_unit_cost.py` | the allocator. Pure functions are unit tested in `backend/tests/unit/test_finops_unit_cost.py` |
| `load_bigquery.py` | dataset/table creation and idempotent per-date loads |
| `gcpauth.py` | the two identities, verified by name before use |
| `pull_gcp.py` + `gcp_component_classifier.sql` + `one_time_events.json` | billing export → components |
| `pull_ledger.py` | `llm_gateway_attempts` → per-uid and per-group daily aggregates |
| `pull_users.py` | users projection snapshot |
| `pull_hourly_usage.py` | transcription seconds per uid-day |
| `pull_prometheus.py` | VAD-forwarded audio hours |
| `pull_providers.py` + `pull_stt_costs.py` | OpenAI/Anthropic invoices and optional measured STT totals |
| `pull_stripe.py` | subscription book → MRR/ARPU by plan |
| `posthog_dau.py` | DAU by platform (denominators only) |
| `fs.py` | dependency-free Firestore REST client |

## Known gaps

* **Per-user STT vendor cost remains modelled.** `stt_vendor_low` uses a $0.0043/min
  placeholder and `stt_vendor_high` is ×1.8. Optional measured Soniox/Deepgram company
  totals are separate lines (see below); Modulate has no measured feed here.
* **SaaS with no feed** (PostHog, Sentry, Redis Cloud, ~$500–700/mo) is in no pool at all.
* **Half of variable cost is shared overhead** split by headcount because no per-uid request or
  Firestore-read counter exists. `shared_activity` is the alternative, not a better truth.
* **The ledger's `app_platform` header is written only by `desktop_proactivity`**, so request-level
  platform is unavailable; platform comes from the users cohort join.
* **Stripe is a snapshot**, not history. `plan_revenue_daily.snapshot_date` says so on every row.

## Measured STT invoices (optional, company totals)

`pull_providers.py` also pulls Soniox `GET /v1/usage/summary` using whole UTC days,
with a midnight-exclusive end. It sums `cost_usd` for `stt-*` models, including
input/output and API/playground cost once. The summary has no pagination; windows
larger than 366 days are split without overlap. No per-request identifiers reach disk.
API contract: <https://soniox.com/docs/api-reference/other/get_usage_summary>.
The hermetic JSON fixtures in `backend/tests/unit/fixtures/finops/` are reduced
published response examples, not live account captures.

`raw/stt_vendor_cost_daily.json` records daily decimal USD amounts and skipped
providers. It is overwritten on every pull, so a missing key cannot reuse an older
invoice from the same run directory. Missing/unreadable/empty secrets (including a
non-UTF-8 mount) and usage API 401/403 responses warn and skip only that provider;
they do not publish zero cost. Other API/shape failures fail the pull to avoid
publishing a false invoice.

Deepgram measured dollars are streaming/sync `nova`, `base`, `enhanced`, and
`whisper` only. Any other positive line item on that UTC day is `unclassified`.
The day is stored under `incomplete` with `usd` (known STT) and `unclassified_usd`,
and that provider is omitted from `providers`, so it is not published as
`method=measured`. TTS such as `aura` stays out of the STT total; a new or unknown
positive line item must not disappear inside a measured row. A published measured
row does not claim `delta_pct`: the dollars are the accepted invoice, and there
is no separate allocation to compare. Incomplete days are omitted, so they do
not publish a zero delta either.

The existing assembler and `load_bigquery.py` publish the measured lines to:

- `based-hardware.omi_finops.unit_cost_daily`: `date`, `usd`,
  `segment_type='total'`, `segment='all'`, `method='measured'`,
  `component='stt_soniox_measured'` (and `stt_deepgram_measured` when configured).
- `based-hardware.omi_finops.unit_cost_reconciliation`: matching `pool`,
  `pool_usd`, `allocated_usd`, `invoice_source='<provider>_usage_api'`.
  Here `allocated_usd` means published company total, not user allocation.

These are company-only rows (`users=0`, `usd_per_user_day=NULL`). They do not change
plan/user allocation or the existing modelled `gross_total`. A TV reader must use
these measured components instead of its hand-entered STT constant; do not add them
to `gross_total` or `stt_vendor_low/high` (which already model vendor STT).
Absence means unknown/unavailable; an explicit zero means a successful zero-cost
summary. The loader replaces each requested date in its existing transaction:
latest completed load wins, never appends the same invoice twice. A later skipped
pull removes that date's measured line along with the normal date replacement.

Soniox `client_reference_id` can support a later per-user/plan join via usage logs,
but the current `utils/stt/soniox.py` config does not set it. Adding identity tagging
and a historical plan join is outside this company-total pull.

### Secret wiring and dark deployment

Backend ExternalSecret values map `SONIOX_API_KEY` to Secret Manager
`projects/based-hardware/secrets/SONIOX_API_KEY` (same name for Deepgram).
`cloudrun.secret('soniox')` resolves either
`$FINOPS_SECRETS_DIR/SONIOX_API_KEY` or
`$FINOPS_SECRETS_DIR/SONIOX_API_KEY/SONIOX_API_KEY` (default directory
`/run/secrets/finops`). It performs no Secret Manager API lookup. Local pulls use
explicit `SONIOX_API_KEY` / `DEEPGRAM_API_KEY` environment variables only.

The job runs as `finops-writer@based-hardware.iam.gserviceaccount.com`. Its existing
deploy workflow does not mount either STT key. This change intentionally leaves
that workflow untouched; the orchestrator must add the mount after IAM is ready:

```text
/run/secrets/finops/SONIOX_API_KEY/SONIOX_API_KEY=SONIOX_API_KEY:latest
```

On 2026-10-17, `ro-prod` could read the job definition and project IAM policy, but
`gcloud secrets get-iam-policy SONIOX_API_KEY --project=based-hardware` was denied
`secretmanager.secrets.getIamPolicy`. Project-level grants for the job SA were
BigQuery jobUser and Datastore viewer; secret-level access remains **unverified**.
David can inspect the secret policy, and if no accessor grant exists, run:

```bash
gcloud secrets add-iam-policy-binding SONIOX_API_KEY --project=based-hardware --member=serviceAccount:finops-writer@based-hardware.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor
```

No secret payload, IAM mutation or deployment is required to land this code.
Do not add an inaccessible Cloud Run secret binding before granting access: Cloud
Run may reject startup before the Python missing-secret skip can run.

### Deepgram scope

The runtime routing manifest currently prefers Parakeet/Modulate/Soniox and omits
Deepgram from deployed model lists; policy still permits cloud Deepgram streaming,
and `streaming._deepgram_client_for_request()` can use the company key as well as
BYOK. Therefore source inspection alone cannot establish zero company spend.
A dark Deepgram billing pull is included rather than treating it as zero. It
requires both the optional mounted `DEEPGRAM_API_KEY` and an explicitly verified
company `FINOPS_DEEPGRAM_PROJECT_ID` (no project discovery, no BYOK account reads).
It pulls hosted `billing/breakdown` through the following date, selects each exact
UTC daily bucket, and sums STT line items
(Nova/base/enhanced/Whisper, streaming or sync); Aura TTS is excluded. The key also
needs vendor-side billing-read permission; otherwise 401/403 skips it.
API contract: <https://developers.deepgram.com/reference/manage/billing/breakdown/get>.
Mount, IAM and project configuration belong to the orchestrator. No current
Deepgram dollar amount was read in this task because secret payloads are excluded.

### Backfill after access and mount are ready

Run inside the deployed producer image under its existing writer/runtime identity,
not under `ro-prod` (which cannot load BigQuery):

```bash
FINOPS_AUTH=cloudrun python /app/monorepo/backend/scripts/finops/run_unit_cost.py \
  --backfill-from 2026-10-01 --date 2026-10-17 --allow-unsettled --load
```

The normal job's date-range flags are inclusive. `--allow-unsettled` is needed for
Oct 16–17; those rows carry `inputs_settled=false` and must be rerun at D-2. For
settled history only on Oct 17 use `--date 2026-10-15` and omit that flag. The normal
Cloud Run entrypoint handles single-date runs via `FINOPS_DATE`; the range command
above must be invoked as the job's Python command, not passed as arguments to
`cloudrun_entry.py`. The orchestrator owns execution and deployment.

Cross-check measured totals against the canonical KB console receipt dated
2026-10-15: September $10,315.16; Oct 1–13 $2,657.96; Oct 13 UTC $143.00. These are
comparison targets, not fixtures or substituted invoice data. No cross-check has
been executed before access and backfill.

## Mercury vendor spend (dark, Read Only)

`pull_mercury.py` adds company bank-spend reconciliation without adding bank payments
to the existing GCP/STT/LLM cost pools. It is **default off**:
`FINOPS_MERCURY_ENABLED=true` and a mounted Mercury **Read Only** token are both
required. David creates the token and stores it as Secret Manager
`finops-mercury-readonly`. `cloudrun.secret('mercury')` reads a flat file or the
usual nested mount at:

```text
/run/secrets/finops/finops-mercury-readonly/finops-mercury-readonly=finops-mercury-readonly:latest
```

Local execution accepts explicit `FINOPS_MERCURY_READONLY_TOKEN` only. Disabled,
missing/empty/unreadable (including non-UTF-8) secrets and Mercury 401/403 responses warn and skip the
Mercury line without failing other pulls; no Mercury table is read or written on
a skip. Other API/shape errors fail the run. A previous ready file cannot be
reused after a skipped/failed pull. Successful-child warnings reach Cloud Logging.

[Mercury's current token policy](https://docs.mercury.com/docs/api-token-security-policies)
says **Read Only tokens do not require an IP whitelist**. No static-egress/NAT
change is required or included. Do not use a Read and Write token. If a future
token policy requires an allowlist, the orchestrator would need a stable public
egress IP (for example Cloud Run VPC egress routed through Cloud NAT with a reserved
address) and whitelist that address before activation. That infrastructure is not
part of this pull. Tokens unused for 45 days may be deleted by Mercury.

The runtime SA is still `finops-writer@based-hardware.iam.gserviceaccount.com`.
`ro-prod` cannot read this secret's IAM policy (`getIamPolicy` denied on 2026-10-17),
so secret-level access is unverified. After David creates the secret, if needed:

```bash
gcloud secrets add-iam-policy-binding finops-mercury-readonly --project=based-hardware --member=serviceAccount:finops-writer@based-hardware.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor
```

No payload was read and no IAM, mount, flag or deploy change was applied here.

### Projection and classification

The all-accounts [transactions endpoint](https://docs.mercury.com/reference/listtransactions)
is GET-only. Each daily run refreshes the **90 posted UTC dates ending at the job's
`--date`** (normally D-2). Requests use `postedStart/postedEnd`, not the API's
created-date `start/end`. The projection accepts only `status='sent'`, non-null
`postedAt`, and negative account-USD amounts. It buckets the timezone-aware posted
timestamp into UTC and applies the half-open end locally. It never uses foreign
merchant minor-unit amounts or the credit-statement endpoint's different signs.
Pagination uses the last actual transaction ID as `start_after` (exclusive),
matching the [official Go SDK](https://github.com/MercuryTechnologies/mercury-go/blob/166dc7d99d3f5fc59672f60deaf910f23ca62860/packages/pagination/pagination.go#L43-L54),
dedupes IDs in memory, and fails on a non-advancing cursor. It does not infer a
request cursor from the potentially different `page.nextPage` value.

Raw responses never reach files, BigQuery or logs. The normalized artifact stores
only date, checked-in canonical vendor, category, USD amount and aggregate count,
plus window/status metadata. No account/card numbers or IDs, person names, memo,
note, attachment or raw counterparty strings are persisted. Redirects are refused
and HTTP/shape failures use bounded messages. Fixtures are synthetic API-shape
examples containing privacy canaries; no bank API was called to record them.

`mercury_vendor_map.json` schema v2 uses normalized token-boundary aliases, with
the longest matching alias winning, followed by `mercuryCategory` rules and then
`categoryData.name` rules, and finally `uncategorized_kind_rules` by transaction
kind: an unlabelled `outgoingPayment` (wire/ACH) is `other_opex` under the
synthetic vendor `uncategorized_payment`, because those are suppliers and
contractors (Sept–Oct 2026 had $4K–$67K wires every few weeks that would
otherwise block the line). A SaaS paid by wire/ACH must therefore have a vendor
alias or a Mercury category. Excluded kinds/categories always win. The map keeps
schema v1 readable with no category rules and the default `$2,500` uncategorized
threshold. It seeds explicit known vendor aliases and generic category rules;
rule-classified aggregates use the synthetic vendor labels `mercury_category`
and `category_data`, never raw counterparty names. Google Workspace has a separate
alias from Google Cloud, while `Google Payment Corp` maps to GCP; ambiguous
`Google` remains uncategorized. Yearly cadence is **detected from charge
history** (`detect_annual_charges`), never inferred from a merchant name: a
charge is an annual bill when it repeats about every 12 months (gap 304–426 days
to its neighbour), when it is ≥5× that vendor's other-charge median, or — for a
vendor seen exactly once — as an ambiguous one-off amortized ÷12 and reported as
`estimated`. `annual: true` in the map is only a manual correction that forces
the annual treatment (SaaS vendors only); `annual: false` means auto-detect, the
default. Ledger evidence 2026-07-04..2026-10-19 (read 2026-10-22,
`mercury_vendor_spend_daily`): shopify, posthog, nevercode and pinecone all
bill monthly (same-day-of-month repeats), so the "single annual payment"
reading of the 2026-10-22 wall audit was wrong — detection classifies that
pattern monthly, which is why the committed map carries no `annual: true`
override. A 2026-10-23 read-only 13-month Mercury check found real once-a-year
postings outside the ledger window (for example a $12,000 wire on 2026-01-08 to
`Modal Group, Inc.`, plus once-each software bills); that evidence drives the
completeness gate below, not the cadence of any named vendor.

| Category | Treatment |
| --- | --- |
| `saas` | Non-GCP software subscriptions; drives the TV SaaS line |
| `stt_vendor`, `llm_vendor` | Cash cross-check against provider invoices; never add to usage costs. Anthropic maps to `saas` since 2026-10-22: its Mercury cash is Claude team seats, not per-customer API spend |
| `infra_non_gcp` | Non-GCP infrastructure/platform cash spend (Modal, AWS, Runpod, …), including outgoing Stripe fees; drives the TV "Infra (non-GCP)" line. The run-rate table's `amount_usd` excludes the `stripe_fees` vendor (that cash is measured on the `stripe_fee_daily` line; the two must never stack) but carries its own run rate in `stripe_fees_usd`, so the TV can count it on the infra line only on a day the measured fee line is unavailable — never on both lines, never on neither |
| `gcp` | Excluded from TV addition; already covered by GCP billing |
| `marketing`, `fulfillment`, `hardware_cogs`, `travel_meals`, `professional_services`, `facilities`, `other_opex` | Reconciliation categories only; never included in the SaaS line |
| `excluded` | Payroll, internal/treasury transfers, card repayments, expense reimbursements, taxes, refunds/credits and explicitly excluded hardware categories; collapsed to vendor `excluded` |
| `unmapped` | Uncategorized outgoing spend, one total and count per UTC date, no counterparty detail |

Category rules reconcile common advertising, shipping, travel, meal, hardware,
professional-service and office spend without claiming those expenses are SaaS.
`Software` / `Software & Subscriptions` / `Software Costs` map to `saas` after
vendor aliases and Mercury categories have been checked. Thus an Advertising
transaction remains marketing even if its accounting category says Software &
Subscriptions. Vendor aliases remain the most specific source: `Google Payment
Corp` stays GCP and Shopify stays SaaS even when the category fields disagree.
Aliases added from the 2026-10-23 read-only 13-month check (company vendors
only, never person names): `modal group` (Modal's compute wire →
`infra_non_gcp`, not SaaS), `www deepgram com` (annual-scale STT cash wire →
`stt_vendor`), and named SaaS entries for the Software-category posters seen
once in 12 months (`vanta`, `mintlify`) plus monthly `greptile`, so cadence
detection reads each vendor's own series instead of the blended
`mercury_category` aggregate.

Incoming credits/refunds are outside this outgoing-spend feed and are not netted
against bills. External ACH/wire transfers are **not** blanket-excluded: they may
be vendor payments. Transactions without an alias or recognized category remain
uncategorized. Generic `Stripe`/`Stripe Inc` descriptors
also remain unmapped; only explicit `Stripe Fee`/`Stripe Fees` aliases classify
as outgoing fees. Stripe fees withheld from
incoming payouts cannot be measured as outgoing transactions here; do not invent
them from net deposits. The initial alias map needs human review against Mercury's
own dashboard; extend it there, never by logging unknown counterparties. Mixed
monthly/annual bills for one canonical vendor need separate verified aliases.

### BigQuery and TV contract

The existing `load_bigquery.py` path loads three date-partitioned aggregate tables:

- `based-hardware.omi_finops.mercury_vendor_spend_daily`: `date`, `vendor`, `category`,
  `amount_usd` (NUMERIC, positive outgoing spend), `transaction_count`, `run_id`, `computed_at`.
- `based-hardware.omi_finops.mercury_saas_daily`: `date`, `vendor='all'`, `category='saas'`,
  **`amount_usd`** (daily TV line), `annual_monthly_usd`, `annual_estimated_usd`
  (the ÷12 portion from ambiguous one-off vendors), `unmapped_usd`, `unmapped_count`,
  `coverage_days`, `annual_history_complete`, `annual_history_reason`,
  `inputs_complete`, `run_id`, `computed_at`.
- `based-hardware.omi_finops.mercury_infra_non_gcp_daily`: the SaaS run-rate
  schema plus a `stripe_fees_usd` column, at `category='infra_non_gcp'` — the
  same run-rate treatment as SaaS over non-GCP infrastructure cash (Modal, AWS,
  Runpod, …), feeding the TV "Infra (non-GCP)" cost line. The `stripe_fees`
  vendor is kept out of `amount_usd` (measured on `stripe_fee_daily` instead)
  and reported separately in `stripe_fees_usd`, which the TV counts on the
  infra line only on a day the measured fee line is unavailable. The table is
  created whole from `SCHEMAS` on its first load (every produced field has a
  column, pinned by test) and stays dark until then, so the wall shows an
  unavailable line, never a guess. Reconciling an OLDER live table against the
  current schema is #23354's job, not this loader's.

Every successful refresh replaces **all 90 dates**, including zero-spend dates,
through the existing per-table delete/insert transaction. The daily unmapped row
exists even when zero and proves a successfully fetched date. Older aggregates
are retained, not appended/reinserted into the refreshed range. A bounded 100 MiB
BigQuery history read retrieves only older aggregates for annual amortization.
Late corrections older than 90 days require an explicit backfill.

TV `amount_usd` = `(non-annual SaaS paid over [date-29,date] + active annual bills/12) / 30.4375`.
Annual bills remain active from posted day through the day before their 12-month
anniversary (Feb 29 clamps to Feb 28); a bill is annual by detected cadence
(yearly repeat, ≥5× the vendor's monthly-median outlier, ambiguous one-off, or a
manual `annual: true` override), and one-off amortization is broken out in
`annual_estimated_usd` so the `estimated` label is visible in the data. Known
annual aggregates continue contributing after they age out of the 90-day API
refresh. NUMERIC outputs round to nine decimal places. SaaS never includes GCP,
LLM, STT, other infrastructure or excluded spend.

`inputs_complete` requires all 30 posted days and no more than
`max_uncategorized_usd` of uncategorized spend in the rolling 30-day window
(2026-10-22: the cash-window gate; see below for the separate annual-history
signal). The map defaults that threshold
to `$2,500`. The existing BigQuery fields `unmapped_usd` and `unmapped_count`
retain their names for loader/admin compatibility; they now mean uncategorized
USD and transaction count. Unlabelled wires/ACH are `other_opex`, so the
residual is mostly unlabelled card spend; anything above the threshold (for
example a kind with no rule) blocks completeness while it remains in the 30-day
window, then ages out; it is never added to SaaS. Add a category or vendor map rule when its nature is known.
`annual_history_complete` is its own signal and now requires a full preceding
365 covered days **regardless of configured annual vendors** — an empty
override map no longer implies complete (2026-10-23, Luna r3 finding 4: the
2026-07-04 ledger start is ~109 days and cannot rule out yearly bills; the
13-month read-only check confirmed such charges exist outside the window).
Annual uncategorized spend above the same threshold also blocks it. While
incomplete, `annual_history_reason` names the gate — `history_under_12_months`
or `uncategorized_above_threshold` — and the value still amortizes every annual
bill and one-off the seeded history contains.
The reader should require `inputs_complete=true` and fresh `computed_at` (for
example within 3 days), prefer this USD value over `SAAS_MONTHLY_USD/30.4375`,
and use the dated `SAAS_AS_OF` estimate only when no complete fresh row exists.
Treat `annual_history_complete=false` as a disclosed partial labelled with its
reason, not as an unavailable line: the wall shows the amortized value and
appends the partial note.
Preserve an explicit measured zero. The admin wall reads this table through
`wall-finops.ts` (`saasMeasured` + `saasAnnualPartial`), which is in place.

The infra run rate keeps the SaaS read gates but not the SaaS display rule:
while `annual_history_complete=false` the run rate is a **floor**, not a
measurement — the cadence treatment amortizes only charges the ledger holds,
so an annual bill posted before the ledger starts (the 2026-01-08 Modal wire)
contributes nothing, and a first-seen charge is an ambiguous one-off ÷12. The
wall shows max(measured, dated `INFRA_MONTHLY_USD` fallback), still labelled
partial with the producer's reason, so a fresh-but-short row never drops the
known Modal bill from the all-in total; once the history is complete the
measured value stands alone. `stripe_fees_usd` is counted on the infra line
only on a day the measured fee line is unavailable, so those fees are never on
both lines and never on neither.

Bank posting dates and prepayments differ from provider usage days. Reconcile
`mercury_vendor_spend_daily` by vendor/month against every non-GCP invoice and the
unmapped total, allowing timing, credits and prepaid-balance differences; do not
replace daily usage invoices with same-day bank debits or sum both.

To seed complete annual history, run the deployed producer once with a widened
window. `pull_mercury.py` reads `FINOPS_MERCURY_BACKFILL_DAYS` (91..400) from
the environment because the Cloud Run job invokes it with fixed arguments; the
env var widens that one run's Mercury pull to N posted days ending at the run's
D-2 date. The one-time deploy step for the lead:

```bash
# 1. Add the var to the deployed job. The workflow deploys the job with a fixed
#    env list, so --set-env-vars must repeat all of it (project: based-hardware).
gcloud run jobs update finops-unit-cost-job --region us-central1 \
  --set-env-vars=FINOPS_LOCK_BUCKET=based-hardware-finops-runs,FINOPS_AUTH=cloudrun,FINOPS_WRITER_SA=finops-writer@based-hardware.iam.gserviceaccount.com,FINOPS_MERCURY_ENABLED=true,FINOPS_MERCURY_BACKFILL_DAYS=400
# 2. Execute once (gap-fill loads the frontier date; Mercury pulls 400 days).
gcloud run jobs execute finops-unit-cost-job --region us-central1 --wait
# 3. Remove the var: re-run step 1 without FINOPS_MERCURY_BACKFILL_DAYS, or
#    redeploy the job from the workflow, which resets the env list.
```

The backfill is idempotent on (date, vendor): the aggregate artifact is keyed
(date, vendor, category) — duplicate keys are rejected — and the loader's
per-date delete/insert transaction replaces exactly the window's dates, never
appending, so re-running the backfill re-derives the same rows. A 400-day window
covers 13 months, after which `annual_history_complete` can turn true for
current dates (subject to the uncategorized year-window gate).

The manual in-image path stays available for an explicit window, pulling into
an existing complete FinOps run's raw directory, then invoking the existing
loader:

```bash
# Inside the producer image, writer runtime identity, access/mount/flag already ready.
python /app/monorepo/backend/scripts/finops/pull_mercury.py --end 2026-10-15 --backfill-from 2025-09-11 --raw /tmp/finops-runs/history/raw
# Use load_bigquery.py with that run's normal --derived/--raw/--run-id arguments.
```

The raw directory must belong to a fully assembled FinOps run; do not invoke the
normal loader with only Mercury inputs. No backfill, database write or deployment
was run as part of this implementation.

## Subscription book rules (2026-10-22, round 3)

The same `pull_stripe.py` run writes the book first (`raw/stripe_plan_mrr.json`):

* **Currency scale follows the price**: zero-decimal currencies (JPY, KRW, VND,
  … — <https://docs.stripe.com/currencies#zero-decimal>) are NOT divided by 100;
  three-decimal currencies (BHD, JOD, KWD, OMR) divide by 1000. A JPY ¥1,200
  price is 1,200 major units, never "$12".
* **`mrr_usd` is USD only.** A non-USD price is never booked as dollars (no
  implicit FX): its customer still counts as paying, its native monthly amount
  is reported per currency (`non_usd_mrr_native` in the artifact), and
  `non_usd_paying_subs` lets the wall label the figure partial.
* **Customers, not items.** `paying_subs` counts a customer once per plan,
  never per subscription item; `paying_customers` (new nullable
  `plan_revenue_daily` column, added to a live table automatically by the
  loader's schema reconcile) is the book-wide distinct customer
  count repeated on every plan row — the wall takes MAX per snapshot day, not
  the plan-row sum, and falls back to the sum (labelled item-based) on rows
  written before the column existed. Old artifacts load with NULL.

## Measured Stripe processing fees

`pull_stripe.py --end <date>` refreshes the trailing 90 posted UTC days of
balance transactions into `raw/stripe_fee_daily.json`: per day the signed `fee`
sum across **all** transaction types, gross `charge`/`payment` volume, the row
count, and how many rows were non-USD (counted, never summed — no implicit FX).
Fee semantics follow the documented contract
(<https://docs.stripe.com/api/balance_transactions/object>): `fee` is
"Represented as a positive integer when assessed", the funds direction lives in
`amount`, and a refund hands the previously assessed fee back as negative
`fee_details` entries (type `stripe_fee`) matching a negative `fee` — so summing
the API's signed `fee` nets refunds on the refund's own day. When `fee_details`
is present it is authoritative: a breakdown that does not sum to `fee` is a
shape failure, never a guessed number. A charge converted into the account's
USD balance already arrives as a `usd` row (`exchange_rate` set, per the docs'
EUR example), so the non-USD count covers only balances held in other
currencies; the wall labels the fee line partial while that count is non-zero.
Only aggregates are persisted; no transaction or customer ids.
The loader writes `omi_finops.stripe_fee_daily` (date-partitioned, idempotent
per date, replaced with each refresh) and is **dark while the fee source is
unavailable**: a restricted Stripe key without balance-transaction read scope
gets 401/403, the artifact is written with `status=skipped` and the exact
grant needed (Read on the "Balance" category, `GET /v1/balance_transactions`),
no table is created or read, and the daily job is unaffected. Transport or
shape failures also skip (`reason=error`) rather than publish a guessed number
or lose the subscription book, which is written first.

The TV reads it through `wall-finops.ts` (`fetchStripeFeeHistory`, carrying
`foreign_transaction_count` so the wall can label coverage), kept
outside the plan-cost query so a dark fee table can never fail the plan/STT/SaaS
legs; the wall shows the fee line as unavailable with the missing scope until
the first successful pull creates the table.

## Vendor balance snapshots: the measured Soniox day-rate (2026-10-22)

The Soniox **organization** key (`FINOPS_SONIOX_ORG_KEY`) has no usage, invoice
or billing API — every such path returns 404. The one readable endpoint is
`GET https://api.soniox.com/v1/organization/balance` (`Authorization: Bearer`),
which returns `used_balance_usd` (cumulative, a string), `available_balance_usd`
and `invoice_billing_enabled`. `pull_vendor_balance.py` snapshots those parsed
numbers once per daily run into `raw/vendor_balance_snapshot.json`; the pull
logs and artifact carry parsed numbers only — never the key and never the raw
response body.

The loader writes two dark-able tables:

- `omi_finops.vendor_balance_snapshot` — one row per successful pull
  (`date`, `ts`, `vendor`, `used_usd`, `available_usd`,
  `invoice_billing_enabled`), idempotent per (date, vendor).
- `omi_finops.vendor_balance_spend_daily` — the **derived day rate**: each
  interval between consecutive snapshots belongs to the UTC days strictly
  after the previous snapshot's day through the current snapshot's day
  (daily runs ⇒ exactly the snapshot's own day). A run gap spreads the delta
  evenly over the missed days and flags them `gap_spread` (an assumption, not
  a measurement). A lower `used` value is a recharge/reset: that day is
  unmeasured (`usd` NULL, flag `baseline_reset`) and the new value becomes
  the next interval's baseline. The whole trailing window is recomputed from
  the snapshot table on every run, so the spread/reset rules can change
  without backfilling.

Optional by design: a missing key, a 401/403, or a transport/shape failure
writes `status=skipped` with a reason and never fails the daily job. The TV
(`fetchVendorBalanceHistory`) shows Soniox as **measured** with its as-of
date only once **≥2 snapshots** exist; before that the labelled, dated
console constant (read 2026-10-16, STALE after 14 days) stays as the
fallback, and a dark table is an explicit unavailable line, never a guess.

Secret wiring: `cloudrun.secret('soniox_org')` resolves the
`FINOPS_SONIOX_ORG_KEY` file mount (added to the deploy workflow's
`--set-secrets` on 2026-10-22; the secret is readable by
`finops-writer@based-hardware.iam.gserviceaccount.com`). Local runs use the
`FINOPS_SONIOX_ORG_KEY` env var. The separate `SONIOX_API_KEY` mount and its
usage-summary leg are unchanged; the balance series supersedes that line on
the wall once live.

## Modelled Modulate STT cost (no vendor API exists)

Modulate exposes no usage or balance API — every GET path probed returns 404 —
so its line can never be measured. `pull_prometheus.py` additionally pulls
`sum by (provider) (increase(omi_live_stt_audio_seconds_total[1d]))` (VAD
speech seconds flushed to backend-provider live sessions; the `modulate`
series is the measured volume), and `pull_modulate_modelled.py` multiplies it
by the **committed, dated unit price** from `backend/config/rate_card_v2.json`
(committed 2026-10-18 @ f6a358902db): **$0.06 per audio hour** — Modulate
"Multilingual Transcription" streaming WebSocket list price,
platform.modulate.ai (100 credits = $1, so $0.06/h is 6 credits/h); live SKU
`velma-2-stt-streaming`, not Velma Triage. Every row is `method=modelled`.
The rate card is SHA-pinned by backend tests; a price change is a reviewed
commit that updates the pinned expectations and this line's as-of date.

Coverage caveat, surfaced by the reconciliation rather than hidden: the
Prometheus series meters backend live/PTT streaming sessions; any Modulate
batch-REST volume outside that counter appears as reconciliation variance
against Mercury cash. The wall computes the trailing-30-day variance between
the modelled line and Mercury `modulate` cash (`stt_vendor` in the vendor
map) and prints it on the STT line. When the modelled line is unavailable
(missing series or missing card) the wall falls back to labelled Mercury
Modulate cash, exactly as before.

The loader writes `omi_finops.stt_modulate_modelled_daily` (date, audio
seconds, usd, price, price as-of, `method='modelled'`), dark while skipped.
The Modulate ORG key binding (`FINOPS_MODULATE_ORG_KEY`) is mounted for a
future vendor API; **no code calls a Modulate endpoint with it**, pinned by
test.
