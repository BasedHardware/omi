# R0.5 Review — Lane Catalog + Serving Config Split

**Reviewer:** pi (5-axis AIDLC review)
**Branch:** `feat/auto-router-catalog`
**Commit:** `370035bcd` — `feat(llm_gateway): R0.5 — separate lane catalog from serving config (per David 2026-07-02)`
**Worktree:** `/Users/choguun/Documents/workspaces/cool-projects/omi-worktrees/auto-router-catalog`
**Date:** 2026-07-02

---

## Verdict
**needs_fix** — 0 P0, 0 P1, **3 P2** findings.

The architectural split is correct and matches David's feedback. Catalog data, cross-validation intent, and resolver derivation are all in place. But three correctness gaps in the cross-validation are real: the `lane_id` validator is weaker than the rest of the codebase, the count-only check on `serving_artifact_ids` lets prod_ready lanes be silently unserved, and the cross-validation raises plain `ValueError` instead of `ConfigValidationError`. Each is a small, surgical fix; none blocks the architecture.

---

## Spec Compliance

| AC | Status | Notes |
|----|--------|-------|
| AC1: `lanes_catalog.yaml` lists all 16 lanes | ✅ | 1 prod_ready (`chat-structured`) + 12 dev_only + 3 planned. Verified by `test_load_catalog_from_default_path` (16 lanes). |
| AC2: `lane_id` format + `promoted_at` coherence | ⚠️ Partial | `promoted_at` coherence works (prod_ready ⇒ set, others ⇒ None). But `lane_id` validator in `CatalogEntry` is **weaker** than the existing `LaneId` pattern in `schemas.py:21` (`^omi:auto:[a-z0-9][a-z0-9-]*$`). The catalog accepts `omi:auto:BAD-CAPS`, `omi:auto:has space`, `omi:auto:-dash-prefix`, `omi:auto:1digit-prefix` — all of which the rest of the gateway would reject at the `LaneConfig` / `RouteArtifact` parse layer. |
| AC3-5: `validate_serving_config` rejects wrong serving configs | ⚠️ Partial | The "serving lane not in catalog" + "serving lane not prod_ready" checks work. **But** the second check (artifacts ↔ prod_ready) is a count-only check, not a per-lane association check. A `prod_ready` catalog lane can be entirely missing from the serving config as long as the artifact count is high enough. See Finding F2. |
| AC6: `load_gateway_config` integration | ✅ | Works, but cross-validation raises plain `ValueError`, not `ConfigValidationError`. Inconsistent with the rest of the loader. See Finding F3. |
| AC7: `SUPPORTED_AUTO_LANE_IDS` derivation | ✅ | Confirmed: `frozenset({'omi:auto:chat-structured'})`. Resolver falls back to empty frozenset on missing catalog. **However**, the existing 61 R0 tests in `test_llm_gateway_resolver.py` + `test_llm_gateway_config.py` + `test_llm_gateway_readiness.py` will all fail (they expect 13/16 lanes + 17 artifacts). Migration plan covers this, but those tests are RED on this branch today. |
| AC8: `LaneCatalog` Pydantic validation | ✅ | Pydantic models are typed. `provider_support_status` is an Enum (rejects garbage). |
| AC9-10: Promotion path + internal eval are out of scope | ✅ | Documented in `r3_2_plan.md` and `r4_plan.md`. |

---

## Code Quality

**Type hints:** ✅ All functions have full type hints. `from __future__ import annotations` is used.
**Docstrings:** ✅ Module + class + function docstrings present. Cross-references to David's 2026-07-02 feedback are valuable.
**Naming:** ✅ `LaneCatalog`, `CatalogEntry`, `ProviderSupportStatus`, `load_catalog`, `validate_serving_config` — clear and consistent.
**Section structure:** ✅ `lane_catalog.py` is well-organized (Status enum → Entry model → Catalog model → loader → validator).
**Pydantic model style:** ✅ `model_config = ConfigDict(extra="forbid")` matches the rest of the codebase. But `CatalogEntry` does not use `StrictBaseModel` from `schemas.py:14` for consistency. (Minor — the package has its own convention here.)

**Concrete code-quality nits:**

