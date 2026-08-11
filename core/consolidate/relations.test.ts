import { expect, test } from "bun:test";
import type { Predicate } from "../schema";
import {
  invokePredicateAlignment,
  predicateAlignmentBatchDigest,
  predicateAlignmentVocabularyFrontier,
  type PredicateAlignmentAdjudicationContract,
  type PredicateAlignmentOptions,
  type PredicateAlignmentRequest,
} from "./relations";
import { predicateIdForName, predicateRevisionForObservation } from "./predicate-identity";

const id = (name: string): string => predicateIdForName(name);

const contract: PredicateAlignmentAdjudicationContract = {
  model_version: "cheap-model-v1",
  strategy: "predicate-alignment",
  prompt_version: "predicate-prompt-v2",
  schema_version: "predicate-response-v2",
  code_version: "relations-v2",
};

const options = (overrides: Partial<PredicateAlignmentOptions> = {}): PredicateAlignmentOptions => ({
  owner_account_id: "owner-a",
  batch_prompt_budget: 10_000,
  model_concurrency: 2,
  prompt_cost: (request) => 5 + request.predicates.length * 10,
  adjudication_contract: contract,
  ...overrides,
});

const v2 = (
  _predicate_id: string,
  name: string,
  owner_account_id: string,
  observed_roles: readonly string[],
  revision = observed_roles.join("-") || "empty",
): Predicate => {
  const predicate_id = id(name);
  void revision;
  return predicateRevisionForObservation({
    predicate_id,
    owner_account_id,
    display_name: name,
    roles: observed_roles,
    lifecycle: "canonical",
  }).predicate;
};

const legacy = (predicate_id: string, name: string, slots: readonly string[]): Predicate => ({
  predicate_id,
  owner_account_id: "owner-a",
  predicate_revision_id: `${predicate_id}:legacy`,
  identity_version: "name-slots-v1",
  identity_name: name,
  display_name: name,
  lifecycle: "canonical",
  slot_ids: [...slots],
});

test("alignment merges name-v2 revisions, unions semantic roles, and orders by name then id", async () => {
  const requests: PredicateAlignmentRequest[] = [];
  const result = await invokePredicateAlignment({ invoke: async ({ input }) => {
    requests.push(input as PredicateAlignmentRequest);
    return { assertions: [] };
  } }, [
    v2("p:z", "beta relation", "owner-a", ["object", "actor"], "two"),
    legacy("p:z", "beta relation", ["window-slot-17"]),
    v2("p:a", "Alpha-Relation", "owner-a", ["subject"]),
    v2("p:z", "beta relation", "owner-a", ["actor"], "one"),
    v2("p:b", "alpha relation", "owner-a", ["object"]),
  ], options());

  expect(requests).toEqual([{
    predicate_frontier: expect.any(String),
    predicates: [
      { predicate_id: id("alpha relation"), name: "alpha_relation", slot_ids: ["object", "subject"] },
      { predicate_id: id("beta relation"), name: "beta_relation", slot_ids: ["actor", "object"] },
    ],
  }]);
  expect(result.excluded_predicates).toEqual([
    { predicate_revision_id: "p:z:legacy", code: "legacy_identity_version" },
  ]);
  expect(result.batch_outcomes[0]).toMatchObject({
    kind: "success",
    predicate_ids: [id("alpha relation"), id("beta relation")],
  });
});

test("vocabulary frontier is deterministic and changes only with decision vocabulary", () => {
  const alphaSubject = v2("ignored", "alpha relation", "owner-a", ["subject"], "subject");
  const alphaObject = v2("ignored", "alpha relation", "owner-a", ["object"], "object");
  const bravo = v2("ignored", "bravo relation", "owner-a", ["subject"]);
  const original = predicateAlignmentVocabularyFrontier([alphaSubject, alphaObject, bravo], "owner-a");
  expect(predicateAlignmentVocabularyFrontier([bravo, alphaObject, alphaSubject], "owner-a")).toBe(original);
  expect(predicateAlignmentVocabularyFrontier([
    alphaSubject,
    alphaObject,
    v2("ignored", "bravo relation", "owner-a", ["place", "subject"]),
  ], "owner-a")).not.toBe(original);
  expect(predicateAlignmentVocabularyFrontier([alphaSubject, alphaObject, bravo], "owner-b")).not.toBe(original);
});

test("alignment excludes a name-v2 row whose immutable revision coordinate is forged", async () => {
  const valid = v2("ignored", "alpha", "owner-a", ["subject"]);
  let calls = 0;
  const result = await invokePredicateAlignment({ invoke: async () => { calls += 1; return { assertions: [] }; } }, [
    { ...valid, predicate_revision_id: `${valid.predicate_id}:revision:forged` },
  ], options());
  expect(calls).toBe(0);
  expect(result.excluded_predicates).toEqual([{
    predicate_revision_id: `${valid.predicate_id}:revision:forged`,
    code: "invalid_name_v2_revision",
  }]);
});

