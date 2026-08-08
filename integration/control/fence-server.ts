#!/usr/bin/env bun
/**
 * Live backend-under-test for the ACCOUNT EPOCH FENCE. Loopback only.
 *
 * ── WHAT IS REAL HERE AND WHAT IS NOT ────────────────────────────────────────
 *
 * Real: the fence (`core/control/write-fence.ts`), the account-control
 * projection and its ordering/activation rules (`core/control/account-control.ts`),
 * the projection store, the producer-side counter, and the HTTP refusal binding
 * (`apps/service/control/*`). Every refusal byte this process emits is produced by
 * shipped code.
 *
 * Not real, and deliberately so: **nothing is applied.** An admitted write
 * returns `202 {"fence":"admitted"}` and touches no record. Applying is the write
 * contract's job and it is landing in a different lane; a placeholder apply here
 * would be a second implementation of the thing that matters most, invisible from
 * either side — the exact defect rule 16 exists for.
 *
 * The route is `POST /v1/{domain}/ops`, which is ratified (ruling B4), on the
 * Tasks domain, which is ratified as the first writable one (ruling B6). This
 * process is a harness, not a shipped service: it is not mounted in
 * `apps/service/app-facing.ts` and it must not become the write endpoint.
 *
 * ── WHY A SEPARATE PROCESS AT ALL ────────────────────────────────────────────
 *
 * The same reason `integration/adversarial/live-server.ts` gives: the properties
 * under test are properties of the BYTES. An in-process assertion compares
 * JavaScript objects and would pass while the status code, the header set or the
 * body framing differed — and the whole content of ADR-010 §3 is that a client
 * can tell `stale_epoch` from `authentication` by what it receives.
 *
 * ── THE CONTROL PLANE IS ON THIS SAME SERVER, ON PURPOSE ─────────────────────
 *
 * `/control/*` drives the projection and reads the fence counter from the SAME
 * process that answers `/v1/tasks/ops`. A counter in a sidecar is exactly the
 * evidence shape that proved nothing in wave 9: `servedCount=4 status=PASS` while
 * the backend served zero, both numbers accurate.
 */

import { applyWriteFence } from "../../apps/service/control/write-fence-guard";
import { createWriteFenceCounter } from "../../apps/service/control/fence-counter";
import { writeFenceRefusalResponse } from "../../apps/service/control/fence-http";
import { createInMemoryAccountControlProjectionStore } from "../../apps/service/control/projection-store";
import type { AccountControlObservation } from "../../core/control/account-control";
import { ACCOUNT_OF_PRINCIPAL, OPS_PATH, QA_BEARER, RUN_ID_HEADER } from "./fence-protocol";

const DEFAULT_PORT = 4853;
const HOSTNAME = "127.0.0.1";

const JSON_HEADERS = { "content-type": "application/json", "cache-control": "no-store" } as const;

let store = createInMemoryAccountControlProjectionStore();
let counter = createWriteFenceCounter();

const json = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: JSON_HEADERS });

/**
 * The authentication gate, kept crude on purpose: this harness proves the fence,
 * and a real credential composition would put a second authentication path in the
 * repo. What matters is only that a caller with no valid token gets the
 * `authentication` outcome and never reaches the fence.
 */
const bearer = (request: Request): string | null => {
  const header = request.headers.get("authorization");
  if (typeof header !== "string" || !header.startsWith("Bearer ")) return null;
  const token = header.slice("Bearer ".length);
  return token === QA_BEARER ? token : null;
};

// `ACCOUNT_OF_PRINCIPAL` comes from the authenticated principal, NEVER from the
// request body (`backend:ADR-012` §4). This harness has one principal, so the
// mapping is a constant — but it is a constant on the SERVER side of the
// boundary, which is the property that matters.

interface OpsEnvelope {
  readonly account_epoch: number | null;
  readonly op: unknown;
}

