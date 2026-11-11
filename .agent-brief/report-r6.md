# Round 6: conservative unknown boundaries and private diagnostic capture

Worktree: `/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-capture-window-coverage-upstream-keep-clean`.
Starting HEAD: `7648439cb914e331fed4820cacd0aacb2b09f983`.
Initial runtime/test/documentation commit: `cf1fe2e822c2f5f315c59b3d8434ebf269b6f9b2`.
Final merge-union runtime and R6 regression commit: `928b0486c6f3d275b39b3dbbb54338bcfd41cca0`.
Additional fixture-only commit: `d28fbfddbf31096b57e413cd8b932496349f6d55`.
New commits only. No push, PR creation, fetch/sync, deployment, production reads,
cloud/API access, credentials, network-guard relaxation or forbidden-path edits.
The prescribed starting HEAD takes precedence over fresh-main/sync guidance.

## Findings repaired

**R4.1 (P2).** A mixed known/unknown pair now stays separate only when:

- The existing chronological continuation guard accepts it.
- Both pieces already contain at least two whitespace-delimited words containing
  letters or digits and span at least one second. Standalone punctuation does
  not count as a word. The rule never assumes future callback continuation.
- The preceding token ends in supported terminal punctuation and its remaining
  body consists of at least two letters, is not a known abbreviation/title and
  is not an all-uppercase acronym.
- The next token starts with an uppercase character. Lowercase, uncased,
  quoted or otherwise uncertain starts abstain.

Known titles/abbreviations, initials, decimals, dotted URLs and ellipses cannot
supply this boundary. English/Spanish/Vietnamese abbreviations share a conservative
denylist; embedded punctuation/digits, short initials and uppercase acronyms are
rejected structurally. Provider callback boundaries alone carry no explicit
sentence/utterance proof here and are not treated as such. No provider API or
public/storage schema was extended.

When uncertain, legacy absorption continues and clears the window as before.
This deliberately loses some window recovery, especially with single-word
callbacks. The sentence rule cannot create a one-word or sub-second row. Existing
speaker/manual/protected-ID/replay guards retain precedence; positive-gap unions
still require matching same-epoch receiver proofs with one run covering the union.
Partial speaker sentence redistribution and unknown text remain conservative.

The reviewer's exact callback-before-send-acceptance case now stores one row,
`Lost sentence. Dr. Smith arrived.`, unknown, with both ON and OFF. Starting HEAD
ON stored `Lost sentence.`, `Dr.`, `Smith arrived.` with durations 0, 0.3, 0.8 s;
only `Dr.` had a known window. Candidate stores the five words in one 1.4 s row.
Real-path tables cover both flag states and both known/unknown directions for
English and Vietnamese (already supported in `test_stt_provider_policy.py`):
`Dr.`, `Mr.`, `e.g.`, `U.S.`, `J. R. R.`, `R.`, `AB.`, `3.5`, `3.5.`, `...`,
`wait...`, `omi.me`, `omi.me.`, `TS.`, `ThS.`, `PGS.`. Positive substantial
sentence boundaries, short left/right pieces, single words, lowercase and uncased
starts also have receiver -> transcript ticks -> StrictFirestore assertions.
`Next .`, `Next ?`, `Next ...` and `Next ！` test the provider's standalone
punctuation shape: formatting cannot turn a nominal two-token piece into an
isolated single word. These eight ON cases failed on the initial R6 commit
(**8 failed / 177 passed**) before the lexical word-count refinement;
`r6-punctuation-red.log` records that additional red proof.

**R4.2 (P3).** `_enqueue_stt_segments` passes diagnostic capture a shallow copy
of each dictionary with `_capture_merge_proof` omitted. The original dictionaries
retain their proof for live processing; the diagnostic adapter still deep-copies
its input through its existing boundary. A local cassette sink exercises actual
receiver delivery and persisted cassette bytes alongside public JSON and Python
storage-model serialization. The marker, epoch and `accepted_run` are absent;
the model demonstrably contains the proof before dumping. The test subsequently
persists a proven positive-gap union, confirming diagnostic filtering did not
remove the live proof. The dev admission gate and exporter were not changed;
this test calls only the low-level local cassette sink's `persist()`.

