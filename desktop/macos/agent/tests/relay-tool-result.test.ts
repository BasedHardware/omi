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

function finalize(result: string, outcome?: "succeeded" | "failed") {
  const artifactRoot = mkdtempSync(join(tmpdir(), "omi-relay-tool-result-"));
  roots.push(artifactRoot);
  return finalizeRelayToolResult({
    identity,
    result,
    outcome,
    kernel: kernelWithArtifact(),
    artifactRoot,
  });
}

describe("normal pending stdio tool-result boundary", () => {
  it("persists and replaces an oversized Swift success before writing the relay frame", () => {
    const result = finalize(JSON.stringify({ ok: true, snapshot: "x".repeat(MAX_RELAY_TOOL_RESULT_BYTES + 1) }), "succeeded");
    expect(Buffer.byteLength(result, "utf8")).toBeLessThanOrEqual(MAX_RELAY_TOOL_RESULT_BYTES);

    const payload = JSON.parse(result) as { ok: boolean; toolResultEnvelope: unknown; error?: { code: string } };
    expect(payload.ok).toBe(false);
    expect(payload.error?.code).toBe("tool_result_projection_exceeded_budget");
    assertToolResultEnvelope(payload.toolResultEnvelope);
    expect(payload.toolResultEnvelope).toMatchObject({
      status: "failed",
      truncated: true,
      fullOutputRef: "artifact:artifact-relay-output",
      provenance: {
        invocationId: identity.invocationId,
        runId: identity.runId,
        attemptId: identity.attemptId,
        toolName: identity.toolName,
      },
    });
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
});
