import { expect, test } from "bun:test";
import { projectTreeInputSnapshot } from "./index";
import * as agentic from "./agentic";
import { retrieveAgentic, runAgenticTools, AGENTIC_SYSTEM_PROMPT } from "./agentic";
import { snapshot } from "./tree.fixture";

const ownerContext = { reader_account_id: "owner", grant: { grant_id: "owner", policy_classes: [] } };

/** Owner claim naming a person via relationship cue — shared by salvage / harvest fixtures. */
const peopleGraph = () => {
  const graph = snapshot();
  const base = graph.claims[0]!;
  graph.claims = [
    {
      ...base,
      claim: {
        ...base.claim,
        policy_labels: ["subject:owner"],
        arguments: [{ slot_id: "object", role: "object", surface: "John", value: { kind: "literal" as const, value: "John" } }],
      },
    },
    graph.claims[1]!,
  ];
  graph.evidence = [{
    ...graph.evidence[0]!,
    evidence: { ...graph.evidence[0]!.evidence, excerpt: "John is my friend from work" },
  }];
  return graph;
};

/** Many claims cite one evidence blob — compose must see that id once. */
const sharedEvidenceGraph = () => {
  const graph = snapshot();
  const base = graph.claims[0]!;
  const baseEv = graph.evidence[0]!;
  graph.evidence = [{
    ...baseEv,
    evidence: { ...baseEv.evidence, evidence_id: "e_shared", excerpt: "At dinner David mentioned Liz and my brother" },
  }];
  graph.events[0]!.event.evidence_addressable_refs = ["e_shared"];
  const names = ["Liz", "Sam", "Amy", "Ben", "Zoe", "Max", "Ira", "Ned"];
  graph.claims = names.map((name, i) => ({
    ...base,
    revision_id: `c${i}`,
    claim: {
      ...base.claim,
      claim_revision_id: `c${i}`,
      claim_lineage_id: `lineage:c${i}`,
      evidence_refs: ["e_shared"],
      policy_labels: ["subject:owner"],
      arguments: [{ slot_id: "object", role: "object", surface: name, value: { kind: "literal" as const, value: name } }],
    },
  }));
  graph.adjacency = graph.claims.map((c) => ({ claim_revision_id: c.revision_id, entity_id: "entity", role_slot_id: "subject" }));
  return graph;
};

test("agentic search ranks overlapping live claims and walk stays on the safe projection", () => {
  const graph = snapshot();
  const input = projectTreeInputSnapshot(graph, { account_timezone: "UTC", request_context: ownerContext });
  const search = runAgenticTools(input, graph, { owner_account_id: "owner", query: "met", request_context: ownerContext }, { tool: "search", args: { query: "met", limit: 5 } });
  expect((search.result as { hits: unknown[] }).hits.length).toBeGreaterThan(0);
  const claimId = input.claims[0]!.claim_revision_id;
  const walked = runAgenticTools(input, graph, { owner_account_id: "owner", query: "met", request_context: ownerContext }, { tool: "walk", args: { anchor: `claim:${claimId}`, max_hops: 1, limit: 10 } });
  expect(walked.result).toMatchObject({ node_count: expect.any(Number) });
});

test("agentic recall gathers evidence via tools then grounds the compose", async () => {
  const graph = snapshot();
  const input = projectTreeInputSnapshot(graph, { account_timezone: "UTC", request_context: ownerContext });
  const evidenceId = input.claims[0]!.evidence_spans[0]!.evidence_id;
  let steps = 0;
  const model = {
    agentStep: async () => {
      steps += 1;
      return steps === 1
        ? { tool: "search" as const, args: { query: "met", limit: 5 } }
        : { tool: "done" as const, args: { evidence_ids: [evidenceId] } };
    },
    compose: async () => ({ answer_text: "They met.", citations: [evidenceId], assertions: [{ text: "They met.", citations: [evidenceId] }] }),
    invoke: async () => ({ entailed: true }),
  };
  const answer = await retrieveAgentic({ owner_account_id: "owner", query: "Who did I meet?", request_context: ownerContext }, graph, input, model);
  expect(answer).toMatchObject({ answer_text: "They met.", grounding: { status: "grounded" }, agent_steps: 2 });
  expect(answer.citations).toContain(evidenceId);
  expect(AGENTIC_SYSTEM_PROMPT).toContain("list_surfaces");
  expect(AGENTIC_SYSTEM_PROMPT).not.toContain("MUST call done by step 5–6");
});

