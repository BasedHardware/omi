import { Hono } from "hono";

import type {
  HttpStatusClass,
  OperationalTelemetryEmitter,
  ServiceOperation,
  ServiceOutcome,
} from "../../core/observability/operational-telemetry";

export type StandardFetchHandler = (request: Request) => Response | Promise<Response>;

export interface ServiceAppObservability {
  readonly telemetry?: OperationalTelemetryEmitter;
  readonly nowMilliseconds?: () => number;
}

const JSON_HEADERS = Object.freeze({
  "cache-control": "no-store",
  "content-type": "application/json",
});

/**
 * Runtime-neutral HTTP composition root.
 *
 * Runtime binding, lifecycle, authorization, and data access remain outside
 * this shell. The injected handler owns the complete MCP transport response.
 */
export function createServiceApp(
  mcpHandler: StandardFetchHandler,
  observability: ServiceAppObservability = {},
): Hono {
  const app = new Hono({ strict: true });

  let inFlight = 0;
  const now = (): number => {
    try {
      const value = (observability.nowMilliseconds ?? Date.now)();
      return Number.isSafeInteger(value) && value >= 0 ? value : 0;
    } catch {
      return 0;
    }
  };
  const observed = async (
    operation: ServiceOperation,
    action: () => Response | Promise<Response>,
  ): Promise<Response> => {
    const started = now();
    inFlight += 1;
    try {
      const response = await action();
      const status = response.status;
      const statusClass: HttpStatusClass | null = status >= 200 && status < 300
        ? "2xx"
        : status >= 400 && status < 500
        ? "4xx"
        : status >= 500 && status < 600
        ? "5xx"
        : null;
      const outcome: ServiceOutcome = statusClass === "2xx"
        ? "success"
        : status === 401 || status === 403
        ? "denied"
        : statusClass === "4xx"
        ? "invalid"
        : status === 503
        ? "unavailable"
        : "failure";
      const finished = now();
      observability.telemetry?.emit({
        version: "operational-telemetry-v1",
        family: "service",
        operation,
        outcome,
        status_class: statusClass,
        duration_ms: finished >= started ? Math.min(finished - started, 86_400_000) : 0,
        in_flight: Math.min(inFlight, 1_000_000_000),
      });
      return response;
    } finally {
      inFlight = Math.max(0, inFlight - 1);
    }
  };

  app.get("/health", () => observed("health", () => jsonResponse({ status: "ok" }, 200)));
  app.get("/ready", () => observed("readiness", () => jsonResponse({ status: "ready" }, 200)));

  app.all("/mcp", (context) => observed("mcp", async () => {
    try {
      return await mcpHandler(context.req.raw);
    } catch {
      return internalServerErrorResponse();
    }
  }));

  app.notFound(() => observed("other", () => jsonResponse({ error: "not_found" }, 404)));
  app.onError(() => observed("other", () => internalServerErrorResponse()));

  return app;
}

function internalServerErrorResponse(): Response {
  return jsonResponse({ error: "internal_server_error" }, 500);
}

function jsonResponse(body: Readonly<Record<string, string>>, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: JSON_HEADERS });
}
