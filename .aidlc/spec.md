# Auto-Router Gateway — R0.5 (Lane Catalog + Serving Config Split)

## Origin (David's feedback, 2026-07-02)

> - I think we should separate lane catalog from serving config
> - Catalog is where we can list the future lanes / taxonomy we want
> - Serving config should only include lanes the gateway can actually execute today
> - **No prod-loadable placeholder route artifacts**
> - If a lane doesn't have the real surface / provider support / eval yet, keep it catalog-only
> - First real cutover should still be chat-structured / extraction-style work
> - I don't mind shadowing other lanes, but shadowing cannot affect user latency or behavior
> - MVP promotion path should be eval → promotion PR → human review / merge
> - Cron / automation can propose promotion PRs, but shouldn't directly mutate serving routes yet, once gateway is stable and we're comfortable with the promotion path we can then go to full auto
> - External benchmarks alone are not enough for promotion, we will need to have our own internal evaluation set for the stuff that we care about, at least as a gate (table for later)
> - Fake smoke is fine as a unit harness, but the actual gate should hit the real gateway path
> - Shadow cutover should return control immediately and observe gateway in the background

## Objective

Split the lane configuration into two distinct artifacts with clear ownership boundaries:

1. **Lane catalog** (`backend/llm_gateway/config/lanes_catalog.yaml`): the registry of ALL lanes — both serving and planned. Includes every lane id, regardless of provider/eval support. The catalog is the source of truth for "what lanes exist or will exist."
2. **Serving config** (`backend/llm_gateway/config/lanes.yaml` + `route_artifacts.yaml`): only lanes the gateway can actually execute today. No placeholder artifacts. Every entry must be a real, prod-ready model/provider combination.

