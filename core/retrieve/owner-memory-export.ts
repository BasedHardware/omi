import { isProxy } from "node:util/types";

import type { ApplicationGrantProjectedTreeInputSnapshot } from "./authorization-boundary";
import { isApplicationGrantProjectedTreeInput } from "./authorization-boundary";
import { sha256CanonicalContent } from "./content-digest";
import { selectNodesForGranularity } from "./granularity";
import { buildOwnerBoundSynthesizedProjection } from "./projection-boundary";
import { isProducedRenderNode, type RenderNode } from "./render";
import { buildDeterministicAnchors } from "./tree";

export const OWNER_MEMORY_EXPORT_VERSION = "owner-memory-export-v1" as const;
export const OWNER_MEMORY_EXPORT_CHUNK_VERSION = "owner-memory-export-chunk-v1" as const;

export type OwnerMemoryExportRefKind =
  | "memory"
  | "lineage"
  | "revision"
  | "evidence"
  | "event"
  | "capture";

export interface OwnerMemoryExportSource {
  readonly evidenceRef: string;
  readonly eventRef: string;
  readonly captureRef: string;
  readonly excerpt: string | null;
  readonly range: Readonly<{ start: number; end: number }>;
}

export interface OwnerMemoryExportLineage {
  readonly lineageRef: string;
  readonly revisionRef: string;
  readonly observedAt: string;
  readonly temporalPrecision: string;
  readonly sources: readonly OwnerMemoryExportSource[];
}

export interface OwnerMemoryExportItem {
  readonly id: string;
  readonly text: string;
  readonly sourceLanguage: string;
  readonly lineage: readonly OwnerMemoryExportLineage[];
}

export interface OwnerMemoryExportChunk {
  readonly contractVersion: typeof OWNER_MEMORY_EXPORT_CHUNK_VERSION;
  readonly snapshotDigest: string;
  readonly ordinal: number;
  readonly memories: readonly OwnerMemoryExportItem[];
  readonly chunkDigest: string;
}

export interface OwnerMemoryExportManifest {
  readonly contractVersion: typeof OWNER_MEMORY_EXPORT_VERSION;
  readonly exportedAtEpochSeconds: number;
  readonly snapshotDigest: string;
  readonly granularity: "temporal_leaf";
  readonly counts: Readonly<{
    memories: number;
    lineages: number;
    sources: number;
    chunks: number;
  }>;
  readonly chunks: readonly Readonly<{
    ordinal: number;
    chunkDigest: string;
    memoryCount: number;
    lineageCount: number;
    sourceCount: number;
  }>[];
  readonly exportDigest: string;
}

export interface OwnerMemoryExportBundle {
  readonly manifest: OwnerMemoryExportManifest;
  readonly chunks: readonly OwnerMemoryExportChunk[];
  readonly manifest_json: string;
  readonly chunk_json: readonly string[];
}

export interface OwnerMemoryExportInput {
  readonly projected: ApplicationGrantProjectedTreeInputSnapshot;
  readonly renders: readonly RenderNode[];
  readonly exported_at_epoch_seconds: number;
  readonly chunk_max_bytes: number;
  readonly encode_ref: (kind: OwnerMemoryExportRefKind, internalRef: string) => string;
}

const EXPORT_REF = /^mxr1_[a-f0-9]{64}$/;
export const OWNER_MEMORY_EXPORT_MIN_CHUNK_BYTES = 64 * 1024;
export const OWNER_MEMORY_EXPORT_MAX_CHUNK_BYTES = 16 * 1024 * 1024;
const MAX_MEMORIES = 100_000;
const MAX_LINEAGES = 1_000_000;
const MAX_SOURCES = 2_000_000;
const INPUT_KEYS = Object.freeze([
  "projected", "renders", "exported_at_epoch_seconds", "chunk_max_bytes", "encode_ref",
]);

export class OwnerMemoryExportError extends Error {
  constructor(readonly code:
    | "invalid_input"
    | "incomplete_render_set"
    | "invalid_render"
    | "duplicate_lineage"
    | "invalid_export_ref"
    | "export_too_large") {
    super(code);
    this.name = "OwnerMemoryExportError";
  }
}

