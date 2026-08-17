#!/usr/bin/env bun
/**
 * Live adversarial backend target for the integration harness. Defaults to port
 * 4851 (INTEGRATION's registry allocation); tests may supply a bounded
 * loopback override. Loopback only — board ruling PR-4.
 *
 * WHAT IS ACTUALLY THE CODE UNDER TEST, STATED PRECISELY
 * -----------------------------------------------------
 * This file's previous header claimed "every byte of transport, envelope, and
 * validation is the code under test." That sentence was FALSE for
 * `/v1/memories`: the recall route was hand-rolled here, over a hand-rolled
 * read composition in `compose.ts`. A mechanism whose self-description is wrong
 * is its own defect class (swarm protocol §8), so the sentence is replaced with
 * the inventory below rather than merely made true.
 *
 *   the Hono shell            apps/service/app.ts              — real
 *   the recall route          apps/service/routes/memories.ts  — real
 *   the read composition      apps/service/composition/
 *                             memory-read.ts                   — real, registered
 *   the MCP protocol seam     apps/mcp/protocol.ts             — real
 *   the Bun MCP adapter       apps/mcp/bun-http.ts             — real
 *   the served-read counter   apps/service/observability/
 *                             served-count.ts                  — real
 *
 *   the fixture corpus        apps/service/qa/seed.ts over SQLite — harness
 *   the credential table      compose.ts                          — harness
 *   origin list, rate limit,
 *   trace sink                compose.ts                          — harness
 *   the /qa/* control plane   this file                           — harness
 *   the per-client counter    client-counter.ts                   — harness
 *
 * Everything in the first block is the shipped binding; everything in the
 * second is a faked port. That is the shape `apps/service/app-facing.ts`
 * already uses, and fable's W4 ruling required this harness to match it.
 *
 * A `/qa/*` control plane exists for seed/reset/stats. It is deliberately
 * mounted on the SAME server so the served-request counter observes the same
 * process that answers domain traffic — a counter in a sidecar process would
 * be exactly the kind of evidence that proved nothing in Wave 9.
 */

import { createBunMcpHttpHandler } from "../../apps/mcp/bun-http";
import { createMcpProtocolHandler } from "../../apps/mcp/protocol";
import { createMemoryServiceApp } from "../../apps/service/memory-service-app";
import {
  createServedCounter,
  reset as resetServedCounter,
} from "../../apps/service/observability/served-count";
import {
  createPreparedMemoryRouteReadPort,
} from "../../apps/service/routes/memories";

import { createClientReadCounter } from "./client-counter";
import { createQaBackend, type QaFixturePlan } from "./compose";
import { assertFixtureTimezone, FIXTURE_ANCHOR_EPOCH_SECONDS } from "./fixture-clock";
import { BACKEND_PROCESS_STAMP } from "./provenance";
import { parseIntegrationPort } from "./port";

/** Request header a launcher sends on every bridge request so served reads are joinable to the run that made them — see provenance.ts and client-counter.ts. */
const CLIENT_ID_HEADER = "x-omi-client-id";

// The direct service door is fixed at 4851. The adversarial child may use a
// test-owned loopback port, but only within the bounded user-port range below.
const HOSTNAME = "127.0.0.1";
const DEFAULT_PLAN: QaFixturePlan = Object.freeze({ visibleCount: 7, hiddenCount: 0 });

const timezone = assertFixtureTimezone();

const backend = createQaBackend();
backend.reseed(DEFAULT_PLAN);

/**
 * The REAL served counter, driven by the REAL route. `domainReadsServed` moves
 * only after a domain response body exists — counting earlier is the wave-9 bug
 * where a served count moved while the backend served nothing.
 */
const counter = createServedCounter();
const clientReads = createClientReadCounter();

const mcpHandler = createBunMcpHttpHandler(createMcpProtocolHandler(backend.mcpPorts));
const app = createMemoryServiceApp(mcpHandler, {
  readPort: createPreparedMemoryRouteReadPort({
    resolvePrincipal: backend.resolvePrincipal,
    prepareRead: backend.prepareRead,
  }),
  nowEpochSeconds: () => FIXTURE_ANCHOR_EPOCH_SECONDS,
  counter,
});
/**
 * The settled client recall route: `GET /v1/memories?limit=&cursor=` with
 * `Authorization: Bearer <token>`. Registered — not re-implemented — so this
 * adversarial process exercises the same route module as the dev service. Its
 * fixture, credential, and `/qa/*` controls are deliberately bounded test
 * compatibility seams, not a claim that this process is a drop-in backend.
 *
 * It reuses the SAME composition as the `/mcp` path over the same fixture and
 * the same principal identity, so the two transports cannot drift into serving
 * different ids for the same memory.
 */
const RECALL_PATHS = new Set(["/v1/memories", "/v1/memories/recall"]);
const MCP_PATH = "/mcp";

/**
 * Domain requests observed at dispatch. This is a DISPATCH-side number and is
 * reported as such: it answers "did anything reach me?", never "did I serve
 * it?". The verdict-grade counters are `servedReads` and `servedReadsByClient`,
 * both of which move only after response bytes exist.
 */