/**
 * Reads the straggler stamp. A missing field and a malformed one are different
 * things: missing is `null` and reaches the fence as `request_epoch_absent`,
 * whereas a non-integer is a grammar failure and is refused before the fence, so
 * a malformed request can never be counted as a fence outcome.
 */
const parseEnvelope = (raw: unknown): OpsEnvelope | "malformed" => {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) return "malformed";
  const record = raw as Record<string, unknown>;
  const epoch = record["account_epoch"];
  if (epoch !== undefined && epoch !== null
    && !(typeof epoch === "number" && Number.isSafeInteger(epoch) && epoch >= 0)) {
    return "malformed";
  }
  if (record["op"] === undefined) return "malformed";
  return { account_epoch: epoch === undefined || epoch === null ? null : (epoch as number), op: record["op"] };
};

async function handleOps(request: Request): Promise<Response> {
  const runId = request.headers.get(RUN_ID_HEADER);

  // ADR-010 §3, outcome 1. Reached before the fence and counted nowhere: the
  // fence produced no decision, so the fence counter must not move.
  if (bearer(request) === null) {
    return new Response(
      JSON.stringify({ error: "unauthorized", refusal_outcome: "authentication" }),
      { status: 401, headers: JSON_HEADERS },
    );
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return json({ error: "bad_request" }, 400);
  }
  const envelope = parseEnvelope(body);
  if (envelope === "malformed") return json({ error: "bad_request" }, 400);

  const decision = applyWriteFence(
    { store, counter },
    { accountId: ACCOUNT_OF_PRINCIPAL, requestEpoch: envelope.account_epoch, runId },
  );
  if (!decision.admitted) return writeFenceRefusalResponse(decision);

  // NOT a write result. See the module header.
  return json({ fence: "admitted", account_epoch: decision.account_epoch }, 202);
}

function handleControl(url: URL, body: unknown): Response {
  switch (url.pathname) {
    case "/control/reset": {
      store = createInMemoryAccountControlProjectionStore();
      counter = createWriteFenceCounter();
      return json({ status: "reset", account_id: ACCOUNT_OF_PRINCIPAL });
    }
    case "/control/observe": {
      const result = store.observe(body as AccountControlObservation);
      return json({
        accepted: result.accepted,
        reason: result.accepted ? null : result.reason,
        conflicted: result.projection.conflict !== null,
      });
    }
    case "/control/activate": {
      const request = body as { epoch: number; at_control_revision: number };
      const result = store.activate(ACCOUNT_OF_PRINCIPAL, request);
      return json({ activated: result.activated, reason: result.activated ? null : result.reason });
    }
    case "/control/deactivate": {
      const projection = store.deactivate(ACCOUNT_OF_PRINCIPAL);
      return json({ deactivated: projection !== null });
    }
    case "/control/fence-stats": {
      // The PRODUCER-SIDE arbiter. `null` for a run that produced no fence
      // decision — never an all-zero tally, which would read as "measured, and
      // nothing happened" and is the number a broken join returns.
      const run = url.searchParams.get("run") ?? "";
      return json({ run, tally: counter.tally(run) });
    }
    default:
      return json({ error: "not_found" }, 404);
  }
}

const port = Number(process.env.OMI_FENCE_INTEGRATION_PORT ?? DEFAULT_PORT);

const server = Bun.serve({
  hostname: HOSTNAME,
  port,
  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname === "/health") return json({ status: "ok" });
    if (url.pathname === OPS_PATH && request.method === "POST") return handleOps(request);
    if (url.pathname.startsWith("/control/")) {
      let body: unknown = null;
      if (request.method === "POST") {
        try {
          body = await request.json();
        } catch {
          body = null;
        }
      }
      return handleControl(url, body);
    }
    return json({ error: "not_found" }, 404);
  },
});

process.stdout.write(
  `${JSON.stringify({ event: "fence_backend_listening", url: `http://${HOSTNAME}:${server.port}` })}\n`,
);