const fail = (code: OwnerMemoryExportError["code"]): never => {
  throw new OwnerMemoryExportError(code);
};

const compareStrings = (left: string, right: string): number =>
  left < right ? -1 : left > right ? 1 : 0;

const snapshotInput = (value: unknown): OwnerMemoryExportInput => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) return fail("invalid_input");
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const keys = Reflect.ownKeys(descriptors);
  const expected = [...INPUT_KEYS].sort();
  if (keys.some((key) => typeof key !== "string") || keys.length !== expected.length
    || (keys as string[]).sort().some((key, index) => key !== expected[index])) {
    return fail("invalid_input");
  }
  const detached: Record<string, unknown> = {};
  for (const key of expected) {
    const descriptor = descriptors[key];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) {
      return fail("invalid_input");
    }
    detached[key] = descriptor.value;
  }
  return detached as unknown as OwnerMemoryExportInput;
};

const snapshotRenders = (value: unknown): readonly RenderNode[] => {
  if (!Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Array.prototype) return fail("invalid_input");
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const keys = Reflect.ownKeys(descriptors);
  if (keys.some((key) => typeof key !== "string") || keys.length !== value.length + 1) {
    return fail("invalid_input");
  }
  const renders: RenderNode[] = [];
  for (let index = 0; index < value.length; index += 1) {
    const descriptor = descriptors[String(index)];
    if (!descriptor || !descriptor.enumerable || !("value" in descriptor)) {
      return fail("invalid_input");
    }
    renders.push(descriptor.value as RenderNode);
  }
  return Object.freeze(renders);
};

