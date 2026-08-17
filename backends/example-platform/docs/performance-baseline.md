# Performance baseline

`perf-baseline` ranked what a person feels and fixed nothing. This file now
records the re-measure of those three targets at current trunk, what was
dropped, what was left, and the one Chat hitch that still reproduced.

**Re-measured here** (felt-latency, this confirmation pass): dedicated
`pageMs` for listen / folders / home / memories / conversations, in-app
`fromClick` for listen / folders, canned-gateway Chat first-turn (five
independent boots before and after), and service boot with the Chat warmup.
Method: `bun scripts/performance-baseline.mjs`.

**Inherited** (not re-run): launcher skip numbers from `shell-rebuild-cost`,
and `perf-baseline`'s formation / L1–L4 wall-clock tables.

---

## Felt-latency re-measure

**After ref:** `ed2e2fee3c` (`ed2e2fee3c1acd25ab374bf33e44850a441e4e85`) on
`lane/perf-felt-latency`, tracking `origin/codex/track3-backend-integration`
at `6a72712ba9`. Frontend surfaces were not changed. Chat's first-turn path
was (yield before the authorized page read; long-lived `dev-server` warms
that path before it listens).

**Chat before** used the three Chat runtime files from `6a72712ba9` checked
out over that after-tree (dirty=true, disclosed on each boot). UI and boot
were taken on the clean after-tree.

**Machine:** Apple M5 Max, Darwin 25.6.0 arm64. David's daily app stayed on
4851/8788/5290 the whole time and was not stopped. A sibling lane
(`lying-state-sweep`) was also leasing control-acceptance ports. A stuck
`flutterfire` dartvm at ~99% CPU has been on the machine since Monday. All
of that is load on these numbers. Verification leased its own ports and
never bound 4851/5290/8788.

**N = 5.** Median is the middle sample after sorting. Spread is max − min.
Units are milliseconds. Samples are listed in run order.

Re-run: `bun scripts/performance-baseline.mjs`. Scratch under `os.tmpdir()`,
never worktree `data/`. Frontend `dist/` must already exist. Chat first-turn
median needs five independent process boots (`--only chat` five times); one
invocation's run 1 is a single first turn.

A quieter pass in this worktree (loadavg ~4.7) saw the same three verdicts
and Chat first-token 145 → 81. This file's tables are the confirmation pass
under the load above.

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

Confirmation at `ed2e2fee3c`, loadavg **15.22 / 41.23 / 32.14**, David's
ports bound, N = 5, same probe (pending while `data-surface-state` is
`initial-loading` or `refreshing`). Every Listen sample landed `state=ready`.

Dedicated landing (`pageMs`):

| Route | Median | Min | Max | Spread | Samples |
|---|---:|---:|---:|---:|---|
| folders | 133 | 132 | 137 | 5 | 133, 134, 133, 137, 132 |
| listen | 190 | 156 | 196 | 40 | 196, 196, 190, 156, 186 |
| home | 133 | 131 | 144 | 13 | 131, 144, 133, 132, 142 |
| memories | 187 | 183 | 202 | 19 | 185, 193, 187, 183, 202 |
| conversations | 130 | 107 | 144 | 37 | 130, 127, 134, 107, 144 |

In-app walk (`fromClick`):

| Route | Median | Min | Max | Spread | Samples |
|---|---:|---:|---:|---:|---|
| folders | 54 | 53 | 54 | 1 | 53, 54, 53, 54, 54 |
| listen | 104 | 94 | 110 | 16 | 104, 110, 94, 96, 104 |

Listen is ~1.4× folders on dedicated landing (190 vs 133) and ~1.9× on
in-app click (104 vs 54), not five times. The remaining Listen extra is
first paint of a heavier route (native preflight provider + capture client
before `root.render`), not `connecting` folded into `refreshing`. Moving
schema parse or preflight to bundle boot would tax every route. **Dropped.**

---

### 2. Chat first-turn — fixed

Against the canned gateway (`integration/local-test-gateway.mjs` on a leased
port, not 8788 and not `api.omi.me`). Clock starts at POST `/v1/chat-messages`.
**first-token** is the first SSE `event: delta`. **admission** is POST return.
Run 1 is the first turn after boot; five independent boots for first-turn
median.

`perf-baseline` had one first-turn sample: admission 127, first-token **180**,
then subsequent first-token ~53.

Confirmation before the fix (`6a72712ba9` Chat runtime files over this
after-tree), David's ports bound, dirty=true:

