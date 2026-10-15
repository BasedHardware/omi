# Round 4: strictly additive speaker clip recovery

Worktree: `/Volumes/Ephemeral/scratch/worktrees/omi/omi-lane-capture-window-coverage-upstream-keep-clean`.
Starting HEAD: `cec8675d35466e23dab25744e73833220ffffc0b`.
Implementation/test HEAD: `8e3a115afc`; runtime source last changed at `b2abb8c9d3`.
Read the workspace/root/backend guides, all three supplied prompts, round 3 report and independent `review-r2.md` before changing the policy. Used only pinned local refs; no fetch/sync was needed for the prescribed HEAD. New commits only. No push, PR publication, deployment, production data, cloud/API access, guard relaxation, padding, interpolation or cache invalidation.

## Local commits

- `8f472c2c65` — preserve exact base midpoint evidence before attempting adjacent-chunk recovery; add inward half-open sample cuts with an operand-ULP roundoff bound and a shared integer 240,000-sample assembly budget. Update the owning pipeline description and earlier tests that had expected replacement evidence. Add 303 round 4 cases.
- `b2abb8c9d3` — pass the narrowed, nonoptional read session into the nested cache iterator. The initial shard attempt found three pyright optional-member errors; this fixes the type boundary without suppressions or changing clip selection.
- `75f99c74e7` — repair an existing shutdown-tail test precondition: wait for the receiver capture position to include both queued tail packets before disconnecting. The prior wait could observe the prefix writer still in flight, so it disconnected before accepting either tail packet. All drain/final-transcript/ordering assertions stay intact; no serving code or timeout/guard change.
- `8e3a115afc` — reuse the stack fixture's existing explicit-release socket instead of an idle-time disconnect, and repair the declaration fixture parsing seams: safe C YAML parsing for validator calls and the renderer's actual function globals for its parsed-manifest cache. All assertions and guards stay intact.
- Report commit follows these four commits; its hash is visible in the local Git log.

Runtime scope is the shared conversation speaker stage on backend/backend-sync (including current cohosts), listen and pusher wherever processing runs. No configuration change or enablement. Strict projection, capture retention/preservation, reasons/logs, public shapes, status values, PCM/storage format, CACHE_FORMAT_VERSION=1 and bare/span key construction are untouched. AUDIO_TIMELINE_V2 stays false; the three capture flags retain their previous false declarations. Consumer OFF retains exact legacy midpoint clips.

## Additive-policy proof (R2.1 and R2.2)

The ON path first scans the invocation's already admitted decoded cache in the exact base iterator's start order. Its wanted predicate and bisected midpoint ranges match `0a435947a9`, including batch interactions on tolerated overlapping inventories. Each selected segment uses the same intersection, same middle-15-second reduction and same `trim_pcm16` call as base. A base clip with at least 16,000 verified PCM16 samples is yielded unchanged, and its segment ID is marked before the diarizer call. Neither successful embedding nor diarizer failure permits substituting assembly for that embeddable clip. Existing embedding order and budgets are retained before any recovery work.

Only IDs without an embeddable base clip enter recovery. Recovery reads the same invocation cache; it cannot list, fetch or read other generations. It accepts only adjacent actual extents, refusing internal gaps beyond the existing 1 microsecond wall-axis roundoff allowance. At most 1 ms missing outer edges can trim to actual PCM. There is no synthetic audio.

Mechanical proof is stronger than a constant-vector replay:

- 192 seeded randomized real-stage replays (64 grids times sync/v2/live), with 1–6 chunks, 2–22-second chunk lengths, nonintegral sample grids, exact adjacency, tolerance-sized gaps, roundoff-sized gaps, fractional segment starts/ends and epoch timestamps. All 192 explicitly require a base embedding, then compare exact PCM bytes, entire encoded cache (including durations, vectors and bare/span keys), and the full resolved object. A local sample-dependent diarizer observes differing voices within and across chunks; it records the actual WAV PCM.
- 48 seeded batch replays (16 times three scopes), using real inventory admission on spanless tolerated overlaps and grids at zero/epoch origins. Three pending segments exercise the base iterator's batch-dependent selection in an overlap. Exact call order, PCM and encoded caches agree with base. Fetch and assembly are replaced by raising sentinels, proving neither is needed for these base clips. Overlapping span manifests are intentionally not admitted by the unchanged placement gate; full-stage randomized cases use otherwise placeable manifests.
- Six full-stage cache regressions: the review's `[0,1.3)` / `[1.3005,2.4)` tolerated-gap scenario and two adjacent six-second distinct voices, each in sync/v2/live. Start from base's resolved object, use its cache as a hit, then make download return no bytes. Cache hit makes no diarizer call; miss embeds the byte-identical base clip and keeps the full resolved object and encoded cache identical. In the mixed-voice scenario the concatenation would select enrolled voice 1 while base selects non-owner voice 2; the candidate keeps base's non-owner outcome.
- Three exact-base comparisons prove two adjacent 0.6-second chunks produce no base embedding but now produce one resolved embedding of original concatenated PCM in sync/v2/live. Existing three-scope regression also remains green.

