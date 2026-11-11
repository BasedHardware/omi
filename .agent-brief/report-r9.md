# Round 9: exclusive send-map ends

Branch `lane/capture-window-translator`, prescribed Ephemeral worktree.
Started at `a091158c90000e89d1c138d055fbf019f4376c3b`; retained the supplied
`origin/main` `cb319aff0f73f39d218553d0050c5c01fb5bfb1e`, with no fetch or sync.
Read `.agent-brief/review-r7.md` and inherited safety rules before changing code.
All execution is offline, through explicit `backend/test.sh` file lists or the
canonical unit runner, with the network guard intact. No cloud/API/data or
credential access, push, remote PR, deployment, flag enablement or forbidden-path
edit. No new flag: the mapper correctness repair is unconditional as requested.

## Root cause and fix

`map_sample` correctly uses inclusive point ownership: a compact boundary names
the NEXT span's first sample. `map_interval` incorrectly used that operation for
its exclusive end, while stopping its capture-adjacency scan before the span
starting at that same end. Thus `[0.2,1.0)` on provider sends at capture `[0,1)`
and `[2,3)` became capture `[0.2,2.0)`, including unsent `[1,2)`.
Provider-axis coverage and continuous receiver wall time did not detect this.

The mapper now locates the last included provider sample, `end - 1`. If that
sample's accepted span ends exactly at `end`, the exclusive capture end comes
from THAT span. Other endpoint mapping retains the existing tolerance policy.
The existing contributing-span scan additionally requires provider adjacency;
it already requires capture adjacency. Together, accepted windows comprise one
ordered, contiguous run of exactly the sends represented by the provider
interval, without an internal capture gap, duplicated capture samples, reordered
samples or provider-axis hole. Crossing those discontinuities refuses placement.
A boundary BEFORE a later discontinuity uses only the preceding send.

The point API, zero-duration semantics, start-boundary conservatism, outer edge
tolerance, minimal-tail recovery and retention limits remain as before. This is
one extra logarithmic endpoint lookup plus the existing linear span scan; no
additional retained state. Both word-range and segment mapping share this fix.
Provider selection, pacing, finalize behavior, public/storage schemas, audio
format and rollout settings are unchanged. `LIVE_CAPTURE_WINDOW_TRANSLATOR_SENDS`
is false in all declarations; `AUDIO_TIMELINE_V2` is false in prod Helm values.
Live state was not read. An inherited R8 reporting mismatch was found during
verification: the two dev Helm values already declare `AUDIO_TIMELINE_V2=true`
at supplied HEAD `a091158c90` (listen line 562, pusher line 190). Thus R8's
claim that it was false in every deployment declaration was inaccurate. No
flag declaration was changed or enabled in R9; the supplied baseline is retained.

## OFF-path change analysis

OFF no longer means mapper byte parity with the defective base. On ordinary
compact sends, provider spans are adjacent by construction. The additional
provider-adjacency comparison therefore cannot change their result. Start
mapping, the scanned capture spans and all non-boundary end mapping are unchanged.
The only possible difference is an EXACT exclusive end at a compact boundary
whose following capture span starts somewhere other than the preceding capture
end. Contiguous capture sends coalesce and map identically.

For positive accepted base windows that previously stretched across a forward
capture gap, the corrected end is shorter and equals the end of the actual
preceding send. Cross-gap intervals still refuse. A duplicate/reordered next
span can instead make the old boundary endpoint collapse, reverse, or land
inside an earlier part of the prefix: some previously refused prefix intervals
become provable. A partially overlapping next send can also make a defective
positive base window too short; its correction lengthens back to the proper
preceding-send end (directed test: sends capture `[0,10)` then `[5,15)`,
provider `[2,10)` changes from incorrect `[2,5)` to correct `[2,10)`).
This is an additional exact-boundary case beyond the prompt's forward-gap
example; it does not change a previously correct accepted window. The fix is
about ownership, so the next span need not be a forward gap.

An independent sample-enumeration oracle checks the actual capture sample for
EVERY provider sample in a window. A candidate acceptance must equal that
ordered contiguous sample sequence. Every correct accepted base window must be
identical in the candidate. For compact maps, the endpoint argument above proves
why a correct base window cannot change: at a differing boundary the base end
already differs from the last contributed sample plus one.

