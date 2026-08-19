import type { Conversation } from "../../packages/contracts/src/domain/conversations.js";
import type { Memory } from "../../packages/contracts/src/domain/memories.js";
import type { Task } from "../../packages/contracts/src/domain/tasks.js";
import {
  assertLocalProxyPath,
  LOCAL_PROXY_PREFIX,
  localProxyRequestInit,
} from "./local-proxy";

export type BrowserCurrentKind = "conversation" | "memory" | "task";

export type BrowserCurrent = {
  kind: BrowserCurrentKind;
  id: string;
  title: string;
  summary: string;
  updatedAt: number;
  source: string;
};

type ConversationView = Pick<
  Conversation,
  "id" | "title" | "overview" | "updatedAt"
> & {
  source?: string;
};

type MemoryView = Pick<Memory, "id" | "content" | "updatedAt"> & {
  source?: string;
};

type TaskView = Pick<
  Task,
  "id" | "description" | "completed" | "dueAt" | "updatedAt"
> & {
  source?: string;
};

export const DEMO_CURRENTS: readonly BrowserCurrent[] = [
  {
    kind: "conversation",
    id: "demo-conversation-today",
    title: "A quieter shape for the morning",
    summary: "The last conversation ended with a smaller, calmer Home surface.",
    updatedAt: Date.parse("2026-08-19T01:30:00.000Z"),
    source: "Local validation data",
  },
  {
    kind: "memory",
    id: "demo-memory-remember",
    title: "Keep the first screen spacious",
    summary: "A saved memory about letting quiet, important signals breathe.",
    updatedAt: Date.parse("2026-08-18T08:00:00.000Z"),
    source: "Local validation data",
  },
  {
    kind: "task",
    id: "demo-task-validate",
    title: "Validate the browser Home contract",
    summary: "Pending · a local testbed task",
    updatedAt: Date.parse("2026-08-17T04:20:00.000Z"),
    source: "Local validation data",
  },
];

export function projectConversation(value: ConversationView): BrowserCurrent {
  return {
    kind: "conversation",
    id: String(value.id),
    title: value.title,
    summary: value.overview,
    updatedAt: value.updatedAt,
    source: value.source ?? "Backend read",
  };
}

export function projectMemory(value: MemoryView): BrowserCurrent {
  return {
    kind: "memory",
    id: String(value.id),
    title: value.content,
    summary: "Synthesized memory",
    updatedAt: value.updatedAt,
    source: value.source ?? "Backend read",
  };
}

export function projectTask(value: TaskView): BrowserCurrent {
  return {
    kind: "task",
    id: String(value.id),
    title: value.description,
    summary: value.completed
      ? "Completed"
      : value.dueAt === null
      ? "Pending"
      : "Due soon",
    updatedAt: value.updatedAt,
    source: value.source ?? "Backend read",
  };
}

export function filterCurrents(
  items: readonly BrowserCurrent[],
  query: string
): BrowserCurrent[] {
  const normalized = query.trim().toLocaleLowerCase();
  if (normalized.length === 0) return [];
  return items.filter((item) =>
    `${item.kind}\n${item.title}\n${item.summary}`
      .toLocaleLowerCase()
      .includes(normalized)
  );
}

export type BackendReadResult = {
  items: BrowserCurrent[];
  unavailable: string[];
};

export type BrowserReadTransport = {
  get(path: string): Promise<unknown>;
};

type BrowserFetcher = (
  input: RequestInfo | URL,
  init?: RequestInit
) => Promise<Response>;

export function createSameOriginReadTransport(
  fetcher: BrowserFetcher = fetch
): BrowserReadTransport {
  return {
    async get(path: string) {
      if (!path.startsWith("/") || path.startsWith("//")) {
        throw new Error("Backend path must be origin-relative");
      }
      const proxyPath = path.startsWith(LOCAL_PROXY_PREFIX)
        ? path
        : `${LOCAL_PROXY_PREFIX}${path}`;
      const response = await fetcher(
        assertLocalProxyPath(proxyPath),
        localProxyRequestInit({
          credentials: "omit",
          headers: { Accept: "application/json" },
        })
      );
      if (!response.ok)
        throw new Error(`Backend read failed (${response.status})`);
      return response.json() as Promise<unknown>;
    },
  };
}

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function timestampValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function parseConversations(value: unknown): BrowserCurrent[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((entry) => {
    const item = record(entry);
    const structured = record(item?.structured);
    const id = stringValue(item?.id);
    const title = stringValue(structured?.title);
    const overview = stringValue(structured?.overview);
    const updatedAt = timestampValue(item?.updated_at);
    if (
      id === null ||
      title === null ||
      overview === null ||
      updatedAt === null
    )
      return [];
    return projectConversation({
      id: id as Conversation["id"],
      overview,
      source: stringValue(item?.source) ?? undefined,
      title,
      updatedAt,
    });
  });
}

function parseMemories(value: unknown): BrowserCurrent[] {
  const page = record(value);
  if (!Array.isArray(page?.items)) return [];
  return page.items.flatMap((entry) => {
    const item = record(entry);
    const id = stringValue(item?.id);
    const content = stringValue(item?.text);
    const updatedAt = timestampValue(item?.updatedAt ?? item?.createdAt);
    if (id === null || content === null || updatedAt === null) return [];
    return projectMemory({
      content,
      id: id as Memory["id"],
      source: "Backend read",
      updatedAt,
    });
  });
}

function parseTasks(value: unknown): BrowserCurrent[] {
  const page = record(value);
  if (!Array.isArray(page?.items)) return [];
  return page.items.flatMap((entry) => {
    const item = record(entry);
    const id = stringValue(item?.id);
    const description = stringValue(item?.description);
    const updatedAt = timestampValue(item?.updatedAt ?? item?.createdAt);
    if (id === null || description === null || updatedAt === null) return [];
    return projectTask({
      completed: item?.completed === true,
      description,
      dueAt: typeof item?.dueAt === "number" ? item.dueAt : null,
      id: id as Task["id"],
      source: stringValue(item?.source) ?? "Backend read",
      updatedAt,
    });
  });
}

export async function loadBackendCurrents(
  transport: BrowserReadTransport
): Promise<BackendReadResult> {
  const reads = await Promise.allSettled([
    transport.get("/v1/conversations?limit=50&offset=0"),
    transport.get("/v1/memories?limit=50"),
    transport.get("/v1/tasks"),
  ]);
  const parsers = [parseConversations, parseMemories, parseTasks];
  const labels = ["Conversations", "Memories", "Tasks"];
  const items: BrowserCurrent[] = [];
  const unavailable: string[] = [];
  reads.forEach((read, index) => {
    if (read.status === "fulfilled") {
      items.push(...parsers[index](read.value));
    } else {
      unavailable.push(labels[index]);
    }
  });
  return {
    items: items.sort((left, right) => right.updatedAt - left.updatedAt),
    unavailable,
  };
}
