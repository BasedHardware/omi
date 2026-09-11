import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { conversationOperationReceipts } from "../src/runtime/conversation-operations.js";
import { clearJournalConversation } from "../src/runtime/conversation-journal.js";
import { buildContextSnapshot } from "../src/runtime/context-snapshot.js";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";
import { resolveSurfaceSession } from "../src/runtime/surface-session.js";
import {
  completeToolInvocation,
  markToolInvocationDispatched,
  prepareToolInvocation,
} from "../src/runtime/tool-invocation-ledger.js";

const roots: string[] = [];
afterEach(() => {
  while (roots.length) rmSync(roots.pop()!, { recursive: true, force: true });
});

function fixture() {
  const root = mkdtempSync(join(tmpdir(), "omi-operation-context-"));
  roots.push(root);
  const databasePath = join(root, "agent.sqlite");
  const store = new SqliteAgentStore({ databasePath, reconcileOnOpen: false });
  const surface = resolveSurfaceSession(store, {
    ownerId: "owner",
    surfaceRef: { surfaceKind: "main_chat", externalRefKind: "chat", externalRefId: "shared" },
    defaultAdapterId: "acp",
  }, () => 1);
  let sequence = 0;
  function prepare(options: { conversationId?: string; conversationGeneration?: number; readOnly?: boolean; nowMs?: number } = {}) {
    sequence += 1;
    const run = store.insertRun({
      sessionId: surface.agentSessionId,
      clientId: "client",
      requestId: `request-${sequence}`,
      status: "running",
      mode: "act",
      inputJson: JSON.stringify({
        admittedContextSnapshot: {
          conversationId: options.conversationId ?? surface.conversationId,
          conversationGeneration: options.conversationGeneration,
        },
      }),
    });
    const attempt = store.insertAttempt({
      runId: run.runId, attemptNo: 1, status: "running", adapterId: "acp", adapterInstanceId: "worker",
    });
    return prepareToolInvocation(store, {
      invocationId: `invocation-${sequence}`, ownerId: "owner", sessionId: surface.agentSessionId,
      runId: run.runId, attemptId: attempt.attemptId, profileGeneration: 1,
      manifestVersion: 1, manifestDigest: "manifest", daemonBootEpoch: "boot",
      executionGeneration: 1, inputHash: "sensitive-input-hash",
      toolName: options.readOnly ? "read_conversation_evidence" : "create_memory",
      effectClass: options.readOnly ? "read_only" : "non_idempotent_write",
      retryPolicy: options.readOnly ? "safe_retry" : "never_auto_retry",
      nowMs: options.nowMs ?? 100,
    });
  }
  return { databasePath, store, surface, prepare };
}

describe("conversation operation context", () => {
  it("reflects authoritative operation transitions without leaking inputs or results", () => {
    const { store, surface, prepare } = fixture();
    const identity = prepare();
    const input = { ownerId: "owner", conversationId: surface.conversationId };
    expect(conversationOperationReceipts(store, input)[0]?.status).toBe("prepared");
    markToolInvocationDispatched(store, identity, 101);
    expect(conversationOperationReceipts(store, input)[0]?.status).toBe("dispatched");
    completeToolInvocation(store, { ...identity, outcome: "succeeded", result: "private saved content", nowMs: 102 });
    const receipts = conversationOperationReceipts(store, input);
    expect(receipts[0]).toMatchObject({ status: "succeeded", retryPolicy: "never_auto_retry", updatedAtMs: 102 });
    expect(JSON.stringify(receipts)).not.toMatch(/private|sensitive|inputHash|resultHash/);
    store.close();
  });

  it("reconstructs unknown dispatched writes after process restart rather than claiming success", () => {
    const { databasePath, store, surface, prepare } = fixture();
    markToolInvocationDispatched(store, prepare(), 101);
    store.close();
    const restarted = new SqliteAgentStore({ databasePath });
    expect(conversationOperationReceipts(restarted, { ownerId: "owner", conversationId: surface.conversationId }))
      .toMatchObject([{ status: "outcome_unknown", retryPolicy: "never_auto_retry" }]);
    restarted.close();
  });

  it("isolates owners and exact conversations even when a session has multiple aliases", () => {
    const { store, surface, prepare } = fixture();
    prepare();
    prepare({ conversationId: "another-conversation" });
    prepare({ readOnly: true });
    expect(conversationOperationReceipts(store, { ownerId: "owner", conversationId: surface.conversationId })).toHaveLength(1);
    expect(() => conversationOperationReceipts(store, { ownerId: "other-owner", conversationId: surface.conversationId }))
      .toThrow(/owned conversation/);
    store.close();
  });

  it("bounds the projection and excludes work admitted before the conversation was cleared", () => {
    const { store, surface, prepare } = fixture();
    for (let index = 0; index < 15; index += 1) prepare({ nowMs: 100 + index });
    const input = { ownerId: "owner", conversationId: surface.conversationId };
    expect(conversationOperationReceipts(store, input)).toHaveLength(12);
    clearJournalConversation(store, { ...input, expectedGeneration: 1, nowMs: 111, deleteBackend: false });
    expect(conversationOperationReceipts(store, input)).toHaveLength(3);
    store.close();
  });

  it("fences a clear by admitted generation even when writes share its millisecond", () => {
    const { store, surface, prepare } = fixture();
    const input = { ownerId: "owner", conversationId: surface.conversationId };
    const before = buildContextSnapshot(store, surface.agentSessionId, "owner", 100);
    prepare({ conversationGeneration: before.conversationGeneration, nowMs: 100 });
    clearJournalConversation(store, { ...input, expectedGeneration: 1, nowMs: 100, deleteBackend: false });
    const after = buildContextSnapshot(store, surface.agentSessionId, "owner", 100);
    const current = prepare({ conversationGeneration: after.conversationGeneration, nowMs: 100 });
    expect(after.conversationGeneration).toBe(2);
    expect(after.version).not.toBe(before.version);
    expect(conversationOperationReceipts(store, input).map((receipt) => receipt.invocationId))
      .toEqual([current.invocationId]);
    store.close();
  });
});
