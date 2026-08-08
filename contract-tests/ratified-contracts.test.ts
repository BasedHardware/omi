import { describe, expect, test } from "bun:test";

import { parseKeysetCursor } from "@omi-core/ratified-contracts/pagination/cursor";
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMCORE-006)
import {
  MAX_SYNTHESIZED_PAGE_JSON_CODE_UNITS,
  isTrustedPageWindowHonest,
  isTrustedRecallCompletenessHonest,
  isTrustedSynthesizedPageData,
  parseCitationRef,
  parseRecallFrontier,
  parseSha256Digest,
  parseSynthesizedPageJson,
  parseSynthesizedItemId,
  parseSynthesizedText,
} from "@omi-core/ratified-contracts/projections/synthesized";
import {
  MAX_RECALL_TRACE_JSON_CODE_UNITS,
  isTrustedRecallTraceData,
  parseRecallTraceJson,
  parseRecallTraceRef,
} from "@omi-core/ratified-contracts/recall/trace";
import {
  WRITABLE_DOMAINS,
  WRITE_ERRORS,
  WRITE_ID_ENTROPY_BYTES,
  WRITE_ID_PATTERN,
  WRITE_REFUSALS,
  isTrustedWriteAccepted,
  isWritableDomain,
  mintWriteId,
  parseWriteId,
  parseWriteOpEnvelopeJson,
  readWriteRefusalOutcome,
  writeOpsPath,
} from "@omi-core/ratified-contracts/write/ops";

const installedRoot = new URL("../node_modules/@omi-core/ratified-contracts/", import.meta.url);

async function fixture<T>(name: string): Promise<T> {
  return await Bun.file(new URL(`fixtures/${name}`, installedRoot)).json() as T;
}