The pipeline document now describes both contracts. All flag declarations retain
their existing defaults: `LIVE_CAPTURE_WINDOW_MERGE_UNION=false`, retention,
preservation and strict projection false, and `AUDIO_TIMELINE_V2=false`.

Local commits:

- `cf1fe2e822` repairs both review findings, adds the real-path tables/cassette
  regression and updates the pipeline contract and simulations.
- `928b0486c6` excludes standalone punctuation from the word minimum and adds
  the extra punctuation-token regressions. This is the final serving source.
- `d28fbfddbf` freezes the reconnect test's historical main probes at the
  previously qualified main baseline `3697ab9fd0`. It changes only that fixture;
  serving source and assertions are unchanged. The live shared `origin/main`
  advanced to `93b7ac97c4` during validation and its storage module imports a
  newly added `utils.observability.sync_phases` absent from this frozen checkout.
  Comparing pinned historical modules avoids mixing arbitrary newer source with
  this checkout's dependencies. All **68** fixture tests pass locally with the
  0.30 s guard; `r6-reconnect.log` and `r6-reconnect.txt` record the standalone run.

## Proof, parity and simulations

All backend test execution used `backend/test.sh` explicit file lists or the
canonical `backend/scripts/run-unit-ci.sh` runner. Network guards stayed enabled.
Synthetic PCM, fake provider transport and StrictFirestore exercise the real
local receiver, processing and persistence path; no real client was constructed.

- Exact starting-source replay: **85 failed / 162 passed / 0 errors** across two
  files (**84 failed / 101 passed** in the 185-test R6 file; **1 failed / 61 passed**
  in the updated R5 file). `.agent-brief/r6-head-proof.py` temporarily loads only
  the two exact starting source files with `git show 7648439cb9:<path>`, invokes
  `backend/test.sh`, then restores candidate bytes in `finally`. No ref/history
  rewrite. Receipt: `r6-red-head-final.log`.
- Final focused list: **1,299 passed / 30 files / 0 failed**, exit 0. All 185
  new R6 tests and all 62 R5 tests ran with the default **0.30 s** local call-phase
  CPU guard. The updated list adds R6, the existing listen diagnostic-capture suite and the
  repaired reconnect fixture. Receipt: `r6-focused-final.log`; list: `r6-focused.txt`.
- OFF parity: starting HEAD and candidate each **1 passed**; decoded stored
  payloads and exercised existing metric deltas match exactly. Receipts:
  `r6-off-head.json`, `r6-off-candidate.json`; logs: `r6-parity-{head,candidate}.log`.
  R6 tables separately assert legacy row shape with OFF across all ambiguous cases.
- An early table attempt had eight expected-text failures because existing
  formatting attaches standalone `...` to its preceding word. The fixture's
  expected spacing was corrected; production formatting was not changed.

Commands from repository root:

```sh
python3 .agent-brief/r6-head-proof.py
CAPTURE_R5_SIMULATION_OUTPUT="$PWD/.agent-brief/r6-simulation-wordstream-final" CAPTURE_R6_SIMULATION_OUTPUT="$PWD/.agent-brief/r6-simulation-mixed-final" CAPTURE_R6_TITLE_OUTPUT="$PWD/.agent-brief/r6-simulation-title-final" BACKEND_PYTEST_WORKERS=1 BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-brief/r6-focused.txt" PYTHON=.venv/bin/python bash backend/test.sh
CAPTURE_PARITY_OUTPUT="$PWD/.agent-brief/r6-off-candidate.json" LIVE_CAPTURE_WINDOW_MERGE_UNION=false BACKEND_PYTEST_WORKERS=1 BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-brief/r5-parity.txt" PYTHON=.venv/bin/python bash backend/test.sh
```

The original twelve-sentence/72-word simulation includes two reconnects, received
silence and one callback before send acceptance. Soniox uses its actual interim/
final token handler; Modulate and Deepgram use final callback shapes. Every word
passes through receiver, ticks and storage. Fresh before/after receipts use the
same simulation against exact starting source and candidate.

