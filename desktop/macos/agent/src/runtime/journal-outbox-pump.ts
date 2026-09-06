/**
 * Journal outbox pump: each delivery is its own fault domain.
 * Kept out of index.ts so that 4k-line file does not grow.
 */
import {
  drainBackendConversationDeleteOutbox,
  drainBackendTurnOutbox,
  drainChatFirstDeferralOutbox,
} from "./conversation-journal.js";
import { drainIsolated } from "./durable-queue.js";
import type { OutboundMessageDraft } from "../protocol.js";
import type { AgentStore } from "./types.js";

export function pumpJournalOutboxDeliveries(input: {
  store: AgentStore;
  ownerId: string;
  hasChatFirstMainCapability: boolean;
  send: (message: OutboundMessageDraft) => void;
  onQuarantine: (turnId: string) => void;
}): void {
  drainIsolated(
    drainBackendConversationDeleteOutbox(input.store, {
      ownerId: input.ownerId,
      limit: 20,
    }),
    (deletion) => {
      input.send({
        type: "journal_backend_delete",
        requestId: `journal-delete:${deletion.operationId}:${deletion.deliveryGeneration}`,
        clientId: "kernel-journal",
        ownerId: deletion.ownerId,
        operationId: deletion.operationId,
        conversationId: deletion.conversationId,
        conversationGeneration: deletion.conversationGeneration,
        attemptCount: deletion.attemptCount,
        deliveryGeneration: deletion.deliveryGeneration,
        payloadHash: deletion.payloadHash,
        targetKind: deletion.targetKind,
        targetId: deletion.targetId,
      });
      return { kind: "ack" };
    },
  );

  drainIsolated(
    drainBackendTurnOutbox(input.store, {
      ownerId: input.ownerId,
      limit: 20,
      onQuarantine: input.onQuarantine,
    }),
    (delivery) => {
      input.send({
        type: "journal_backend_sync",
        requestId: `journal:${delivery.turnId}:${delivery.deliveryGeneration}`,
        clientId: "kernel-journal",
        ownerId: delivery.ownerId,
        ...delivery.payload,
        turnId: delivery.turnId,
        conversationId: delivery.conversationId,
        conversationGeneration: delivery.conversationGeneration,
        attemptCount: delivery.attemptCount,
        deliveryGeneration: delivery.deliveryGeneration,
        payloadHash: delivery.payloadHash,
      });
      return { kind: "ack" };
    },
  );

  // This deliberately remains distinct from backend_turn_outbox: a
  // deferral is task-intelligence state, never a second transcript write.
  // Do not even claim an outbox row until the server-sampled Main Chat
  // capability is present in this process. A fresh capability-off launch
  // must leave chat-first background work entirely dormant.
  if (!input.hasChatFirstMainCapability) return;

  drainIsolated(
    drainChatFirstDeferralOutbox(input.store, { ownerId: input.ownerId, limit: 20 }),
    (delivery) => {
      const deferredQuestionSubject = delivery.question.subject;
      if (deferredQuestionSubject.kind === "cold_start") {
        throw new Error("Cold-start sequence questions cannot enter the deferral outbox");
      }
      const deferralSubject = deferredQuestionSubject as { kind: "task" | "goal" | "capture"; id: string };
      input.send({
        type: "chat_first_deferral_delivery",
        requestId: `chat-first-deferral:${delivery.continuityKey}:${delivery.deliveryGeneration}`,
        clientId: "kernel-chat-first",
        ownerId: delivery.ownerId,
        continuityKey: delivery.continuityKey,
        controlGeneration: delivery.controlGeneration,
        subject: delivery.subject,
        question: {
          questionId: delivery.question.questionId,
          text: delivery.question.text,
          subject: deferralSubject,
          options: delivery.question.options,
        },
        attemptCount: delivery.attemptCount,
        deliveryGeneration: delivery.deliveryGeneration,
        payloadHash: delivery.payloadHash,
      });
      return { kind: "ack" };
    },
  );
}