This is a deterministic selection invariant plus finite randomized qualification, not a fleet voice-quality measurement. The unchanged inventory and placement gates still refuse malformed, unplaced, wrong-generation and excessively overlapping inputs before clip selection.

## Inward cuts and budget (R2.3)

Recovery uses `ceil((start-origin)*16000)` for the first sample and `floor((exclusive_end-origin)*16000)` for the end index. It snaps a near-integer offset only within an explicit bound from the ULPs of both timestamp operands and the scaled offset. This handles cancellation at epoch-sized timestamps without treating ordinary fractional starts/ends as exact grid points. Complete original sample bytes are sliced without resampling.

An integer `remaining_samples=240000` is shared across all pieces. Each piece is bounded by its decoded sample count and the remaining budget, then decrements that budget by its actual byte length divided by two. Thus joins cannot exceed 480,000 bytes even with different sample grids or tolerated overlaps. Recovered clips still require 16,000 actual samples.

Ten fractional-start/end cases cover 0, .01, .49, .5 and .99 sample offsets at zero and epoch origins. Forty mixed-grid cases cover four fractional windows, five tolerated overlaps and two origins, using real inventory admission and independent expected original-byte cuts. This includes the exact R2.3 `[.0000125,20.0000125)` with B beginning at `7.499975`; the 240,001-sample result is rejected by the cap assertion on pre-R4 and bounded after repair. Four continuity cases distinguish float-roundoff-size gaps from actual 0.5 ms gaps.

Inward recovery cuts intentionally do not rewrite an embeddable base clip's legacy nearest-rounded cuts: doing so would violate the requested exact byte/evidence/cache parity. The existing single-chunk convention remains solely for preserved base evidence and consumer OFF; assembled recovery has the new inward convention and final integer budget.

## Commands and local receipts

All backend tests ran only through `backend/test.sh` file lists or `backend/scripts/run-unit-ci.sh`. No bare pytest or ad-hoc real-client construction. Focused runs retained the default 0.30-second call-phase guard. Canonical shards retained their checked-in CI contract, guards and isolation settings.

1. Exact pre-R4 red replay, repository root:
   `OMI_CAPTURE_R4_RED=1 BACKEND_PYTEST_WORKERS=1 BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-brief/r4-tests.txt" PYTHON=.venv/bin/python bash backend/test.sh`
   — **260 failed / 43 passed**, exit 1 as expected; `r4-red-proof-final.log`. The module fixture loads exact `cec8675d35` source from local Git and redirects only the candidate clip functions to it, with local dependency proxies. Base source is exact `0a435947a9`. No ref edits. Earlier partial red runs were interrupted while pytest tried to print huge raw-PCM diffs; final assertions still compare exact bytes but report Boolean/numeric failures compactly. An initial pinned-module fixture lacked dataclass registration and produced setup errors; registration is now fixture-scoped and removed on teardown. An early randomized generator included ambiguous overlapping span manifests; those were moved to the real spanless-inventory batch tests, while every full-stage randomized case now explicitly proves a base embedding.
2. Standalone round 4 green before batch additions — **255 passed**, exit 0; `r4-tests-third.log`.
3. Full focused list, repository root:
   `BACKEND_PYTEST_WORKERS=1 BACKEND_UNIT_TEST_FILE_LIST="$PWD/.agent-brief/r4-focused.txt" PYTHON=.venv/bin/python bash backend/test.sh`
   — **913 passed / 22 files**, exit 0; `r4-focused.log`. Repeated after the typed iterator repair: same command, **913 passed / 22 files**, exit 0; `r4-focused-final.log`. After the shutdown-tail fixture repair, append `tests/unit/test_live_recovery_shutdown_tail.py` and rerun the expanded list alone: **927 passed / 23 files**, exit 0; `r4-focused-complete.log`. All 303 new cases and all 14 shutdown-tail cases ran, no timing or network guard breaches.
