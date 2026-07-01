# Plan: Auto-Router Gateway — R0.5 (Lane Catalog + Serving Config Split)

## Dependency Graph

```
David's feedback (2026-07-02) — "separate lane catalog from serving config"
   |
   v
R0.5 work (this worktree)
   |
   +-- T-001: New file backend/llm_gateway/config/lanes_catalog.yaml
   |     - All 16 R0 lanes with provider_support_status
   |     - Plus any future lanes (planned, not in R0)
   |
   +-- T-002: New module backend/llm_gateway/gateway/lane_catalog.py
   |     - LaneCatalog Pydantic model
   |     - load_catalog() function
   |     - validate_serving_config(catalog, cfg) cross-check
   |
   +-- T-003: Modify backend/llm_gateway/config/lanes.yaml
   |     - Remove 3 placeholder lanes (stt-realtime, transcription, screenshot-embedding)
   |     - Add only prod_ready entries (initially: chat-structured + chat-extraction)
   |
   +-- T-004: Modify backend/llm_gateway/config/route_artifacts.yaml
   |     - Remove 3 placeholder artifacts
   |     - Keep only artifacts for serving lanes
   |
   +-- T-005: Modify backend/llm_gateway/gateway/resolver.py
   |     - SUPPORTED_AUTO_LANE_IDS derives from catalog (prod_ready entries)
   |     - Or: keep as-is, but validate via the catalog at load time
   |
   +-- T-006: Modify backend/llm_gateway/gateway/config_loader.py
   |     - Add LaneCatalog loading to load_gateway_config
   |     - Cross-check: every serving lane has a catalog entry with prod_ready
   |
   +-- T-007: Tests in backend/tests/unit/llm_gateway/test_lane_catalog.py
   |     - Catalog loading
   |     - Serving config cross-validation
   |     - Placeholder rejection
   |     - prod_ready promotion validation
   |
   +-- T-008: Migration plan for the 4 open PRs
   |     - PR #8739 (R0): re-base + remove placeholders from serving config
   |     - PR #8740 (R5a+R1): re-base + update emitter to use catalog
   |     - PR #8744 (R5b): re-base + update SUPPORTED_AUTO_LANE_IDS source
   |     - PR #8746 (R2): re-base + update smoke to use catalog
   |     - PR #8748 (R3.1): re-base + verify dual-path semantics
   |
   +-- T-009: Plan-only updates for R3.2 and R4
   |     - R3.2: first cutover is chat-structured (real, has openai-compatible provider)
   |     - R4: cron uses the catalog + internal eval gate (table for later)
   |
   +-- T-010: Final regression + AIDLC review

After R0.5 ships:
   |
   v
PRs #8739, #8740, #8744, #8746, #8748 re-based onto R0.5 + re-migrated
   |
   v
R3.2 (chat-structured first cutover) — separate cycle
   |
   v
R4 (cron with new promotion path) — separate cycle, plan-only updated
```

## Tasks

### T-001: New file `lanes_catalog.yaml` (the catalog of all lanes)

**Files:**
- `backend/llm_gateway/config/lanes_catalog.yaml` (new)

**Description:**
Define the catalog of ALL lanes. The serving config (`lanes.yaml` + `route_artifacts.yaml`) is a subset. Each catalog entry has:
- `lane_id`
- `description`
- `surface` (`openai.chat_completions`, `unknown` for planned)
- `provider` (`openai`, `anthropic`, `tbd`)
- `model`
- `provider_support_status` (`planned` | `dev_only` | `prod_ready`)
- `eval_suite` (path to internal eval set, or `null` for planned/dev_only)
- `notes` (human-readable context)
- `promoted_at` (ISO timestamp when a lane moved to `prod_ready`; absent for `dev_only`/`planned`)

The catalog includes all 16 R0 lanes (1 existing + 15 new) with their actual `provider_support_status`:
- `prod_ready` (catalog, not yet in serving): `chat-structured` (the R0 pilot)
- `dev_only` (catalog only, not in serving): `chat-extraction`, `daily-summary`, `memories-extraction`, `memory-graph`, `conv-action-items`, `conv-structure`, `general-assistant`, `reasoning`, `realtime-ptt`, `persona-chat`, `notification-classifier` — all 11 R0 lanes that aren't the pilot
- `planned` (catalog only): `stt-realtime`, `transcription`, `screenshot-embedding` — the 3 placeholders David wants out of the serving config

