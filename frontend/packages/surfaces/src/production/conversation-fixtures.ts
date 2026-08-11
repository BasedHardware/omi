import { parseRecordId, type Conversation, type DeadLetter, type Folder } from "@omi-core/contracts";
import type { QueuePhase, QueueStatus } from "@omi-core/sync";
import type { RefreshPhase, StoreStatus } from "@omi-core/domain";
import type { ProductionConversationStore, ProductionFolderStore } from "./ProductionStores.js";

export const CONVERSATION_FIXED_NOW = Date.UTC(2026, 7, 7, 12, 0, 0);

function id(value: string): Conversation["id"] {
  const parsed = parseRecordId(value);
  if (!parsed) throw new Error(`fixture id is not a valid RecordId: ${value}`);
  return parsed.id;
}

function folderId(value: string): Folder["id"] {
  const parsed = parseRecordId(value);
  if (!parsed) throw new Error(`fixture folder id is not a valid RecordId: ${value}`);
  return parsed.id;
}

function conversation(value: Partial<Conversation> & Pick<Conversation, "id" | "title" | "overview">): Conversation {
  return {
    id: value.id,
    title: value.title,
    overview: value.overview,
    createdAt: value.createdAt ?? CONVERSATION_FIXED_NOW - 86_400_000,
    updatedAt: value.updatedAt ?? CONVERSATION_FIXED_NOW - 3_600_000,
    startedAt: value.startedAt ?? CONVERSATION_FIXED_NOW - 3_900_000,
    finishedAt: value.finishedAt ?? CONVERSATION_FIXED_NOW - 3_600_000,
    source: value.source ?? "omi",
    status: value.status ?? "completed",
    discarded: value.discarded ?? false,
    starred: value.starred ?? false,
    visibility: value.visibility ?? "private",
    isLocked: value.isLocked ?? false,
    folderId: value.folderId ?? null,
    revision: value.revision ?? "fixture-r1",
  };
}

function baseRows(): Conversation[] {
  return [
    conversation({
      id: id("calm-conversation-one"),
      title: "Morning review",
      overview: "A short review of priorities and the next useful step.",
      starred: true,
      visibility: "private",
      folderId: folderId("work-folder-one"),
    }),
    conversation({
      id: id("quiet-conversation-two"),
      title: "Planning notes",
      overview: "A saved summary about planning the next iteration.",
      visibility: "shared",
      folderId: null,
      startedAt: CONVERSATION_FIXED_NOW - 25 * 60 * 60 * 1000,
      finishedAt: CONVERSATION_FIXED_NOW - 24 * 60 * 60 * 1000,
    }),
    conversation({
      id: id("steady-conversation-three"), title: "Desktop design review",
      overview: "Reviewed the glass hierarchy and compact list rhythm.", folderId: folderId("work-folder-one"),
      startedAt: CONVERSATION_FIXED_NOW - 2 * 60 * 60 * 1000, finishedAt: CONVERSATION_FIXED_NOW - 90 * 60 * 1000,
    }),
    conversation({
      id: id("bright-conversation-four"), title: "Weekly team sync",
      overview: "Decisions, open questions, and owners for the next iteration.", starred: true,
      startedAt: CONVERSATION_FIXED_NOW - 4 * 60 * 60 * 1000, finishedAt: CONVERSATION_FIXED_NOW - 3.4 * 60 * 60 * 1000,
    }),
    conversation({
      id: id("open-conversation-seven"), title: "Product direction notes",
      overview: "Captured the strongest options and the decision still to make.",
      startedAt: CONVERSATION_FIXED_NOW - 6 * 60 * 60 * 1000, finishedAt: CONVERSATION_FIXED_NOW - 5.3 * 60 * 60 * 1000,
    }),
    conversation({
      id: id("clear-conversation-five"), title: "Customer feedback notes",
      overview: "Themes from the latest product feedback session.",
      startedAt: CONVERSATION_FIXED_NOW - 26 * 60 * 60 * 1000, finishedAt: CONVERSATION_FIXED_NOW - 25.2 * 60 * 60 * 1000,
    }),
    conversation({
      id: id("kind-conversation-six"), title: "Launch checklist",
      overview: "A final pass through the launch and rollback checklist.", folderId: folderId("work-folder-one"),
      startedAt: CONVERSATION_FIXED_NOW - 27 * 60 * 60 * 1000, finishedAt: CONVERSATION_FIXED_NOW - 26.4 * 60 * 60 * 1000,
    }),
  ];
}

function folders(): Folder[] {
  return [
    {
      id: folderId("default-folder-one"),
      name: "Other",
      description: null,
      color: "#6B7280",
      icon: "folder",
      createdAt: CONVERSATION_FIXED_NOW - 4 * 86_400_000,
      updatedAt: CONVERSATION_FIXED_NOW - 4 * 86_400_000,
      order: 0,
      isDefault: true,
      isSystem: true,
      revision: "fixture-folder-r1",
    },
    {
      id: folderId("work-folder-one"),
      name: "Work",
      description: "Work conversations",
      color: "#007AFF",
      icon: "briefcase",
      createdAt: CONVERSATION_FIXED_NOW - 3 * 86_400_000,
      updatedAt: CONVERSATION_FIXED_NOW - 3 * 86_400_000,
      order: 1,
      isDefault: false,
      isSystem: false,
      revision: "fixture-folder-r1",
    },
  ];
}

