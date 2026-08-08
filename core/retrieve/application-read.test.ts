// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMX-001)
// domain-pending(DIV-DOMX-005)
// domain-pending(DIV-DOMX-006)
import { createHash } from "node:crypto";
import { describe, expect, test } from "bun:test";

import {
  parseCitationRef,
  parseSynthesizedItemId,
  parseSynthesizedPageJson,
} from "@omi-core/ratified-contracts/projections/synthesized";

import {
  ApplicationReadInvalidatedError,
  computeApplicationSynthesizedProjectionGenerationDigest,
  readApplicationSynthesizedPage,
  readApplicationSynthesizedPageWithAttestation,
  type ApplicationReadCoherentCoordinates,
  type ApplicationReadPorts,
  type ApplicationRecallGenerationDigests,
} from "./application-read";
import {
  ApplicationReadDenied,
  readAfterApplicationAuthorization,
  type ApplicationGrantProjectedTreeInputSnapshot,
  type ApplicationMemoryReadAuthorizationRequest,
} from "./authorization-boundary";
import type { ContentSafeRecallTrace, RecallCompletenessInput } from "./recall-integrity";
import { renderStructuralTree, type RenderNode } from "./render";
import { buildDeterministicAnchors } from "./tree";
import { snapshot } from "./tree.fixture";
import type { GraphSnapshot } from "./index";

const digest = (value: string): string => createHash("sha256").update(value).digest("hex");
const DECLARED_FRONTIER = "frontier-v1:declared";

const authorization = (): ApplicationMemoryReadAuthorizationRequest => ({
  owner_account_id: "owner",
  credential: {
    owner_account_id: "owner",
    credential_kind: "mcp_api_key",
    app_id: "app:a",
    key_id: "key:a",
    scopes: ["memories.read"],
    active: true,
  },
  persisted_grant: {
    owner_account_id: "owner",
    consumer: "mcp",
    app_id: "app:a",
    key_id: "key:a",
    enabled: true,
    default_read: true,
    scopes: ["memories.read"],
  },
});

const project = (
  graph: GraphSnapshot = snapshot(),
  request: ApplicationMemoryReadAuthorizationRequest = authorization(),
): ApplicationGrantProjectedTreeInputSnapshot => readAfterApplicationAuthorization(request, () => ({
  snapshot: structuredClone(graph),
  options: { account_timezone: "UTC" },
}));

const generations = (suffix = "a"): ApplicationRecallGenerationDigests => ({
  authorization_generation_digest: digest(`authorization:${suffix}`),
  synthesized_projection_generation_digest: digest(`synthesized:${suffix}`),
  durable_generation_digest: digest(`durable:${suffix}`),
  overlay_generation_digest: digest(`overlay:${suffix}`),
  declared_generation_digest: digest(`declared:${suffix}`),
  accepted_generation_digest: digest(`accepted:${suffix}`),
  stm_generation_digest: digest(`stm:${suffix}`),
});

const coordinates = (
  generation: ApplicationRecallGenerationDigests,
  suffix = "a",
  timestamp = 1_800_000_000,
): ApplicationReadCoherentCoordinates => ({
  owner_identity_digest: digest(`owner-identity:${suffix}`),
  application_identity_digest: digest(`application-identity:${suffix}`),
  credential_identity_digest: digest(`credential-identity:${suffix}`),
  authorization_state_digest: generation.authorization_generation_digest,
  grant_state_digest: digest(`grant-state:${suffix}`),
  account_head_digest: digest(`account-head:${suffix}`),
  authorized_graph_digest: digest(`authorized-graph:${suffix}`),
  coherent_projection_commit_digest: digest(`projection-commit:${suffix}`),
  visibility_digest: digest(`visibility:${suffix}`),
  filter_digest: digest(`filter:${suffix}`),
  query_digest: digest(`query:${suffix}`),
  source_digest: digest(`source:${suffix}`),
  read_mode_digest: digest(`read-mode:${suffix}`),
  read_timestamp_epoch_seconds: timestamp,
});

const completeCoverage = (overrides: Partial<RecallCompletenessInput> = {}): RecallCompletenessInput => ({
  declared_frontier: DECLARED_FRONTIER,
  accepted: { state: "no_eligible", searched_frontier: null },
  stm: { state: "no_eligible", searched_frontier: null },
  projection_freshness: "fresh",
  intentional_bounds: [],
  ...overrides,
});

