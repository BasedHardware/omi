# Replay harness

Replays real or synthetic pipeline inputs through the actual product code, locally, and reports the stage
each item stops at and why. A fix ships only after its failing cases replay to the expected outcome.

Stages, in order (`manifest.STAGES`): `capture_upload`, `admission`, `worker`, `projection`, `final_pass`, `titling`,
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

## Replay a service's runtime config

Pass `--runtime-env <service>[:<env>]` to `run`, or `RUNTIME_ENV=backend` to
`make replay-harness`, `make replay-privacy-full` and `make replay-gate`.
The environment defaults to `prod`; `dev` is also supported. This renders the
**repository's declared deploy inputs offline**, without reading production or
claiming they match a running revision. Unknown services/environments fail closed.
Cloud Run services use `deploy/compose_runtime_env.py` (base plus overlay);
GKE workloads use the drift checker's workload registry and exact `helm template`
invocation with their checked-in chart values. GKE requires Helm on PATH. No
live private overrides, ConfigMaps, Secret Manager payloads or ambient env inputs
are fetched or resolved. Indirect `envFrom` sources are dropped as whole sources.

Only literal scalar entries matching `FSR_*`, `FIRESTORE_READ_*`, `*_PERCENT`,
`*_TTL_SECONDS` or `*_ENABLED` can be applied. Credential/secret/token, identity,
project, endpoint/URL/URI, host/port/emulator/socket, bucket/database and path/file
names are denied even under those prefixes. Entries marked secret, credential,
auth, identity or service discovery, and all secret refs and `env_var` bindings
(including bindings with defaults) are dropped. Rendering runs in a separate
process with only PATH/TMPDIR/SYSTEMROOT inherited. A differing binding for any
setting owned by the hermetic environment refuses the run; an equal binding
preserves that setting. Values outside this policy never enter reports or error
messages. Each case report and gate worker outcome records only:

```json
{"runtime_env":{"service":"backend","env":"prod","applied_keys":["FSR_SUBSCRIPTION_TTL_SECONDS"],"dropped_count":1}}
```

The key list/count above is illustrative. `dropped_count` includes nonallowlisted,
secret and indirect entries (one count per unresolved GKE `envFrom` source).
With no selector the existing code-default replay behavior is preserved.

```bash
unset GOOGLE_APPLICATION_CREDENTIALS CLOUDSDK_CONFIG CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE
export PATH=/opt/homebrew/opt/openjdk@21/bin:$PATH
/Users/dazheng/workspace/omi/bin/omi-heavy run -- \
  node_modules/.bin/firebase emulators:exec --only firestore --project demo-omi-isolated-tests \
  'make replay-privacy-full RUNTIME_ENV=backend OUTPUT=/Volumes/Ephemeral/scratch/privacy-runtime'
```

Gate workers render REF and BASE separately using **each side's archived
composition code and inputs**, including retries. The fixed adapter never copies
its checkout's runtime settings into either side. A config-only TTL fix therefore
produces a normal `fixed` classification when BASE reproduces the expected stop
and REF passes. `runtime_env` is recorded per outcome because values can differ
between the two sides even when their applied key names are identical.

The privacy stage still explicitly enables its test levers with shadow off to
exercise staleness. Runtime TTLs reach the real helpers unchanged; no TTL override
is needed. `PRIVACY_TTL_OVERRIDE_S` remains an explicit test monkeypatch and takes
precedence when supplied. Privacy replay does not certify live rollout enablement, and it
checks the checked-in config at the tested source, not the live traffic-serving revision.

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

## Decrypting captured cases

Decryption is opt-in. With no private files, captured transcript fields stay opaque,
`titling:precondition_skipped:recovery_undecoded` remains an explicit stop, and the
reports say `decryption: off`. To enable it, supply **all three** files:

- `--secret-file`: the UTF-8 product master secret (at least 32 bytes, optional trailing newline).
- `--uid-file`: the consenting owner's UID.
- `--consent-file`: the capture consent pins, one lowercase SHA-256 UID hash per line.

