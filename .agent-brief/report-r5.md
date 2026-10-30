# Round 5: receiver-proven capture unions

Worktree: `/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-capture-window-coverage-upstream-keep-clean`.
Starting HEAD: `3697ab9fd0450d9e044981da9b93860f64d2dd6e`.
Runtime/test HEAD: `fb7b265c7970a858f93606513681ce40816fdda6`.
Documentation HEAD: `92a2ae3154`; it moves the pipeline section to avoid an advancing-main EOF conflict.
Its Python tree is identical to the tested runtime HEAD.
New commits only; no push, PR creation, deployment, fetch/sync, production reads,
cloud/API requests, credentials, guard relaxation or forbidden-path changes.
The prescribed frozen HEAD takes precedence over ordinary fresh-main/sync guidance.

## Changes and why they are provable

One new default-off switch: **LIVE_CAPTURE_WINDOW_MERGE_UNION**. Code, base/dev/prod
overlays, composed runtime manifest, classification, registry and all four dev/prod
listen/pusher Helm lists agree. Retention, preservation, strict projection and
AUDIO_TIMELINE_V2 retain their existing false declarations.

For each translated known piece, the receiver can attach a fixed-size private
`CaptureWindowProof`: a UUID epoch identity, exact strict half-open word/window
bounds, and one contiguous accepted-send run projected through CaptureTimeline.
SendMap coalesces only if BOTH provider and capture axes are adjacent. Missing,
failed or VAD-skipped sends and elapsed-axis holes break a run. Wall anchors split
the run; compacted samples cannot prove its prefix. The new marker uses strict
projection regardless of the legacy strict-projection flag, but does not change
legacy attachment or timestamps. If the stored legacy window differs from the
strict window (notably an exclusive end at a hiatus anchor), it cannot use this proof.

A union requires both contributors' current windows to match their proofs, the
same epoch, and ONE accepted-run snapshot covering the entire union. A later
snapshot may expand an earlier run across silence actually received by the
provider. It never stitches disconnected snapshots or fills an unsent interval.
If proof is absent, invalid or mismatched, the original overlap/touch behavior and
positive-gap clearing remain. Existing speaker/provider/manual/protected-ID guards
run before this change. Partial cross-speaker sentence redistribution still clears
both windows; no per-word repair proof is invented.

Proofs travel separately through receiver raw dictionaries, TranscriptSegment
PrivateAttr/property, transcript persistence kwargs and LiveTranscriptMerge return
metadata. The planner reconstructs them after rebuilding models and verifies the
transaction snapshot bounds, not a cached tail's bounds. Successful writes update
one proof for the mutable tail of each of at most 32 recent conversations in the
processor's session. No translator, PCM or mutable send map is retained; no epoch identifier or new
field enters transcript storage or public projections. Buffer entries carry only fixed-size snapshots.
Restarts, cap eviction, a concurrently changed window, or an uncertain acknowledgement
can reduce recovery and fail closed. Turning OFF clears the session sidecar.

## Where unknown sides come from

The user supplied #20657's first-ten-minute production attribution: 185 known,
110 unknown-side, 37 gap, 27 custom-STT, 18 discontinuous-translator and 5
outside-accepted-send distinct stored segments (382 total); inherited-unknown
versions were 503, while anchor compaction and send-map eviction were zero.
These are supplied observations, not queries performed in this lane. They favor
merge recovery over more retention, but cannot by themselves separate initiating
losses from within-batch amplification.

Code and real-path tests establish two amplification mechanisms:

1. **Within one fresh provider batch**, `We[known]`, `heard[known]`, `audio.[known]`
   have small positive word gaps. Legacy absorption of the first two clears the
   window as `merge_gap`; absorption of the third then overwrites the cause with
   `merge_unknown_side`. The first stored segment is therefore labeled unknown-side
   even though all three original pieces were known. ON keeps `We heard audio.` in
   ONE row with its known union. This means the supplied production labels are not
   disjoint initiating root causes: some unknown-side counts can be gap descendants.
