# Omi TV daily PostHog rollup

Option A, approved 2026-10-16. No production deployment or new workflow is part
of this change. **David must name/authorize a public GitHub Actions workflow
before a new production image is built/shipped.** No `.github/` files change.

## Data contract

`wall-rollup-extract.ts` queries **one closed UTC arrival day per extraction**,
including all-event identity observations (so zero-qualified people remain in
cohort denominators), qualified activity, capture evidence and schema-2 MCP
activity. It imports the existing allowlist, exclusions, platform/source rules,
capture-time projection, and MCP threshold/cadence screen. The snapshot HogQL
queries explicitly deduplicate UTC days as well. This preserves the wall's
**telemetry proxy**, not a claim of a verified signup bridge/full staff roster or
complete saved-state/source-device coverage. Existing coverage disclosures apply.

The feature key is person × kind × platform × capture UTC date × signup-relative
24h bin × capture evidence. Rows carry only HMACs, closed-enum dimensions, counts,
first/last timestamps and the PostHog person-created anchor (the existing proxy).
`activity_day` deduplicates capture days across arrival days/retries; `age_day`
retains signup-relative clocks when a signup day crosses midnight. Source
microseconds are preserved for recency and signup-boundary comparisons. Primary
platform ranks distinct qualified days, latest activity, fixed platform order;
UI precedes MCP to match the snapshot. Cohorts freeze **entry platform** from
all-event observations; established retention freezes the denominator platform.
Capture families share the exact HogQL classifier. All cohort results require the
full query window including its **180-day prior history**. Money/health remain on
their existing sources. MCP is included only in the activity/growth/MAU paths,
as in the current snapshot; cohort MCP linkage remains unavailable.

Daily extracts include late captures on their original capture day when the
arrival day is in the requested source window, matching the existing HogQL
arrival bounds. Three recent arrival days are re-extracted daily to repair late
ingestion/person changes; up to two missing days in the last 14 days catch up,
serially with 5s pauses. Older late-ingestion or identity-merge changes require
an explicit date rerun. Neither source promises immutable resolved identity.

## Storage and privacy

BigQuery `based-hardware.omi_tv` in **US** (same as live `omi_finops`, verified
read-only 2026-10-16). Partition by arrival day; cluster features by kind/person.
BigQuery supports exact rolling distinct-person counts and cross-day cohorts;
GCS JSON would require loading person rows into the admin process, and Firestore
would require many document reads and add cache/store contention. The admin uses
ADC and **SELECT-only aggregate SQL**; its results contain counts, labels and
receipt metadata. No writer or billing JSON-key override is used on this path.

Person and feature keys are domain-separated HMAC-SHA256 using the existing
**`WEB_ADMIN_CRON_SECRET`**, injected as `CRON_SECRET` (also used by admin cache
precompute). No secret payload was read/changed for this implementation. The job
requires at least 32 characters. David must confirm that prerequisite privately;
if the existing secret does not meet it, propose a dedicated `OMI_TV_HASH_KEY`
secret for human provisioning before enabling, rather than weakening the check.
The implementation never prints the key or raw IDs/emails/properties. A separate
HMAC key fingerprint is stored in receipts and required on every read. Rotation
invalidates coverage; disable the reader and backfill the whole desired window
with the new key before enabling. This avoids mixing pseudonym epochs.

Each day is staged in a short-lived table from an in-memory NDJSON stream; only
HMACs/features enter that stream. On complete load, one BigQuery transaction
replaces that day in `person_day` **and** `coverage`. Empty days carry a zero-count
marker row and still get a receipt. Failed pages/loads leave the previous day
unchanged; concurrent transactions either commit a complete day or abort. A
staging table has a one-hour expiry and is deleted in `finally`. There is no
streaming insert deduplication window or non-atomic delete/load gap.

Reads have a 10 GiB maximum-bytes-billed ceiling and 30s job deadline.
The reader requires receipts for **every** arrival day in the precise query
window, matching definition version and key epoch. Missing days, IAM/schema/query
errors or disabled configuration use the existing bounded/backed-off HogQL leg.
Existing shared fenced leases and leg caches remain in place. Controlled source
selection/fallback events are logged without SQL or response bodies. The existing
Data & coverage row includes `rollup YYYY-MM-DD` (latest completed receipt; each
metric still independently checks for holes). Cached leg data and the live v2
snapshot retain their existing freshness/last-point rules. Turning the flag off
returns fills to HogQL; already-cached aggregates expire on their existing daily
schedule. No PostHog service credentials are needed to read a covered window.

## Cost and coverage

