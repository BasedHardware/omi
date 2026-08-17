# Determinism hunt — L3 / L4 / tsc, 2026-08-16

Measured so a later run can be compared, not summarized away. Raw logs and
receipt copies live outside this repo under
`/tmp/omi-determinism-hunt-platform/` (worktree `data/` is forbidden). Official
lane receipts are under the workspace `.omi/receipts/` tree-hash history.

Related: the verification ladder, defined upstream at
[`docs/verification.md`](https://github.com/Git-on-my-level/omi-platform/blob/main/docs/verification.md).
The ladder drives native shells that are not part of this vendored backend
subset, so it is defined and run upstream, not here.

## Environment

| | |
|---|---|
| Worktree | `/Volumes/Ephemeral/scratch/worktrees/omi-lane-determinism-hunt-platform` |
| Branch | `lane/determinism-hunt` |
| Campaign HEAD (frozen) | `6e0f33796e8ce998ffc4a7d798477b9df6f7e60b` |
| Campaign tree hash | `620deb4e2a89c2f843a330995b6c8427ba2e1d12` |
| After harness edits | tree hash `c73ba23c236111214919f4bda2994389f5cbf01e` |
| bun | 1.3.14 |
| ncpu | 18 |
| Host uptime at start | 14 days |

David's headed app was up for the whole hunt: **4851** (`bun`) and **5290**
(`omi-on-lo`). **8788** was not listening. That is the realistic environment,
not a contaminant. Verification leased 14851–14870 / 18788–18807 / 15290–15309
and did not kill those listeners.

Two iOS simulators were already booted with no lease (treated as someone
else's). Sequential L3s took one leased device at a time. The cap of 4 was
never hit; no named refusal.

L3 and L4 were run **sequentially** for the N=10 distribution: both
unconditionally `pnpm -r build` the same `frontend/` tree, and two of those
in parallel would confound the gate with a worktree write race. Two extra
L3+L4 pairs were then overlapped on purpose as a concurrency experiment.

## Green gates (refs actually measured)

| Gate | Result | Ref |
|---|---|---|
| `bun test` | 2356 pass, 36 skip, 0 fail, 349 files, 43.99s | after harness edits, same dirty tree as L3-after-fix |
| `bun run lint:imports` | exit 0 | same |
| `bun run lint:closure` | exit 0 | same |
| L1 `pnpm verify` | exit 0, 39.4s | frontend, after harness edits |
| L2 | PASS in 67793ms | receipt `L2-2471ce48717e50de/00001233389073402458-…` |
| L3 distribution | 12/12 pass on frozen HEAD, then 3/3 pass after the WebKit fix | tables below |
| L4 distribution | 12/12 pass on frozen HEAD | table below |

## L3 — every run

CONTROL lines were **byte-identical** across all 15 passing L3s
(sha256 prefix `78f40e648a7e`):

```
CONTROL home=ready
CONTROL chat=streamed-and-persisted
CONTROL mic=transcript-rendered
CONTROL screen=frame-rendered
CONTROL nav.*=rendered  (11 chrome routes)
CONTROL-ACCEPTANCE skips: (none)
CONTROL-ACCEPTANCE status=PASS passed=15 failed=0 skipped=0
```

Non-chat evidence-matrix semantics (memories 12/12, tasks 0/0, listen
capturing/segments:1, screen frames:0, …) were **stable** across the ten
sequential frozen-HEAD runs. Chat was not. That is Finding 1.

| run | mode | result | duration_ms | step1_ms | step2_ms | surface | macos chat:messages | notes |
|---|---|---|---|---|---|---|---|---|
| L3-seq-01 | sequential | pass | 267862 | 67963 | 199747 | 15290 | 66 | first sim boot; load 5.08 |
| L3-seq-02 | sequential | pass | 288546 | 69171 | 201472 | 15290 | 68 | overlapped full `bun test` loop; load 12.08 20.95 16.72 |
| L3-seq-03 | sequential | pass | 261304 | 56421 | 201141 | 15290 | 70 | |
| L3-seq-04 | sequential | pass | 254403 | 51464 | 199164 | 15290 | 72 | |
| L3-seq-05 | sequential | pass | 255306 | | | 15290 | 74 | |
| L3-seq-06 | sequential | pass | 255219 | | | 15290 | 76 | |
| L3-seq-07 | sequential | pass | 255905 | | | 15290 | 78 | |
| L3-seq-08 | sequential | pass | 255483 | | | 15290 | 80 | |
| L3-seq-09 | sequential | pass | 254965 | | | 15290 | 82 | |
| L3-seq-10 | sequential | pass | 256129 | | | 15290 | 84 | |
| L3-par-01 | parallel-with-L4 | pass | 263247 | | | **15291** | 26 | L4 held 15290 |
| L3-par-02 | parallel-with-L4 | pass | 274492 | | | **15291** | 28 | |
| L3-after-fix-01 | sequential | pass | 257938 | | | 15290 | **2** | tree `c73ba23c…` |
| L3-after-fix-02 | sequential | pass | 256114 | | | 15290 | **2** | iPhone Air (different sim) |
| L3-after-fix-03 | sequential | pass | 256648 | | | 15290 | **2** | iPhone 17 Pro Max |

Frozen-HEAD sequential n=10: min 254403, max 288546, median ~255694.
Drop seq-02 (the loaded outlier) and the rest sit in 254403–267862, ~13s
wide, ~255s typical. seq-02 is Finding 3 (duration), not a red run.

No lease refusals. No fail-then-pass-on-retry. Order after L4 did not change
CONTROL tokens.

## L4 — every run

CONTROL lines were **byte-identical** across all 12 passing L4s
(sha256 prefix `65d103f0375f`):

```
CONTROL mic=transcript-rendered
CONTROL conversation=row-rendered
CONTROL memory=card-rendered
CONTROL home.memory=row-rendered
CONTROL chat.memory=retrieved-and-streamed
CONTROL-ACCEPTANCE skips: (none)
CONTROL-ACCEPTANCE status=PASS passed=5 failed=0 skipped=0
```

| run | mode | result | duration_ms | load_end |
|---|---|---|---|---|
| L4-seq-01 | sequential | pass | 260522 | 10.03 10.85 10.78 (bun-test overlap) |
| L4-seq-02 | sequential | pass | 260812 | 9.90 17.28 16.28 |
| L4-seq-03 | sequential | pass | 258458 | 3.60 6.93 11.31 |
| L4-seq-04 | sequential | pass | 259004 | 4.21 5.24 8.63 |
| L4-seq-05 | sequential | pass | 259318 | 5.56 5.20 7.16 |
| L4-seq-06 | sequential | pass | 259505 | 4.41 5.05 6.37 |
| L4-seq-07 | sequential | pass | 259227 | 3.84 4.42 5.64 |
| L4-seq-08 | sequential | pass | 259269 | 4.05 4.99 5.65 |
| L4-seq-09 | sequential | pass | 259458 | 4.93 7.16 6.82 |
| L4-seq-10 | sequential | pass | 259129 | 4.78 5.60 6.24 |
| L4-par-01 | parallel-with-L3 | pass | 264508 | 6.52 6.94 6.85 |
| L4-par-02 | parallel-with-L3 | pass | 269044 | 6.16 9.23 8.34 |

Sequential n=10: min 258458, max 260812 (**2.35s** wide). Parallel pairs
were 4–10s slower. No red, no CONTROL disagreement, no lease refusal.

## tsc / `unit-of-work-context.test.ts`

bun's default per-test timeout is **5000ms** (`bun test --help`). The compile
test spawned `tsc` via `Bun.spawnSync` with no explicit ceiling.

| sample | n | result | wall_ms |
|---|---|---|---|
| isolated `tsc --noEmit` idle | 12 | 12 pass | 1017–1270 |
| bun test, default 5s, idle | 12 | 12 pass | 1036–1096 |
| bun test during/after L3/L4 | 10+ | all pass | 961–1251 typical; one 1399 |
| 8-way parallel tsc storm | 16 | 16 pass | 2510–2944 |
| bun test of that file during L3's first 90s | 79 | 79 pass | 1034–1399 |
| full `bun test` (349 files) overlapping L3/L4 | 12 | 12 pass, 0 timed out | 45543–52819 suite wall |

This session **did not reproduce** the 5037ms timeout. Last night's field
evidence (two unrelated lanes, same tree, isolated 3/3 pass in 1.81s) still
stands: the 5s default is a speed budget standing in for "tsc exited".
`spawnSync` already waits on that condition.

Mechanism red-proof, `/tmp` tests, bun 1.3.14, verbatim:

```
(fail) six second sleep under default budget [5000.80ms]
  ^ this test timed out after 5000ms.
 0 pass
 1 fail
Ran 1 test across 1 file. [5.03s]
default_exit=1
```

Same sleep with `test(..., 30_000)`:

```
 1 pass
 0 fail
 1 expect() calls
Ran 1 test across 1 file. [6.01s]
explicit_exit=0
```

After the per-test 30s ceiling on the real file: **20/20 pass**, wall
946–991ms (idle). Full `bun test` after the edit: 2356 pass, 0 fail.

## Findings

### 1. macOS L3 chat semantics climb on reused verification origin

**Class: test/harness defect. Fixed here.**

**Evidence.** Ten sequential passing L3s on frozen HEAD, all `surface=15290`,
macos `chat:messages` = 66,68,70,…,84. Exactly +2 messages / +1 admitted per
run. Non-chat coordinates stayed identical. CONTROL tokens stayed identical,
so the gate still passed. Parallel L3s were pushed to **15291** (L4 held
15290) and jumped to 26,28 — a different origin, a different store.

Cause, from code not guesswork:

- `dev-run-macos.sh` documents 15290–15309 as a **clean** IndexedDB origin.
- `WKWebsiteDataStore.nonPersistent()` ran only when `ephemeral` was true.
- `ephemeral` was `fixtureCapture || semanticWindow`, and `fixtureCapture` is
  `OMI_PROBE_EXIT != nil`.
- L3 step 1 (evidence) sets `OMI_CONSUMER_EVIDENCE_PATH` /
  `OMI_CONSUMER_EVIDENCE_EXIT`, **not** `OMI_PROBE_EXIT`.
- Control-acceptance (step 2) does set `OMI_PROBE_EXIT`, so it was already
  ephemeral. The persistent writer is step 1, rereading 15290 next time.

Fix: `LoopbackServer.isVerificationOrigin` (15290–15309) and
`ephemeral: … || verificationOrigin`. 5290 stays persistent.

**Observed-layer red-proof.** Same machine, same 15290, three L3s after the
edit: macos `chat:messages:2` / `admitted:1` on every run. Not 86,88,90.
CONTROL still PASS passed=15. What still fails if the guard is dropped: the
glass-host source assertion on `verificationOrigin`, and the next sequential
L3s will start climbing again.

### 2. bun default 5s timeout on the in-suite `tsc` compile test

**Class: test/harness defect. Fixed here.**

**Evidence.** Field: ~5037ms timeout in `unit-of-work-context.test.ts` during
two other lanes last night; isolated 3/3 pass in 1.81s on the same tree.
This session: 0/79+ timeouts, but 8-way tsc contention moved the same test
from ~1.05s to ~2.9s — the budget is load-sensitive, the condition is "tsc
exited". Mechanism red-proof is the 6s sleep above.

Fix: per-test hung ceiling `30_000` on that test only. Not a longer sleep
inside the test; `spawnSync` already waits. Not `--timeout` on the whole
suite. Not `skipLibCheck`. After: 20/20 on the file, full suite 0 fail.

### 3. L3 duration outlier under concurrent `bun test`

**Class: environmental. Reported, not fixed.**

L3-seq-02 took 288546ms (~33s above the 255s cluster) while a 12-deep
`bun test` loop drove load to 67. Step times only grew ~3s; the rest was
pre-step (simulator / build). The run still passed. A gate that usually
takes 255s and occasionally 289s is not yet a timeout, but it is the same
shape. No harness sleep was lengthened to hide it.

### 4. iOS chat counts vary across passing L3s

**Class: environmental / origin invariant. Not fixed.**

iOS origin is frozen at `omi-ui://local` (ADR-009). Sequential L3s reused
leased simulators and iOS `chat:messages` moved 34 → 4 (different device) →
42,46,…70, then after the macOS fix 78 / 12 / 82 depending on which
simulator was leased. CONTROL still passed. Changing that origin would move
a ratified wire. A later hunt that wants comparable iOS chat semantics needs
a per-run data store **without** unfreezing the scheme, which this lane did
not invent.

### 5. Concurrent L3+L4 on one worktree

**Class: COULD NOT DETERMINE whether the shared `pnpm -r build` is safe.**

Two overlapped L3+L4 pairs both passed (L3 263s/274s, L4 265s/269s). N=2
does not prove the race absent. Sequential remains the honest way to
measure the gates. Exceeding the simulator cap was not exercised; L4 does
not take a simulator lease.

## Ranked product bugs not fixed

None. Every disagreement that had a cause was harness or environment. The
valuable intermittent-product-bug outcome of this lane did not appear in
n=12+12 plus three post-fix L3s.

tasks:visible:0 and screen:frames:0 on the evidence matrix were **stable**,
so they are not this hunt. CONTROL `screen=frame-rendered` still comes from
step 2.

## GUARD CHANGED

- `apps/service/stores/unit-of-work-context.test.ts` — per-test timeout
  30000. A 6s sleep still fails under bun's default 5000. A hung tsc still
  fails at 30s. L3 CONTROL assertions were not touched.
- `frontend/shells/macos/tests/glass-host.test.mjs` — now requires
  `verificationOrigin` on `ephemeral`. Dropping that flag fails this test.
  5290 remains persistent (`isVerificationOrigin(5290)` is false).

## What was not done

- No retries around races.
- No assertion loosened so a flake would pass.
- No `data/` in this worktree.
- No push, no rebase, no `bin/omi-lane finish`.
- No request to `api.omi.me`.
