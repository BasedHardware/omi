import type { Hono } from "hono";

import type { DevPrincipal } from "../auth/dev-token";
import {
  projectAgentRunTimeline,
  type AgentRunEvent,
  type AgentRunEventStore,
  type AgentRunVisibleTimelineEvent,
} from "../chat/agent-run-events";
import {
  realtimeChatGenerationScheduler,
  type ChatGenerationScheduler,
} from "../chat/generation-source";

const JSON_HEADERS = Object.freeze({
  "cache-control": "no-store",
  "content-type": "application/json",
});
const SSE_HEADERS = Object.freeze({
  "cache-control": "no-cache, no-store",
  connection: "keep-alive",
  "content-type": "text/event-stream; charset=utf-8",
});
const RETENTION_EXPIRED = JSON.stringify({ error: { code: "generation_replay_expired", retryable: false, action: "refresh_history" } });

export interface ChatAgentRunRouteDependencies {
  readonly resolvePrincipal: (token: string) => DevPrincipal | null;
  readonly events: AgentRunEventStore;
  readonly resolveGenerationOwner: (accountId: string, runId: string) => boolean;
  readonly scheduler?: ChatGenerationScheduler;
  readonly pollIntervalMs?: number;
  readonly maxBatchEvents?: number;
}

const response = (body: string, status: number, headers: Readonly<Record<string, string>> = JSON_HEADERS): Response =>
  new Response(body, { status, headers });
const unauthorized = (): Response => response(JSON.stringify({ error: { code: "unauthorized", retryable: false } }), 401);
const notFound = (): Response => response(JSON.stringify({ error: { code: "not_found", retryable: false } }), 404);
const badRequest = (): Response => response(JSON.stringify({ error: { code: "bad_request", retryable: false } }), 400);
const replayExpired = (): Response => response(RETENTION_EXPIRED, 410);

const encodeEvent = (event: AgentRunVisibleTimelineEvent): Uint8Array =>
  new TextEncoder().encode(`event: ${event.kind}\nid: ${event.eventId}\ndata: ${JSON.stringify(event)}\n\n`);

const streamAgentEvents = (input: {
  readonly events: AgentRunEventStore;
  readonly runId: string;
  readonly accountId: string;
  readonly token: string;
  readonly resolvePrincipal: (token: string) => DevPrincipal | null;
  readonly resolveGenerationOwner: (accountId: string, runId: string) => boolean;
  readonly initial: readonly AgentRunEvent[];
  readonly visibleById: ReadonlyMap<string, AgentRunVisibleTimelineEvent>;
  readonly afterEventId: string | null;
  readonly signal: AbortSignal;
  readonly scheduler: ChatGenerationScheduler;
  readonly pollIntervalMs: number;
  readonly maxBatchEvents: number;
}): Response => {
  let timer: unknown | null = null;
  let stopped = false;
  let cursor = input.afterEventId;
  const body = new ReadableStream<Uint8Array>({
    start(controller): void {
      const close = (): void => {
        if (stopped) return;
        stopped = true;
        if (timer !== null) input.scheduler.clearTimeout(timer);
        controller.close();
      };
      // Keep the producer side bounded. A slow reader can reconnect from the
      // last durable event instead of allowing an unbounded in-memory queue.
      const queueLimit = Math.max(input.maxBatchEvents * 8, input.maxBatchEvents);
      const queue = input.initial.slice(0, queueLimit);
      let overflowed = input.initial.length > queue.length;
      type EmitResult = "closed" | "blocked" | "progress";
      const emit = (): EmitResult => {
        if (controller.desiredSize !== null && controller.desiredSize <= 0) return "blocked";
        const batch = queue.splice(0, input.maxBatchEvents);
        for (const [index, event] of batch.entries()) {
          if (controller.desiredSize !== null && controller.desiredSize <= 0) {
            queue.unshift(...batch.slice(index));
            return "blocked";
          }
          cursor = event.eventId;
          const visible = input.visibleById.get(event.eventId);
          if (visible !== undefined) controller.enqueue(encodeEvent(visible));
          if (event.kind === "terminal") {
            close();
            return "closed";
          }
        }
        return "progress";
      };
      const schedule = (poll: () => void): void => {
        if (stopped || timer !== null) return;
        try {
          timer = input.scheduler.setTimeout(() => {
            timer = null;
            poll();
          }, Math.max(1, input.pollIntervalMs));
        } catch {
          close();
        }
      };
      const poll = (): void => {
        if (stopped) return;
        if (input.signal.aborted) {
          close();
          return;
        }
        try {
          const principal = input.resolvePrincipal(input.token);
          if (principal === null || principal.uid !== input.accountId
            || !input.resolveGenerationOwner(input.accountId, input.runId)) {
            close();
            return;
          }
        } catch {
          close();
          return;
        }
        if (queue.length === 0) {
          const next = input.events.list(input.runId);
          const start = cursor === null ? 0 : next.findIndex((event) => event.eventId === cursor) + 1;
          if (cursor !== null && start === 0) {
            close();
            return;
          }
          const available = next.slice(start);
          const capacity = queueLimit - queue.length;
          queue.push(...available.slice(0, capacity));
          overflowed ||= available.length > capacity;
        }
        const result = emit();
        if (result === "closed") return;
        if (result === "blocked") {
          // A reader that has not consumed the previous chunk must not cause
          // a microtask spin. Retry only on the injected positive scheduler
          // cadence; reconnect remains the bounded escape hatch.
          schedule(poll);
          return;
        }
        if (queue.length === 0) {
          if (overflowed) {
            close();
            return;
          }
          schedule(poll);
        } else {
          queueMicrotask(poll);
        }
      };
      poll();
    },
    cancel(): void {
      stopped = true;
      if (timer !== null) input.scheduler.clearTimeout(timer);
    },
  });
  return new Response(body, { status: 200, headers: SSE_HEADERS });
};

