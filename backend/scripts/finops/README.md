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
| Users projection | Firestore `users` (field mask) | read-only bot | platform cohort, plan |
| Transcription seconds | Firestore collection group `hourly_usage` | read-only bot | audio-pipeline driver |
| VAD-forwarded audio hours | Prometheus via the Grafana proxy on monitor.omi.me | Grafana token | modelled STT vendor volume |
| OpenAI invoice | OpenAI admin costs API | org admin key | the LLM residual and the reconciliation |
| Anthropic invoice | Anthropic admin cost API | org admin key | same |
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
  under any other account (`gcpauth.assert_writer_identity()`). The read-only bot stays
  read-only. Human ADC is not the cron writer.
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

All four are partitioned by `date` and clustered. Loads are **idempotent per date**: the run's
dates are deleted and re-inserted inside one BigQuery transaction, so re-running a date replaces
it rather than doubling it.

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
| `pull_providers.py` | OpenAI and Anthropic invoices |
| `pull_stripe.py` | subscription book → MRR/ARPU by plan |
| `posthog_dau.py` | DAU by platform (denominators only) |
| `fs.py` | dependency-free Firestore REST client |

## Known gaps

* **STT vendor cost is modelled, not measured.** Modulate carries ~95% of live sessions and there
  is no invoice feed or contract rate; `stt_vendor_low` uses a $0.0043/min placeholder and
  `stt_vendor_high` is ×1.8. Replace `STT_VENDOR_RATE_PER_MIN` when the contract rates land.
* **SaaS with no feed** (PostHog, Sentry, Redis Cloud, ~$500–700/mo) is in no pool at all.
* **Half of variable cost is shared overhead** split by headcount because no per-uid request or
  Firestore-read counter exists. `shared_activity` is the alternative, not a better truth.
* **The ledger's `app_platform` header is written only by `desktop_proactivity`**, so request-level
  platform is unavailable; platform comes from the users cohort join.
* **Stripe is a snapshot**, not history. `plan_revenue_daily.snapshot_date` says so on every row.
