import { parseRecordId, type DeadLetter, type Task } from "@omi-core/contracts";
import type { QueuePhase, QueueStatus } from "@omi-core/sync";
import type { RefreshPhase, StoreStatus } from "@omi-core/domain";
import type { ProductionTaskStore } from "./ProductionStores.js";

export const FIXED_NOW = Date.UTC(2026, 7, 7, 12, 0, 0);
const DAY_MS = 86_400_000;

function id(value: string): Task["id"] {
  const parsed = parseRecordId(value);
  if (!parsed) throw new Error(`fixture id is not a valid RecordId: ${value}`);
  return parsed.id;
}

function task(value: Partial<Task> & Pick<Task, "id" | "description">, now: number): Task {
  return {
    id: value.id,
    description: value.description,
    completed: value.completed ?? false,
    completedAt: value.completedAt ?? null,
    dueAt: value.dueAt ?? null,
    owner: value.owner ?? null,
    source: value.source ?? "user",
    provenance: value.provenance ?? [],
    sortOrder: value.sortOrder ?? 0,
    indentLevel: value.indentLevel ?? 0,
    createdAt: value.createdAt ?? now - 3_600_000,
    updatedAt: value.updatedAt ?? now - 900_000,
    revision: value.revision ?? "fixture-task-r1",
  };
}

function dayStart(now: number): number {
  const date = new Date(now);
  return Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
}

function baseRows(now: number): Task[] {
  const today = dayStart(now);
  return [
    task({ id: id("fixture-task-today"), description: "Review the first captured note", dueAt: today + 15 * 3_600_000, source: "user" }, now),
    task({ id: id("fixture-task-design"), description: "Compare the desktop render with the approved reference", dueAt: today + 16 * 3_600_000 }, now),
    task({ id: id("fixture-task-glass"), description: "Validate the native glass window on a light and dark desktop", dueAt: today + 17 * 3_600_000 }, now),
    task({ id: id("fixture-task-copy"), description: "Tighten the empty and offline product copy", dueAt: today + 18 * 3_600_000 }, now),
    task({ id: id("fixture-task-focus"), description: "Check keyboard focus across every task row", dueAt: today + 19 * 3_600_000 }, now),
    task({ id: id("fixture-task-details"), description: "Review the conversation detail hierarchy", dueAt: today + 20 * 3_600_000 }, now),
    task({ id: id("fixture-task-empty"), description: "Check empty, offline, and retry states", dueAt: today + 21 * 3_600_000 }, now),
    task({ id: id("fixture-task-nav"), description: "Verify navigation and keyboard shortcuts", dueAt: today + 22 * 3_600_000 }, now),
    task({ id: id("fixture-task-handoff"), description: "Prepare the desktop review handoff", dueAt: today + 23 * 3_600_000 }, now),
    task({ id: id("fixture-task-finished"), description: "Build the deterministic UI fixture matrix", dueAt: today + 23.5 * 3_600_000, completed: true, completedAt: now - 1_800_000 }, now),
    task({ id: id("fixture-task-tomorrow"), description: "Send the short project update", dueAt: today + DAY_MS + 12 * 3_600_000, source: "assistant", provenance: ["assistant"] }, now),
    task({ id: id("fixture-task-polish"), description: "Polish the conversation detail layout", dueAt: today + DAY_MS + 14 * 3_600_000 }, now),
    task({ id: id("fixture-task-later"), description: "Archive the completed checklist", dueAt: today + 3 * DAY_MS, completed: true, completedAt: now - 1_800_000, source: "" }, now),
    task({ id: id("fixture-task-release"), description: "Prepare the review build handoff", dueAt: today + 4 * DAY_MS }, now),
    task({ id: id("fixture-task-unscheduled"), description: "Capture a due date when one is known", dueAt: null, source: "" }, now),
  ];
}

function deadLetter(now: number): DeadLetter {
  return {
    opId: "fixture-dead-task-001",
    recordId: id("fixture-task-today"),
    domain: "tasks",
    summary: "Edit task description",
    failure: { kind: "permanent", reason: "validation", detail: "The task change was rejected." },
    deadAt: now,
  };
}

export const FIXTURE_STATES = [
  "loading", "empty", "unavailable", "saved-failed", "queued", "sending", "retrying", "needs-auth", "dead", "normal", "long", "operation-failed",
] as const;
export type FixtureState = (typeof FIXTURE_STATES)[number];

function queue(phase: QueuePhase): QueueStatus {
  return { phase, pendingCount: phase === "idle" ? 0 : phase === "needs-auth" ? 2 : 1 };
}

export function fixtureStore(state: FixtureState, now = FIXED_NOW): ProductionTaskStore {
  let rows = state === "empty" || state === "unavailable" || state === "loading" ? [] : baseRows(now);
  if (state === "long") {
    rows = [task({
      id: id("fixture-long-task"),
      description: "Prepare a detailed handoff that remains readable when the task title is unusually long. ".repeat(10),
      dueAt: dayStart(now) + 2 * DAY_MS,
      source: "assistant",
      provenance: ["assistant"],
    }, now)];
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
  const status: StoreStatus = {
    refresh: { phase: refreshPhase, hasSavedData: rows.length > 0 },
    queue: queue(queuePhase),
  };
  let dead = state === "dead" ? [deadLetter(now)] : [];
  let refreshFailuresRemaining = state === "operation-failed" ? 1 : 0;
  const listeners = new Set<() => void>();
  const notify = (): void => { listeners.forEach((listener) => listener()); };

  return {
    async list() { return rows; },
    status() { return status; },
    async deadLetters() { return dead; },
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    async refresh() {
      if (refreshFailuresRemaining > 0) {
        refreshFailuresRemaining -= 1;
        throw new Error("fixture refresh failed");
      }
      notify();
    },
    async create(description, dueAt) {
      if (state === "operation-failed") throw new Error("fixture operation failed");
      const suffix = ["one", "two", "three", "four", "five"][rows.length] ?? "more";
      rows = [task({ id: id(`fixture-created-${suffix}`), description, dueAt: dueAt ?? null, createdAt: now, updatedAt: now, source: "user" }, now), ...rows];
      notify();
    },
    async patch(taskId, patch) {
      if (state === "operation-failed") throw new Error("fixture operation failed");
      rows = rows.map((row) => row.id === taskId ? {
        ...row,
        ...patch,
        completedAt: patch.completed === undefined ? row.completedAt : patch.completed ? now : null,
        updatedAt: now,
      } : row);
      notify();
    },
    async delete(taskId) {
      if (state === "operation-failed") throw new Error("fixture operation failed");
      rows = rows.filter((row) => row.id !== taskId);
      notify();
    },
    async discardDeadLetter(opId) { dead = dead.filter((letter) => letter.opId !== opId); notify(); },
  };
}
