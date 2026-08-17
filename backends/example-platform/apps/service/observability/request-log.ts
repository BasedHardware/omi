import { randomUUID } from "node:crypto";
import type { Hono } from "hono";

import { isQaEvidenceRunId } from "./producer-evidence";
import {
  createRuntimeLogSink,
  type RuntimeLogInput,
  type RuntimeLogLevel,
  type RuntimeLogSink,
} from "./runtime-log";

export const SERVICE_REQUEST_EVENT = "service.request";
export const SERVICE_REQUEST_DROPPED_EVENT = "service.request.dropped";

export interface ServiceRequestLogOptions {
  readonly dir?: string;
  readonly sink?: RuntimeLogSink;
  readonly resolveOwnerAccountId?: (request: Request) => string | null;
  readonly nowMs?: () => number;
  readonly nowIso?: () => string;
  readonly createRequestId?: () => string;
  readonly maxBytes?: number;
}

const MAX_PATH_CHARS = 256;
const MAX_QUERY_KEYS = 32;
const MAX_QUERY_KEY_CHARS = 64;
const BEARER = "Bearer ";

export const bearerTokenFromAuthorization = (header: string | null): string | null => {
  if (header === null || !header.startsWith(BEARER)) return null;
  const token = header.slice(BEARER.length);
  return token.length > 0 ? token : null;
};

const requestPath = (url: string): string => {
  try {
    return new URL(url).pathname.slice(0, MAX_PATH_CHARS);
  } catch {
    return "/";
  }
};

const queryKeyNames = (url: string): readonly string[] => {
  try {
    const keys: string[] = [];
    const seen = new Set<string>();
    for (const key of new URL(url).searchParams.keys()) {
      if (seen.has(key) || keys.length >= MAX_QUERY_KEYS) continue;
      seen.add(key);
      keys.push(key.slice(0, MAX_QUERY_KEY_CHARS));
    }
    return Object.freeze(keys);
  } catch {
    return Object.freeze([]);
  }
};

const headerValue = (request: Request, name: string): string | null => {
  try {
    const value = request.headers?.get(name);
    return typeof value === "string" ? value : null;
  } catch {
    return null;
  }
};

const abortSignal = (request: Request): AbortSignal | null => {
  const signal = request.signal;
  if (signal === null || signal === undefined) return null;
  return signal;
};

const runIdFromRequest = (request: Request): string | null => {
  const explicit = headerValue(request, "x-omi-run-id");
  if (isQaEvidenceRunId(explicit)) return explicit;
  const clientId = headerValue(request, "x-omi-client-id");
  if (clientId === null) return null;
  const separator = clientId.indexOf("::");
  if (separator < 1) return null;
  const combined = clientId.slice(0, separator);
  return isQaEvidenceRunId(combined) ? combined : null;
};

const levelForStatus = (status: number): RuntimeLogLevel => {
  if (status >= 500) return "error";
  if (status >= 400) return "warn";
  return "info";
};

const observeRequest = async (
  request: Request,
  dispatch: () => Response | Promise<Response>,
  options: ServiceRequestLogOptions,
  sink: RuntimeLogSink,
): Promise<Response> => {
  const nowMs = options.nowMs ?? (() => Date.now());
  const started = nowMs();
  const method = request.method;
  const path = requestPath(request.url);
  const query_keys = queryKeyNames(request.url);
  const request_id = (options.createRequestId ?? randomUUID)();
  const run_id = runIdFromRequest(request);
  let owner_account_id: string | null = null;
  try {
    owner_account_id = options.resolveOwnerAccountId?.(request) ?? null;
  } catch {
    owner_account_id = null;
  }
  const write = (input: RuntimeLogInput): void => {
    try {
      sink.write(input);
    } catch {
      // Request logging must never change the HTTP outcome.
    }
  };
  let finished = false;
  const duration = (): number => {
    const ended = nowMs();
    const value = ended >= started ? ended - started : 0;
    return Number.isFinite(value) ? Math.min(Math.max(0, Math.round(value)), 86_400_000) : 0;
  };
  const fields = (): Pick<
    RuntimeLogInput,
    "method" | "path" | "query_keys" | "owner_account_id" | "run_id" | "request_id"
  > => ({
    method,
    path,
    query_keys,
    owner_account_id,
    run_id,
    request_id,
  });
  const onAbort = (): void => {
    if (finished) return;
    finished = true;
    write({
      proc: "service",
      level: "warn",
      event: SERVICE_REQUEST_DROPPED_EVENT,
      duration_ms: duration(),
      ...fields(),
    });
  };
  const signal = abortSignal(request);
  if (signal?.aborted === true) {
    onAbort();
    return dispatch();
  }
  if (signal !== null && typeof signal.addEventListener === "function") {
    signal.addEventListener("abort", onAbort, { once: true });
  }
  try {
    const response = await dispatch();
    if (!finished) {
      finished = true;
      const status = response.status;
      write({
        proc: "service",
        level: levelForStatus(status),
        event: SERVICE_REQUEST_EVENT,
        status,
        duration_ms: duration(),
        ...fields(),
      });
    }
    return response;
  } catch (error) {
    if (!finished) {
      finished = true;
      write({
        proc: "service",
        level: "error",
        event: SERVICE_REQUEST_EVENT,
        duration_ms: duration(),
        ...fields(),
      });
    }
    throw error;
  } finally {
    if (signal !== null && typeof signal.removeEventListener === "function") {
      signal.removeEventListener("abort", onAbort);
    }
  }
};

export const attachServiceRequestLog = (
  app: Hono,
  options: ServiceRequestLogOptions = {},
): Hono => {
  const sink = options.sink ?? createRuntimeLogSink({
    proc: "service",
    ...(options.dir === undefined ? {} : { dir: options.dir }),
    ...(options.nowIso === undefined ? {} : { nowIso: options.nowIso }),
    ...(options.maxBytes === undefined ? {} : { maxBytes: options.maxBytes }),
  });
  const inner = app.fetch.bind(app);
  const wrapped = (request: Request, env?: unknown, executionCtx?: unknown): Promise<Response> =>
    observeRequest(
      request,
      () => inner(request, env as never, executionCtx as never),
      options,
      sink,
    );
  Object.defineProperty(app, "fetch", {
    configurable: true,
    enumerable: true,
    writable: true,
    value: wrapped,
  });
  return app;
};
