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

**`pnpm verify` green is the Definition of Done here.** It runs the aggregate: barrels,
structure (no dep cycles; tests for contracts/domain/sync/kernel/adapters live in
`packages/testkit/`), wire conformance, and the generated Swift/Dart bridge constants.
During a concurrent wave, verify your own package scope (`pnpm --filter <pkg> build/test`)
— siblings' unbarrelled files keep the full `-r` check red until the orchestrator
integrates, and the integrated check is theirs. Put the output in your commit evidence.

## The exemplar rule

The exemplar is the **tasks + memories pair**. When you add or change anything, find how
those two slices do it and copy that shape. Two slices, not one, because a single
instance cannot teach multiplicity: wave 4 proved that copying tasks *correctly* still
produced a cross-domain outbox collision, because nothing in one instance shows which
names must be namespaced per domain. Where the two slices differ, the difference IS the
lesson — look at why before choosing. **Do not invent a parallel pattern** — if the
exemplar pair genuinely cannot express what you need, stop and surface it; that is a
foundation gap, not your call to fill.

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
    **Barrels are GENERATED**: never hand-edit a package's generated barrel —
    run `node scripts/gen-barrels.mjs` (CI runs `--check`). Adding a file to a
    package's source tree is all it takes to export it.

12. **Snapshot honesty — `complete: true` is the exceptional claim.** Filtered sources
    are the NORM here (2 of the first 4 domains filter server-side, one *after* the page
    limit), so the default assumption for any list endpoint is that it may NOT back
    `complete: true`. An id snapshot claims completeness only when the source provably
    returned the whole unfiltered set, and its `SnapshotDescriptor` must carry declared
    evidence — a descriptor asserting complete-capability without evidence fails the
    harness. A 200 with an unexpected body returns `null`; a full page never claims
    completeness. Wrong `complete: true` is user data loss via `Projection.reconcile`.
    ENFORCED BY HARNESS: every new domain registers a `SnapshotDescriptor` in
    `packages/testkit/src/test/snapshot-conformance.test.ts`. The kind you declare is a
    claim about the BACKEND, not your adapter, and must cite backend evidence — why:
    [`core-invariant-history`](../docs/agents/core-invariant-history.md).

13. **Shell hosts bind loopback-only, and the origin is frozen.** Bind `127.0.0.1`
    explicitly and assert it (`lsof` + a LAN curl that must fail): `NWListener(using:on:)`
    binds all interfaces silently — in wave 2 the "LoopbackServer" was publishing the
    bundle to the LAN. The origin (fixed port / custom scheme) is a storage-correctness
    invariant: an ephemeral port is a silent user-data wipe, since IndexedDB is
    origin-keyed.

14. **Invariant tests declare their red-proof.** A test that guards an invariant (data
    loss, id routing, outcome folding, snapshot honesty, cross-domain isolation) carries
    a `// red-proof:` comment naming the specific mutation that makes it fail, and the
    reviewer APPLIES that mutation before accepting the test. Row-count assertions are the
    canonical decorative shape: assert the *content* only a working mechanism can produce,
    not how many rows survived. Why: [`core-invariant-history`](../docs/agents/core-invariant-history.md).

15. **A shared wire is tested against its REAL shape, never a remembered one.** When two
    components are developed independently against one wire, at least one test must consume
    the OTHER side's actual wire shape — a shared corpus of record — not a payload its own
    author typed out. ENFORCED BY `scripts/check-wire-conformance.mjs` (in `pnpm verify`):
    every seam in its registry needs a corpus covering every frame its schema-of-record
    declares, plus a named test that reads it. A new shared wire means a new registry row.
    The three defects that wrote this rule: [`core-invariant-history`](../docs/agents/core-invariant-history.md).

## What you may do freely

Add tests, extend the testkit's fakes with new fault modes, add a domain following the
exemplar, tighten types, fix defects with a regression test. Dependencies are NOT free:
`contracts`, `kernel`, `domain`, `sync` stay dependency-free; elsewhere, justify in the PR.
