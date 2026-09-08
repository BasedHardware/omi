import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { recordJournalTurn } from "../src/runtime/conversation-journal.js";
import { toolManifestEntry } from "../src/runtime/omi-tool-manifest.js";
import { RunToolCapabilityRejectedError } from "../src/runtime/run-tool-capability.js";
import { createKernelHarness, waitUntil } from "./kernel-fakes.js";

const roots: string[] = [];

afterEach(() => {
  while (roots.length) rmSync(roots.pop()!, { recursive: true, force: true });
});

describe("chat-first history search dispatch", () => {
  it("requires the enabled main-Chat run capability before the parent kernel searches its journal", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "acp");
    const resolved = kernel.resolveSurfaceSession({
      ownerId: "owner",
      surfaceRef: { surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "history-search" },
      defaultAdapterId: "acp",
      chatFirstCapability: { chatFirstUi: true, controlGeneration: 9 },
    });
    recordJournalTurn(store, {
      ownerId: "owner",
      conversationId: resolved.conversationId,
      turnId: "old-decision",
      role: "assistant",
      surfaceKind: "main_chat",
      origin: "typed_chat",
      status: "completed",
      content: "We agreed to keep the launch intentionally small.",
      contentBlocks: [],
      createdAtMs: 1_000,
    });
    // A single session can retain multiple legacy surface aliases.  The
    // capability's external chat reference, not whichever alias was touched
    // most recently, must select the searchable transcript.
    store.insertSurfaceConversation({
      ownerId: "owner",
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "other-history-alias",
      conversationId: "other-history-conversation",
      agentSessionId: resolved.agentSessionId,
      createdAtMs: 2_000,
      lastActiveAtMs: 2_000,
    });
    recordJournalTurn(store, {
      ownerId: "owner",
      conversationId: "other-history-conversation",
      turnId: "other-decision",
      role: "assistant",
      surfaceKind: "main_chat",
      origin: "typed_chat",
      status: "completed",
      content: "A different alias must never replace the caller's transcript.",
      contentBlocks: [],
      createdAtMs: 2_001,
    });

    adapter.deferResult();
    const runPromise = kernel.executeRun({
      ownerId: "owner",
      sessionId: resolved.agentSessionId,
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "history-search",
      defaultAdapterId: "acp",
      adapterId: "acp",
      clientId: "history-client",
      requestId: "history-request",
      prompt: "What did we decide before?",
      cwd: "/tmp/history-search",
      admittedContextSnapshot: kernel.contextSnapshot(resolved.agentSessionId, "owner", "main_chat"),
    });
    await waitUntil(() => adapter.executed.length === 1);
    const capabilityRef = adapter.executed[0]!.toolCapabilityRef;

    expectCapabilityCode(() => kernel.authorizeRelayedRunToolInvocation({
      capabilityRef,
      invocationId: "history-off-manifest",
      toolName: "search_chat_history",
      toolInput: { query: "launch intentionally" },
      activeOwnerId: "different-owner",
    }), "owner_mismatch");
    expect(Number(store.getRow("SELECT COUNT(*) AS count FROM tool_invocation_ledger").count)).toBe(0);

    const authorized = kernel.authorizeRelayedRunToolInvocation({
      capabilityRef,
      invocationId: "history-authorized",
      toolName: "search_chat_history",
      toolInput: { query: "launch intentionally" },
      activeOwnerId: "owner",
    });
    expect(authorized).toMatchObject({
      canonicalToolName: "search_chat_history",
      surfaceKind: "main_chat",
      chatFirstUi: true,
      chatFirstControlGeneration: 9,
    });

    kernel.markRunToolInvocationDispatched(authorized);
    const result = kernel.searchAuthorizedChatHistory({
      invocation: authorized,
      toolInput: { query: "launch intentionally" },
      activeOwnerId: () => "owner",
    });
    expect(result).toEqual({
      matches: [{
        timestamp: new Date(1_000).toISOString(),
        role: "assistant",
        excerpt: "We agreed to keep the launch intentionally small.",
      }],
    });
    kernel.completeRunToolInvocation({
      invocationId: authorized.invocationId,
      ownerId: authorized.ownerId,
      sessionId: authorized.sessionId,
      runId: authorized.runId,
      attemptId: authorized.attemptId,
      profileGeneration: authorized.profileGeneration,
      manifestVersion: authorized.manifestVersion,
      manifestDigest: authorized.manifestDigest,
      daemonBootEpoch: authorized.daemonBootEpoch,
      executionGeneration: authorized.executionGeneration,
      inputHash: authorized.inputHash,
      capabilityRef: authorized.capabilityRef,
      activeOwnerId: "owner",
      outcome: "succeeded",
      result: JSON.stringify(result),
    });
    adapter.resolveDeferred();
    await runPromise;
    store.close();
  });

  it("cannot authorize history search for the legacy capability-off manifest", async () => {
    const { store, adapter, kernel } = createKernelHarness(newDatabasePath(), "acp");
    const resolved = kernel.resolveSurfaceSession({
      ownerId: "owner",
      surfaceRef: { surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "legacy-history" },
      defaultAdapterId: "acp",
      chatFirstCapability: { chatFirstUi: false, controlGeneration: 9 },
    });
    adapter.deferResult();
    const runPromise = kernel.executeRun({
      ownerId: "owner",
      sessionId: resolved.agentSessionId,
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "legacy-history",
      defaultAdapterId: "acp",
      adapterId: "acp",
      clientId: "legacy-history-client",
      requestId: "legacy-history-request",
      prompt: "Can you look up an older choice?",
      cwd: "/tmp/legacy-history-search",
      admittedContextSnapshot: kernel.contextSnapshot(resolved.agentSessionId, "owner", "main_chat"),
    });
    await waitUntil(() => adapter.executed.length === 1);
    expectCapabilityCode(() => kernel.authorizeRelayedRunToolInvocation({
      capabilityRef: adapter.executed[0]!.toolCapabilityRef,
      invocationId: "legacy-history-attempt",
      toolName: "search_chat_history",
      toolInput: { query: "older choice" },
      activeOwnerId: "owner",
    }), "tool_not_allowed");
    expect(toolManifestEntry("search_chat_history")?.executor.kind).toBe("nodeTool");
    adapter.resolveDeferred();
    await runPromise;
    store.close();
  });
});

function expectCapabilityCode(work: () => unknown, code: string): void {
  try {
    work();
    throw new Error("Expected a run-tool capability rejection");
  } catch (error) {
    expect(error).toBeInstanceOf(RunToolCapabilityRejectedError);
    expect((error as RunToolCapabilityRejectedError).code).toBe(code);
  }
}

function newDatabasePath(): string {
  const root = mkdtempSync(join(tmpdir(), "omi-chat-history-search-"));
  roots.push(root);
  return join(root, "agent.sqlite");
}