describe("ratified package runtime boundary", () => {
  test("runtime imports expose the reviewed parsers", () => {
    expect(parseKeysetCursor("v1.signature.payload")).not.toBeNull();
    expect(parseSynthesizedItemId("retrieval-node-v1:fixture")).not.toBeNull();
    expect(parseSynthesizedText("Synthesized result")).not.toBeNull();
    expect(parseCitationRef("citation-v1:fixture")).not.toBeNull();
    expect(parseRecallFrontier("frontier-v1:fixture")).not.toBeNull();
    expect(parseSha256Digest("a".repeat(64))).not.toBeNull();
    expect(parseRecallTraceRef("trace-v1:fixture")).not.toBeNull();
    expect(parseKeysetCursor("")).toBeNull();
    expect(parseSynthesizedText("  ")).toBeNull();
    expect(parseSha256Digest("A".repeat(64))).toBeNull();
  });

  test("packed page-window fixtures retain their verdicts", async () => {
    const rows = await fixture<Array<{ window: Parameters<typeof isTrustedPageWindowHonest>[0]; honest: boolean }>>("read-page-windows.json");
    for (const row of rows) expect(isTrustedPageWindowHonest(row.window)).toBe(row.honest);
  });

  test("packed recall-completeness fixtures retain their verdicts", async () => {
    const rows = await fixture<Array<{ page: Parameters<typeof isTrustedRecallCompletenessHonest>[0]; honest: boolean }>>("recall-completeness.json");
    for (const row of rows) expect(isTrustedRecallCompletenessHonest(row.page)).toBe(row.honest);
  });

  test("packed 0.1.1 mixed precedence conformance retains every verdict", async () => {
    const rows = await fixture<Array<{
      name: string;
      page: Parameters<typeof isTrustedRecallCompletenessHonest>[0];
      honest: boolean;
    }>>("recall-completeness.json");
    const expected = new Map<string, boolean>([
      ["degraded outranks incomplete while preserving both reasons", true],
      ["incomplete cannot understate degraded plus incomplete reasons", false],
      ["degraded outranks partial while preserving both reasons", true],
      ["partial cannot understate degraded plus partial reasons", false],
      ["incomplete outranks partial while preserving both reasons", true],
      ["partial cannot understate incomplete plus partial reasons", false],
      ["degraded outranks all lower families while preserving every reason", true],
      ["incomplete cannot understate all three reason families", false],
      ["missing frontier limitation must remain in mixed reason set", false],
    ]);

    for (const [name, honest] of expected) {
      const row = rows.find((candidate) => candidate.name === name);
      expect(row).toBeDefined();
      if (!row) throw new Error(`missing 0.1.1 mixed-precedence fixture: ${name}`);
      expect(isTrustedRecallCompletenessHonest(row.page)).toBe(honest);
    }
  });

  test("packed strict-page fixtures retain their verdicts", async () => {
    const rows = await fixture<Array<{ page: unknown; safe: boolean }>>("page-conformance.json");
    for (const row of rows) {
      expect(isTrustedSynthesizedPageData(row.page)).toBe(row.safe);
      expect(parseSynthesizedPageJson(JSON.stringify(row.page)) !== null).toBe(row.safe);
    }
  });

  test("packed recall-trace fixtures retain their verdicts", async () => {
    const rows = await fixture<Array<{ trace: unknown; safe: boolean }>>("recall-trace.json");
    for (const row of rows) {
      expect(isTrustedRecallTraceData(row.trace)).toBe(row.safe);
      expect(parseRecallTraceJson(JSON.stringify(row.trace)) !== null).toBe(row.safe);
    }
  });

  test("duplicate projection identities and reasons fail closed", async () => {
    const pageRows = await fixture<Array<{ page: Record<string, unknown>; safe: boolean }>>("page-conformance.json");
    const valid = structuredClone(pageRows.find((row) => row.safe)?.page);
    if (!valid) throw new Error("safe page fixture is required");
    const item = (valid["items"] as Array<Record<string, unknown>>)[0];
    if (!item) throw new Error("safe page fixture must contain an item");

    const duplicateItems = structuredClone(valid);
    duplicateItems["items"] = [structuredClone(item), structuredClone(item)];
    expect(isTrustedSynthesizedPageData(duplicateItems)).toBe(false);

    const duplicateCitations = structuredClone(valid);
    (duplicateCitations["items"] as Array<Record<string, unknown>>)[0]!["citations"] = ["citation-v1:fixture", "citation-v1:fixture"];
    expect(isTrustedSynthesizedPageData(duplicateCitations)).toBe(false);

    const duplicateReasons = structuredClone(valid);
    duplicateReasons["items"] = [];
    duplicateReasons["window"] = { status: "incomplete", complete: false, hasMore: false, nextCursor: null };
    duplicateReasons["completeness"] = {
      version: "recall-completeness-v1",
      status: "incomplete",
      reasons: ["accepted_work_pending", "accepted_work_pending"],
      frontiers: {
        declaredFrontier: "frontier-v1:declared",
        newestSearchedAcceptedFrontier: "frontier-v1:behind",
        missingAcceptedFrontierReason: null,
        newestSearchedStmFrontier: null,
        missingStmFrontierReason: "accepted_work_pending",
      },
    };
    duplicateReasons["absence"] = { kind: "query_gap" };
    expect(isTrustedSynthesizedPageData(duplicateReasons)).toBe(false);
  });

  test("projection provenance requires real lowercase SHA-256 digests", async () => {
    const pageRows = await fixture<Array<{ page: Record<string, unknown>; safe: boolean }>>("page-conformance.json");
    const valid = structuredClone(pageRows.find((row) => row.safe)?.page);
    if (!valid) throw new Error("safe page fixture is required");
    const item = (valid["items"] as Array<Record<string, unknown>>)[0];
    const provenance = item?.["provenance"] as Record<string, unknown> | undefined;
    if (!provenance) throw new Error("safe page fixture must contain provenance");
    provenance["inputDigest"] = "raw input text";
    provenance["outputDigest"] = "sha256:ABCDEF";
    expect(isTrustedSynthesizedPageData(valid)).toBe(false);
    expect(parseSynthesizedPageJson(JSON.stringify(valid))).toBeNull();
  });

  test("object validators reject classes, accessors, and proxies", async () => {
    const pageRows = await fixture<Array<{ page: Record<string, unknown>; safe: boolean }>>("page-conformance.json");
    const traceRows = await fixture<Array<{ trace: Record<string, unknown>; safe: boolean }>>("recall-trace.json");
    const page = structuredClone(pageRows.find((row) => row.safe)?.page);
    const trace = structuredClone(traceRows.find((row) => row.safe)?.trace);
    if (!page || !trace) throw new Error("safe page and trace fixtures are required");

    class JsonImpostor {
      constructor(value: Record<string, unknown>) {
        Object.assign(this, value);
      }
    }
    expect(isTrustedSynthesizedPageData(new JsonImpostor(page))).toBe(false);
    expect(isTrustedRecallTraceData(new JsonImpostor(trace))).toBe(false);

    const pageWithAccessor = structuredClone(page);
    const pageItems = pageWithAccessor["items"];
    Object.defineProperty(pageWithAccessor, "items", { enumerable: true, get: () => pageItems });
    const traceWithAccessor = structuredClone(trace);
    const traceStages = traceWithAccessor["stages"];
    Object.defineProperty(traceWithAccessor, "stages", { enumerable: true, get: () => traceStages });
    expect(isTrustedSynthesizedPageData(pageWithAccessor)).toBe(false);
    expect(isTrustedRecallTraceData(traceWithAccessor)).toBe(false);

    expect(isTrustedSynthesizedPageData(new Proxy(page, {}))).toBe(false);
    expect(isTrustedRecallTraceData(new Proxy(trace, {}))).toBe(false);
  });

  test("authoritative raw parsers are canonical, bounded, and do not execute objects", async () => {
    const pageRows = await fixture<Array<{ page: Record<string, unknown>; safe: boolean }>>("page-conformance.json");
    const traceRows = await fixture<Array<{ trace: Record<string, unknown>; safe: boolean }>>("recall-trace.json");
    const page = structuredClone(pageRows.find((row) => row.safe)?.page);
    const trace = structuredClone(traceRows.find((row) => row.safe)?.trace);
    if (!page || !trace) throw new Error("safe page and trace fixtures are required");

    const pageJson = JSON.stringify(page);
    const traceJson = JSON.stringify(trace);
    expect(parseSynthesizedPageJson(pageJson)).not.toBeNull();
    expect(parseRecallTraceJson(traceJson)).not.toBeNull();
    expect(parseSynthesizedPageJson(JSON.stringify(page, null, 2))).toBeNull();
    expect(parseRecallTraceJson(` ${traceJson}`)).toBeNull();
    expect(parseSynthesizedPageJson(pageJson.replace(
      "{\"contractVersion\":",
      "{\"contractVersion\":\"duplicate\",\"contractVersion\":",
    ))).toBeNull();
    expect(parseRecallTraceJson(traceJson.replace(
      "{\"version\":",
      "{\"version\":\"duplicate\",\"version\":",
    ))).toBeNull();
    expect(parseSynthesizedPageJson(`\"${"x".repeat(MAX_SYNTHESIZED_PAGE_JSON_CODE_UNITS)}\"`)).toBeNull();
    expect(parseRecallTraceJson(`\"${"x".repeat(MAX_RECALL_TRACE_JSON_CODE_UNITS)}\"`)).toBeNull();

    let objectTrapRead = false;
    const hostileObject = new Proxy({}, {
      get: () => {
        objectTrapRead = true;
        throw new Error("must not execute");
      },
    });
    expect(parseSynthesizedPageJson(hostileObject as unknown as string)).toBeNull();
    expect(parseRecallTraceJson(hostileObject as unknown as string)).toBeNull();
    expect(objectTrapRead).toBe(false);
  });

  test("authoritative raw parsers ignore inherited serialization hooks", async () => {
    const pageRows = await fixture<Array<{ page: Record<string, unknown>; safe: boolean }>>("page-conformance.json");
    const traceRows = await fixture<Array<{ trace: Record<string, unknown>; safe: boolean }>>("recall-trace.json");
    const page = structuredClone(pageRows.find((row) => row.safe)?.page);
    const trace = structuredClone(traceRows.find((row) => row.safe)?.trace);
    if (!page || !trace) throw new Error("safe page and trace fixtures are required");

    const pageJson = JSON.stringify(page);
    const traceJson = JSON.stringify(trace);
    const inheritedToJson = Object.getOwnPropertyDescriptor(Object.prototype, "toJSON");
    let inheritedToJsonCalls = 0;
    Object.defineProperty(Object.prototype, "toJSON", {
      configurable: true,
      value(this: unknown) {
        inheritedToJsonCalls += 1;
        return this;
      },
    });
    try {
      expect(parseSynthesizedPageJson(pageJson)).not.toBeNull();
      expect(parseRecallTraceJson(traceJson)).not.toBeNull();
      expect(inheritedToJsonCalls).toBe(0);
    } finally {
      if (inheritedToJson) Object.defineProperty(Object.prototype, "toJSON", inheritedToJson);
      else delete (Object.prototype as { toJSON?: unknown }).toJSON;
    }

  });

  test("authoritative page parsing ignores inherited optional-field accessors", async () => {
    const pageRows = await fixture<Array<{ page: Record<string, unknown>; safe: boolean }>>("page-conformance.json");
    const pageWithoutCitations = structuredClone(pageRows.find((row) => row.safe)?.page);
    if (!pageWithoutCitations) throw new Error("safe page fixture is required");
    const firstItem = (pageWithoutCitations["items"] as Array<Record<string, unknown>>)[0];
    if (!firstItem) throw new Error("safe page fixture must contain an item");
    delete firstItem["citations"];
    const pageWithoutCitationsJson = JSON.stringify(pageWithoutCitations);
    const inheritedCitations = Object.getOwnPropertyDescriptor(Object.prototype, "citations");
    let inheritedCitationReads = 0;
    Object.defineProperty(Object.prototype, "citations", {
      configurable: true,
      get() {
        inheritedCitationReads += 1;
        return undefined;
      },
    });
    try {
      expect(parseSynthesizedPageJson(pageWithoutCitationsJson)).not.toBeNull();
      expect(inheritedCitationReads).toBe(0);
    } finally {
      if (inheritedCitations) Object.defineProperty(Object.prototype, "citations", inheritedCitations);
      else delete (Object.prototype as { citations?: unknown }).citations;
    }
  });

  test("authoritative raw parsers ignore inherited descriptor get accessors", async () => {
    const pageRows = await fixture<Array<{ page: Record<string, unknown>; safe: boolean }>>("page-conformance.json");
    const traceRows = await fixture<Array<{ trace: Record<string, unknown>; safe: boolean }>>("recall-trace.json");
    const page = structuredClone(pageRows.find((row) => row.safe)?.page);
    const trace = structuredClone(traceRows.find((row) => row.safe)?.trace);
    if (!page || !trace) throw new Error("safe page and trace fixtures are required");

    const pageJson = JSON.stringify(page);
    const traceJson = JSON.stringify(trace);
    const inheritedGet = Object.getOwnPropertyDescriptor(Object.prototype, "get");
    let inheritedGetReads = 0;
    let pageResult: ReturnType<typeof parseSynthesizedPageJson> = null;
    let traceResult: ReturnType<typeof parseRecallTraceJson> = null;
    Object.defineProperty(Object.prototype, "get", {
      configurable: true,
      get() {
        inheritedGetReads += 1;
        return undefined;
      },
    });
    try {
      pageResult = parseSynthesizedPageJson(pageJson);
      traceResult = parseRecallTraceJson(traceJson);
    } finally {
      if (inheritedGet) Object.defineProperty(Object.prototype, "get", inheritedGet);
      else delete (Object.prototype as { get?: unknown }).get;
    }
    expect(inheritedGetReads).toBe(0);
    expect(pageResult).not.toBeNull();
    expect(traceResult).not.toBeNull();
  });

  test("authoritative raw parsers ignore inherited descriptor set accessors", async () => {
    const pageRows = await fixture<Array<{ page: Record<string, unknown>; safe: boolean }>>("page-conformance.json");
    const traceRows = await fixture<Array<{ trace: Record<string, unknown>; safe: boolean }>>("recall-trace.json");
    const page = structuredClone(pageRows.find((row) => row.safe)?.page);
    const trace = structuredClone(traceRows.find((row) => row.safe)?.trace);
    if (!page || !trace) throw new Error("safe page and trace fixtures are required");

    const pageJson = JSON.stringify(page);
    const traceJson = JSON.stringify(trace);
    const inheritedSet = Object.getOwnPropertyDescriptor(Object.prototype, "set");
    let inheritedSetReads = 0;
    let pageResult: ReturnType<typeof parseSynthesizedPageJson> = null;
    let traceResult: ReturnType<typeof parseRecallTraceJson> = null;
    Object.defineProperty(Object.prototype, "set", {
      configurable: true,
      get() {
        inheritedSetReads += 1;
        return undefined;
      },
    });
    try {
      pageResult = parseSynthesizedPageJson(pageJson);
      traceResult = parseRecallTraceJson(traceJson);
    } finally {
      if (inheritedSet) Object.defineProperty(Object.prototype, "set", inheritedSet);
      else delete (Object.prototype as { set?: unknown }).set;
    }
    expect(inheritedSetReads).toBe(0);
    expect(pageResult).not.toBeNull();
    expect(traceResult).not.toBeNull();
  });

  test("accepted and STM searched frontiers are distinct mandatory coordinates", async () => {
    const pageRows = await fixture<Array<{ page: Record<string, unknown>; safe: boolean }>>("page-conformance.json");
    const valid = structuredClone(pageRows.find((row) => row.safe)?.page);
    if (!valid) throw new Error("safe page fixture is required");
    const frontiers = (valid["completeness"] as Record<string, unknown>)["frontiers"] as Record<string, unknown>;
    expect("newestSearchedAcceptedFrontier" in frontiers).toBe(true);
    expect("newestSearchedStmFrontier" in frontiers).toBe(true);

    const missingAcceptedCoordinate = structuredClone(valid);
    const missingAcceptedFrontiers = (
      (missingAcceptedCoordinate["completeness"] as Record<string, unknown>)["frontiers"] as Record<string, unknown>
    );
    delete missingAcceptedFrontiers["newestSearchedAcceptedFrontier"];
    delete missingAcceptedFrontiers["missingAcceptedFrontierReason"];
    expect(isTrustedSynthesizedPageData(missingAcceptedCoordinate)).toBe(false);

    const missingStmCoordinate = structuredClone(valid);
    const missingStmFrontiers = (
      (missingStmCoordinate["completeness"] as Record<string, unknown>)["frontiers"] as Record<string, unknown>
    );
    delete missingStmFrontiers["newestSearchedStmFrontier"];
    delete missingStmFrontiers["missingStmFrontierReason"];
    expect(isTrustedSynthesizedPageData(missingStmCoordinate)).toBe(false);
  });

  test("an empty continuing page cannot claim a query gap", async () => {
    const pageRows = await fixture<Array<{ page: Record<string, unknown>; safe: boolean }>>("page-conformance.json");
    const valid = structuredClone(pageRows.find((row) => row.safe)?.page);
    if (!valid) throw new Error("safe page fixture is required");
    valid["items"] = [];
    valid["window"] = {
      status: "more",
      complete: false,
      hasMore: true,
      nextCursor: "v1.signature.payload",
    };
    valid["completeness"] = {
      version: "recall-completeness-v1",
      status: "complete",
      reasons: [],
      frontiers: {
        declaredFrontier: "frontier-v1:declared",
        newestSearchedAcceptedFrontier: null,
        missingAcceptedFrontierReason: "no_accepted_work",
        newestSearchedStmFrontier: null,
        missingStmFrontierReason: "no_eligible_stm",
      },
    };
    valid["absence"] = { kind: "query_gap" };
    expect(isTrustedSynthesizedPageData(valid)).toBe(false);
  });

  test("an incomplete service window cannot claim complete recall", async () => {
    const pageRows = await fixture<Array<{ page: Record<string, unknown>; safe: boolean }>>("page-conformance.json");
    const valid = structuredClone(pageRows.find((row) => row.safe)?.page);
    if (!valid) throw new Error("safe page fixture is required");
    valid["window"] = {
      status: "incomplete",
      complete: false,
      hasMore: false,
      nextCursor: null,
    };
    expect(isTrustedSynthesizedPageData(valid)).toBe(false);
  });

  test("trace outcome must agree with the furthest populated stage", async () => {
    const rows = await fixture<Array<{ trace: Record<string, unknown>; safe: boolean }>>("recall-trace.json");
    const valid = structuredClone(rows.find((row) => row.safe)?.trace);
    if (!valid) throw new Error("safe trace fixture is required");
    const cases = [
      { outcome: "no_selection", stage: "selected" },
      { outcome: "hydration_unavailable", stage: "hydrated" },
      { outcome: "policy_filtered", stage: "policyEligible" },
      { outcome: "ungrounded", stage: "grounded" },
    ] as const;
    for (const row of cases) {
      const trace = structuredClone(valid);
      trace["outcome"] = row.outcome;
      (trace["stages"] as Record<string, string[]>)[row.stage] = ["node-v1:a"];
      expect(isTrustedRecallTraceData(trace)).toBe(false);
    }
  });

  test("packed status matrix enforces all 22 window/completeness combinations", async () => {
    type StatusRow = {
      window: "complete_terminal" | "more_continuation" | "incomplete_terminal" | "incomplete_continuation";
      completeness: "complete" | "incomplete" | "degraded" | "partial";
      empty?: boolean;
      queryGap?: boolean;
      safe: boolean;
    };
    const rows = await fixture<StatusRow[]>("status-matrix.json");
    expect(rows).toHaveLength(22);
    for (const row of rows) {
      const windows = {
        complete_terminal: { status: "complete", complete: true, hasMore: false, nextCursor: null },
        more_continuation: { status: "more", complete: false, hasMore: true, nextCursor: "v1.signature.payload" },
        incomplete_terminal: { status: "incomplete", complete: false, hasMore: false, nextCursor: null },
        incomplete_continuation: { status: "incomplete", complete: false, hasMore: true, nextCursor: "v1.signature.payload" },
      } as const;
      const complete = {
        version: "recall-completeness-v1",
        status: "complete",
        reasons: [],
        frontiers: {
          declaredFrontier: "frontier-v1:declared",
          newestSearchedAcceptedFrontier: row.empty ? null : "frontier-v1:declared",
          missingAcceptedFrontierReason: row.empty ? "no_accepted_work" : null,
          newestSearchedStmFrontier: row.empty ? null : "frontier-v1:included",
          missingStmFrontierReason: row.empty ? "no_eligible_stm" : null,
        },
      } as const;
      const limitations = {
        incomplete: ["accepted_work_pending", "accepted_work_pending"],
        degraded: ["projection_unavailable", "projection_unavailable"],
        partial: ["source_bound", "source_bound"],
      } as const;
      const completeness = row.completeness === "complete" ? complete : {
        version: "recall-completeness-v1",
        status: row.completeness,
        reasons: [limitations[row.completeness][0]],
        frontiers: {
          declaredFrontier: "frontier-v1:declared",
          newestSearchedAcceptedFrontier: row.completeness === "incomplete" ? "frontier-v1:behind" : "frontier-v1:declared",
          missingAcceptedFrontierReason: null,
          newestSearchedStmFrontier: null,
          missingStmFrontierReason: limitations[row.completeness][1],
        },
      };
      const page = {
        contractVersion: "1.0.0",
        items: row.empty ? [] : [{ id: "retrieval-node-v1:fixture", text: "Synthesized result" }],
        window: windows[row.window],
        completeness,
        absence: row.queryGap ? { kind: "query_gap" } : null,
      };
      const actual = isTrustedSynthesizedPageData(page);
      if (actual !== row.safe) {
        throw new Error(`status matrix mismatch for ${row.window}/${row.completeness}: expected ${row.safe}, received ${actual}`);
      }
    }
  });

  test("packed fixture manifest names only installed JSON evidence", async () => {
    const manifest = await fixture<{ schemaVersion: number; files: string[] }>("manifest.json");
    expect(manifest).toEqual({
      schemaVersion: 1,
      files: [
        "read-page-windows.json",
        "recall-completeness.json",
        "recall-trace.json",
        "page-conformance.json",
        "status-matrix.json",
        "write-ops-outcomes.json",
        "write-ops-conformance.json",
      ],
    });
    for (const name of manifest.files) expect(await Bun.file(new URL(`fixtures/${name}`, installedRoot)).exists()).toBe(true);
  });

  test("package root and non-exported internals stay unreachable", async () => {
    const packageRoot = "@omi-core/ratified-contracts";
    const hiddenFixture = "@omi-core/ratified-contracts/fixtures/manifest.json";
    const hiddenWireParser = "@omi-core/ratified-contracts/wire/json";
    await expect(import(packageRoot)).rejects.toThrow();
    await expect(import(hiddenFixture)).rejects.toThrow();
    await expect(import(hiddenWireParser)).rejects.toThrow();
  });
});

