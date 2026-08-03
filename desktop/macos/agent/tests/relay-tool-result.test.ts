import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import type { AgentRuntimeKernel } from "../src/runtime/kernel.js";
import {
  finalizeRelayToolResult,
  finalizedToolResultOutcome,
  MAX_RELAY_TOOL_RESULT_BYTES,
  RELAY_TRUNCATION_KEY,
  RELAY_TRUNCATION_SUFFIX,
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

type TruncationNotice = {
  reason: string;
  field: string;
  fullOutputRef: string;
  message: string;
  shownItems?: number;
  totalItems?: number;
};

function head(text: string): string {
  expect(text.endsWith(RELAY_TRUNCATION_SUFFIX)).toBe(true);
  return text.slice(0, text.length - RELAY_TRUNCATION_SUFFIX.length);
}

describe("normal pending stdio tool-result boundary", () => {
  it("persists an oversized Swift success and still delivers a marked head projection", () => {
    const snapshot = "x".repeat(MAX_RELAY_TOOL_RESULT_BYTES + 1);
    const result = finalize(JSON.stringify({ ok: true, snapshot }), "succeeded");
    expect(Buffer.byteLength(result, "utf8")).toBeLessThanOrEqual(MAX_RELAY_TOOL_RESULT_BYTES);

    const payload = JSON.parse(result) as {
      ok: boolean;
      snapshot: string;
      toolResultEnvelope: unknown;
      error?: { code: string };
      [RELAY_TRUNCATION_KEY]: TruncationNotice;
    };
    // A budget overflow is a partial answer, not a lost one: the successful
    // tool result keeps its status and returns usable content.
    expect(payload.ok).toBe(true);
    expect(payload.error).toBeUndefined();
    expect(head(payload.snapshot).length).toBeGreaterThan(0);
    expect(snapshot.startsWith(head(payload.snapshot))).toBe(true);
    expect(payload[RELAY_TRUNCATION_KEY]).toMatchObject({
      reason: "relay_result_exceeded_budget",
      field: "snapshot",
      fullOutputRef: "artifact:artifact-relay-output",
    });
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

  it("delivers a readable head of an oversized plain-text Swift success", () => {
    // The `search_conversations` regression: plain text, so the whole payload
    // is one `text` field and no structural projection is possible.
    const source = Array.from(
      { length: 400 },
      (_, index) => `Conversation ${index}: ${"detail ".repeat(20)}`,
    ).join("\n");
    expect(Buffer.byteLength(source, "utf8")).toBeGreaterThan(MAX_RELAY_TOOL_RESULT_BYTES);

    const result = finalize(source, "succeeded");
    expect(Buffer.byteLength(result, "utf8")).toBeLessThanOrEqual(MAX_RELAY_TOOL_RESULT_BYTES);

    const payload = JSON.parse(result) as {
      ok: boolean;
      text: string;
      [RELAY_TRUNCATION_KEY]: TruncationNotice;
      toolResultEnvelope: unknown;
    };
    expect(payload.ok).toBe(true);
    expect(payload.text).toContain("Conversation 0:");
    expect(source.startsWith(head(payload.text))).toBe(true);
    expect(Buffer.byteLength(head(payload.text), "utf8")).toBeGreaterThan(MAX_RELAY_TOOL_RESULT_BYTES / 2);
    expect(payload[RELAY_TRUNCATION_KEY].field).toBe("text");
    assertToolResultEnvelope(payload.toolResultEnvelope);
    expect(payload.toolResultEnvelope).toMatchObject({ status: "succeeded", truncated: true });
  });

  it("drops whole trailing items rather than cutting a JSON-shaped payload mid-structure", () => {
    const conversations = Array.from({ length: 13 }, (_, index) => ({
      id: `conversation-${index}`,
      title: `Conversation ${index}`,
      transcript: "spoken detail ".repeat(80),
    }));
    const result = finalize(JSON.stringify({ ok: true, matched: 13, conversations }), "succeeded");
    expect(Buffer.byteLength(result, "utf8")).toBeLessThanOrEqual(MAX_RELAY_TOOL_RESULT_BYTES);

    const payload = JSON.parse(result) as {
      ok: boolean;
      matched: number;
      conversations: { id: string; title: string; transcript: string }[];
      [RELAY_TRUNCATION_KEY]: TruncationNotice;
    };
    expect(payload.ok).toBe(true);
    // Sibling fields survive intact, and every delivered item is whole.
    expect(payload.matched).toBe(13);
    expect(payload.conversations.length).toBeGreaterThan(0);
    expect(payload.conversations.length).toBeLessThan(13);
    for (const [index, conversation] of payload.conversations.entries()) {
      expect(conversation).toEqual(conversations[index]);
    }
    expect(payload[RELAY_TRUNCATION_KEY]).toMatchObject({
      field: "conversations",
      shownItems: payload.conversations.length,
      totalItems: 13,
    });
  });

  it("reaches a shrinkable field nested under a wrapper object", () => {
    const notes = Array.from({ length: 30 }, (_, index) => ({ id: index, body: "note body ".repeat(40) }));
    const result = finalize(JSON.stringify({ ok: true, data: { source: "local", notes } }), "succeeded");
    expect(Buffer.byteLength(result, "utf8")).toBeLessThanOrEqual(MAX_RELAY_TOOL_RESULT_BYTES);

    const payload = JSON.parse(result) as {
      ok: boolean;
      data: { source: string; notes: { id: number; body: string }[] };
      [RELAY_TRUNCATION_KEY]: TruncationNotice;
    };
    expect(payload.ok).toBe(true);
    expect(payload.data.source).toBe("local");
    expect(payload.data.notes.length).toBeGreaterThan(0);
    expect(payload.data.notes.length).toBeLessThan(30);
    expect(payload.data.notes[0]).toEqual(notes[0]);
    expect(payload[RELAY_TRUNCATION_KEY]).toMatchObject({ field: "data.notes", totalItems: 30 });
  });

  it("cuts a multi-byte head on a code-point boundary", () => {
    // Three ASCII bytes offset the 4-byte code points so a naive byte cut at
    // the budget lands inside a character, and a naive JS index cut would
    // split the surrogate pair.
    const source = `abc${"😀".repeat(MAX_RELAY_TOOL_RESULT_BYTES)}`;
    const result = finalize(source, "succeeded");
    expect(Buffer.byteLength(result, "utf8")).toBeLessThanOrEqual(MAX_RELAY_TOOL_RESULT_BYTES);

    const projected = head((JSON.parse(result) as { text: string }).text);
    expect(projected.length).toBeGreaterThan(0);
    expect(source.startsWith(projected)).toBe(true);
    // A split code point survives neither a UTF-8 round trip nor a surrogate
    // scan: both catch a lone surrogate or a replacement character.
    expect(Buffer.from(projected, "utf8").toString("utf8")).toBe(projected);
    expect(projected).not.toContain("�");
    expect([...projected].every((character) => character.codePointAt(0)! < 0xd800 || character.codePointAt(0)! > 0xdfff))
      .toBe(true);
  });

  it("keeps a result that fits the budget byte-identical and unmarked", () => {
    const source = JSON.stringify({ ok: true, conversations: [{ id: "c-1", title: "Standup" }] });
    const payload = JSON.parse(finalize(source, "succeeded")) as Record<string, unknown>;

    expect(payload.ok).toBe(true);
    expect(payload.conversations).toEqual([{ id: "c-1", title: "Standup" }]);
    expect(payload[RELAY_TRUNCATION_KEY]).toBeUndefined();
    assertToolResultEnvelope(payload.toolResultEnvelope);
    expect(payload.toolResultEnvelope).toMatchObject({ truncated: false, fullOutputRef: null });
  });

  it("names the recovery tools when no head slice fits the budget", () => {
    // Numeric fields are not shrinkable, so no head projection exists and the
    // typed budget failure remains the terminal answer.
    const wide: Record<string, number> = {};
    for (let index = 0; index < 1200; index += 1) wide[`metric_${index}`] = index;
    const result = finalize(JSON.stringify({ ok: true, ...wide }), "succeeded");
    expect(Buffer.byteLength(result, "utf8")).toBeLessThanOrEqual(MAX_RELAY_TOOL_RESULT_BYTES);

    const payload = JSON.parse(result) as { ok: boolean; error: { code: string; message: string } };
    expect(payload.ok).toBe(false);
    expect(payload.error.code).toBe("tool_result_projection_exceeded_budget");
    expect(payload.error.message).toContain("read_tool_output");
    expect(payload.error.message).toContain("search_tool_output");
  });

  it("tells the model how to read the rest of a truncated result", () => {
    const result = finalize("x".repeat(MAX_RELAY_TOOL_RESULT_BYTES * 2), "succeeded");
    const notice = (JSON.parse(result) as Record<string, TruncationNotice>)[RELAY_TRUNCATION_KEY]!;

    expect(notice.message).toContain("fullOutputRef");
    expect(notice.message).toContain("read_tool_output");
    expect(notice.message).toContain("search_tool_output");
    expect(notice.fullOutputRef).toBe("artifact:artifact-relay-output");
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
