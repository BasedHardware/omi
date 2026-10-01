import { describe, expect, test } from "bun:test";

import {
  PRODUCT_PROJECTION_CONTRACT_VERSION,
  ProductProjectionContractError,
  acceptLegacyMappingWinner,
  appendProductMembership,
  birthProductProposition,
  buildAuthorizedProductProjectionSet,
  buildProductGroupProjection,
  buildProductProjectionRevision,
  buildProductPropositionRedirect,
  parseProductMembershipRevision,
  parseProductProjectionRevision,
  parseProductPropositionIdentity,
  planLegacyPropositionMapping,
  resolveTerminalPropositionIds,
  selectLatestAuthorizedProductProjection,
  type ProductProjectionContractErrorCode,
  type ProductProjectionRevision,
  type ProductPropositionIdentity,
} from "./product-projection";
import {
  readAfterApplicationAuthorization,
  type ApplicationGrantProjectedTreeInputSnapshot,
  type ApplicationMemoryReadAuthorizationRequest,
} from "./authorization-boundary";
import { snapshot } from "./tree.fixture";

const digest = (character: string): string => character.repeat(64);

const expectCode = (
  code: ProductProjectionContractErrorCode,
  operation: () => unknown,
): void => {
  try {
    operation();
    throw new Error("expected product projection contract error");
  } catch (error) {
    expect(error).toBeInstanceOf(ProductProjectionContractError);
    expect((error as ProductProjectionContractError).code).toBe(code);
    expect((error as Error).message).toBe(code);
  }
};

const born = (
  propositionId = "proposition-a",
  lineageId = "lineage-a",
  owner = "owner-a",
): ReturnType<typeof birthProductProposition> => birthProductProposition({
  owner_account_id: owner,
  proposition_id: propositionId,
  birth_claim_lineage_id: lineageId,
  origin: "native",
  graph_frontier: "frontier-1",
  input_digest: digest("a"),
  result_digest: digest("b"),
  created_at_event_time: 10,
});

const citation = (
  lineage = "lineage-a",
  claim = "claim-revision-a",
  evidence: readonly string[] = ["evidence-revision-a"],
) => ({
  claim_lineage_id: lineage,
  claim_revision_id: claim,
  evidence_refs: evidence,
});

const projection = (
  birth = born(),
  sequence = 1,
  renderedDigest = digest("d"),
): ProductProjectionRevision => buildProductProjectionRevision({
  identity: birth.identity,
  membership: birth.membership,
  projection_sequence: sequence,
  graph_frontier: birth.membership.graph_frontier,
  renderer_contract_digest: digest("c"),
  rendered_content_digest: renderedDigest,
  citations: [citation(birth.identity.birth_claim_lineage_id)],
  created_at_event_time: 20 + sequence,
});

const authorizationRequest = (): ApplicationMemoryReadAuthorizationRequest => ({
  owner_account_id: "owner",
  credential: {
    owner_account_id: "owner", credential_kind: "mcp_api_key", app_id: "app:a",
    key_id: "key:a", scopes: ["memories.read"], active: true,
  },
  persisted_grant: {
    owner_account_id: "owner", consumer: "mcp", app_id: "app:a", key_id: "key:a",
    enabled: true, default_read: true, scopes: ["memories.read"],
  },
});

const projectedInput = (): ApplicationGrantProjectedTreeInputSnapshot =>
  readAfterApplicationAuthorization(authorizationRequest(), () => ({
    snapshot: snapshot(), options: { account_timezone: "UTC" },
  }));