const canonicalJson = (value: unknown): string => {
  if (value === null || typeof value === "string" || typeof value === "boolean") {
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return fail("invalid_input");
    return JSON.stringify(Object.is(value, -0) ? 0 : value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (typeof value !== "object" || isProxy(value)) return fail("invalid_input");
  return `{${Object.entries(value).sort(([left], [right]) => compareStrings(left, right))
    .map(([key, entry]) => `${JSON.stringify(key)}:${canonicalJson(entry)}`).join(",")}}`;
};

const freezeSource = (source: OwnerMemoryExportSource): OwnerMemoryExportSource =>
  Object.freeze({ ...source, range: Object.freeze({ ...source.range }) });

const freezeLineage = (lineage: OwnerMemoryExportLineage): OwnerMemoryExportLineage =>
  Object.freeze({ ...lineage, sources: Object.freeze(lineage.sources.map(freezeSource)) });

const freezeItem = (item: OwnerMemoryExportItem): OwnerMemoryExportItem =>
  Object.freeze({ ...item, lineage: Object.freeze(item.lineage.map(freezeLineage)) });

const encodedRef = (
  encode: OwnerMemoryExportInput["encode_ref"],
  kind: OwnerMemoryExportRefKind,
  internalRef: string,
): string => {
  const result = Reflect.apply(encode, undefined, [kind, internalRef]);
  if (typeof result !== "string" || !EXPORT_REF.test(result)) return fail("invalid_export_ref");
  return result;
};

const countsFor = (memories: readonly OwnerMemoryExportItem[]): {
  memories: number; lineages: number; sources: number;
} => ({
  memories: memories.length,
  lineages: memories.reduce((sum, item) => sum + item.lineage.length, 0),
  sources: memories.reduce((sum, item) => sum
    + item.lineage.reduce((lineageSum, lineage) => lineageSum + lineage.sources.length, 0), 0),
});

const chunkBody = (
  snapshotDigest: string,
  ordinal: number,
  memories: readonly OwnerMemoryExportItem[],
) => ({
  contractVersion: OWNER_MEMORY_EXPORT_CHUNK_VERSION,
  snapshotDigest,
  ordinal,
  memories,
});

const chunkEnvelopeForSizing = (
  snapshotDigest: string,
  ordinal: number,
  memories: readonly OwnerMemoryExportItem[],
) => ({ ...chunkBody(snapshotDigest, ordinal, memories), chunkDigest: "0".repeat(64) });

/**
 * Builds a complete, private account-memory export from one already-authorized
 * projection. It does not decide who may export: that belongs to the caller's
 * application capability. Every visible temporal leaf and every supporting
 * claim lineage must appear exactly once or the export fails closed.
 */
export const buildOwnerMemoryExport = (input: OwnerMemoryExportInput): OwnerMemoryExportBundle => {
  const supplied = snapshotInput(input);
  const renders = snapshotRenders(supplied.renders);
  if (!isApplicationGrantProjectedTreeInput(supplied.projected)
    || !Number.isSafeInteger(supplied.exported_at_epoch_seconds)
    || supplied.exported_at_epoch_seconds < 0
    || !Number.isSafeInteger(supplied.chunk_max_bytes)
    || supplied.chunk_max_bytes < OWNER_MEMORY_EXPORT_MIN_CHUNK_BYTES
    || supplied.chunk_max_bytes > OWNER_MEMORY_EXPORT_MAX_CHUNK_BYTES
    || typeof supplied.encode_ref !== "function" || isProxy(supplied.encode_ref)) {
    return fail("invalid_input");
  }

  const nodes = selectNodesForGranularity(
    buildDeterministicAnchors(supplied.projected).nodes,
    "temporal_leaf",
  ).slice().sort((left, right) => compareStrings(left.node_id, right.node_id));
  if (nodes.length > MAX_MEMORIES || renders.length !== nodes.length) {
    return fail("incomplete_render_set");
  }
  const renderByNode = new Map<string, RenderNode>();
  for (const render of renders) {
    if (!isProducedRenderNode(render) || renderByNode.has(render.node_id)) return fail("invalid_render");
    renderByNode.set(render.node_id, render);
  }
  if (nodes.some((node) => !renderByNode.has(node.node_id))) return fail("incomplete_render_set");

  const claimByRevision = new Map(supplied.projected.claims.map((claim) => [claim.claim_revision_id, claim]));
  const seenLineages = new Set<string>();
  const memories: OwnerMemoryExportItem[] = [];
  for (const node of nodes) {
    const render = renderByNode.get(node.node_id)!;
    let synthesized;
    try {
      synthesized = buildOwnerBoundSynthesizedProjection(supplied.projected, render);
    } catch {
      return fail("invalid_render");
    }
    const lineage: OwnerMemoryExportLineage[] = [];
    for (const revisionId of synthesized.live_claim_revision_ids.slice().sort(compareStrings)) {
      const claim = claimByRevision.get(revisionId);
      if (!claim) return fail("invalid_render");
      if (seenLineages.has(claim.claim_lineage_id)) return fail("duplicate_lineage");
      seenLineages.add(claim.claim_lineage_id);
      const sources = claim.evidence_spans.slice()
        .sort((left, right) => compareStrings(left.evidence_id, right.evidence_id))
        .map((source): OwnerMemoryExportSource => ({
          evidenceRef: encodedRef(supplied.encode_ref, "evidence", source.evidence_id),
          eventRef: encodedRef(supplied.encode_ref, "event", source.event_revision_id),
          captureRef: encodedRef(supplied.encode_ref, "capture", source.capture_session_id),
          excerpt: source.excerpt === null ? null : String(source.excerpt),
          range: { start: source.range.start, end: source.range.end },
        }));
      if (sources.length === 0) return fail("invalid_render");
      lineage.push({
        lineageRef: encodedRef(supplied.encode_ref, "lineage", claim.claim_lineage_id),
        revisionRef: encodedRef(supplied.encode_ref, "revision", claim.claim_revision_id),
        observedAt: String(claim.observed_at),
        temporalPrecision: String(claim.temporal_precision),
        sources,
      });
    }
    if (lineage.length === 0) return fail("invalid_render");
    memories.push(freezeItem({
      id: encodedRef(supplied.encode_ref, "memory", node.node_id),
      text: synthesized.synthesized_summary,
      sourceLanguage: render.source_language,
      lineage,
    }));
  }

  const total = countsFor(memories);
  if (total.lineages !== supplied.projected.claims.length
    || total.lineages > MAX_LINEAGES || total.sources > MAX_SOURCES) {
    return fail("duplicate_lineage");
  }
  const snapshotDigest = sha256CanonicalContent({
    version: OWNER_MEMORY_EXPORT_VERSION,
    graph_generation: supplied.projected.graph_generation,
    projected_content_digest: supplied.projected.projected_content_digest,
    projection_authorization_digest: supplied.projected.projection_authorization_digest,
    reader_projection_digest: supplied.projected.reader_projection_digest,
    granularity: "temporal_leaf",
  });

  const chunkGroups: OwnerMemoryExportItem[][] = [];
  let pending: OwnerMemoryExportItem[] = [];
  for (const memory of memories) {
    const candidate = [...pending, memory];
    const bytes = Buffer.byteLength(
      canonicalJson(chunkEnvelopeForSizing(snapshotDigest, chunkGroups.length, candidate)),
      "utf8",
    );
    if (bytes > supplied.chunk_max_bytes && pending.length === 0) return fail("export_too_large");
    if (bytes > supplied.chunk_max_bytes) {
      chunkGroups.push(pending);
      pending = [memory];
    } else {
      pending = candidate;
    }
  }
  if (pending.length > 0) chunkGroups.push(pending);

  const chunks = chunkGroups.map((group, ordinal): OwnerMemoryExportChunk => {
    const body = chunkBody(snapshotDigest, ordinal, group);
    const chunkDigest = sha256CanonicalContent(body);
    return Object.freeze({ ...body, memories: Object.freeze([...group]), chunkDigest });
  });
  const chunkRows = chunks.map((chunk) => {
    const counts = countsFor(chunk.memories);
    return Object.freeze({
      ordinal: chunk.ordinal,
      chunkDigest: chunk.chunkDigest,
      memoryCount: counts.memories,
      lineageCount: counts.lineages,
      sourceCount: counts.sources,
    });
  });
  const manifestBody = {
    contractVersion: OWNER_MEMORY_EXPORT_VERSION,
    exportedAtEpochSeconds: supplied.exported_at_epoch_seconds,
    snapshotDigest,
    granularity: "temporal_leaf" as const,
    counts: Object.freeze({ ...total, chunks: chunks.length }),
    chunks: Object.freeze(chunkRows),
  };
  const exportDigest = sha256CanonicalContent(manifestBody);
  const manifest: OwnerMemoryExportManifest = Object.freeze({ ...manifestBody, exportDigest });
  const chunkJson = Object.freeze(chunks.map((chunk) => canonicalJson(chunk)));
  return Object.freeze({
    manifest,
    chunks: Object.freeze(chunks),
    manifest_json: canonicalJson(manifest),
    chunk_json: chunkJson,
  });
};

const exactRecord = (value: unknown, keys: readonly string[]): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) return fail("invalid_input");
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length
    || actual.some((key, index) => key !== expected[index])) return fail("invalid_input");
  return value as Record<string, unknown>;
};