| Word-stream provider | Before OFF known/all rows | Before ON known/all rows | After OFF known/all rows | After ON known/all rows | ON known words before -> after |
| --- | --- | --- | --- | --- | --- |
| Modulate | 0/3 | 4/5 | 0/3 | 2/3 | 66/72 -> 48/72 |
| Soniox | 0/3 | 4/5 | 0/3 | 2/3 | 66/72 -> 48/72 |
| Deepgram | 0/3 | 4/5 | 0/3 | 2/3 | 66/72 -> 48/72 |

ON row coverage falls from 80% to 66.7%, word coverage from 91.7% to 66.7%.
OFF retains 0% coverage with identical row text before/after. All candidate rows
in this simulation span 15.3 s and contain 24 words. The unknown first epoch
continues absorbing; later independently proven epochs retain their windows.

A new four-utterance simulation mixes an unknown title-bearing prefix, a known
title continuation, a clear known sentence and a later unknown sentence. The
title's continuation remains in the same row after the repair, while clear
substantial sentence boundaries can still recover a window.

| Mixed-language simulation (each of 3 providers) | Before OFF known/all rows | Before ON known/all rows | After OFF known/all rows | After ON known/all rows | ON known words before -> after |
| --- | --- | --- | --- | --- | --- |
| English | 0/1 | 1/3 | 0/1 | 1/3 | 7/14 -> 4/14 |
| Vietnamese | 0/1 | 1/3 | 0/1 | 1/3 | 8/16 -> 4/16 |

Candidate ON rows span 3.4, 1.5 and 1.5 s. English rows are
`We met Dr. Smith arrived today.`, `We have clear audio.`, `This audio was lost.`;
only the middle row is known. Vietnamese has the corresponding `TS.` case.
All words survive; both ON/OFF are recorded. The exact `Dr. Smith` word race has
its own before/after OFF/ON receipts showing **3 -> 1 ON rows** and **1 -> 0 ON
known windows**, removing the unsafe 0.3 s title row.

Artifacts: `r6-before-wordstream.{modulate,soniox,deepgram}.json`,
`r6-simulation-wordstream-final.{modulate,soniox,deepgram}.json`,
`r6-{before-mixed,simulation-mixed-final}.<provider>.{en,vi}.json`,
`r6-{before-title,simulation-title-final}.{false,true}.json`.
These are controlled synthetic estimates, not fleet coverage or speaker-identity
accuracy. Row/window coverage is reported separately from acoustic placement and
conversation-wide speaker resolution.

## Full validation

All four canonical shards pass with the final serving source from `928b0486c6`.
Shards 4/1–4/3 ran on that commit. Shard 4/4 passed on `d28fbfddbf`, whose sole
change is the historical reconnect fixture selected only by 4/4. No other test
imports that fixture, no selected file was added/removed, and the serving Python
tree is byte-identical. The passing 1–3 results cover unchanged inputs after the
isolated fixture repair.

Commands from `backend/`:

```sh
PYTHON=.venv/bin/python bash scripts/run-unit-ci.sh --all --shard 4/1
PYTHON=.venv/bin/python bash scripts/run-unit-ci.sh --all --shard 4/2
PYTHON=.venv/bin/python bash scripts/run-unit-ci.sh --all --shard 4/3
PYTHON=.venv/bin/python bash scripts/run-unit-ci.sh --all --shard 4/4
```

`.agent-brief/r6-run-shards.py` ran the four commands sequentially, then its
`4` resume reran only 4/4 after the fixture repair. The CLI uses TOTAL/INDEX.

| Shard | Files | Passed | Failed | Errors | Skipped | Deselected | Exit | Seconds | Receipt |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 4/1 | 397 | 7,849 | 0 | 0 | 1 | 712 | 0 | 267.03 | `r6-shard-1.log` |
| 4/2 | 397 | 7,440 | 0 | 0 | 0 | 18 | 0 | 253.33 | `r6-shard-2.log` |
| 4/3 | 396 | 7,625 | 0 | 0 | 26 | 1,319 | 0 | 248.88 | `r6-shard-3.log` |
| 4/4 | 396 | 6,226 | 0 | 0 | 0 | 43 | 0 | 150.63 | `r6-shard-4.log` |
| Total | **1,586** | **29,140** | **0** | **0** | **27** | **2,092** | | | |