describe("stable product proposition identity", () => {
  test("birth is one lineage, stable, exact, and deterministic on replay", () => {
    const first = born();
    const second = born();

    expect(first).toEqual(second);
    expect(first.identity.proposition_id).toBe("proposition-a");
    expect(first.membership.member_claim_lineage_ids).toEqual(["lineage-a"]);
    expect(first.membership.cause).toBe("birth");
    expect(first.membership.revision_sequence).toBe(1);
    expect(first.membership.parent_membership_revision_id).toBeNull();
    expect(first.membership.membership_revision_id).toMatch(/^pmr1_[a-f0-9]{64}$/);
    expect(Object.isFrozen(first.identity)).toBe(true);
    expect(Object.isFrozen(first.membership.member_claim_lineage_ids)).toBe(true);
    expect(parseProductPropositionIdentity(first.identity)).toEqual(first.identity);
    expect(parseProductMembershipRevision(first.membership)).toEqual(first.membership);
  });

  test("birth rejects overloaded, grouping, and malformed identities", () => {
    expectCode("invalid_identity", () => born("lineage-a", "lineage-a"));
    expectCode("invalid_identity", () => born(`grp1_${digest("a")}`));
    expectCode("invalid_identity", () => parseProductPropositionIdentity({
      ...born().identity,
      extra: true,
    }));
    expectCode("invalid_identity", () => parseProductPropositionIdentity(new Proxy(born().identity, {})));
  });

  test("routine membership changes retain product identity and append history", () => {
    const birth = born();
    const next = appendProductMembership({
      identity: birth.identity,
      parent: birth.membership,
      member_claim_lineage_ids: ["lineage-a", "lineage-b"],
      cause: "ledger_consolidation",
      graph_frontier: "frontier-2",
      input_digest: digest("c"),
      result_digest: digest("d"),
      created_at_event_time: 30,
    });
    const replay = appendProductMembership({
      identity: birth.identity,
      parent: birth.membership,
      member_claim_lineage_ids: ["lineage-a", "lineage-b"],
      cause: "ledger_consolidation",
      graph_frontier: "frontier-2",
      input_digest: digest("c"),
      result_digest: digest("d"),
      created_at_event_time: 30,
    });

    expect(next).toEqual(replay);
    expect(next.proposition_id).toBe(birth.identity.proposition_id);
    expect(next.parent_membership_revision_id).toBe(birth.membership.membership_revision_id);
    expect(next.revision_sequence).toBe(2);
    expect(next.membership_revision_id).not.toBe(birth.membership.membership_revision_id);
  });

  test("membership rejects missing order, duplicate, empty, birth reuse, time reversal, and cross owner", () => {
    const birth = born();
    const base = {
      identity: birth.identity,
      parent: birth.membership,
      member_claim_lineage_ids: ["lineage-a", "lineage-b"] as readonly string[],
      cause: "correction" as const,
      graph_frontier: "frontier-2",
      input_digest: digest("c"),
      result_digest: digest("d"),
      created_at_event_time: 30,
    };
    expectCode("invalid_membership", () => appendProductMembership({ ...base, member_claim_lineage_ids: [] }));
    expectCode("invalid_membership", () => appendProductMembership({ ...base, member_claim_lineage_ids: ["lineage-b", "lineage-a"] }));
    expectCode("invalid_membership", () => appendProductMembership({ ...base, member_claim_lineage_ids: ["lineage-a", "lineage-a"] }));
    expectCode("invalid_membership", () => appendProductMembership({ ...base, cause: "birth" as never }));
    expectCode("invalid_membership", () => appendProductMembership({ ...base, created_at_event_time: 9 }));
    expectCode("invalid_membership", () => appendProductMembership({ ...base, identity: born("p-b", "l-b", "owner-b").identity }));
  });

  test("a changed immutable revision under an old id is rejected", () => {
    const membership = born().membership;
    expectCode("invalid_membership", () => parseProductMembershipRevision({
      ...membership,
      result_digest: digest("e"),
    }));
  });
});

