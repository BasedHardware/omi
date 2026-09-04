import { describe, expect, it } from "vitest";
import { pumpJournalOutboxDeliveries } from "../src/runtime/journal-outbox-pump.js";
import { SqliteAgentStore } from "../src/runtime/sqlite-store.js";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

describe("journal outbox pump", () => {
  it("one throwing send does not skip later independent deliveries", () => {
    const stateDir = mkdtempSync(join(tmpdir(), "journal-pump-"));
    const store = new SqliteAgentStore({ stateDir, reconcileOnOpen: false });
    const ownerId = "owner";
    const session = store.insertSession({ ownerId, surfaceKind: "main_chat", defaultAdapterId: "acp" });
    store.insertSurfaceConversation({
      ownerId,
      surfaceKind: "main_chat",
      externalRefKind: "chat",
      externalRefId: "pump-isolation",
      conversationId: "conv-a",
      agentSessionId: session.sessionId,
      createdAtMs: 1,
      lastActiveAtMs: 1,
    });
    store.execute(
      `INSERT INTO backend_conversation_delete_outbox(
         operation_id, conversation_id, owner_id, target_kind, target_id,
         conversation_generation, status, attempt_count, delivery_generation,
         payload_hash, available_at_ms, lease_expires_at_ms, last_error_code,
         created_at_ms, updated_at_ms, delivered_at_ms
       ) VALUES (?, ?, ?, 'messages', NULL, 1, 'pending', 0, 0, 'hash-a', 0, NULL, NULL, 1, 1, NULL)`,
      ["op-poison", "conv-a", ownerId],
    );
    store.execute(
      `INSERT INTO backend_conversation_delete_outbox(
         operation_id, conversation_id, owner_id, target_kind, target_id,
         conversation_generation, status, attempt_count, delivery_generation,
         payload_hash, available_at_ms, lease_expires_at_ms, last_error_code,
         created_at_ms, updated_at_ms, delivered_at_ms
       ) VALUES (?, ?, ?, 'messages', NULL, 1, 'pending', 0, 0, 'hash-b', 0, NULL, NULL, 2, 2, NULL)`,
      ["op-healthy", "conv-b", ownerId],
    );

    const sent: string[] = [];
    pumpJournalOutboxDeliveries({
      store,
      ownerId,
      hasChatFirstMainCapability: false,
      send: (message) => {
        if (message.type !== "journal_backend_delete") return;
        const operationId = String(message.operationId);
        sent.push(operationId);
        if (operationId === "op-poison") throw new Error("send failed");
      },
      onQuarantine: () => undefined,
    });
    expect(sent).toEqual(["op-poison", "op-healthy"]);
    store.close();
    rmSync(stateDir, { recursive: true, force: true });
  });
});
