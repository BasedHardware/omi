import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import type { AgentRuntimeKernel } from "../src/runtime/kernel.js";
import {
  finalizeRelayToolResult,
  finalizedToolResultOutcome,
  MAX_RELAY_TOOL_RESULT_BYTES,
  type RelayToolResultIdentity,
} from "../src/runtime/relay-tool-result.js";
import { assertToolResultEnvelope } from "../src/runtime/tool-result-envelope.js";

const identity: RelayToolResultIdentity = {
  invocationId: "inv-normal-pending-tool",
  ownerId: "owner-relay",
  sessionId: "session-relay",
  runId: "run-relay",
  attemptId: "attempt-relay",
  toolName: "capture_screen",
};

const roots: string[] = [];

afterEach(() => {
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true });
});

function kernelWithArtifact(): AgentRuntimeKernel {
  return {
    persistArtifact: vi.fn(() => ({ artifactId: "artifact-relay-output" })),
  } as unknown as AgentRuntimeKernel;
}

function finalize(
  result: string,
  outcome?: "succeeded" | "failed",
  resultIdentity: RelayToolResultIdentity = identity,
) {
  const artifactRoot = mkdtempSync(join(tmpdir(), "omi-relay-tool-result-"));
  roots.push(artifactRoot);
  return finalizeRelayToolResult({
    identity: resultIdentity,
    result,
    outcome,
    kernel: kernelWithArtifact(),
    artifactRoot,
  });
}