test("agent that never calls done still auto-dones with accumulated search evidence", async () => {
  const graph = snapshot();
  const input = projectTreeInputSnapshot(graph, { account_timezone: "UTC", request_context: ownerContext });
  const evidenceId = input.claims[0]!.evidence_spans[0]!.evidence_id;
  const model = {
    agentStep: async () => ({ tool: "search" as const, args: { query: "met", limit: 5 } }),
    compose: async () => ({ answer_text: "They met.", citations: [evidenceId], assertions: [{ text: "They met.", citations: [evidenceId] }] }),
    invoke: async () => ({ entailed: true }),
  };
  const answer = await retrieveAgentic(
    { owner_account_id: "owner", query: "Who did I meet?", request_context: ownerContext, max_steps: 3 },
    graph,
    input,
    model,
  );
  expect(answer).toMatchObject({ answer_text: "They met.", grounding: { status: "grounded" }, agent_steps: 3 });
  expect(answer.citations).toContain(evidenceId);
  expect(answer.agent_trace.every((step) => step.tool === "search")).toBe(true);
});

test("agentic recall returns query_gap when nothing matches (no invent)", async () => {
  const graph = snapshot();
  const input = projectTreeInputSnapshot(graph, { account_timezone: "UTC", request_context: ownerContext });
  const model = {
    agentStep: async () => ({ tool: "done" as const, args: { evidence_ids: [] } }),
    compose: async () => ({ answer_text: "", citations: [], assertions: [] }),
    invoke: async () => ({ entailed: true }),
  };
  const answer = await retrieveAgentic(
    { owner_account_id: "owner", query: "kayaking underwater volcano", request_context: ownerContext },
    graph,
    input,
    model,
  );
  expect(answer).toMatchObject({ answer_text: null, citations: [], absence: { kind: "query_gap", message: "no cited memory matched" }, grounding: null });
});

test("empty compose after evidence is query_gap, never grounded empty string", async () => {
  const graph = snapshot();
  const input = projectTreeInputSnapshot(graph, { account_timezone: "UTC", request_context: ownerContext });
  const evidenceId = input.claims[0]!.evidence_spans[0]!.evidence_id;
  const model = {
    agentStep: async () => ({ tool: "done" as const, args: { evidence_ids: [evidenceId] } }),
    compose: async () => ({ answer_text: "", citations: [], assertions: [] }),
    invoke: async () => ({ entailed: true }),
  };
  const answer = await retrieveAgentic(
    { owner_account_id: "owner", query: "What tools do I use for writing and chat?", request_context: ownerContext },
    graph,
    input,
    model,
  );
  expect(answer).toMatchObject({ answer_text: null, citations: [], absence: { kind: "query_gap" }, grounding: null });
  expect(answer.answer_text).not.toBe("");
});

test("many claims sharing one evidence_id compose that evidence once", async () => {
  const graph = sharedEvidenceGraph();
  const input = projectTreeInputSnapshot(graph, { account_timezone: "UTC", request_context: ownerContext });
  expect(input.claims.length).toBeGreaterThan(3);
  expect(new Set(input.claims.flatMap((c) => c.evidence_spans.map((s) => s.evidence_id)))).toEqual(new Set(["e_shared"]));
  let composeIds: string[] = [];
  const model = {
    agentStep: async () => ({ tool: "done" as const, args: { evidence_ids: ["e_shared"] } }),
    compose: async ({ input: composeInput }: { input: unknown }) => {
      composeIds = (composeInput as { evidence_spans: { evidence_id: string }[] }).evidence_spans.map((s) => s.evidence_id);
      return {
        answer_text: "Liz is in your life.",
        citations: ["e_shared"],
        assertions: [{ text: "Liz is in your life.", citations: ["e_shared"] }],
      };
    },
    invoke: async () => ({ entailed: true }),
  };
  const answer = await retrieveAgentic(
    { owner_account_id: "owner", query: "Who are the people in my life?", request_context: ownerContext },
    graph,
    input,
    model,
  );
  expect(composeIds.filter((id) => id === "e_shared")).toHaveLength(1);
  expect(new Set(composeIds).size).toBe(composeIds.length);
  expect(answer).toMatchObject({ answer_text: "Liz is in your life.", grounding: { status: "grounded" } });
});

