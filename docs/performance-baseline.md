# Performance baseline

`perf-baseline` ranked what a person feels and fixed nothing. This file now
records the re-measure of those three targets at current trunk, what was
dropped, what was left, and the one Chat hitch that still reproduced.

**Re-measured here** (felt-latency): dedicated `pageMs` for listen / folders /
home, in-app `fromClick` for listen / folders, canned-gateway Chat first-turn,
and service boot after the Chat warmup. Method: `bun scripts/performance-baseline.mjs`.

**Inherited** (not re-run): launcher skip numbers from `shell-rebuild-cost`,
and `perf-baseline`'s formation / L1–L4 wall-clock tables.

---

## Felt-latency re-measure

**Before ref:** `6a72712ba9` (`6a72712ba9550c4bd4b1a23eab76bec6d270c2b3`) on
`lane/perf-felt-latency`, tracking `origin/codex/track3-backend-integration`.
Working tree was dirty only with the measurement harness while UI and Chat
before-numbers were taken.

**After:** this commit. Frontend surfaces were not changed. Chat's first-turn
path was.

**Machine:** Apple M5 Max, Darwin 25.6.0 arm64. David's daily app stayed on
4851/8788/5290 the whole time and was not stopped. That usage is load on
these numbers. Verification leased its own ports and never bound those three.

**N = 5.** Median is the middle sample after sorting. Spread is max − min.
Units are milliseconds. Samples are listed in run order.

Re-run: `bun scripts/performance-baseline.mjs`. Scratch under `os.tmpdir()`,
never worktree `data/`. Frontend `dist/` must already exist.

---

### 1. Listen vs folders — dropped

`perf-baseline` (`fc4b3a774d`, loadavg 32.12 / 16.1 / 12.08) had Listen
dedicated landing pageMs median **251** (201–263) vs folders **52**. Suspected
cause: native preflight and capture `connecting` both collapsing into surface
`refreshing`, so the probe — and the user — waited until that lifted.

**That 5× gap does not reproduce.** `listen-polish` gave `connecting` its own
capture kind and stopped mapping transport `connecting` onto store
`refreshing`. `createPlatformProductionListenStore` reports refresh `ready`
unless the transport is `reconnecting` or `failed`. The old hypothesis is
dead. Do not inherit it.

Re-measure at `6a72712ba9`, loadavg **4.75 / 4.84 / 4.15**, David's ports
bound, N = 5, same probe (pending while `data-surface-state` is
`initial-loading` or `refreshing`). Every Listen sample landed `state=ready`.

Dedicated landing (`pageMs`):

| Route | Median | Min | Max | Spread | Samples |
|---|---:|---:|---:|---:|---|
| folders | 126 | 124 | 131 | 7 | 124, 125, 126, 126, 131 |
| listen | 177 | 173 | 182 | 9 | 173, 178, 177, 176, 182 |
| home | 128 | 104 | 132 | 28 | 132, 128, 104, 128, 132 |
| memories | 175 | 61 | 182 | 121 | 182, 178, 175, 175, 61 |
| conversations | 124 | 59 | 129 | 70 | 126, 124, 129, 123, 59 |

In-app walk (`fromClick`):

| Route | Median | Min | Max | Spread | Samples |
|---|---:|---:|---:|---:|---|
| folders | 54 | 52 | 56 | 4 | 54, 56, 54, 54, 52 |
| listen | 99 | 95 | 109 | 14 | 102, 99, 95, 109, 98 |

Listen is still ~50 ms above the ~126 ms cluster (and tied with memories),
not five times folders. Folders itself moved from a bimodal 52 (three samples
at probe grain) to a tight 126 — quieter machine, no fast-cluster grain hits
in this batch. The remaining Listen extra is first paint of a heavier route
(native preflight provider + capture client before `root.render`), not
`connecting` folded into `refreshing`. Moving schema parse or preflight to
bundle boot would tax every route. **Dropped.**

---

### 2. Chat first-turn — fixed

Against the canned gateway (`integration/local-test-gateway.mjs` on a leased
port, not 8788 and not `api.omi.me`). Clock starts at POST `/v1/chat-messages`.
**first-token** is the first SSE `event: delta`. **admission** is POST return.
Run 1 is the first turn after boot; five independent boots for first-turn
median.

`perf-baseline` had one first-turn sample: admission 127, first-token **180**,
then subsequent first-token ~53.

Re-measure before the fix, `6a72712ba9`, loadavg **4.74 / 4.92 / 4.07**,
David's ports bound:

| Clock | N | Median | Min | Max | Spread | Samples |
|---|---:|---:|---:|---:|---:|---|
| first-token, first turn after boot | 5 | 145 | 138 | 154 | 16 | 145, 150, 154, 139, 138 |
| admission, first turn | 5 | 93 | 92 | 107 | 15 | 92, 104, 107, 93, 92 |
| first-token, subsequent | 5 | 45 | 44 | 53 | 9 | 45, 44, 53, 46, 45 |

The hitch reproduced. It is ours, not a provider's.

**Named cost.** First successful POST spends ~78 ms inside
`supervisor.onAdmitted` before it returns. `admit()` itself is 0–1 ms.
`GET /v1/chat-messages`, invalid JSON POST, and validation-failing POST do
not warm it. Split inside `onAdmitted`: sync snapshot append is 1 ms; the
remainder is the first execution of `generationContext.load()` /
`readCanonicalPage` (authorized memory page). That call does not yield until
the page is built, so fire-and-forget dispatch was not fire-and-forget on a
cold process. Subsequent `load` is ~17 ms and POST no longer waits for it.

