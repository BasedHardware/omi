# R0.5 Migration Plan — for the 5 open PRs

## Context

R0.5 separates the lane catalog from the serving config. The 5 open PRs were built on the OLD architecture (lanes.yaml + route_artifacts.yaml as a single source of truth, with placeholders in serving). R0.5 changes that architecture.

After R0.5 merges to main, the 5 open PRs need to be re-based + re-migrated to use the new architecture. This document describes the migration strategy for each.

## Migration strategy: re-base + re-migrate

**Re-base**: Update each PR's branch to include R0.5's commits (catalog, lane_catalog.py module, trimmed serving config).
**Re-migrate**: Update each PR's code/tests to use the new architecture.

This preserves the review history of each PR. The alternative (close + reopen) loses history. R0.5 is a structural change but the existing PRs' review history is still relevant.

## Migration per PR

### PR #8739 (R0) — 15 new lanes + initial artifacts

**Current state**: 15 new lane entries in `lanes.yaml` (all `dev_only: false`); 16 new artifacts in `route_artifacts.yaml` (15 new + 1 chat-structured LKG); 3 of the 16 with `placeholder: true`.

**R0.5 migration**:
1. Re-base onto R0.5. The R0 commit (091fa4ce5) added 15 new lane entries; with R0.5 the serving config keeps only `chat-structured`.
2. Move the 15 new lane entries' descriptions into the catalog's `notes` field (R0.5 has them all in the catalog with `provider_support_status: dev_only` or `planned`).
3. The 3 placeholders' `placeholder: true` flag is no longer needed (they're catalog-only with `planned` status).
4. The 15 R0 new artifacts in `route_artifacts.yaml` are no longer in the serving config. They're "moved" to the catalog (their lane_ids are in the catalog, but they have NO serving artifacts — R3 will build them when promoting).
5. `test_llm_gateway_config.py::test_loads_default_gateway_config` needs updating: 1 lane + 2 artifacts (chat-structured's active + LKG), not 16 lanes + 17 artifacts.
6. The R0 fix commit (0d3442de2) for the `placeholder` field is no longer needed for the serving config (the placeholders aren't in the serving config). The `placeholder` field is kept in the `Evidence` schema for future use.
7. The R5b commit (b76c58de4) that restricted `SUPPORTED_AUTO_LANE_IDS` to 13 chat-completion lanes is updated: with R0.5 the allowlist is derived from the catalog (1 prod_ready lane = 1 element).

**Tests to update**:
- `tests/unit/test_llm_gateway_config.py` — update the default-config expectations
- `tests/unit/test_llm_gateway_resolver.py` — remove the parametrized tests for the 12 dev_only lanes (keep only `chat-structured`)

### PR #8740 (R5a + R1) — scoring engine + emitter

**Current state**: `LANE_TO_V3_TASK` maps 5 v3 tasks to 5 R0 lanes. The emitter produces artifacts for the 15 new R0 lanes (all 15 → catalog-only after R0.5). The fixture in `benchmarks_emitter_sample.json` has 5 v3 tasks.

**R0.5 migration**:
1. Re-base onto R0.5.
2. `LANE_TO_V3_TASK` shrinks from 5 entries to 1 (only `chat-structured` has a v3 task mapping in the catalog's `eval_suite` field). Wait — actually `LANE_TO_V3_TASK` maps R0 lanes to v3 tasks. With R0.5, only `chat-structured` is in the serving config. The emitter can still emit for v3 tasks; the question is which R0 lane gets associated.
3. The fixture's task list should reflect what the catalog says (1 task: `chat-structured`).
4. The 14 catalog-only lanes (R0's 12 dev_only + R0's 3 planned - `chat-structured`) don't have v3 task mappings → emitter skips them. The R5a+R1 tests need to reflect this: the fixture has fewer tasks; the emitter iterates only over lanes that have both a v3 task mapping AND are in the serving config.

**Tests to update**:
- `tests/unit/llm_gateway/test_sync_benchmarks_emitter.py` — update the expected task count
- `tests/unit/llm_gateway/test_daily_refresh.py` — adjust if needed (parity tests for the cherry-pick)

### PR #8744 (R5b) — mtime-watched hot-reload

**Current state**: `SUPPORTED_AUTO_LANE_IDS` is a hardcoded frozenset of 13 chat-completion lanes. `config_reload.py` loads the config and cross-checks via `load_gateway_config(..., required_lane_ids=SUPPORTED_AUTO_LANE_IDS)`.

**R0.5 migration**:
1. Re-base onto R0.5.
2. `resolver.py` now derives `SUPPORTED_AUTO_LANE_IDS` from the catalog (1 prod_ready entry = 1 element).
3. `config_reload.py` uses `load_catalog()` to get the prod_ready lane_ids and passes them as `required_lane_ids=...`.
4. The `config_reload.py` code itself is unchanged (the mtime polling + LKG fallback are still correct).
5. The placeholder test (which was added in this PR) is no longer needed (placeholders aren't in the serving config). But the placeholder field on `Evidence` is kept for future use.
6. The `_R0_NEW_LANE_IDS` set in `test_llm_gateway_config.py` is updated to 1 element (just `chat-structured`).

**Tests to update**:
- `tests/unit/test_llm_gateway_dependencies.py` — `SUPPORTED_AUTO_LANE_IDS` is now 1 element
- `tests/unit/test_llm_gateway_config.py` — `_R0_NEW_LANE_IDS` is 1 element
- `tests/unit/llm_gateway/test_daily_refresh.py` — adjust parity tests

### PR #8746 (R2) — capability smoke

**Current state**: The smoke iterates over `SUPPORTED_AUTO_LANE_IDS` (13 lanes per R0+5a+R1). Uses `--provider fake` by default + `FakeProvider` in tests.

**R0.5 migration**:
1. Re-base onto R0.5.
2. The smoke iterates over `SUPPORTED_AUTO_LANE_IDS` (1 lane: `chat-structured`).
3. The smoke's plan mentioned `--provider real` for the actual gate (R4). With R0.5, R2's fake is still the unit test mock; the real gate is R4.
4. `FakeProvider` in `tests/unit/llm/deterministic_provider.py` is unchanged.
5. The fixture (5 v3 tasks → 5 R0 lanes) shrinks to 1 v3 task → 1 R0 lane.

**Tests to update**:
- `tests/unit/llm/test_capability_smoke.py` — the fixture has fewer tasks; the smoke iterates fewer lanes
- `tests/unit/llm/fakes.py` — no changes

### PR #8748 (R3.1) — dual-path infrastructure

**Current state**: `ShadowCutover` + `ShadowMetrics` + fakes + tests. Lane-agnostic. The tests don't reference specific lane ids.

**R0.5 migration**:
1. Re-base onto R0.5.
2. The R3.1 infrastructure is unchanged — it's lane-agnostic.
3. R3.2 (the actual cutover) will be a separate cycle. R3.1's tests don't need R0.5 changes.

**Tests to update**: None (R3.1 is lane-agnostic).

## Migration order

Re-migrate in dependency order:
1. **First**: PR #8739 (R0) — base architecture; the other PRs depend on it
2. **Second**: PR #8744 (R5b) — depends on R0
3. **Third**: PR #8740 (R5a+R1) — depends on R0
4. **Fourth**: PR #8746 (R2) — depends on R5a+R1 + R0
5. **Fifth**: PR #8748 (R3.1) — depends on R0

Each re-migration is a separate commit (or series of commits) on each PR's branch. After re-migration, the PR's diff (against the updated R0.5 base) shows only the R0.5-adapted changes.

## Risks

- **Merge conflicts**: re-basing against R0.5 may cause conflicts in `lanes.yaml`, `route_artifacts.yaml`, and the various test files. Mitigation: the migration plan above gives a recipe for each file; conflicts should be resolvable.
- **CI failures**: the re-migrated PRs may have failing tests (because the OLD tests reference the OLD architecture). Mitigation: update the tests as part of the re-migration (each PR's plan above lists which tests to update).
- **Reviewer confusion**: the re-migrated PR has R0.5 + the original work stacked. The diff against main shows R0.5 + the original work, which is the same as before but with the architecture change. Mitigation: the PR description should explain the re-migration.

## How to execute

For each PR (in order):
1. `git fetch origin` (R0.5 is on main now)
2. `git rebase origin/main` (R0.5's commits are on main)
3. Resolve conflicts per the migration plan above
4. Update the PR's tests
5. Force-push the PR branch
6. Re-run the PR's review (cubic will fire fresh; expected — we've been through this before)

Total expected work: ~3-4 hours across all 5 PRs.

## Done criteria

- All 5 open PRs are re-based onto R0.5 + re-migrated
- All 5 PRs pass their CI
- Each PR's diff against main shows: R0.5 (architecture change) + the original work (adapted to new architecture)
- All 5 PRs are ready to merge

## Note

This migration plan is a guide. The actual re-migration will be done in follow-up AIDLC cycles (one per PR). Each cycle follows the same pattern: spec + plan + implement + test + review + push.