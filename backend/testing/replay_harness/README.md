# Replay harness

Replays real or synthetic pipeline inputs through the actual product code, locally, and reports the stage
each item stops at and why. A fix ships only after its failing cases replay to the expected outcome.

Stages, in order (`manifest.STAGES`): `capture_upload`, `admission`, `worker`, `projection`, `final_pass`, `titling`,
`episodes`. Today `capture_upload`, `admission` and `titling` are implemented. The others report `not_implemented`, which can never
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
production frequency. Whether retries exhaust depends on scheduling and host load, so
`admission-drain-contention` usually stops on `FirestoreContentionExhausted` but can admit cleanly. CI
accepts only those two outcomes for it; repeat it locally before reading a single run as a fix.

## Add a case

One directory per case: `manifest.json` (schema version 1, validated by `manifest.py`), `corpus.json`, and
optional `blobs/` and `cassettes/`. Expect either `pass` or a stop at a named stage with a reason regex:

```json
{"stages": {"admission": {"expect_stop_stage": "admission", "expect_reason": "retained_capture_not_durable"}}}
```

Keep the reproduced stop while gating a candidate (see below). After adopting the fix, a normal
regression fixture can expect `pass`. Record what the baseline actually does when you add a case;
never write the outcome you hope for.

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

## Gate a fix

Keep the failing expectation in the case, and add an optional v1 manifest block:

```json
{"gate": {"fixed_by_ref": true}}
```

A target must declare an expected failing stop. The baseline must reproduce that
stop and the candidate must pass that stage. This differential command does not
require the candidate to keep reproducing the old failure.

Run the **whole gate** in one Firestore emulator session, using the existing
Python environment (no dependency installation, branch switch, or cloud access):

```bash
unset GOOGLE_APPLICATION_CREDENTIALS CLOUDSDK_CONFIG CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE
export PATH=/opt/homebrew/opt/openjdk@21/bin:$PATH
/Users/dazheng/workspace/omi/bin/omi-heavy run -- \
  node_modules/.bin/firebase emulators:exec --only firestore --project demo-omi-isolated-tests \
  'make replay-gate REF=HEAD BASE=<last-good-sha> CASES="backend/testing/replay_harness/fixtures/admission-control /absolute/private/case" OUTPUT=/Volumes/Ephemeral/scratch/replay-gate K=3'
```

`REF` and `BASE` resolve to full commit SHAs. The gate archives each backend into
a temporary directory under `OUTPUT`, removes the snapshot on exit, and runs
**this checkout's fixed adapter and testing support** against each product tree.
`adapter_sha256` covers the Python testing support, drivers, gate, snapshot helper
and strict transaction fixture. Adapter/case changes during replay fail closed.
Use trusted local refs; the gate executes their product code.

Every case/repetition gets its own unique `batch_pipeline_test_replayharness_*`
namespace and synthetic user IDs. The environment cleans these documents and
seeded finalization/outbox rows before the next run; no emulator-wide flush is
used. Both sides share only the running emulator, with fresh subprocesses per
side. Do not run another gate into the same output directory concurrently.

`K` (`--repeats`, default 3) controls runs **per side** for multi-drainer admission
stress shapes, detected from corpus geometry rather than the case name. Other
cases run once. Classification uses a strict majority of `(status, stop stage,
reason)` outcomes; a tie or no strict majority fails as inconclusive. All runs
are saved; any new exception class/site in even a minority run fails the gate.

| Classification | Meaning |
|---|---|
| `fixed` | BASE reproduced the expected failing stop; REF passes that stage |
| `still_failing` | Both stop at the same stage/reason |
| `regressed` | BASE passed all selected stages; REF stops |
| `changed_reason` | Stops differ, or an unexpected BASE stop became a pass |
| `unchanged_pass` | Both pass all selected stages |

If REF passes the repaired stage then stops later, the case is `fixed`; the later
outcome and any new exceptions remain visible. PASS requires every declared
target to be `fixed`, no `regressed` cases, no new exception class/site across the
corpus, and no inconclusive or unimplemented outcomes. Untargeted known failures
may remain. PASS with no targets establishes regression coverage only.

`gate.json` contains SHAs, adapter identity, per-case identities/digests,
classifications, all sanitized per-run stage reports and the verdict. `gate.md`
is a short table. Case identities are **SHA-256 of manifest IDs for every tier**;
raw IDs, scrub descriptions, notes, evidence, paths and case content never appear
in gate output or stdout. `corpus_sha256` length-frames the relative names and raw
bytes of manifest + corpus + local blobs/cassettes, in sorted order; moving a case
does not change its digest. Content is read in place, including Tier C paths
outside Git, and never copied into output. Child stdout/stderr is discarded;
only the runner's sanitized outcome fields are retained. Keep output private
(mode 0700 on creation). Exit codes: 0 PASS, 1 FAIL, 2 execution/input error.

Run the proof suite (including all-fixture REF=BASE=HEAD and a throwaway,
unpushed product commit that turns an expected stop into a pass):

```bash
/Users/dazheng/workspace/omi/bin/omi-heavy run -- \
  node_modules/.bin/firebase emulators:exec --only firestore --project demo-omi-isolated-tests \
  'backend/.venv/bin/python -m pytest backend/tests/integration/test_replay_harness_gate.py -q'
```

The synthetic commit deliberately overrides custody only to prove product-tree
selection; it is not a shippable product fix. Set `REPLAY_GATE_EVIDENCE` to a
private directory to retain its two `gate.md`/`gate.json` receipts.