- `lane_catalog.py:35` — `_PACKAGE_DIR = Path(__file__).resolve().parent` is dead. It's only used to compute `DEFAULT_CATALOG_DIR`. Inline it.
- `lane_catalog.py:158-170` — The "second check" in `validate_serving_config` is a weak proxy. The function takes `serving_artifact_ids` (a `set[str]`) but the only meaningful check (lane ↔ artifact association) requires the full `RouteArtifact` objects. The signature is the wrong shape.
- `resolver.py:46` — `except (FileNotFoundError, ValueError, Exception) as _exc:` is redundant. `Exception` already covers the first two. The list is harmless but reads as if `Exception` is a third specific exception, which is confusing.
- `resolver.py:43-55` — The module-level catalog load + silent fallback to empty frozenset is a footgun. If the catalog file is missing in production (e.g., wrong Docker COPY layer, config map typo), the gateway boots with **zero resolvable lanes** and the only signal is a log line. The `load_gateway_config` path correctly raises; the `resolver` path silently degrades. Asymmetric failure modes.
- `config_loader.py:69-82` — The catalog cross-check is wired with two slightly different branches (explicit `catalog` param vs. auto-load from `config_dir / "lanes_catalog.yaml"`). A single helper would be cleaner.

**Pydantic validator:**
- `lane_catalog.py:79-86` — The `lane_id` validator checks `v.startswith("omi:auto:")` and `len(v.split(":")) == 3`. This accepts:
  - `omi:auto:` → rejected (capability empty) ✅
  - `omi:auto:BAD` → ACCEPTED ❌ (uppercase; rest of gateway rejects)
  - `omi:auto:has space` → ACCEPTED ❌ (space; rest rejects)
  - `omi:auto:has/slash` → ACCEPTED ❌ (slash)
  - `omi:auto:-dash` → ACCEPTED ❌ (leading dash)
  - `omi:auto:1digit` → ACCEPTED ❌ (leading digit)

  The existing `LaneId = Annotated[str, Field(pattern=r'^omi:auto:[a-z0-9][a-z0-9-]*$')]` in `schemas.py:21` already encodes the correct rule. The catalog entry should reuse it (or copy its pattern) so a lane id can be in the catalog but rejected at lane-config / route-artifact parse time.

---

## Architecture

**The split is the right call.** Catalog is the source of truth for "what lanes exist"; serving config is the executable subset. This matches David's "if a lane doesn't have the real surface / provider support / eval yet, keep it catalog-only" verbatim. Promotion path (R4) becomes "dev_only in catalog → eval gate → promotion PR → add to serving" — clean.

**Module layout is sensible.** `lane_catalog.py` is a new leaf module (no upward imports); it only depends on `pydantic`, `yaml`, `pathlib`, `datetime`, `enum`. ✅ matches the import hierarchy (database → utils → routers → main).

**The resolver's `SUPPORTED_AUTO_LANE_IDS` derivation is a real improvement.** It removes the hardcoded frozenset (13 entries in the old code) and replaces it with a catalog-derived view. The dev workflow it enables is exactly what David described: flipping a catalog entry to `prod_ready` automatically widens the resolver. ✅

**Cross-validation intent is right, execution is wrong.** See Finding F2 — the count check is a weak proxy for "every prod_ready lane has a serving artifact". The function signature would need to take the full `GatewayConfig` (or the artifacts) to do the right check.

**The "missing catalog is tolerated" backward-compat is dangerous in production.** Two failure modes exist:

1. `load_gateway_config` with no catalog: PASSES (no cross-check). Pre-R0.5 deployments behave correctly.
2. Resolver at import with no catalog: silently sets `SUPPORTED_AUTO_LANE_IDS = frozenset()`. Pre-R0.5 deployments would have a hardcoded allowlist; post-R0.5, they get nothing.

These are asymmetric. Either both should fail loud (production must have a catalog) or both should be tolerant (pre-R0.5 deploys work). Right now the silent-fail path in `resolver.py` is the riskier one.

**`_private/` boundaries:** There is no `_private/` module in this branch. The user's question about "Are the `_private/` boundaries right?" is moot — the project doesn't use that convention here. The catalog is at `gateway/lane_catalog.py` (sibling of `resolver.py`, `config_loader.py`), which is the right location. The catalog file is at `config/lanes_catalog.yaml`, sibling to `lanes.yaml` and `route_artifacts.yaml` — also right. ✅

