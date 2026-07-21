import { createHash } from "node:crypto";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { compactRealtimeSpawnToolResult } from "../src/runtime/agent-spawn-journal.js";

const FIXTURE_DIR = join(
  dirname(fileURLToPath(import.meta.url)),
  "../fixtures/spawn-receipt/v1",
);

describe("spawn-receipt fixtures v1", () => {
  it("lists both valid and malformed fixtures", () => {
    const names = readdirSync(FIXTURE_DIR).filter((name) => name.endsWith(".json"));
    expect(names.some((name) => name.startsWith("valid-"))).toBe(true);
    expect(names.some((name) => name.startsWith("malformed-"))).toBe(true);
  });

  it("matches emitter output semantically for valid-running", () => {
    const fixture = JSON.parse(
      readFileSync(join(FIXTURE_DIR, "valid-running.json"), "utf8"),
    ) as Record<string, unknown>;
    const continuityKey = (fixture.journalReceipt as { continuityKey: string }).continuityKey;
    const pillId = (fixture.child as { pillId: string }).pillId;
    const descriptor = {
      schemaVersion: 1 as const,
      surface: {
        surfaceKind: "realtime_voice",
        externalRefKind: "chat",
        externalRefId: "voice-default",
      },
      continuityKey,
      pillId,
      userText: "Have an agent research launch risks.",
      assistantText: "I started a background agent for that.",
      objective: "Research launch risks",
      title: "Launch Risk Research",
    };
    const raw = JSON.stringify({
      ok: true,
      agents: [{
        session: {
          sessionId: "session-child",
          externalRefId: pillId,
          title: "Launch Risk Research",
        },
        run: {
          runId: "run-child",
          sessionId: "session-child",
          status: "running",
          input: { prompt: "Research launch risks" },
          updatedAtMs: 1_720_000_000_000,
        },
        attempt: {
          attemptId: "attempt-child",
          runId: "run-child",
          status: "running",
          adapterId: "hermes",
          updatedAtMs: 1_720_000_000_000,
        },
      }],
      toolResultEnvelope: {
        version: 1,
        status: "succeeded",
        truncated: false,
        originalBytes: 512,
        projectedBytes: 512,
        fullOutputRef: null,
        provenance: {
          invocationId: "invocation-spawn",
          runId: "run-parent",
          attemptId: "attempt-parent",
          toolName: "spawn_agent",
        },
      },
    });
    const emitted = JSON.parse(compactRealtimeSpawnToolResult(raw, descriptor));
    expect(emitted).toMatchObject({
      schemaVersion: fixture.schemaVersion,
      ok: fixture.ok,
      journalReceipt: fixture.journalReceipt,
      child: fixture.child,
      semanticDigest: fixture.semanticDigest,
      providerResult: {
        schemaVersion: 1,
        ok: true,
        code: "spawn_started",
        child: (fixture.providerResult as { child: unknown }).child,
        semanticDigest: fixture.semanticDigest,
      },
      toolResultEnvelope: {
        version: 1,
        truncated: false,
        fullOutputRef: null,
      },
    });
    // Digest must stay bound to journalReceipt+child (not providerResult mirror alone).
    const recomputed = createHash("sha256")
      .update(JSON.stringify({
        journalReceipt: fixture.journalReceipt,
        child: fixture.child,
      }))
      .digest("hex")
      .slice(0, 32);
    expect(emitted.semanticDigest).toBe(recomputed);
  });

  it("keeps malformed fixtures structurally invalid for the consumer", () => {
    const malformed = readdirSync(FIXTURE_DIR)
      .filter((name) => name.startsWith("malformed-") && name.endsWith(".json"));
    expect(malformed.length).toBeGreaterThanOrEqual(4);
    for (const name of malformed) {
      const payload = JSON.parse(readFileSync(join(FIXTURE_DIR, name), "utf8")) as Record<string, unknown>;
      if (name === "malformed-ok-false.json") {
        expect(payload.ok).toBe(false);
      } else if (name === "malformed-wrong-schema-version.json") {
        expect(payload.schemaVersion).not.toBe(1);
      } else if (name === "malformed-missing-child.json") {
        expect(payload.child).toBeUndefined();
      } else if (name === "malformed-digest-mismatch.json") {
        expect(payload.semanticDigest).not.toBe(
          (payload.providerResult as { semanticDigest?: string }).semanticDigest,
        );
      } else if (name === "malformed-tampered-turn-id.json") {
        expect((payload.journalReceipt as { userTurnId?: string }).userTurnId).toBe("turn_tampered");
      } else {
        expect(payload).toBeTruthy();
      }
    }
  });
});