interface LoadConfig {
  readonly graph: GraphSnapshot;
  readonly projected: ApplicationGrantProjectedTreeInputSnapshot;
  readonly generations: ApplicationRecallGenerationDigests;
  readonly coverage: RecallCompletenessInput;
  readonly coordinates: ApplicationReadCoherentCoordinates;
  readonly renders: readonly RenderNode[];
}

const loadConfig = (options: {
  graph?: GraphSnapshot;
  generation?: ApplicationRecallGenerationDigests;
  coverage?: RecallCompletenessInput;
  coordinateSuffix?: string;
  timestamp?: number;
} = {}): LoadConfig => {
  const graph = options.graph ?? snapshot();
  const projected = project(graph);
  const generation = {
    ...(options.generation ?? generations()),
    synthesized_projection_generation_digest:
      computeApplicationSynthesizedProjectionGenerationDigest(projected, []),
  };
  return {
    graph,
    projected,
    generations: generation,
    coverage: options.coverage ?? completeCoverage(),
    coordinates: coordinates(generation, options.coordinateSuffix, options.timestamp),
    renders: [],
  };
};

const withProducedRenders = async (
  config: LoadConfig,
  summaries: readonly string[],
  citations: readonly string[] = ["e1"],
  modelVersion = "render-model-v1",
): Promise<LoadConfig> => {
  if (summaries.length === 0) return config;
  const tree = buildDeterministicAnchors(config.projected);
  const selectedNodes = [...tree.nodes].sort((left, right) => left.node_id.localeCompare(right.node_id)).slice(0, summaries.length);
  if (selectedNodes.length !== summaries.length) throw new Error("test requested more renders than structural nodes");
  const summaryByNode = new Map(selectedNodes.map((node, index) => [node.node_id, summaries[index]!]));
  const renders = await renderStructuralTree(tree, config.projected, {
    render: async (request) => {
      const nodeId = (request.input as { node: { node_id: string } }).node.node_id;
      return {
        summary_text: summaryByNode.get(nodeId) ?? `Unused summary ${nodeId}`,
        citations: [...citations],
      };
    },
  }, {
    strategy: "application-read-qa",
    model_version: modelVersion,
    prompt_version: "prompt-v1",
    policy_version: "policy-v1",
    schema_version: "schema-v1",
  });
  const byNode = new Map(renders.map((render) => [render.node_id, render]));
  const selectedRenders = selectedNodes.map((node) => byNode.get(node.node_id)!);
  return {
    ...config,
    generations: {
      ...config.generations,
      // Citationless renders are intentionally retained only for the negative
      // produced-authority reproducer below; the public precompute helper must
      // and does reject them.
      synthesized_projection_generation_digest: citations.length === 0
        ? config.generations.synthesized_projection_generation_digest
        : computeApplicationSynthesizedProjectionGenerationDigest(config.projected, selectedRenders),
    },
    renders: selectedRenders,
  };
};

const canonicalVisibleTuple = (render: RenderNode): string => JSON.stringify([
  "application-visible-order-v1",
  render.node_id,
  `render:${render.render_hash}`,
]);

const expectedVisibleKey = (render: RenderNode): string =>
  `vk1_${digest(`visible-key:${canonicalVisibleTuple(render)}`)}`;

interface Counters {
  resolve: number;
  coherent: number;
  durable: number;
  verify: number;
  visible: number;
  item: number;
  citation: number;
  traceCodec: number;
  issue: number;
  sink: number;
}

interface Harness {
  readonly ports: ApplicationReadPorts;
  readonly counters: Counters;
  readonly traceInputs: ContentSafeRecallTrace[];
  readonly visibleInputs: string[];
  readonly citationInputs: string[];
  readonly issueInputs: Array<{ key: string; attestation: unknown }>;
  readonly verifyInputs: Array<{ cursor: string; attestation: unknown }>;
  readonly sequence: string[];
}