Per extraction: 5,000 feature rows/page, explicit outer LIMIT, stable keyset
cursor, maximum 100 pages / 64 MiB of feature JSON, 120s HTTP timeout and three attempts/page; any
truncation indication inconsistent with that page size or exhausted budget fails
closed. **No OFFSET and no 30–180-day PostHog window.** All raw and MCP branches
scan [D,D+1). Feature kinds run separately, keeping MCP cadence joins out of app extraction.
CTEs may inline into several scans of that single day; pagination
repeats those day scans. Expected small-day work is five feature queries plus any additional pages, not a
measurement or guaranteed 504 avoidance. Hard budget: 300 requests/extraction;
normally three extractions/day, up to five during gap catch-up. A day that still
times out remains a visible coverage hole. No dollar cost or Cloud Run job execution latency has been measured. A read-only
2026-10-15 source smoke extracted 15,653 features in seven logical page queries
and 100.4s, including nonempty MCP data; it performed no BigQuery load. Retries
are bounded but were not separately instrumented in that measurement.

Default backfill is 180 days, **one day per Cloud Run execution**, one task,
serial `--wait`, 30s pause, at most five days per invocation of `backfill.py
--execute` (maximum configurable batch ten). Commands print by default. At
30–120s/day plus 30s pause, estimated total 3–7.5h plus cold starts/retries and
operator gaps. Extrapolating that source smoke plus the 30s driver pause gives
about 6.5h for 180 similar days, before loading, job pauses and cold starts. Rerun a failed date; it overwrites, never appends duplicates.

**180 initial days do not cover every existing leg.** The 26-week growth leg
needs 189 days including its prior week. Capture-source needs 194 days; the oldest
12-week activation/retained cohorts need up to 271/301 days, respectively, because
the contract requires a full 180-day prior window. Those windows deliberately
fall back; do not claim the initial backfill removes every 504. To eliminate
cohort fallbacks immediately, explicitly extend the same bounded daily backfill
to 301 days (optional human decision); otherwise wait for daily accumulation.
Instrumentation-start labels remain in effect for older growth points.

## Human steps, in order (not executed by the agent)

Run from the public task checkout at the reviewed commit. All IAM/secret work is
David's human tier; do not use the agent read-only identity for these commands.
Existing accounts are reused; **do not create service accounts or keys**.
The FinOps writer and admin runtime accounts were verified live read-only; the
scheduler identity follows its checked-in deployment configuration. Grants below are
idempotent desired bindings, not claims that every grant is currently missing.

1. Confirm the existing secrets/config and key length privately. Do not print,
   paste, or rotate secret payloads as part of this rollout. Apply the schema:

   ```sh
   bq query --project_id=based-hardware --location=US --use_legacy_sql=false \
     < web/admin/jobs/omi-tv-rollup/schema.sql
   ```

   This creates dataset and tables through code; no separate `bq mk` is needed.

2. Apply dataset-scoped IAM with BigQuery schema-level DCL grants. `bq
   add-iam-policy-binding` supports tables/views only — not datasets — and there
   is no supported `gcloud ... datasets add-iam-policy-binding`:

   ```sh
   bq query --project_id=based-hardware --location=US --use_legacy_sql=false \
     "GRANT \`roles/bigquery.dataEditor\`
      ON SCHEMA \`based-hardware.omi_tv\`
      TO 'serviceAccount:finops-writer@based-hardware.iam.gserviceaccount.com';"
   bq query --project_id=based-hardware --location=US --use_legacy_sql=false \
     "GRANT \`roles/bigquery.dataViewer\`
      ON SCHEMA \`based-hardware.omi_tv\`
      TO 'serviceAccount:omi-admin-dashboard-runtime@based-hardware.iam.gserviceaccount.com';"
   gcloud projects add-iam-policy-binding based-hardware \
     --member='serviceAccount:finops-writer@based-hardware.iam.gserviceaccount.com' \
     --role=roles/bigquery.jobUser --condition=None
   gcloud projects add-iam-policy-binding based-hardware \
     --member='serviceAccount:omi-admin-dashboard-runtime@based-hardware.iam.gserviceaccount.com' \
     --role=roles/bigquery.jobUser --condition=None
   gcloud secrets add-iam-policy-binding WEB_ADMIN_CRON_SECRET --project=based-hardware \
     --member='serviceAccount:finops-writer@based-hardware.iam.gserviceaccount.com' \
     --role=roles/secretmanager.secretAccessor --condition=None
   gcloud secrets add-iam-policy-binding WEB_ADMIN_POSTHOG_PERSONAL_API_KEY --project=based-hardware \
     --member='serviceAccount:finops-writer@based-hardware.iam.gserviceaccount.com' \
     --role=roles/secretmanager.secretAccessor --condition=None
   ```

   The admin already consumes `WEB_ADMIN_CRON_SECRET`; no new admin secret grant.
   Dataset dataViewer allows queries over pseudonyms, but the implemented admin
   queries only return counts/metadata. It receives no dataEditor/write grant.