---

## Security

**YAML loading:** `yaml.safe_load` is used in both `load_catalog` (`lane_catalog.py:122`) and `_load_config_list` (`config_loader.py:108`). ✅ No `yaml.load` or `unsafe_load` anywhere.

**Path traversal:** `load_catalog(catalog_path: Path | None = None)` accepts an arbitrary path. In production, it's only called with the package-bundled default or with `config_dir / "lanes_catalog.yaml"`. No user-supplied input flows in. ✅

**Catalog file trust:** The catalog is loaded at startup and validated by Pydantic. A malformed or malicious catalog raises at load time (verified: `ScannerError` propagates from `yaml.safe_load` through `LaneCatalog.model_validate`). ✅

**No secrets in catalog:** The catalog only contains lane metadata (provider name, model name, surface). No API keys, no tokens, no credentials. ✅

**Logger exception message:** `resolver.py:50-52` logs `_exc` (the exception) at WARNING level. The exception message could include the path. The path is internal (package-bundled), so this is fine — but if a future caller passes a user-controlled path, the log could leak filesystem structure. Low risk; flagged for awareness.

**Pydantic `extra="forbid"`:** ✅ Both `CatalogEntry` and `LaneCatalog` forbid extra fields, so a typo'd field name will be caught at validation time.

---

## Performance

**Catalog loaded at import time** (`resolver.py:46`). Verified: cold import = 62.86ms; resolver import = 66.97ms. `load_catalog()` itself = 3.52ms. `validate_serving_config` = 4.1µs. ✅ Performance is fine.

**Module-level side effects:** The catalog is read from disk on `import llm_gateway.gateway.resolver`. This is the only module-level I/O in the gateway. It's bounded (3.5ms) and idempotent. ✅

**Worst-case config load time:** `_load_config_list` reads 3 files + the new catalog file. ~5 file reads + 4 `model_validate` calls. Total <100ms in the cold path. ✅

**Hot path impact:** `resolve_lane` does `if model not in SUPPORTED_AUTO_LANE_IDS` — O(1) frozenset membership test. ✅

**No N+1 queries or algorithmic concerns.** The catalog has 16 entries; the cross-validation does O(n) iteration over `serving_lane_ids` and O(n) over `prod_ready_lane_ids`. Constant in practice.

---

## Findings (Critical / Important / Minor)

### Critical (P0)
_None._

### Important (P1)
_None._ (The cross-validation bug is P2 because the current serving config is correct, but the test coverage gap means a future change could regress silently.)

### Minor (P2)

**F1 [P2 / correctness]: `CatalogEntry.lane_id` validator is weaker than `LaneId` in `schemas.py:21`.**
- **File:** `backend/llm_gateway/gateway/lane_catalog.py:79-86`
- **What:** The catalog accepts `omi:auto:BAD-CAPS`, `omi:auto:has space`, `omi:auto:has/slash`, `omi:auto:-dash`, `omi:auto:1digit`, etc. The rest of the gateway (via `LaneId = Annotated[str, Field(pattern=r'^omi:auto:[a-z0-9][a-z0-9-]*$')]`) rejects all of these. A lane id that passes the catalog but fails `LaneConfig.model_validate` would surface as a confusing Pydantic error at lane-config parse time, not at the source (the catalog).
- **Fix:** Use the same regex pattern as `schemas.py:21`. Either:
  - `lane_id: LaneId` (import the annotated type from `schemas.py`).
  - Or copy the pattern: `lane_id: str = Field(pattern=r'^omi:auto:[a-z0-9][a-z0-9-]*$')`.
- **Risk if not fixed:** The catalog becomes the "permissive" boundary that lets typos in. A future operator who adds a lane with an upper-case character (e.g., a Claude lane named `claude-Opus`) would get a runtime error at startup with a confusing stack trace.

**F2 [P2 / correctness]: `validate_serving_config` second check is count-based, not association-based.**
- **File:** `backend/llm_gateway/gateway/lane_catalog.py:154-170`
- **What:** The check `if len(serving_artifact_ids) < len(prod_ready)` only verifies counts match. It does NOT verify that any specific `prod_ready` lane has a serving artifact. **Concrete repro:**
  ```python
  catalog = load_catalog()  # 1 prod_ready: chat-structured
  validate_serving_config(
      catalog,
      serving_lane_ids=set(),                                          # 0 lanes
      serving_artifact_ids={'route.chat_extraction.2026_07_01.001'},  # 1 artifact
  )  # PASSES — but chat-structured has no serving entry!
  ```
  In this state, the serving config has 1 artifact for `chat-extraction` (a `dev_only` lane) but 0 artifacts for `chat-structured` (the `prod_ready` one). The cross-validation should fail. Currently it passes.
