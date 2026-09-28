import { describe, expect, test } from "bun:test";

import {
  PRODUCT_CONFLICT_CONTRACT_VERSION,
  ProductConflictContractError,
  buildProductConflictOccurrence,
  buildProductConflictResolutionInput,
  parseProductConflictOccurrence,
  parseProductConflictResolutionInput,
  type ProductConflictContractErrorCode,
} from "./product-conflict";
import {
  ProductProjectionContractError,
  birthProductProposition,
  buildProductPropositionRedirect,
  type ProductPropositionIdentity,
  type ProductPropositionRedirect,
} from "./product-projection";

const digest = (character: string): string => character.repeat(64);

const identity = (
  propositionId: string,
  owner = "owner-a",
): ProductPropositionIdentity => birthProductProposition({
  owner_account_id: owner,
  proposition_id: propositionId,
  birth_claim_lineage_id: `lineage:${propositionId}`,
  origin: "native",
  graph_frontier: "frontier:birth",
  input_digest: digest("a"),
  result_digest: digest("b"),
  created_at_event_time: 1,
}).identity;

const propositions = (): readonly ProductPropositionIdentity[] => [
  identity("p-a"), identity("p-b"), identity("p-c"), identity("p-d"),
];

const occurrence = (patch: Record<string, unknown> = {}) => buildProductConflictOccurrence({
  owner_account_id: "owner-a",
  original_proposition_ids: ["p-a", "p-b"],
  propositions: propositions(),
  graph_frontier: "frontier:conflict",
  detector_contract_digest: digest("c"),
  conflict_basis_digest: digest("d"),
  created_at_event_time: 10,
  ...patch,
} as never);

const expectCode = (
  code: ProductConflictContractErrorCode,
  operation: () => unknown,
): void => {
  try {
    operation();
    throw new Error("expected product conflict contract error");
  } catch (error) {
    expect(error).toBeInstanceOf(ProductConflictContractError);
    expect((error as ProductConflictContractError).code).toBe(code);
    expect((error as Error).message).toBe(code);
  }
};

describe("product conflict occurrence references", () => {
  test("two same-owner propositions produce one immutable deterministic occurrence with no winner vocabulary", () => {
    const first = occurrence();
    const replay = occurrence();
    expect(JSON.stringify(first)).toBe(JSON.stringify(replay));
    expect(first.version).toBe(PRODUCT_CONFLICT_CONTRACT_VERSION);
    expect(first.occurrence_id).toMatch(/^pco1_[a-f0-9]{64}$/);
    expect(first.reference_snapshot_digest).toMatch(/^[a-f0-9]{64}$/);
    expect(first.original_proposition_ids).toEqual(["p-a", "p-b"]);
    expect(parseProductConflictOccurrence(first, propositions())).toEqual(first);
    expect(Object.isFrozen(first)).toBe(true);
    expect(Object.isFrozen(first.original_proposition_ids)).toBe(true);
    for (const forbidden of ["winner", "selected", "status", "confidence", "score", "snippet"]) {
      expect(Object.keys(first)).not.toContain(forbidden);
      expect(JSON.stringify(first)).not.toContain(`\"${forbidden}\"`);
    }
  });

  test("every immutable coordinate changes the content-addressed occurrence id", () => {
    const base = occurrence();
    for (const changed of [
      occurrence({ original_proposition_ids: ["p-a", "p-c"] }),
      occurrence({ graph_frontier: "frontier:other" }),
      occurrence({ detector_contract_digest: digest("e") }),
      occurrence({ conflict_basis_digest: digest("f") }),
      occurrence({ created_at_event_time: 11 }),
      occurrence({
        propositions: propositions().map((item) => item.proposition_id === "p-a"
          ? { ...item, created_at_event_time: 2 }
          : item),
      }),
    ]) expect(changed.occurrence_id).not.toBe(base.occurrence_id);
  });

  test("one, duplicate, unsorted, group, dangling, cross-owner, malformed and unsafe inputs fail closed", () => {
    expectCode("invalid_conflict_occurrence", () => occurrence({ original_proposition_ids: ["p-a"] }));
    expectCode("invalid_conflict_occurrence", () => occurrence({ original_proposition_ids: ["p-a", "p-a"] }));
    expectCode("invalid_conflict_occurrence", () => occurrence({ original_proposition_ids: ["p-b", "p-a"] }));
    expectCode("invalid_conflict_occurrence", () => occurrence({ original_proposition_ids: [`grp1_${digest("a")}`, "p-a"] }));
    expectCode("invalid_conflict_occurrence", () => occurrence({ original_proposition_ids: ["p-a", "p-missing"] }));
    expectCode("invalid_conflict_occurrence", () => occurrence({ propositions: [...propositions(), identity("foreign", "owner-b")] }));
    expectCode("invalid_conflict_occurrence", () => occurrence({ detector_contract_digest: "not-a-digest" }));
    expectCode("invalid_conflict_occurrence", () => occurrence({ created_at_event_time: Number.MAX_SAFE_INTEGER + 1 }));
    expectCode("invalid_conflict_occurrence", () => parseProductConflictOccurrence({
      ...occurrence(), occurrence_id: `pco1_${digest("f")}`,
    }, propositions()));
    expectCode("invalid_conflict_occurrence", () => parseProductConflictOccurrence({
      ...occurrence(), reference_snapshot_digest: digest("0"),
    }, propositions()));
  });

  test("hostile containers and oversized alternatives fail before construction", () => {
    const base = {
      owner_account_id: "owner-a",
      original_proposition_ids: ["p-a", "p-b"],
      propositions: propositions(),
      graph_frontier: "frontier:conflict",
      detector_contract_digest: digest("c"),
      conflict_basis_digest: digest("d"),
      created_at_event_time: 10,
    };
    expectCode("invalid_conflict_occurrence", () => buildProductConflictOccurrence(new Proxy(base, {}) as never));
    const getter = { ...base };
    Object.defineProperty(getter, "graph_frontier", { enumerable: true, get: () => "frontier:conflict" });
    expectCode("invalid_conflict_occurrence", () => buildProductConflictOccurrence(getter as never));
    expectCode("invalid_conflict_occurrence", () => buildProductConflictOccurrence(Object.assign(Object.create(null), base)));
    const sparse = ["p-a", , "p-b"];
    expectCode("invalid_conflict_occurrence", () => buildProductConflictOccurrence({ ...base, original_proposition_ids: sparse } as never));
    const decorated = ["p-a", "p-b"] as string[] & { extra?: boolean };
    decorated.extra = true;
    expectCode("invalid_conflict_occurrence", () => buildProductConflictOccurrence({ ...base, original_proposition_ids: decorated }));
    const symbol = { ...base, [Symbol("hidden")]: true };
    expectCode("invalid_conflict_occurrence", () => buildProductConflictOccurrence(symbol));
    expectCode("invalid_conflict_occurrence", () => buildProductConflictOccurrence({ ...base, extra: "raw-secret" } as never));
    expectCode("invalid_conflict_occurrence", () => buildProductConflictOccurrence({
      ...base,
      original_proposition_ids: Array.from({ length: 10_001 }, (_, index) => `p-${index}`),
    }));
  });
});