2. **Across ticks**, a persisted missing tail is explicitly tagged
   `inherited_unknown`, and every later append propagates that unknown. The planner
   intentionally reconstructs models from serialized payloads; previously no private
   accepted-run proof survived this reconstruction. The new bounded sidecar restores
   proof for genuinely known tails, preventing the initiating observed-gap loss.

No code evidence supports replacing committed text/window by ID when a later final
arrives. The receiver mints IDs before buffering; Soniox forwards only final tokens,
Deepgram declares `interim_results=False`, and Modulate buffers word messages until
final utterance handling. Text/timing are paired at callback translation. Durable
replay receipts deliberately suppress repeated IDs. The new duplicate-ID test keeps
stored `Lost text.` unknown rather than accepting `Changed text.` with a known
window. Unknown audio is never reconstructed from a newer different text interval.
A controlled callback-before-send-acceptance case also remains genuinely unknown.
This is source/fixture evidence, not a measured attribution of production providers.

For genuinely unknown contributors, ON stops mixed known/unknown absorption only
when the PRECEDING row ends with existing supported sentence punctuation. It handles
both directions, protecting a completed known sentence from the next unknown one
and resuming known text after a completed unknown sentence. Inside a sentence,
ordinary word merging continues and unknown text remains unknown. For example:

| OFF persisted rows | ON persisted rows |
| --- | --- |
| `Lost old sentence. Now we have audio.` (unknown) | `Lost old sentence.` (unknown); `Now we have audio.` (known) |
| `Hello world.` (unknown because of received silence) | `Hello world.` (known; one row) |
| `A long unfinished phrase yes.`; `Another sentence.` (both unknown) | Same two rows, both unknown after partial speaker repair |

Ten supported punctuation variants have row assertions. No provider-word boundary
is used to start a row, and the old preservation flag remains OFF.

Recovered unions report the existing `known_window` in both version and first-ID
attribution. No recovered sub-signal or new labels were needed. Unknown-side and
inherited-unknown labels remain for actual unknown results. Existing metric names,
label sets and flag-OFF deltas are unchanged.

## Local commits

- `ea95b9a333` — receiver/run proof, private planner transport, bounded sentence
  absorption, all default-off declarations, pipeline documentation and initial
  real-path/simulation tests; migrate offline declaration and planner-call fixtures.
- `fb7b265c79` — typed accessors for private model proof and SendMap run lookup;
  extra three-word same-batch poisoning regression. No suppression or guard change.
  The first shard attempt on ea95b9a333 found 8 private-usage type errors before
  executing tests; the complete candidate includes this repair.
- `92a2ae3154` — documentation-only: move the new pipeline section beside existing
  capture-window sections to avoid a synthetic-merge EOF conflict with concurrently
  advancing main. No Python source or deployment declaration changes.
- Report-only commit follows validation; its hash is in the local Git log.

## Proof and simulation

All backend execution used backend/test.sh explicit file lists or the canonical
run-unit-ci.sh runner. Network and CPU guards remained enabled. StrictFirestore
provides real transaction ordering enforcement; provider transport receives only
synthetic PCM. No ad-hoc client construction or external replay.

- Initial exact-HEAD red replay: 40 tests, **19 failed / 21 passed**; candidate
  subsequently passed all 40. Receipt: `r5-red-head.log`, `r5-third.log`.
- Final selected red replay of exact starting source: **22 failed / 8 passed / 0 errors**,
  including same-batch/separate-tick silence unions for three providers, unknown
  sentence boundaries, the three-word causal chain, attribution and simulations.
  `.agent-brief/r5-head-proof-final.py` overlays six exact `git show 3697ab9fd0:<path>`
  files, invokes only `backend/test.sh`, and restores candidate bytes in finally.
  No refs/history change. Receipt: `r5-red-head-final.log`.
