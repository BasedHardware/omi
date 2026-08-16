import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { adapterProfile } from "../src/runtime/adapter-selection.js";
import { recordJournalExchange, listJournalTurns } from "../src/runtime/conversation-journal.js";
import { evaluateDesktopToolPolicy } from "../src/runtime/desktop-tool-policy.js";
import { routeExternalSurfaceTool } from "../src/runtime/external-surface-tool-policy.js";
import { omiToolManifest } from "../src/runtime/omi-tool-manifest.js";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";
import { resolveSurfaceSession } from "../src/runtime/surface-session.js";
import { routePromptForPublicWeb } from "../src/adapters/pi-mono.js";

describe("cross-surface contract smoke", () => {
  let stateDir: string;
  let store: SqliteAgentStore;

  beforeEach(() => {
    stateDir = mkdtempSync(join(tmpdir(), "omi-cross-surface-contract-"));
    store = new SqliteAgentStore({ stateDir, reconcileOnOpen: false });
  });

  afterEach(() => {
    store.close();
    rmSync(stateDir, { recursive: true, force: true });
  });

  it("uses one owner/session/conversation and idempotent journal timeline for typed and PTT turns", () => {
    const main = resolveSurfaceSession(store, {
      ownerId: "owner-contract",
      surfaceRef: { surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "contract-chat" },
      defaultAdapterId: "pi-mono",
    }, () => 10);
    const voice = resolveSurfaceSession(store, {
      ownerId: "owner-contract",
      surfaceRef: { surfaceKind: "realtime_voice", externalRefKind: "chat", externalRefId: "contract-chat" },
      defaultAdapterId: "acp",
    }, () => 20);

    expect(voice).toEqual(main);

    const exchange = {
      ownerId: "owner-contract",
      conversationId: main.conversationId,
      turns: [
        {
          turnId: "turn:typed:1",
          producerId: "typed:1",
          role: "user" as const,
          surfaceKind: "main_chat",
          origin: "typed_chat" as const,
          status: "completed" as const,
          content: "Ask from the main chat",
          contentBlocks: [{ type: "text" as const, id: "typed:1:text", text: "Ask from the main chat" }],
          createdAtMs: 30,
        },
        {
          turnId: "turn:voice:1",
          producerId: "voice:1",
          role: "assistant" as const,
          surfaceKind: "realtime_voice",
          origin: "realtime_voice" as const,
          status: "completed" as const,
          content: "Answer from PTT in the same timeline",
          contentBlocks: [{ type: "text" as const, id: "voice:1:text", text: "Answer from PTT in the same timeline" }],
          createdAtMs: 31,
        },
      ],
    };

    expect(recordJournalExchange(store, exchange).createdTurns).toHaveLength(2);
    expect(recordJournalExchange(store, exchange).createdTurns).toHaveLength(0);
    expect(listJournalTurns(store, {
      ownerId: "owner-contract",
      conversationId: main.conversationId,
    }).turns.map((turn) => turn.turnId)).toEqual(["turn:typed:1", "turn:voice:1"]);
  });

  it("keeps permission, public-web, and provider capability decisions compatible across coordinator and PTT paths", () => {
    const permissionTool = omiToolManifest.find((tool) => tool.name === "request_permission");
    expect(permissionTool?.surfaces).toEqual(expect.arrayContaining(["desktop_chat", "realtime_voice"]));

    for (const surface of ["desktop_chat", "realtime_voice"]) {
      const decision = evaluateDesktopToolPolicy({
        toolName: "request_permission",
        selectedBundles: ["desktop.permissions.request"],
        operation: "request_permission",
        resourceRef: "permission:screen_recording",
        surface,
        nowMs: 1_000,
      });
      expect(decision.decision).toBe("dispatch_required");
      expect(decision.descriptor.approvalPolicy).toBe("user_approval");
      expect(decision.requiredBundles).toEqual(["desktop.permissions.request"]);
    }

    expect(routeExternalSurfaceTool({
      toolName: "spawn_agent",
      toolInput: { objective: "Request Omi screen share permission" },
      originatingPrompt: "Please request Omi screen share permission now",
    })).toMatchObject({
      action: "execute",
      toolName: "request_permission",
      toolInput: { type: "screen_recording" },
      recoveredFromDelegation: true,
    });
    expect(routeExternalSurfaceTool({
      toolName: "spawn_agent",
      toolInput: { objective: "Research the release notes and report back" },
      originatingPrompt: "Please use a background agent to research the release notes",
    })).toMatchObject({
      action: "execute",
      toolName: "spawn_agent",
      recoveredFromDelegation: false,
    });

    for (const query of [
      "what's the weather in NYC right now?",
      "what AI models were released this week?",
    ]) {
      expect(routePromptForPublicWeb(query)).toContain("<omi_retrieval_policy>");
    }
    expect(routePromptForPublicWeb("search my calendar for weather in NYC")).toBe(
      "search my calendar for weather in NYC",
    );

    expect(adapterProfile("pi-mono").capabilities.supportsTools).toBe(true);
    expect(adapterProfile("openclaw").capabilities).toMatchObject({
      supportsTools: false,
      supportsModelSwitching: false,
    });
  });
});
