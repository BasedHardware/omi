import type { QueuePhase, QueueStatus } from "@omi-core/sync";
import type { RefreshPhase, StoreStatus } from "@omi-core/domain";
import type {
  ChatCapabilities,
  ChatHistoryPage,
  ChatMessage,
} from "./chat-reconcile.js";
import type { ProductionChatStore } from "./ProductionChatStore.js";
import type { RetainedChatSend } from "./ProductionChatStore.js";
import { createDevNoopAttachmentScanner } from "./chat-attachment-scan.js";

/** Fixed instant for deterministic chat fixtures (UTC). */
export const CHAT_FIXED_NOW = Date.UTC(2026, 7, 7, 12, 0, 0);

export const CHAT_FIXTURE_STATES = [
  "loading",
  "empty",
  "ready",
  "normal",
  "streaming",
  "cancelled",
  "pending-echo",
  "send-failed",
  "older-available",
  "attachments-unknown-cap",
  "unavailable",
  "saved-failed",
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
  agentRun?: ChatMessage["agentRun"],
): ChatMessage {
  return {
    role,
    text,
    delivery: { kind: "canonical", serverId, clientMessageId, generationOutcome },
    attachments: [],
    ...(agentRun === undefined ? {} : { agentRun }),
  };
}

const fixtureAgentRun: NonNullable<ChatMessage["agentRun"]> = {
  state: "complete",
  events: [
    { sequence: 1, createdAt: CHAT_FIXED_NOW, kind: "run_accepted", safeSummary: "Request accepted", details: {} },
    { sequence: 2, createdAt: CHAT_FIXED_NOW + 1, kind: "capability_receipt", safeSummary: "Local scripted adapter declared", details: { tier: "deterministic-scripted", adapter: "local-scripted", deterministic: true } },
    { sequence: 3, createdAt: CHAT_FIXED_NOW + 2, kind: "context_receipt", safeSummary: "Saved context selected", details: { sourceKind: "memory", redactedPreview: "Review checklist preference", tokenEstimate: 18, inclusionReason: "Relevant to the handoff question", policyDecision: "included" } },
    { sequence: 4, createdAt: CHAT_FIXED_NOW + 3, kind: "tool_request", safeSummary: "Searching saved conversations", details: { toolName: "search_conversations", timeoutMs: 5_000 } },
    { sequence: 5, createdAt: CHAT_FIXED_NOW + 4, kind: "tool_result", safeSummary: "Saved conversations searched", details: { toolName: "search_conversations", resultSummary: "Two relevant conversations found", durationMs: 42, retryable: false } },
    { sequence: 6, createdAt: CHAT_FIXED_NOW + 5, kind: "approval_requested", safeSummary: "Approval requested for an account change", details: { reason: "Account changes require confirmation", expiresAt: CHAT_FIXED_NOW + 60_000 } },
    { sequence: 7, createdAt: CHAT_FIXED_NOW + 6, kind: "approval_resolved", safeSummary: "Approval was denied", details: { resolution: "denied" } },
    { sequence: 8, createdAt: CHAT_FIXED_NOW + 7, kind: "tool_request", safeSummary: "Reading the review checklist", details: { toolName: "read_checklist", timeoutMs: 5_000 } },
    { sequence: 9, createdAt: CHAT_FIXED_NOW + 8, kind: "tool_result", safeSummary: "Review checklist read", details: { toolName: "read_checklist", resultSummary: "Checklist is ready", durationMs: 21, retryable: false } },
    { sequence: 10, createdAt: CHAT_FIXED_NOW + 9, kind: "recovery", safeSummary: "Response reconnected", details: { action: "reconnect", reason: "The event stream briefly disconnected" } },
    { sequence: 11, createdAt: CHAT_FIXED_NOW + 10, kind: "usage", safeSummary: "Usage recorded", details: { inputTokens: 30, outputTokens: 20, totalTokens: 50, durationMs: 80 } },
    { sequence: 12, createdAt: CHAT_FIXED_NOW + 11, kind: "terminal", safeSummary: "Response complete", details: { terminalOutcome: "completed", terminalCode: "completed", retryable: false, recoveryAction: null } },
  ],
};

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
    canonical("fixture-chat-s4", "assistant", "Only the glass parity pass on dark desktop.", null, "completed", fixtureAgentRun),
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
  if (state === "loading" || state === "empty" || state === "unavailable") {
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
      messages: baseMessages(),
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
  if (state === "ready") {
    return {
      messages: baseMessages().slice(0, 3),
      hasOlder: false,
      olderCursor: null,
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
    return {
      maxAttachmentsPerMessage: null,
      maxAttachmentBytes: null,
      allowedAttachmentMimeTypes: null,
    };
  }
  return {
    maxAttachmentsPerMessage: FIXTURE_SERVER_ATTACHMENT_CAP,
    maxAttachmentBytes: 50_000_000,
    allowedAttachmentMimeTypes: ["application/pdf", "image/png", "image/jpeg"],
  };
}

/**
 * Deterministic chat store for QA fixtures. Time is fixed via CHAT_FIXED_NOW;
 * attachment caps come only from the fixture server report above.
 */
export function fixtureChatStore(state: ChatFixtureState): ProductionChatStore {
  let historyPage = pageFor(state);
  const caps = capabilitiesFor(state);
  const refreshPhase: RefreshPhase = state === "loading"
    ? "initial-loading"
    : state === "unavailable"
      ? "unavailable"
      : state === "saved-failed"
        ? "saved-but-refresh-failed"
        : "ready";
  const status: StoreStatus = {
    refresh: { phase: refreshPhase, hasSavedData: historyPage.messages.length > 0 },
    queue: queue("idle"),
  };
  const listeners = new Set<() => void>();
  const notify = (): void => {
    listeners.forEach((listener) => listener());
  };
  let olderLoaded = false;
  let sentSequence = 0;
  let retained: RetainedChatSend[] = state === "send-failed"
    ? [{
        opId: "fixture-dead-send",
        text: "Reconstruct this message without replaying its old envelope.",
        attachmentCount: 2,
      }]
    : [];

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
      sentSequence += 1;
      const clientMessageId = `fixture-sent-client-${sentSequence}`;
      historyPage = {
        ...historyPage,
        messages: [
          ...historyPage.messages,
          canonical(`fixture-sent-${clientMessageId}`, "user", input.text, clientMessageId),
        ],
      };
      notify();
    },
    capabilities() {
      return caps;
    },
    stagingAvailable() {
      return false;
    },
    async stageAttachment() {
      throw new Error("fixture staging requires an explicitly supplied typed port");
    },
    async scanAttachment(attachment) {
      return createDevNoopAttachmentScanner().scan(attachment);
    },
    async deadLetters() {
      return retained;
    },
    async discardDeadLetter(opId) {
      retained = retained.filter((letter) => letter.opId !== opId);
      notify();
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
    async resolveApproval(resolution) {
      historyPage = {
        ...historyPage,
        messages: historyPage.messages.map((message) => {
          const timeline = message.agentRun;
          if (!timeline) return message;
          const pending = [...timeline.events].reverse().find((event) =>
            event.kind === "approval_requested" || event.kind === "approval_resolved");
          if (pending?.kind !== "approval_requested") return message;
          const sequence = Math.max(...timeline.events.map((event) => event.sequence)) + 1;
          return {
            ...message,
            agentRun: {
              ...timeline,
              events: [
                ...timeline.events,
                {
                  sequence,
                  createdAt: CHAT_FIXED_NOW + sequence,
                  kind: "approval_resolved" as const,
                  safeSummary: resolution === "approved"
                    ? "Approval was granted"
                    : resolution === "denied"
                      ? "Approval was denied"
                      : "Approval was cancelled",
                  details: { resolution },
                },
              ],
            },
          };
        }),
      };
      notify();
    },
  };
}
