import type {
  BridgeStreamPort,
  ChatAttachmentStagingPort,
  HttpClient,
  StagedChatAttachment,
  StorageBridge,
} from "@omi-core/contracts";
import { deadLetterPayload } from "@omi-core/contracts";
import type { Env } from "@omi-core/kernel";
import { ChatMessagesStore, type StoreStatus } from "@omi-core/domain";
import type {
  ChatCapabilities,
  ChatAttachment,
  ChatHistoryPage,
  ChatMessage,
  ChatRole,
  ChatAgentRunTimeline,
} from "./chat-reconcile.js";
import {
  createDevNoopAttachmentScanner,
  type ChatAttachmentScanTerminal,
} from "./chat-attachment-scan.js";

export type {
  ChatCapabilities,
  ChatAttachment,
  ChatHistoryPage,
  ChatMessage,
  ChatRole,
  ChatAgentRunTimeline,
};
export type { StagedChatAttachment } from "@omi-core/contracts";
export {
  ATTACHMENT_SCAN_TIMEOUT_MS,
  DEV_NOOP_SCANNER_ID,
  asScanTerminal,
  attachmentsAreAdmissibleForSend,
  canRemoveTrayAttachment,
  canRetryAttachmentScan,
  createDevNoopAttachmentScanner,
  isAdmissibleForBind,
  toTrayAttachment,
} from "./chat-attachment-scan.js";
export type {
  ChatAttachmentScanClock,
  ChatAttachmentScanState,
  ChatAttachmentScanTerminal,
  ChatAttachmentScanner,
  ChatTrayAttachment,
} from "./chat-attachment-scan.js";

export interface RetainedChatSend {
  readonly opId: string;
  readonly text: string | null;
  /** Safe recovery metadata. Opaque staged ids never cross into the UI port. */
  readonly attachmentCount: number | null;
}

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
  /** Development scan only. Identity is always `dev-noop-scanner`; never a real product scanner. */
  scanAttachment(attachment: StagedChatAttachment): Promise<ChatAttachmentScanTerminal>;
  deadLetters(): Promise<readonly RetainedChatSend[]>;
  discardDeadLetter(opId: string): Promise<void>;
  cancel(generationId: string): Promise<void>;
  resolveApproval(resolution: "approved" | "denied" | "cancelled"): Promise<void>;
};

function role(sender: "human" | "ai"): ChatRole {
  return sender === "human" ? "user" : "assistant";
}

function projectCanonical(
  message: Exclude<import("@omi-core/contracts").ChatMessage, { sender: "unknown" }>,
  pending = false,
  agentRun?: ChatAgentRunTimeline,
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
    ...(agentRun === undefined ? {} : { agentRun }),
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
  const deliveries = await store.generationDeliveries();
  const timelines = store.agentRunTimelines();
  const timelineByGeneration = new Map(timelines.map((timeline) => [timeline.generationId, {
    state: timeline.observationState,
    events: timeline.events,
  } satisfies ChatAgentRunTimeline]));
  const failedByClient = new Map(
    deliveries
      .filter((delivery) => delivery.terminal.kind === "failed")
      .map((delivery) => [delivery.clientMessageId, delivery]),
  );
  const generationByAssistant = new Map(
    deliveries.flatMap((delivery) => {
      const terminal = delivery.terminal;
      const message = terminal.kind === "done" ? terminal.message
        : terminal.kind === "cancelled" ? terminal.message : null;
      return message === null ? [] : [[message.id, delivery.generationId] as const];
    }),
  );
  const activeByClient = new Map(
    store.activeGenerations().map((generation) => [generation.clientMessageId, generation]),
  );
  const projected: ChatMessage[] = [];
  for (const message of await store.list()) {
    if (message.sender === "unknown") continue;
    const canonicalGeneration = message.sender === "ai" ? generationByAssistant.get(message.id) : undefined;
    projected.push(projectCanonical(
      message,
      message.sender === "human" && pendingIds.has(message.id),
      canonicalGeneration === undefined ? undefined : timelineByGeneration.get(canonicalGeneration),
    ));
    const active = activeByClient.get(message.id);
    if (message.sender === "human" && active !== undefined) {
      projected.push({
        role: "assistant",
        text: active.text,
        delivery: active.observationState === "streaming"
          ? { kind: "streaming", generationId: active.generationId }
          : {
              kind: "failed",
              generationId: active.generationId,
              clientMessageId: active.clientMessageId,
              source: active.failure === "stream-unavailable" ? "transport" : "observer",
              retryable: false,
            },
        attachments: [],
        ...(timelineByGeneration.get(active.generationId) === undefined ? {} : {
          agentRun: timelineByGeneration.get(active.generationId)!,
        }),
      });
      activeByClient.delete(message.id);
    } else if (message.sender === "human") {
      const failure = failedByClient.get(message.id);
      if (failure?.terminal.kind === "failed") {
        projected.push({
          role: "assistant",
          text: "",
          delivery: {
            kind: "failed",
            generationId: failure.generationId,
            clientMessageId: failure.clientMessageId,
            source: "provider",
            retryable: failure.terminal.error.retryable,
          },
          attachments: [],
          ...(timelineByGeneration.get(failure.generationId) === undefined ? {} : {
            agentRun: timelineByGeneration.get(failure.generationId)!,
          }),
        });
        failedByClient.delete(message.id);
      }
    }
  }
  for (const active of activeByClient.values()) {
    projected.push({
      role: "assistant",
      text: active.text,
      delivery: active.observationState === "streaming"
        ? { kind: "streaming", generationId: active.generationId }
        : {
            kind: "failed",
            generationId: active.generationId,
            clientMessageId: active.clientMessageId,
            source: active.failure === "stream-unavailable" ? "transport" : "observer",
            retryable: false,
          },
      attachments: [],
      ...(timelineByGeneration.get(active.generationId) === undefined ? {} : {
        agentRun: timelineByGeneration.get(active.generationId)!,
      }),
    });
  }
  return projected;
}

function retainedChatSend(letter: import("@omi-core/contracts").DeadLetter): RetainedChatSend {
  const payload = deadLetterPayload(letter);
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    return { opId: letter.opId, text: null, attachmentCount: null };
  }
  const op = payload as Record<string, unknown>;
  if (
    op["op"] !== "create" ||
    typeof op["text"] !== "string" ||
    !Array.isArray(op["attachmentIds"]) ||
    !op["attachmentIds"].every((id) =>
      typeof id === "string" && /^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$/u.test(id))
  ) {
    return { opId: letter.opId, text: null, attachmentCount: null };
  }
  return {
    opId: letter.opId,
    text: op["text"],
    attachmentCount: op["attachmentIds"].length,
  };
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
    scanAttachment: async (attachment) => {
      return createDevNoopAttachmentScanner().scan(attachment);
    },
    async deadLetters() {
      return (await store.deadLetters()).map(retainedChatSend);
    },
    discardDeadLetter: (opId) => store.discardDeadLetter(opId),
    cancel: (generationId) => store.cancelGeneration(generationId),
    async resolveApproval(resolution) {
      const candidate = store as ChatMessagesStore & {
        resolveApproval?: (value: "approved" | "denied" | "cancelled") => Promise<void>;
      };
      if (typeof candidate.resolveApproval !== "function") return;
      await candidate.resolveApproval(resolution);
    },
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