Each file must be an owned, nonsymlink regular file with mode exactly `0600`.
Replay reuses `guard.py`'s private-file and consent checks, then requires
`sha256(uid)` to equal the case's `corpus.owner_sha256`. New captures include this
pin. Older captures may use their retained result `owner_key` or immutable
artifact URI owner hash; every retained pin must agree. A case without an owner
pin must be recaptured; the salted owner token alone cannot prove ownership.
Inputs are validated before infrastructure starts. Never put these files under
OUTPUT or Git. Replay does not obtain credentials or read production.

```bash
unset GOOGLE_APPLICATION_CREDENTIALS CLOUDSDK_CONFIG CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE
export PATH=/opt/homebrew/opt/openjdk@21/bin:$PATH
/Users/dazheng/workspace/omi/bin/omi-heavy run -- \
  node_modules/.bin/firebase emulators:exec --only firestore --project demo-omi-isolated-tests \
  'make replay-harness CASES="/absolute/private/owner-case" OUTPUT=/Volumes/Ephemeral/scratch/replay-decrypted SECRET_FILE=/absolute/private/master-secret UID_FILE=/absolute/private/owner-uid CONSENT_FILE=/absolute/private/consent-pins'
```

The direct `run` command accepts `--secret-file`, `--uid-file` and `--consent-file`.
`make replay-gate` accepts the same `SECRET_FILE`, `UID_FILE` and `CONSENT_FILE`
variables alongside `REF`, `BASE`, `CASES` and `OUTPUT`. Both sides and any retry
receive the existing file paths; the gate never copies the files or their values.
The report and each worker outcome record `decryption: on` when enabled.

Decrypted Tier C replay supports `capture_upload` and `titling`. Product key
derivation, transcript decryption/decompression and artifact authentication run
unchanged. The real owner identity is used only in memory for derivation and
artifact AAD; emulator document names remain synthetic. Product string/byte
field values are replaced at the Firestore SDK boundary with random opaque
identity tokens backed by a per-run memory table, so even generated titles stay
in memory. Equality queries and transactions remain real; this adapter does not
support ordering queries over string fields. Artifact ciphertext is read in
place and plaintext is returned only in memory. Product stdout/stderr and logs
are discarded during decrypted execution. No plaintext, UID or secret is written
to temporary files, reports or logs. This is process-local instrumentation: do
not run concurrent replay coroutines in the same Python process. Separate gate
workers remain isolated. Reports retain only the existing sanitized observations.

## Privacy cache replay

`privacy_cache` qualifies **cache staleness only**. It is a schema-v1 boundary that compares real cached readers with
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

The report records `bound_s` and `bound_comparison`. Qualification requires
**at least 1,000 verified faulted transitions**, zero mismatches, zero errors and
no unverified applicable faults. `min_verified_transitions` defaults to `1000`;
the committed smoke explicitly sets it to `0` and cannot establish qualification.
A short run may pass its smoke expectation while `qualification_met` is false.
The full generator emits 1,400 rows to exceed the verified minimum after excluding
baseline controls. An insufficient count stops with
`privacy_cache:insufficient_verified_transitions`; a fault with no observed
application stops with `privacy_cache:unverified_fault`.

`transition_results` records each row's applicability, actual application,
completion, verification status and bounded evidence. Redis injection counters
prove calls were refused; BEGIN loss also requires a successful END. Subscription
request memo cases require a warmed entry, a real memo hit and writer-driven clearing.
Deletion-marker `request_memo` cases instead prove the absence of request memoization:
both warm reads must consult fenced Redis, a real writer runs in a separate request
scope, and every probe in the original open scope must consult Redis and immediately
observe the updated marker. Reintroducing the request memo fails this proof, including
when the writer would have cleared a memo in its own request.
Overlap cases require every writer to reach real FSR BEGIN, or (for batch and
uncached protection) a nonempty Firestore SDK Commit, before the overlapping read.
The Commit barrier delegates to the saved real method, retaining the product
privacy-token fence and emulator RPC. All concurrent attempts join before any
recovery. An SDK transaction that exhausted `Aborted` retries gets one additional
real-writer call after contention ends; `writer_outcomes` and `writer_retry_count`
record it. The retry is never an extra gate sample, and unrecovered or unrelated
errors still fail the stage.