const exactArray = (value: unknown, maximum: number): readonly unknown[] => {
  if (!Array.isArray(value) || isProxy(value) || Object.getPrototypeOf(value) !== Array.prototype
    || value.length > maximum || Reflect.ownKeys(value).length !== value.length + 1) {
    return fail("invalid_input");
  }
  return value;
};

const count = (value: unknown, maximum: number): number => {
  if (!Number.isSafeInteger(value) || (value as number) < 0 || (value as number) > maximum) {
    return fail("invalid_input");
  }
  return value as number;
};

const text = (value: unknown, allowEmpty = false): string => {
  if (typeof value !== "string" || (!allowEmpty && value.length === 0)) return fail("invalid_input");
  return value;
};

const ref = (value: unknown): string => {
  const parsed = text(value);
  return EXPORT_REF.test(parsed) ? parsed : fail("invalid_export_ref");
};

const parseSource = (value: unknown): OwnerMemoryExportSource => {
  const row = exactRecord(value, ["evidenceRef", "eventRef", "captureRef", "excerpt", "range"]);
  const range = exactRecord(row["range"], ["start", "end"]);
  const start = count(range["start"], Number.MAX_SAFE_INTEGER);
  const end = count(range["end"], Number.MAX_SAFE_INTEGER);
  if (end < start || (row["excerpt"] !== null && typeof row["excerpt"] !== "string")) {
    return fail("invalid_input");
  }
  return freezeSource({
    evidenceRef: ref(row["evidenceRef"]),
    eventRef: ref(row["eventRef"]),
    captureRef: ref(row["captureRef"]),
    excerpt: row["excerpt"] as string | null,
    range: { start, end },
  });
};

