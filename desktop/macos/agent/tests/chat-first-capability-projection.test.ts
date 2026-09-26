import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { mcpToolDefinitionsForAdapter } from "../src/runtime/omi-tool-manifest.js";
import { RunToolCapabilityRejectedError } from "../src/runtime/run-tool-capability.js";
import { createKernelHarness, waitUntil } from "./kernel-fakes.js";

const roots: string[] = [];
const CHAT_FIRST_DYNAMIC_TOOLS = [
  "render_chat_blocks",
  "search_chat_history",
  "show_rewind_evidence",
] as const;

afterEach(() => {
  while (roots.length) rmSync(roots.pop()!, { recursive: true, force: true });
});

describe("chat-first admitted capability projection", () => {
  it("forwards the enabled projection when opening and resuming an adapter binding", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "acp");
    const resolved = kernel.resolveSurfaceSession({
      ownerId: "owner",
      surfaceRef: { surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "binding-projection" },
      defaultAdapterId: "acp",
      chatFirstCapability: { chatFirstUi: true, controlGeneration: 23 },
    });
    const admittedContextSnapshot = kernel.contextSnapshot(resolved.agentSessionId, "owner", "main_chat");
    const runInput = {
      ownerId: "owner",
      sessionId: resolved.agentSessionId,
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "binding-projection",
      defaultAdapterId: "acp",
      adapterId: "acp",
      clientId: "binding-client",
      prompt: "Use a rich Chat card.",
      cwd: "/tmp/chat-first-binding-projection",
      admittedContextSnapshot,
    } as const;

    await kernel.executeRun({ ...runInput, requestId: "binding-request-1" });
    await kernel.executeRun({ ...runInput, requestId: "binding-request-2" });

    const expected = {
      surfaceKind: "main_chat",
      chatFirstUi: true,
      chatFirstControlGeneration: 23,
    };
    expect(adapter.opened[0]?.metadata).toMatchObject(expected);
    expect(adapter.resumed[0]?.metadata).toMatchObject(expected);
    store.close();
  });

  /// The desktop never sends `admittedContextSnapshot` — it is an internal
  /// kernel field, absent from the wire protocol — so every real Main Chat run
  /// takes the branch that builds its own snapshot. That branch dropped the
  /// capability, and the adapter metadata is derived from that snapshot, so the
  /// spawned model was offered the 41 base tools and never `render_chat_blocks`.
  /// Every existing test here passed a snapshot in by hand and so never
  /// exercised the path the product uses.
  it("projects the capability onto a run that arrives without a context snapshot", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "acp");
    const resolved = kernel.resolveSurfaceSession({
      ownerId: "owner",
      surfaceRef: { surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "no-snapshot" },
      defaultAdapterId: "acp",
      chatFirstCapability: { chatFirstUi: true, controlGeneration: 7 },
    });

    await kernel.executeRun({
      ownerId: "owner",
      sessionId: resolved.agentSessionId,
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "no-snapshot",
      defaultAdapterId: "acp",
      adapterId: "acp",
      clientId: "no-snapshot-client",
      prompt: "Show me three open tasks I could pick up right now.",
      cwd: "/tmp/chat-first-no-snapshot",
      requestId: "no-snapshot-request-1",
    });

    expect(adapter.opened[0]?.metadata).toMatchObject({
      surfaceKind: "main_chat",
      chatFirstUi: true,
      chatFirstControlGeneration: 7,
    });
    store.close();
  });

  /// One shell: main Chat and the floating bar project the same conversation,
  /// so the session row can carry `floating_chat` while a main-Chat run executes
  /// on it. Every chat-first gate admits `main_chat` only, so the adapter has to
  /// be told the run's surface, not the session's registration.
  it("stamps the run surface on a session the floating bar registered first", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "acp");
    const resolved = kernel.resolveSurfaceSession({
      ownerId: "owner",
      surfaceRef: { surfaceKind: "floating_chat", externalRefKind: "chat", externalRefId: "shared-shell" },
      defaultAdapterId: "acp",
    });
    kernel.resolveSurfaceSession({
      ownerId: "owner",
      surfaceRef: { surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "shared-shell" },
      defaultAdapterId: "acp",
      chatFirstCapability: { chatFirstUi: true, controlGeneration: 0 },
    });

    await kernel.executeRun({
      ownerId: "owner",
      sessionId: resolved.agentSessionId,
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "shared-shell",
      defaultAdapterId: "acp",
      adapterId: "acp",
      clientId: "shared-shell-client",
      prompt: "List three of my open tasks.",
      cwd: "/tmp/chat-first-shared-shell",
      requestId: "shared-shell-request-1",
    });

    expect(adapter.opened[0]?.metadata).toMatchObject({ surfaceKind: "main_chat" });
    store.close();
  });

  /// The tool being advertised is not the same as the tool being allowed. The
  /// broker re-checks the surface when the model actually calls it, and it read
  /// the session's registration rather than the run's surface — so a shared
  /// shell offered `render_chat_blocks` and then answered
  /// `tool_not_allowed: Tool is unavailable for this run execution profile`.
  it("allows the chat-first tools on a main-Chat run of a floating-registered session", async () => {
    const { store, kernel } = createKernelHarness(newDatabasePath(), "acp");
    const resolved = kernel.resolveSurfaceSession({
      ownerId: "owner",
      surfaceRef: { surfaceKind: "floating_chat", externalRefKind: "chat", externalRefId: "shared-allow" },
      defaultAdapterId: "acp",
    });
    kernel.resolveSurfaceSession({
      ownerId: "owner",
      surfaceRef: { surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "shared-allow" },
      defaultAdapterId: "acp",
      chatFirstCapability: { chatFirstUi: true, controlGeneration: 0 },
    });

    await kernel.executeRun({
      ownerId: "owner",
      sessionId: resolved.agentSessionId,
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "shared-allow",
      defaultAdapterId: "acp",
      adapterId: "acp",
      clientId: "shared-allow-client",
      prompt: "Render my tasks as cards.",
      cwd: "/tmp/chat-first-shared-allow",
      requestId: "shared-allow-request-1",
    });

    const runRow = store.getRow(
      "SELECT input_json FROM runs WHERE session_id = ? ORDER BY rowid DESC LIMIT 1",
      [resolved.agentSessionId],
    );
    const runInput = JSON.parse(String(runRow.input_json));
    expect(runInput.surfaceKind).toBe("main_chat");
    expect(runInput.admittedContextSnapshot.capabilities.allowedToolNames).toContain("render_chat_blocks");
    store.close();
  });

  it("leaves a run capability-off when the shell never sampled one", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "acp");
    const resolved = kernel.resolveSurfaceSession({
      ownerId: "owner",
      surfaceRef: { surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "unsampled" },
      defaultAdapterId: "acp",
    });

    await kernel.executeRun({
      ownerId: "owner",
      sessionId: resolved.agentSessionId,
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "unsampled",
      defaultAdapterId: "acp",
      adapterId: "acp",
      clientId: "unsampled-client",
      prompt: "Anything.",
      cwd: "/tmp/chat-first-unsampled",
      requestId: "unsampled-request-1",
    });

    expect(adapter.opened[0]?.metadata).toMatchObject({
      surfaceKind: "main_chat",
      chatFirstUi: false,
      chatFirstControlGeneration: null,
    });
    store.close();
  });

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

  it("leaves chat block payloads open for the backend's authoritative validator", () => {
    const projected = mcpToolDefinitionsForAdapter("omi-tools-stdio", {
      surfaceKind: "main_chat",
      chatFirstUi: true,
      controlGeneration: 19,
    });
    const render = projected.find((tool) => tool.name === "render_chat_blocks");
    expect(render?.inputSchema.properties?.blocks?.items).toMatchObject({
      type: "object",
      additionalProperties: true,
    });
  });

  it("adds canonical goal retrieval only to the enabled main-chat projection", () => {
    const enabled = mcpToolDefinitionsForAdapter("omi-tools-stdio", {
      surfaceKind: "main_chat", chatFirstUi: true, controlGeneration: 19,
    });
    expect(enabled.find((tool) => tool.name === "get_canonical_goals")?.description).toContain(
      "Do not use execute_sql, legacy local goals, memories, or inferred goals",
    );
    expect(JSON.stringify(mcpToolDefinitionsForAdapter("omi-tools-stdio"))).not.toContain("get_canonical_goals");
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