| Clock | N | Loadavg (boot 1) | Median | Min | Max | Spread | Samples |
|---|---:|---|---:|---:|---:|---:|---|
| first-token, first turn after boot | 5 | 16.82 / 22.66 / 25.80 | 158 | 144 | 209 | 65 | 144, 174, 158, 157, 209 |
| admission, first turn | 5 | (same batch, load 16.82 → 21.01) | 109 | 96 | 153 | 57 | 96, 121, 108, 109, 153 |
| first-token, subsequent | 20 | | 48 | 44 | 52 | 8 | 45, 44, 46, 47, 48, 48, 50, 49, 49, 45, 46, 46, 44, 51, 48, 51, 52, 50, 48, 49 |

The hitch reproduced. It is ours, not a provider's. Subsequent turns stayed
in a 44–52 ms band even while 1-minute loadavg sat in the 20s.

**Named cost.** First successful POST spends the hitch inside
`supervisor.onAdmitted` before it returns. `admit()` itself is 0–1 ms.
`GET /v1/chat-messages`, invalid JSON POST, and validation-failing POST do
not warm it. Split inside `onAdmitted`: sync snapshot append is 1 ms; the
remainder is the first execution of `generationContext.load()` /
`readCanonicalPage` (authorized memory page). That call does not yield until
the page is built, so fire-and-forget dispatch was not fire-and-forget on a
cold process.

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
| Cold `/ready` | after warmup, `ed2e2fee3c` | 25.95 / 25.06 / 26.35 | 266 | 230 | 285 | 55 | 274, 266, 285, 230, 241 |
| Warm `/ready` | after warmup, `ed2e2fee3c` | 25.95 / 25.06 / 26.35 | 255 | 231 | 264 | 33 | 255, 257, 245, 264, 231 |

Boot is ~100 ms above the pre-warmup `perf-baseline` cold median. The daily
app is already up on 4851; that cost is paid when the stack starts, not when
David sends. First send is the felt clock.

After, same Chat method, five independent boots on the clean after-tree,
David's ports still bound:

| Clock | N | Loadavg (boot 1) | Median | Min | Max | Spread | Samples |
|---|---:|---|---:|---:|---:|---:|---|
| first-token, first turn after boot | 5 | 7.13 / 24.12 / 26.79 | 94 | 67 | 135 | 68 | 67, 67, 94, 135, 106 |
| admission, first turn | 5 | (same batch, load 7.13 → 30.72) | 46 | 27 | 57 | 30 | 28, 27, 46, 57, 57 |
| first-token, subsequent | 20 | | 56 | 43 | 160 | 117 | 43, 44, 44, 46, 46, 44, 47, 46, 56, 57, 59, 59, 116, 154, 116, 160, 54, 54, 56, 57 |

Boot 4 of the after-batch (loadavg 17.52 / 23.03 / 26.13) made even later
turns 116–160 ms. That is machine contention, not the hitch: the before-batch
at similar load kept subsequent turns at 44–52. Including it, first-token
**158 → 94** and admission **109 → 46**. Subsequent on the uncontended after
boots stays ~44–59.

A ~30–40 ms first-vs-later remainder remains on quiet boots (first POST
success-path JIT after `load` has been warmed). Fake-admitting a message at
boot to chase that would write user-visible Chat history. Left.

---

### 3. Home waits on both spines — unchanged

`combineHomeRefreshStatuses` is still worst-of. That is the honest merged-spine
rule: Home is not entitled to say `ready` / empty-projection while either
memories or conversations is still `initial-loading` or `refreshing`. Showing
each half as it arrives would be a two-step settle and would re-open the
"nothing is saved yet" lie `homeSurfacePresentation.emptyKind` exists to
prevent, unless empty stayed gated on both halves — at which point worst-of
is back.

Confirmation at `ed2e2fee3c` (same UI batch as Listen): dedicated home pageMs
median **133** (131–144). Conversations 130. Memories 187. Home is not as slow
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
Chat first-turn median needs five independent boots.

---

## Green gates at the after-tree

Taken on this machine. David's app held 4851/5290/8788. `bun test` / lints /
frontend build at `ed2e2fee3c`. L1–L4 frozen at `03f9918726` (docs-only commit
on top of the Chat warmup; frontend hash unchanged).

| Gate | Result |
|---|---|
| `bun test` | 2358 pass, 36 skip, 0 fail, 2394 tests / 350 files, 63.90 s |
| `bun run lint:imports` | exit 0 |
| `bun run lint:closure` | exit 0 |
| `(cd frontend && pnpm -r build)` | exit 0 |
| L1 | PASS in 57268ms |
| L2 | PASS in 77077ms |
| L3 | PASS in 350527ms; CONTROL-ACCEPTANCE status=PASS passed=15 failed=0 skipped=0 |
| L4 | PASS in 277615ms; CONTROL-ACCEPTANCE status=PASS passed=5 failed=0 skipped=0 |
