import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { mcpToolDefinitionsForAdapter } from "../src/runtime/omi-tool-manifest.js";
import { RunToolCapabilityRejectedError } from "../src/runtime/run-tool-capability.js";
import { createKernelHarness, waitUntil } from "./kernel-fakes.js";

const roots: string[] = [];
const CHAT_FIRST_DYNAMIC_TOOLS = ["render_chat_blocks", "search_chat_history"] as const;

afterEach(() => {
  while (roots.length) rmSync(roots.pop()!, { recursive: true, force: true });
});

describe("chat-first admitted capability projection", () => {
  it("preserves the enabled main-Chat generation through run admission for both dynamic tools", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "acp");
    const resolved = kernel.resolveSurfaceSession({
      ownerId: "owner",
      surfaceRef: { surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "chat-first-main" },
      defaultAdapterId: "acp",
      chatFirstCapability: { chatFirstUi: true, controlGeneration: 19 },
    });
    const admittedContextSnapshot = kernel.contextSnapshot(resolved.agentSessionId, "owner", "main_chat");
    expect(admittedContextSnapshot.capabilities).toMatchObject({
      chatFirstUi: true,
      chatFirstControlGeneration: 19,
    });
    expect(kernel.hasChatFirstMainCapability("owner")).toBe(true);
    expect(kernel.hasChatFirstMainCapability("other-owner")).toBe(false);

    adapter.deferResult();
    const runPromise = kernel.executeRun({
      ownerId: "owner",
      sessionId: resolved.agentSessionId,
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "chat-first-main",
      defaultAdapterId: "acp",
      adapterId: "acp",
      clientId: "chat-first-client",
      requestId: "chat-first-request",
      prompt: "Use a rich Chat card.",
      cwd: "/tmp/chat-first-projection",
      admittedContextSnapshot,
    });
    await waitUntil(() => adapter.executed.length === 1);

    const capabilityRef = adapter.executed[0]!.toolCapabilityRef;
    for (const toolName of CHAT_FIRST_DYNAMIC_TOOLS) {
      const authorized = kernel.authorizeRelayedRunToolInvocation({
        capabilityRef,
        invocationId: `enabled-${toolName}`,
        toolName,
        toolInput: {},
        activeOwnerId: "owner",
      });
      expect(authorized).toMatchObject({
        canonicalToolName: toolName,
        surfaceKind: "main_chat",
        chatFirstUi: true,
        chatFirstControlGeneration: 19,
      });
    }

    adapter.resolveDeferred();
    await runPromise;
    store.close();
  });

  it.each([
    ["capability-off main Chat", "main_chat", { chatFirstUi: false, controlGeneration: 19 }],
    ["enabled non-main surface", "floating_chat", { chatFirstUi: true, controlGeneration: 19 }],
  ] as const)("keeps dynamic tools absent and un-authorizable for %s", async (_label, surfaceKind, capability) => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "acp");
    const resolved = kernel.resolveSurfaceSession({
      ownerId: "owner",
      surfaceRef: { surfaceKind, externalRefKind: "chat", externalRefId: `projection-${surfaceKind}` },
      defaultAdapterId: "acp",
      chatFirstCapability: capability,
    });
    const admittedContextSnapshot = kernel.contextSnapshot(resolved.agentSessionId, "owner", surfaceKind);
    expect(admittedContextSnapshot.capabilities).toMatchObject({
      chatFirstUi: false,
      chatFirstControlGeneration: null,
    });
    expect(kernel.hasChatFirstMainCapability("owner")).toBe(false);
    expect(admittedContextSnapshot.capabilities.allowedToolNames).not.toEqual(
      expect.arrayContaining(CHAT_FIRST_DYNAMIC_TOOLS),
    );

    adapter.deferResult();
    const runPromise = kernel.executeRun({
      ownerId: "owner",
      sessionId: resolved.agentSessionId,
      surfaceKind,
      externalRefKind: "chat",
      externalRefId: `projection-${surfaceKind}`,
      defaultAdapterId: "acp",
      adapterId: "acp",
      clientId: `projection-client-${surfaceKind}`,
      requestId: `projection-request-${surfaceKind}`,
      prompt: "Use a rich Chat card.",
      cwd: "/tmp/chat-first-projection",
      admittedContextSnapshot,
    });
    await waitUntil(() => adapter.executed.length === 1);

    for (const toolName of CHAT_FIRST_DYNAMIC_TOOLS) {
      expectToolNotAllowed(() => kernel.authorizeRelayedRunToolInvocation({
        capabilityRef: adapter.executed[0]!.toolCapabilityRef,
        invocationId: `${surfaceKind}-${toolName}`,
        toolName,
        toolInput: {},
        activeOwnerId: "owner",
      }));
    }

    adapter.resolveDeferred();
    await runPromise;
    store.close();
  });

  it("keeps capability-off and non-main MCP tools/list bytes equal to the legacy projection", () => {
    const legacy = JSON.stringify(mcpToolDefinitionsForAdapter("omi-tools-stdio"));
    for (const projection of [
      { surfaceKind: "main_chat", chatFirstUi: false, controlGeneration: 19 },
      { surfaceKind: "floating_chat", chatFirstUi: true, controlGeneration: 19 },
    ]) {
      expect(JSON.stringify(mcpToolDefinitionsForAdapter("omi-tools-stdio", projection))).toBe(legacy);
    }
  });
});

function expectToolNotAllowed(work: () => unknown): void {
  try {
    work();
    throw new Error("Expected a run-tool capability rejection");
  } catch (error) {
    expect(error).toBeInstanceOf(RunToolCapabilityRejectedError);
    expect((error as RunToolCapabilityRejectedError).code).toBe("tool_not_allowed");
  }
}

function newDatabasePath(): string {
  const root = mkdtempSync(join(tmpdir(), "omi-chat-first-projection-"));
  roots.push(root);
  return join(root, "agent.sqlite");
}