export const registerChatAgentRunRoutes = (
  app: Hono,
  deps: ChatAgentRunRouteDependencies,
): void => {
  const scheduler = deps.scheduler ?? realtimeChatGenerationScheduler;
  const pollIntervalMs = deps.pollIntervalMs ?? 5;
  const maxBatchEvents = deps.maxBatchEvents ?? 16;
  if (!Number.isSafeInteger(pollIntervalMs) || pollIntervalMs < 1
    || !Number.isSafeInteger(maxBatchEvents) || maxBatchEvents < 1 || maxBatchEvents > 128) {
    throw new TypeError("invalid agent run stream policy");
  }
  app.get("/v1/chat-generations/:generationId/agent-events", (context) => {
    const authorization = context.req.header("authorization");
    if (authorization === undefined || !authorization.startsWith("Bearer ")) return unauthorized();
    const token = authorization.slice("Bearer ".length);
    const principal = deps.resolvePrincipal(token);
    if (principal === null) return unauthorized();
    const runId = context.req.param("generationId");
    if (!deps.resolveGenerationOwner(principal.uid, runId)) return notFound();
    const events = deps.events.list(runId);
    const timeline = events.length === 0 ? null : projectAgentRunTimeline(events);
    if (timeline === null) return replayExpired();
    const lastEventId = context.req.header("last-event-id") ?? null;
    if (lastEventId === "") return badRequest();
    if (lastEventId !== null && !events.some((event) => event.eventId === lastEventId)) return replayExpired();
    const terminal = events.findLast((event) => event.kind === "terminal");
    const afterIndex = lastEventId === null ? -1 : events.findIndex((event) => event.eventId === lastEventId);
    const initial = lastEventId === null
      ? events
      : events.slice(afterIndex + 1).length > 0
        ? events.slice(afterIndex + 1)
        : terminal === undefined ? [] : [terminal];
    return streamAgentEvents({
      events: deps.events,
      runId,
      accountId: principal.uid,
      token,
      resolvePrincipal: deps.resolvePrincipal,
      resolveGenerationOwner: deps.resolveGenerationOwner,
      initial,
      visibleById: new Map(timeline.events.map((event) => [event.eventId, event])),
      afterEventId: lastEventId,
      signal: context.req.raw.signal,
      scheduler,
      pollIntervalMs,
      maxBatchEvents,
    });
  });
};