// ── SERVER-side consumer of the write-ops corpus of record (rule 15) ────────
//
// The client-side consumer is
// core-foundation/core/packages/testkit/src/test/write-ops-conformance.test.ts.
// This is the other end. Both read the SAME file; this one reads it out of the
// INSTALLED tarball, which is the strongest form available — the bytes here are
// the bytes a deployed backend would have, not the bytes in somebody's source
// tree.
//
// WHY THIS EXISTS RATHER THAN A HAND-WRITTEN SUITE. The two write-path spikes
// each hand-authored their counterpart's payloads, and their own memo says so:
// "the spikes themselves would not satisfy rule 15 ... the first real landing
// must add the wire-seam registry row and corpus". This is that landing.
//
// WHAT IT DOES NOT COVER. There is no write ROUTE yet: the account epoch fence
// (backend:ADR-010) is a separate landing and nothing here invents a second
// one. So these tests bind the vendored contract's tables and validators, which
// is what a route will be built out of. When the fence lands, its handler
// returns WRITE_REFUSALS[...] rather than a literal, and these rows become
// live-response assertions without the corpus changing.
describe("write-ops wire seam (COORD-write-path-rulings)", () => {
  interface WriteOpsCase {
    name: string;
    wireOutcome: string;
    path: string;
    requestBody: string;
    envelopeAccepted: boolean;
    response: { status: number; body: string };
  }
  interface WriteOpsSchema {
    route: string;
    writableDomains: string[];
    writeIdPattern: string;
    writeIdEntropyBytes: number;
    outcomes: {
      outcome: string;
      kind: string;
      status: number;
      body?: string | null;
      bodyRatified?: boolean;
      servingSideBody?: string;
    }[];
  }

  test("the installed schema of record matches the installed module's tables", async () => {
    // red-proof: change any status in the shipped write-ops-outcomes.json and
    // this goes red. APPLIED AND OBSERVED RED.
    const schema = await fixture<WriteOpsSchema>("write-ops-outcomes.json");
    expect(schema.route).toBe("/v1/{domain}/ops");
    expect(schema.writableDomains).toEqual([...WRITABLE_DOMAINS]);
    expect(schema.writeIdPattern).toBe(WRITE_ID_PATTERN.source);
    expect(schema.writeIdEntropyBytes).toBe(WRITE_ID_ENTROPY_BYTES);
    for (const row of schema.outcomes) {
      if (row.kind === "refusal") {
        const refusal = WRITE_REFUSALS[row.outcome as keyof typeof WRITE_REFUSALS];
        expect<number>(refusal.status).toBe(row.status);
        expect<string>(refusal.body).toBe(row.body as string);
      } else if (row.kind === "error") {
        const error = WRITE_ERRORS[row.outcome as keyof typeof WRITE_ERRORS];
        expect<number>(error.status).toBe(row.status);
        expect<string | null>(error.body).toBe((row.body ?? null) as string | null);
      }
    }
  });

  test("every corpus request is accepted or refused exactly as the corpus declares", async () => {
    // red-proof: flip `envelopeAccepted` on the unknown-field row and this goes
    // red. APPLIED AND OBSERVED RED.
    const corpus = await fixture<WriteOpsCase[]>("write-ops-conformance.json");
    expect(corpus.length).toBeGreaterThanOrEqual(16);
    let checked = 0;
    for (const row of corpus) {
      expect([parseWriteOpEnvelopeJson(row.requestBody) !== null, row.name])
        .toEqual([row.envelopeAccepted, row.name]);
      if (row.envelopeAccepted) expect(row.path).toMatch(/^\/v1\/[a-z]+\/ops$/);
      if (row.response.status === 200) {
        expect(isTrustedWriteAccepted(JSON.parse(row.response.body))).toBe(true);
      }
      checked += 1;
    }
    // Producer-side count (rows declared) against consumer-side count (rows
    // actually asserted). A loop that silently skipped a class would otherwise
    // be a green result about nothing.
    expect(checked).toBe(corpus.length);
  });

  test("stale_epoch is a distinct 409 and can never be read as conflict", async () => {
    // red-proof: give WRITE_REFUSALS.stale_epoch the conflict body in the
    // source package and this goes red. APPLIED AND OBSERVED RED.
    //
    // The server side of B2. A backend that answered a straggler with the
    // conflict body would be telling the client to tell the user their edit
    // lost a race that never happened.
    expect(WRITE_REFUSALS.stale_epoch.status).toBe(409);
    expect(WRITE_ERRORS.conflict.status).toBe(409);
    expect(WRITE_REFUSALS.stale_epoch.body).not.toBe(WRITE_ERRORS.conflict.body);
    expect(readWriteRefusalOutcome(409, WRITE_REFUSALS.stale_epoch.body)).toBe("stale_epoch");
    expect(readWriteRefusalOutcome(409, WRITE_ERRORS.conflict.body)).toBeNull();

    const corpus = await fixture<WriteOpsCase[]>("write-ops-conformance.json");
    const stale = corpus.filter((row) => row.wireOutcome === "stale_epoch");
    expect(stale.length).toBeGreaterThanOrEqual(1);
    for (const row of stale) {
      expect(row.response.status).toBe(WRITE_REFUSALS.stale_epoch.status);
      expect(row.response.body).toBe(WRITE_REFUSALS.stale_epoch.body);
    }
  });

  test("the wire carries no word slug and no client opId", async () => {
    // backend:RISK-015, asserted over the serialized bytes of every accepted
    // envelope in the corpus rather than over a type.
    const corpus = await fixture<WriteOpsCase[]>("write-ops-conformance.json");
    for (const row of corpus.filter((entry) => entry.envelopeAccepted)) {
      const envelope = parseWriteOpEnvelopeJson(row.requestBody);
      expect(envelope).not.toBeNull();
      expect(parseWriteId(envelope!.write_id)).not.toBeNull();
      expect(row.requestBody).not.toContain("opId");
      expect(row.requestBody).not.toContain("op_id");
    }
    expect(parseWriteId("edit-task-9f21-set-done")).toBeNull();
    expect<string | null>(mintWriteId(new Uint8Array(WRITE_ID_ENTROPY_BYTES))).toBe("00".repeat(32));
    expect(mintWriteId(new Uint8Array(16))).toBeNull();
  });

  test("memories is not writable and its route is not constructible", () => {
    // B6. Memories is read-only by ratified design; the type system refuses to
    // build the path, and the runtime predicate refuses the domain.
    expect(isWritableDomain("memories")).toBe(false);
    expect(writeOpsPath("tasks")).toBe("/v1/tasks/ops");
  });
});