test("list_surfaces skips pronouns; lowercase nicknames are kept without Proper-Case", () => {
  const graph = snapshot();
  const base = graph.claims[0]!;
  const baseEv = graph.evidence[0]!;
  graph.evidence = [
    { ...baseEv, evidence: { ...baseEv.evidence, evidence_id: "e_pronoun", excerpt: "I think we should call liz" } },
    {
      revision_id: "e_liz",
      evidence: { ...baseEv.evidence, evidence_id: "e_liz", excerpt: "liz is my friend from college", event_revision_id: "event" },
    },
  ];
  graph.events[0]!.event.evidence_addressable_refs = ["e_pronoun", "e_liz"];
  graph.claims = [
    {
      ...base,
      revision_id: "c_i",
      claim: {
        ...base.claim,
        claim_revision_id: "c_i",
        claim_lineage_id: "lineage:c_i",
        evidence_refs: ["e_pronoun"],
        policy_labels: ["subject:owner"],
        arguments: [
          { slot_id: "subject", role: "subject", surface: "I", value: { kind: "literal" as const, value: "I" } },
          { slot_id: "object", role: "object", surface: "me", value: { kind: "literal" as const, value: "me" } },
          { slot_id: "object2", role: "object", surface: "you", value: { kind: "literal" as const, value: "you" } },
          { slot_id: "object3", role: "object", surface: "they", value: { kind: "literal" as const, value: "they" } },
        ],
      },
    },
    {
      ...base,
      revision_id: "c_liz",
      claim: {
        ...base.claim,
        claim_revision_id: "c_liz",
        claim_lineage_id: "lineage:c_liz",
        evidence_refs: ["e_liz"],
        policy_labels: ["subject:owner"],
        arguments: [{ slot_id: "object", role: "object", surface: "liz", value: { kind: "literal" as const, value: "liz" } }],
      },
    },
  ];
  graph.adjacency = [
    { claim_revision_id: "c_i", entity_id: "entity", role_slot_id: "subject" },
    { claim_revision_id: "c_liz", entity_id: "entity", role_slot_id: "subject" },
  ];
  const input = projectTreeInputSnapshot(graph, { account_timezone: "UTC", request_context: ownerContext });
  const request = { owner_account_id: "owner", query: "Who are the people in my life?", request_context: ownerContext };
  const listed = runAgenticTools(input, graph, request, { tool: "list_surfaces", args: { limit: 40 } });
  const surfaces = (listed.result as { surfaces: { name: string; count: number; owner: boolean; claim_ids: string[] }[] }).surfaces ?? [];
  const names = surfaces.map((s) => s.name.toLocaleLowerCase());
  for (const pronoun of ["i", "me", "you", "we", "us", "it", "they", "them"]) {
    expect(names).not.toContain(pronoun);
  }
  expect(names).toContain("liz");
  const liz = surfaces.find((s) => s.name.toLocaleLowerCase() === "liz");
  expect(liz).toMatchObject({ owner: true, count: expect.any(Number) });
  expect(liz!.claim_ids.length).toBeGreaterThan(0);
});

test("partial entailment salvages grounded assertions and drops the rest", async () => {
  const graph = peopleGraph();
  const input = projectTreeInputSnapshot(graph, { account_timezone: "UTC", request_context: ownerContext });
  const evidenceId = input.claims.find((c) => c.policy_labels.includes("subject:owner"))!.evidence_spans[0]!.evidence_id;
  const model = {
    agentStep: async () => ({ tool: "done" as const, args: { evidence_ids: [evidenceId] } }),
    compose: async () => ({
      answer_text: "John is your friend. You have a dog.",
      citations: [evidenceId],
      assertions: [
        { text: "John is your friend.", citations: [evidenceId] },
        { text: "You have a dog.", citations: [evidenceId] },
      ],
    }),
    invoke: async ({ input: inv }: { input: unknown }) => {
      const assertion = (inv as { assertion: string }).assertion;
      return { entailed: assertion.includes("friend") };
    },
  };
  const answer = await retrieveAgentic(
    { owner_account_id: "owner", query: "Who are the people in my life?", request_context: ownerContext },
    graph,
    input,
    model,
  );
  expect(answer).toMatchObject({ grounding: { status: "grounded" }, absence: null });
  expect(answer.answer_text).toContain("friend");
  expect(answer.answer_text).not.toContain("dog");
  expect(answer.citations).toEqual([evidenceId]);
});

