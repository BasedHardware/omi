import { parseRecordId, type DeadLetter, type Memory, type MemoryPatch } from "@omi-core/contracts";
import type { QueuePhase, QueueStatus } from "@omi-core/sync";
import type { RefreshPhase, StoreStatus } from "@omi-core/domain";

export type ProductionMemoryStore = {
  list(): Promise<Memory[]>;
  status(): StoreStatus;
  deadLetters(): Promise<DeadLetter[]>;
  subscribe(listener: () => void): () => void;
  refresh(): Promise<void>;
  create(content: string, opts?: { visibility?: "public" | "private" }): Promise<void>;
  patch(id: Memory["id"], patch: MemoryPatch): Promise<void>;
  delete(id: Memory["id"]): Promise<void>;
  discardDeadLetter(opId: string): Promise<void>;
};

const FIXED_NOW = Date.UTC(2026, 7, 7, 12, 0, 0);
function id(value: string): Memory["id"] {
  const parsed = parseRecordId(value);
  if (!parsed) throw new Error(`fixture id is not a valid RecordId: ${value}`);
  return parsed.id;
}

function memory(value: Partial<Memory> & Pick<Memory, "id" | "content">): Memory {
  return {
    id: value.id,
    content: value.content,
    category: value.category ?? "manual",
    visibility: value.visibility ?? "private",
    reviewed: value.reviewed ?? true,
    userReview: value.userReview ?? null,
    createdAt: value.createdAt ?? FIXED_NOW - 86_400_000,
    updatedAt: value.updatedAt ?? FIXED_NOW - 3_600_000,
    revision: value.revision ?? "fixture-r1",
    locked: value.locked ?? false,
  };
}

function baseRows(): Memory[] {
  return [
    memory({ id: id("fixture-memory-one"), content: "notes: Keep the morning review short, focused, and ordered around the one decision that matters most.", category: "manual", visibility: "private" }),
    memory({ id: id("fixture-memory-two"), content: "preferences: Omi should surface saved context before asking the same question again.", category: "review", visibility: "public" }),
    memory({ id: id("fixture-memory-three"), content: "work: The current project is a desktop-first redesign with shared product logic and thin native shells.", updatedAt: FIXED_NOW - 2 * 86_400_000, visibility: "private" }),
    memory({ id: id("fixture-memory-four"), content: "communication: Concise updates are preferred when the next action is already clear.", updatedAt: FIXED_NOW - 4 * 86_400_000, visibility: "private" }),
    memory({ id: id("fixture-memory-five"), content: "product: Fast iteration and native feel are both release criteria; neither is a trade for the other.", updatedAt: FIXED_NOW - 7 * 86_400_000, visibility: "public" }),
  ];
}

function deadLetter(): DeadLetter {
  return {
    opId: "fixture-dead-001",
    recordId: id("fixture-memory-one"),
    domain: "memories",
    summary: "Edit memory visibility",
    failure: { kind: "permanent", reason: "validation", detail: "The saved memory was rejected." },
    deadAt: FIXED_NOW,
  };
}

export const FIXTURE_STATES = [
  "loading", "empty", "unavailable", "saved-failed", "queued", "sending", "retrying", "needs-auth", "dead", "normal", "locked", "long",
] as const;
export type FixtureState = (typeof FIXTURE_STATES)[number];

function queue(phase: QueuePhase): QueueStatus {
  return { phase, pendingCount: phase === "idle" ? 0 : phase === "needs-auth" ? 2 : 1 };
}

export function fixtureStore(state: FixtureState): ProductionMemoryStore {
  let rows = state === "empty" || state === "unavailable" || state === "loading" ? [] : baseRows();
  if (state === "locked") rows = [memory({ id: id("fixture-locked-memory"), content: "This is a shortened preview of protected memory…", locked: true, visibility: "private" })];
  if (state === "long") rows = [memory({ id: id("fixture-long-memory"), content: "research: " + "A saved memory with enough detail to exercise the long-content disclosure. ".repeat(10) })];
  const refreshPhase: RefreshPhase = state === "loading" ? "initial-loading" : state === "unavailable" ? "unavailable" : state === "saved-failed" ? "saved-but-refresh-failed" : "ready";
  const status: StoreStatus = { refresh: { phase: refreshPhase, hasSavedData: rows.length > 0 }, queue: queue(state === "queued" ? "queued" : state === "sending" ? "sending" : state === "retrying" ? "retrying" : state === "needs-auth" ? "needs-auth" : "idle") };
  let dead = state === "dead" ? [deadLetter()] : [];
  const listeners = new Set<() => void>();
  const notify = () => listeners.forEach((listener) => listener());
  return {
    async list() { return rows; },
    status() { return status; },
    async deadLetters() { return dead; },
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    async refresh() { notify(); },
    async create(content, opts) {
      const suffix = ["one", "two", "three", "four", "five"][rows.length] ?? "more";
      rows = [memory({ id: id(`fixture-created-${suffix}`), content, visibility: opts?.visibility ?? "private", createdAt: FIXED_NOW, updatedAt: FIXED_NOW }), ...rows];
      notify();
    },
    async patch(memoryId, patch) { rows = rows.map((row) => row.id === memoryId ? { ...row, ...patch, updatedAt: FIXED_NOW } : row); notify(); },
    async delete(memoryId) { rows = rows.filter((row) => row.id !== memoryId); notify(); },
    async discardDeadLetter(opId) { dead = dead.filter((letter) => letter.opId !== opId); notify(); },
  };
}