Wait, that's 16 lanes total. Let me re-check. R0 added 15 new lanes + 1 existing. The 3 placeholders are `stt-realtime`, `transcription`, `screenshot-embedding`. So:

- R0 (15 new) + existing `chat-structured` = 16 lanes
- Pilot: `chat-structured` (R0 has been in production; it's the real one)
- 3 placeholders: `stt-realtime`, `transcription`, `screenshot-embedding` (catalog only, dev_only or planned)
- 12 more R0 lanes (other than the 3 placeholders): all dev_only

The serving config keeps only `chat-structured` initially. R3.2's first cutover is also `chat-structured` (per David's "first real cutover should be chat-structured"). R3.2's later cuts can add `chat-extraction`, then `daily-summary`, etc.

**Acceptance criteria:**
- [ ] AC1: `lanes_catalog.yaml` lists all 16 lanes
- [ ] AC2: Each entry has `provider_support_status` matching the real state
- [ ] AC3: The 3 placeholders (`stt-realtime`, `transcription`, `screenshot-embedding`) are `planned` or `dev_only` (catalog only)
- [ ] AC4: `chat-structured` is `prod_ready` (pilot)
- [ ] AC5: The 11 other R0 new lanes are `dev_only`
- [ ] AC6: `eval_suite` field is present (null for `dev_only`/`planned`; a path for `prod_ready`)
- [ ] AC7: `promoted_at` is present only for `prod_ready` entries

**Test approach:** Smoke test the catalog loading (T-002). Cross-validation is T-006.

**Estimated effort:** S (~30 min)

### T-002: New module `lane_catalog.py` (Pydantic model + load + validate)

**Files:**
- `backend/llm_gateway/gateway/lane_catalog.py` (new)

**Description:**
Define the Pydantic model for the catalog + the `load_catalog()` function + the `validate_serving_config(catalog, cfg)` cross-check.

```python
class ProviderSupportStatus(str, Enum):
    PLANNED = "planned"
    DEV_ONLY = "dev_only"
    PROD_READY = "prod_ready"

class CatalogEntry(StrictBaseModel):
    lane_id: LaneId
    description: str
    surface: Surface  # openai.chat_completions, or "unknown" for planned
    provider: str  # "openai", "anthropic", "tbd"
    model: str  # model name, or "tbd"
    provider_support_status: ProviderSupportStatus
    eval_suite: Optional[str] = None  # path to internal eval set
    notes: str = ""
    promoted_at: Optional[datetime] = None  # when it became prod_ready

class LaneCatalog(StrictBaseModel):
    lanes: list[CatalogEntry]

def load_catalog(config_dir: Path | None = None) -> LaneCatalog: ...

def validate_serving_config(
    catalog: LaneCatalog,
    serving_cfg: GatewayConfig,
) -> None:
    """Cross-check: every serving lane must be in the catalog with prod_ready
    status. Every prod_ready catalog entry must have a serving artifact.
    Raises ConfigValidationError on mismatch.
    """
```

**Acceptance criteria:**
- [ ] AC1: `load_catalog()` loads `lanes_catalog.yaml` from the default config dir (or override)
- [ ] AC2: `validate_serving_config(catalog, cfg)` raises `ConfigValidationError` on:
  - A serving lane that isn't in the catalog
  - A serving lane whose catalog entry is not `prod_ready`
  - A `prod_ready` catalog entry that has no serving artifact
- [ ] AC3: `validate_serving_config` is silent on a valid config

**Test approach:** TDD. Tests in `test_lane_catalog.py` cover the cross-validation rules.

**Estimated effort:** M (~60 min)

### T-003: Modify `lanes.yaml` (remove 3 placeholders)

**Files:**
- `backend/llm_gateway/config/lanes.yaml` (modify)

**Description:**
The serving config currently has 16 lane entries (1 existing + 15 R0 new). Remove the 3 placeholders: `stt-realtime`, `transcription`, `screenshot-embedding`. Also remove the other 11 R0 dev_only lanes — keep only `chat-structured` (the pilot) in the initial serving config. R3.2 will add lanes back as they get promoted.

