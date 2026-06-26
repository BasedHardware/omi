# Auto-router stack — merge plan & product framing

> **TL;DR:** The 5 PRs in the stack are independently mergeable. Each can be
> reverted without breaking the ones below it. **Recommended path: land
> v1 first, see production signal, then decide on v2-v5.**

This document addresses the maintainer feedback on PR
[#8359](https://github.com/BasedHardware/omi/pull/8359) about the
5-deep stack. It is **not a code change** — it's a decision aid for
the team. Read this before deciding what to merge.

---

## 1. The stack in one minute

| PR | Branch | What it adds | Commits | Tests | New files (approx) |
|---|---|---|---|---|---|
| [v1](#v1-framework) | `feat/auto-router-v1` | Framework: scoring, registries, daily-refresh cache, `/pick` endpoint, Swift client | 26 | 142 | ~30 |
| [v2](#v2-production-useful) | `feat/auto-router-v2` | Auth on `/pick`, `/metrics` endpoint, `ChatModelRouter` wiring | 16 | 175 | ~5 |
| [v3](#v3-per-user-prefs) | `feat/auto-router-v3` | Per-user prefs (in-memory), AA integration, `RealtimeOmniSettings` wiring | 14 | 287 | ~8 |
| [v4](#v4-persistent-prefs) | `feat/auto-router-v4` | Firestore-backed prefs with 5min cache, `FirestoreUserPrefsStore` | 8 | 325 | ~4 |
| [v5](#v5-settings-ui) | `feat/auto-router-v5` | Settings UI, expanded benchmarks, admin key timing fix, process artifact cleanup | 11 | 446+ | ~5 |
| (v6 reverted) | — | User-visible model selection (per-task picker). Withdrawn pending v1 production signal. | — | — | — |

Each version's tests are a strict superset of the previous (v1's 142
+ v2's new tests, etc.). **No version breaks any earlier version's
contracts.** v1's `/pick` endpoint is the same in v2-v5 (with auth
added as a wrapping dependency).

## 2. The merge plan

### Option A: Land v1 only (recommended)

```bash
# From main, cherry-pick just v1's commits
git checkout main
git checkout -b feat/auto-router-v1-clean
git cherry-pick <v1 commit range>
# Push + open PR
```

**What's in:** 26 commits, ~1,300 lines, 142 tests, the framework +
`/pick` endpoint + Swift client + demo + docs.

**What's NOT in:** auth on `/pick` (callers must be signed in
themselves), `/metrics` endpoint, per-user prefs, Settings UI, model
selection, Firestore persistence.

**Risk:** zero. v1 is a self-contained framework. Existing upstream
`/v1/auto/model-pick` continues to work — v1's `/v1/auto-router/pick`
is a parallel endpoint that nothing calls yet (no callers in main).

**Decision gate after landing:**
- Is `/v1/auto-router/pick` being called in production? (instrument
  with logs)
- Are there user complaints about model selection? (feedback)
- Is the AA benchmarks path worth standing up? (ops decision)

If yes to any → v2-v5 become "productize the framework" work, each
backed by a concrete signal. If no → the framework sits unused and
v2-v5 are dead code; revert and stop.

### Option B: Bottom-up merge (v1 → v2 → v3 → v4 → v5)

Merge each PR in order. Each merge creates a "checkpoint" the team
can roll back to.

**Pros:** preserves per-version narrative, each PR is independently
reviewable.

**Cons:**
- 5-deep stack risk is real (any single PR failure = lose everything
  above it)
- Bisect across the stack is slow (you have to know the boundary
  commit for each version)
- Reviewer has to context-switch between 5 PRs with different scopes
  (5 P1, ~30 P2 across the stack)

**Rollback guarantee (this is the key point):** Each version is
revertable *independently*. v1's endpoint and contracts don't change
in v2-v5. Reverting v5 doesn't break v4. Reverting v4 doesn't break
v3. Etc. So Option B's worst case is "rolled back to v1" — which is
Option A anyway.

### Option C: Squash the stack (one big PR)

Single commit / single PR with everything. Lose per-version
narrative. One CI run. Easier merge mechanics.

**Cons:**
- Reviewer fatigue (~9k lines in one PR)
- Bisect across the squashed commit gives a single regression point
  (no per-version granularity)
- If the maintainer wants to revert PART of the stack, they can't
  (it's one big commit)

**Recommended only if:** the team is comfortable evaluating the whole
stack as a single unit. Given the maintainer's stated concerns about
reviewing 5 PRs, adding 9k lines into 1 PR doesn't help.

### Recommended: **Option A, with Option B as fallback**

1. Land v1. Monitor for 30 days.
2. If v1 sees real usage, start merging v2 → v5 in order (Option B).
3. If v1 sees no usage, revert it. v2-v5 are dead code, no merge
   needed.

---

## 3. Per-version rationale (for the feature-fit question)

Each version is justified by a different product signal. Listing them
explicitly so the team can decide what to ship based on observed demand.

### v1 (framework)

- **What it is:** a standalone, well-tested scoring + registry +
  cache + endpoint. No auth, no metrics, no per-user state.
- **Justified by:** "we need a flexible model-selection framework
  that's decoupled from upstream's hardcoded `/v1/auto/model-pick`"
  (the maintainer's stated rationale).
- **Production signal needed:** any caller of `/v1/auto-router/pick`
  (including the Swift client, even with a hardcoded fallback).
- **Risk if landed alone:** zero. The endpoint exists but nothing
  calls it yet.

### v2 (production-useful)

- **What it is:** auth + `/metrics` + wiring into `ChatModelRouter`
  (so the Swift chat path actually consults the router).
- **Justified by:** "we need to know if the router is being called
  and whether it's behaving correctly in production."
- **Production signal needed:** v1 is being called. Without v1
  callers, the metrics are noise.
- **Risk if landed:** auth is the only addition that affects callers.
  `/metrics` is opt-in (no current callers in main).

### v3 (per-user prefs)

- **What it is:** per-user weight overrides + AA benchmarks integration
  + `RealtimeOmniSettings` wiring (realtime voice model selection
  consults the router).
- **Justified by:** "users want to tune per-task weights; ops want
  real benchmarks from AA instead of the mock file."
- **Production signal needed:** evidence that users want weight tuning
  (support tickets, user feedback, PM input) and that ops needs
  live benchmarks (not a decision we'd make from engineering alone).
- **Risk if landed without v2:** the `RealtimeOmniSettings` wiring
  makes the realtime session depend on the router pick. If the
  router is misbehaving, realtime voice breaks. v2's auth +
  metrics give us the observability to detect that.

### v4 (persistent prefs)

- **What it is:** Firestore-backed prefs with 5min cache.
- **Justified by:** "users set their prefs on one device, expect
  them on another."
- **Production signal needed:** v3 is shipped + user feedback
  confirms multi-device usage pattern.
- **Risk if landed without v3:** zero (no callers in main to break).

### v5 (Settings UI)

- **What it is:** the `Settings → Auto-router` page + STT/embedding
  benchmark data + admin key timing fix + process artifact cleanup.
- **Justified by:** "users need a UI to edit their prefs."
- **Production signal needed:** v4 is shipped + users are actively
  using prefs.
- **Risk if landed without v4:** the Settings UI persists to
  in-memory prefs (v3's storage), which means prefs reset on every
  app restart. Users will notice and complain.

---

## 4. What was already addressed in this PR

Two of the maintainer's four observations are already fixed in
[PR #8359](https://github.com/BasedHardware/omi/pull/8359):

- ✅ **Process artifacts in repo root** (commit `f261e1ee`) — removed
  `UAT-REPORT.md`, `review-report.md`, `uat-findings.json`. Added
  `.gitignore` entries to prevent recurrence.
- ✅ **Admin key timing attack** (commit `f261e1ee`) — replaced `==`
  with `hmac.compare_digest` in `routers/auto_router.py`. Plus
  follow-up default-closed admin gating in commit `dab05f0` (per
  cubic review).

The remaining two observations are the strategic questions above
(merge plan + feature fit), which this document addresses.

---

## 5. CI status (current)

All 3 checks passing on `feat/auto-router-v5` at commit `dab05f0`:

- ✅ Hermetic Backend E2E
- ✅ Lint & Format Check (black 26.5.1)
- ✅ cubic · AI code reviewer

Cubic's 33 findings across 2 review passes are all addressed.

## 6. What to do

1. **Maintainer reads this doc, decides on Option A / B / C.**
2. If A: I open a cherry-pick PR for v1 only.
3. If B: I document the merge order in the PR descriptions and we
   proceed bottom-up.
4. If C: I squash the 5 branches into one and we re-review as a unit.

The actual code in `feat/auto-router-v5` is mergeable as-is. The
question is *what subset* to merge.