`fault_coverage` counts verified faults, baseline controls, N/A rows and unverified
rows separately per family/fault. `none` is always a baseline, never a gate sample.
Ten unsupported cells are N/A: all three Redis faults for batch/protection, and
request memo crossing for tombstone/hold/batch/protection. Their real readers do
not use those mechanisms. The generator excludes these combinations; a manually
supplied N/A row can still run baseline probes but never contributes to the gate.
The Markdown table marks unsupported cells N/A and prints verified/completed
counts for supported cells.

The standard probes always run; a nonstandard bound also adds an exact-bound probe. TTL experiments never
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

The fixed-seed generator covers every kind and every applicable family/fault pair in its
120-transition smoke prefix. Faults include persistent Redis outage, both
invalidations lost with Redis reads available, BEGIN-token loss, overlapping
writers/readers, a reader held inside the real BEGIN fence, and a request memo
spanning the real writer. Cache publication/memo events verify eligible warm
paths actually exercise the optimization. Batch reads call the real guard twice
inside one transaction; distinct source sets force cold generation-memo misses
and independent live authority walks. `batch:memo_hit` proves generation-decision
reuse across repeated checks; the retired WQ12 snapshot memo is no longer a
qualification requirement. Emulator mutation tests set
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
selects other fixtures. `make replay-privacy-full` generates 1,400 transitions
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
CI's existing `backend/scripts/run-emulator-proofs.sh` invokes the privacy
integration file, including the committed 120-transition smoke and catch proofs.
The full corpus remains outside fast unit tests and that CI command.

The report's `scope` is `cache_staleness_only`. Its explicit
`wall_clock_decisions_not_simulated` limits are legal-hold gate age and BYOK
heartbeat age: their wall clocks do not advance with the Redis/cache clock. Hold
age is seeded before the transition; BYOK scenarios read `get_byok_state.active`
and do not exercise the heartbeat-age decision in `is_byok_active`. Cache replay
does not qualify those time-derived decisions.

This is synthetic emulator qualification only. Recorded Tier-S timelines and
the required two-hour production shadow are separate work packages.

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

`--worker-timeout SECONDS` (`WORKER_TIMEOUT` in Make, default 1800) sends SIGTERM
on expiry. The worker cancels its asyncio task so environment cleanup unwinds;
the parent allows ten seconds of grace, then kills and waits for a stuck worker.
Before each Firestore commit/batch-write, a private journal records only synthetic
document names (never values). After a timeout or worker failure, the parent
deletes those exact documents through the validated loopback emulator endpoint,
including namespace rows, synthetic user children and global outbox/finalization
rows. Local storage and the journal live below the parent's private temporary
resource tree outside OUTPUT (on `/Volumes/Ephemeral/scratch` on this host) and
are removed with it. The gate fails on timeout/cleanup error; no receipt can authorize
shipping. No emulator-wide flush or production client is used.

`K` (`--repeats`, default 3) controls runs **per side** for multi-drainer admission
stress shapes, detected from corpus geometry rather than the case name. Other
cases run once. Repeated outcomes are compared by `(status, stop stage, reason)`.
If BASE is mixed, the case is `unstable`: it never counts as fixed, regressed or
changed_reason. If BASE is unanimous but REF is mixed, the gate automatically
runs **one additional batch of K REF runs for that case**, using the same REF
snapshot and fresh namespaces. Only a unanimous retry matching BASE clears the
instability and permits normal classification. A mixed retry or a unanimous
retry differing from BASE leaves the case `unstable` and produces `INCONCLUSIVE`
(nonzero), even for a non-target case. The initial mixed batch can never prove a
fix. There is no majority vote or further retry. BASE unanimity also checks that
every run agrees on reproducing the expected stop, including matches in sanitized
observations. Every initial and retry outcome remains in `candidate.outcomes`;
`candidate.retry_start` gives the retry's zero-based starting index, or null if
none was needed. `candidate.unanimous` describes the accepted initial batch or
equal retry. New exception class/sites from **any** run still fail the gate,
including exceptions from the initial batch of a recovered case.