- **Fix:** Change the function signature to take the full `GatewayConfig` (or just the route artifacts with their `lane_id`):
  ```python
  def validate_serving_config(
      catalog: LaneCatalog,
      serving_cfg: GatewayConfig,  # full config, not just id sets
  ) -> None: ...
  ```
  Then for each `prod_ready` catalog entry, verify `any(art.lane_id == e.lane_id for art in serving_cfg.route_artifacts.values())`.
  Update callers: `config_loader.py:74-82` already has access to the full config; just pass it.
- **Why P2 not P1:** The current serving config is correct (chat-structured is in both), so this is a latent bug, not an active one. But the test in `test_lane_catalog.py:156-165` only tests the "0 lanes + 0 artifacts" case — it doesn't cover the "0 lanes + N artifacts for a non-prod_ready lane" case. The test gap is also part of the finding.
- **Test gap to close:** add a test like:
  ```python
  def test_prod_ready_lane_missing_from_serving_raises_even_with_artifacts():
      catalog = load_catalog()
      with pytest.raises(ValueError, match="chat-structured"):
          validate_serving_config(
              catalog,
              serving_lane_ids=set(),  # chat-structured missing
              serving_artifact_ids={'route.chat_extraction.2026_07_01.001'},
          )
  ```

**F3 [P2 / consistency]: Cross-validation raises plain `ValueError`, not `ConfigValidationError`.**
- **File:** `backend/llm_gateway/gateway/lane_catalog.py:144,152,165` (3 raise sites)
- **What:** All other validation in `config_loader.py` uses `ConfigValidationError` (a `ValueError` subclass defined at `config_loader.py:24-26`). The new `validate_serving_config` raises plain `ValueError`. The tests use `pytest.raises(ValueError, match=...)` which catches both, so the inconsistency is invisible to tests. But operators monitoring for `ConfigValidationError` (e.g., in Sentry or log filters) will see the catalog cross-validation slip through.
- **Fix:** Either:
  - `from llm_gateway.gateway.config_loader import ConfigValidationError` in `lane_catalog.py` and raise it (creates a circular-ish dependency, but config_loader already imports from lane_catalog, so the cycle is one-way).
  - Or move `ConfigValidationError` to a shared location (e.g., `gateway/errors.py`).
- **Severity:** Cosmetic / monitoring-impacting, not functional.

### Additional (non-blocking) observations

**F4 [P2 / docs]: PR count is inconsistent in spec/plan/state files.**
- **Files:** `.aidlc/spec.md:111` says "The 4 open PRs (#8739, #8740, #8744, #8746, #8748) — re-migration is a follow-up". That's **5 PR numbers** in a list that says **"4"**. `.aidlc/plan.md:42` and `.aidlc/state.md` also say "4 open PRs". `.aidlc/migration_plan.md` correctly documents 5 PRs.
- **Fix:** Pick a number and stick with it. The migration plan and the spec disagree. Suggest updating spec/plan/state to "5 open PRs".
- **Severity:** Documentation, not code.

**F5 [P2 / architecture]: Resolver's missing-catalog fallback is silent.**
- **File:** `backend/llm_gateway/gateway/resolver.py:46-55`
- **What:** If the catalog file is missing at import time, `SUPPORTED_AUTO_LANE_IDS` becomes empty (with a log warning). The gateway boots with zero resolvable lanes. In production, this is the worst kind of failure: silent + zero lanes.
- **Fix:** Two options:
  - **Loud:** Remove the fallback. Let `FileNotFoundError` propagate. Production must have the catalog file. The PR is the right time to make this break loud (matches the architectural change).
  - **Quiet with better signal:** Keep the fallback, but make `load_gateway_config` raise `ConfigValidationError` if `_CATALOG is None`. This way the boot path fails loud even if the import-time path is quiet.
