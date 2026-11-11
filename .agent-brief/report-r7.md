# Round 7: only receiver-proven known-window unions

Worktree: `/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-capture-window-coverage-upstream-keep-clean`.
Starting HEAD: `d58c5e0e6d31d7a2cf942e195c6e847c5a740ef9`.
Implementation/test/documentation commit: `d7e8d2a7a52f6e16ad6deb2beb7949906368e8df`.
New commits only; no push, PR creation, sync/fetch, deployment, flag enablement,
cloud/API access, credentials or production data. Prescribed HEAD overrides
fresh-main guidance. No forbidden-path edits or network-guard relaxation.
Read review-r5 in full, plus inherited prompt.md and prompt-r3 safety ruling.

## Contract and implementation

Removed the mixed known/unknown early-return branch from `combine_segments`,
the `_unambiguous_unknown_boundary` function, its abbreviation denylist, both
lexical row minimums and duration minimums, and the `bound_unknown_sentences`
parameter and in-tree caller. No replacement heuristic, punctuation exception,
provider-boundary assumption or row-splitting path was added. Legacy sentence
repair/formatting shared by OFF and ON remains, preserving OFF parity.

The accepted-send union implementation is unchanged. ON only recovers a capture
window that legacy merging clears when two known windows have a positive gap:
both private proofs must match their windows, share one provider epoch, and one
receiver-observed contiguous accepted-send run must cover the complete union.
Ordinary received silence is valid; two endpoints alone cannot bridge a hole.
Unknown-side merges keep legacy absorption and clearing. No text/window repair
of historical unknown data is attempted. ON introduces no row count, row text,
row order, speaker, ID or timing change. Private proof retention and attribution
support the recovered window; proof never enters public/storage/cassette bytes.

Updated the flag description and pipeline contract and regenerated the feature
flag registry. Existing default false declarations and all other rollout flags
are unchanged, including `AUDIO_TIMELINE_V2=false`.

## Real-path proof and exact OFF parity

New `test_capture_window_merge_union_r7.py`: **126 cases**.

- **90 seeded property cases**: 30 deterministic randomized streams for each of
  Modulate, Soniox and Deepgram, replayed OFF and ON. Each has 20 persistence
  ticks, including two reconnects, received pauses, failed/missing sends, wall
  hiatuses, zero/outside intervals, speaker changes, late intervals and randomized
  multi-final batches. Capt./Mt./Dra./No./Dr. appear in both unknown directions;
  the randomized vocabulary also includes initials, decimals, ellipses, URLs,
  standalone punctuation, CJK text and ordinary complete/unfinished sentences.
- Actual Modulate partial/final parser methods and Soniox interim/final token
  handling feed the real receiver -> transcript processor -> StrictFirestore
  path. Deepgram uses the real callback extracted by replacing only its connector
  with a fully local no-socket fake. Its production subscription disables
  interims; empty events exercise its no-transcript callback path. No provider
  clients or keepalive threads are constructed.
- At every tick, comparison removes only `audio_capture_start/end` and requires
  equality of the complete ordered persisted row lists. This checks every other
  field, including row IDs, row counts, exact text, speaker/scope and timestamps:
  **1,800 paired persistence snapshots**, **3,600 actual ticks**. Each stream
  must also recover at least one window, avoiding a vacuous flag-disabled pass.
  Any difference must be OFF absent -> ON present, and a single real receiver
  proof already observed by that tick must cover the whole window; future or
  stitched proof snapshots cannot satisfy the assertion.
- **36 mixed-window regressions**: reviewer titles plus ordinary sentence
  punctuation, all three providers and both unknown directions. Complete stored
  payloads must be identical OFF/ON, one legacy row, unknown window.

Final new tests against exact starting runtime source: **102 failed / 24 passed /
0 errors**, exit 1; `r7-red-final.log` and `r7-red-final-result.log`. The failures
are desired parity/legacy-row assertions, not error reproductions counted as
acceptance. `.agent-brief/r7-red-final.py` temporarily loads only the two merge
source files using `git show d58c5e0e6d:<path>`, runs the authorized file-list
runner and restores candidate bytes in `finally`. Earlier pre-batch receipt:
`r7-red-head.log`, same counts. Candidate: all 126 pass under the unchanged
**0.30 s** local call-phase guard; no slow marks, skips or deselections.