const parseLineage = (value: unknown): OwnerMemoryExportLineage => {
  const row = exactRecord(value, [
    "lineageRef", "revisionRef", "observedAt", "temporalPrecision", "sources",
  ]);
  const sources = exactArray(row["sources"], MAX_SOURCES).map(parseSource);
  if (sources.length === 0 || new Set(sources.map((source) => source.evidenceRef)).size !== sources.length) {
    return fail("invalid_input");
  }
  return freezeLineage({
    lineageRef: ref(row["lineageRef"]),
    revisionRef: ref(row["revisionRef"]),
    observedAt: text(row["observedAt"]),
    temporalPrecision: text(row["temporalPrecision"]),
    sources,
  });
};

const parseItem = (value: unknown): OwnerMemoryExportItem => {
  const row = exactRecord(value, ["id", "text", "sourceLanguage", "lineage"]);
  const lineage = exactArray(row["lineage"], MAX_LINEAGES).map(parseLineage);
  if (lineage.length === 0
    || new Set(lineage.map((entry) => entry.lineageRef)).size !== lineage.length) {
    return fail("invalid_input");
  }
  return freezeItem({
    id: ref(row["id"]),
    text: text(row["text"]),
    sourceLanguage: text(row["sourceLanguage"]),
    lineage,
  });
};

/**
 * Strict consumer-side verifier for the emitted manifest/chunks. Alternate
 * JSON encodings, missing chunks, reordered ordinals, digest drift, duplicate
 * memories/lineages, and count mismatches are rejected.
 */