const harness = (options: {
  loads?: readonly LoadConfig[];
  authorizations?: readonly ApplicationMemoryReadAuthorizationRequest[];
  durable?: (input: ApplicationGrantProjectedTreeInputSnapshot, config: LoadConfig) => unknown;
  verify?: ApplicationReadPorts["verifyCursor"];
  issue?: ApplicationReadPorts["issueCursor"];
  visibleCodec?: ApplicationReadPorts["encodeVisibleKey"];
  itemCodec?: ApplicationReadPorts["encodeItemRef"];
  citationCodec?: ApplicationReadPorts["encodeCitationRef"];
  traceCodec?: ApplicationReadPorts["encodeTraceRef"];
  sink?: ApplicationReadPorts["traceSink"];
} = {}): Harness => {
  const loads = options.loads ?? [loadConfig()];
  const authorizations = options.authorizations ?? [authorization()];
  const counters: Counters = {
    resolve: 0, coherent: 0, durable: 0, verify: 0, visible: 0,
    item: 0, citation: 0, traceCodec: 0, issue: 0, sink: 0,
  };
  const traceInputs: ContentSafeRecallTrace[] = [];
  const visibleInputs: string[] = [];
  const citationInputs: string[] = [];
  const issueInputs: Array<{ key: string; attestation: unknown }> = [];
  const verifyInputs: Array<{ cursor: string; attestation: unknown }> = [];
  const sequence: string[] = [];
  const cursorKeys = new Map<string, string>();
  let current = loads[0]!;

  const ports: ApplicationReadPorts = {
    resolveAttempt: () => {
      sequence.push("resolve");
      const resolveIndex = counters.resolve++;
      const request = authorizations[Math.min(resolveIndex, authorizations.length - 1)]!;
      return {
        authorization_request: structuredClone(request),
        load_coherent: () => {
          sequence.push("coherent");
          const loadIndex = counters.coherent++;
          current = loads[Math.min(loadIndex, loads.length - 1)]!;
          return {
            projection_load: {
              snapshot: structuredClone(current.graph),
              options: { account_timezone: "UTC" },
            },
            coverage: structuredClone(current.coverage),
            generations: { ...current.generations },
            read_coordinates: { ...current.coordinates },
          };
        },
      };
    },
    loadDurableRenders: (input) => {
      sequence.push("durable");
      counters.durable++;
      return options.durable ? options.durable(input, current) : [...current.renders];
    },
    verifyCursor: (cursor, attestation) => {
      sequence.push("verify");
      counters.verify++;
      verifyInputs.push({ cursor, attestation });
      if (options.verify) return options.verify(cursor, attestation);
      const key = cursorKeys.get(cursor);
      if (!key) throw new TestInvalidCursorError();
      return key;
    },
    encodeVisibleKey: (tuple) => {
      sequence.push("visible");
      counters.visible++;
      visibleInputs.push(tuple);
      return options.visibleCodec ? options.visibleCodec(tuple) : `vk1_${digest(`visible-key:${tuple}`)}`;
    },
    encodeItemRef: (ref) => {
      sequence.push("item");
      counters.item++;
      return options.itemCodec ? options.itemCodec(ref) : `mem1_${digest(`item-key:${ref}`)}`;
    },
    encodeCitationRef: (closure) => {
      sequence.push("citation");
      counters.citation++;
      citationInputs.push(closure);
      return options.citationCodec ? options.citationCodec(closure) : `cit1_${digest(`citation-key:${closure}`)}`;
    },
    encodeTraceRef: (ref) => {
      sequence.push("trace");
      counters.traceCodec++;
      return options.traceCodec ? options.traceCodec(ref) : `tr1_${digest(`trace-key:${ref}`)}`;
    },
    issueCursor: (key, attestation) => {
      sequence.push("issue");
      counters.issue++;
      issueInputs.push({ key, attestation });
      if (options.issue) return options.issue(key, attestation);
      const cursor = `cursor1.${digest(`${key}:${attestation.projected_content_digest}:${attestation.query_digest}`)}`;
      cursorKeys.set(cursor, key);
      return cursor;
    },
    traceSink: async (trace) => {
      sequence.push("sink");
      counters.sink++;
      traceInputs.push(structuredClone(trace));
      if (options.sink) await options.sink(trace);
    },
  };
  return { ports, counters, traceInputs, visibleInputs, citationInputs, issueInputs, verifyInputs, sequence };
};

class TestInvalidCursorError extends Error {
  readonly code = "invalid_cursor";
  constructor() {
    super("invalid cursor");
    this.name = "TestInvalidCursorError";
  }
}

const firstPage = { limit: 100, cursor: null } as const;

const parsed = async (fixture: Harness, request: { limit: number; cursor: string | null } = firstPage) => {
  const raw = await readApplicationSynthesizedPage(request, fixture.ports);
  const page = parseSynthesizedPageJson(raw);
  expect(page).not.toBeNull();
  return { raw, page: page! };
};