describe("normal pending stdio tool-result boundary", () => {
  it("persists and projects an oversized Swift success without changing its outcome", () => {
    const result = finalize(JSON.stringify({ ok: true, snapshot: "x".repeat(MAX_RELAY_TOOL_RESULT_BYTES + 1) }), "succeeded");
    expect(Buffer.byteLength(result, "utf8")).toBeLessThanOrEqual(MAX_RELAY_TOOL_RESULT_BYTES);

    const payload = JSON.parse(result) as { ok: boolean; omitted: Record<string, number>; toolResultEnvelope: unknown };
    expect(payload.ok).toBe(true);
    expect(payload.omitted).toBeDefined();
    assertToolResultEnvelope(payload.toolResultEnvelope);
    expect(payload.toolResultEnvelope).toMatchObject({
      status: "succeeded",
      truncated: true,
      fullOutputRef: "artifact:artifact-relay-output",
      provenance: {
        invocationId: identity.invocationId,
        runId: identity.runId,
        attemptId: identity.attemptId,
        toolName: identity.toolName,
      },
    });
    expect(finalizedToolResultOutcome(result)).toBe("succeeded");
  });

  it("keeps succeeded executor results succeeded for deterministic fuzz sizes through 4 MB", () => {
    for (const bytes of [0, 1, 127, 8191, 8192, 8193, 65_537, 524_289, 4 * 1024 * 1024]) {
      const result = finalize(JSON.stringify({ ok: true, text: "x".repeat(bytes) }), "succeeded");
      const payload = JSON.parse(result) as { ok: boolean; toolResultEnvelope: { status: string } };
      expect(Buffer.byteLength(result, "utf8")).toBeLessThanOrEqual(MAX_RELAY_TOOL_RESULT_BYTES);
      expect(payload.ok, `bytes=${bytes}`).toBe(true);
      expect(payload.toolResultEnvelope.status, `bytes=${bytes}`).toBe("succeeded");
      expect(finalizedToolResultOutcome(result), `bytes=${bytes}`).toBe("succeeded");
    }
  });

  it("never throws when rewrapping truncated source envelopes with expanded payloads", () => {
    for (const payloadBytes of [80, 100, 101, 1_024, 16_384]) {
      const source = JSON.stringify({
        ok: true,
        text: "x".repeat(payloadBytes),
        toolResultEnvelope: {
          version: 1,
          status: "succeeded",
          truncated: true,
          originalBytes: 100,
          projectedBytes: 50,
          fullOutputRef: "artifact:upstream-result",
        },
      });
      let result = "";
      expect(() => { result = finalize(source, "succeeded"); }).not.toThrow();
      expect(JSON.parse(result)).toMatchObject({
        ok: true,
        toolResultEnvelope: { status: "succeeded" },
      });
    }
  });

  it("normalizes an untruncated source whose complete byte measurement exceeds its payload", () => {
    const source = JSON.stringify({
      ok: true,
      text: "complete",
      toolResultEnvelope: {
        version: 1,
        status: "succeeded",
        truncated: false,
        originalBytes: 1_000,
        projectedBytes: 1_000,
        fullOutputRef: null,
      },
    });
    let result = "";
    expect(() => { result = finalize(source, "succeeded"); }).not.toThrow();
    const payload = JSON.parse(result) as {
      ok: boolean;
      toolResultEnvelope: { truncated: boolean; originalBytes: number; projectedBytes: number };
    };
    expect(payload.ok).toBe(true);
    expect(payload.toolResultEnvelope.truncated).toBe(false);
    expect(payload.toolResultEnvelope.originalBytes).toBe(payload.toolResultEnvelope.projectedBytes);
  });

  it("clamps an unbounded originating utterance without stranding projection", () => {
    const result = finalize(
      JSON.stringify({ ok: true, text: "x".repeat(MAX_RELAY_TOOL_RESULT_BYTES * 2) }),
      "succeeded",
      { ...identity, purpose: "🧠".repeat(10_000) },
    );
    const payload = JSON.parse(result) as {
      ok: boolean;
      toolResultEnvelope: { status: string; purpose?: string };
    };
    expect(Buffer.byteLength(result, "utf8")).toBeLessThanOrEqual(MAX_RELAY_TOOL_RESULT_BYTES);
    expect(payload.ok).toBe(true);
    expect(payload.toolResultEnvelope.status).toBe("succeeded");
    expect(Buffer.byteLength(payload.toolResultEnvelope.purpose ?? "", "utf8")).toBeLessThanOrEqual(256);
  });

  it("emits one degraded fallback record for a truncated projection", () => {
    const artifactRoot = mkdtempSync(join(tmpdir(), "omi-relay-tool-result-"));
    roots.push(artifactRoot);
    const onDegraded = vi.fn();
    const result = finalizeRelayToolResult({
      identity,
      result: JSON.stringify({ ok: true, text: "x".repeat(MAX_RELAY_TOOL_RESULT_BYTES * 2) }),
      outcome: "succeeded",
      kernel: kernelWithArtifact(),
      artifactRoot,
      onDegraded,
    });
    expect(JSON.parse(result).toolResultEnvelope.truncated).toBe(true);
    expect(onDegraded).toHaveBeenCalledOnce();
    expect(onDegraded).toHaveBeenCalledWith(expect.objectContaining({
      toolName: identity.toolName,
      originalBytes: expect.any(Number),
      projectedBytes: expect.any(Number),
    }));
  });

  it("accounts for non-section siblings as truncated recoverable metadata", () => {
    const artifactRoot = mkdtempSync(join(tmpdir(), "omi-relay-tool-result-"));
    roots.push(artifactRoot);
    const onDegraded = vi.fn();
    const items = Array.from({ length: 18 }, (_, index) => ({
      title: `Conversation ${index}`,
      summary: `detail-${index}-${"x".repeat(270)}`,
    }));
    const result = finalizeRelayToolResult({
      identity: { ...identity, toolName: "get_conversations" },
      result: JSON.stringify({
        ok: true,
        transportPadding: "p".repeat(4_000),
        sections: [{ name: "conversations", total: items.length, items }],
      }),
      outcome: "succeeded",
      kernel: kernelWithArtifact(),
      artifactRoot,
      onDegraded,
    });
    const payload = JSON.parse(result) as {
      omitted?: Record<string, number>;
      toolResultEnvelope: { truncated: boolean; originalBytes: number; projectedBytes: number };
    };
    expect(payload.omitted?.conversations).toBe(0);
    expect(payload.omitted?.meta).toBeDefined();
    expect(payload.toolResultEnvelope.truncated).toBe(true);
    expect(payload.toolResultEnvelope.originalBytes).toBeGreaterThan(payload.toolResultEnvelope.projectedBytes);
    expect(onDegraded).toHaveBeenCalledOnce();
  });

  it.each([
    ["swift_tool_timeout", "Timed out waiting for the Swift tool executor"],
    ["policy_denied", "Tool capability rejected"],
  ])("envelopes a normal pending rejection: %s", (code, message) => {
    const result = finalize(JSON.stringify({ ok: false, error: { code, message } }), "failed");
    const payload = JSON.parse(result) as { ok: boolean; toolResultEnvelope: unknown; error: { code: string } };

    expect(payload.ok).toBe(false);
    expect(payload.error.code).toBe(code);
    assertToolResultEnvelope(payload.toolResultEnvelope);
    expect(payload.toolResultEnvelope).toMatchObject({
      status: "failed",
      truncated: false,
      provenance: {
        invocationId: identity.invocationId,
        runId: identity.runId,
        attemptId: identity.attemptId,
        toolName: identity.toolName,
      },
    });
  });

  it("makes a structured tool failure canonical despite a succeeded Swift transport receipt", () => {
    const result = finalize(JSON.stringify({
      ok: false,
      error: { code: "permission_denied", message: "Screen Recording is not available." },
    }), "succeeded");
    const payload = JSON.parse(result) as { ok: boolean; toolResultEnvelope: unknown; error: { code: string } };

    expect(payload.ok).toBe(false);
    expect(payload.error.code).toBe("permission_denied");
    assertToolResultEnvelope(payload.toolResultEnvelope);
    expect(payload.toolResultEnvelope).toMatchObject({ status: "failed" });
    expect(finalizedToolResultOutcome(result)).toBe("failed");
  });

  it("preserves plain-text Swift success as a successful bounded projection", () => {
    const result = finalize("No tasks due today.", "succeeded");
    const payload = JSON.parse(result) as { ok: boolean; text: string; toolResultEnvelope: unknown };

    expect(payload.ok).toBe(true);
    expect(payload.text).toBe("No tasks due today.");
    assertToolResultEnvelope(payload.toolResultEnvelope);
    expect(payload.toolResultEnvelope).toMatchObject({ status: "succeeded", truncated: false });
    expect(finalizedToolResultOutcome(result)).toBe("succeeded");
  });

  it("keeps a worst-case bounded realtime conversation projection model-visible", () => {
    const items = Array.from({ length: 8 }, (_, index) => ({
      title: `Conversation ${index} ${"t".repeat(140)}`,
      summary: `Summary ${index} ${"s".repeat(400)}`,
      created_at: `2026-08-28T23:${String(index).padStart(2, "0")}:00Z`,
    }));
    const conversationIdentity = { ...identity, toolName: "get_conversations" };
    const result = finalize(
      JSON.stringify({ ok: true, tool: "get_conversations", order: "newest_first", items }),
      "succeeded",
      conversationIdentity,
    );
    const payload = JSON.parse(result) as {
      ok: boolean;
      items: unknown[];
      toolResultEnvelope: { status: string; truncated: boolean; fullOutputRef: unknown };
    };

    expect(Buffer.byteLength(result, "utf8")).toBeLessThanOrEqual(MAX_RELAY_TOOL_RESULT_BYTES);
    expect(payload.ok).toBe(true);
    expect(payload.items).toHaveLength(8);
    expect(payload.toolResultEnvelope).toMatchObject({
      status: "succeeded",
      truncated: false,
      fullOutputRef: null,
      provenance: { toolName: "get_conversations" },
    });
  });
});