- Final full focused list: **1,034 passed / 27 files / 0 failed**, exit 0, with the
  default 0.30-second call-phase guard. All **62** new round-5 tests executed.
  Command: `CAPTURE_R5_SIMULATION_OUTPUT="$PWD/.agent-brief/r5-simulation-final" BACKEND_PYTEST_WORKERS=1 BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-brief/r5-focused.txt" PYTHON=.venv/bin/python bash backend/test.sh`.
  Receipt: `r5-focused-complete.log`.
- Initial broader focused run found stale fixture assumptions (three Cloud Run
  env tests, one pusher rendered-env test and one planner spy), all repaired by
  supplying the new false declaration or forwarding the new private argument.
  No assertion or policy was weakened. A subsequent focused run passed 1,032;
  after the typed accessors and batch regression, the terminal run above passed 1,034.
- Exact flag-OFF receipt comparison: base and final candidate each **1 passed**, and
  decoded persisted payloads plus all exercised existing metric deltas are equal.
  Command: `CAPTURE_PARITY_OUTPUT=<receipt> LIVE_CAPTURE_WINDOW_MERGE_UNION=false BACKEND_PYTEST_WORKERS=1 BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-brief/r5-parity.txt" PYTHON=.venv/bin/python bash backend/test.sh`.
  Receipts: `r5-off-head-final.json`, `r5-off-candidate-final.json`, corresponding logs.
  The earlier base/candidate receipts also compare equal.

The simulation uses twelve six-word sentences, received pauses, one callback before
send acceptance, three provider identities, and two reconnects with provider-axis
rebasing. Every word is persisted through receiver -> transcript ticks -> StrictFirestore.
The Soniox lane uses its actual token handler, submitting an interim then a final
for every known word and asserting each interim contributes no raw text. Other
provider lanes use their final callback shape. Real-path refusal tests separately
cover failed sends, absent sends, wall hiatuses, restart and concurrent-window changes.

| Simulated provider | OFF known rows / all rows | ON known rows / all rows | OFF known words | ON known words | Total words |
| --- | --- | --- | --- | --- | --- |
| Modulate | 0 / 3 | 4 / 5 | 0 / 72 | 66 / 72 | 72 |
| Soniox | 0 / 3 | 4 / 5 | 0 / 72 | 66 / 72 | 72 |
| Deepgram | 0 / 3 | 4 / 5 | 0 / 72 | 66 / 72 | 72 |

Thus this workload goes from 0% to 80% distinct-row coverage and 91.7% word coverage,
with 3 -> 5 rows, all containing at least one complete six-word sentence. The six-word
unknown sentence stays unknown. JSON receipts contain every resulting row text:
`r5-simulation-final.{modulate,soniox,deepgram}.json`. These are controlled synthetic
estimates, not a predicted fleet percentage. Existing upstream adapter tests also
run in the focused suite; no provider network is involved.

## Full validation

All four final canonical shards passed on exact runtime/test HEAD `fb7b265c79`.
Command from `backend/`: `PYTHON=.venv/bin/python bash scripts/run-unit-ci.sh --all --shard 4/k`,
k=1,2,3,4, executed sequentially by `.agent-brief/r5-run-shards.py`. The CLI uses
TOTAL/INDEX, hence 4/k rather than the inverse spelling in the request.

| Shard | Files | Passed | Failed | Skipped | Deselected | Exit | Seconds | Receipt |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 4/1 | 397 | 7,596 | 0 | 0 | 18 | 0 | 410.86 | `r5-shard-1.log` |
| 4/2 | 396 | 7,373 | 0 | 24 | 1,319 | 0 | 373.25 | `r5-shard-2.log` |
| 4/3 | 396 | 6,125 | 0 | 2 | 24 | 0 | 336.05 | `r5-shard-3.log` |
| 4/4 | 396 | 7,861 | 0 | 1 | 731 | 0 | 175.69 | `r5-shard-4.log` |
| Total | **1,585** | **28,955** | **0** | **27** | **2,092** | | | |

Every final shard's environment preflight: 17 passed / 9 optional warnings / 0
failed; typecheck: 0 errors / 12,801 warnings / 0 informations. Independently
recounted the summary totals, selected-file counts and completed file groups;
every final command exits 0 with no error annotations. Existing skips and marker
deselections remain; all 62 new tests executed. `r5-shard-counts.json` records totals.