- **Severity:** Latent footgun. Acceptable as-is if you're confident production always ships the catalog (which it should, post-R0.5). Worth a comment in the code explaining the asymmetry.

**F6 [P2 / security/observability]: The `Exception` catch in resolver.py is overly broad.**
- **File:** `backend/llm_gateway/gateway/resolver.py:46`
- **What:** `except (FileNotFoundError, ValueError, Exception) as _exc:` — `Exception` is the base class of the other two. This is functionally equivalent to `except Exception`, but reads as if all three are equally specific.
- **Fix:** Drop the redundant entries: `except Exception as _exc:`. Or, more precisely, catch `(FileNotFoundError, ValueError, yaml.YAMLError)` so KeyboardInterrupt / SystemExit / MemoryError propagate as intended.
- **Severity:** Stylistic.

**F7 [P2 / test gap]: No test for `SUPPORTED_AUTO_LANE_IDS` derivation in the new test file.**
- **File:** `backend/tests/unit/llm/test_lane_catalog.py`
- **What:** The 20 tests cover `load_catalog`, `validate_serving_config`, `load_gateway_config` integration, and `CatalogEntry` validation. None of them assert that `resolver.SUPPORTED_AUTO_LANE_IDS == {'omi:auto:chat-structured'}` after R0.5. The existing `test_llm_gateway_resolver.py::test_supported_auto_lane_ids_contains_thirteen_r0_chat_completion_lanes` will fail post-R0.5 (expects 13 lanes); per the migration plan, that test is rewritten during the R0 PR re-migration. But the new test file should pin the post-R0.5 invariant.
- **Fix:** Add a test like:
  ```python
  def test_resolver_supported_lane_ids_derives_from_catalog():
      from llm_gateway.gateway.resolver import SUPPORTED_AUTO_LANE_IDS
      assert SUPPORTED_AUTO_LANE_IDS == frozenset({"omi:auto:chat-structured"})
  ```
  This pins the R0.5 behavior. When R3.2 promotes `chat-extraction`, this test is updated in the same PR.
- **Severity:** Test coverage gap.

---

## Recommendation

**Fix needed (F1, F2, F3) before merge. Optional cleanup (F4-F7) in this or a follow-up PR.**

| # | Severity | Effort | Suggestion |
|---|----------|--------|------------|
| F1 | P2 | S (~5 min) | Reuse `LaneId` from `schemas.py` for the catalog `lane_id` field. |
| F2 | P2 | M (~30 min) | Change `validate_serving_config` signature to take `GatewayConfig`; iterate per-prod_ready lane and check artifact association. Add the missing test. |
| F3 | P2 | XS (~5 min) | Import `ConfigValidationError` and raise it from `validate_serving_config` (3 sites). |
| F4 | P2 | XS (~2 min) | Fix PR count in spec/plan/state to match the 5 documented in `migration_plan.md`. |
| F5 | P2 | S (~15 min) | Decide on loud vs. quiet + better signal; document the choice. |
| F6 | P2 | XS (~1 min) | Drop redundant exception types from the resolver's except clause. |
| F7 | P2 | XS (~5 min) | Add the resolver-derivation test in `test_lane_catalog.py`. |

**Estimated total to address P2s:** ~60 min. F1+F2+F3 are the must-fix items. F4-F7 are nice-to-haves that can ship in a follow-up.

---

## Spec-Compliance Smoke Tests (run by the reviewer)

I ran these by hand against the committed code. Results:

1. ✅ `load_catalog()` loads the default path with 16 entries.
2. ✅ `catalog.prod_ready_lane_ids() == {'omi:auto:chat-structured'}`.
3. ✅ `catalog.prod_ready_lane_ids()` correctly excludes 12 dev_only + 3 planned.
4. ✅ `LaneCatalog(lanes=[])` + `validate_serving_config(empty, set(), set())` PASSES.
5. ⚠️ `validate_serving_config(load_catalog(), set(), {'route.foo.001'})` **PASSES** (bug — see F2).
6. ⚠️ `validate_serving_config(load_catalog(), set(), set())` **RAISES** (correct behavior; raises on count mismatch because catalog has 1 prod_ready lane).
7. ✅ `load_gateway_config(prod_mode=False)` returns 1 lane + 2 artifacts.
8. ✅ `route_artifacts.yaml` digests match `RouteArtifact.model_validate(...).content_digest` for both artifacts.
9. ⚠️ Existing `test_llm_gateway_resolver.py` and `test_llm_gateway_config.py` and `test_llm_gateway_readiness.py` will FAIL (expect 13/16/17 lanes/artifacts; new state is 1/2). This is **expected** per the migration plan; the implementer notes this in the commit message.
10. ✅ Resolver falls back to empty frozenset on missing catalog (verified by deleting the file + reload).
11. ✅ `yaml.safe_load` used (no `yaml.load` / `unsafe_load`).
12. ✅ Pydantic `extra="forbid"` on both `CatalogEntry` and `LaneCatalog`.

