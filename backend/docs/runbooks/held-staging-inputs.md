# Held staging inputs approaching expiry

The reviewed `deploy/storage-lifecycle/retention_contract.json` declares the staging
bucket lifecycle at **60 days** (production extended on 2026-11-16). It supersedes
the former 30-day lead2 ruling `9a5190` for this bucket.
This change does not alter or apply a bucket lifecycle. Audio is never deleted
by dead-lettering. A terminal row does **not** preserve an object past its
existing lifecycle; recover it or obtain the original client bundle before then.

`audio_staged_at` anchors the CURRENT staged object after exact-bundle repair
replaces `audio_uri`. An absent or malformed replacement clock falls back to
`enqueued_at`, the earlier creation
**proxy** because staging occurs at admission. Neither is a GCS metadata read.
Quarantine, assignment, expiry and operator requeue do not reset object age. The scope is
`audio_uri` under `gs://based-hardware-batch-pipeline-staging/`, not other buckets.

## Warning and retained terminal

The existing timeliness exporter emits
`omi_batch_held_oldest_age_seconds{leg="staged_input"}` for GPU worker quarantine
and committed assignment holds across all epochs, using the current object
anchor above. A fresh restage cannot mask an older legacy input; an incomplete
bounded age scan fails the sample rather than publishing a healthy age. The new
warning `omi-batch-staged-input-age` fires above 51 days for 10 minutes. A sample
must be younger than 900 seconds; absent/stale data is unknown, covered by the
existing sampler-stale alert. No GCS reads or additional timer are introduced.

`omi_batch_staged_input_clock_invalid_total` counts malformed clock observations
in completed bounded age samples and existing held sweep pages, including rows
with neither clock usable. Name-ordered held pages also observe missing clock
fields that age-ordered queries cannot discover.
Repeated observations count again; this is not a distinct-row fleet census.
A valid admission clock still contributes its conservative age and the 51-day
warning. When neither clock is usable, the row cannot enter `input_expiring`.
When an age sample observes such a row,
`omi_batch_timeliness_scan_truncated{leg="staged_input"}` is 1 so the existing
scan-blind warning exposes the incomplete age sample. Failed scans retain the
existing sample-error/staleness path. No IDs or clock values become labels.

The existing held dead-letter sweep checks these same inputs at age **>=59 days**
and writes job `state=dead`, `dead_letter_reason=input_expiring`, plus its prior
leg and transition time. It retains audio, result receipts, intent/attempt
history, binding and privacy generation. It refuses active tokens/leases,
open operator/paid intents, privacy refusals and lost content ownership.
`record_pending`, allowance parking and uncommitted provider-STT states do not
enter this path. A committed provider result can enter the assignment leg if its
original assignment/result/privacy fences pass.

Before the ordinary held name-cursor page, **every serving maintenance tick** reads
oldest-first cutoff pages for `enqueued_at` (legacy objects) and `audio_staged_at`
(replacements), **128 rows per indexed query**, at most 256 candidates total.
The enqueue stream excludes only replacements with valid staging clocks;
malformed replacements remain discoverable by admission age. The replacement
stream admits only valid staging clocks, preventing duplicate candidates.
The transaction rechecks the
current object clock. Separate durable age cursors advance even over fresh
restages, malformed rows and transaction refusals, so none can pin a prefix.
Neither urgency cursor depends on the ordinary held name cursor. Crash replay
and competing sweeps retain the existing idempotent transaction/checkpoint CAS.
Urgency also runs while the ordinary pass's `next_at` is in the future. Such a
tick checkpoints only `input_after`, preserving `next_at`, `held_after` and all
redrive state. Only the ordinary name page and nightly dead-held pass honor
`next_at`; the input kill disables urgency queries and cursor writes.

For the supplied review's dated 22,583-row cohort, allow one maintenance interval
plus a page drain: `(1 + ceil(22583 / 128)) * T = 178 * T`, per stream. Both
streams advance in the same tick. `config/batch_pipeline.py:serving_tick_seconds`
defaults to a 20-second sleep and caps configured sleep at 60 seconds. Thus the
cadence component is **3,560 seconds (59m20s)** by default, or **10,680 seconds
(2h58m)** at the maximum configured sleep. Add maintenance, query and transaction
runtime; the sleep alone is not a wall-clock SLA. A conservative **300-second
completed-maintenance-tick budget** yields **53,400 seconds (14h50m)**, including
the initial wait; the previous 14h45m estimate omitted it. Meeting that budget
requires successful ticks within 300 seconds and no more than the cited cohort
per stream. Outages, transaction refusals or a growing backlog invalidate that
assumption. The ordinary 300-second throttle, 32-row page and all timer settings
are unchanged. Missing indexes fail urgency discovery rather than silently
falling back to the slow name cursor.

