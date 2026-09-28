import { createHash } from "node:crypto";
import { describe, expect, test } from "bun:test";

import {
  projectApplicationDefaultReadTreeInputFromAuthorizationEvidence,
} from "./authorization-boundary";
import { selectNodesForGranularity } from "./granularity";
import {
  buildOwnerMemoryExport,
  OwnerMemoryExportError,
  parseOwnerMemoryExportBundle,
  type OwnerMemoryExportRefKind,
} from "./owner-memory-export";
import { renderStructuralTree } from "./render";
import { buildDeterministicAnchors } from "./tree";
import { snapshot } from "./tree.fixture";

const digest = (value: string): string => createHash("sha256").update(value).digest("hex");

const fixture = async () => {
  const projected = projectApplicationDefaultReadTreeInputFromAuthorizationEvidence(
    snapshot(),
    { account_timezone: "UTC" },
    {
      owner_account_id: "owner",
      app_id: "app:export",
      key_id: "credential:export",
      principal_digest: digest("principal"),
      authorization_digest: digest("authorization"),
      persisted_grant_state_digest: digest("grant"),
    },
  );
  const tree = buildDeterministicAnchors(projected);
  const allRenders = await renderStructuralTree(tree, projected, {
    render: async (request) => {
      const claims = (request.input as { claims: readonly { evidence_refs: readonly string[] }[] }).claims;
      return {
        summary_text: "A user-legible memory summary.",
        citations: [...new Set(claims.flatMap((claim) => claim.evidence_refs))].sort(),
      };
    },
  }, {
    strategy: "owner-export-summary",
    model_version: "deterministic-test-v1",
    prompt_version: "owner-export-test-v1",
    policy_version: "application-default-v1",
    schema_version: "owner-memory-export-v1",
  });
  const leafIds = new Set(selectNodesForGranularity(tree.nodes, "temporal_leaf")
    .map((node) => node.node_id));
  const renders = allRenders.filter((render) => leafIds.has(render.node_id));
  const encode_ref = (kind: OwnerMemoryExportRefKind, value: string): string =>
    `mxr1_${digest(`${kind}\0${value}`)}`;
  return { projected, renders, encode_ref };
};