Retained existing proof/refusal tests covering failed and missing sends,
VAD-disjoint sends, elapsed holes, wall hiatuses, compaction, eviction, stale
snapshot windows, runtime disable, restarts, replay receipts, half-open exclusive
anchors and reconnect epochs. Updated only tests that expected the now-retired
unknown splitting; full-sentence punctuation now asserts ordinary legacy merging.

R4.2 cassette exclusion test is unchanged: actual persisted local cassette bytes,
public JSON and Python storage-model dumps omit the private marker, epoch and
`accepted_run`; original live transport keeps its proof and subsequently stores
a received-silence positive-gap union. Capture admission remains unchanged.

Exact OFF parity: starting HEAD and candidate each **1 passed**, exit 0; decoded
stored payloads and exercised existing metric deltas are exactly equal, enforced
by the replay driver, not visual comparison. Receipts `r7-off-{head,candidate}.json`,
logs `r7-off-{head,candidate}.log`, driver `r7-off-parity.py` / `r7-off-parity.log`.
Only the two merge modules were temporarily replaced; restoration completed
before focused validation. No ref/history rewrite.

## Updated simulations: identical rows

Fresh synthetic 12-sentence/72-word stream with received silence, one unknown
callback before acceptance and two reconnects. All words pass through receiver,
ticks and storage; Soniox uses its actual token handler. Reports assert identical
ON/OFF row count, row text and row durations and preserve all 72 words.

| Provider | OFF known/all rows | ON known/all rows | OFF known/all words | ON known/all words |
| --- | ---: | ---: | ---: | ---: |
| Modulate | 0/3 | 2/3 | 0/72 | 48/72 |
| Soniox | 0/3 | 2/3 | 0/72 | 48/72 |
| Deepgram | 0/3 | 2/3 | 0/72 | 48/72 |

ON coverage is **66.7% of rows and words**, with exactly the same three 24-word,
15.3-second rows as OFF. The first unknown epoch continues absorbing; independently
proven known epochs retain their windows. Artifacts:
`r7-simulation-wordstream.<provider>.json`.

Mixed title/unknown simulation in English and Vietnamese, for all three providers:
OFF and ON both store **one row, zero known windows**, with identical text, words
and durations. This replaces R6's three-row/one-known-window shape. Unknown-side
clearing is intentional. Artifacts `r7-simulation-mixed.<provider>.<en|vi>.json`.
Exact Dr. Smith race also remains one unknown row with either flag:
`r7-simulation-title.{false,true}.json`.
These are controlled synthetic estimates, not fleet coverage or live-provider
speaker accuracy.

## Focused and full validation

All backend tests use `backend/test.sh` explicit lists or the canonical
`backend/scripts/run-unit-ci.sh` runner, with network guards enabled.

Final focused list on committed source `d7e8d2a7a5`: **1,425 passed / 31 files /
0 failed / 0 errors / 0 skipped / 0 deselected**, exit 0.
`r7-focused-final.log`, `r7-focused-result.json`, list `r7-focused.txt`.
Adds R7 to all 30 R6 files; includes R5/R6, cassette and reconnect fixtures.
Earlier pre-format full focused run also passed 1,425; `r7-focused.log`.

Commands from repository root:

```sh
python3 .agent-brief/r7-red-final.py
python3 .agent-brief/r7-off-parity.py
CAPTURE_R5_SIMULATION_OUTPUT="$PWD/.agent-brief/r7-simulation-wordstream" CAPTURE_R6_SIMULATION_OUTPUT="$PWD/.agent-brief/r7-simulation-mixed" CAPTURE_R6_TITLE_OUTPUT="$PWD/.agent-brief/r7-simulation-title" BACKEND_PYTEST_WORKERS=1 BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-brief/r7-focused.txt" PYTHON=.venv/bin/python bash backend/test.sh
```

All four canonical shards passed on the same implementation commit
`d7e8d2a7a5`, with no intervening source edits. Driver `r7-run-shards.py` ran
all four commands sequentially; `r7-shards-driver.log` records terminal exits.
Commands from `backend/`:

```sh
PYTHON=.venv/bin/python bash scripts/run-unit-ci.sh --all --shard 4/1
PYTHON=.venv/bin/python bash scripts/run-unit-ci.sh --all --shard 4/2
PYTHON=.venv/bin/python bash scripts/run-unit-ci.sh --all --shard 4/3
PYTHON=.venv/bin/python bash scripts/run-unit-ci.sh --all --shard 4/4
```

| Shard | Files | Passed | Failed | Errors | Skipped | Deselected | Exit | Seconds | Receipt |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 4/1 | 397 | 6,214 | 0 | 0 | 0 | 24 | 0 | 134.86 | `r7-shard-1.log` |
| 4/2 | 397 | 7,693 | 0 | 0 | 1 | 712 | 0 | 131.66 | `r7-shard-2.log` |
| 4/3 | 397 | 7,692 | 0 | 0 | 2 | 18 | 0 | 214.85 | `r7-shard-3.log` |
| 4/4 | 396 | 7,667 | 0 | 0 | 24 | 1,338 | 0 | 112.38 | `r7-shard-4.log` |
| Total | **1,587** | **29,266** | **0** | **0** | **27** | **2,092** | | | |

Each shard's environment preflight: **17 passed / 9 optional warnings / 0 failed**.
Each typecheck: **0 errors / 12,801 warnings / 0 informations**. The canonical
runner's worker/isolation/marker settings and 1.0 s CI guard were unchanged;
focused validation separately proves all new tests pass the local 0.30 s guard.
The full suite adds exactly 126 passing R7 tests to R6's 29,140, with unchanged
skip/deselection totals. Independent recount includes long-duration pytest
summaries with parenthesized elapsed-time annotations, matches all four driver
receipts and verifies terminal exit 0. Receipts `r7-shard-counts.json` and
`r7-all-shards-result.json`. No shard failure or retry in this round.

Local PR metadata: `scripts/pr-preflight --suggest` followed by
`scripts/pr-preflight --pr-body-file .agent-brief/pr-body-r7.md --metadata-only`:
**4 checks passed**, exit 0. Receipts `r7-pr-suggest.log`, `r7-pr-body.log`.
The local body cites INV-MEM-4, explains Failure-Class: none, and preserves the
existing six-line receiver diagnostic-copy line-count exception. No remote PR
lookup was performed.

Full `OMI_PR_BODY_FILE=.agent-brief/pr-body-r7.md make preflight`:
**46 checks passed**, exit 0, on `d7e8d2a7a5`; **101.00 s** wrapper wall time,
100.77 s reported by the CLI. `r7-run-preflight.py` supplies the absolute local
body path and records the tested HEAD/exit/time in `r7-preflight-result.json`;
`r7-preflight.log` and `r7-preflight-driver.log` retain terminal output. Independently
counted all 46 PASS records. Includes synthetic-merge admission, local metadata,
compose/flag-registry/cohost contracts, source closure, import purity, async
blockers, Firestore query/index guards and other selected repository checks.
Diff whitespace and final implementation worktree status were clean. Report-only
commit follows validation; implementation bytes remain unchanged and that
commit's hash is available in local Git history.

## Scope and remaining limits

No new positive-gap union may span an unreceived hole. The inherited
strict-projection-OFF endpoint fallback can still create such a legacy window
before merging, as R5 independently demonstrated. This round neither upgrades
legacy projection nor claims all existing capture windows are receiver-proven;
only the new positive-gap union requires complete strict accepted-send proof.
Proof eviction, restart or uncertain writes may reduce recovery. Unknown-side
absorption can keep an entire row unknown; coverage is intentionally sacrificed
without changing transcript segmentation.

The independent preservation flag retains its separate existing contract. The
R7 property harness holds preservation and strict projection OFF to compare
against legacy behavior; neither flag is enabled or changed here.

Local source qualification is complete only at the recorded test/preflight
layer. No remote CI, image build/identity, deployed revision, live provider health
or production enablement result is asserted. Authorized release targets remain
GKE backend-listen and pusher hosts executing this shared path, plus normal backend
release cohosts (Cloud Run backend/backend-sync/backend-sync-backfill). Cloud
Run-only publication would not update GKE listen. This round publishes nothing.
