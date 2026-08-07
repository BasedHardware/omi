# core/ Agent Guide

Rules for any agent working under `core/`. The root `AGENTS.md` still applies (Definition
of Done, git, testing); this file carries what is different here. `core/README.md` explains
what this directory *is* — read it first if you haven't.

## Setup / verify loop

```bash
cd core
pnpm install
pnpm -r build        # tsc project references; strict; must be clean
pnpm -r test         # hermetic; node:test; no network, no wall clock
node scripts/check-isolation.mjs
```

All three commands green (plus `node scripts/gen-barrels.mjs --check`) = the baseline Definition of Done for any change here. During a concurrent wave, verify your own package scope (`pnpm --filter <pkg> build/test`) — sibling workers' unbarrelled files make the full `-r` check red until the orchestrator integrates; the orchestrator owns the integrated check. Include
their output in your commit message evidence.

## The exemplar rule

The tasks slice is the exemplar. When you add or change anything, find how the tasks slice
does it and copy that shape. **Do not invent a parallel pattern** — if the exemplar's
pattern genuinely cannot express what you need, stop and surface it; that is a foundation
gap, not your call to fill.

## Hard rules (violations are review-blocking, most are CI-enforced)

1. **Never import old-tree code** (`app/`, `desktop/`, `web/`, `backend/`) into `core/`.
   Old code is reference material only. `check-isolation.mjs` enforces this.
2. **Raw backend endpoints appear only in `packages/adapters-legacy/` and `shells/`.**
   Domain and sync code speak contracts. Also enforced by `check-isolation.mjs`.
3. **No wall clock, no `Math.random`, no ambient timers** in `contracts/`, `packages/domain`,
   `packages/sync`, `packages/kernel` logic — take an `Env` (`@omi-core/kernel`). This is
   what keeps every test deterministic.
4. **Fallback paths construct `Degraded<T>` via `degrade()`** — never hand-build the shape,
   never add a second cast to the brand. If you are writing a `catch` that substitutes a
   value, you are writing a fallback path.
5. **Ids**: parse raw strings with `parseRecordId` at the boundary; generate with
   `generateSlug`; accept `legacy-UUID | slug` everywhere; never validate slug-only.
6. **Every operation reaches a terminal outcome.** If you add a failure branch, say which
   `WriteFailure` kind it is. `permanent` never retries; `dead` is always user-visible.
   There is no fifth kind; if nothing fits, use `retryable { unclassified: true }`.
7. **Patches are keyed**: absent key = unchanged. Never write a "prepare defaults" helper
   that `setdefault`s fields into an update (the exact bug class of issue draft 02).
8. **Tests are hermetic**: `ManualEnv` + `MemoryStore` + `ScriptedTransport` from
   `@omi-core/testkit`. A test that needs the network or real time does not land in CI.
9. **Contracts changes are ratchet events**: anything under `contracts/` that a shell or
   the backend consumes bumps `BRIDGE_CONTRACT_VERSION` on breaking change and gets a
   tracker note. When a contract is silent on something you need — stop and surface it.
10. **Old-tree mount points** (the thin patches that host `core/` surfaces in existing
    apps) carry a `// core-seam:` marker comment at every call site.

11. **Adapter export names carry the domain in the identifier** — `sendTaskOp`,
    `fetchMemoryIdSnapshot`, `tasksTransport` — because the barrels re-export every
    domain with `export *` and bare names collide.
    **Barrels are GENERATED**: never edit any `src/index.ts` by hand — run
    `node scripts/gen-barrels.mjs` (CI runs `--check`). Adding a file to a package's
    `src/` is all it takes to export it.

12. **Snapshot honesty.** An id snapshot may claim `complete: true` only when the source
    provably returned the whole unfiltered set: a 200 with an unexpected body returns
    `null` (never a complete empty snapshot), a full page never claims completeness, and
    a list endpoint with ANY server-side filter may never back `complete: true` at all.
    Wrong `complete: true` is user data loss via `Projection.reconcile`.
    ENFORCED BY HARNESS: every new domain registers a `SnapshotDescriptor` in
    `packages/testkit/src/test/snapshot-conformance.test.ts` — the shared law suite runs
    it automatically (it caught this bug in 3 of the first 5 domains, including the
    original exemplar).

13. **Shell hosts bind loopback-only, and the origin is frozen.** A serving socket binds
    `127.0.0.1` explicitly and the verification script asserts it (`lsof` + a LAN-address
    curl that must fail) — `NWListener(using:on:)` binds all interfaces silently (caught
    live in wave 2: the "LoopbackServer" was publishing the bundle to the LAN). The
    origin (fixed port / custom scheme) is a storage-correctness invariant: an ephemeral
    port is a silent user-data wipe (IndexedDB is origin-keyed).

## What you may do freely

Add tests, extend the testkit's fakes with new fault modes, add a new domain following the
exemplar (contract file → codec → adapter → conformance tests), tighten types, fix defects
with a regression test. Adding dependencies is NOT free: `contracts`, `kernel`, `domain`,
`sync` stay dependency-free; elsewhere, justify in the PR.
