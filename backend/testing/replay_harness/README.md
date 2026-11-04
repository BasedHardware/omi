# Replay harness

Replays real or synthetic pipeline inputs through the actual product code, locally, and reports the stage
each item stops at and why. A fix ships only after its failing cases replay to the expected outcome.

Stages, in order (`manifest.STAGES`): `admission`, `worker`, `projection`, `final_pass`, `titling`,
`episodes`, `privacy_cache`. Implemented boundaries are `capture_upload`, `admission`, `titling` and
`privacy_cache`. The others report `not_implemented`, which can never
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

## Privacy cache replay

`privacy_cache` is a schema-v1 boundary that compares real cached readers with
`fresh_reads()` authority on the loopback Firestore emulator. Each transition
owns a fresh replay environment, fakeredis and virtual cache clock. The stage
forces privacy levers on only inside that environment; shadow is off so it
cannot hide candidate behavior. It seeds the before state, warms the real
reader, invokes the real writer, then probes at +0/+1/+59/+60/+61/+300 seconds.
The batch authority check additionally starts a new attempt for ground truth,
since its memo is independent of the Redis/request bypass. Candidate reads retain
a real privacy session across the transition; authority reads temporarily leave
that session so its separate memo cannot mask a mismatch.

Every transition and every scheduled probe runs, including after a mismatch.
The stage ends `stopped` with `privacy_cache:staleness_bound_exceeded` if any
unequal decision occurs at or after the bound. Unexpected transition/probe
errors are sanitized, accumulated and also prevent a pass. Reports contain no
user, conversation or writer-token identifiers.

The optional schema-v1 manifest parameter `stages.privacy_cache.bound_s` defaults
to `60.0`: an old decision at **offset >= bound_s** is a mismatch. For example:

```json
{"stages": {"privacy_cache": {"expect": "pass", "bound_s": 60.0}}}
```

The report records `bound_s` and `bound_comparison`. The standard probes always
run; a nonstandard bound also adds an exact-bound probe. TTL experiments never
change this rule. `by_family_fault_offset` includes explicit zero cells for every
family/fault/offset, with `probes`, `stale`, `mismatches` and `errors`. Earlier
stale decisions count separately from bounded mismatches. A companion
`<case>-privacy.md` table prints +59/+60/+61/+300 cells as stale/mismatches/probes.
The report counts attempted, applied and completed transitions, probes and overlap
probes, and gives the largest sampled stale offset per family.
A reported zero means no probe observed stale state; it does not measure latency
between probes. Idempotent tombstone retries count as transitions too.

Families cover deletion marker state-machine arcs, tombstone creation/retry,
legal-hold placement/release and destructive-operation acquire/finish/takeover,
batch generation advance/purge completion, subscription/BYOK changes and the
currently uncached data-protection level. The external-write cache checks
account deletion and destructive gates; the separate uncached legal-hold reader
checks hold placement. Data-protection writers remain unfenced and uncached;
this replay does not authorize adding a cache to them.

`bound_margin_s` is the smallest observed difference between the bound deadline
and a warmed key's actual Redis `PEXPIRETIME` boundary, rather than its configured
TTL. `bound_margin_s_by_family` and `expiry_samples_by_family` show its coverage;
no Redis expiry observation is `null` (batch attempt memos and uncached protection
reads have no Redis TTL). Redis/fakeredis retain a key in its expiry millisecond,
so **zero margin is not safe** for the strict comparator. The exact-bound probe
remains authoritative; this field does not turn a failing boundary into a pass.

The fixed-seed generator covers every kind and every family/fault pair in its
120-transition smoke prefix. Faults include persistent Redis outage, both
invalidations lost with Redis reads available, BEGIN-token loss, overlapping
writers/readers, a reader held inside the real BEGIN fence, and a request memo
spanning the real writer. Cache publication/memo events verify eligible warm
paths actually exercise the optimization. Emulator mutation tests set
120s TTLs and lose invalidations: both BYOK directions and deletion-marker creation
must record the +60/+61 mismatches and finish all probes. Default-TTL controls
preserve the observed closed-boundary behavior, and 55s controls must qualify.

```bash
unset GOOGLE_APPLICATION_CREDENTIALS CLOUDSDK_CONFIG CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE
export PATH=/opt/homebrew/opt/openjdk@21/bin:$PATH
/Users/dazheng/workspace/omi/bin/omi-heavy run -- \
  node_modules/.bin/firebase emulators:exec --only firestore --project demo-omi-isolated-tests \
  'make replay-harness OUTPUT=/Volumes/Ephemeral/scratch/privacy-smoke'
/Users/dazheng/workspace/omi/bin/omi-heavy run -- \
  node_modules/.bin/firebase emulators:exec --only firestore --project demo-omi-isolated-tests \
  'make replay-privacy-full OUTPUT=/Volumes/Ephemeral/scratch/privacy-full'
```

`make replay-harness` defaults to the committed smoke; explicit `CASES` still
selects other fixtures. `make replay-privacy-full` generates 1,000 transitions
under `OUTPUT`, then writes reports under `OUTPUT/report`; reports stay out of
Git. For an exact 55s experiment across deletion-marker, tombstone, legal-hold
and subscription Redis entries, pass `PRIVACY_TTL_OVERRIDE_S=55` to either Make
target (CLI: `--privacy-ttl-override-s 55`). This test-side monkeypatch changes
both the TTL helper and cached-read duration, including the imported aliases in
`users`; the real readers, writers and cache logic still execute. The report
records `ttl_override_s`. It does not alter product configuration or the
manifest bound. Generate variants from `backend/` with
`.venv/bin/python -m testing.replay_harness.gen_privacy_timeline --output <dir>`
(`--seed`, `--transitions`, `--mix` JSON family weights and `--faults` comma list).
This is synthetic emulator qualification only. Recorded Tier-S timelines and
the required two-hour production shadow are separate work packages.