export const parseOwnerMemoryExportBundle = (
  manifestJsonValue: unknown,
  chunkJsonValue: unknown,
): OwnerMemoryExportBundle => {
  if (typeof manifestJsonValue !== "string"
    || Buffer.byteLength(manifestJsonValue, "utf8") > OWNER_MEMORY_EXPORT_MAX_CHUNK_BYTES
    || !Array.isArray(chunkJsonValue) || isProxy(chunkJsonValue)
    || Object.getPrototypeOf(chunkJsonValue) !== Array.prototype
    || chunkJsonValue.length > MAX_MEMORIES
    || chunkJsonValue.some((value) => typeof value !== "string"
      || Buffer.byteLength(value, "utf8") > OWNER_MEMORY_EXPORT_MAX_CHUNK_BYTES)) {
    return fail("invalid_input");
  }
  let rawManifest: unknown;
  const rawChunks: unknown[] = [];
  try {
    rawManifest = JSON.parse(manifestJsonValue);
    for (const value of chunkJsonValue) rawChunks.push(JSON.parse(value as string));
  } catch {
    return fail("invalid_input");
  }
  if (canonicalJson(rawManifest) !== manifestJsonValue
    || rawChunks.some((chunk, index) => canonicalJson(chunk) !== chunkJsonValue[index])) {
    return fail("invalid_input");
  }

  const manifestRow = exactRecord(rawManifest, [
    "contractVersion", "exportedAtEpochSeconds", "snapshotDigest", "granularity",
    "counts", "chunks", "exportDigest",
  ]);
  if (manifestRow["contractVersion"] !== OWNER_MEMORY_EXPORT_VERSION
    || manifestRow["granularity"] !== "temporal_leaf") return fail("invalid_input");
  const snapshotDigest = text(manifestRow["snapshotDigest"]);
  const exportDigest = text(manifestRow["exportDigest"]);
  if (!/^[a-f0-9]{64}$/.test(snapshotDigest) || !/^[a-f0-9]{64}$/.test(exportDigest)) {
    return fail("invalid_input");
  }
  const expectedCounts = exactRecord(manifestRow["counts"], [
    "memories", "lineages", "sources", "chunks",
  ]);
  const expectedChunkRows = exactArray(manifestRow["chunks"], MAX_MEMORIES);
  if (expectedChunkRows.length !== rawChunks.length) return fail("invalid_input");

  const memories = new Set<string>();
  const lineages = new Set<string>();
  const chunks: OwnerMemoryExportChunk[] = [];
  const chunkRows: OwnerMemoryExportManifest["chunks"][number][] = [];
  for (let ordinal = 0; ordinal < rawChunks.length; ordinal += 1) {
    const row = exactRecord(rawChunks[ordinal], [
      "contractVersion", "snapshotDigest", "ordinal", "memories", "chunkDigest",
    ]);
    if (row["contractVersion"] !== OWNER_MEMORY_EXPORT_CHUNK_VERSION
      || row["snapshotDigest"] !== snapshotDigest || row["ordinal"] !== ordinal) {
      return fail("invalid_input");
    }
    const parsedMemories = exactArray(row["memories"], MAX_MEMORIES).map(parseItem);
    if (parsedMemories.length === 0) return fail("invalid_input");
    for (const memory of parsedMemories) {
      if (memories.has(memory.id)) return fail("invalid_input");
      memories.add(memory.id);
      for (const lineage of memory.lineage) {
        if (lineages.has(lineage.lineageRef)) return fail("duplicate_lineage");
        lineages.add(lineage.lineageRef);
      }
    }
    const body = chunkBody(snapshotDigest, ordinal, parsedMemories);
    const chunkDigest = text(row["chunkDigest"]);
    if (chunkDigest !== sha256CanonicalContent(body)) return fail("invalid_input");
    const chunk = Object.freeze({ ...body, memories: Object.freeze(parsedMemories), chunkDigest });
    chunks.push(chunk);
    const totals = countsFor(parsedMemories);
    const chunkRow = Object.freeze({
      ordinal,
      chunkDigest,
      memoryCount: totals.memories,
      lineageCount: totals.lineages,
      sourceCount: totals.sources,
    });
    if (canonicalJson(exactRecord(expectedChunkRows[ordinal], [
      "ordinal", "chunkDigest", "memoryCount", "lineageCount", "sourceCount",
    ])) !== canonicalJson(chunkRow)) return fail("invalid_input");
    chunkRows.push(chunkRow);
  }
  const totals = countsFor(chunks.flatMap((chunk) => chunk.memories));
  const counts = Object.freeze({ ...totals, chunks: chunks.length });
  if (count(expectedCounts["memories"], MAX_MEMORIES) !== counts.memories
    || count(expectedCounts["lineages"], MAX_LINEAGES) !== counts.lineages
    || count(expectedCounts["sources"], MAX_SOURCES) !== counts.sources
    || count(expectedCounts["chunks"], MAX_MEMORIES) !== counts.chunks) {
    return fail("invalid_input");
  }
  const exportedAtEpochSeconds = count(
    manifestRow["exportedAtEpochSeconds"],
    Number.MAX_SAFE_INTEGER,
  );
  const manifestBody = {
    contractVersion: OWNER_MEMORY_EXPORT_VERSION,
    exportedAtEpochSeconds,
    snapshotDigest,
    granularity: "temporal_leaf" as const,
    counts,
    chunks: Object.freeze(chunkRows),
  };
  if (sha256CanonicalContent(manifestBody) !== exportDigest) return fail("invalid_input");
  const manifest: OwnerMemoryExportManifest = Object.freeze({ ...manifestBody, exportDigest });
  return Object.freeze({
    manifest,
    chunks: Object.freeze(chunks),
    manifest_json: manifestJsonValue,
    chunk_json: Object.freeze([...(chunkJsonValue as string[])]),
  });
};