let domainRequests = 0;

/** True when this MCP response actually carried a page, read off the bytes. */
async function mcpServedAPage(response: Response): Promise<boolean> {
  if (response.status !== 200) return false;
  try {
    const envelope = JSON.parse(await response.clone().text()) as {
      result?: { content?: readonly { text?: unknown }[] };
    };
    return typeof envelope.result?.content?.[0]?.text === "string";
  } catch {
    return false;
  }
}

const port = parseIntegrationPort(process.env.OMI_INTEGRATION_PORT);

const server = Bun.serve({
  hostname: HOSTNAME,
  port,
  async fetch(request) {
    const url = new URL(request.url);

    if (url.pathname.startsWith("/qa/")) {
      return handleQaControl(url, request);
    }

    const clientId = request.headers.get(CLIENT_ID_HEADER);

    if (RECALL_PATHS.has(url.pathname)) {
      domainRequests += 1;
      // The route's OWN counter decides whether this was served. Reading it
      // before and after is a consumer-side observation of the producer-side
      // number, which is what makes the per-client tally joinable rather than
      // merely correlated: a request the route denied cannot inflate it.
      const before = counter.snapshot().domainReadsServed;
      const response = await app.fetch(request);
      if (counter.snapshot().domainReadsServed > before) {
        clientReads.record(clientId);
      }
      return response;
    }

    if (url.pathname === MCP_PATH) {
      domainRequests += 1;
      const response = await app.fetch(request);
      if (await mcpServedAPage(response)) {
        clientReads.record(clientId);
        counter.recordDomainRead("served");
      }
      return response;
    }

    return app.fetch(request);
  },
});

function handleQaControl(url: URL, request: Request): Response {
  void request;
  switch (url.pathname) {
    case "/qa/reset": {
      // `seed` is the number of VISIBLE memories; `hidden` is how many
      // additional hidden-but-present rows to seed alongside them. Each hidden
      // memory shares a local day with a visible one, so the served day-node
      // exists in both fixture worlds and only its membership differs.
      const plan = planFrom(url, "seed", "hidden");
      backend.reseed(plan);
      resetCounters();
      return json({ status: "reset", seeded: plan.visibleCount, hidden: plan.hiddenCount });
    }
    case "/qa/absent": {
      // The counterpart world: the same visible memories, with the hidden rows
      // PHYSICALLY ABSENT rather than authorization-hidden. The harness fetches
      // the same page from this variant and from /qa/reset?hidden=<same count>
      // and asserts the two wire transcripts are byte-identical. Any difference
      // — ordering, count, envelope, cursor, completeness — is an
      // authorization oracle.
      const plan = { visibleCount: countFrom(url, "seed", 7), hiddenCount: 0 };
      backend.reseed(plan);
      resetCounters();
      return json({ status: "absent", seeded: plan.visibleCount, hidden: 0 });
    }
    case "/qa/grow": {
      // Grows the corpus MID-PAGINATION without resetting the counters, for the
      // concurrent-change proof. The seeder is a pure function of the memory
      // index, so rows already served keep byte-identical content and only the
      // snapshot generation moves.
      const by = countFrom(url, "by", 2);
      const current = backend.plan();
      const grown = {
        visibleCount: current.visibleCount + by,
        hiddenCount: current.hiddenCount,
      };
      backend.reseed(grown);
      return json({ status: "grown", seeded: grown.visibleCount, hidden: grown.hiddenCount });
    }
    case "/qa/stats": {
      const served = counter.snapshot();
      return json({
        // Dispatch-side: requests that reached a domain path, any outcome.
        servedRequests: domainRequests,
        // Verdict-grade: pages that actually left this process.
        servedReads: served.domainReadsServed,
        servedReadsByClient: clientReads.snapshot(),
        memories: backend.plan().visibleCount,
        hiddenMemories: backend.plan().hiddenCount,
        fixtureTimezone: timezone,
        stamp: BACKEND_PROCESS_STAMP,
      });
    }
    default:
      return json({ error: "not_found" }, 404);
  }
}

/**
 * Zeroes every counter between fixture worlds. Uses the served counter's own
 * QA reset seam rather than replacing the instance, because the registered
 * route captured the instance at registration time.
 */
function resetCounters(): void {
  domainRequests = 0;
  clientReads.reset();
  resetServedCounter(counter);
}

function planFrom(url: URL, visibleParam: string, hiddenParam: string): QaFixturePlan {
  const visibleCount = countFrom(url, visibleParam, 7);
  const hiddenCount = Math.min(countFrom(url, hiddenParam, 0), visibleCount);
  return { visibleCount, hiddenCount };
}

function countFrom(url: URL, name: string, fallback: number): number {
  const raw = url.searchParams.get(name);
  if (raw === null || raw === "") return fallback;
  const value = Number(raw);
  return Number.isSafeInteger(value) && value >= 0 ? value : fallback;
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