describe("cited immutable product projections", () => {
  test("provider recomputation appends a projection without changing proposition identity", () => {
    const birth = born();
    const first = projection(birth, 1, digest("d"));
    const replay = projection(birth, 1, digest("d"));
    const recomputed = projection(birth, 2, digest("e"));

    expect(first).toEqual(replay);
    expect(first.proposition_id).toBe(birth.identity.proposition_id);
    expect(recomputed.proposition_id).toBe(birth.identity.proposition_id);
    expect(recomputed.projection_revision_id).not.toBe(first.projection_revision_id);
    expect(parseProductProjectionRevision(first)).toEqual(first);
  });

  test("projection requires complete exact membership citation support", () => {
    const birth = born();
    const membership = appendProductMembership({
      identity: birth.identity,
      parent: birth.membership,
      member_claim_lineage_ids: ["lineage-a", "lineage-b"],
      cause: "correction",
      graph_frontier: "frontier-2",
      input_digest: digest("c"),
      result_digest: digest("d"),
      created_at_event_time: 30,
    });
    const base = {
      identity: birth.identity,
      membership,
      projection_sequence: 1,
      graph_frontier: membership.graph_frontier,
      renderer_contract_digest: digest("e"),
      rendered_content_digest: digest("f"),
      citations: [citation("lineage-a"), citation("lineage-b", "claim-b", ["evidence-b"])],
      created_at_event_time: 40,
    };
    expect(buildProductProjectionRevision(base).citations).toHaveLength(2);
    expectCode("invalid_projection", () => buildProductProjectionRevision({
      ...base,
      citations: [citation("lineage-a")],
    }));
    expectCode("invalid_projection", () => buildProductProjectionRevision({
      ...base,
      citations: [citation("lineage-a"), citation("lineage-c")],
    }));
    expectCode("invalid_projection", () => buildProductProjectionRevision({
      ...base,
      graph_frontier: "stale-frontier",
    }));
    expectCode("invalid_projection", () => buildProductProjectionRevision({ ...base, citations: [] }));
  });

  test("only the existing branded authorized and deletion-live snapshot can feed latest selection", () => {
    const authorized = projectedInput();
    const birth = birthProductProposition({
      owner_account_id: "owner", proposition_id: "product-visible",
      birth_claim_lineage_id: "lineage:a", origin: "native",
      graph_frontier: authorized.graph_generation,
      input_digest: digest("a"), result_digest: digest("b"), created_at_event_time: 10,
    });
    const olderVisible = buildProductProjectionRevision({
      identity: birth.identity, membership: birth.membership, projection_sequence: 1,
      graph_frontier: authorized.graph_generation,
      renderer_contract_digest: digest("c"), rendered_content_digest: digest("d"),
      citations: [citation("lineage:a", "a", ["e1"])], created_at_event_time: 20,
    });
    const selectedSet = buildAuthorizedProductProjectionSet(
      authorized, [birth.identity], [birth.membership], [olderVisible],
    );
    const selected = selectLatestAuthorizedProductProjection(birth.identity, selectedSet);
    expect(selected?.projection_revision_id).toBe(olderVisible.projection_revision_id);

    const unbranded = structuredClone(selectedSet);
    expectCode("invalid_projection", () => selectLatestAuthorizedProductProjection(birth.identity, unbranded));

    const hiddenBirth = birthProductProposition({
      owner_account_id: "owner", proposition_id: "product-hidden",
      birth_claim_lineage_id: "lineage:private", origin: "native",
      graph_frontier: authorized.graph_generation,
      input_digest: digest("e"), result_digest: digest("f"), created_at_event_time: 10,
    });
    const hiddenProjection = buildProductProjectionRevision({
      identity: hiddenBirth.identity, membership: hiddenBirth.membership, projection_sequence: 2,
      graph_frontier: authorized.graph_generation,
      renderer_contract_digest: digest("c"), rendered_content_digest: digest("d"),
      citations: [citation("lineage:private", "private", ["e1"])], created_at_event_time: 20,
    });
    expectCode("invalid_projection", () => buildAuthorizedProductProjectionSet(
      authorized, [hiddenBirth.identity], [hiddenBirth.membership], [hiddenProjection],
    ));
  });

  test("same-sequence divergent authorized heads fail closed", () => {
    const authorized = projectedInput();
    const birth = birthProductProposition({
      owner_account_id: "owner", proposition_id: "product-visible",
      birth_claim_lineage_id: "lineage:a", origin: "native",
      graph_frontier: authorized.graph_generation,
      input_digest: digest("a"), result_digest: digest("b"), created_at_event_time: 10,
    });
    const make = (rendered: string): ProductProjectionRevision => buildProductProjectionRevision({
      identity: birth.identity, membership: birth.membership, projection_sequence: 1,
      graph_frontier: authorized.graph_generation,
      renderer_contract_digest: digest("c"), rendered_content_digest: rendered,
      citations: [citation("lineage:a", "a", ["e1"])], created_at_event_time: 20,
    });
    expectCode("invalid_projection", () => buildAuthorizedProductProjectionSet(
      authorized,
      [birth.identity],
      [birth.membership],
      [make(digest("a")), make(digest("b"))],
    ));
  });
});