const outwardCounts = (counters: Counters) => ({
  visible: counters.visible,
  item: counters.item,
  citation: counters.citation,
  traceCodec: counters.traceCodec,
  issue: counters.issue,
  sink: counters.sink,
});

describe("production-neutral application synthesized read", () => {
  test("projects only produced renders with grounded evidence closure and exact derived provenance", async () => {
    const config = await withProducedRenders(loadConfig(), ["A grounded synthesized summary."]);
    const render = config.renders[0]!;
    const fixture = harness({ loads: [config] });
    const result = await parsed(fixture);
    const item = result.page.items[0]!;

    expect(String(item.text)).toBe("A grounded synthesized summary.");
    expect(item.citations?.length).toBe(1);
    expect(item.provenance as unknown).toEqual({
      synthesisVersion: render.model_version,
      inputDigest: render.rendered_from_digest,
      outputDigest: render.render_hash!,
    });
    expect(fixture.citationInputs).toEqual([
      JSON.stringify(["application-citation-closure-v1", "e1", "event", "capture", ["a"]]),
    ]);
    expect(fixture.traceInputs[0]!.outcome).toBe("grounded");
    expect(fixture.traceInputs[0]!.stages.cited.length).toBe(1);
    expect(fixture.traceInputs[0]!.stages.grounded.length).toBe(1);
    for (const rawId of [render.node_id, "e1", "event", "capture"]) expect(result.raw).not.toContain(rawId);
  });

  test("rejects cloned, forged, cross-snapshot, and citationless renders before outward work", async () => {
    const config = await withProducedRenders(loadConfig(), ["Produced"]);
    const produced = config.renders[0]!;
    const otherGraph = snapshot();
    otherGraph.claims = otherGraph.claims.map((entry) => entry.revision_id === "a"
      ? { ...entry, claim: { ...entry.claim, predicate: "changed" } }
      : entry);
    const other = await withProducedRenders(loadConfig({ graph: otherGraph }), ["Other snapshot"]);
    const citationless = await withProducedRenders(loadConfig(), ["Ungrounded"], []);
    const attacks: unknown[] = [
      structuredClone(produced),
      { ...produced },
      other.renders[0],
      citationless.renders[0],
    ];

    for (const attack of attacks) {
      const fixture = harness({ loads: [config], durable: () => [attack] });
      await expect(readApplicationSynthesizedPage(firstPage, fixture.ports)).rejects.toThrow();
      expect(outwardCounts(fixture.counters)).toEqual({ visible: 0, item: 0, citation: 0, traceCodec: 0, issue: 0, sink: 0 });
    }
  });

  test("rejects independently produced authority for the same node before recall merge", async () => {
    const base = loadConfig();
    const first = await withProducedRenders(base, ["First independently produced render"]);
    const second = await withProducedRenders(base, ["Second independently produced render"]);
    const firstRender = first.renders[0]!;
    const secondRender = second.renders[0]!;
    expect(firstRender).not.toBe(secondRender);
    expect(firstRender.node_id).toBe(secondRender.node_id);
    expect(firstRender.render_hash).not.toBe(secondRender.render_hash);

    const fixture = harness({
      loads: [{ ...base, renders: [firstRender, secondRender] }],
    });
    await expect(readApplicationSynthesizedPage(firstPage, fixture.ports))
      .rejects.toThrow("unique node authority");
    expect(outwardCounts(fixture.counters)).toEqual({ visible: 0, item: 0, citation: 0, traceCodec: 0, issue: 0, sink: 0 });
  });

  test("keeps accepted and STM completeness-only until they have a produced-render boundary", async () => {
    const limited = loadConfig({ coverage: completeCoverage({
      accepted: { state: "pending", searched_frontier: null },
      stm: { state: "unavailable", searched_frontier: null },
      intentional_bounds: ["source_bound"],
    }) });
    const result = await parsed(harness({ loads: [limited] }));
    expect(result.page.items).toEqual([]);
    expect(result.page.absence).toEqual({ kind: "query_gap" });
    expect(String(result.page.completeness.status)).toBe("degraded");
    expect(result.page.completeness.reasons.map(String)).toEqual([
      "accepted_work_pending", "projection_unavailable", "source_bound",
    ]);

    for (const coverage of [
      completeCoverage({ accepted: { state: "searched", searched_frontier: DECLARED_FRONTIER } }),
      completeCoverage({ stm: { state: "searched", searched_frontier: "frontier-v1:stm" } }),
    ]) {
      const fixture = harness({ loads: [loadConfig({ coverage })] });
      await expect(readApplicationSynthesizedPage(firstPage, fixture.ports)).rejects.toThrow("produced-render boundary");
      expect(fixture.counters.durable).toBe(0);
      expect(outwardCounts(fixture.counters)).toEqual({ visible: 0, item: 0, citation: 0, traceCodec: 0, issue: 0, sink: 0 });
    }
  });

  test("preserves mixed limitation reasons under degraded > incomplete > partial precedence", async () => {
    const cases: readonly [RecallCompletenessInput, string, readonly string[]][] = [
      [completeCoverage({
        accepted: { state: "pending", searched_frontier: null },
        intentional_bounds: ["source_bound"],
      }), "incomplete", ["accepted_work_pending", "source_bound"]],
      [completeCoverage({
        accepted: { state: "pending", searched_frontier: null },
        projection_freshness: "unavailable",
        intentional_bounds: ["source_bound"],
      }), "degraded", ["accepted_work_pending", "projection_unavailable", "source_bound"]],
    ];
    for (const [coverage, status, reasons] of cases) {
      const result = await parsed(harness({ loads: [loadConfig({ coverage })] }));
      expect(String(result.page.completeness.status)).toBe(status);
      expect(result.page.completeness.reasons.map(String)).toEqual([...reasons]);
      expect(result.page.window).toEqual({ status: "incomplete", complete: false, hasMore: false, nextCursor: null });
    }
  });

  test("derives deterministic pagination solely from post-dedupe server-keyed sort tuples", async () => {
    const config = await withProducedRenders(loadConfig(), ["First", "Second", "Third"]);
    const forward = harness({ loads: [config] });
    const reverse = harness({ loads: [config], durable: () => [...config.renders].reverse() });
    const firstForward = await parsed(forward, { limit: 2, cursor: null });
    const firstReverse = await parsed(reverse, { limit: 2, cursor: null });
    expect(firstForward.raw).toBe(firstReverse.raw);
    expect(firstForward.page.items.map((item) => String(item.text))).toEqual(["First", "Second"]);
    expect(forward.issueInputs).toHaveLength(1);
    expect(forward.issueInputs[0]!.key).toBe(expectedVisibleKey(config.renders[1]!));
    expect(forward.visibleInputs).toEqual(config.renders.map(canonicalVisibleTuple));

    const nextCursor = firstForward.page.window.nextCursor;
    expect(typeof nextCursor).toBe("string");
    const second = await parsed(forward, { limit: 2, cursor: nextCursor });
    expect(second.page.items.map((item) => String(item.text))).toEqual(["Third"]);
    expect(second.page.window).toEqual({ status: "complete", complete: true, hasMore: false, nextCursor: null });
    for (const render of config.renders) {
      expect(String(nextCursor)).not.toContain(render.node_id);
      expect(JSON.stringify(forward.issueInputs)).not.toContain(render.node_id);
    }
  });

  test("the exact produced-render set is order-independent across the final fence", async () => {
    const config = await withProducedRenders(loadConfig(), ["One", "Two", "Three"]);
    let durableCall = 0;
    const fixture = harness({
      loads: [config],
      durable: () => durableCall++ % 2 === 0 ? [...config.renders] : [...config.renders].reverse(),
    });
    const result = await parsed(fixture);
    expect(result.page.items.map((item) => String(item.text))).toEqual(["One", "Two", "Three"]);
    expect(fixture.counters.durable).toBe(2);
    expect(outwardCounts(fixture.counters)).toEqual({ visible: 3, item: 3, citation: 3, traceCodec: 4, issue: 0, sink: 1 });
  });

  test("a render-set-only change retries, then emits only the stable replacement set", async () => {
    const base = loadConfig({ coordinateSuffix: "stable" });
    const first = await withProducedRenders(base, ["First render set"]);
    const replacement = await withProducedRenders(base, ["Replacement render set"]);
    const fixture = harness({ loads: [first, replacement, replacement, replacement] });
    const result = await parsed(fixture);
    expect(result.page.items.map((item) => String(item.text))).toEqual(["Replacement render set"]);
    expect(fixture.counters.durable).toBe(4);
    expect(outwardCounts(fixture.counters)).toEqual({ visible: 1, item: 1, citation: 1, traceCodec: 2, issue: 0, sink: 1 });
  });

  test("model-version-only render-set churn invalidates with zero outward work", async () => {
    const base = loadConfig({ coordinateSuffix: "stable" });
    const first = await withProducedRenders(base, ["Same summary"], ["e1"], "render-model-v1");
    const second = await withProducedRenders(base, ["Same summary"], ["e1"], "render-model-v2");
    const fixture = harness({ loads: [first, second, first, second] });
    await expect(readApplicationSynthesizedPage(firstPage, fixture.ports)).rejects.toBeInstanceOf(ApplicationReadInvalidatedError);
    expect(fixture.counters.durable).toBe(4);
    expect(outwardCounts(fixture.counters)).toEqual({ visible: 0, item: 0, citation: 0, traceCodec: 0, issue: 0, sink: 0 });
  });

  test("a retried invalidated attempt performs outward work only once after the stable fence", async () => {
    const a = await withProducedRenders(loadConfig({ generation: generations("a"), coordinateSuffix: "stable" }), ["Stable after retry"]);
    const b = await withProducedRenders(loadConfig({ generation: generations("b"), coordinateSuffix: "stable" }), ["Stable after retry"]);
    const fixture = harness({ loads: [a, b, b, b] });
    const result = await parsed(fixture);
    expect(result.page.items.map((item) => String(item.text))).toEqual(["Stable after retry"]);
    expect(fixture.counters.resolve).toBe(4);
    expect(fixture.counters.coherent).toBe(4);
    expect(fixture.counters.durable).toBe(4);
    expect(outwardCounts(fixture.counters)).toEqual({ visible: 1, item: 1, citation: 1, traceCodec: 2, issue: 0, sink: 1 });
    expect(fixture.sequence.indexOf("visible")).toBeGreaterThan(fixture.sequence.lastIndexOf("coherent"));
  });

  test("double invalidation is externally silent", async () => {
    const configs: LoadConfig[] = [];
    for (const suffix of ["a", "b", "c", "d"]) {
      configs.push(await withProducedRenders(loadConfig({ generation: generations(suffix), coordinateSuffix: "stable" }), [`Render ${suffix}`]));
    }
    const fixture = harness({ loads: configs });
    await expect(readApplicationSynthesizedPage(firstPage, fixture.ports)).rejects.toBeInstanceOf(ApplicationReadInvalidatedError);
    expect(fixture.counters.durable).toBe(4);
    expect(outwardCounts(fixture.counters)).toEqual({ visible: 0, item: 0, citation: 0, traceCodec: 0, issue: 0, sink: 0 });
  });

  test("timestamp-only drift invalidates twice and remains externally silent", async () => {
    const first = await withProducedRenders(loadConfig({ coordinateSuffix: "stable", timestamp: 100 }), ["Timestamp-bound"]);
    const second = { ...first, coordinates: { ...first.coordinates, read_timestamp_epoch_seconds: 101 } };
    const fixture = harness({ loads: [first, second, first, second] });
    await expect(readApplicationSynthesizedPage(firstPage, fixture.ports)).rejects.toBeInstanceOf(ApplicationReadInvalidatedError);
    expect(fixture.counters.durable).toBe(4);
    expect(outwardCounts(fixture.counters)).toEqual({ visible: 0, item: 0, citation: 0, traceCodec: 0, issue: 0, sink: 0 });
  });

  test("final revocation returns no bytes and performs no outward work", async () => {
    const config = await withProducedRenders(loadConfig(), ["Revoked"]);
    const revoked = authorization();
    revoked.persisted_grant = { ...revoked.persisted_grant!, enabled: false };
    const fixture = harness({ loads: [config], authorizations: [authorization(), revoked] });
    await expect(readApplicationSynthesizedPage(firstPage, fixture.ports)).rejects.toBeInstanceOf(ApplicationReadDenied);
    expect(fixture.counters.durable).toBe(1);
    expect(outwardCounts(fixture.counters)).toEqual({ visible: 0, item: 0, citation: 0, traceCodec: 0, issue: 0, sink: 0 });
  });

  test("verifies a raw cursor from the coherent receipt before any render or candidate work", async () => {
    const config = await withProducedRenders(loadConfig(), ["Cursor-bound"]);
    const expected = expectedVisibleKey(config.renders[0]!);
    const fixture = harness({
      loads: [config],
      verify: (cursor, attestation) => {
        expect(cursor).toBe("cursor.valid");
        expect(Object.isFrozen(attestation)).toBe(true);
        expect(Object.isFrozen(attestation.coverage)).toBe(true);
        return expected;
      },
    });
    await parsed(fixture, { limit: 1, cursor: "cursor.valid" });
    expect(fixture.sequence.slice(0, 4)).toEqual(["resolve", "coherent", "verify", "durable"]);

    const invalid = new TestInvalidCursorError();
    const rejected = harness({ loads: [config], verify: () => { throw invalid; } });
    try {
      await readApplicationSynthesizedPage({ limit: 1, cursor: "cursor.invalid" }, rejected.ports);
      throw new Error("expected cursor failure");
    } catch (error) {
      expect(error).toBe(invalid);
    }
    expect(rejected.counters.durable).toBe(0);
    expect(outwardCounts(rejected.counters)).toEqual({ visible: 0, item: 0, citation: 0, traceCodec: 0, issue: 0, sink: 0 });
  });

  test("rejects a false coherent render-set receipt after cursor verification and before outward work", async () => {
    const config = await withProducedRenders(loadConfig(), ["Digest-bound"]);
    const wrong = {
      ...config,
      generations: {
        ...config.generations,
        synthesized_projection_generation_digest: digest("wrong-produced-render-set"),
      },
    };
    const fixture = harness({
      loads: [wrong],
      verify: () => expectedVisibleKey(config.renders[0]!),
    });
    await expect(readApplicationSynthesizedPage({ limit: 1, cursor: "cursor.valid" }, fixture.ports))
      .rejects.toThrow("coherent synthesized projection generation disagrees");
    expect(fixture.sequence.slice(0, 4)).toEqual(["resolve", "coherent", "verify", "durable"]);
    expect(fixture.counters.durable).toBe(1);
    expect(outwardCounts(fixture.counters)).toEqual({ visible: 0, item: 0, citation: 0, traceCodec: 0, issue: 0, sink: 0 });
  });

  test("requires dedicated fixed-format keyed visible, item, citation, and trace handles", async () => {
    const config = await withProducedRenders(loadConfig(), ["Strict handles"]);
    expect(parseSynthesizedItemId("arbitrary-item-sentinel")).not.toBeNull();
    expect(parseCitationRef("arbitrary-citation-sentinel")).not.toBeNull();

    const cases: readonly [Partial<Parameters<typeof harness>[0]>, string][] = [
      [{ visibleCodec: (tuple: string) => tuple }, "visible-key codec"],
      [{ itemCodec: () => "arbitrary-item-sentinel" }, "item codec"],
      [{ citationCodec: () => "arbitrary-citation-sentinel" }, "citation codec"],
      [{ traceCodec: () => "arbitrary-trace-sentinel" }, "trace codec"],
    ];
    for (const [ports, message] of cases) {
      const fixture = harness({ loads: [config], ...ports });
      await expect(readApplicationSynthesizedPage(firstPage, fixture.ports)).rejects.toThrow(message);
      expect(fixture.counters.sink).toBe(0);
    }
  });

  test("scope, grant, owner, app, and key denials perform zero read or outward work", async () => {
    const base = authorization();
    const denied: ApplicationMemoryReadAuthorizationRequest[] = [
      { ...base, credential: { ...base.credential, scopes: [] } },
      { ...base, persisted_grant: null },
      { ...base, persisted_grant: { ...base.persisted_grant!, enabled: false } },
      { ...base, credential: { ...base.credential, owner_account_id: "owner:b" } },
      { ...base, persisted_grant: { ...base.persisted_grant!, app_id: "app:b" } },
      { ...base, persisted_grant: { ...base.persisted_grant!, key_id: "key:b" } },
    ];
    for (const request of denied) {
      const fixture = harness({ authorizations: [request] });
      await expect(readApplicationSynthesizedPage(firstPage, fixture.ports)).rejects.toBeInstanceOf(ApplicationReadDenied);
      expect(fixture.counters.resolve).toBe(1);
      expect(fixture.counters.coherent).toBe(0);
      expect(fixture.counters.durable).toBe(0);
      expect(fixture.counters.verify).toBe(0);
      expect(outwardCounts(fixture.counters)).toEqual({ visible: 0, item: 0, citation: 0, traceCodec: 0, issue: 0, sink: 0 });
    }
  });

  test("request input is exactly limit and cursor and cannot inject renders, text, citations, or order", async () => {
    const fixture = harness();
    for (const extra of ["renders", "synthesized_text", "citations", "order_key"]) {
      await expect(readApplicationSynthesizedPage({ limit: 1, cursor: null, [extra]: "attacker" } as never, fixture.ports)).rejects.toThrow(TypeError);
    }
    expect(fixture.counters.resolve).toBe(0);
  });

  test("rejects hostile produced-render arrays without invoking accessors", async () => {
    const config = await withProducedRenders(loadConfig(), ["Array-safe"]);
    const render = config.renders[0]!;
    let getterCalls = 0;
    const getterArray: unknown[] = [];
    Object.defineProperty(getterArray, "0", {
      enumerable: true,
      get: () => { getterCalls++; return render; },
    });
    Object.defineProperty(getterArray, "length", { value: 1, writable: true });
    const sparse = new Array(2);
    sparse[0] = render;
    const decorated = [render];
    Object.defineProperty(decorated, "extra", { enumerable: true, value: render });
    for (const value of [getterArray, sparse, decorated, [render, render], new Proxy([render], {})]) {
      const fixture = harness({ loads: [config], durable: () => value });
      await expect(readApplicationSynthesizedPage(firstPage, fixture.ports)).rejects.toThrow(TypeError);
      expect(outwardCounts(fixture.counters)).toEqual({ visible: 0, item: 0, citation: 0, traceCodec: 0, issue: 0, sink: 0 });
    }
    expect(getterCalls).toBe(0);
  });

  test("returns a frozen provider-neutral attestation without placing read coordinates in page bytes", async () => {
    const config = await withProducedRenders(loadConfig({ timestamp: 1234 }), ["Attested"]);
    const fixture = harness({ loads: [config] });
    const result = await readApplicationSynthesizedPageWithAttestation(firstPage, fixture.ports);
    expect(parseSynthesizedPageJson(result.canonical_json)).not.toBeNull();
    expect(Object.isFrozen(result)).toBe(true);
    expect(Object.isFrozen(result.attestation)).toBe(true);
    expect(Object.isFrozen(result.attestation.coverage)).toBe(true);
    expect(result.attestation.last_visible_key).toBe(expectedVisibleKey(config.renders[0]!));
    expect(result.attestation.read_timestamp_epoch_seconds).toBe(1234);
    expect(result.attestation.synthesized_projection_generation_digest).toMatch(/^[a-f0-9]{64}$/);
    expect(result.attestation.synthesized_projection_generation_digest).not.toBe(config.projected.graph_generation);
    for (const key of ["owner_identity_digest", "grant_state_digest", "query_digest", "read_timestamp_epoch_seconds"] as const) {
      expect(result.canonical_json).not.toContain(String(result.attestation[key]));
    }
  });

  test("trace sink sync and async failures cannot change canonical result", async () => {
    const config = await withProducedRenders(loadConfig(), ["Trace safe"]);
    const baseline = await parsed(harness({ loads: [config] }));
    const sync = await parsed(harness({ loads: [config], sink: () => { throw new Error("sync sink"); } }));
    const asyncFailure = await parsed(harness({
      loads: [config], sink: async () => { throw new Error("async sink"); },
    }));
    expect(sync.raw).toBe(baseline.raw);
    expect(asyncFailure.raw).toBe(baseline.raw);
  });

  test("hostile callback records and coherent loaders fail without accessor execution", async () => {
    const fixture = harness();
    let portGetterCalls = 0;
    const getterPorts = { ...fixture.ports } as Record<string, unknown>;
    Object.defineProperty(getterPorts, "issueCursor", {
      enumerable: true,
      get: () => { portGetterCalls++; return fixture.ports.issueCursor; },
    });
    await expect(readApplicationSynthesizedPage(firstPage, getterPorts as unknown as ApplicationReadPorts)).rejects.toThrow(TypeError);
    expect(portGetterCalls).toBe(0);
    expect(fixture.counters.resolve).toBe(0);

    let coherentGetterCalls = 0;
    const hostile: ApplicationReadPorts = {
      ...fixture.ports,
      resolveAttempt: () => ({
        authorization_request: authorization(),
        load_coherent: () => {
          const value = { projection_load: {}, coverage: {}, generations: {} } as Record<string, unknown>;
          Object.defineProperty(value, "read_coordinates", {
            enumerable: true,
            get: () => { coherentGetterCalls++; return {}; },
          });
          return value as never;
        },
      }),
    };
    await expect(readApplicationSynthesizedPage(firstPage, hostile)).rejects.toThrow(TypeError);
    expect(coherentGetterCalls).toBe(0);
  });
});
