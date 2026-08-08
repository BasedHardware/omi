#!/usr/bin/env bun
/**
 * Live backend-under-test for the integration harness. Port 4851 (INTEGRATION's
 * registry allocation). Loopback only — board ruling PR-4.
 *
 * Serves the real Hono composition shell (`apps/service/app.ts`) over the real
 * MCP protocol seam (`apps/mcp/protocol.ts`) via the real Bun adapter
 * (`apps/mcp/bun-http.ts`), with the deterministic QA store behind it. The only
 * harness-authored part of the request path is the store; every byte of
 * transport, envelope, and validation is the code under test.
 *
 * A `/qa/*` control plane exists for seed/reset/stats. It is deliberately
 * mounted on the SAME server so the served-request counter observes the same
 * process that answers domain traffic — a counter in a sidecar process would
 * be exactly the kind of evidence that proved nothing in Wave 9.
 */

import { createBunMcpHttpHandler } from "../../apps/mcp/bun-http";
import { createMcpProtocolHandler, SYNTHESIZED_MEMORY_READ_DEPENDENCY } from "../../apps/mcp/protocol";
import { createServiceApp } from "../../apps/service/app";

import { createQaPorts } from "./compose";
import { assertFixtureTimezone } from "./fixture-clock";
import { QaStore } from "./qa-store";

const DEFAULT_PORT = 4851;
const HOSTNAME = "127.0.0.1";

const timezone = assertFixtureTimezone();

const store = new QaStore();
store.seed(7);

const ports = createQaPorts({ store });
const mcpHandler = createBunMcpHttpHandler(createMcpProtocolHandler(ports));
const app = createServiceApp(mcpHandler);

/**
 * The settled client recall route: `GET /v1/memories?limit=&cursor=` with
 * `Authorization: Bearer <token>`, agreed between FE-CORE and BE-SURFACE
 * (2026-08-08). Serving it here is what makes this instance interchangeable
 * with BE-SURFACE's 4811 and the dev stub on 4821 **by base URL alone**.
 *
 * It deliberately reuses the SAME ports object as the MCP path, so the two
 * transports cannot drift into serving different data from the same store.
 */
const PLATFORM_RECALL_PATH = "/v1/memories";
const DEFAULT_LIMIT = 25;
const MAX_LIMIT = 100;

async function handleRecallRoute(url: URL, request: Request): Promise<Response> {
  const credential = await ports.authenticate({
    apiKeyHeader: request.headers.get("authorization") ?? undefined,
    requiredKind: "mcp_api_key",
  });
  if (credential === null) {
    return json({ error: "authentication_required" }, 401);
  }

  const decision = await ports.authorize({
    credential,
    tool: { name: "read_synthesized_memory", dependency: SYNTHESIZED_MEMORY_READ_DEPENDENCY },
  });
  if (decision.allowed !== true) {
    // Same body and status as an unknown route would produce for a caller who
    // may not know this collection exists.
    return json({ error: "not_found" }, 404);
  }

  const rawLimit = Number(url.searchParams.get("limit") ?? DEFAULT_LIMIT);
  const limit = Number.isSafeInteger(rawLimit) && rawLimit >= 1
    ? Math.min(rawLimit, MAX_LIMIT)
    : DEFAULT_LIMIT;
  const cursor = url.searchParams.get("cursor");

  store.countRequest();

  let page: unknown;
  try {
    page = await ports.readPage({
      authorization: decision.readAuthorization,
      cursor: cursor === null || cursor === "" ? null : cursor,
      limit,
    });
  } catch {
    // Public shape for every client-controlled cursor failure. It must not
    // distinguish "forged", "expired", "other owner's" or "unknown".
    return json({ error: "invalid_cursor" }, 400);
  }

  const validated = await ports.validatePage(page);
  if (typeof validated !== "string") {
    return json({ error: "internal_server_error" }, 500);
  }

  // Emit the validated canonical text verbatim. Re-serializing would defeat
  // the client's strong `canonical-json-text` parse boundary.
  return new Response(validated, {
    status: 200,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

const port = Number(process.env.OMI_INTEGRATION_PORT ?? DEFAULT_PORT);

const server = Bun.serve({
  hostname: HOSTNAME,
  port,
  async fetch(request) {
    const url = new URL(request.url);

    if (url.pathname.startsWith("/qa/")) {
      return handleQaControl(url, request);
    }

    if (url.pathname === PLATFORM_RECALL_PATH) {
      return handleRecallRoute(url, request);
    }

    // Count every domain-path request that reaches the app under test.
    if (url.pathname === "/mcp") {
      store.countRequest();
    }
    return app.fetch(request);
  },
});

function handleQaControl(url: URL, request: Request): Response {
  switch (url.pathname) {
    case "/qa/reset": {
      store.reset();
      const count = Number(url.searchParams.get("seed") ?? "7");
      const hiddenParam = url.searchParams.get("hidden");
      const hiddenIds = hiddenParam === null || hiddenParam === ""
        ? []
        : hiddenParam.split(",");
      store.seed(count, { hiddenIds });
      return json({ status: "reset", seeded: count, hiddenIds });
    }
    case "/qa/absent": {
      // Seeds a corpus where the named rows are PHYSICALLY ABSENT rather than
      // authorization-hidden. The harness fetches the same page from this
      // variant and from /qa/reset?hidden=<same ids> and asserts the two wire
      // responses are byte-identical. Any difference — ordering, count,
      // envelope, cursor — is an authorization oracle.
      const count = Number(url.searchParams.get("seed") ?? "7");
      const omitParam = url.searchParams.get("omit");
      const omit = new Set(omitParam === null || omitParam === "" ? [] : omitParam.split(","));
      seedSubset(store, count, omit);
      return json({ status: "absent", seeded: store.allRowIds().length, omitted: [...omit] });
    }
    case "/qa/insert": {
      const id = url.searchParams.get("id") ?? "retrieval-node-v1:inserted";
      const sortKey = url.searchParams.get("sortKey") ?? "s00000005";
      store.insert({ sortKey, id, text: `Inserted proposition ${id}`, visibleTo: null });
      return json({ status: "inserted", id, sortKey });
    }
    case "/qa/stats": {
      return json({
        servedRequests: store.servedRequests,
        servedReads: store.servedReads,
        rows: store.allRowIds().length,
        fixtureTimezone: timezone,
      });
    }
    default:
      return json({ error: "not_found" }, 404);
  }
}

/** Seeds the standard corpus minus the omitted ids, which are never inserted. */
function seedSubset(target: QaStore, count: number, omitIds: ReadonlySet<string>): void {
  target.reset();
  for (let index = 0; index < count; index += 1) {
    const id = `retrieval-node-v1:seed-${String(index).padStart(4, "0")}`;
    if (omitIds.has(id)) {
      continue;
    }
    target.insert({
      sortKey: `s${String(index * 10).padStart(8, "0")}`,
      id,
      text: `Synthesized proposition ${index}`,
      visibleTo: null,
    });
  }
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

process.stdout.write(
  `${JSON.stringify({
    event: "integration_backend_listening",
    url: `http://${HOSTNAME}:${server.port}`,
    fixtureTimezone: timezone.resolvedTz,
    fixtureAnchorLocalDate: timezone.anchorLocalDate,
  })}\n`,
);