test("exact injected prompt cost bounds whole-row batches and concurrency", async () => {
  const requests: PredicateAlignmentRequest[] = [];
  let inFlight = 0;
  let peak = 0;
  await invokePredicateAlignment({ invoke: async ({ input }) => {
    requests.push(input as PredicateAlignmentRequest);
    inFlight += 1;
    peak = Math.max(peak, inFlight);
    await Bun.sleep(5);
    inFlight -= 1;
    return { assertions: [] };
  } }, ["echo", "alpha", "delta", "bravo", "charlie"].map((name) => v2(`p:${name}`, name, "owner-a", ["subject"])), options({
    batch_prompt_budget: 25,
    model_concurrency: 2,
  }));

  expect(requests.map((request) => request.predicates.map((predicate) => predicate.name))).toEqual([
    ["alpha", "bravo"],
    ["charlie", "delta"],
    ["echo"],
  ]);
  expect(peak).toBe(2);
  expect(requests.every((request) => 5 + request.predicates.length * 10 <= 25)).toBe(true);
});

test("parallel completion order cannot change outcomes or assertion ids", async () => {
  const predicates = ["alpha", "bravo", "charlie", "delta"].map((name) => v2(`p:${name}`, name, "owner-a", ["subject"]));
  const run = async (delays: Readonly<Record<string, number>>, completion: string[]) => invokePredicateAlignment({ invoke: async ({ input }) => {
    const request = input as PredicateAlignmentRequest;
    const first = request.predicates[0]!.name;
    await Bun.sleep(delays[first] ?? 0);
    completion.push(first);
    return { assertions: [{
      predicate_id: request.predicates[0]!.predicate_id,
      target_predicate_id: request.predicates[1]!.predicate_id,
    }] };
  } }, predicates, options({ batch_prompt_budget: 25, model_concurrency: 2 }));

  const reversedCompletion: string[] = [];
  const reversed = await run({ alpha: 20, charlie: 0 }, reversedCompletion);
  const sequential = await run({ alpha: 0, charlie: 20 }, []);
  expect(reversedCompletion).toEqual(["charlie", "alpha"]);
  expect(reversed).toEqual(sequential);
  expect(reversed.batch_outcomes.map((outcome) => outcome.batch_index)).toEqual([0, 1]);
});

test("admission rejects self, invented, and cross-batch proposals while foreign-owner rows never reach the model", async () => {
  const predicates = [
    v2("p:a", "alpha", "owner-a", ["subject"]),
    v2("p:b", "bravo", "owner-a", ["actor"]),
    v2("p:c", "charlie", "owner-b", ["actor"]),
    v2("p:d", "delta", "owner-a", ["subject"]),
  ];
  const result = await invokePredicateAlignment({ invoke: async ({ input }) => {
    const request = input as PredicateAlignmentRequest;
    if (request.predicates[0]?.name !== "alpha") return { assertions: [] };
    return { assertions: [
      { predicate_id: id("alpha"), target_predicate_id: id("bravo"), slot_aliases: [{ from_slot_id: "subject", to_slot_id: "actor" }] },
      { predicate_id: id("alpha"), target_predicate_id: id("alpha") },
      { predicate_id: "p:invented", target_predicate_id: id("alpha") },
      { predicate_id: id("alpha"), target_predicate_id: id("delta") },
    ] };
  } }, predicates, options({ batch_prompt_budget: 25 }));

  expect(result.assertions).toHaveLength(1);
  expect(result.assertions[0]).toMatchObject({ predicate_id: id("alpha"), target_predicate_id: id("bravo"), owner_account_id: "owner-a" });
  expect(result.batch_outcomes[0]).toMatchObject({
    kind: "success",
    rejected_proposals: [
      { proposal_index: 1, code: "self_alias" },
      { proposal_index: 2, code: "invented_predicate" },
      { proposal_index: 3, code: "predicate_outside_successful_batch" },
    ],
  });
  expect(result.excluded_predicates).toContainEqual({
    predicate_revision_id: v2("ignored", "charlie", "owner-b", ["actor"]).predicate_revision_id,
    code: "owner_mismatch",
  });
});

