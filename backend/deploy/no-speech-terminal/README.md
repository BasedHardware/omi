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
seconds of speech (or provably no retained audio). It never deletes a row or an
audio object.

The close stamps `status=completed`, `discarded=true`,
`terminal_no_derived_effects=true` and a `no_speech_terminal` marker that saves
the prior lifecycle fields. The operator undo restores those fields exactly and
removes the marker.

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

Review the dispositions and the digest, then apply the same page:

```sh
NO_SPEECH_TERMINAL_ENABLED=true python backend/scripts/mark_no_speech_orphans.py \
  --limit 128 --apply --approve-plan-sha256 REVIEWED_DIGEST \
  --after-file /Volumes/Ephemeral/scratch/private-nospeech/after.json \
  --next-file /Volumes/Ephemeral/scratch/private-nospeech/next.json \
  --ledger /Volumes/Ephemeral/scratch/private-nospeech/ledger.jsonl
```

The apply reauthorizes privacy, re-reads the exact row revision, re-measures the
retained audio and rechecks job absence before one fenced lifecycle close. A
changed row, measurement, consent or privacy generation refuses the write; get
a fresh plan and approval. Pace pages manually; do not run parallel applies.

## Undo

The ledger is the only undo input. It records the row identity, run id, prior
row digest, planned revision and committed revision. Undo restores only the
unchanged generation this run closed:

```sh
NO_SPEECH_TERMINAL_ENABLED=true python backend/scripts/mark_no_speech_orphans.py \
  --undo --apply --limit 128 \
  --ledger /Volumes/Ephemeral/scratch/private-nospeech/ledger.jsonl
```

A later edit, deletion, merge, lock or finalization job refuses the restore. The
row then stays in the no-speech terminal for operator review.

## Dispositions and exits

- `no_speech` / `no_retained_audio`: actionable. Exit:
  **operator undo restores original fields**.
- `has_speech`: left for the normal batch pipeline. Exit: **normal batch
  pipeline**.
- `retained_audio_unmeasured`: legacy chunks exist but no raw-live objects; the
  tool does not claim silence it did not measure. Exit: **operator review**.
- `decode_failed`: retained audio could not be decoded. Left untouched. Exit:
  **operator review**.
- `privacy_blocked`: owner or capture privacy refused. Left untouched. Exit:
  **operator re-run after consent**.
- `not_candidate`, `barrier_mismatch`, `already_registered`: left to the
  existing lifecycle owner or normal batch pipeline.
- `already_marked`: already in the no-speech terminal. Exit: **operator undo**.
- `state_changed`, `proof_refused`, `read_error`, `write_error`: park for
  **operator re-run**.
- `disabled`: the kill switch is off. Exit: **operator re-run after
  enablement**.

## Rollback and acceptance

Set `NO_SPEECH_TERMINAL_ENABLED=false` to stop new applies and undos. Use the
ledger undo to restore any closed page. No audio or row deletion is involved.
Local synthetic tests do not establish staging or production acceptance; that
remains operator work.