describe("permanent product redirects", () => {
  const identities = (): ProductPropositionIdentity[] => [
    born("p-a", "l-a").identity,
    born("p-b", "l-b").identity,
    born("p-c", "l-c").identity,
    born("p-d", "l-d").identity,
  ];

  test("merge and split chains resolve to a sorted terminal set", () => {
    const redirects = [
      buildProductPropositionRedirect({
        owner_account_id: "owner-a", source_proposition_id: "p-a",
        successor_proposition_ids: ["p-b"], operation: "merge",
        operation_ref: "merge-op", created_at_event_time: 40,
      }),
      buildProductPropositionRedirect({
        owner_account_id: "owner-a", source_proposition_id: "p-b",
        successor_proposition_ids: ["p-c", "p-d"], operation: "split",
        operation_ref: "split-op", created_at_event_time: 50,
      }),
    ];
    expect(resolveTerminalPropositionIds({
      owner_account_id: "owner-a",
      start_proposition_ids: ["p-a"],
      propositions: identities(),
      redirects,
    })).toEqual(["p-c", "p-d"]);
  });

  test("redirects reject cycles, self, dangling, duplicate source, and cross owner", () => {
    expectCode("invalid_redirect", () => buildProductPropositionRedirect({
      owner_account_id: "owner-a", source_proposition_id: "p-a",
      successor_proposition_ids: ["p-a"], operation: "merge",
      operation_ref: "bad", created_at_event_time: 1,
    }));
    const ab = buildProductPropositionRedirect({
      owner_account_id: "owner-a", source_proposition_id: "p-a",
      successor_proposition_ids: ["p-b"], operation: "merge",
      operation_ref: "ab", created_at_event_time: 1,
    });
    const ba = buildProductPropositionRedirect({
      owner_account_id: "owner-a", source_proposition_id: "p-b",
      successor_proposition_ids: ["p-a"], operation: "merge",
      operation_ref: "ba", created_at_event_time: 2,
    });
    expectCode("redirect_cycle", () => resolveTerminalPropositionIds({
      owner_account_id: "owner-a", start_proposition_ids: ["p-a"],
      propositions: identities(), redirects: [ab, ba],
    }));
    const dangling = buildProductPropositionRedirect({
      owner_account_id: "owner-a", source_proposition_id: "p-a",
      successor_proposition_ids: ["p-missing"], operation: "merge",
      operation_ref: "dangling", created_at_event_time: 2,
    });
    expectCode("invalid_redirect", () => resolveTerminalPropositionIds({
      owner_account_id: "owner-a", start_proposition_ids: ["p-a"],
      propositions: identities(), redirects: [dangling],
    }));
    expectCode("invalid_redirect", () => resolveTerminalPropositionIds({
      owner_account_id: "owner-a", start_proposition_ids: ["p-a"],
      propositions: identities(), redirects: [ab, ab],
    }));
    expectCode("invalid_redirect", () => resolveTerminalPropositionIds({
      owner_account_id: "owner-a", start_proposition_ids: ["p-a"],
      propositions: [...identities(), born("foreign", "foreign-l", "owner-b").identity],
      redirects: [ab],
    }));
  });
});

