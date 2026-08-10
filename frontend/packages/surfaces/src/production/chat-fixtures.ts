import type { QueuePhase, QueueStatus } from "@omi-core/sync";
import type { RefreshPhase, StoreStatus } from "@omi-core/domain";
import type {
  ChatCapabilities,
  ChatHistoryPage,
  ChatMessage,
} from "./chat-reconcile.js";
import type { ProductionChatStore } from "./ProductionChatStore.js";

/** Fixed instant for deterministic chat fixtures (UTC). */
export const CHAT_FIXED_NOW = Date.UTC(2026, 7, 7, 12, 0, 0);

export const CHAT_FIXTURE_STATES = [
  "empty",
  "normal",
  "streaming",
  "cancelled",
  "pending-echo",
  "send-failed",
  "older-available",
  "attachments-unknown-cap",
  "unavailable",
] as const;

export type ChatFixtureState = (typeof CHAT_FIXTURE_STATES)[number];

/** Cap the fixture "server" reports for the normal matrix — never read by the component. */
const FIXTURE_SERVER_ATTACHMENT_CAP = 4;

function queue(phase: QueuePhase): QueueStatus {
  return { phase, pendingCount: phase === "idle" ? 0 : 1 };
}

function canonical(
  serverId: string,
  role: ChatMessage["role"],
  text: string,
  clientMessageId: string | null = null,
  generationOutcome: "completed" | "cancelled" | null = role === "assistant" ? "completed" : null,
): ChatMessage {
  return {
    role,
    text,
    delivery: { kind: "canonical", serverId, clientMessageId, generationOutcome },
    attachments: [],
  };
}

function streaming(generationId: string, text: string): ChatMessage {
  return {
    role: "assistant",
    text,
    delivery: { kind: "streaming", generationId },
    attachments: [],
  };
}

function baseMessages(): ChatMessage[] {
  return [
    canonical("fixture-chat-s1", "user", "What did we decide about the handoff?", "fixture-cid-1"),
    canonical("fixture-chat-s2", "assistant", "Keep the review checklist short and ship the named build."),
    canonical("fixture-chat-s3", "user", "Any open risks?", "fixture-cid-2"),
    canonical("fixture-chat-s4", "assistant", "Only the glass parity pass on dark desktop."),
  ];
}

function olderPage(): ChatHistoryPage {
  return {
    messages: [
      canonical("fixture-chat-older-1", "user", "Start from yesterday's notes.", "fixture-cid-older-1"),
      canonical("fixture-chat-older-2", "assistant", "Yesterday's notes are ready when you are."),
    ],
    hasOlder: false,
    olderCursor: null,
  };
}

function pageFor(state: ChatFixtureState): ChatHistoryPage {
  if (state === "empty" || state === "unavailable") {
    return { messages: [], hasOlder: false, olderCursor: null };
  }
  if (state === "streaming") {
    return {
      messages: [
        ...baseMessages(),
        streaming("fixture-generation-stream", "Checking the saved review notes"),
      ],
      hasOlder: false,
      olderCursor: null,
    };
  }
  if (state === "cancelled") {
    return {
      messages: [
        ...baseMessages(),
        canonical(
          "fixture-chat-cancelled",
          "assistant",
          "Checking the saved review notes",
          null,
          "cancelled",
        ),
      ],
      hasOlder: false,
      olderCursor: null,
    };
  }
  if (state === "pending-echo") {
    return {
      messages: [
        ...baseMessages(),
        {
          role: "user",
          text: "Hold the glass check until after lunch.",
          delivery: { kind: "echo", clientMessageId: "fixture-cid-pending" },
          attachments: [],
        },
      ],
      hasOlder: false,
      olderCursor: null,
    };
  }
  if (state === "send-failed") {
    return {
      messages: [
        ...baseMessages(),
        {
          role: "user",
          text: "Retry the delivery when the queue clears.",
          delivery: { kind: "failed", clientMessageId: "fixture-cid-failed", retryable: true },
          attachments: [],
        },
      ],
      hasOlder: false,
      olderCursor: null,
    };
  }
  if (state === "older-available") {
    return {
      messages: baseMessages(),
      hasOlder: true,
      olderCursor: "fixture-older-cursor-1",
    };
  }
  return {
    messages: baseMessages(),
    hasOlder: false,
    olderCursor: null,
  };
}

function capabilitiesFor(state: ChatFixtureState): ChatCapabilities {
  if (state === "attachments-unknown-cap") {
    return { maxAttachmentsPerMessage: null };
  }
  return { maxAttachmentsPerMessage: FIXTURE_SERVER_ATTACHMENT_CAP };
}

/**
 * Deterministic chat store for QA fixtures. Time is fixed via CHAT_FIXED_NOW;
 * attachment caps come only from the fixture server report above.
 */
export function fixtureChatStore(state: ChatFixtureState): ProductionChatStore {
  let historyPage = pageFor(state);
  const caps = capabilitiesFor(state);
  const refreshPhase: RefreshPhase = state === "unavailable" ? "unavailable" : "ready";
  const status: StoreStatus = {
    refresh: { phase: refreshPhase, hasSavedData: historyPage.messages.length > 0 },
    queue: queue("idle"),
  };
  const listeners = new Set<() => void>();
  const notify = (): void => {
    listeners.forEach((listener) => listener());
  };
  let olderLoaded = false;

  return {
    status() {
      return status;
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    async refresh() {
      if (state === "unavailable") throw new Error("fixture chat unavailable");
      notify();
    },
    async history() {
      return historyPage;
    },
    async loadOlder(cursor: string) {
      if (state !== "older-available" || cursor !== "fixture-older-cursor-1" || olderLoaded) {
        return { messages: [], hasOlder: false, olderCursor: null };
      }
      olderLoaded = true;
      const older = olderPage();
      historyPage = {
        messages: [...older.messages, ...historyPage.messages],
        hasOlder: false,
        olderCursor: null,
      };
      notify();
      return older;
    },
    async send(input) {
      if (state === "unavailable") throw new Error("fixture chat send failed");
      historyPage = {
        ...historyPage,
        messages: [
          ...historyPage.messages.filter(
            (message) =>
              !(
                (message.delivery.kind === "echo" || message.delivery.kind === "failed") &&
                message.delivery.clientMessageId === input.clientMessageId
              ),
          ),
          canonical(`fixture-sent-${input.clientMessageId}`, "user", input.text, input.clientMessageId),
        ],
      };
      notify();
    },
    capabilities() {
      return caps;
    },
    async retry(clientMessageId) {
      const failed = historyPage.messages.find(
        (message) => message.delivery.kind === "failed" && message.delivery.clientMessageId === clientMessageId,
      );
      if (!failed) return;
      await this.send({ text: failed.text, clientMessageId, attachmentIds: [] });
    },
    async cancel(generationId) {
      const streamingMessage = historyPage.messages.find(
        (message) => message.delivery.kind === "streaming" &&
          message.delivery.generationId === generationId,
      );
      if (!streamingMessage) return;
      historyPage = {
        ...historyPage,
        messages: historyPage.messages.map((message) =>
          message === streamingMessage
            ? canonical(
                `fixture-cancelled-${generationId}`,
                "assistant",
                message.text,
                null,
                "cancelled",
              )
            : message,
        ),
      };
      notify();
    },
  };
}
