// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMX-001)
// domain-pending(DIV-DOMX-006)
import { createHash } from "node:crypto";
import { describe, expect, test } from "bun:test";

import { parseSynthesizedPageJson } from "@omi-core/ratified-contracts/projections/synthesized";

import {
  ApplicationReadInvalidatedError,
  readApplicationSynthesizedPage,
  readApplicationSynthesizedPageWithAttestation,
  type ApplicationReadCoherentCoordinates,
  type ApplicationReadPorts,
  type ApplicationRecallGenerationDigests,
  type ApplicationSynthesizedCandidateRecord,
} from "./application-read";
import {
  ApplicationReadDenied,
  readAfterApplicationAuthorization,
  type ApplicationGrantProjectedTreeInputSnapshot,
  type ApplicationMemoryReadAuthorizationRequest,
} from "./authorization-boundary";
import type { ContentSafeRecallTrace, RecallCompletenessInput } from "./recall-integrity";
import { snapshot } from "./tree.fixture";
import type { GraphSnapshot } from "./index";

const digest = (value: string): string => createHash("sha256").update(value).digest("hex");
const visibleKey = (value: string): string => `vk1_${digest(value)}`;
const DECLARED_FRONTIER = "frontier-v1:declared";
const STM_FRONTIER = "frontier-v1:stm";

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
  durable_generation_digest: digest(`durable:${suffix}`),
  overlay_generation_digest: digest(`overlay:${suffix}`),
  declared_generation_digest: digest(`declared:${suffix}`),
  accepted_generation_digest: digest(`accepted:${suffix}`),
  stm_generation_digest: digest(`stm:${suffix}`),
});

const coordinates = (
  generation: ApplicationRecallGenerationDigests,
  suffix = "a",
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
  read_timestamp_epoch_seconds: 1_800_000_000,
});

const completeCoverage = (overrides: Partial<RecallCompletenessInput> = {}): RecallCompletenessInput => ({
  declared_frontier: DECLARED_FRONTIER,
  accepted: { state: "no_eligible", searched_frontier: null },
  stm: { state: "no_eligible", searched_frontier: null },
  projection_freshness: "fresh",
  intentional_bounds: [],
  ...overrides,
});

type CandidateOverrides = Partial<ApplicationSynthesizedCandidateRecord>;

const candidate = (
  input: ApplicationGrantProjectedTreeInputSnapshot,
  generation: ApplicationRecallGenerationDigests,
  origin: ApplicationSynthesizedCandidateRecord["origin"],
  ref: string,
  overrides: CandidateOverrides = {},
): ApplicationSynthesizedCandidateRecord => ({
  owner_account_id: input.owner_account_id,
  projection_authorization_digest: input.projection_authorization_digest,
  reader_projection_digest: input.reader_projection_digest,
  authorization_generation_digest: generation.authorization_generation_digest,
  projection_generation_digest: input.graph_generation,
  projected_content_digest: input.projected_content_digest,
  durable_generation_digest: generation.durable_generation_digest,
  overlay_generation_digest: generation.overlay_generation_digest,
  declared_generation_digest: generation.declared_generation_digest,
  accepted_generation_digest: generation.accepted_generation_digest,
  stm_generation_digest: generation.stm_generation_digest,
  candidate_ref: `candidate:${ref}`,
  dedupe_ref: `dedupe:${ref}`,
  dedupe_rank: 1,
  order_key: `order:${ref}`,
  stable_visible_key: visibleKey(ref),
  origin,
  frontier: origin === "stm" ? STM_FRONTIER
    : origin === "accepted_unprocessed" ? DECLARED_FRONTIER
      : generation.durable_generation_digest,
  supersedes_refs: [],
  effective_policy: { subject_class: "generic", sensitivity: "generic", capture_class: "generic" },
  synthesized_text: `Synthesized ${ref}`,
  citation_provenance_ids: [`provenance:${ref}`],
  synthesis_provenance: {
    synthesis_version: "synthesis-v1",
    input_digest: digest(`input:${ref}`),
    output_digest: digest(`output:${ref}`),
  },
  ...overrides,
});