The randomized property test uses 24 deterministic seeds, 384 maps, and exhausts
all positive integer windows in each map. Each map contains contiguous sends,
VAD gaps, replay duplicates and capture reorders in a shuffled order, with random
lengths/positions. Frozen base logic comes directly from supplied HEAD's method;
CI needs no historical Git object. It uses unchanged point lookup/ledger methods.
`r9-pinned-source-proof.json` verifies the frozen method's AST is exactly the
supplied base method and all five R7 pinned-main modules equal `git show` bytes.
There is no candidate source-string assertion. Results (`r9-property-result.json`):

- **125,996** base/candidate/oracle comparisons.
- **28,132** previously correct accepted base windows, all identical.
- **119,603** unchanged outcomes overall.
- **6,393** changed windows, all exact ends at discontinuous compact boundaries.
- **2,042** defective positive base windows corrected to shorter windows.
- **4,351** defective base refusals corrected to provable prefix windows.
- **0** candidate windows accepted contrary to the sample oracle; **0** correct
  accepted base windows changed. Crossing discontinuities remains refused.

These counts describe a constructed test population, not fleet frequency.
The finite randomized evidence supports the construction argument; it is not a
claim to have exhaustively enumerated all maps or tested production.

Noncompact elapsed maps get one additional refusal class: an interval spanning
a provider-axis hole with adjacent capture spans used to be accepted without
provider coverage. It now refuses. A directed test proves this separately.
An exact end at the preceding accepted span before that hole is now provable.
These are invalid old coverage proofs, distinct from ordinary compact OFF sends;
no elapsed axis is selected or promoted.

## P3 counting unit

The owning pipeline doc and historical R8 report now say **outside-send rejected
segment translations**. A callback with N outside-send refused segments increments
N times; retries recount. Persisted rows/IDs have an independent population.
No metric code, label, name or increment behavior changed.

## Real-path proof and R7 reruns

`test_capture_window_exclusive_end_r9.py` drives the actual Soniox token,
Deepgram callback, Modulate utterance and Parakeet materializer parsers, then the
actual receiver callback, transcript tick and StrictFirestore persistence.
The paced pump and legacy rebuild each exercise gapped, duplicated and reordered
prefix sends with both exact-end and crossing finals, flag ON and OFF. A known
exact prefix must persist its precise start AND end (absolute one-sample tolerance,
`rel=0`); mere refusal is not accepted as a successful repaired prefix.

The reviewer's exact capture `[0,3)`, sends `[0,1)` then `[2,3)`, provider final
`[0.2,1.0)` repro passes all four providers through both recovery paths ON:
capture `[0.2,1.0)`. OFF still has no raw replacement prefix registration and
keeps those raw prefix rows unknown, as before. Ordinary gated sends exercise
real `GatedSTTSocket` accounting and a deterministic local VAD decision that
withholds `[1,2)`. The same final is now correctly short with the new flag OFF
AND ON, for all four providers. Non-boundary controls and crossing refusals also
persist through the real path. No test claims a remote provider connection or
live service acceptance.

Base-red temporarily loads only the exact supplied base `audio_timeline.py`,
runs the final two-file list via `backend/test.sh`, and restores candidate bytes
in `finally`; restoration/hash receipt is `r9-final-red-proof.json`.
**61 failed, 96 passed**, with no collection/infrastructure error: 29 helper/
property tests and 32 real-path cases fail on base (24 ON exact replay cases,
eight ordinary gated exact-boundary cases across both flag states).
Candidate: **157 passed** (29 mapper/property + 128 real-path), no guard relaxation.
Final logs: `r9-base-red-final.log`, `r9-new-final.log`.

The R7 probes were rerun using their original lists:

- `review7-files.txt`: **118 passed** (112 R8 + six attribution).
- `review7-repro-files.txt`: **16 passed**; the old review allows either unknown
  or correct prefix ON, while the new shipped regression above requires correct.
- `review7-recovery-files.txt` with `LIVE_CAPTURE_WINDOW_TRANSLATOR_SENDS=true`:
  **211 passed, 16 failed, three deselected**, identical fixture-only matrix
  failures reported in R7. Its initial capture ends at wall 1000, but tail arrival
  is wall 1000 + duration, producing a real positive wall hiatus. Strict repaired
  epochs refuse this geometry. No production guard or existing test was changed.
- R7's scratch continuous-timing matrix (`review7-matrix-files.txt`,
  `PYTEST_ADDOPTS='-k test_directed_recovery_matrix'`, flag ON): **30 passed,
  70 deselected**. Only that inherited scratch fixture changes tail timing.