Not a lazy `import()`. The modules are already loaded at boot. It is
first-execution of the memory-context path, paid on the first user send.

**What moved.** Two changes, both in the service, neither delaying first
token:

1. `createMemoryReadChatGenerationContextSource.load` yields once before
   touching the authorized page, so POST admission matches the existing
   fire-and-forget contract.
2. Long-lived `dev-server` awaits `warmupChatGenerationContext()` **before
   it listens**. That compiles the memory-context path against the seeded
   owner without admitting a chat message. Tests do not call it.

**Trade.** Service boot now includes that warmup. Same method, N = 5,
David's ports bound.

| Kind | When | Loadavg | Median | Min | Max | Spread | Samples |
|---|---|---|---:|---:|---:|---:|---|
| Cold `/ready` | `perf-baseline` `fc4b3a774d` | 12.33 / 9.87 / 9.74 | 160 | 158 | 270 | 112 | 270, 173, 160, 158, 160 |
| Warm `/ready` | `perf-baseline` `fc4b3a774d` | 12.33 / 9.87 / 9.74 | 144 | 142 | 161 | 19 | 147, 143, 142, 144, 161 |
| Cold `/ready` | after warmup, this commit | 7.82 / 10.65 / 8.40 | 250 | 245 | 269 | 24 | 246, 245, 250, 266, 269 |
| Warm `/ready` | after warmup, this commit | 7.82 / 10.65 / 8.40 | 245 | 226 | 268 | 42 | 226, 268, 231, 245, 258 |

Boot rose by ~90 ms. The daily app is already up on 4851; that cost is paid
when the stack starts, not when David sends. First send is the felt clock.

After, same Chat method, five independent boots, loadavg 15.94 → 8.39 (David's
ports still bound; machine busier than the before-batch):

| Clock | N | Median | Min | Max | Spread | Samples |
|---|---:|---:|---:|---:|---:|---|
| first-token, first turn after boot | 5 | 81 | 74 | 96 | 22 | 82, 81, 96, 79, 74 |
| admission, first turn | 5 | 34 | 31 | 46 | 15 | 34, 37, 46, 31, 32 |
| first-token, subsequent | 5 | 45 | 43 | 62 | 19 | 43, 50, 62, 45, 45 |

First-token **145 → 81**. Admission **93 → 34**. Subsequent unchanged at ~45.
A ~35 ms first-vs-later remainder remains (first POST success-path JIT after
`load` has been warmed). Fake-admitting a message at boot to chase that would
write user-visible Chat history. Left.

---

### 3. Home waits on both spines — unchanged

`combineHomeRefreshStatuses` is still worst-of. That is the honest merged-spine
rule: Home is not entitled to say `ready` / empty-projection while either
memories or conversations is still `initial-loading` or `refreshing`. Showing
each half as it arrives would be a two-step settle and would re-open the
"nothing is saved yet" lie `homeSurfacePresentation.emptyKind` exists to
prevent, unless empty stayed gated on both halves — at which point worst-of
is back.

Re-measure at `6a72712ba9` (same UI batch as Listen): dedicated home pageMs
median **128** (104–132). Conversations 124. Memories 175. Home is not as slow
as the Memories *page*; Home's two projections become ready in the
conversations band. The ranked finding "Home is as slow as its slower half"
does not reproduce as felt slowness at this ref.

**Measured, considered, deliberately unchanged.**

---

## Inherited — launcher skip (`shell-rebuild-cost`)

Not re-run by this lane. Numbers below are copied from the previous
`docs/performance-baseline.md` at `6a72712ba9`.

`perf-baseline` measured app first-render `launcherMs` at median **27510**
(spread 30292) against `pageMs` 131. `run-shell.sh` now skips `build-shell.sh`
only when the bundle stamp `treeHash` and bundled surfaces bytes exactly match
current inputs.

Independent re-measure at after-ref `0d4a7268f4`, origin **15290**, loadavg
17.11 / 9.67 / 8.83:

| Kind | Clock | N | Median | Min | Max | Spread | Samples |
|---|---|---:|---:|---:|---:|---:|---|
| Unchanged tree, second+ launch | `run-shell.sh` to ready | 5 | 1370 | 1364 | 1374 | 10 | 1370, 1364, 1367, 1370, 1374 |
| Warm, stamp deleted (still rebuilds) | `run-shell.sh` to ready | 5 | 16085 | 15999 | 16412 | 413 | 16085, 15999, 16084, 16315, 16412 |

---

## How to re-run

From this repo root. Leases its own ports. Never binds 4851/5290. JSON on
stdout. Scratch under `os.tmpdir()`.

```bash
cd frontend && corepack pnpm install && corepack pnpm -r build && cd ..
bun scripts/performance-baseline.mjs --n 5 --only chat
bun scripts/performance-baseline.mjs --n 5 --only ui
bun scripts/performance-baseline.mjs --n 5 --only boot
```

Record loadavg, whether 4851/5290/8788 were bound, the git ref, and whether
the working tree was dirty. Compare medians and spreads, not single runs.

---

## Green gates at the after-tree

Taken on this machine. David's app held 4851/5290/8788.

| Gate | Result |
|---|---|
| `bun test` | 2358 pass, 36 skip, 0 fail, 2394 tests / 350 files, 51.46 s |
| `bun run lint:imports` | exit 0 |
| `bun run lint:closure` | exit 0 |
| `(cd frontend && pnpm -r build)` | exit 0 |

L1–L4 are run after this tree is committed so a ladder cannot see a mid-run hash change. Outcomes belong in the lane report if this section is not yet updated.