interface CandidateSpec {
  readonly origin: ApplicationSynthesizedCandidateRecord["origin"];
  readonly ref: string;
  readonly overrides?: CandidateOverrides;
}

interface LoadConfig {
  readonly graph: GraphSnapshot;
  readonly projected: ApplicationGrantProjectedTreeInputSnapshot;
  readonly generations: ApplicationRecallGenerationDigests;
  readonly coverage: RecallCompletenessInput;
  readonly coordinates: ApplicationReadCoherentCoordinates;
  readonly overlay: (input: ApplicationGrantProjectedTreeInputSnapshot, generation: ApplicationRecallGenerationDigests) => unknown;
  readonly maxItems: number;
  readonly maxBytes: number;
}

const loadConfig = (options: {
  graph?: GraphSnapshot;
  generation?: ApplicationRecallGenerationDigests;
  coverage?: RecallCompletenessInput;
  coordinateSuffix?: string;
  overlaySpecs?: readonly CandidateSpec[];
  overlay?: LoadConfig["overlay"];
  maxItems?: number;
  maxBytes?: number;
} = {}): LoadConfig => {
  const graph = options.graph ?? snapshot();
  const projected = project(graph);
  const generation = options.generation ?? generations();
  const specs = options.overlaySpecs ?? [];
  return {
    graph,
    projected,
    generations: generation,
    coverage: options.coverage ?? completeCoverage(),
    coordinates: coordinates(generation, options.coordinateSuffix),
    overlay: options.overlay ?? ((input, current) => specs.map((spec) =>
      candidate(input, current, spec.origin, spec.ref, spec.overrides))),
    maxItems: options.maxItems ?? 100,
    maxBytes: options.maxBytes ?? 500_000,
  };
};

interface Counters {
  resolve: number;
  coherent: number;
  durable: number;
  verify: number;
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
  readonly issueInputs: Array<{ key: string; attestation: unknown }>;
  readonly verifyInputs: Array<{ cursor: string; attestation: unknown }>;
  readonly sequence: string[];
}

const harness = (options: {
  loads?: readonly LoadConfig[];
  authorizations?: readonly ApplicationMemoryReadAuthorizationRequest[];
  durableSpecs?: readonly CandidateSpec[];
  durable?: (input: ApplicationGrantProjectedTreeInputSnapshot, config: LoadConfig) => unknown;
  verify?: ApplicationReadPorts["verifyCursor"];
  issue?: ApplicationReadPorts["issueCursor"];
  itemCodec?: ApplicationReadPorts["encodeItemRef"];
  citationCodec?: ApplicationReadPorts["encodeCitationRef"];
  traceCodec?: ApplicationReadPorts["encodeTraceRef"];
  sink?: ApplicationReadPorts["traceSink"];
} = {}): Harness => {
  const loads = options.loads ?? [loadConfig()];
  const authorizations = options.authorizations ?? [authorization()];
  const durableSpecs = options.durableSpecs ?? [];
  const counters: Counters = {
    resolve: 0, coherent: 0, durable: 0, verify: 0, item: 0, citation: 0, traceCodec: 0, issue: 0, sink: 0,
  };
  const traceInputs: ContentSafeRecallTrace[] = [];
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
            overlay: {
              max_items: current.maxItems,
              max_bytes: current.maxBytes,
              candidates: current.overlay(current.projected, current.generations),
            },
            coverage: structuredClone(current.coverage),
            generations: { ...current.generations },
            read_coordinates: { ...current.coordinates },
          } as never;
        },
      };
    },
    loadDurableCandidates: (input) => {
      sequence.push("durable");
      counters.durable++;
      if (options.durable) return options.durable(input, current);
      return durableSpecs.map((spec) => candidate(input, current.generations, spec.origin, spec.ref, spec.overrides));
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
    encodeItemRef: (ref) => {
      counters.item++;
      return options.itemCodec ? options.itemCodec(ref) : `mem1_${digest(`item-key:${ref}`)}`;
    },
    encodeCitationRef: (ref) => {
      counters.citation++;
      return options.citationCodec ? options.citationCodec(ref) : `cit1_${digest(`citation-key:${ref}`)}`;
    },
    encodeTraceRef: (ref) => {
      counters.traceCodec++;
      return options.traceCodec ? options.traceCodec(ref) : `tr1_${digest(`trace-key:${ref}`)}`;
    },
    issueCursor: (key, attestation) => {
      counters.issue++;
      issueInputs.push({ key, attestation });
      if (options.issue) return options.issue(key, attestation);
      const cursor = `cursor1.${digest(`${key}:${attestation.projected_content_digest}:${attestation.query_digest}`)}`;
      cursorKeys.set(cursor, key);
      return cursor;
    },
    traceSink: async (trace) => {
      counters.sink++;
      traceInputs.push(structuredClone(trace));
      if (options.sink) await options.sink(trace);
    },
  };
  return { ports, counters, traceInputs, issueInputs, verifyInputs, sequence };
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

