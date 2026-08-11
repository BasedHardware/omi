import { describe, expect, test } from "bun:test";

import {
  MEMORY_STRATEGY_VERSION,
  assertMintedMemoryStrategyAssignment,
  createMemoryStrategyAssigner,
  defineMemoryStrategyAssignmentPolicy,
  registerMemoryStrategy,
  type MemoryStrategyDefinition,
} from "./strategy-assignment";

const definition = (
  strategyId: string,
  overrides: Partial<MemoryStrategyDefinition["coordinates"]> = {},
): MemoryStrategyDefinition => ({
  version: MEMORY_STRATEGY_VERSION,
  strategy_id: strategyId,
  work_kind: "formation",
  coordinates: {
    strategy_version: "formation:v1",
    model_version: "deepseek-flash:v1",
    prompt_version: "formation-prompt:v1",
    policy_version: "memory-policy:v1",
    code_version: "code:v1",
    schema_version: "schema:v1",
    tokenizer_version: "tokenizer:v1",
    tool_version: "none",
    result_contract_version: "formation-result:v2",
    speaker_strategy_version: "speaker-frame:v1",
    boundary_strategy_version: "boundary:deepseek:v1",
    ...overrides,
  },
});
const registry = () => [
  registerMemoryStrategy(definition("strategy:authority")),
  registerMemoryStrategy(definition("strategy:shadow-a", { prompt_version: "formation-prompt:v2" })),
  registerMemoryStrategy(definition("strategy:shadow-b", { model_version: "glm-4.7:v1" })),
];

const policy = (strategies = registry(), shadowCandidates = [
  { strategy_id: "strategy:shadow-a", basis_points: 10_000 },
  { strategy_id: "strategy:shadow-b", basis_points: 0 },
]) => defineMemoryStrategyAssignmentPolicy({
  policy_id: "formation-policy:v1",
  work_kind: "formation",
  unit_kind: "session",
  key_version: "assignment-key:v1",
  authority_strategy_id: "strategy:authority",
  shadow_candidates: shadowCandidates,
}, strategies);

describe("memory strategy registry", () => {
  test("every result-affecting coordinate participates in immutable execution identity", () => {
    const original = registerMemoryStrategy(definition("strategy:one"));
    for (const [coordinate, value] of Object.entries(original.coordinates)) {
      const changed = registerMemoryStrategy(definition("strategy:one", {
        [coordinate]: `${value}:changed`,
      }));
      expect(changed.execution_contract_digest, coordinate)
        .not.toBe(original.execution_contract_digest);
    }
    expect(Object.isFrozen(original)).toBe(true);
    expect(Object.isFrozen(original.coordinates)).toBe(true);
  });

  test("policy lookup is closed over one work kind and immutable strategy ids", () => {
    const strategies = registry();
    expect(() => defineMemoryStrategyAssignmentPolicy({
      policy_id: "bad", work_kind: "formation", unit_kind: "session",
      key_version: "key:v1", authority_strategy_id: "missing", shadow_candidates: [],
    }, strategies)).toThrow("unknown_authority_strategy");
    expect(() => defineMemoryStrategyAssignmentPolicy({
      policy_id: "bad", work_kind: "formation", unit_kind: "session",
      key_version: "key:v1", authority_strategy_id: "strategy:authority",
      shadow_candidates: [{ strategy_id: "strategy:authority", basis_points: 1 }],
    }, strategies)).toThrow("authority_cannot_be_shadow");
    expect(() => defineMemoryStrategyAssignmentPolicy({
      policy_id: "bad", work_kind: "formation", unit_kind: "session",
      key_version: "key:v1", authority_strategy_id: "strategy:authority",
      shadow_candidates: [
        { strategy_id: "strategy:shadow-a", basis_points: 1 },
        { strategy_id: "strategy:shadow-a", basis_points: 2 },
      ],
    }, strategies)).toThrow("duplicate_shadow_strategy");
  });
});

describe("deterministic memory strategy assignment", () => {
  test("same unit is byte-stable, policy order is irrelevant, and allocation bounds are exact", () => {
    const strategies = registry();
    const assigner = createMemoryStrategyAssigner(new Uint8Array(32).fill(7));
    const firstPolicy = policy(strategies);
    const reorderedPolicy = policy(strategies, [
      { strategy_id: "strategy:shadow-b", basis_points: 0 },
      { strategy_id: "strategy:shadow-a", basis_points: 10_000 },
    ]);
    const first = assigner.assign({
      owner_account_id: "account:alice", unit_ref: "session:one",
      policy: firstPolicy, strategies,
    });
    const replay = assigner.assign({
      owner_account_id: "account:alice", unit_ref: "session:one",
      policy: reorderedPolicy, strategies: [...strategies].reverse(),
    });
    expect(replay).toEqual(first);
    expect(first.authority.mode).toBe("authority");
    expect(first.authority.strategy_id).toBe("strategy:authority");
    expect(first.shadows.map((entry) => entry.strategy_id)).toEqual(["strategy:shadow-a"]);
    expect(first.shadows[0]!.bucket).toBeGreaterThanOrEqual(0);
    expect(first.shadows[0]!.bucket).toBeLessThan(10_000);
    expect(JSON.stringify(first)).not.toContain("session:one");
    expect(JSON.stringify(first)).not.toContain("07070707");
    expect(assertMintedMemoryStrategyAssignment(first)).toBe(first);
  });

  test("unit, policy, allocation, key version, and secret all change assignment identity", () => {
    const strategies = registry();
    const basePolicy = policy(strategies);
    const assign = (secret: number, unitRef: string, selectedPolicy = basePolicy) =>
      createMemoryStrategyAssigner(new Uint8Array(32).fill(secret)).assign({
        owner_account_id: "account:alice", unit_ref: unitRef,
        policy: selectedPolicy, strategies,
      });
    const original = assign(1, "session:one");
    expect(assign(1, "session:two").assignment_bundle_id).not.toBe(original.assignment_bundle_id);
    expect(assign(2, "session:one").assignment_bundle_id).not.toBe(original.assignment_bundle_id);
    const changedAllocation = policy(strategies, [
      { strategy_id: "strategy:shadow-a", basis_points: 9_999 },
    ]);
    expect(assign(1, "session:one", changedAllocation).assignment_bundle_id)
      .not.toBe(original.assignment_bundle_id);
    const changedKeyVersion = defineMemoryStrategyAssignmentPolicy({
      policy_id: "formation-policy:v1", work_kind: "formation", unit_kind: "session",
      key_version: "assignment-key:v2", authority_strategy_id: "strategy:authority",
      shadow_candidates: [
        { strategy_id: "strategy:shadow-a", basis_points: 10_000 },
        { strategy_id: "strategy:shadow-b", basis_points: 0 },
      ],
    }, strategies);
    expect(assign(1, "session:one", changedKeyVersion).assignment_bundle_id)
      .not.toBe(original.assignment_bundle_id);
  });

  test("forged plain assignment and unsafe secrets fail closed", () => {
    const strategies = registry();
    const assignment = createMemoryStrategyAssigner(new Uint8Array(32).fill(4)).assign({
      owner_account_id: "account:alice", unit_ref: "session:one",
      policy: policy(strategies), strategies,
    });
    expect(() => assertMintedMemoryStrategyAssignment({ ...assignment }))
      .toThrow("unminted_assignment");
    expect(() => createMemoryStrategyAssigner(new Uint8Array(31)))
      .toThrow("invalid_assignment_secret");
  });
});