**Wait** — this is significant. Currently R0 has 15 new lanes in the serving config. Per David's "No prod-loadable placeholder route artifacts", we should remove all 15 R0-new lanes from the serving config, not just the 3 placeholders. Only `chat-structured` (R0's existing pilot) stays in the serving config.

Let me re-read David's feedback:
> "Serving config should only include lanes the gateway can actually execute today"
> "If a lane doesn't have the real surface / provider support / eval yet, keep it catalog-only"

So: only lanes that have REAL surface + provider support + eval. The R0 placeholders (`stt-realtime`, `transcription`, `screenshot-embedding`) are the most obvious "not yet real" — they have `placeholder: true` AND `dev_only: true` (wait, no — they have `dev_only: false` + `placeholder: true` per the R0 fix). Per the new R0 fix in commit `0d3442de2`, the placeholders are `dev_only: false` + `placeholder: true` (which means `is_prod_eligible()` returns True but `placeholder: true` flags them as R3-replaceable).

So the R0 serving config has 16 entries with `dev_only: false`, but 3 of them have `placeholder: true` (the ones we want to remove). The other 13 have `placeholder: false`.

David's feedback is broader: ANY lane without real surface + provider + eval stays catalog-only. So the 11 R0 dev_only entries (with `placeholder: false`) should ALSO be removed from the serving config. They go to the catalog.