- Pinned-main and candidate OFF parity each: **55 passed, 57 deselected**, plus
  **one passed** old parity file. All 16 decoded provider/phase/replay-mode
  persistence/metric receipts and three prior payloads remain exactly equal
  (new sibling counter excluded), `r9-parity-result.json`. These unchanged
  fixtures do not contain the newly fixed ordinary exact-boundary defect.

`r9-probes.py`, `r9-probes-results.json`, `r9-review7-*.log`,
`r9-{main,candidate}-off.log` and per-case JSON receipts preserve the commands
and outcomes. Earlier test-only red/green runs are retained with their smaller
case counts; the final proof above includes actual reordered-prefix cases.

## Final validation

Validation is pinned to behavior/test/doc commit
`a19ae2889ca627752f38538a24057eb14920a5b4`.
The sequential runner verifies HEAD and source SHA256 before each command.
`r9-validation-results.json` and `r9-validation-driver.log` are the authoritative
terminal receipts. The report-only commit follows validation.

Focused **42-file** list: **2,010 passed, three deselected, zero failures/errors/skips**, exit 0, 15.92 seconds:

```sh
BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-brief/r9-focused.txt" PYTHON=.venv/bin/python bash backend/test.sh
```

All four canonical commands ran sequentially from `backend/`:

```sh
PYTHON=.venv/bin/python bash scripts/run-unit-ci.sh --all --shard 4/1
PYTHON=.venv/bin/python bash scripts/run-unit-ci.sh --all --shard 4/2
PYTHON=.venv/bin/python bash scripts/run-unit-ci.sh --all --shard 4/3
PYTHON=.venv/bin/python bash scripts/run-unit-ci.sh --all --shard 4/4
```

| Shard | Files | Passed | Failed/errors | Skipped | Deselected | Exit | Seconds |
|---|---:|---:|---:|---:|---:|---:|---:|
| 4/1 | 400 | 6962 | 0/0 | 1 | 636 | 0 | 112.96 |
| 4/2 | 400 | 7727 | 0/0 | 1 | 89 | 0 | 196.72 |
| 4/3 | 399 | 7674 | 0/0 | 6 | 1273 | 0 | 138.23 |
| 4/4 | 399 | 7418 | 0/0 | 19 | 94 | 0 | 197.76 |

Total: **29,781 passed, 27 skipped, 2,092 deselected, zero failures/errors**.
The 1,598 selected test files run exactly once across the four shards; independent
file-group/count recount is `r9-all-shards-result.json`. Each typecheck reports
**zero errors**, 12,909 existing warnings, zero information. Each canonical
runner includes dependency preflight and typecheck; no timing/selection/network
guard was bypassed. Logs: `r9-focused.log`, `r9-shard-{1,2,3,4}.log`.

After all shards terminated, standalone preflight ran from the worktree root:

```sh
OMI_PR_BODY_FILE="$PWD/.agent-brief/pr-body-r9.md" make preflight
```

**45 checks passed**, exit 0, 155.88 seconds wall time
(155.59 seconds reported by the checks runner). `scripts/pr-preflight --suggest`
and `scripts/pr-preflight --pr-body-file .agent-brief/pr-body-r9.md` preceded it;
the draft validation also passed 45 checks. The draft includes `INV-MEM-4`,
`Failure-Class: FC-transcript-and-audio-on-independent-clocks`, and the existing
narrow R8 receiver line-count exception. Final preflight uses the corrected draft
that describes the inherited dev flag declarations accurately.
Receipts: `r9-pr-suggest.log`, `r9-pr-validation.log`, `r9-preflight.log`.

`r9-validation-results.json` records hashes of the mapper, owning doc and both
new test files. The final report commit changes none of these bytes.


## Local commits and delivery boundary

- `361c96489c`: P3 metric documentation and historical report correction.
- `a19ae2889c`: unconditional shared mapper fix, owning doc contract and reusable
  randomized/real-path regressions.
- Subsequent report-only commit: this R9 handoff; validated source stays identical.

The shared mapper executes wherever `utils.audio_timeline` is used, primarily
backend listen. Shipping still requires a normal backend image release through
the existing workflow. This task publishes no image, pushes no branch and changes
no runtime flag. No remote CI, deployment, canary, fleet-rate estimate or production
acceptance is claimed. R7's known ON-only wall-hiatus fixture remains a reported
limitation of that diagnostic list, not a failure in the canonical OFF shards.
