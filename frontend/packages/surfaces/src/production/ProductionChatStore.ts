import type {
  BridgeStreamPort,
  ChatAttachmentStagingPort,
  HttpClient,
  StagedChatAttachment,
  StorageBridge,
} from "@omi-core/contracts";
import type { Env } from "@omi-core/kernel";
import { ChatMessagesStore, type StoreStatus } from "@omi-core/domain";
import type {
  ChatCapabilities,
  ChatAttachment,
  ChatHistoryPage,
  ChatMessage,
  ChatRole,
} from "./chat-reconcile.js";

export type {
  ChatCapabilities,
  ChatAttachment,
  ChatHistoryPage,
  ChatMessage,
  ChatRole,
};
export type { StagedChatAttachment } from "@omi-core/contracts";

/** Production Chat surface port. Fixtures and the live adapter share it. */
export type ProductionChatStore = {
  status(): StoreStatus;
  subscribe(listener: () => void): () => void;
  refresh(): Promise<void>;
  history(): Promise<ChatHistoryPage>;
  loadOlder(cursor: string): Promise<ChatHistoryPage>;
  send(input: {
    text: string;
    attachmentIds: readonly string[];
  }): Promise<void>;
  capabilities(): ChatCapabilities;
  stagingAvailable(): boolean;
  stageAttachment(): Promise<StagedChatAttachment | null>;
  retry(clientMessageId: string): Promise<void>;
  cancel(generationId: string): Promise<void>;
};

function role(sender: "human" | "ai"): ChatRole {
  return sender === "human" ? "user" : "assistant";
}

function projectCanonical(
  message: Exclude<import("@omi-core/contracts").ChatMessage, { sender: "unknown" }>,
  pending = false,
): ChatMessage {
  return {
    role: role(message.sender),
    text: message.text,
    delivery: pending
      ? { kind: "echo", clientMessageId: message.id }
      : {
          kind: "canonical",
          serverId: message.id,
          clientMessageId: message.sender === "human" ? message.id : null,
          generationOutcome: message.generationOutcome,
        },
    attachments: message.attachments,
  };
}

function capabilities(store: ChatMessagesStore): ChatCapabilities {
  const value = store.capabilities();
  return value === null
    ? {
        maxAttachmentsPerMessage: null,
        maxAttachmentBytes: null,
        allowedAttachmentMimeTypes: null,
      }
    : {
        maxAttachmentsPerMessage: value.maxAttachmentsPerMessage,
        maxAttachmentBytes: value.maxAttachmentBytes,
        allowedAttachmentMimeTypes: value.allowedAttachmentMimeTypes,
      };
}

async function projectedHistory(store: ChatMessagesStore): Promise<readonly ChatMessage[]> {
  const pendingIds = new Set(store.pendingMessageIds());
  const activeByClient = new Map(
    store.activeGenerations().map((generation) => [generation.clientMessageId, generation]),
  );
  const projected: ChatMessage[] = [];
  for (const message of await store.list()) {
    if (message.sender === "unknown") continue;
    projected.push(projectCanonical(message, message.sender === "human" && pendingIds.has(message.id)));
    const active = activeByClient.get(message.id);
    if (message.sender === "human" && active !== undefined) {
      projected.push({
        role: "assistant",
        text: active.text,
        delivery: { kind: "streaming", generationId: active.generationId },
        attachments: [],
      });
      activeByClient.delete(message.id);
    }
  }
  for (const active of activeByClient.values()) {
    projected.push({
      role: "assistant",
      text: active.text,
      delivery: { kind: "streaming", generationId: active.generationId },
      attachments: [],
    });
  }
  return projected;
}

/** Adapt the real domain mirror plus observer to the rendered Chat port. */
export function createProductionChatStore(
  store: ChatMessagesStore,
  attachmentStaging?: ChatAttachmentStagingPort,
): ProductionChatStore {
  return {
    status: () => store.status(),
    subscribe: (listener) => store.subscribe(listener),
    refresh: () => store.refresh(),
    async history() {
      const page = store.historyPage();
      return {
        messages: await projectedHistory(store),
        hasOlder: page.hasOlder,
        olderCursor: page.olderCursor,
      };
    },
    async loadOlder(cursor) {
      const rows = await store.loadOlder(cursor);
      const page = store.historyPage();
      return {
        messages: rows.flatMap((message) =>
          message.sender === "unknown" ? [] : [projectCanonical(message)]),
        hasOlder: page.hasOlder,
        olderCursor: page.olderCursor,
      };
    },
    async send(input) {
      await store.send(input.text, input.attachmentIds);
    },
    capabilities: () => capabilities(store),
    stagingAvailable: () => attachmentStaging?.isAvailable() === true,
    stageAttachment: async () => {
      if (attachmentStaging?.isAvailable() !== true) {
        throw new Error("native Chat attachment staging is unavailable");
      }
      return attachmentStaging.pickAndStage();
    },
    async retry() {
      throw new Error("Chat replay requires the retained authored outbox operation");
    },
    cancel: (generationId) => store.cancelGeneration(generationId),
  };
}

/** Named live factory seam consumed by production composition and C3b3. */
export async function openProductionChatStore(
  bridge: StorageBridge,
  env: Env,
  http: HttpClient,
  streamPort: BridgeStreamPort,
  attachmentStaging?: ChatAttachmentStagingPort,
): Promise<ProductionChatStore> {
  return createProductionChatStore(
    await ChatMessagesStore.open(bridge, env, http, streamPort),
    attachmentStaging,
  );
}
