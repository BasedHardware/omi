# Held staging inputs approaching expiry

Lead2 ruling `9a5190`: retain the staging bucket's **30-day privacy ceiling**.
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
warning `omi-batch-staged-input-age` fires above 21 days for 10 minutes. A sample
must be younger than 900 seconds; absent/stale data is unknown, covered by the
existing sampler-stale alert. No GCS reads or additional timer are introduced.

`omi_batch_staged_input_clock_invalid_total` counts malformed clock observations
in completed bounded age samples and existing held sweep pages, including rows
with neither clock usable. Name-ordered held pages also observe missing clock
fields that age-ordered queries cannot discover.
Repeated observations count again; this is not a distinct-row fleet census.
A valid admission clock still contributes its conservative age and the 21-day
warning. When neither clock is usable, the row cannot enter `input_expiring`.
When an age sample observes such a row,
`omi_batch_timeliness_scan_truncated{leg="staged_input"}` is 1 so the existing
scan-blind warning exposes the incomplete age sample. Failed scans retain the
existing sample-error/staleness path. No IDs or clock values become labels.

The existing held dead-letter sweep checks these same inputs at age **>=29 days**
and writes job `state=dead`, `dead_letter_reason=input_expiring`, plus its prior
leg and transition time. It retains audio, result receipts, intent/attempt
history, binding and privacy generation. It refuses active tokens/leases,
open operator/paid intents, privacy refusals and lost content ownership.
`record_pending` and provider-STT rows do not enter this path.

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
streams require the new prod/dev `*_batch_staged_input_age` composite indexes
on `(state, recovery_state, audio_staged_at, __name__)`. They are declared in
`database/batch_pipeline_indexes.py` and the generated Firestore manifest.
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
passes. Both remain available with the new switch off. Manual release never
resets a paid attempt budget or manufactures a restorable target.

## Manual redrive (never scheduled)

Run from the repository root with its own `backend/.venv`. This tool never reads
audio or GCS. Dry-run makes only Firestore reads and prints aggregate counts and
the plan SHA-256, never IDs, URIs, transcripts or exception bodies. It examines
at most 128 rows per page, ordered by `enqueued_at`, then document name. It selects
GPU/assignment staging holds (including retained `input_expiring` terminals)
at age **>=21 days**. Other examined rows are skipped, not authorized for writes.
The existing `(state, recovery_state, enqueued_at, __name__)` index serves it.
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
