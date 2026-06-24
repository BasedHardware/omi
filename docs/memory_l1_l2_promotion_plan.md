# memory L1 to L2 Agentic Promotion Plan

## Locked Decisions

- Scheduled cron sweep promotes completed sessions only. It never promotes mid-session.
- The batch unit is one completed session, with optional adjacent-session grouping for the same user.
- Promotion receives real grounding: ordered L1 items, vector-near durable memories, a bounded graph snapshot from folded ledger facts, and the observed ledger head.
- Reconciliation is an LLM tool-calling loop. The model must call read tools before durable writes and must call `write_memory` for every ledger write.
- `write_memory` is only a wrapper over validated append-only memory tools. It returns either a commit ID or a validation error so the model can correct within budget.
- Rollout is whitelisted users, forward-only first. Backfill remains flag-gated until forward memory formation is proven with real users.
- This is a new memory pipeline. No compatibility is required between prior internal pipeline versions; compatibility is required only for whitelist promotion from base Omi.

## Target Architecture

1. `jobs.l2_promotion_selector` finds unpromoted L1 items for completed sessions and groups adjacent sessions under configured caps.
2. `utils.memory.promotion_bundle_builder` builds `promotion_bundle.v1` with session L1, vector seed, bounded graph context, evidence packets, and `observed_head_commit_id`.
3. `jobs.l2_promotion_worker` enforces the grounding guard. A headed ledger with empty vector seed and empty graph edges is `ungrounded_promotion`.
4. `utils.memory.l2_promotion_agent` runs a bounded tool loop using `AgentSafetyGuard`.
5. The LLM can call `vector_search`, `graph_walk`, `fetch_fact`, `list_session_l1`, `write_memory`, and `finish`.
6. `utils.memory.memory_tools` validates writes, rejects malformed or ungrounded memory, persists non-active routes, and appends ledger commits.
7. `l2_promotion_trace.v1` records bundle, tool calls, decisions, commit IDs, errors, and safety stats.

## Acceptance Gates

- **G1 Agentic proof:** every durable ledger write is caused by an LLM-issued `write_memory` tool call. An LLM that emits zero tool calls writes nothing.
- **G2 Grounding proof:** the worker injects real grounding. A populated ledger yields non-empty vector or graph context. A headed-but-empty bundle raises in dev/benchmark and returns telemetry-shaped `ungrounded_promotion` in prod.
- **G3 No dead tools:** every registered promotion tool is exercised through the LLM tool-call path in tests.
- **G4 Safety bounded:** the loop uses `AgentSafetyGuard` for max tool calls, loop detection, and context-size checks.
- **G5 Drift guard:** decision semantics come from the PROMOTION RUBRIC in `utils.llm.durable_memory_patches`; benchmark code calls the product agent rather than a copy.
- **G6 No reward-hacking:** empty content, missing subject, malformed predicates, unresolved evidence, and wrong-subject writes are rejected by tools. The agent must review/reject instead of fabricating evidence or subjects.

## Data Integrity Rules

- Empty, missing, or unsupported memories are rejected.
- Evidence refs must resolve to the promotion bundle.
- Subject is required for write decisions that create or alter durable facts.
- Targeted updates must preserve subject integrity unless the patch routes to a non-active outcome.
- Head conflicts are surfaced and may be retried once by `memory_tools`; silent overwrite is forbidden.
- Non-active decisions are persisted through `persist_non_active_route_for_patch`.

## Initial Defaults

- `max_sessions_per_batch`: 3
- `max_l1_items_per_batch`: 50
- completed-session inactivity fallback: 30 minutes after latest L1 item
- tool-call budget: 15 calls per bundle
- vector seed: top 8 durable memories
- graph snapshot: 2 hops, 80 nodes, 120 edges

These values are intentionally conservative and config-driven.

## Rollout

Forward mode is the only default mode. A user must be present in the L2 promotion allowlist before the worker produces work. Backfill additionally requires `enable_backfill=True` and a per-run mode of `backfill`.

## Benchmark Alignment

Benchmark scripts may package evidence and export cards, but product L2 decisions must come from `utils.memory.l2_promotion_agent.run_l2_promotion_agent`. Reports should include decision mix, tool-call counts, grounding non-empty rate, idempotency stability, and replayable promotion traces.