The first shard-1 attempt on ea95b9a333 stopped at 8 private-usage type errors,
with zero unit tests executed (`r5-shard-1-typecheck-failed.log`). Typed accessors
repaired those before the terminal focused rerun and full restart. The first
shard-4 unit attempt on fb7b265c79 had 7,860 passed / 1 failed / 1 skipped / 731
deselected, exit 1 (`r5-shard-4-timing-failed.log`). The unchanged existing
`test_sequential_batching_accumulates_requests` uses 5 ms submission sleeps and a
50 ms fake GPU delay; it produced successful batches `[1, 4, 1]`, violating its
at-most-one-one-item-batch assertion. The standalone file then passed **39 / 0**
with the default local guard:
`BACKEND_PYTEST_WORKERS=1 BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-brief/r5-parakeet-retry.txt" PYTHON=.venv/bin/python bash backend/test.sh`
(`r5-parakeet-retry.log`). The entire 4/4 shard subsequently passed with unchanged
source, worker settings, assertions and guards. This demonstrates a passing full
retry, not a proven root cause or a repaired Parakeet timing assumption. No
production Parakeet engine or test fixture was modified in this round.

Local metadata: `scripts/pr-preflight --suggest`, then
`scripts/pr-preflight --pr-body-file .agent-brief/pr-body-r5.md --metadata-only`
passed 4 checks. The body cites INV-MEM-4 and a Failure-Class: none rationale;
there was no external PR lookup. Registry, compose and cohost source checks also
passed after regenerating the registry with its pinned `--as-of 2026-10-02`.
The async-blocker scan reports zero selected blocking findings. `git diff --check`
passed before both runtime commits.

Full `OMI_PR_BODY_FILE=.agent-brief/pr-body-r5.md make preflight`: **46 checks
passed**, exit 0 in **196.80 seconds**, on documentation HEAD `92a2ae3154`;
`r5-preflight.log`. Includes declaration/source/cohost/image-closure admission,
invariant and failure-class metadata, query/index hermetic guards and the remaining
selected repository checks. No remote PR lookup or live cloud operation.

The first preflight attempt stopped after five passed checks at synthetic-merge
admission: the shared local origin/main ref advanced during this task, and both
branches appended unrelated prose at the pipeline document's EOF. Its receipt is
`r5-preflight-doc-conflict.log` (exit 1, 38.94 seconds). The new documentation-only
commit relocates this lane's section beside capture-window gates; it does not merge,
rebase, rewrite history or change runtime code. The complete preflight rerun above
passes against the advanced target. This lane performed no fetch or sync.

## Deployment scope and limits

Both runtime commits affect the shared server-STT listen receiver/transcript stack
and transaction planner. Ship the normal immutable backend release vector, including
Cloud Run backend/backend-sync/backend-sync-backfill and GKE backend-listen, with
pusher's image/config updated through its own authorized release path wherever it
hosts processing. The composed declarations include backend-integration and all
current cohosts. This report authorizes no deployment; every new declaration is OFF.
No Cloud Run-only change can update the receiver code served by backend-listen.

Local tests do not establish remote CI, built images, live coverage, fleet latency,
provider accuracy or acoustic identity quality. Already merged unknown transcripts
are not rewritten or recovered. Missing sentence punctuation can keep an unknown
sentence absorbing indefinitely; no guessed sentence/word split is introduced.
Successful contiguous legacy unions remain allowed by the old policy, but new
gapped unions always need proof. The strict-projection flag's pre-existing OFF
hiatus weakness is unchanged for original pieces that do not match strict proof.
Stored span validation, conversation-wide completeness gates, speaker-resolution
statuses, embedding-cache format/keys and audio storage format are untouched.
Some new windows may still be too short to embed, and any remaining unplaceable
non-Omi row can keep the conversation unavailable. Do not infer conversation-wide
speaker resolution merely from the simulation's higher field coverage.