Ship comparisons require `K >= 3` for non-target stress cases and `K >= 5` for
stress cases declaring `fixed_by_ref`. Smaller samples produce `DIAGNOSTIC`
(when otherwise clean), never a ship PASS or a proven fix; the diagnostic flag
cannot make that verdict exit zero. For a stress case to count as `fixed`, BASE
must unanimously reproduce its expected failing stop and REF must unanimously
pass every selected stage. A REF that stops later is not a stress fix.

| Classification | Meaning |
|---|---|
| `fixed` | BASE reproduced the expected failing stop; REF passes that stage |
| `still_failing` | Both stop at the same stage/reason |
| `regressed` | BASE passed all selected stages; REF stops |
| `changed_reason` | Stops differ, or an unexpected BASE stop became a pass |
| `unchanged_pass` | Both pass all selected stages |
| `unstable` | A repeated case has mixed outcomes on either side; never a proven fix or regression |
| `insufficient_repeats` | A potential stress fix lacks the required sample count |

For a single-run case, if REF passes the repaired stage then stops later, the
case is `fixed`; the later outcome and any new exceptions remain visible. PASS requires every declared
target to be `fixed`, no `regressed` cases, no new exception class/site across the
corpus, and no inconclusive or unimplemented outcomes. Every `changed_reason`
fails closed, including movement to either an earlier or a later stop. Untargeted
known failures and **BASE-mixed non-target** stress cases may remain. A declared
target that is unstable produces `INCONCLUSIVE` (nonzero) instead of PASS; a
separate regression, incomplete report or new exception still takes precedence
as FAIL. A ship PASS requires at least one target, every target proven fixed,
and the minimum stress sample counts above.

With zero targets, an otherwise clean comparison reports `REGRESSION_ONLY` and
exits nonzero by default. Use `--regression-only` (Make: `REGRESSION_ONLY=1`) to
exit zero with that distinct verdict for regression checks such as REF=BASE.
This flag never turns `FAIL`, `DIAGNOSTIC` or `INCONCLUSIVE` into a successful exit.

`gate.json` contains SHAs, adapter identity, per-case identities/digests,
classifications, all sanitized per-run stage reports and the verdict. `gate.md`
is a short table. Tier C identities are HMAC-SHA256 with a fresh random 32-byte
key for each invocation, stored as `OUTPUT/identity.key` with mode 0600. Equality
holds only within that invocation; rerunning even into the same OUTPUT rotates
the key. Do not share the key with reports. Tier C reports contain **no content
digest**. Tier S identities use SHA-256, and their `corpus_sha256` length-frames
the relative names and bytes of manifest + corpus + local blobs/cassettes in
sorted order. Those fixture/structure-only digests survive case relocation.
Raw IDs, scrub descriptions, notes, evidence, paths and case content never appear
in gate output or stdout. Content is read in place, including Tier C paths outside
Git, and never copied into output. Child stdout/stderr is discarded; only the
runner's sanitized outcome fields are retained. **Reports, keys, journals and
logs stay outside Git**, including reports from synthetic Tier C proof cases.

OUTPUT is created 0700. An existing OUTPUT must be a nonsymlink directory owned
by the current user with mode exactly 0700; broader permissions are refused,
without changing them. `gate.json`, `gate.md`, and the identity key are created
0600, replacing stale named receipts without following symlinks. Temporary
snapshot/resource directories are private and removed after execution.
Exit codes: 0 ship PASS (or explicitly opted-in REGRESSION_ONLY), 1 rejected
verdict (FAIL, DIAGNOSTIC, INCONCLUSIVE, or ship-mode REGRESSION_ONLY), 2 execution/input error.

Run the proof suite (three all-fixture REF=BASE=HEAD trials in regression-only mode, a throwaway
unpushed product commit that turns an expected stop into a pass, and forced
worker-timeout recovery with both cooperative exit and SIGKILL escalation):

```bash
/Users/dazheng/workspace/omi/bin/omi-heavy run -- \
  node_modules/.bin/firebase emulators:exec --only firestore --project demo-omi-isolated-tests \
  'backend/.venv/bin/python -m pytest backend/tests/integration/test_replay_harness_gate.py -q'
```

The synthetic commit deliberately overrides custody only to prove product-tree
selection; it is not a shippable product fix. Set `REPLAY_GATE_EVIDENCE` to a
private directory to retain its two `gate.md`/`gate.json` receipts.