describe("owner memory export", () => {
  test("exports every authorized lineage once with legible source provenance and no raw ids", async () => {
    const { projected, renders, encode_ref } = await fixture();
    const exported = buildOwnerMemoryExport({
      projected,
      renders,
      exported_at_epoch_seconds: 1_800_000_000,
      chunk_max_bytes: 64 * 1024,
      encode_ref,
    });

    expect(exported.manifest.contractVersion).toBe("owner-memory-export-v1");
    expect(exported.manifest.counts).toEqual({ memories: 1, lineages: 1, sources: 1, chunks: 1 });
    expect(exported.chunks[0]!.memories[0]!.text).toBe("A user-legible memory summary.");
    expect(exported.chunks[0]!.memories[0]!.lineage[0]).toMatchObject({
      observedAt: "2026-01-02T10:00:00Z",
      temporalPrecision: "instant",
      sources: [{ excerpt: "evidence", range: { start: 0, end: 1 } }],
    });
    expect(JSON.parse(exported.manifest_json)).toEqual(exported.manifest);
    const serialized = `${exported.manifest_json}\n${exported.chunk_json.join("\n")}`;
    for (const raw of ["owner", "lineage:a", "a", "e1", "event", "capture"]) {
      expect(serialized).not.toContain(`\"${raw}\"`);
    }
    expect(serialized).toContain("evidence");
    expect(Object.isFrozen(exported.manifest)).toBe(true);
    expect(Object.isFrozen(exported.chunks[0]!.memories[0]!.lineage[0]!.sources[0]!.range)).toBe(true);
    const verified = parseOwnerMemoryExportBundle(exported.manifest_json, exported.chunk_json);
    expect(verified.manifest.exportDigest).toBe(exported.manifest.exportDigest);
    expect(verified.chunk_json).toEqual(exported.chunk_json);
  });

  test("is byte-stable for one snapshot and splits only at complete memory boundaries", async () => {
    const { projected, renders, encode_ref } = await fixture();
    const input = {
      projected,
      renders,
      exported_at_epoch_seconds: 1_800_000_000,
      chunk_max_bytes: 64 * 1024,
      encode_ref,
    };
    const first = buildOwnerMemoryExport(input);
    const second = buildOwnerMemoryExport({ ...input, renders: [...renders].reverse() });
    expect(second.manifest_json).toBe(first.manifest_json);
    expect(second.chunk_json).toEqual(first.chunk_json);
    expect(first.manifest.chunks.map((chunk) => chunk.chunkDigest))
      .toEqual(first.chunks.map((chunk) => chunk.chunkDigest));
  });

  test("fails closed on omission, extra renders, cloned authority, or malformed refs", async () => {
    const { projected, renders, encode_ref } = await fixture();
    const base = {
      projected,
      renders,
      exported_at_epoch_seconds: 1_800_000_000,
      chunk_max_bytes: 64 * 1024,
      encode_ref,
    };
    expect(() => buildOwnerMemoryExport({ ...base, renders: [] }))
      .toThrow(new OwnerMemoryExportError("incomplete_render_set"));
    expect(() => buildOwnerMemoryExport({ ...base, renders: [...renders, renders[0]!] }))
      .toThrow(new OwnerMemoryExportError("incomplete_render_set"));
    expect(() => buildOwnerMemoryExport({ ...base, projected: structuredClone(projected) }))
      .toThrow(new OwnerMemoryExportError("invalid_input"));
    expect(() => buildOwnerMemoryExport({ ...base, encode_ref: () => "raw-id" }))
      .toThrow(new OwnerMemoryExportError("invalid_export_ref"));
  });

  test("rejects hostile input without invoking accessors", async () => {
    const { projected, renders, encode_ref } = await fixture();
    let calls = 0;
    const hostile: Record<string, unknown> = {
      projected,
      renders,
      exported_at_epoch_seconds: 1_800_000_000,
      chunk_max_bytes: 64 * 1024,
    };
    Object.defineProperty(hostile, "encode_ref", {
      enumerable: true,
      get: () => {
        calls += 1;
        return encode_ref;
      },
    });
    expect(() => buildOwnerMemoryExport(hostile as never))
      .toThrow(new OwnerMemoryExportError("invalid_input"));
    expect(calls).toBe(0);
    expect(() => buildOwnerMemoryExport(new Proxy({
      projected,
      renders,
      exported_at_epoch_seconds: 1_800_000_000,
      chunk_max_bytes: 64 * 1024,
      encode_ref,
    }, {}) as never)).toThrow(new OwnerMemoryExportError("invalid_input"));
  });

  test("consumer verification rejects reordered, missing, noncanonical, or tampered chunks", async () => {
    const { projected, renders, encode_ref } = await fixture();
    const exported = buildOwnerMemoryExport({
      projected,
      renders,
      exported_at_epoch_seconds: 1_800_000_000,
      chunk_max_bytes: 64 * 1024,
      encode_ref,
    });
    expect(() => parseOwnerMemoryExportBundle(exported.manifest_json, []))
      .toThrow(new OwnerMemoryExportError("invalid_input"));
    expect(() => parseOwnerMemoryExportBundle(
      JSON.stringify(JSON.parse(exported.manifest_json), null, 2),
      exported.chunk_json,
    )).toThrow(new OwnerMemoryExportError("invalid_input"));
    const chunk = JSON.parse(exported.chunk_json[0]!) as { memories: { text: string }[] };
    chunk.memories[0]!.text = "tampered";
    expect(() => parseOwnerMemoryExportBundle(
      exported.manifest_json,
      [JSON.stringify(chunk)],
    )).toThrow(new OwnerMemoryExportError("invalid_input"));
    expect(() => parseOwnerMemoryExportBundle(
      exported.manifest_json,
      new Proxy([...exported.chunk_json], {}),
    )).toThrow(new OwnerMemoryExportError("invalid_input"));
  });
});