Every final shard's environment preflight: **17 passed / 9 optional warnings /
0 failed**. Typecheck: **0 errors / 12,801 warnings / 0 informations**. The
canonical runner's checked-in 1.0 s CI guard, isolation and worker settings were
unchanged; the separate full focused run establishes all new tests also meet
the stricter default 0.30 s local guard. All 185 R6 tests ran, without marking
them slow, deselecting them or altering guards. Existing skips/deselections remain.
Independently recounted terminal summaries against `r6-shard-counts.json`, checked
selected-file totals and verified no final failed/error annotations.

Superseded attempts are retained separately:

- Initial R6 serving commit: 4/1 and 4/2 passed; 4/3's test processes completed,
  but I rotated its still-open log too early. The driver then exited 1 on reading
  the moved path. This was an orchestration error, not a four-shard pass or a
  unit-test failure. `r6-initial-shards-driver.log` and `r6-initial-shard-*.log`
  preserve it. The lexical word-count repair preceded the fresh run above.
- First 4/4 on the final serving commit: **6,214 passed / 12 setup errors /
  0 failed / 0 skipped / 43 deselected**, exit 1, 291.54 s. The moving main
  fixture imported the absent `sync_phases` dependency. Pinning the historical
  main snapshot repaired the fixture, without adding a production stub,
  skipping assertions, or changing guards. `r6-shard-4-setup-failed.log` and
  `r6-shards-setup-failed-driver.log` preserve the failure. Standalone fixture
  validation and the full 4/4 retry both pass.

Local metadata: `scripts/pr-preflight --suggest` followed by
`scripts/pr-preflight --pr-body-file .agent-brief/pr-body-r6.md --metadata-only`.
The terminal check passed **4 checks**, exit 0, against the advanced local main
ref (`r6-pr-body-current.log`). The body cites INV-MEM-4, explains Failure-Class:
none, and records the exact permitted receiver line-count exception for the
synthetic merged view, `2426 -> 2432`, to keep the six-line diagnostic filter
at its existing receiver boundary. An initial metadata attempt caught that
missing declaration (`r6-pr-body-initial-failed.log`); no ratchet was disabled.
No remote PR lookup was used. The async-blocker scan has zero selected findings;
`r6-async-blockers.log`. Diff whitespace checks pass.

Full `OMI_PR_BODY_FILE=.agent-brief/pr-body-r6.md make preflight`: **46 checks
passed**, exit 0, on `d28fbfddbf` (**94.21 s** wrapper wall time; the CLI reports
94.06 s). `.agent-brief/r6-run-preflight.py` invokes exactly that command with
the absolute local body path and records the tested HEAD, exit and elapsed time
in `r6-preflight-result.json`; `r6-preflight.log` contains all check results.
Includes synthetic-merge admission, metadata, compose/registry/cohost source
contracts, image source closure, import purity, query/index guards and remaining
selected repository checks. No remote PR, live cloud, image build or deployment
result is claimed. Report-only commit follows; its hash is in local Git history.

## Deployment scope and remaining limits

These runtime changes affect the shared server-STT receiver/merge path. An authorized
release must update the backend image served by GKE backend-listen and any pusher
host executing this path, plus the normal backend release cohosts (Cloud Run
backend/backend-sync/backend-sync-backfill). Cloud Run-only publication cannot
update GKE listen code. This round performs no deployment or flag enablement.

Local qualification addresses both R4 findings. It does not prove live provider
accuracy, rollout health, remote CI, image identity or conversation-wide resolution.
The conservative predicate intentionally rejects uncertain/uncased/short pieces
and may leave sticky unknown text absorbing for a whole epoch. It neither guesses
future boundaries nor rewrites historical unknown transcripts. The pre-existing
strict-projection-OFF hiatus weakness remains unchanged; new positive-gap unions
still cannot bridge it without matching strict receiver proof. Stored audio
validation, public APIs, resolution statuses and embedding cache formats remain
unchanged. These limits are distinct from the repaired ON-specific row defect.
