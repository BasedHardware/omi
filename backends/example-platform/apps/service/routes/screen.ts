// domain-pending(DIV-DOMAPPS-007)
// domain-pending(UNK-DOMAPPS-001)

import type { Hono } from "hono";

import type { DevPrincipal } from "../auth/dev-token";
import type { ServedCounter } from "../observability/served-count";
import type { ScreenEmbeddingSource } from "../screen/embedding-source";
import type { ScreenStore } from "../stores/screen-store";
import {
  SCREEN_INGEST_MAX_FRAMES,
  isScreenCalendarDay,
} from "../stores/screen-store";

const JSON_HEADERS = Object.freeze({
  "cache-control": "no-store",
  "content-type": "application/json; charset=utf-8",
});

export const SCREEN_FRAMES_PATH = "/v1/screen/frames";
export const SCREEN_TIMELINE_PATH = "/v1/screen/timeline";
export const SCREEN_DAYS_PATH = "/v1/screen/days";
export const SCREEN_SEARCH_PATH = "/v1/screen/search";
export const SCREEN_RETENTION_PATH = "/v1/screen/retention";
export const SCREEN_RETIRED_PATH = "/v1/screen/retired";

export interface ScreenRouteDependencies {
  readonly resolvePrincipal: (token: string) => DevPrincipal | null;
  readonly store: ScreenStore;
  readonly embeddings: ScreenEmbeddingSource;
  readonly counter: ServedCounter;
  readonly now: () => string;
  readonly accountTimezone: string;
}

const jsonResponse = (value: unknown, status = 200): Response =>
  new Response(JSON.stringify(value), { status, headers: JSON_HEADERS });

const errorResponse = (status: number, code: string): Response =>
  jsonResponse({ error: code }, status);

const bearerToken = (header: string | undefined): string | null => {
  if (typeof header !== "string" || !header.startsWith("Bearer ")) return null;
  const token = header.slice("Bearer ".length);
  return token.length > 0 ? token : null;
};

const authenticate = (
  header: string | undefined,
  resolvePrincipal: ScreenRouteDependencies["resolvePrincipal"],
): DevPrincipal | null => {
  const token = bearerToken(header);
  return token === null ? null : resolvePrincipal(token);
};

const requestUrl = (raw: Request): URL | null => {
  try {
    return new URL(raw.url);
  } catch {
    return null;
  }
};

const parseLimit = (value: string | null, fallback: number, max: number): number => {
  const parsed = Number.parseInt(value ?? "", 10);
  if (!Number.isFinite(parsed) || parsed < 0) return fallback;
  return Math.min(parsed, max);
};

const readJson = async (request: Request): Promise<unknown> => {
  const body = await request.text();
  if (body.length === 0) return {};
  return JSON.parse(body) as unknown;
};

const isPlainObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** Registers the authenticated screen ingest, query, and retention routes. */
export const registerScreenRoutes = (app: Hono, deps: ScreenRouteDependencies): void => {
  app.post(SCREEN_FRAMES_PATH, async (context) => {
    const principal = authenticate(context.req.header("authorization"), deps.resolvePrincipal);
    if (principal === null) {
      deps.counter.recordDomainRead("denied");
      return errorResponse(401, "unauthorized");
    }
    let payload: unknown;
    try {
      payload = await readJson(context.req.raw);
    } catch {
      return errorResponse(400, "invalid_json");
    }
    if (!isPlainObject(payload)) return errorResponse(400, "invalid_body");
    if (!Array.isArray(payload.frames) || payload.frames.length === 0
      || payload.frames.length > SCREEN_INGEST_MAX_FRAMES) {
      return errorResponse(400, "invalid_frames");
    }
    try {
      const outcome = deps.store.ingest({
        accountId: principal.uid,
        captureSessionId: payload.capture_session_id as string,
        frames: payload.frames as never,
      });
      return jsonResponse({
        capture_session_id: outcome.captureSessionId,
        accepted: outcome.accepted,
        duplicate: outcome.duplicate,
        frames: outcome.frames,
      }, 201);
    } catch (error) {
      const message = error instanceof Error ? error.message : "";
      if (message === "screen frame id conflict") return errorResponse(409, "conflict");
      if (message === "screen pixels must not cross the wire") {
        return errorResponse(400, "pixels_forbidden");
      }
      return errorResponse(400, "invalid_frame");
    }
  });

  app.get(SCREEN_TIMELINE_PATH, (context) => {
    const principal = authenticate(context.req.header("authorization"), deps.resolvePrincipal);
    if (principal === null) {
      deps.counter.recordDomainRead("denied");
      return errorResponse(401, "unauthorized");
    }
    const url = requestUrl(context.req.raw);
    if (url === null) {
      deps.counter.recordDomainRead("denied");
      return errorResponse(400, "invalid_url");
    }
    const day = url.searchParams.get("day") ?? "";
    if (!isScreenCalendarDay(day)) {
      deps.counter.recordDomainRead("denied");
      return errorResponse(400, "day_required");
    }
    deps.counter.recordDomainRead("served");
    return jsonResponse(deps.store.listTimeline(principal.uid, day, deps.accountTimezone, {
      limit: parseLimit(url.searchParams.get("limit"), 100, 500),
      offset: parseLimit(url.searchParams.get("offset"), 0, 1_000_000),
    }));
  });

  app.get(SCREEN_DAYS_PATH, (context) => {
    const principal = authenticate(context.req.header("authorization"), deps.resolvePrincipal);
    if (principal === null) {
      deps.counter.recordDomainRead("denied");
      return errorResponse(401, "unauthorized");
    }
    deps.counter.recordDomainRead("served");
    return jsonResponse(deps.store.daySpan(principal.uid, deps.accountTimezone));
  });

  app.get(SCREEN_SEARCH_PATH, async (context) => {
    const principal = authenticate(context.req.header("authorization"), deps.resolvePrincipal);
    if (principal === null) {
      deps.counter.recordDomainRead("denied");
      return errorResponse(401, "unauthorized");
    }
    const url = requestUrl(context.req.raw);
    if (url === null) {
      deps.counter.recordDomainRead("denied");
      return errorResponse(400, "invalid_url");
    }
    const query = url.searchParams.get("q") ?? "";
    const limit = parseLimit(url.searchParams.get("limit"), 20, 100);
    const hits = deps.store.searchText(principal.uid, query, { limit });
    const semantic = await deps.embeddings.search({
      accountId: principal.uid,
      query,
      limit,
    });
    deps.counter.recordDomainRead("served");
    return jsonResponse({
      query,
      hits: hits.hits,
      semantic,
    });
  });

  app.get(SCREEN_RETENTION_PATH, (context) => {
    const principal = authenticate(context.req.header("authorization"), deps.resolvePrincipal);
    if (principal === null) {
      deps.counter.recordDomainRead("denied");
      return errorResponse(401, "unauthorized");
    }
    deps.counter.recordDomainRead("served");
    return jsonResponse(deps.store.readRetention(principal.uid));
  });

  app.put(SCREEN_RETENTION_PATH, async (context) => {
    const principal = authenticate(context.req.header("authorization"), deps.resolvePrincipal);
    if (principal === null) return errorResponse(401, "unauthorized");
    let payload: unknown;
    try {
      payload = await readJson(context.req.raw);
    } catch {
      return errorResponse(400, "invalid_json");
    }
    const days = isPlainObject(payload) ? payload.days : undefined;
    // Invalid values fail safe to unlimited (0) rather than a deleting window.
    const setting = deps.store.writeRetention(principal.uid, days, deps.now());
    return jsonResponse(setting);
  });

  app.get(SCREEN_RETIRED_PATH, (context) => {
    const principal = authenticate(context.req.header("authorization"), deps.resolvePrincipal);
    if (principal === null) {
      deps.counter.recordDomainRead("denied");
      return errorResponse(401, "unauthorized");
    }
    deps.counter.recordDomainRead("served");
    return jsonResponse({
      retired: deps.store.listRetiredFrameRefs(principal.uid),
    });
  });
};
