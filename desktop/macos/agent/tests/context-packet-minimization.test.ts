import { describe, expect, it } from "vitest";
import { buildDesktopContextPacket } from "../src/runtime/desktop-context-packet.js";

describe("desktop context packet builder", () => {
  it("allocates unique occurrence ids for simultaneous identical packets", () => {
    const input = {
      ownerId: "owner-a",
      surfaceKind: "task_chat",
      objective: "same objective",
      snippets: [],
      retentionClass: "ephemeral" as const,
      ttlMs: 60_000,
      nowMs: 1_700_000_000_000,
    };

    expect(buildDesktopContextPacket(input).packet.packetId)
      .not.toBe(buildDesktopContextPacket(input).packet.packetId);
  });

  it("builds a minimized packet with hash, TTL, redacted preview, and access logs", () => {
    const result = buildDesktopContextPacket({
      ownerId: "owner-1",
      sessionId: "session-1",
      runId: "run-1",
      surfaceKind: "task_chat",
      objective: "Finish the visible task",
      retentionClass: "ephemeral",
      ttlMs: 60_000,
      nowMs: 10_000,
      selectedToolBundles: ["desktop.context.local_read"],
      snippets: [
        {
          snippetId: "selected-chat",
          sourceKind: "task_chat",
          operation: "selected_snippet",
          provenance: { taskId: "task-1", range: "last_user_turn" },
          content: "User asked to finish the task.",
          redactedContent: "User asked to finish the task.",
          sensitivityTier: "low",
        },
        {
          snippetId: "full-transcript",
          sourceKind: "chat_surface",
          operation: "full_transcript",
          provenance: { messageCount: 200 },
          content: "THIS FULL TRANSCRIPT SHOULD NOT APPEAR",
          redactedContent: "redacted transcript",
          sensitivityTier: "sensitive",
          selected: false,
        },
      ],
    });

    expect(result.packet.expiresAtMs).toBe(70_000);
    expect(result.packet.contextHash).toMatch(/^sha256:/);
    expect(result.packet.tokenEstimate).toBeGreaterThan(0);
    expect(result.packet.retentionClass).toBe("ephemeral");
    expect(result.packet.redactedPreviewJson).toMatchObject({
      objective: "Finish the visible task",
      snippets: [{ snippetId: "selected-chat", preview: "User asked to finish the task." }],
    });
    expect(JSON.stringify(result.packet.packetJson)).toContain("User asked to finish the task.");
    expect(JSON.stringify(result.packet.packetJson)).not.toContain("THIS FULL TRANSCRIPT SHOULD NOT APPEAR");
    expect(result.accessLogs).toHaveLength(1);
    expect(result.accessLogs[0]).toMatchObject({
      ownerId: "owner-1",
      packetId: result.packet.packetId,
      runId: "run-1",
      sourceKind: "task_chat",
      policyDecision: "allowed",
    });
  });

  it("rejects missing TTL", () => {
    expect(() =>
      buildDesktopContextPacket({
        ownerId: "owner-1",
        surfaceKind: "main_chat",
        objective: "No TTL",
        retentionClass: "ephemeral",
        snippets: [],
      }),
    ).toThrow(/TTL/);
  });

  it("rejects raw screenshot image bytes", () => {
    expect(() =>
      buildDesktopContextPacket({
        ownerId: "owner-1",
        surfaceKind: "main_chat",
        objective: "Inspect screen",
        retentionClass: "ephemeral",
        ttlMs: 60_000,
        snippets: [
          {
            snippetId: "screenshot",
            sourceKind: "screenshot_image",
            operation: "get_screenshot",
            provenance: { screenshotId: 42 },
            content: `data:image/jpeg;base64,${"a".repeat(500)}`,
            sensitivityTier: "sensitive",
          },
        ],
      }),
    ).toThrow(/screenshot image bytes/);
  });

  it("rejects caller-labeled allowed sensitive screen snippets", () => {
    expect(() =>
      buildDesktopContextPacket({
        ownerId: "owner-1",
        surfaceKind: "main_chat",
        objective: "Inspect screen metadata",
        retentionClass: "ephemeral",
        ttlMs: 60_000,
        snippets: [
          {
            snippetId: "screen",
            sourceKind: "screen_current",
            operation: "get_work_context",
            provenance: { app: "Browser" },
            content: "Visible page title",
            redactedContent: "Visible page title",
            sensitivityTier: "sensitive",
            policyDecision: "allowed",
          },
        ],
      }),
    ).toThrow(/requires a verified dispatch/);
  });

  it("allows sensitive screen snippets only with a dispatch reference", () => {
    const result = buildDesktopContextPacket({
      ownerId: "owner-1",
      surfaceKind: "main_chat",
      objective: "Inspect screen metadata",
      retentionClass: "ephemeral",
      ttlMs: 60_000,
      snippets: [
        {
          snippetId: "screen",
          sourceKind: "screen_current",
          operation: "get_work_context",
          provenance: { app: "Browser" },
          content: "Visible page title",
          redactedContent: "Visible page title",
          sensitivityTier: "sensitive",
          policyDecision: "dispatch_created",
          dispatchId: "dispatch-1",
        },
      ],
    });

    expect(result.accessLogs[0]).toMatchObject({
      sourceKind: "screen_current",
      policyDecision: "dispatch_created",
      dispatchId: "dispatch-1",
    });
  });

  it("uses deterministic context hashes for equivalent packet content", () => {
    const base = {
      ownerId: "owner-1",
      surfaceKind: "main_chat",
      objective: "Summarize task",
      retentionClass: "debug" as const,
      ttlMs: 60_000,
      nowMs: 1_000,
      snippets: [
        {
          snippetId: "task",
          sourceKind: "omi_db" as const,
          operation: "selected_task",
          provenance: { taskId: "task-1" },
          content: "Task summary",
          sensitivityTier: "low",
        },
      ],
    };

    expect(buildDesktopContextPacket(base).packet.contextHash).toBe(buildDesktopContextPacket(base).packet.contextHash);
  });
});
