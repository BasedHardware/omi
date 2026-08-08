import { Hono } from "hono";

export type StandardFetchHandler = (request: Request) => Response | Promise<Response>;

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
export function createServiceApp(mcpHandler: StandardFetchHandler): Hono {
  const app = new Hono({ strict: true });

  app.get("/health", () => jsonResponse({ status: "ok" }, 200));
  app.get("/ready", () => jsonResponse({ status: "ready" }, 200));

  app.all("/mcp", async (context) => {
    try {
      return await mcpHandler(context.req.raw);
    } catch {
      return internalServerErrorResponse();
    }
  });

  app.notFound(() => jsonResponse({ error: "not_found" }, 404));
  app.onError(() => internalServerErrorResponse());

  return app;
}

function internalServerErrorResponse(): Response {
  return jsonResponse({ error: "internal_server_error" }, 500);
}

function jsonResponse(body: Readonly<Record<string, string>>, status: number): Response {
  return new Response(JSON.stringify(body), { status, headers: JSON_HEADERS });
}
