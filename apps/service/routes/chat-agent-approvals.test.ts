import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";

import { createInMemoryLocalServiceStores, createLocalDevService } from "../app-facing";
import { DEV_NOOP_SCANNER_ID } from "../chat/attachment-scanner";
import type { ChatMessageRecord } from "../stores/chat-messages-store";

const pdf = (): Uint8Array => new Uint8Array([
  0x25, 0x50, 0x44, 0x46, 0x2d, 0x31, 0x2e, 0x37, 0x0a,
]);

const admitGeneration = (
  stores: ReturnType<typeof createInMemoryLocalServiceStores>,
  accountId: string,
  generationId: string,
  messageId: string,
): void => {
  const message: ChatMessageRecord = Object.freeze({
    id: messageId,
    text: "approval proof",
    sender: "human",
    type: "text",
    createdAt: 1,
    updatedAt: 1,
    chatSessionId: null,
    appId: null,
    journalRevision: 1,
    payloadHash: "sha256:approval-proof",
    messageSource: "desktop_chat",
    rating: null,
    reported: false,
    revision: "revision-approval",
    attachments: [],
  });
  const outcome = stores.chatMessages.admitHuman(accountId, message, generationId);
  if (outcome.kind !== "created") throw new TypeError("approval fixture did not admit");
};

describe("chat agent approval route", () => {
  test("resolveApproval route completes durable safe.write after reload", async () => {
    const db = new Database(":memory:");
    const stores = createInMemoryLocalServiceStores();
    const local = createLocalDevService({
      db,
      stores,
      ownerAccountId: "approval-owner",
      memoryCount: 0,
      accountTimezone: "UTC",
      devSecretLabel: "agent-approval-route-proof",
    });
    const runId = "generation-approval-route";
    const attemptId = `${runId}:attempt:1`;
    admitGeneration(stores, "approval-owner", runId, "message-approval");

    const pending = await local.writePath.agentApprovalCoordinator.request({
      runId,
      attemptId,
      call: {
        callId: "call:write",
        toolName: "safe.write",
        idempotencyKey: "idem:write",
        input: {},
      },
    });
    expect(pending).toMatchObject({
      kind: "pending_approval",
      approvalId: "approval:call:write",
    });

    const snapshot = local.writePath.agentApprovalCoordinator.snapshot();
    const reloadedDb = new Database(":memory:");
    const reloadedStores = createInMemoryLocalServiceStores();
    const reloaded = createLocalDevService({
      db: reloadedDb,
      stores: reloadedStores,
      ownerAccountId: "approval-owner",
      memoryCount: 0,
      accountTimezone: "UTC",
      devSecretLabel: "agent-approval-route-reload",
    });
    admitGeneration(reloadedStores, "approval-owner", runId, "message-approval");
    reloaded.writePath.agentApprovalCoordinator.restore(snapshot);

    const response = await reloaded.app.request(`/v1/chat-generations/${runId}/agent-approvals`, {
      method: "POST",
      headers: {
        authorization: `Bearer ${reloaded.devToken}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({
        approvalId: "approval:call:write",
        resolution: "approved",
      }),
    });
    expect(response.status).toBe(200);
    const body = await response.json() as { outcome: { kind: string; summary?: string } };
    expect(body.outcome).toMatchObject({ kind: "completed", summary: "Scoped write recorded." });
    reloadedDb.close();
    db.close();
  });

  test("resolution without approvalId uses the pending approval for that generation", async () => {
    const db = new Database(":memory:");
    const stores = createInMemoryLocalServiceStores();
    const local = createLocalDevService({
      db,
      stores,
      ownerAccountId: "approval-owner",
      memoryCount: 0,
      accountTimezone: "UTC",
      devSecretLabel: "agent-approval-route-pending",
    });
    const runId = "generation-approval-pending";
    admitGeneration(stores, "approval-owner", runId, "message-approval-pending");
    await local.writePath.agentApprovalCoordinator.request({
      runId,
      attemptId: `${runId}:attempt:1`,
      call: {
        callId: "call:write-pending",
        toolName: "safe.write",
        idempotencyKey: "idem:write-pending",
        input: { note: "pending note" },
      },
    });
    const response = await local.app.request(`/v1/chat-generations/${runId}/agent-approvals`, {
      method: "POST",
      headers: {
        authorization: `Bearer ${local.devToken}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({ resolution: "approved" }),
    });
    expect(response.status).toBe(200);
    const body = await response.json() as { outcome: { kind: string; summary?: string } };
    expect(body.outcome).toMatchObject({ kind: "completed", summary: "Scoped write recorded." });
    db.close();
  });

  test("deny and cancel return 202 without executing safe.write", async () => {
    for (const resolution of ["denied", "cancelled"] as const) {
      const db = new Database(":memory:");
      const stores = createInMemoryLocalServiceStores();
      const local = createLocalDevService({
        db,
        stores,
        ownerAccountId: "approval-owner",
        memoryCount: 0,
        accountTimezone: "UTC",
        devSecretLabel: `agent-approval-route-${resolution}`,
      });
      const runId = `generation-${resolution}`;
      admitGeneration(stores, "approval-owner", runId, `message-${resolution}`);
      await local.writePath.agentApprovalCoordinator.request({
        runId,
        attemptId: `${runId}:attempt:1`,
        call: {
          callId: `call:${resolution}`,
          toolName: "safe.write",
          idempotencyKey: `idem:${resolution}`,
          input: {},
        },
      });
      const response = await local.app.request(`/v1/chat-generations/${runId}/agent-approvals`, {
        method: "POST",
        headers: {
          authorization: `Bearer ${local.devToken}`,
          "content-type": "application/json",
        },
        body: JSON.stringify({
          approvalId: `approval:call:${resolution}`,
          resolution,
        }),
      });
      expect(response.status).toBe(202);
      const body = await response.json() as { outcome: { kind: string } };
      expect(body.outcome.kind).not.toBe("completed");
      db.close();
    }
  });
});

describe("chat attachment scan route visibility", () => {
  test("upload exposes scanner identity and clean scan state", async () => {
    const db = new Database(":memory:");
    const local = createLocalDevService({
      db,
      ownerAccountId: "attachment-owner",
      memoryCount: 0,
      accountTimezone: "UTC",
      devSecretLabel: "attachment-scan-route-proof",
    });
    const body = new FormData();
    body.append("file", new File([pdf()], "scan.pdf", { type: "application/pdf" }));
    const response = await local.app.request("/v1/chat-attachments", {
      method: "POST",
      headers: { authorization: `Bearer ${local.devToken}` },
      body,
    });
    expect(response.status).toBe(201);
    const json = await response.json() as { attachment: Record<string, unknown> };
    expect(json.attachment.scanState).toBe("clean");
    expect(json.attachment.scannerId).toBe(DEV_NOOP_SCANNER_ID);
    db.close();
  });
});