describe("legacy mapping and rebuildable grouping", () => {
  test("mapping requires allocation, reuses a winner, and accepts a concurrent winner", () => {
    const allocation = planLegacyPropositionMapping({
      owner_account_id: "owner-a",
      legacy_source_id: "legacy-42",
      item_tombstoned: false,
      existing_mapping: null,
      proposed_random_opaque_proposition_id: null,
    });
    expect(allocation).toEqual({ kind: "allocation_required" });

    const insert = planLegacyPropositionMapping({
      owner_account_id: "owner-a",
      legacy_source_id: "legacy-42",
      item_tombstoned: false,
      existing_mapping: null,
      proposed_random_opaque_proposition_id: "opaque-random-a",
    });
    expect(insert.kind).toBe("insert_if_absent");
    if (insert.kind !== "insert_if_absent") throw new Error("unexpected plan");
    const winner = { ...insert.mapping, proposition_id: "opaque-random-b" };
    expect(acceptLegacyMappingWinner(insert.mapping, winner).proposition_id).toBe("opaque-random-b");

    const reuse = planLegacyPropositionMapping({
      owner_account_id: "owner-a",
      legacy_source_id: "legacy-42",
      item_tombstoned: false,
      existing_mapping: winner,
      proposed_random_opaque_proposition_id: null,
    });
    expect(reuse).toEqual({ kind: "reuse_mapping", mapping: winner });
  });

  test("tombstone dominates allocation and legacy-derived-looking ids are refused", () => {
    expect(planLegacyPropositionMapping({
      owner_account_id: "owner-a",
      legacy_source_id: "legacy-42",
      item_tombstoned: true,
      existing_mapping: null,
      proposed_random_opaque_proposition_id: null,
    })).toEqual({ kind: "tombstoned" });
    expectCode("invalid_migration_mapping", () => planLegacyPropositionMapping({
      owner_account_id: "owner-a",
      legacy_source_id: "legacy-42",
      item_tombstoned: true,
      existing_mapping: null,
      proposed_random_opaque_proposition_id: "opaque-random-a",
    }));
    expectCode("invalid_migration_mapping", () => planLegacyPropositionMapping({
      owner_account_id: "owner-a",
      legacy_source_id: "legacy-42",
      item_tombstoned: false,
      existing_mapping: null,
      proposed_random_opaque_proposition_id: "opaque-LEGACY-42-derived",
    }));
  });

  test("a group is derived and cannot become an authoritative proposition id", () => {
    const group = buildProductGroupProjection({
      owner_account_id: "owner-a",
      proposition_ids: ["p-a", "p-b"],
      input_frontier: "frontier-9",
      projection_contract_digest: digest("a"),
      result_digest: digest("b"),
      created_at_event_time: 90,
    });
    const rebuilt = buildProductGroupProjection({
      owner_account_id: "owner-a",
      proposition_ids: ["p-a", "p-b"],
      input_frontier: "frontier-9",
      projection_contract_digest: digest("a"),
      result_digest: digest("b"),
      created_at_event_time: 90,
    });
    expect(group).toEqual(rebuilt);
    expect(group.group_projection_id).toMatch(/^grp1_[a-f0-9]{64}$/);
    expectCode("invalid_identity", () => born(group.group_projection_id, "lineage-a"));
    expect(born("p-a", "l-a").identity.proposition_id).toBe("p-a");
  });
});

describe("strict plain-data boundary", () => {
  test("rejects getters, sparse/decorated arrays, proxies, null prototypes, and extras", () => {
    const identity = born().identity;
    const getter = { ...identity } as Record<string, unknown>;
    Object.defineProperty(getter, "proposition_id", { enumerable: true, get: () => "p" });
    expectCode("invalid_identity", () => parseProductPropositionIdentity(getter));

    const nullPrototype = Object.assign(Object.create(null), identity);
    expectCode("invalid_identity", () => parseProductPropositionIdentity(nullPrototype));
    expectCode("invalid_identity", () => parseProductPropositionIdentity({ ...identity, extra: null }));

    const sparse: string[] = [];
    sparse.length = 2;
    sparse[1] = "lineage-b";
    expectCode("invalid_membership", () => appendProductMembership({
      identity,
      parent: born().membership,
      member_claim_lineage_ids: sparse,
      cause: "correction",
      graph_frontier: "frontier-2",
      input_digest: digest("a"),
      result_digest: digest("b"),
      created_at_event_time: 20,
    }));

    const decorated = ["lineage-a"] as string[] & { extra?: boolean };
    decorated.extra = true;
    expectCode("invalid_membership", () => appendProductMembership({
      identity,
      parent: born().membership,
      member_claim_lineage_ids: decorated,
      cause: "correction",
      graph_frontier: "frontier-2",
      input_digest: digest("a"),
      result_digest: digest("b"),
      created_at_event_time: 20,
    }));
  });

  test("the public version is fixed and no raw input appears in error text", () => {
    expect(PRODUCT_PROJECTION_CONTRACT_VERSION).toBe("product-projection-v1");
    const sentinel = "SECRET_LEGACY_PERSON";
    try {
      planLegacyPropositionMapping({
        owner_account_id: "owner-a",
        legacy_source_id: sentinel,
        item_tombstoned: false,
        existing_mapping: null,
        proposed_random_opaque_proposition_id: `derived-${sentinel}`,
      });
      throw new Error("expected failure");
    } catch (error) {
      expect((error as Error).message).not.toContain(sentinel);
      expect((error as Error).message).toBe("invalid_migration_mapping");
    }
  });
});