describe("product conflict resolution inputs", () => {
  const redirects = (): readonly ProductPropositionRedirect[] => [
    buildProductPropositionRedirect({
      owner_account_id: "owner-a",
      source_proposition_id: "p-a",
      successor_proposition_ids: ["p-c"],
      operation: "merge",
      operation_ref: "merge:one",
      created_at_event_time: 20,
    }),
  ];

  const resolution = (patch: Record<string, unknown> = {}) => buildProductConflictResolutionInput({
    occurrence: occurrence(),
    proposed_resolved_proposition_ids: ["p-a"],
    propositions: propositions(),
    redirects: redirects(),
    graph_frontier: "frontier:resolution",
    operation_ref: `opref1_${digest("1")}`,
    resolution_contract_digest: digest("e"),
    created_at_event_time: 30,
    ...patch,
  } as never);

  test("an attributable input preserves alternatives and resolves old ids to terminal successors", () => {
    const input = resolution();
    expect(input.resolution_input_id).toMatch(/^pcr1_[a-f0-9]{64}$/);
    expect(input.reference_snapshot_digest).toMatch(/^[a-f0-9]{64}$/);
    expect(input.original_proposition_ids).toEqual(occurrence().original_proposition_ids);
    expect(input.resolved_proposition_ids).toEqual(["p-c"]);
    expect(parseProductConflictResolutionInput(
      input, occurrence(), propositions(), redirects(),
    )).toEqual(input);
    expect(Object.isFrozen(input)).toBe(true);
    expect(Object.isFrozen(input.original_proposition_ids)).toBe(true);
    expect(Object.isFrozen(input.resolved_proposition_ids)).toBe(true);
  });

  test("split redirects retain several explicit terminal propositions", () => {
    const split = buildProductPropositionRedirect({
      owner_account_id: "owner-a",
      source_proposition_id: "p-a",
      successor_proposition_ids: ["p-c", "p-d"],
      operation: "split",
      operation_ref: "split:one",
      created_at_event_time: 20,
    });
    expect(resolution({ redirects: [split] }).resolved_proposition_ids).toEqual(["p-c", "p-d"]);
  });

  test("empty, group, dangling, unsorted and changed immutable resolution inputs fail closed", () => {
    expectCode("invalid_conflict_resolution_input", () => resolution({ proposed_resolved_proposition_ids: [] }));
    expectCode("invalid_conflict_resolution_input", () => resolution({ proposed_resolved_proposition_ids: [`grp1_${digest("a")}`] }));
    expect(() => resolution({ proposed_resolved_proposition_ids: ["p-missing"] }))
      .toThrow("invalid_redirect");
    expectCode("invalid_conflict_resolution_input", () => resolution({ proposed_resolved_proposition_ids: ["p-b", "p-a"] }));
    expectCode("invalid_conflict_resolution_input", () => resolution({ created_at_event_time: 9 }));
    const valid = resolution();
    for (const changed of [
      resolution({ graph_frontier: "frontier:changed" }),
      resolution({ operation_ref: `opref1_${digest("2")}` }),
      resolution({ resolution_contract_digest: digest("f") }),
      resolution({ created_at_event_time: 31 }),
    ]) expect(changed.resolution_input_id).not.toBe(valid.resolution_input_id);
    expectCode("invalid_conflict_resolution_input", () => parseProductConflictResolutionInput({
      ...valid,
      original_proposition_ids: ["p-a", "p-c"],
    }, occurrence(), propositions(), redirects()));
    expectCode("invalid_conflict_resolution_input", () => parseProductConflictResolutionInput({
      ...valid,
      reference_snapshot_digest: digest("0"),
    }, occurrence(), propositions(), redirects()));

    const laterRedirect = buildProductPropositionRedirect({
      owner_account_id: "owner-a",
      source_proposition_id: "p-c",
      successor_proposition_ids: ["p-d"],
      operation: "merge",
      operation_ref: "merge:later",
      created_at_event_time: 40,
    });
    expectCode("invalid_conflict_resolution_input", () => parseProductConflictResolutionInput(
      valid, occurrence(), propositions(), [...redirects(), laterRedirect],
    ));
    const rebuiltAtLaterSnapshot = resolution({ redirects: [...redirects(), laterRedirect] });
    expect(rebuiltAtLaterSnapshot.resolved_proposition_ids).toEqual(["p-d"]);
    expect(rebuiltAtLaterSnapshot.reference_snapshot_digest)
      .not.toBe(valid.reference_snapshot_digest);
    expect(rebuiltAtLaterSnapshot.resolution_input_id).not.toBe(valid.resolution_input_id);
  });

  test("cycles and excessive redirect depth remain closed redirect-contract failures", () => {
    const cycle = [
      buildProductPropositionRedirect({
        owner_account_id: "owner-a", source_proposition_id: "p-a",
        successor_proposition_ids: ["p-b"], operation: "merge",
        operation_ref: "cycle:ab", created_at_event_time: 20,
      }),
      buildProductPropositionRedirect({
        owner_account_id: "owner-a", source_proposition_id: "p-b",
        successor_proposition_ids: ["p-a"], operation: "merge",
        operation_ref: "cycle:ba", created_at_event_time: 21,
      }),
    ];
    expect(() => resolution({ redirects: cycle })).toThrow("redirect_cycle");

    const chainIdentities = Array.from({ length: 67 }, (_, index) => identity(`depth-${index}`));
    const chain = Array.from({ length: 66 }, (_, index) => buildProductPropositionRedirect({
      owner_account_id: "owner-a",
      source_proposition_id: `depth-${index}`,
      successor_proposition_ids: [`depth-${index + 1}`],
      operation: "merge",
      operation_ref: `depth-op-${index}`,
      created_at_event_time: index,
    }));
    expect(() => resolution({
      occurrence: occurrence(),
      proposed_resolved_proposition_ids: ["depth-0"],
      propositions: [...propositions(), ...chainIdentities],
      redirects: chain,
    })).toThrow("redirect_bound_exceeded");
  });

  test("resolution errors never retain proposition content or provider text", () => {
    try {
      resolution({ operation_ref: "contains spaces and raw provider response" });
      throw new Error("expected failure");
    } catch (error) {
      expect(error).toBeInstanceOf(ProductConflictContractError);
      expect((error as Error).message).toBe("invalid_conflict_resolution_input");
      expect((error as Error).message).not.toContain("provider");
    }
    const redirectError = (() => {
      try {
        resolution({ proposed_resolved_proposition_ids: ["unknown-private-proposition"] });
      } catch (error) { return error; }
      return null;
    })();
    expect(redirectError).toBeInstanceOf(ProductProjectionContractError);
    expect((redirectError as Error).message).toBe("invalid_redirect");
  });
});
