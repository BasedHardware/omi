# V17 memory desktop local test plan

**Status:** Ready to execute on a Mac runner/dev machine after commit `fcc20de16` plus acceptance-test additions.  
**Scope:** Local macOS desktop validation only. This does **not** prove backend/dev-cloud/production readiness.

## Build and unit commands

Run from a Mac with Xcode command line tools:

```bash
cd desktop/macos

xcode-select -p
xcrun swift --version

rm -rf Desktop/.build
xcrun swift package --package-path Desktop resolve

xcrun swift build -c debug --package-path Desktop

xcrun swift test --package-path Desktop --filter MemoryReconciliationScopeTests
xcrun swift test --package-path Desktop --filter MemoryTierFilterTests
xcrun swift test --package-path Desktop --filter ServerMemoryV17DecodingTests
xcrun swift test --package-path Desktop --filter APIClientMemoryBulkSafetyTests

xcrun swift test --package-path Desktop \
  --skip CrispManagerLifecycleTests \
  --skip MemoriesViewModelObserverTests \
  --skip TasksStoreObserverTests \
  --skip OnboardingFlowTests

# Diagnostic only; investigate every new warning/error in touched code.
xcrun swift build -c debug --package-path Desktop \
  -Xswiftc -strict-concurrency=complete
```

## Seed data

Use a disposable local profile/database or localhost fixture server. Do **not** use production.

Required rows:

| ID | Tier | Notes |
|---|---|---|
| `ST-A` | Short-term | visible by default |
| `ST-B` | Short-term | absent from authoritative default fixture for prune test |
| `LT-A` | Long-term | visible by default |
| `LT-B` | Long-term | absent from authoritative default fixture for prune test |
| `AR-A` | Archive | hidden by default, visible only via Archive |
| `AR-B` | Archive | absent from authoritative Archive fixture for prune test |
| `LOCAL-UNSYNCED` | Short-term or Long-term | backendId nil, must never be pruned |
| `SOFT-DELETED` | any | remains hidden |
| `CORRUPT-TIER` | raw SQLite `tier="corrupt_tier"` | excluded, not promoted to Long-term |

## Required scenarios

### Reconciliation

- Default authoritative fixture containing only `ST-A` and `LT-A` may prune `ST-B`/`LT-B`, but must preserve `AR-A`/`AR-B`.
- Archive authoritative fixture containing only `AR-A` may prune `AR-B`, but must preserve Short-term and Long-term.
- Current backend/default response without authoritative scope/completeness metadata must sync returned rows and prune nothing.
- First-page, truncated, failed-decode, timeout, 401, and malformed-response cases must prune nothing.
- `.allIncludingArchive` must never be selected by default UI/reconciliation paths.

### Decoding and persistence

- `id` only, `memory_id` only, and equal aliases decode.
- Conflicting ID aliases fail.
- `tier` only, `memory_tier` only, and equal aliases decode.
- Conflicting tier aliases and unknown explicit tiers fail.
- No tier aliases defaults legacy rows to Long-term.
- Malformed persisted tier is excluded without crash, Long-term promotion, count drift causing infinite pagination, or visible row leakage.

### Bulk operations

- `deleteAllMemories(scope:)`, `updateAllMemoriesVisibility(scope:visibility:)`, and `markAllMemoriesRead(scope:)` throw `unsupportedTierScopedBulkMutation` before any URLSession request.
- Disabled bulk server calls perform zero local mutations and trigger no auth refresh/retry behavior.
- Local scoped helpers behave correctly when called directly:
  - default scope affects only Short-term + Long-term
  - Archive scope affects only Archive
  - explicit all scope affects all three
- Insight mark-all-read path makes no network request, mutates no rows, and does not retry-loop.

### Async races

Use controllable delayed dependencies or a fixture server; avoid timing sleeps as proof.

- Start a Default load, switch to Archive, then complete Default request.
- Start Archive paging, switch to Default, then complete paging.
- Start refresh in one scope, switch scope, then complete refresh.
- Run search `A`, then search `B` in the same scope and complete `A` last.
- Stale completions must not alter rows, filtered caches, offset, `hasMore`, loading flags, errors, counts, or pending-delete state.

### Delete/undo/failure restoration

- Delete a Default item, switch to Archive, then undo: SQLite restores it, but Archive UI does not append it.
- Delete an Archive item, switch to Default, then undo: SQLite restores it, but Default UI does not append it.
- Repeat both with delayed server-delete failure.
- Returning to the original scope shows exactly one restored row.
- Restoration preserves backend ID, tier, sync state, timestamps, and deletion flags.

### Migration/restart

- Open a database from the immediately preceding desktop version.
- Legacy records receive Long-term compatibility tier.
- Existing Archive rows remain Archive.
- Insert malformed raw tier, restart twice, verify stable exclusion.
- Counts, ordering, offsets, and `hasMore` remain stable.

### UI smoke

```bash
cd desktop/macos
./run.sh
```

- Default view shows Short-term + Long-term only.
- Archive requires explicit selection and is visually distinct.
- Bulk controls remain disabled with accurate help text.
- Labels say Default scope, not “all memories.”
- Per-item delete/edit/visibility and undo still work.
- No global bulk request appears in network logs.

## Still blocked after local Mac success

Even if this plan passes, keep blocked:

- re-enabling global/bulk server mutation controls
- destructive reconciliation from `/v3/memories` without authoritative scope/completeness metadata
- default Archive exposure
- Windows/mobile/web broadening beyond contract alignment
- dev-cloud/prod rollout claims
- backend tier-scoped mutation semantics
- cursor/completeness/authorization proof
