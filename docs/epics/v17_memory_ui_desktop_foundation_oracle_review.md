# Oracle review — V17 desktop memory tier UX foundation

**Date:** 2026-06-21  
**Oracle session:** `we-need-prescripti-oracle-guidance-6`  
**Command shape:** compact no-attachment `consult-oracle` prompt from `/home/ubuntu` with `ORACLE_HOME_DIR=/home/ubuntu/.oracle` after smoke check passed.  
**Model caveat:** Oracle reported `requested=Pro; resolved=(unavailable); status=unavailable; strategy=current; verified=no`. Preserve this caveat when citing the review.

## Prompt context

Oracle reviewed commit:

- `a02ac1459 feat(v17): add desktop memory tier UX foundation`

The prompt asked whether the committed local-only desktop-first V17 memory UI/UX foundation is a safe maintainable first slice, with explicit non-claims for backend/dev-cloud/prod readiness and Mac test execution.

## Verdict

**NO-GO** for the commit **as currently described**, while affirming that the architecture and UX direction are correct.

The blocker is not the tier/filter design. The blocker is that existing desktop synchronization and mutation paths are not demonstrably tier-scoped. The normative rule is that Archive is never default access and requires an explicit Archive operation.

## P0 local fixes required before continuing

### P0-1 — Make reconciliation scope-aware

The current cache reconcile treats `GET memories` as a complete inventory, then soft-deletes every synced local row whose ID was absent. Once the backend correctly makes its default response Short-term + Long-term, every cached Archive row will look orphaned and can be deleted.

Prescriptive fix:

- Change orphan reconciliation to accept an explicit tier scope.
- A default fetch may reconcile only `.shortTerm` and `.longTerm`.
- Archive may be reconciled only after an explicit Archive fetch.
- Carry a response-scope/completeness marker rather than inferring completeness from pagination ending.
- Version-bump the one-time sync/reconcile keys.
- Add a test with Short-term, Long-term, and Archive rows proving a default reconciliation preserves Archive.

### P0-2 — Scope every bulk operation, not only reads

Existing “make all private/public” and “delete all” paths call global API/storage operations. That can mutate or delete Archive without the user explicitly selecting or acknowledging Archive.

Prescriptive fix:

- Require `MemoryTierScope` on bulk storage and view-model methods.
- Default bulk scope is Short-term + Long-term.
- An all-tier destructive action must explicitly say “including Archive” and require confirmation.
- Until the backend has matching tier-scoped mutation semantics, disable V17 bulk server operations rather than calling legacy global endpoints.

### P0-3 — Fail closed on malformed tiers and stale UI state

- Missing tier may use the documented legacy `.longTerm` fallback.
- A present but unknown `tier` or `memory_tier` must not become Long-term. Quarantine/exclude it and record a diagnostic.
- Conflicting `tier`/`memory_tier` or `id`/`memory_id` values must fail decoding or be excluded.
- `undoDelete()` currently restores directly into search/filter arrays; after switching Archive → Default, this can republish an Archive item under the wrong active scope. Restore the database record and recompute/requery instead.
- Apply the same current-scope check when asynchronous search, paging, sync, or delete-failure restoration completes.

### P0-4 — Obtain real macOS build/test proof

Balanced braces and static-presence checks do not establish Swift type correctness, GRDB migration correctness, actor isolation, or SwiftUI compilation. Run `xcrun swift build` followed by the stated test command on a Mac runner. This is an acceptance gate, not a production-readiness claim.

```bash
cd desktop/macos
xcrun swift build --package-path Desktop
xcrun swift test --package-path Desktop \
  --skip CrispManagerLifecycleTests \
  --skip MemoriesViewModelObserverTests \
  --skip TasksStoreObserverTests \
  --skip OnboardingFlowTests
```

## P1 fixes before broadening to Windows/mobile/web

- Define one reusable desktop `MemoryTierScope` policy and apply it to list, search, counts, pagination, tag filters, chat prompt reads, export, graph, imports, bulk operations, and reconciliation.
- Add server-side tier filtering and cursor pagination before large Archive datasets are exposed.
- Exclude expired Short-term items from Default as defense in depth; explicit Short-term inspection can still show them if desired.
- Add an SQLite index matching the common predicate, such as deleted/scope/order fields, and test query plans on a realistically sized database.
- Ensure the migration backfills existing rows only; all new inserts must provide an intentional tier rather than inheriting a persistent SQLite `long_term` default.
- Add truthful delete copy explaining that deleting a memory does not itself delete the original conversation/audio/imported source.
- Add matrix tests covering tier × search × category × pagination × delete/undo × restart, including rapid Archive/Default switching and stale asynchronous responses.

## Unsafe assumptions Oracle identified

- That a default API listing represents every tier.
- That hiding Archive in `filteredMemories` is sufficient even when synchronization and mutations remain unscoped.
- That any unrecognized tier can safely become Long-term.
- That locally migrated legacy rows labeled Long-term are thereby proven ledger-backed V17 Long-term records.
- That client-side filtering after offset pagination produces complete, stable pages.
- That an additive decoder alone makes the existing API, deletion, export, chat, and reconciliation paths V17-safe.
- That Linux static checks are a substitute for compiling and executing the macOS package.

## Recommended next sequence

1. Amend the desktop slice with scope-aware reconciliation, scoped bulk operations, fail-closed tier parsing, and requery-based undo/restoration.
2. Add focused tests for those four failure modes.
3. On macOS, run `xcrun swift build --package-path Desktop` and the focused Swift test command above.
4. Perform a seeded desktop smoke test containing Short-term, Long-term, Archive, expired Short-term, missing-tier legacy, and malformed-tier records; test restart, paging, search, filter switching, delete/undo, bulk actions, and reconciliation.
5. Then prove the backend/dev-cloud contract: scoped default response, explicit authorized Archive response, cursor behavior, mutation semantics, and response completeness metadata.
6. Only after that contract is stable, port the same scope type and conformance cases to Windows, mobile, and web.

None of these steps establishes production readiness. Dev-cloud/provider proof, rollout gates, production Archive authorization, and production mutation semantics remain separate and explicitly unproven.

## Short guidance for David

> The desktop-first direction is right, but the current slice is not safe to build on unchanged. Before proceeding, we need to make cache reconciliation and bulk operations tier-scoped, fail closed on malformed tiers, harden undo/async state against Archive leakage, and pass the Mac build/tests. After those local fixes, this becomes a limited desktop foundation — not backend, dev-cloud, or production readiness.