Then:
- The R0 work (PR #8739) needs migration: remove 3 placeholder artifacts from the serving config
- R5a+R1 (PR #8740): re-migrate to use the catalog
- R3.1 (PR #8748): already correct on the dual-path semantics; needs minor doc updates
- R3.2 (next cycle): first cutover targets `omi:auto:chat-structured` (real, openai-compatible, no Anthropic dependency)
- R4 (cron): uses the catalog as input; proposes promotion PRs but doesn't directly mutate serving routes; uses internal eval set as a gate

## Commands (planned, post-approval)

```bash
cd backend && python -m pytest tests/unit/test_llm_gateway_*.py -v
# → all tests pass

# Validate the split
python -c "
from llm_gateway.gateway.config_loader import load_gateway_config
from llm_gateway.gateway.lane_catalog import load_catalog, validate_serving_config
catalog = load_catalog()
cfg = load_gateway_config()
validate_serving_config(catalog, cfg)  # cross-checks the split
"
```

## Project Structure (planned)

```
backend/llm_gateway/config/
  lanes_catalog.yaml            # NEW — registry of all lanes (serving + planned)
  lanes.yaml                    # MODIFY — only prod-ready lanes
  route_artifacts.yaml          # MODIFY — only real, executable artifacts
  feature_bundles.yaml          # UNCHANGED
backend/llm_gateway/gateway/
  lane_catalog.py               # NEW — load + validate the catalog
  resolver.py                   # MODIFY — SUPPORTED_AUTO_LANE_IDS derives from catalog
  config_loader.py              # MODIFY — required_lane_ids is sourced from the catalog
backend/llm_gateway/scripts/
  (no change yet — R4 is plan-only)
backend/tests/unit/llm_gateway/
  test_lane_catalog.py           # NEW — catalog + serving config tests
```

## Catalog Schema (proposed)

```yaml
# backend/llm_gateway/config/lanes_catalog.yaml
# The catalog of ALL lanes — both serving and planned. The serving config
# (lanes.yaml + route_artifacts.yaml) only includes prod_ready entries from
# this catalog.
lanes:
  - lane_id: omi:auto:chat-structured
    description: Chat structured extraction (pilot)
    surface: openai.chat_completions
    provider: openai
    model: gpt-4.1-mini
    provider_support_status: prod_ready
    eval_suite: backend/llm_gateway/eval/chat_extraction.v1.json
    notes: R0 pilot. Real provider. Real eval. Ready for first cutover.

  - lane_id: omi:auto:chat-extraction
    description: Chat extraction for structured data
    surface: openai.chat_completions
    provider: openai
    model: gpt-4.1-mini
    provider_support_status: prod_ready
    eval_suite: backend/llm_gateway/eval/chat_extraction.v1.json
    notes: Same model/provider as chat-structured. Distinct lane id.

  - lane_id: omi:auto:realtime-ptt
    description: Real-time push-to-talk (Claude)
    surface: openai.chat_completions
    provider: anthropic
    model: claude-sonnet-4-6
    provider_support_status: dev_only
    eval_suite: null
    notes: |
      Anthropic provider is not yet registered in the gateway's
      ProviderRegistry (which only supports openai). TODO(R3): register
      AnthropicCompatibleChatCompletionProvider. Until then, this lane
      CANNOT be in the serving config (R0.5 split). It stays in the
      catalog only.

  - lane_id: omi:auto:stt-realtime
    description: Speech-to-text (real-time)
    surface: unknown
    provider: tbd
    model: tbd
    provider_support_status: planned
    eval_suite: null
    notes: |
      Audio surface — the gateway doesn't have a STT endpoint yet.
      Stays in the catalog only. R3+ scope.

  - lane_id: omi:auto:transcription
    description: Audio transcription
    surface: unknown
    provider: tbd
    model: tbd
    provider_support_status: planned
    eval_suite: null
    notes: Audio surface. Catalog only.

  - lane_id: omi:auto:screenshot-embedding
    description: Screenshot embedding
    surface: unknown
    provider: tbd
    model: tbd
    provider_support_status: planned
    eval_suite: null
    notes: Embedding surface. Catalog only.

  # ... remaining lanes in the catalog, all with provider_support_status
  # reflecting their actual state:
  - lane_id: omi:auto:daily-summary
    description: Daily summary of conversations
    surface: openai.chat_completions
    provider: openai
    model: gpt-5.4-mini
    provider_support_status: dev_only
    eval_suite: null
    notes: |
      R0 placeholder. Catalog only. Needs internal eval suite before
      promotion to serving config.

  - lane_id: omi:auto:memories-extraction
    description: ...
    provider_support_status: dev_only
    ...

  # ... 11 more lanes, all dev_only
```

## Serving Config Schema (proposed — much smaller)

```yaml
# backend/llm_gateway/config/lanes.yaml
# The serving config — only lanes the gateway can execute today.
# Source: lanes_catalog.yaml entries with provider_support_status: prod_ready.
lanes:
  - lane_id: omi:auto:chat-structured
    surface: openai.chat_completions
    capabilities:
      text_input: true
      streaming: false
      structured_output: json_schema
      tools: false
    objective: {quality: 0.60, latency: 0.20, cost: 0.20}
    credential_policy: { ... }
    active_route: route.chat_structured.2026_07_01.001
    last_known_good: route.chat_structured.2026_07_01.001

  - lane_id: omi:auto:chat-extraction
    # ... same as before, but no placeholder artifacts
```

`route_artifacts.yaml` would contain only the real, executable artifacts — no placeholders for `stt-realtime`, `transcription`, `screenshot-embedding`.

## Code Style (planned)

Match existing `backend/llm_gateway/gateway/` style: Pydantic models, frozen dataclasses for config, `from __future__ import annotations`.

**Good example (existing):** `backend/llm_gateway/gateway/config_loader.py::GatewayConfig` is a typed Pydantic model. The new `LaneCatalog` model follows the same pattern.

**DO NOT do this:**
- Mix catalog entries with the `routes` (R0 schema) — keep them in separate files
- Add a placeholder artifact to the serving config (David's explicit "No prod-loadable placeholder route artifacts")
- Skip the cross-validation between catalog and serving config
- Modify the existing R0 work in this branch (R0.5 is a separate cycle; the re-migration is a follow-up)

## Testing Strategy (planned)

| Level | File | What it covers |
|---|---|---|
| Unit | `tests/unit/llm_gateway/test_lane_catalog.py` | Catalog loading; serving config cross-validation; rejection of placeholders in serving config; rejection of prod_ready entries in catalog without serving artifact |
| Regression | `tests/unit/test_llm_gateway_*.py` | Full suite must remain green |

## Boundaries (planned)

- **Always do:**
  - Keep catalog and serving config in separate files
  - Cross-validate: every serving lane must have a catalog entry; every catalog entry with `prod_ready` must have a serving artifact
  - Document the promotion path: catalog `dev_only` → internal eval gate → promotion PR → serving config (R4)
  - The `evidences.eval_report` field on RouteArtifact (already in R0 schema) points to the internal eval suite path
- **Ask first:**
  - Add new fields to the catalog schema (e.g., `eval_suite` field type, ownership tags)
  - Move the catalog to a different location (e.g., `backend/llm_gateway/catalog/lanes.yaml`)
  - Change the cross-validation semantics (e.g., allow `dev_only` catalog entries in serving config with a flag)
- **Never do:**
  - Add a placeholder artifact to the serving config
  - Skip the cross-validation
  - Use external benchmarks alone as the promotion gate (must be internal eval)
  - Auto-merge a promotion PR (R4 — cron proposes, humans merge)

## Acceptance Criteria (planned)

1. `backend/llm_gateway/config/lanes_catalog.yaml` exists. Lists ALL 16 lanes (1 R0 existing + 15 R0 new) with `provider_support_status` for each.
2. `backend/llm_gateway/config/lanes.yaml` contains ONLY `prod_ready` catalog entries (initially: `chat-structured` + `chat-extraction` if both are prod-ready; could be 1 lane initially).
3. `backend/llm_gateway/config/route_artifacts.yaml` contains ONLY artifacts for lanes in the serving config (no placeholders).
4. `backend/llm_gateway/gateway/lane_catalog.py` exposes `LaneCatalog`, `load_catalog()`, `validate_serving_config(catalog, cfg)`.
5. `SUPPORTED_AUTO_LANE_IDS` derives from the catalog (`prod_ready` entries only).
6. `load_gateway_config(required_lane_ids=...)` cross-checks the serving config against the catalog.
7. Promotion path is documented: `dev_only` catalog → internal eval gate → promotion PR → serving config (R4 cron proposes).
8. Tests in `test_lane_catalog.py` cover: catalog loading, cross-validation, placeholder rejection, prod_ready promotion.
9. No auto-merge in R4 — cron proposes, humans merge.
10. Internal eval set is a separate work ("table for later"); R0.5 plans its location and schema.

## Day-one invariants (planned)

1. **No prod-loadable placeholder route artifacts** — the serving config has only real, executable lanes.
2. **Catalog is the source of truth** — every lane is in the catalog; the serving config is a subset (prod_ready entries only).
3. **The split is enforced** — `load_gateway_config` rejects configs that violate the split.
4. **The promotion path is human-in-the-loop** — R4's cron proposes, humans merge.
5. **Shadowing cannot affect user latency** — R3.1's design is already correct; R3.2's tests must assert the latency invariant (control returned in the same time as before, regardless of gateway behavior).

## Out of Scope (planned)

- R3.2 (actual cutover) — separate cycle, gated on R0.5 + R3.1 merging
- R4 (cron implementation) — plan-only update as part of R0.5; implementation in a separate cycle
- Internal eval set design — "table for later"; a separate work item
- The 4 open PRs (#8739, #8740, #8744, #8746, #8748) — re-migration is a follow-up; R0.5 plans the migration strategy

## Open Questions (planned)

- **Catalog file location**: `backend/llm_gateway/config/lanes_catalog.yaml` (alongside `lanes.yaml`)? Default; confirm.
- **Catalog schema fields**: `{lane_id, description, surface, provider, model, provider_support_status, eval_suite, notes}`. Plus `promoted_at` for tracking when a lane moved to `prod_ready`. Confirm.
- **PR migration strategy**: re-base + re-migrate the 4 open PRs (preserves review history). Confirm.

## References

- David's feedback message (2026-07-02)
- `PLAN.md` §R3 — the cutover that depends on the split
- `PLAN.md` §R4 — the cron that uses the catalog
- `backend/llm_gateway/gateway/resolver.py` — current `SUPPORTED_AUTO_LANE_IDS` (needs to derive from the catalog)
- `backend/llm_gateway/gateway/config_loader.py` — current `load_gateway_config` (needs `required_lane_ids` cross-check)
- `backend/llm_gateway/config/lanes.yaml` — current serving config (needs to remove placeholders)
- `backend/llm_gateway/config/route_artifacts.yaml` — current artifacts (needs to remove placeholders)
- Local AIDLC artifacts from R0/R5a/R1/R5b/R2/R3.1 — pattern for spec/plan/discipline