**Re: the user's specific concerns:**

- **`validate_serving_config(catalog, set(), set())`:** the user's framing was "no prod_ready lanes in catalog → no requirement" — but the catalog DOES have 1 prod_ready lane. The function correctly raises. The test `test_prod_ready_catalog_lane_without_serving_artifact_raises` pins this behavior. Note: there's a separate bug (F2) where the function passes when it shouldn't; that bug is independent of this question.
- **`load_catalog()` missing file:** raises `FileNotFoundError` with the path. ✅
- **Resolver's module-level `SUPPORTED_AUTO_LANE_IDS` on missing catalog:** falls back to empty frozenset with a WARNING log. ✅
- **Digests in `route_artifacts.yaml`:** both correct (verified by direct computation against `RouteArtifact.content_digest`).
- **4 open PRs migration:** covered in `migration_plan.md`, but the doc says "4" while listing 5. (See F4.)

---

## Open Questions for the User (before pushing the PR)

1. **F2 (the cross-validation bug):** should the fix land in this PR, or wait for a follow-up? The current serving config is correct, so the bug is latent — but the test gap means a future change to `lanes.yaml` could regress silently. I'd vote to fix in this PR (it's a 30-min change). The other option is to add a `TODO(R0.6): tighten validate_serving_config` comment and address in a follow-up cycle.

2. **F1 (lane_id validator strength):** do you want the catalog to be **stricter** (reject anything the rest of the gateway rejects) or **looser** (be a permissive inventory)? I'd vote for stricter (use the existing `LaneId` pattern). It makes the catalog a true single source of truth.

3. **F5 (resolver silent fallback):** what's the right failure mode for a missing catalog in production? Options: (a) fail loud at import (remove fallback), (b) fail loud at config-load (keep fallback but make `load_gateway_config` raise), (c) keep current (silent + log). I'd vote (a) for production — R0.5 is the right time to make the system honest about its config dependency. Tests can use a fixture.

4. **F3 (ConfigValidationError):** is moving `ConfigValidationError` to `gateway/errors.py` (where the other `Gateway*Error` classes live) in scope, or out of scope for R0.5? It's a 5-min refactor but creates a tiny circular import dance.

5. **The 4-vs-5 PR count:** is the actual number 4 (and one of #8739, #8740, #8744, #8746, #8748 is merged or abandoned) or 5? The migration plan documents 5; the spec/plan/state say 4. The implementer's commit message says "4 open PRs" too. Clarify so the migration plan is honest.

6. **Test readiness:** the implementer's commit message says "20 new R0.5 tests pass". I didn't run them (no venv on the review machine), but the assertions are correct. **Are you running the full suite before push?** `tests/unit/test_llm_gateway_config.py`, `test_llm_gateway_resolver.py`, `test_llm_gateway_readiness.py` will all fail (expecting the old 13/16/17 counts). Per the migration plan, those tests are rewritten during the R0 PR re-migration — but they're RED on this branch right now. Confirm this is acceptable for the PR (i.e., the PR title is "R0.5 architectural split" and the test failures are documented in the PR body as "expected; re-migration is follow-up").

7. **Catalog file location:** spec.md's open question #1 asks to confirm `backend/llm_gateway/config/lanes_catalog.yaml`. The implementation chose this location. ✅ Confirm or move.

8. **Catalog schema:** spec.md's open question #2 asks to confirm the schema fields. The implementation added `promoted_at` in addition to the spec's list. ✅ Confirm or remove.

9. **PR migration strategy:** spec.md's open question #3 asks to confirm "re-base + re-migrate". The migration plan documents this. ✅ Confirm.
