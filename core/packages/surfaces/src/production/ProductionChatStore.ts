import type { StoreStatus } from "@omi-core/domain";
import type {
  ChatCapabilities,
  ChatDelivery,
  ChatHistoryPage,
  ChatMessage,
  ChatRole,
} from "./chat-reconcile.js";

export type {
  ChatCapabilities,
  ChatDelivery,
  ChatHistoryPage,
  ChatMessage,
  ChatRole,
};

/**
 * Composition boundary between production chat UI and a backend generation.
 * FE-CORE's platform chat slice will implement this surface-facing port the
 * same way `ProductionStoreFactory` documents its own stores: fixtures and the
 * live adapter satisfy the same contract without changing product components
 * or their offline/status behavior. ADR-005: the server owns the conversation;
 * the client mirrors it.
 */
export type ProductionChatStore = {
  status(): StoreStatus;
  subscribe(listener: () => void): () => void;
  refresh(): Promise<void>;
  history(): Promise<ChatHistoryPage>;
  loadOlder(cursor: string): Promise<ChatHistoryPage>;
  send(input: {
    text: string;
    clientMessageId: string;
    attachments: readonly string[];
  }): Promise<void>;
  capabilities(): ChatCapabilities;
  retry(clientMessageId: string): Promise<void>;
};