describe("production-neutral application synthesized read", () => {
  test("durable miss still returns an authorized STM hit", async () => {
    const fixture = harness({
      loads: [loadConfig({
        coverage: completeCoverage({ stm: { state: "searched", searched_frontier: STM_FRONTIER } }),
        overlaySpecs: [{ origin: "stm", ref: "stm-hit" }],
      })],
    });
    const result = await parsed(fixture);
    expect(result.page.items.map((item) => String(item.text))).toEqual(["Synthesized stm-hit"]);
    expect(result.page.absence).toBeNull();
    expect(String(result.page.completeness.frontiers.newestSearchedStmFrontier)).toBe(STM_FRONTIER);
    expect(fixture.counters.durable).toBe(1);
  });

  test("durable miss still returns accepted-unprocessed material", async () => {
    const fixture = harness({
      loads: [loadConfig({
        coverage: completeCoverage({ accepted: { state: "searched", searched_frontier: DECLARED_FRONTIER } }),
        overlaySpecs: [{ origin: "accepted_unprocessed", ref: "accepted-hit" }],
      })],
    });
    const result = await parsed(fixture);
    expect(result.page.items.map((item) => String(item.text))).toEqual(["Synthesized accepted-hit"]);
    expect(String(result.page.completeness.frontiers.newestSearchedAcceptedFrontier)).toBe(DECLARED_FRONTIER);
  });

  test("merges permutations with deterministic dedupe, supersession, and cursor paging", async () => {
    const specs: CandidateSpec[] = [
      { origin: "durable", ref: "durable", overrides: { dedupe_ref: "dedupe:same", dedupe_rank: 3, order_key: "order:020" } },
      { origin: "durable", ref: "loser", overrides: { dedupe_ref: "dedupe:same", dedupe_rank: 2, order_key: "order:001" } },
      { origin: "durable", ref: "precursor", overrides: { dedupe_ref: "dedupe:precursor", order_key: "order:000" } },
      { origin: "durable", ref: "successor", overrides: {
        dedupe_ref: "dedupe:successor", order_key: "order:010", supersedes_refs: ["candidate:precursor"],
      } },
      { origin: "durable", ref: "tail", overrides: { order_key: "order:030" } },
    ];
    const forward = harness({ durableSpecs: specs });
    const reverse = harness({ durableSpecs: [...specs].reverse() });
    const firstForward = await parsed(forward, { limit: 2, cursor: null });
    const firstReverse = await parsed(reverse, { limit: 2, cursor: null });
    expect(firstForward.raw).toBe(firstReverse.raw);
    expect(firstForward.page.items.map((item) => String(item.text))).toEqual(["Synthesized successor", "Synthesized durable"]);
    expect(firstForward.page.window.hasMore).toBe(true);
    expect(forward.counters.issue).toBe(1);

    const second = await parsed(forward, { limit: 2, cursor: firstForward.page.window.nextCursor });
    expect(second.page.items.map((item) => String(item.text))).toEqual(["Synthesized tail"]);
    expect(second.page.window).toEqual({ status: "complete", complete: true, hasMore: false, nextCursor: null });
    expect(forward.counters.verify).toBe(1);
  });

  test("maps complete, incomplete, degraded, and partial kernel states without claiming global absence", async () => {
    const cases: readonly [RecallCompletenessInput, string, readonly string[]][] = [
      [completeCoverage(), "complete", []],
      [completeCoverage({ accepted: { state: "pending", searched_frontier: null } }), "incomplete", ["accepted_work_pending"]],
      [completeCoverage({
        accepted: { state: "unavailable", searched_frontier: null },
        stm: { state: "unavailable", searched_frontier: null },
        projection_freshness: "unavailable",
      }), "degraded", ["projection_unavailable"]],
      [completeCoverage({ intentional_bounds: ["source_bound"] }), "partial", ["source_bound"]],
    ];
    for (const [coverage, status, reasons] of cases) {
      const result = await parsed(harness({ loads: [loadConfig({ coverage })] }));
      expect(result.page.items).toEqual([]);
      expect(result.page.absence).toEqual({ kind: "query_gap" });
      expect(String(result.page.completeness.status)).toBe(status);
      expect(result.page.completeness.reasons.map(String)).toEqual([...reasons]);
      expect(result.page.window.status).toBe(status === "complete" ? "complete" : "incomplete");
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
      expect(result.page.absence).toEqual({ kind: "query_gap" });
    }
  });

  test("scope, grant, owner, app, and key denials perform zero coherent, synthesis, codec, cursor, and trace work", async () => {
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
      expect(fixture.counters).toEqual({
        resolve: 1, coherent: 0, durable: 0, verify: 0, item: 0, citation: 0, traceCodec: 0, issue: 0, sink: 0,
      });
    }
  });

  test("well-formed private and unknown policy candidates are byte- and trace-noninterfering", async () => {
    const visible: CandidateSpec[] = [
      { origin: "durable", ref: "first", overrides: { order_key: "order:001" } },
      { origin: "durable", ref: "second", overrides: { order_key: "order:002" } },
    ];
    const absent = harness({ durableSpecs: visible });
    const hidden = harness({
      durableSpecs: visible,
      loads: [loadConfig({ overlaySpecs: [
        { origin: "stm", ref: "raw-hidden-sentinel", overrides: {
          effective_policy: { subject_class: "generic", sensitivity: "private", capture_class: "generic" },
          synthesized_text: "RAW-HIDDEN-SENTINEL",
          citation_provenance_ids: ["RAW-HIDDEN-SENTINEL"],
        } },
        { origin: "accepted_unprocessed", ref: "unknown-hidden", overrides: {
          effective_policy: { subject_class: "mystery", sensitivity: "generic", capture_class: "generic" },
        } },
      ] })],
    });
    const absentResult = await parsed(absent, { limit: 1, cursor: null });
    const hiddenResult = await parsed(hidden, { limit: 1, cursor: null });
    expect(hiddenResult.raw).toBe(absentResult.raw);
    expect(hidden.issueInputs).toEqual(absent.issueInputs);
    expect(hidden.traceInputs).toEqual(absent.traceInputs);
    expect(hiddenResult.raw).not.toContain("RAW-HIDDEN-SENTINEL");
    expect(JSON.stringify(hidden.traceInputs)).not.toContain("RAW-HIDDEN-SENTINEL");
  });

  test("malformed, cross-owner, wrong-generation, and raw-ref codec outputs fail closed", async () => {
    const malformedCases: Array<(input: ApplicationGrantProjectedTreeInputSnapshot, generation: ApplicationRecallGenerationDigests) => unknown> = [
      (input, generation) => [{ ...candidate(input, generation, "stm", "extra"), raw_query: "secret" }],
      (input, generation) => [{ ...candidate(input, generation, "stm", "owner"), owner_account_id: "owner:b" }],
      (input, generation) => [{ ...candidate(input, generation, "stm", "generation"), overlay_generation_digest: digest("wrong") }],
    ];
    for (const overlay of malformedCases) {
      const fixture = harness({ loads: [loadConfig({
        coverage: completeCoverage({ stm: { state: "searched", searched_frontier: STM_FRONTIER } }), overlay,
      })] });
      await expect(readApplicationSynthesizedPage(firstPage, fixture.ports)).rejects.toThrow(TypeError);
      expect(fixture.counters.sink).toBe(0);
    }

    const rawItem = harness({
      durableSpecs: [{ origin: "durable", ref: "raw-item" }],
      itemCodec: (ref) => ref,
    });
    await expect(readApplicationSynthesizedPage(firstPage, rawItem.ports)).rejects.toThrow("raw or invalid");
    const rawCitation = harness({
      durableSpecs: [{ origin: "durable", ref: "raw-citation" }],
      citationCodec: (ref) => `opaque:${ref}`,
    });
    await expect(readApplicationSynthesizedPage(firstPage, rawCitation.ports)).rejects.toThrow("raw or invalid");
  });

  test("retries once on graph/frontier generation change and succeeds from one stable snapshot", async () => {
    const a = loadConfig({ generation: generations("a"), coordinateSuffix: "stable" });
    const changedGraph = snapshot();
    changedGraph.claims = changedGraph.claims.map((entry) => entry.revision_id === "a"
      ? { ...entry, claim: { ...entry.claim, predicate: "changed" } }
      : entry);
    const b = loadConfig({ graph: changedGraph, generation: generations("b"), coordinateSuffix: "stable" });
    const fixture = harness({
      loads: [a, b, b, b],
      durableSpecs: [{ origin: "durable", ref: "stable-after-retry" }],
    });
    const result = await parsed(fixture);
    expect(result.page.items.map((item) => String(item.text))).toEqual(["Synthesized stable-after-retry"]);
    expect(fixture.counters.resolve).toBe(4);
    expect(fixture.counters.coherent).toBe(4);
    expect(fixture.counters.durable).toBe(2);
    expect(fixture.counters.sink).toBe(1);
  });

  test("throws a typed invalidated error when the fence changes twice", async () => {
    const configs = ["a", "b", "c", "d"].map((suffix) => loadConfig({
      generation: generations(suffix), coordinateSuffix: "stable",
    }));
    const fixture = harness({ loads: configs, durableSpecs: [{ origin: "durable", ref: "never-emitted" }] });
    await expect(readApplicationSynthesizedPage(firstPage, fixture.ports)).rejects.toBeInstanceOf(ApplicationReadInvalidatedError);
    expect(fixture.counters.durable).toBe(2);
    expect(fixture.counters.sink).toBe(0);
  });

  test("final revocation returns no bytes or trace", async () => {
    const revoked = authorization();
    revoked.persisted_grant = { ...revoked.persisted_grant!, enabled: false };
    const fixture = harness({
      authorizations: [authorization(), revoked],
      durableSpecs: [{ origin: "durable", ref: "revoked" }],
    });
    await expect(readApplicationSynthesizedPage(firstPage, fixture.ports)).rejects.toBeInstanceOf(ApplicationReadDenied);
    expect(fixture.counters.durable).toBe(1);
    expect(fixture.counters.sink).toBe(0);
  });

  test("verifies raw cursors after authorization/coherent attestation and before candidate loading", async () => {
    const expected = visibleKey("cursor-before-durable");
    const invalid = new TestInvalidCursorError();
    const fixture = harness({
      durableSpecs: [{ origin: "durable", ref: "cursor-before-durable" }],
      verify: (cursor, attestation) => {
        expect(cursor).toBe("cursor.valid");
        expect(Object.isFrozen(attestation)).toBe(true);
        expect(Object.isFrozen(attestation.coverage)).toBe(true);
        return expected;
      },
    });
    await parsed(fixture, { limit: 1, cursor: "cursor.valid" });
    expect(fixture.sequence.slice(0, 4)).toEqual(["resolve", "coherent", "verify", "durable"]);

    const rejected = harness({
      durableSpecs: [{ origin: "durable", ref: "never-loaded" }],
      verify: () => { throw invalid; },
    });
    try {
      await readApplicationSynthesizedPage({ limit: 1, cursor: "cursor.invalid" }, rejected.ports);
      throw new Error("expected cursor failure");
    } catch (error) {
      expect(error).toBe(invalid);
    }
    expect(rejected.counters.durable).toBe(0);
  });

  test("issues a cursor only for a nonempty continuation and never for terminal or empty pages", async () => {
    const continuation = harness({ durableSpecs: [
      { origin: "durable", ref: "one", overrides: { order_key: "order:001" } },
      { origin: "durable", ref: "two", overrides: { order_key: "order:002" } },
    ] });
    await parsed(continuation, { limit: 1, cursor: null });
    expect(continuation.counters.issue).toBe(1);
    expect(continuation.issueInputs[0]!.key).toBe(visibleKey("one"));

    const terminal = harness({ durableSpecs: [{ origin: "durable", ref: "only" }] });
    await parsed(terminal, { limit: 1, cursor: null });
    expect(terminal.counters.issue).toBe(0);
    const empty = harness();
    await parsed(empty, { limit: 1, cursor: null });
    expect(empty.counters.issue).toBe(0);
  });

  test("returns a frozen provider-neutral attestation without placing it in page bytes", async () => {
    const fixture = harness({ durableSpecs: [{ origin: "durable", ref: "attested" }] });
    const result = await readApplicationSynthesizedPageWithAttestation(firstPage, fixture.ports);
    expect(parseSynthesizedPageJson(result.canonical_json)).not.toBeNull();
    expect(Object.isFrozen(result)).toBe(true);
    expect(Object.isFrozen(result.attestation)).toBe(true);
    expect(Object.isFrozen(result.attestation.coverage)).toBe(true);
    expect(result.attestation.last_visible_key).toBe(visibleKey("attested"));
    expect(result.attestation.synthesized_projection_generation_digest).toMatch(/^[a-f0-9]{64}$/);
    for (const key of ["owner_identity_digest", "grant_state_digest", "query_digest", "read_timestamp_epoch_seconds"]) {
      expect(result.canonical_json).not.toContain(String(result.attestation[key as keyof typeof result.attestation]));
    }
  });

  test("trace sink sync and async failures cannot change canonical result", async () => {
    const baseline = await parsed(harness({ durableSpecs: [{ origin: "durable", ref: "trace-safe" }] }));
    const sync = await parsed(harness({
      durableSpecs: [{ origin: "durable", ref: "trace-safe" }], sink: () => { throw new Error("sync sink"); },
    }));
    const asyncFailure = await parsed(harness({
      durableSpecs: [{ origin: "durable", ref: "trace-safe" }], sink: async () => { throw new Error("async sink"); },
    }));
    expect(sync.raw).toBe(baseline.raw);
    expect(asyncFailure.raw).toBe(baseline.raw);
  });

  test("raw internal sentinel strings are absent from both canonical page and emitted trace", async () => {
    const raw = "RAW-QUERY-EVIDENCE-EVENT-SOURCE-CREDENTIAL-SECRET";
    const fixture = harness({
      durableSpecs: [{ origin: "durable", ref: raw, overrides: {
        dedupe_ref: raw,
        order_key: raw,
        frontier: raw,
        citation_provenance_ids: [raw],
        synthesized_text: "Allowed synthesized presentation",
      } }],
    });
    const result = await parsed(fixture);
    expect(result.raw).not.toContain(raw);
    expect(JSON.stringify(fixture.traceInputs)).not.toContain(raw);
  });

  test("rejects getter, proxy, class, symbol, nonenumerable, extra, sparse, alias, and TOCTOU shapes", async () => {
    const baseConfig = loadConfig({
      coverage: completeCoverage({ stm: { state: "searched", searched_frontier: STM_FRONTIER } }),
      overlaySpecs: [{ origin: "stm", ref: "shape" }],
    });
    const baseCandidate = candidate(baseConfig.projected, baseConfig.generations, "stm", "shape");
    let getterCalls = 0;
    const getterCandidate = { ...baseCandidate } as Record<string, unknown>;
    Object.defineProperty(getterCandidate, "candidate_ref", {
      enumerable: true,
      get: () => { getterCalls++; return "candidate:attacker"; },
    });
    class CandidateClass { constructor(readonly value: unknown) {} }
    const symbolCandidate = { ...baseCandidate } as Record<PropertyKey, unknown>;
    symbolCandidate[Symbol("secret")] = "raw";
    const hiddenCandidate = { ...baseCandidate };
    Object.defineProperty(hiddenCandidate, "raw_secret", { enumerable: false, value: "raw" });
    const extraCandidate = { ...baseCandidate, raw_query: "raw" };
    const decorated = [baseCandidate];
    Object.defineProperty(decorated, "4294967295", { enumerable: true, value: "raw" });
    const sparse = new Array(2);
    sparse[0] = baseCandidate;
    const alias = [baseCandidate, baseCandidate];
    const proxy = new Proxy(baseCandidate, {
      ownKeys: (target) => Reflect.ownKeys(target),
      getOwnPropertyDescriptor: (target, key) => Reflect.getOwnPropertyDescriptor(target, key),
    });
    const attacks: unknown[] = [
      getterCandidate,
      new CandidateClass(baseCandidate),
      symbolCandidate,
      hiddenCandidate,
      extraCandidate,
      proxy,
    ];
    for (const attack of attacks) {
      const fixture = harness({ loads: [loadConfig({
        coverage: baseConfig.coverage,
        overlay: () => [attack],
      })] });
      await expect(readApplicationSynthesizedPage(firstPage, fixture.ports)).rejects.toThrow(TypeError);
    }
    for (const arrayAttack of [decorated, sparse, alias]) {
      const fixture = harness({ loads: [loadConfig({
        coverage: baseConfig.coverage,
        overlay: () => arrayAttack,
      })] });
      await expect(readApplicationSynthesizedPage(firstPage, fixture.ports)).rejects.toThrow(TypeError);
    }
    expect(getterCalls).toBe(0);

    let requestGetterCalls = 0;
    const hostileRequest = { cursor: null } as Record<string, unknown>;
    Object.defineProperty(hostileRequest, "limit", {
      enumerable: true,
      get: () => { requestGetterCalls++; return 1; },
    });
    const requestFixture = harness();
    await expect(readApplicationSynthesizedPage(hostileRequest as never, requestFixture.ports)).rejects.toThrow(TypeError);
    expect(requestGetterCalls).toBe(0);
    expect(requestFixture.counters.resolve).toBe(0);

    const mutable = candidate(baseConfig.projected, baseConfig.generations, "stm", "detached");
    const fixture = harness({ loads: [loadConfig({
      coverage: baseConfig.coverage,
      overlay: () => [mutable],
    })] });
    const promise = readApplicationSynthesizedPage(firstPage, fixture.ports);
    (mutable as { synthesized_text: string }).synthesized_text = "mutated after load";
    const result = await promise;
    expect(result).toContain("Synthesized detached");
    expect(result).not.toContain("mutated after load");
  });

  test("rejects hostile ports, attempt descriptors, and coherent loaders without invoking accessors", async () => {
    const portsFixture = harness();
    let portGetterCalls = 0;
    const getterPorts = { ...portsFixture.ports } as Record<string, unknown>;
    Object.defineProperty(getterPorts, "issueCursor", {
      enumerable: true,
      get: () => { portGetterCalls++; return portsFixture.ports.issueCursor; },
    });
    await expect(readApplicationSynthesizedPage(firstPage, getterPorts as unknown as ApplicationReadPorts)).rejects.toThrow(TypeError);
    await expect(readApplicationSynthesizedPage(
      firstPage,
      new Proxy({ ...portsFixture.ports }, {}) as ApplicationReadPorts,
    )).rejects.toThrow(TypeError);
    expect(portGetterCalls).toBe(0);
    expect(portsFixture.counters.resolve).toBe(0);

    let attemptGetterCalls = 0;
    const attemptFixture = harness();
    const attemptPorts: ApplicationReadPorts = {
      ...attemptFixture.ports,
      resolveAttempt: () => {
        const value = { authorization_request: authorization() } as Record<string, unknown>;
        Object.defineProperty(value, "load_coherent", {
          enumerable: true,
          get: () => { attemptGetterCalls++; return () => ({}); },
        });
        return value as never;
      },
    };
    await expect(readApplicationSynthesizedPage(firstPage, attemptPorts)).rejects.toThrow(TypeError);
    expect(attemptGetterCalls).toBe(0);
    expect(attemptFixture.counters.coherent).toBe(0);
    expect(attemptFixture.counters.durable).toBe(0);

    let coherentGetterCalls = 0;
    const coherentFixture = harness();
    const coherentPorts: ApplicationReadPorts = {
      ...coherentFixture.ports,
      resolveAttempt: () => ({
        authorization_request: authorization(),
        load_coherent: () => {
          const value = {
            projection_load: {}, coverage: {}, generations: {}, read_coordinates: {},
          } as Record<string, unknown>;
          Object.defineProperty(value, "overlay", {
            enumerable: true,
            get: () => { coherentGetterCalls++; return {}; },
          });
          return value as never;
        },
      }),
    };
    await expect(readApplicationSynthesizedPage(firstPage, coherentPorts)).rejects.toThrow(TypeError);
    expect(coherentGetterCalls).toBe(0);
    expect(coherentFixture.counters.durable).toBe(0);

    const proxyCoherentFixture = harness();
    const proxyCoherentPorts: ApplicationReadPorts = {
      ...proxyCoherentFixture.ports,
      resolveAttempt: () => ({
        authorization_request: authorization(),
        load_coherent: () => new Proxy({}, {}) as never,
      }),
    };
    await expect(readApplicationSynthesizedPage(firstPage, proxyCoherentPorts)).rejects.toThrow(TypeError);
    expect(proxyCoherentFixture.counters.durable).toBe(0);
  });

  test("rejects bounded overlay over-return and invalid synthesis digests", async () => {
    const overItems = harness({ loads: [loadConfig({
      maxItems: 1,
      overlay: (input, generation) => [
        candidate(input, generation, "stm", "one"),
        candidate(input, generation, "stm", "two"),
      ],
    })] });
    await expect(readApplicationSynthesizedPage(firstPage, overItems.ports)).rejects.toThrow("overlay bound");

    const badDigest = harness({ durableSpecs: [{ origin: "durable", ref: "bad-digest", overrides: {
      synthesis_provenance: {
        synthesis_version: "v1",
        input_digest: "A".repeat(64),
        output_digest: digest("output"),
      },
    } }] });
    await expect(readApplicationSynthesizedPage(firstPage, badDigest.ports)).rejects.toThrow("provenance");
  });
});
