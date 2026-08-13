// domain-pending(DIV-CHAT-TOOL-001)

import { isProxy } from "node:util/types";

import type { AgentRunEventStore } from "./agent-run-events";
import {
  createAgentToolRegistry,
  type AgentToolDefinition,
} from "./agent-tools";
import type { GatewayReadOnlyToolLoopOptions } from "./gateway-tool-loop";
import { TASKS_READ_PATH } from "../routes/tasks-read";

/** The only action-items tool advertised by the production-shaped gateway lane. */
export const GET_ACTION_ITEMS_TOOL_NAME = "get_action_items" as const;
export const GET_ACTION_ITEMS_MAX_ITEMS = 25 as const;

/**
 * Deliberately no-argument: the authenticated owner is taken from the
 * generation context, never from model-controlled input. The read itself is
 * bounded to the canonical tasks page limit.
 */
export const GET_ACTION_ITEMS_TOOL_SCHEMA = Object.freeze({
  name: GET_ACTION_ITEMS_TOOL_NAME,
  description: "Read the authenticated owner's current action items.",
  parameters: Object.freeze({
    type: "object" as const,
    additionalProperties: false as const,
    properties: Object.freeze({}),
    required: Object.freeze([] as readonly string[]),
  }),
});

export interface GetActionItemsToolRuntime {
  /** The in-process app fetch; this is the canonical authenticated read door. */
  readonly fetch: (request: Request) => Response | Promise<Response>;
  /** The only bearer credential used by the app-facing local composition. */
  readonly bearerToken: string;
  /** Bound to the authenticated service identity, never supplied by the model. */
  readonly ownerAccountId: string;
  readonly nowEpochMilliseconds: () => number;
  readonly agentRunEvents: AgentRunEventStore;
}

const ownPlainRecord = (value: unknown): Record<string, unknown> | null => {
  try {
    if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)) return null;
    const prototype = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== null) return null;
    const keys = Reflect.ownKeys(value);
    if (keys.some((key) => typeof key !== "string")) return null;
    const descriptors = Object.getOwnPropertyDescriptors(value);
    const result = Object.create(null) as Record<string, unknown>;
    for (const key of keys) {
      const descriptor = descriptors[key as string];
      if (descriptor === undefined || !("value" in descriptor)) return null;
      result[key as string] = descriptor.value;
    }
    return result;
  } catch {
    return null;
  }
};

const emptyObject = (value: unknown): boolean => {
  const record = ownPlainRecord(value);
  return record !== null && Object.keys(record).length === 0;
};

const boundedText = (value: unknown, max: number): value is string =>
  typeof value === "string" && value.length <= max && !/[\u0000-\u001f\u007f]/u.test(value);

interface ReadItem {
  readonly description: string;
  readonly completed: boolean;
  readonly dueAt: number | null;
}

interface ReadPage {
  readonly items: readonly ReadItem[];
  readonly absence: unknown;
  readonly hasMore: boolean;
  readonly complete: boolean;
}

const parseReadPage = (value: unknown): ReadPage | null => {
  const page = ownPlainRecord(value);
  if (page === null || !Array.isArray(page.items) || page.items.length > GET_ACTION_ITEMS_MAX_ITEMS) return null;
  const window = ownPlainRecord(page.window);
  const completeness = ownPlainRecord(page.completeness);
  if (window === null || completeness === null
    || typeof window.hasMore !== "boolean" || typeof window.complete !== "boolean"
    || (completeness.status !== "complete" && completeness.status !== "incomplete")) return null;
  const items: ReadItem[] = [];
  for (const raw of page.items) {
    const item = ownPlainRecord(raw);
    if (item === null || !boundedText(item.description, 4_096)
      || typeof item.completed !== "boolean"
      || (item.dueAt !== null && !(typeof item.dueAt === "number" && Number.isSafeInteger(item.dueAt)))) {
      return null;
    }
    items.push(Object.freeze({
      description: item.description,
      completed: item.completed,
      dueAt: item.dueAt as number | null,
    }));
  }
  return Object.freeze({
    items: Object.freeze(items),
    absence: page.absence ?? null,
    hasMore: window.hasMore,
    complete: completeness.status === "complete" && window.complete,
  });
};

const summaryFor = (page: ReadPage): string => {
  if (page.items.length === 0) {
    return page.absence !== null && typeof page.absence === "object"
      ? "No action items were returned; the canonical read reports a query gap."
      : "No action items are currently available.";
  }
  const previews = page.items.slice(0, 3).map((item) => {
    const status = item.completed ? "done" : "open";
    const description = item.description.replace(/\s+/gu, " ").trim().slice(0, 54);
    return `${status}: ${description}`;
  });
  const qualifiers = [
    page.items.length > previews.length ? `+${page.items.length - previews.length} more on page` : null,
    page.hasMore ? "more available" : null,
    !page.complete ? "read incomplete" : null,
  ].filter((value): value is string => value !== null);
  const suffix = qualifiers.length > 0 ? ` (${qualifiers.join(", ")})` : "";
  const summary = `Action items (${page.items.length}): ${previews.join("; ")}${suffix}`;
  return summary.length <= 240 ? summary : `${summary.slice(0, 237)}...`;
};

const readActionItems = async (
  runtime: GetActionItemsToolRuntime,
): Promise<{ readonly items: readonly ReadItem[]; readonly absence: unknown }> => {
  const request = new Request(`http://omi.local${TASKS_READ_PATH}?limit=${GET_ACTION_ITEMS_MAX_ITEMS}`, {
    method: "GET",
    headers: {
      authorization: `Bearer ${runtime.bearerToken}`,
      // Keep this request on the same compatibility floor as other app reads.
      "cache-control": "no-store",
    },
  });
  const response = await runtime.fetch(request);
  if (!response.ok) throw new Error("canonical tasks read unavailable");
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new Error("canonical tasks read returned invalid data");
  }
  const page = ownPlainRecord(body);
  if (page === null) throw new Error("canonical tasks read returned invalid data");
  const parsed = parseReadPage(page);
  if (parsed === null) throw new Error("canonical tasks read returned invalid data");
  return parsed;
};

export const createGetActionItemsTool = (
  runtime: GetActionItemsToolRuntime,
): AgentToolDefinition => Object.freeze({
  schemaVersion: 1,
  name: GET_ACTION_ITEMS_TOOL_NAME,
  risk: "safe",
  timeoutMs: 5_000,
  retryable: true,
  displaySummary: "Read action items",
  validateInput: emptyObject,
  execute: async (_input, control) => {
    if (control.cancelled) throw new Error("tool cancelled");
    const started = runtime.nowEpochMilliseconds();
    const result = await readActionItems(runtime);
    if (control.cancelled) throw new Error("tool cancelled");
    const ended = runtime.nowEpochMilliseconds();
    const durationMs = Number.isSafeInteger(started) && Number.isSafeInteger(ended)
      ? Math.max(0, ended - started)
      : 0;
    return Object.freeze({
      summary: summaryFor(result),
      durationMs,
      retryable: true,
    });
  },
});

export const createGetActionItemsToolLoop = (
  runtime: GetActionItemsToolRuntime,
): GatewayReadOnlyToolLoopOptions => Object.freeze({
  registry: createAgentToolRegistry([createGetActionItemsTool(runtime)]),
  tool: GET_ACTION_ITEMS_TOOL_SCHEMA,
  agentRunEvents: runtime.agentRunEvents,
  nowEpochMilliseconds: runtime.nowEpochMilliseconds,
});