export const CONVERSATION_FIXTURE_STATES = [
  "loading", "empty", "empty-summary", "fallbacks", "unavailable", "saved-failed", "queued", "sending", "retrying", "needs-auth", "dead", "normal", "locked", "discarded", "long",
] as const;
export type ConversationFixtureState = (typeof CONVERSATION_FIXTURE_STATES)[number];

export function fixtureConversationDetailId(state: ConversationFixtureState): Conversation["id"] {
  switch (state) {
    case "empty":
    case "empty-summary": return id("empty-summary-conversation");
    case "fallbacks": return id("fallback-conversation-one");
    case "locked": return id("locked-conversation-one");
    case "discarded": return id("discarded-conversation-one");
    case "long": return id("long-conversation-one");
    default: return id("calm-conversation-one");
  }
}

function queue(phase: QueuePhase): QueueStatus {
  return { phase, pendingCount: phase === "idle" ? 0 : phase === "needs-auth" ? 2 : 1 };
}

function deadLetter(): DeadLetter {
  return {
    opId: "fixture-conversation-dead-one",
    recordId: id("calm-conversation-one"),
    domain: "conversations",
    summary: "Update conversation visibility",
    failure: { kind: "permanent", reason: "validation", detail: "The saved conversation change was rejected." },
    deadAt: CONVERSATION_FIXED_NOW,
  };
}

export type FolderFixtureState = "loading" | "empty" | "ready" | "error" | "offline";

export function fixtureFolderStore(state: FolderFixtureState = "ready"): ProductionFolderStore {
  const rows = state === "loading" || state === "empty" || state === "error" ? [] : folders();
  const phase: RefreshPhase = state === "loading"
    ? "initial-loading"
    : state === "error"
      ? "unavailable"
      : state === "offline"
        ? "saved-but-refresh-failed"
        : "ready";
  const status: StoreStatus = { refresh: { phase, hasSavedData: rows.length > 0 }, queue: queue("idle") };
  const listeners = new Set<() => void>();
  const notify = () => listeners.forEach((listener) => listener());
  return {
    async list() { return rows; },
    status() { return status; },
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    async refresh() { notify(); },
  };
}

export function fixtureConversationStore(state: ConversationFixtureState, detail = false): ProductionConversationStore {
  let rows = state === "empty" || state === "unavailable" || state === "loading" ? [] : baseRows();
  if (state === "empty-summary") rows = [conversation({ id: id("empty-summary-conversation"), title: "Summary unavailable", overview: "" })];
  if (state === "empty" && detail) rows = [conversation({ id: id("empty-summary-conversation"), title: "Summary unavailable", overview: "" })];
  if (state === "fallbacks") rows = [conversation({
    id: id("fallback-conversation-one"),
    title: "",
    overview: "",
    createdAt: 0,
    updatedAt: 0,
    startedAt: null,
    finishedAt: null,
  })];
  if (state === "locked") rows = [conversation({ id: id("locked-conversation-one"), title: "Protected conversation", overview: "A protected conversation preview.", isLocked: true, visibility: "private" })];
  if (state === "discarded") rows = [conversation({ id: id("discarded-conversation-one"), title: "Discarded conversation", overview: "This saved row was discarded and remains visible for reconciliation.", discarded: true })];
  if (state === "long") {
    rows = [conversation({
      id: id("long-conversation-one"),
      title: "Long planning conversation",
      overview: "A saved summary with enough detail to exercise the disclosure control. ".repeat(12),
      folderId: folderId("work-folder-one"),
    })];
  }
  const refreshPhase: RefreshPhase = state === "loading"
    ? "initial-loading"
    : state === "unavailable"
      ? "unavailable"
      : state === "saved-failed"
        ? "saved-but-refresh-failed"
        : "ready";
  const queuePhase: QueuePhase = state === "queued"
    ? "queued"
    : state === "sending"
      ? "sending"
      : state === "retrying"
        ? "retrying"
        : state === "needs-auth"
          ? "needs-auth"
          : "idle";
  const status: StoreStatus = { refresh: { phase: refreshPhase, hasSavedData: rows.length > 0 }, queue: queue(queuePhase) };
  let dead = state === "dead" ? [deadLetter()] : [];
  const listeners = new Set<() => void>();
  const notify = () => listeners.forEach((listener) => listener());
  return {
    async list() { return rows; },
    status() { return status; },
    async deadLetters() { return dead; },
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    async refresh() { notify(); },
    async patch(conversationId, patch) {
      rows = rows.map((row) => row.id === conversationId ? { ...row, ...patch, updatedAt: CONVERSATION_FIXED_NOW } : row);
      notify();
    },
    async delete(conversationId) {
      rows = rows.filter((row) => row.id !== conversationId);
      notify();
    },
    async discardDeadLetter(opId) {
      dead = dead.filter((letter) => letter.opId !== opId);
      notify();
    },
  };
}
