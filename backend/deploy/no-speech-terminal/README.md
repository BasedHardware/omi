# Reversible no-speech terminal

Operation: `batch-live-no-speech-v1`. Owner: dazheng. Authority: relay-cl1 GO
320bdf. `NO_SPEECH_TERMINAL_ENABLED` defaults **on** in
`config/refactor_modes.py`; it is an operator kill switch, not a fleet rollout.
No scheduled or automatic apply exists. This runbook authorizes no production
execution by itself.

## What the tool does

`backend/scripts/mark_no_speech_orphans.py` discovers one bounded, newest-first
page of stale `status=in_progress`, `record_lane_owner=batch_live_v1` captures,
decodes their retained raw-live audio in memory, runs the repository's strict
local VAD, and plans a reversible `no_speech` terminal for rows with under ten
seconds of speech after complete capture coverage is proven. It never deletes a row or an
audio object.

The close stamps `status=completed`, `discarded=true`,
`terminal_no_derived_effects=true` and a `no_speech_terminal` marker that saves
the prior lifecycle fields. The operator undo restores those fields exactly and
removes the marker.

## Capture coverage proof

Planning and apply reproof each list the raw objects afresh, pin their data
generations and metadata versions (metageneration), and decode through the existing authenticated source reader. The
capture interval is the row's timezone-aware `started_at` and `finished_at`.
Each object's versioned `capture_start` (or canonical filename start),
`capture_end`, explicit zero `gap_count`, and decoded mono 16 kHz PCM sample
count must agree. Missing listing size/metageneration, a failed download precondition,
missing/unknown timing, internal gaps, conflicting overlaps,
or objects extending outside the capture beyond tolerance refuse the proof.

The retained-audio sample-range `union` helper proves coverage from actual
sample counts, never padded unit durations. The fixed allowance is **20 ms
(320 frames) missing in total**, including both boundaries and all interior
gaps. Only those rounding-sized holes receive zero padding. Overlapping samples
must be byte-identical and are included once, including contained objects.
VAD sees the resulting capture timeline, so overlaps cannot inflate speech or
audio duration. The existing two-hour decoded-input budget still bounds all
objects, including duplicates.

`coverage_incomplete` leaves the row untouched for operator review. Empty raw
and legacy listings also receive that refusal: absence cannot establish complete
coverage. Historical `no_retained_audio` plans are no longer actionable. Obtain
a fresh plan only after coverage is established; never weaken proof to drain a
refusal. No operator execution is authorized by this change.

## Plan, review, approve one page

Use the approved operator environment with the repository backend on `PATH`.
Dry-run may use `ro-prod` or `prod-operator`; apply requires `prod-operator`
because retained audio GETs need it. Prepare a private directory with mode 0700
for the cursor and ledger. Never print or copy the cursor or ledger.

```sh
python backend/scripts/mark_no_speech_orphans.py --limit 128 \
  --after-file /Volumes/Ephemeral/scratch/private-nospeech/after.json \
  --next-file /Volumes/Ephemeral/scratch/private-nospeech/next.json
```

Default dry-run performs no data or filesystem writes except the explicitly
requested private next-page cursor. The report contains counts, closed exits, a
plan digest, measured speech/audio seconds and raw/legacy object counts. It
never prints a UID, conversation ID, object path or decoded audio.

Use a new ledger path for each page. A ledger is created exclusively and cannot
be reused for another apply, including a partially applied page after a crash.
Undo the old ledger separately, then plan again with a new ledger path. This
keeps each ledger bounded to one page; do not concatenate or append ledgers.

Review the dispositions and the digest, then apply the same page:

```sh
NO_SPEECH_TERMINAL_ENABLED=true python backend/scripts/mark_no_speech_orphans.py \
  --limit 128 --apply --approve-plan-sha256 REVIEWED_DIGEST \
  --after-file /Volumes/Ephemeral/scratch/private-nospeech/after.json \
  --next-file /Volumes/Ephemeral/scratch/private-nospeech/next.json \
  --ledger /Volumes/Ephemeral/scratch/private-nospeech/ledger.jsonl
```

The apply reauthorizes privacy, re-reads the exact row revision, re-measures the
retained audio with a fresh coverage proof and rechecks job absence before one fenced lifecycle close. A
changed row, measurement, consent or privacy generation refuses the write; get
a fresh plan and approval. Pace pages manually; do not run parallel applies.

## Undo

The ledger is the only undo input. It records the row identity, run id, prior
row digest, planned revision and committed revision. Undo restores only the
unchanged generation this run closed. A prepared-only entry (crash or receipt
write failure) or committed_revision_unknown is resolved by reading the row:
marker.run_id and the three closed fields must match, then restoration fences
on that current revision. A receipt with a known revision keeps its original
exact-revision fence. Undo requires neither ENCRYPTION_SECRET nor a GCS client:


```sh
NO_SPEECH_TERMINAL_ENABLED=false python backend/scripts/mark_no_speech_orphans.py \
  --undo --apply --limit 128 \
  --ledger /Volumes/Ephemeral/scratch/private-nospeech/ledger.jsonl
```

A later edit, deletion, merge, lock or finalization job refuses the restore. The
row then stays in the no-speech terminal for operator review. Never replace a
known receipt revision just to bypass revision_changed. For manual recovery,
an operator must review the current row and marker.prior, confirm this run and
closed shape still own the three lifecycle fields, then submit a separately
approved restore with that exact current revision; preserve unrelated edits,
all content and audio. This runbook authorizes no production recovery.

## Dispositions and exits

- `no_speech`: actionable. Exit:
  **operator undo restores original fields**.
- `has_speech`: left for the normal batch pipeline. Exit: **normal batch
  pipeline**.
- `retained_audio_unmeasured`: legacy chunks exist but no raw-live objects; the
  tool does not claim silence it did not measure. Exit: **operator review**.
- `coverage_incomplete`: missing timing/audio, gaps or conflicting overlaps;
  left untouched for **operator review**. Historical `no_retained_audio` is also
  non-actionable and exits by **operator review**.
- `decode_failed`: retained audio could not be decoded. Left untouched. Exit:
  **operator review**.
- `privacy_blocked` / `privacy_skipped`: owner or capture privacy refused. Left untouched. Exit:
  **operator re-run after consent**.
- `not_candidate`, `barrier_mismatch`, `already_registered`: left to the
  existing lifecycle owner or normal batch pipeline.
- `upload_pending`: left untouched for **operator review** of the upload.
- `committed_revision_unknown`: hide committed without an SDK revision receipt;
  exit: **ledger undo resolves the matching marker**, rather than a fresh close.
- `already_marked`: already in the no-speech terminal. Exit: **operator undo**.
- `state_changed`, `proof_refused`, `read_error`, `write_error`: park for
  **operator re-run**.
- `disabled`: the kill switch is off. Exit: **operator re-run after
  enablement**.

## Rollback and acceptance

First set `NO_SPEECH_TERMINAL_ENABLED=false` to stop new close applies. Keep
it false while using ledger undo to restore unchanged closed pages, then revert
the operator/storage code if needed. Undo remains available while disabled.
No audio or row deletion is involved.
Local synthetic tests do not establish staging or production acceptance; that
remains operator work.