The legacy stream reuses `*_batch_timeliness_assignment_held`. Replacement
streams require the prod/dev `*_batch_staged_input_age` composite indexes
on `(state, recovery_state, audio_staged_at, __name__)`, plus the allowance-hold
and exhausted-allowance retry staging-input composites (`*_batch_staged_allowance_*`)
declared in `database/batch_pipeline_indexes.py` and `firestore.indexes.json`.
The repository index guard/deploy gate must establish them READY before this
serving rollout. Follow the [index apply/deploy workflow](../../../.github/agent-docs/firestore-queries-and-indexes.md#apply-and-deploy)
for production approval and READY verification. This lane does not create live
indexes or backfill Firestore;
legacy documents remain queryable through their existing enqueue index.

`BATCH_INPUT_EXPIRING_ENABLED` is a default-on kill switch in
`config/refactor_modes.py`; `false`, `off`, `0` or `no` restores the previous held
behavior. The existing `BATCH_HELD_DEAD_LETTER_ENABLED` sweep kill still applies.
The new kill is explicitly bound true in runtime base/prod and the listen/worker
charts; set that binding false and redeploy the sweep hosts to roll it back.
Neither kill resurrects terminals or changes the bucket's deletion policy.

Upload status uses the existing `failed/batch_artifact_missing` needs-attention
and exact-bundle retry path before any partial/completed status. This is a
replacement-eligibility signal, **not proof of GCS absence**. Capable clients
retain their original content identity and may replace only expired-risk GPU
inputs; projected siblings and paid history stay intact. Released clients
without custody-repair protocol support keep the existing nonterminal response
so they retain local audio rather than regrouping it into duplicate uploads.
Record conversations already use the existing age-bounded failed transcription
presentation; this change adds no conversation writes or UI.

There is no automatic exit from `dead/input_expiring`: polling and nightly
`held_expired` redrive cannot undo it. The existing operator GPU requeue restores
the compute queue; the existing assignment release restores `committed/pending`
only after its target is restorable and every original assignment/privacy fence
passes; and `RecoveryStore.release_allowance_input` (used via
`redrive_staging_inputs.py --scope allowance`) releases pre-expiry or retained
`allowance_held`/exhausted-`retry` inputs only after verifying exact staged
object generation, privacy/erasure generation, content ledger ownership, and live
funded-batch entitlement (decrementing `allowance_holds.held_count` when leaving
`allowance_held`). All manual exits remain available with `BATCH_INPUT_EXPIRING_ENABLED`
off and never bypass entitlement checks or manufacture a restorable target.

## Manual redrive (never scheduled)

Run from the repository root with its own `backend/.venv`. This tool never reads
audio. Dry-run makes only Firestore reads and prints aggregate counts and
the plan SHA-256, never IDs, URIs, transcripts or exception bodies. It examines
at most 128 rows per page, ordered by `enqueued_at`, then document name. Default
`--scope held` selects GPU/assignment staging holds (including retained `input_expiring`
terminals) at age **>=51 days**; `--scope allowance` selects `allowance_held`,
exhausted-allowance `retry`, and `dead/input_expiring` (`input_expiring_leg=allowance`)
units at age **>=51 days**. Other examined rows are skipped, not authorized for writes.
Apply first checks the exact generation pinned by each reviewed `audio_uri` using
a metadata-only GCS GET with `if_generation_match`. Missing, mismatched, unpinned,
permission-denied or otherwise unproven inputs are counted as
`skipped_input_unproven`; neither requeue nor assignment release runs for them.
The check is repeated at apply time after digest approval and immediately before
the existing snapshot-fenced mutation. It is not a lease preventing subsequent
privacy/lifecycle deletion. No object contents, listing, deletion or new credentials
are involved. Dry-run selection does not prove object existence.
The existing `(state, recovery_state, enqueued_at, __name__)` index serves discovery.
Missing indexes fail closed; no fallback or index deployment occurs here.

Freeze the time for a page and keep the same arguments for dry-run and apply:

```bash
source ~/.local/bin/gcp-agent-env.sh ro-prod
export HELD_INPUT_AS_OF="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
OMI_ENV_STAGE=prod backend/.venv/bin/python backend/scripts/redrive_staging_inputs.py \
  --as-of "$HELD_INPUT_AS_OF" --page-size 128
```

The exact same dry-run command works after
`source ~/.local/bin/gcp-agent-env.sh prod-operator`. Dry-run is the default;
neither identity grants approval to apply. Obtain scoped operator authorization,
then use the digest from the fresh dry-run:

```bash
source ~/.local/bin/gcp-agent-env.sh prod-operator
OMI_ENV_STAGE=prod backend/.venv/bin/python backend/scripts/redrive_staging_inputs.py \
  --as-of "$HELD_INPUT_AS_OF" --page-size 128 \
  --apply --approve-plan-sha256 '<approved plan_sha256>'
```

Apply recomputes the entire plan and rejects a different digest before any writer.
Each transaction compares the job snapshot (and the assignment receipt snapshot),
then reuses `RecoveryStore.requeue_quarantined` or
`ProjectionReleaseStore.release`. Changed rows and ownership/privacy/target
refusals are counted. A committed page is not an assertion of successful
transcription: verify actual queue/projection progress separately. Partial
execution or lost replies require a new dry-run and approval; never reuse a
digest for a different page or invent successful counts after an error.

For pagination, use a private directory and separate input/output cursor files:

```bash
install -d -m 700 /Volumes/Ephemeral/scratch/held-input-redrive
OMI_ENV_STAGE=prod backend/.venv/bin/python backend/scripts/redrive_staging_inputs.py \
  --as-of "$HELD_INPUT_AS_OF" --page-size 128 \
  --next-cursor-file /Volumes/Ephemeral/scratch/held-input-redrive/next.json
```

Keep input cursor and frozen time unchanged through approval/apply, and use the
same `--next-cursor-file` arguments. After settling a page, move its output to a
separate input filename, then pass `--cursor-file` for the next page. Cursor files
contain private document references, are mode 0600, and must never enter Git or
logs. A null output ends that pass. Begin another pass after remediating refusals;
advancing the cursor does not prove skipped inputs safe. The CLI has no scheduler,
no implicit loop, no lifecycle/IAM writes and no provider execution.

## Lifecycle configuration and deployment coupling

`config/batch_pipeline_retention.py` is the runtime lifecycle source, already
inside every consuming image's existing source closure. A unit contract requires
its value to equal `batch_staging_delete_age_days` in
`deploy/storage-lifecycle/retention_contract.json` and the production ceiling.
The JSON is used by operator tools and is not copied into images or read on runtime
import. Update the Python value and JSON declaration together. There is no
environment override. Warning is lifecycle minus nine days (51 days),
terminal is lifecycle minus one day (59 days). Sweep discovery, transactional
expiry, provider hold recheck timing and manual redrive selection import these
thresholds. The provider-STT lost-wake sweep window also derives from this lifecycle, covering
the last 59-day + 2-hour recheck and refusing candidates older than the 60-day lifecycle.
The retired `BATCH_PIPELINE_PROVIDER_STT_SWEEP_MAX_AGE_DAYS` override is ignored,
so a stale 30-day deployment binding cannot strand live work. The enrichment
sweep window and the existing sweep-age kill remain unchanged.
The warning alert artifact is checked against the same value in tests.
The production ceiling declaration must match; the separately declared development
bucket ceiling is unchanged, and this input-expiry path matches the production
bucket URI only.

A lifecycle extension must reach the bucket before deploying a longer runtime
threshold. A shortening requires deploying the earlier terminal first and proving
all affected eligible holds settled before shortening the bucket policy. Recheck
bucket metadata and the release lifecycle prerequisite; a code constant cannot
prove live storage policy. Never lower the bucket to roll back this PR. Rolling
back code restores the earlier terminal and can prematurely dead-letter retained
inputs; the existing input-expiry kill may stop new transitions while the lead
coordinates rollback. Neither action resurrects existing dead letters.

Deploy the shared runtime to the five held-sweep services (`backend`, `backend-sync`,
`backend-sync-backfill`, `backend-listen`, `backend-integration`) and the batch/provider
workers that import retention timing, including the GPU batch image, plus the monitoring alert bundle. Confirm
actual deployment bindings with the release owner. This PR performs no rollout.


## Mandatory batch lifecycle-change check (procedural)

There is no scheduled batch-bucket checker or batch lifecycle apply workflow in
this repository. The private-cloud-sync lifecycle workflow covers different
buckets. **Drift detection for batch staging is procedural**, not a continuous
monitor or a guard on arbitrary out-of-band GCS changes.

Before any authorized batch lifecycle change, use the proposed runtime's checked-out
code and review every proposed live-object Delete that can reach staging inputs:
its age in seconds must be **strictly greater than `TERMINAL_SECONDS`** (59 days
for this contract). A day-59 or earlier Delete is forbidden. Preserve the existing
hold/privacy prerequisites too; an unverified hold control still fails closed.
Run the existing read-only bucket checker before the change and immediately after
it, and archive its receipt with the lifecycle change:

```bash
source ~/.local/bin/gcp-agent-env.sh ro-prod
backend/.venv/bin/python backend/scripts/check_sync_staging_lifecycle.py \
  --bucket gs://based-hardware-batch-pipeline-staging
```

`check_sync_staging_lifecycle.policy_failure` passes the runtime `TERMINAL_SECONDS`
to `retention_contract.floor_violations` as an additional strict floor for the
production staging bucket, independent of the shorter declared hold floors.
A checker failure, unavailable metadata or missing permission blocks qualification;
do not waive it or add credentials in this PR. A live day-60 policy can still fail
an independent unverified hold prerequisite; this new check does not certify that
control. Extensions reach storage first; shortenings require the earlier runtime
terminal and proof the affected holds settled before changing storage. The release
owner must carry these steps into any external apply/drift tooling; this PR does
not claim such tooling is wired automatically.
