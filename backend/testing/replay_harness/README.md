# Replay harness

Replays real or synthetic pipeline inputs through the actual product code, locally, and reports the stage
each item stops at and why. A fix ships only after its failing cases replay to the expected outcome.

Stages, in order (`manifest.STAGES`): `admission`, `worker`, `projection`, `final_pass`, `titling`,
`episodes`. Today only `admission` is implemented. The others report `not_implemented`, which can never
satisfy an expectation, and a manifest may not expect a stop at an unimplemented stage.

`batch_replay/` remains the projection deploy gate. This package owns per-case stage expectations.

## Run cases

```bash
/Users/dazheng/workspace/omi/bin/omi-heavy run -- make replay-harness \
  CASES="backend/testing/replay_harness/fixtures/admission-not-durable backend/testing/replay_harness/fixtures/admission-control" \
  OUTPUT=/Volumes/Ephemeral/scratch/<lane>/replay-out
```

Each run writes `report.json` (one item per case: stages, furthest stage, stop reason, duration, verdict)
and prints a table. `FAIL` means the pipeline stopped; the expectation verdict says whether that was the
expected stop. The command exits nonzero when any expectation does not hold.

The admission stage drives the real `register_recording`, `drain_recordings` and `admit_recording` against
a loopback Firestore emulator (namespace `batch_pipeline_test_replayharness`), a local-directory storage
adapter, fakeredis and a fake clock. Outbound network, ambient credentials and cloud clients are refused.
Contention cases run several real drain loops concurrently; they are synthetic stress shapes, not
production frequency.

## Add a case

One directory per case: `manifest.json` (schema version 1, validated by `manifest.py`), `corpus.json`, and
optional `blobs/` and `cassettes/`. Expect either `pass` or a stop at a named stage with a reason regex:

```json
{"stages": {"admission": {"expect_stop_stage": "admission", "expect_reason": "retained_capture_not_durable"}}}
```

A fix PR flips its case from the reproduced stop to `pass`. Record what `main` actually does when you add
a case; never write the outcome you hope for.

Only synthetic fixtures belong in Git (`fixtures/`). Captured production cases never do.

## Capture production inputs (read-only)

`capture_prod.py` reads production through a transport that permits only Firestore `runQuery`/`batchGet`
and Storage `GET`; it never writes, deletes or decrypts.

- **Tier S** (structure only, any user): HMAC identifiers with a per-corpus salt, allowlisted numeric and
  enum fields, no text, URIs or error strings. Runs under the `ro-prod` tier.
- **Tier C** (content, consenting owner only): job, result and artifact rows, the conversation document,
  finalization and outbox rows, the chunk inventory listing, and artifact blobs as stored ciphertext. The
  uid comes from a `0600` file and must match a pinned SHA-256 in a `0600` consent file. Artifact blobs
  need the `prod-operator` tier; audio-derived objects are listed, never fetched.

```bash
cd backend
source ~/.local/bin/gcp-agent-env.sh ro-prod   # or prod-operator for Tier C blobs
umask 077
.venv/bin/python -m testing.replay_harness.capture_prod --check-access
.venv/bin/python -m testing.replay_harness.capture_prod --tier S --limit 2000 --output <new 0700 dir>
.venv/bin/python -m testing.replay_harness.capture_prod --tier C \
  --uid-file <0600> --consent-file <0600> --conversations-file <0600> --output <new 0700 dir>
```

Corpora live under `/Volumes/Ephemeral/scratch/replay-corpus/` (mode `0700`), never in Git, and are deleted
when the program that needed them ends. Output is printed as counts, statuses and exception types only.
Capture at detection time: a fix that lands first erases the failing input.