3. David names/authorizes the GitHub Actions build/deploy workflow. No workflow is
   supplied or added here. Use `web/admin` as build context and
   `jobs/omi-tv-rollup/Dockerfile`; build and smoke the standalone compiled writer
   through the approved GitHub Actions path, with no secrets during build.
   Fill `job.yaml` with that immutable image digest and the existing admin's
   `POSTHOG_PROJECT_ID` (current local harness uses `302298`; verify config).
   The job definition is a review artifact with deliberate placeholders. Then,
   with deployment authorization, replace it:

   ```sh
   gcloud run jobs replace web/admin/jobs/omi-tv-rollup/job.yaml \
     --project=based-hardware --region=us-central1
   gcloud run jobs add-iam-policy-binding omi-tv-rollup \
     --project=based-hardware --region=us-central1 \
     --member='serviceAccount:finops-unit-cost-scheduler@based-hardware.iam.gserviceaccount.com' \
     --role=roles/run.invoker --condition=None
   ```

   The human deploying/replacing must already have `iam.serviceAccounts.actAs` on
   the reused `finops-writer` SA. If a newly named Actions deployer lacks that
   binding, David must separately approve its exact identity; none is invented
   or granted here. The existing Scheduler service agent must retain its normal
   `roles/cloudscheduler.serviceAgent` grant; no new scheduler identity is used.

4. Deploy the reviewed admin source through its existing Actions path; keep
   `OMI_TV_ROLLUP_ENABLED=0` until data validation. Backfill in small batches:

   ```sh
   python3 web/admin/jobs/omi-tv-rollup/backfill.py                 # print 180 commands
   python3 web/admin/jobs/omi-tv-rollup/backfill.py --execute      # first five only
   # Next batch: advance --start by five days and set --days to the days remaining.
   ```

   Each command is `gcloud run jobs execute ... --wait
--update-env-vars=OMI_TV_ROLLUP_DATE=YYYY-MM-DD`; overrides affect only that
   execution. If a backfill operator lacks permissions, the human can grant
   `roles/run.jobsExecutorWithOverrides` on this job to that named operator.
   No persisted date override is applied to daily executions. Inspect aggregate
   coverage/row counts and Cloud Run execution status after each batch.

5. On a shell configured with ADC read access, PostHog credentials and the existing
   `CRON_SECRET` (not printed), validate synthetic SQL and compare real counts:

   ```sh
   cd web/admin
   OMI_TV_ROLLUP_SQL_CHECK=1 npx vitest run lib/__tests__/wall-rollup-sql-live.test.ts --maxWorkers=1 --environment=node --pool=threads
   OMI_TV_ROLLUP_ENABLED=1 OMI_TV_ROLLUP_LIVE_CHECK=1 npx vitest run lib/__tests__/wall-rollup-live.test.ts --maxWorkers=1 --environment=node --pool=threads
   ```

   Live comparison checks WAU and MAU and every platform at the last completed UTC week cutoff, serially. Missing coverage is a failure, not skip
   inside an opted-in run. It logs counts/timings only. Investigate mismatches
   before enabling; identity changes/late ingestion require day reruns.

6. Create the **paused, planned** scheduler explicitly (ordinary reconciles skip
   planned jobs). Existing scheduler-as-code, OAuth to Run Jobs API, daily 02:15 UTC:

   ```sh
   python3 backend/scripts/scheduler_reconcile.py --environment prod --apply --jobs omi-tv-rollup-daily
   ```

   After backfill/comparison, enable `OMI_TV_ROLLUP_ENABLED=1` on the admin through
   its runtime configuration (the existing Actions deploy uses merge semantics
   for environment variables); resume the schedule:

   ```sh
   gcloud run services update omi-admin-dashboard --project=based-hardware --region=us-central1 \
     --update-env-vars=OMI_TV_ROLLUP_ENABLED=1
   gcloud scheduler jobs resume omi-tv-rollup-daily --project=based-hardware --location=us-central1
   ```

   Update the checked-in schedule state to `ENABLED` when that rollout is
   authorized, otherwise a later explicit reconcile restores PAUSED. Verify
   completed executions, `coverage` dates, source-selection events, the actual
   Data & coverage row and equality of final chart points to snapshot stats.
   Rollback: disable the reader, pause scheduler. Do not delete historical data.

BigQuery IAM reference: https://cloud.google.com/bigquery/docs/control-access-to-resources-iam
PostHog SQL/query API: https://posthog.com/docs/sql