test("mixed-owner duplicate ids are excluded before invoke and invented role aliases fail closed", async () => {
  const result = await invokePredicateAlignment({ invoke: async () => ({ assertions: [
    { predicate_id: id("bravo"), target_predicate_id: id("charlie"), slot_aliases: [{ from_slot_id: "invented", to_slot_id: "subject" }] },
  ] }) }, [
    v2("p:shared", "alpha", "owner-a", ["subject"], "a"),
    v2("p:shared", "alpha", "owner-b", ["subject"], "b"),
    v2("p:target", "bravo", "owner-a", ["subject"]),
    v2("p:other", "charlie", "owner-a", ["subject"]),
  ], options());
  expect(result.assertions).toEqual([]);
  expect(result.batch_outcomes[0]).toMatchObject({ rejected_proposals: [
    { proposal_index: 0, code: "invalid_slot_alias" },
  ] });
  expect(result.excluded_predicates).toContainEqual({
    predicate_revision_id: v2("ignored", "alpha", "owner-b", ["subject"]).predicate_revision_id,
    code: "owner_mismatch",
  });
});

test("assertion identity is canonical and deduplicated across proposal ordering", async () => {
  const predicates = [
    v2("p:a", "alpha", "owner-a", ["subject"]),
    v2("p:b", "bravo", "owner-a", ["subject"]),
    v2("p:c", "charlie", "owner-a", ["subject"]),
  ];
  const run = (assertions: readonly unknown[]) => invokePredicateAlignment({ invoke: async () => ({ assertions }) }, predicates, options());
  const first = await run([
    { predicate_id: id("alpha"), target_predicate_id: id("bravo") },
    { predicate_id: id("charlie"), target_predicate_id: id("bravo") },
    { predicate_id: id("alpha"), target_predicate_id: id("bravo") },
  ]);
  const reordered = await run([
    { predicate_id: id("charlie"), target_predicate_id: id("bravo") },
    { predicate_id: id("alpha"), target_predicate_id: id("bravo") },
  ]);
  expect(first.assertions).toHaveLength(2);
  expect(first.assertions).toEqual(reordered.assertions);
  expect(first.batch_outcomes[0]).toMatchObject({ kind: "success", response_digest: expect.any(String), result_digest: expect.any(String) });
});

test("one failed batch stays retryable while a successful sibling settles independently", async () => {
  const predicates = ["alpha", "bravo", "charlie", "delta"].map((name) => v2(`p:${name}`, name, "owner-a", ["subject"]));
  const first = await invokePredicateAlignment({ invoke: async ({ input }) => {
    const request = input as PredicateAlignmentRequest;
    if (request.predicates[0]!.name === "alpha") throw new Error("raw provider text must not escape");
    return { assertions: [{ predicate_id: id("charlie"), target_predicate_id: id("delta") }] };
  } }, predicates, options({ batch_prompt_budget: 25 }));

  expect(first.batch_outcomes.map((outcome) => outcome.kind)).toEqual(["retryable_error", "success"]);
  expect(first.batch_outcomes[0]).toMatchObject({ error_code: "model_invoke_failed" });
  expect(JSON.stringify(first)).not.toContain("raw provider text");
  expect(first.assertions).toHaveLength(1);
  const success = first.batch_outcomes[1]!;
  expect(success).toMatchObject({ kind: "success", response_digest: expect.any(String), result_digest: expect.any(String) });
  if (success.kind !== "success") throw new Error("expected success");
  const successfulDigest = success.settleable_batch_digest;

  const called: string[] = [];
  const replay = await invokePredicateAlignment({ invoke: async ({ input }) => {
    called.push((input as PredicateAlignmentRequest).predicates[0]!.name);
    return { assertions: [] };
  } }, predicates, options({ batch_prompt_budget: 25, settled_batch_digests: new Set([successfulDigest]) }));
  expect(called).toEqual(["alpha"]);
  expect(replay.skipped_settled_batch_digests).toEqual([successfulDigest]);
  expect(replay.batch_outcomes).toHaveLength(1);
  expect(replay.batch_outcomes[0]!.batch_index).toBe(0);
});

test("adding vocabulary asks only new or regrouped batches, not every settled batch", async () => {
  const original = ["alpha", "bravo", "charlie", "delta"].map((name) => v2("ignored", name, "owner-a", ["subject"]));
  const first = await invokePredicateAlignment({ invoke: async () => ({ assertions: [] }) }, original, options({
    batch_prompt_budget: 25,
  }));
  const settled = new Set(first.batch_outcomes.flatMap((outcome) =>
    outcome.kind === "success" ? [outcome.settleable_batch_digest] : []));
  expect(settled.size).toBe(2);

  const called: string[][] = [];
  const incremental = await invokePredicateAlignment({ invoke: async ({ input }) => {
    called.push((input as PredicateAlignmentRequest).predicates.map((predicate) => predicate.name));
    return { assertions: [] };
  } }, [...original, v2("ignored", "echo", "owner-a", ["subject"])], options({
    batch_prompt_budget: 25,
    settled_batch_digests: settled,
  }));
  expect(called).toEqual([["echo"]]);
  expect(incremental.skipped_settled_batch_digests).toHaveLength(2);
});

