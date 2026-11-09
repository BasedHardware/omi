# Held staging inputs approaching expiry

Lead2 ruling `9a5190`: retain the staging bucket's **30-day privacy ceiling**.
This change does not alter or apply a bucket lifecycle. Audio is never deleted
by dead-lettering. A terminal row does **not** preserve an object past its
existing lifecycle; recover it or obtain the original client bundle before then.

`enqueued_at` is the staged-input creation **proxy**, because staging occurs at
admission. It is not a GCS metadata measurement. It excludes time before admission
and does not restart on quarantine, assignment, expiry or requeue. The scope is
`audio_uri` under `gs://based-hardware-batch-pipeline-staging/`, not other buckets.

## Warning and retained terminal

The existing timeliness exporter emits
`omi_batch_held_oldest_age_seconds{leg="staged_input"}` for GPU worker quarantine
and committed assignment holds across all epochs, using `enqueued_at`. The new
warning `omi-batch-staged-input-age` fires above 21 days for 10 minutes. A sample
must be younger than 900 seconds; absent/stale data is unknown, covered by the
existing sampler-stale alert. No GCS reads or additional timer are introduced.

The existing held dead-letter sweep checks these same inputs at age **>=29 days**
and writes job `state=dead`, `dead_letter_reason=input_expiring`, plus its prior
leg and transition time. It retains audio, result receipts, intent/attempt
history, binding and privacy generation. It refuses active tokens/leases,
open operator/paid intents, privacy refusals and lost content ownership.
`record_pending` and provider-STT rows do not enter this path. Sweep pagination
means transition occurs when the existing scan visits the row, not a wall-clock
deadline guarantee.

`BATCH_INPUT_EXPIRING_ENABLED` is a default-on kill switch in
`config/refactor_modes.py`; `false`, `off`, `0` or `no` restores the previous held
behavior. The existing `BATCH_HELD_DEAD_LETTER_ENABLED` sweep kill still applies.
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
backend/.venv/bin/python backend/scripts/redrive_staging_inputs.py \
  --as-of "$HELD_INPUT_AS_OF" --page-size 128
```

The exact same dry-run command works after
`source ~/.local/bin/gcp-agent-env.sh prod-operator`. Dry-run is the default;
neither identity grants approval to apply. Obtain scoped operator authorization,
then use the digest from the fresh dry-run:

```bash
source ~/.local/bin/gcp-agent-env.sh prod-operator
backend/.venv/bin/python backend/scripts/redrive_staging_inputs.py \
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
backend/.venv/bin/python backend/scripts/redrive_staging_inputs.py \
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