OK so the serving config post-R0.5 will have ONLY:
- `chat-structured` (R0's existing pilot — real, has openai-compatible provider, has an eval)

That's 1 lane in the serving config. The other 15 lanes are in the catalog only.

But wait — R5a+R1 (PR #8740) was designed around the 15-new-lanes model. The emitter has a lane-to-task mapping for all 15. If we remove most from the serving config, the emitter is moot for those lanes.

This is exactly the architectural change David wants. R5a+R1's emitter becomes: emit artifacts for the 1 lane that's in the serving config (chat-structured). The other 14 lanes are catalog-only — they're not in the emitter's lane list.

R3.2's first cutover adds `chat-extraction` to the serving config (per David's "first real cutover"). Subsequent cuts add more.

**Acceptance criteria:**
- [ ] AC1: `lanes.yaml` has only `chat-structured` (1 lane) initially
- [ ] AC2: The 3 placeholders + 11 R0 dev_only lanes are NOT in the serving config

**Test approach:** TDD. Tests in `test_lane_catalog.py` verify the cross-validation rule.

**Estimated effort:** S (~15 min)

### T-004: Modify `route_artifacts.yaml` (remove 3 placeholders + 11 R0 dev_only artifacts)

**Files:**
- `backend/llm_gateway/config/route_artifacts.yaml` (modify)

**Description:**
Currently 17 artifacts. Remove 16 of them (the 3 placeholders + the 11 R0 dev_only lanes that aren't in the serving config). Keep only the artifacts for the 1 lane in the serving config: `chat-structured` (1 active + 1 LKG = 2 artifacts).

**Acceptance criteria:**
- [ ] AC1: `route_artifacts.yaml` has only the artifacts for lanes in the serving config (1 lane × 2 artifacts = 2)
- [ ] AC2: The 16 other artifacts (placeholders + R0 dev_only) are NOT in the file

**Test approach:** TDD. The cross-validation test verifies the count.

**Estimated effort:** S (~15 min)

### T-005: Modify `resolver.py` (SUPPORTED_AUTO_LANE_IDS derives from catalog)

**Files:**
- `backend/llm_gateway/gateway/resolver.py` (modify)

**Description:**
Currently `SUPPORTED_AUTO_LANE_IDS` is a hardcoded frozenset. Change it to derive from the catalog at module load time. Specifically: `SUPPORTED_AUTO_LANE_IDS = frozenset(e.lane_id for e in load_catalog().lanes if e.provider_support_status == ProviderSupportStatus.PROD_READY)`.

This means the resolver's allowlist is dynamically derived from the catalog. Adding a `prod_ready` lane to the catalog automatically includes it in the resolver's allowlist. Removing it (or marking it `dev_only`) removes it.

**Acceptance criteria:**
- [ ] AC1: `SUPPORTED_AUTO_LANE_IDS` derives from the catalog (not hardcoded)
- [ ] AC2: Adding a `prod_ready` entry to the catalog makes the lane resolvable
- [ ] AC3: Marking a `prod_ready` entry as `dev_only` removes it from the resolver

**Test approach:** Tests in `test_lane_catalog.py` verify the derivation.

**Estimated effort:** S (~30 min)

### T-006: Modify `config_loader.py` (cross-check serving vs catalog)

**Files:**
- `backend/llm_gateway/gateway/config_loader.py` (modify)

**Description:**
Add `LaneCatalog` loading to `load_gateway_config`. After loading the serving config, cross-check against the catalog:
- Every serving lane must have a catalog entry with `prod_ready` status
- Every `prod_ready` catalog entry must have a serving artifact

The cross-validation uses `validate_serving_config(catalog, cfg)`. It runs at load time and raises `ConfigValidationError` on mismatch.

**Acceptance criteria:**
- [ ] AC1: `load_gateway_config` loads both catalog and serving config
- [ ] AC2: Cross-validation runs at load time
- [ ] AC3: Mismatches raise `ConfigValidationError` with a clear message
- [ ] AC4: Valid config loads successfully

**Test approach:** TDD. Tests in `test_lane_catalog.py` cover the cross-validation.

**Estimated effort:** S (~30 min)

### T-007: Tests in `test_lane_catalog.py`

**Files:**
- `backend/tests/unit/llm_gateway/test_lane_catalog.py` (new)

**Description:**
Comprehensive tests for the catalog + cross-validation:
- Catalog loads correctly
- `LaneCatalog` Pydantic model validates
- `validate_serving_config` raises on:
  - Serving lane not in catalog
  - Serving lane marked `dev_only` in catalog
  - `prod_ready` catalog entry with no serving artifact
- `validate_serving_config` is silent on valid config
- `SUPPORTED_AUTO_LANE_IDS` derivation is correct

**Acceptance criteria:**
- [ ] AC1: 10+ tests covering catalog loading, cross-validation, derivation
- [ ] AC2: Edge cases: empty catalog, missing entries, mismatched surfaces

**Test approach:** TDD. Use `tmp_path` to create test configs.

**Estimated effort:** M (~60 min)

### T-008: Migration plan for the 4 open PRs

**Files:**
- `.aidlc/migration_plan.md` (new — or part of `.aidlc/review.md`)

**Description:**
Document how each open PR will be re-based + re-migrated onto R0.5:

1. **PR #8739 (R0)**: 
   - Re-base onto R0.5
   - The R0 commit (091fa4ce5) added 15 new lane entries; most of them now move to the catalog
   - The R0 fix commit (0d3442de2) added the `placeholder` field; the 3 placeholders are now in the catalog only
   - The serving config keeps only `chat-structured`

2. **PR #8740 (R5a+R1)**: 
   - Re-base onto R0.5
   - The emitter's lane-to-task mapping shrinks from 15 lanes to 1 (chat-structured)
   - `LANE_TO_V3_TASK` dict updates accordingly
   - Tests for the smaller lane list

3. **PR #8744 (R5b)**:
   - Re-base onto R0.5
   - `SUPPORTED_AUTO_LANE_IDS` derives from the catalog (T-005 above)
   - The R5b hot-reload code is unchanged

4. **PR #8746 (R2)**:
   - Re-base onto R0.5
   - The smoke iterates over SUPPORTED_AUTO_LANE_IDS (now derived from the catalog)
   - Initially 1 lane (chat-structured); grows as lanes are promoted
   - `FakeProvider` test mock is unchanged

5. **PR #8748 (R3.1)**:
   - Re-base onto R0.5
   - The dual-path infrastructure is unchanged
   - `ShadowCutover` is lane-agnostic; works with any lane
   - Tests add: latency invariant (control returned in same time regardless of gateway)

**Acceptance criteria:**
- [ ] AC1: Migration plan documented in `.aidlc/migration_plan.md`
- [ ] AC2: Migration strategy is "re-base + re-migrate" (preserves review history)

**Test approach:** N/A (documentation task)

**Estimated effort:** S (~30 min)

### T-009: Plan-only updates for R3.2 and R4

**Files:**
- `.aidlc/r3_2_plan.md` (new — or part of `.aidlc/plan.md`)
- `.aidlc/r4_plan.md` (new — or part of `.aidlc/plan.md`)

**Description:**
Update the R3.2 and R4 plans to reflect the new architecture:

**R3.2 (chat-structured first cutover)**:
- First PR: wire `ShadowCutover` into the existing direct-provider call for `chat-structured`
- Use the catalog to know the lane's provider/model (or read from serving config)
- Run for 14 days in shadow mode
- Drop the control path in a follow-up PR

**R4 (cron with new promotion path)**:
- Cron uses the catalog as input
- Reads the catalog to find `dev_only` lanes with completed eval
- Generates a promotion PR (adds the lane + artifact to the serving config)
- Internal eval gate (separate work, "table for later") must pass before promotion
- Human review + merge (no auto-merge)
- Once merged, the serving config is updated (R5b's hot-reload picks it up)
- Real smoke is the actual gate (not fake)
- Eventually: cron can auto-promote once the promotion path is stable + comfortable

**Acceptance criteria:**
- [ ] AC1: R3.2 plan reflects "first cutover is chat-structured"
- [ ] AC2: R4 plan reflects "cron proposes, humans merge" + "internal eval as gate"
- [ ] AC3: R4 plan reflects "real smoke as the actual gate"

**Test approach:** N/A (planning task)

**Estimated effort:** S (~30 min)

### T-010: Final regression + AIDLC review

**Files:**
- `.aidlc/review.md` (update)

**Description:**
Confirm the broader gateway test suite still passes + write the AIDLC review.

**Acceptance criteria:**
- [ ] AC1: Full backend + gateway test suite green
- [ ] AC2: AIDLC review at `.aidlc/review.md` with 0 P0/P1

**Test approach:** N/A (regression + docs)

**Estimated effort:** S (~15 min)

## Sequencing

1. T-001: lanes_catalog.yaml
2. T-002: lane_catalog.py module
3. T-003 + T-004: serving config + artifacts (in parallel — same data structure)
4. T-005: resolver.py update
5. T-006: config_loader.py update
6. T-007: tests
7. T-008: migration plan (documentation)
8. T-009: plan-only updates for R3.2 and R4
9. T-010: final regression + review

Each task independently committable. Suggested commit structure:
- Commit 1: T-001 (lanes_catalog.yaml)
- Commit 2: T-002 (lane_catalog.py)
- Commit 3: T-003 + T-004 (lanes.yaml + route_artifacts.yaml updates)
- Commit 4: T-005 + T-006 (resolver.py + config_loader.py updates)
- Commit 5: T-007 (tests)
- Commit 6: T-008 + T-009 (migration plan + R3.2/R4 plan updates)
- Commit 7: T-010 (final cleanup)

## Risks

- **Breaking change for 4 open PRs**: R0.5 changes the architecture that the 4 open PRs were built on. The re-base + re-migrate is non-trivial. Mitigation: write a clear migration plan (T-008) so the re-base is mechanical.
- **Catalog file as single source of truth**: if the catalog drifts from the serving config, the cross-validation fires (good). But if the catalog has wrong info (e.g., a lane marked `prod_ready` when it shouldn't be), the serving config inherits the wrong state. Mitigation: catalog changes go through a PR (R4's promotion path).
- **Internal eval set not designed yet**: R4's promotion path needs the internal eval set ("table for later"). Until then, the cron can't actually propose promotions. Mitigation: R0.5 is plan-only for the eval set; a separate work item designs it.

## References

- `.aidlc/spec.md` — full acceptance criteria
- David's feedback message (2026-07-02)
- `PLAN.md` §R3, §R4
- `backend/llm_gateway/gateway/resolver.py` — current `SUPPORTED_AUTO_LANE_IDS`
- `backend/llm_gateway/gateway/config_loader.py` — current `load_gateway_config`
- `backend/llm_gateway/config/lanes.yaml` — current serving config
- `backend/llm_gateway/config/route_artifacts.yaml` — current artifacts
- Local AIDLC artifacts from R0/R5a/R1/R5b/R2/R3.1 — pattern for spec/plan/discipline