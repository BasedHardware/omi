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
import { createMcpProtocolHandler } from "../../apps/mcp/protocol";
import { createServiceApp } from "../../apps/service/app";

import { createQaPorts } from "./compose";
import { assertFixtureTimezone } from "./fixture-clock";
import { QaStore } from "./qa-store";

const DEFAULT_PORT = 4851;
const HOSTNAME = "127.0.0.1";

const timezone = assertFixtureTimezone();

const store = new QaStore();
store.seed(7);

const mcpHandler = createBunMcpHttpHandler(
  createMcpProtocolHandler(createQaPorts({ store })),
);
const app = createServiceApp(mcpHandler);

const port = Number(process.env.OMI_INTEGRATION_PORT ?? DEFAULT_PORT);

const server = Bun.serve({
  hostname: HOSTNAME,
  port,
  async fetch(request) {
    const url = new URL(request.url);

    if (url.pathname.startsWith("/qa/")) {
      return handleQaControl(url, request);
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