4. Shards, from `backend/`, executed sequentially by `.agent-brief/r4-run-shards.py`:
   `PYTHON=.venv/bin/python bash scripts/run-unit-ci.sh --all --shard 4/k`, k=1,2,3,4. CLI spelling is total/index. Initial shard 4/1 stopped at typecheck with **3 errors / 12,799 warnings**, before unit execution (`r4-shard-1-typecheck-failed.log`); the typed argument fix preceded the final focused rerun and restarted full shard run.

Shard 4/2 first reached unit execution but failed the existing shutdown-tail acceptance precondition: **5,995 passed / 1 failed / 0 skipped / 24 deselected**, exit 1 (`r4-shard-2-tail-fixture-failed.log`). After the test-only repair and expanded focused pass, shard 4/2 passed **5,996 / 0 failed / 0 skipped / 24 deselected**, exit 0 (`r4-shard-2-earlier-pass.log`). The earlier successful 4/1 receipt is retained as `r4-shard-1-earlier-pass.log`.

Shard 4/3 first failed an existing stack-fixture idle disconnect: **7,759 passed / 1 failed / 3 skipped / 712 deselected**, exit 1 (`r4-shard-3-idle-fixture-failed.log`). The fake socket could close after 50 ms without incoming frames before listen flushed accepted audio, producing `pending_upload`. Reused its existing explicit-release socket and released input only during test shutdown. No serving websocket or coverage behavior changed. The first 24-file expanded focused run passed all **942 assertions** but failed the unchanged 0.30-second CPU guard in eight existing YAML-heavy calls across two declaration files (`r4-focused-terminal.log`). Repaired their fixture parsing/cache seams; no guard/allowlist changes.

After all fixture repairs, reran the expanded focused list alone: **942 passed / 24 files**, exit 0 (`r4-focused-terminal-final.log`), with no guard breaches. All four final shards ran fresh on exact `8e3a115afc`.

| Shard | Files | Passed | Failed | Skipped | Deselected | Exit | Seconds | Receipt |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 4/1 | 396 | 7,529 | 0 | 24 | 1,319 | 0 | 370.94 | `r4-shard-1.log` |
| 4/2 | 396 | 5,996 | 0 | 0 | 24 | 0 | 325.19 | `r4-shard-2.log` |
| 4/3 | 396 | 7,760 | 0 | 3 | 712 | 0 | 296.28 | `r4-shard-3.log` |
| 4/4 | 396 | 7,608 | 0 | 0 | 37 | 0 | 276.72 | `r4-shard-4.log` |
| Total | **1,584** | **28,893** | **0** | **27** | **2,092** | | | |

Every final shard: environment preflight **17 passed / 9 optional warnings / 0 failed**, typecheck **0 errors / 12,799 warnings / 0 informations**. Independently recounted all 396 summary lines and 396 completed-file markers in each final log and compared with the JSON totals. All four commands exited 0, with no error annotations. The 27 skips and 2,092 deselections are existing suite cases/mark exclusions; all 303 new tests executed.

5. Local PR metadata, repository root:
   `scripts/pr-preflight --suggest` — exit 0; `r4-preflight-suggest.txt`.
   `scripts/pr-preflight --pr-body-file .agent-brief/pr-body-r4.md --metadata-only` — **4 passed**, exit 0; `r4-pr-body.log`. Body cites INV-MEM-4 and gives the existing Failure-Class: none declaration with a policy-specific rationale; no external PR lookup.

6. Full local preflight, repository root:
   `OMI_PR_BODY_FILE=.agent-brief/pr-body-r4.md make preflight`
   — **45 checks passed**, exit 0 in **199.31 seconds**; `r4-preflight.log`. PR metadata came from the local body file, with no external PR lookup. This includes compose, registry, source validators/cohost contracts, invariant/failure-class metadata and source/fixture guards selected by the existing local contract.

7. `git diff --check` — exit 0 before implementation commits. Final working/index status checked before report commit. `.agent-brief/r4-shard-counts.json` contains parsed terminal shard totals.

## Remaining limits

Results are local source/unit/admission evidence, not remote CI, an image build, deployment, live product acceptance or diarizer voice-quality qualification. Existing generation/content revalidation of historical cached vectors, transferred-versus-decoded memory budgeting and fleet latency limits are unchanged. Newly recoverable fragments can add diarizer calls within the existing 1,500-embedding / 45-second stage / 30-second read-session / 32-download / 64 MiB transferred-byte caps. Preservation remains OFF and unchanged. All reviewed strict projection and anonymous diagnostics/declaration contracts are retained.