test("no host packs or expandQuery; people and tools queries share one path", () => {
  for (const banned of [
    "seedPeopleEvidence",
    "seedToolsEvidence",
    "packPeopleComposeEvidence",
    "packToolsComposeEvidence",
    "expandQuery",
    "isPeopleQuery",
  ] as const) {
    expect((agentic as Record<string, unknown>)[banned]).toBeUndefined();
  }
  expect(AGENTIC_SYSTEM_PROMPT).toContain("list_surfaces");
  expect(AGENTIC_SYSTEM_PROMPT).not.toContain("list_subjects");
  expect(AGENTIC_SYSTEM_PROMPT).not.toMatch(/People\/relationship/i);

  // Lexical search must not inject expand tokens like "chatgpt" for tools-ish queries.
  const graph = snapshot();
  const base = graph.claims[0]!;
  const baseEv = graph.evidence[0]!;
  graph.evidence = [
    { ...baseEv, evidence: { ...baseEv.evidence, evidence_id: "e_gpt", excerpt: "chatgpt chatgpt chatgpt" } },
    {
      revision_id: "e_tools",
      evidence: { ...baseEv.evidence, evidence_id: "e_tools", excerpt: "I use tools for writing", event_revision_id: "event" },
    },
  ];
  graph.events[0]!.event.evidence_addressable_refs = ["e_gpt", "e_tools"];
  graph.claims = [
    {
      ...base,
      revision_id: "c_gpt",
      claim: {
        ...base.claim,
        claim_revision_id: "c_gpt",
        claim_lineage_id: "lineage:c_gpt",
        predicate: "mentions",
        evidence_refs: ["e_gpt"],
        policy_labels: ["subject:owner"],
        arguments: [{ slot_id: "object", role: "object", surface: "chatgpt", value: { kind: "literal" as const, value: "chatgpt" } }],
      },
    },
    {
      ...base,
      revision_id: "c_tools",
      claim: {
        ...base.claim,
        claim_revision_id: "c_tools",
        claim_lineage_id: "lineage:c_tools",
        predicate: "uses",
        evidence_refs: ["e_tools"],
        policy_labels: ["subject:owner"],
        arguments: [{ slot_id: "object", role: "object", surface: "tools", value: { kind: "literal" as const, value: "tools" } }],
      },
    },
  ];
  graph.adjacency = graph.claims.map((c) => ({ claim_revision_id: c.revision_id, entity_id: "entity", role_slot_id: "subject" }));
  const input = projectTreeInputSnapshot(graph, { account_timezone: "UTC", request_context: ownerContext });
  const request = { owner_account_id: "owner", query: "What tools do I use", request_context: ownerContext };
  const search = runAgenticTools(input, graph, request, { tool: "search", args: { query: "What tools do I use", limit: 10 } });
  const hits = (search.result as { hits: { claim_revision_id: string; score: number }[] }).hits;
  expect(hits.find((h) => h.claim_revision_id === "c_gpt")).toBeUndefined();
  const toolsHit = hits.find((h) => h.claim_revision_id === "c_tools");
  expect(toolsHit).toBeDefined();
  expect(toolsHit!.score).toBeGreaterThan(0);
});

test("done with empty evidence_ids still uses prior search harvest, not host seed", async () => {
  const graph = peopleGraph();
  const input = projectTreeInputSnapshot(graph, { account_timezone: "UTC", request_context: ownerContext });
  const evidenceId = input.claims.find((c) => c.policy_labels.includes("subject:owner"))!.evidence_spans[0]!.evidence_id;
  let steps = 0;
  let composeSpanCount = 0;
  const model = {
    agentStep: async () => {
      steps += 1;
      return steps === 1
        ? { tool: "search" as const, args: { query: "friend John", limit: 5 } }
        : { tool: "done" as const, args: { evidence_ids: [] } };
    },
    compose: async ({ input: composeInput }: { input: unknown }) => {
      const spans = (composeInput as { evidence_spans: { evidence_id: string }[] }).evidence_spans;
      composeSpanCount = spans.length;
      const ids = spans.map((s) => s.evidence_id);
      return {
        answer_text: "John is someone in your life.",
        citations: ids,
        assertions: [{ text: "John is someone in your life.", citations: ids }],
      };
    },
    invoke: async () => ({ entailed: true }),
  };
  const answer = await retrieveAgentic(
    { owner_account_id: "owner", query: "Who are the people in my life?", request_context: ownerContext },
    graph,
    input,
    model,
  );
  expect(composeSpanCount).toBeGreaterThan(0);
  expect(answer).toMatchObject({ answer_text: "John is someone in your life.", grounding: { status: "grounded" } });
  expect(answer.citations).toContain(evidenceId);
});