test("settlement digest changes with adjudication contract or exact ordered question", async () => {
  const predicates = [v2("p:a", "alpha", "owner-a", ["subject"]), v2("p:b", "bravo", "owner-a", ["object"])];
  const request: PredicateAlignmentRequest = {
    predicate_frontier: "frontier-1",
    predicates: [
      { predicate_id: id("alpha"), name: "alpha", slot_ids: ["subject"] },
      { predicate_id: id("bravo"), name: "bravo", slot_ids: ["object"] },
    ],
  };
  const originalDigest = predicateAlignmentBatchDigest(contract, request);
  expect(predicateAlignmentBatchDigest({ ...contract, prompt_version: "predicate-prompt-v3" }, request)).not.toBe(originalDigest);
  expect(predicateAlignmentBatchDigest(contract, {
    ...request,
    predicates: [request.predicates[0]!, { ...request.predicates[1]!, slot_ids: ["object", "place"] }],
  })).not.toBe(originalDigest);

  let calls = 0;
  await invokePredicateAlignment({ invoke: async () => { calls += 1; return { assertions: [] }; } }, predicates, options({
    settled_batch_digests: new Set([originalDigest]),
    adjudication_contract: { ...contract, prompt_version: "predicate-prompt-v3" },
  }));
  expect(calls).toBe(1);
  await invokePredicateAlignment({ invoke: async () => { calls += 1; return { assertions: [] }; } }, [
    predicates[0]!, v2("p:b", "bravo", "owner-a", ["object", "place"]),
  ], options({ settled_batch_digests: new Set([originalDigest]) }));
  expect(calls).toBe(2);
});

test("oversize questions and malformed responses are retryable, never successful empty answers", async () => {
  let calls = 0;
  const oversize = await invokePredicateAlignment({ invoke: async () => { calls += 1; return { assertions: [] }; } }, [
    v2("p:a", "alpha", "owner-a", ["subject"]),
  ], options({ batch_prompt_budget: 10, prompt_cost: () => 11 }));
  expect(calls).toBe(0);
  expect(oversize.batch_outcomes[0]).toMatchObject({ kind: "retryable_error", error_code: "batch_prompt_budget_exceeded" });

  const malformed = await invokePredicateAlignment({ invoke: async () => ({ assertions: "not-an-array" }) }, [
    v2("p:a", "alpha", "owner-a", ["subject"]),
  ], options());
  expect(malformed.batch_outcomes[0]).toMatchObject({ kind: "retryable_error", error_code: "model_response_invalid" });
});

test("provider responses must be detached plain data with exact envelopes", async () => {
  const decorated: unknown[] = [];
  Object.defineProperty(decorated, "decoration", { value: true, enumerable: false });
  const accessor = {} as Record<string, unknown>;
  Object.defineProperty(accessor, "assertions", { get: () => [] });
  const nullPrototype = Object.assign(Object.create(null), { assertions: [] });
  const invalidResponses: unknown[] = [
    { assertions: [], extra: true },
    accessor,
    nullPrototype,
    new Proxy({ assertions: [] }, {}),
    { assertions: decorated },
  ];
  for (const response of invalidResponses) {
    const result = await invokePredicateAlignment({ invoke: async () => response }, [
      v2("ignored", "alpha", "owner-a", ["subject"]),
    ], options());
    expect(result.batch_outcomes[0]).toMatchObject({
      kind: "retryable_error",
      error_code: "model_response_invalid",
    });
  }

  const proposalWithExtra = await invokePredicateAlignment({ invoke: async () => ({ assertions: [{
    predicate_id: id("alpha"),
    target_predicate_id: id("bravo"),
    hidden: "must not be accepted",
  }] }) }, [
    v2("ignored", "alpha", "owner-a", ["subject"]),
    v2("ignored", "bravo", "owner-a", ["subject"]),
  ], options());
  expect(proposalWithExtra.assertions).toEqual([]);
  expect(proposalWithExtra.batch_outcomes[0]).toMatchObject({
    kind: "success",
    rejected_proposals: [{ proposal_index: 0, code: "invalid_proposal" }],
  });
});

test("budget and concurrency must be positive and bounded", async () => {
  const model = { invoke: async () => ({ assertions: [] }) };
  const predicates = [v2("p:a", "alpha", "owner-a", ["subject"])];
  await expect(invokePredicateAlignment(model, predicates, options({ batch_prompt_budget: 0 }))).rejects.toThrow("predicate_alignment_prompt_budget_invalid");
  await expect(invokePredicateAlignment(model, predicates, options({ model_concurrency: 0 }))).rejects.toThrow("predicate_alignment_concurrency_invalid");
  await expect(invokePredicateAlignment(model, predicates, options({ model_concurrency: 65 }))).rejects.toThrow("predicate_alignment_concurrency_invalid");
});
