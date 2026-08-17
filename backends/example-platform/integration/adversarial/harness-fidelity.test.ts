/**
 * The harness must refuse what the real backend refuses.
 *
 * `integration/server/serve.ts` is the live adversarial harness target. The
 * product stack is launched by the core integration entrypoint. This harness
 * mounts the registered route but keeps bounded fixture and QA-control seams;
 * its compatibility claims are behavioural, and nothing was
 * checking it: the recall route dispatched on `url.pathname` and never looked at
 * `request.method`, so POST/PUT/PATCH/DELETE each returned 200 with the full read
 * payload while `apps/service/routes/memories.ts` — GET-only, pinned by
 * `route-hardening.test.ts` — correctly returned the fixed 404.
 *
 * The 690-test suite was green throughout, because it exercises the real route and
 * this file is a second, hand-rolled implementation of the same wire. A client with
 * a method bug would have passed every local gate and failed against production.
 *
 * WHY THIS COMPARES AGAINST THE REAL ROUTE'S CONSTANT rather than a status code:
 * "not 200" is satisfied by a crash, a 500, or a 405. A 405 in particular would be
 * WRONG here — a distinct method-not-allowed status confirms the collection exists
 * to a caller who may not be allowed to know that, which is the authorization
 * oracle the real route's fixed `not_found` body exists to close. So the assertion
 * is byte identity with an unauthorized caller's 404, obtained from this same live
 * process, and the paired GET proves the route is actually mounted.
 */

import { afterAll, beforeAll, describe, expect, test } from "bun:test";

import { QA_KEY, control, startLiveServer, type LiveServer } from "./live-server";

const RECALL_PATH = "/v1/memories?limit=1";
/** A route this server does not serve. Its 404 is the arbiter — see below. */
const UNKNOWN_PATH = "/v1/not-a-collection";
const MUTATING_METHODS = ["POST", "PUT", "PATCH", "DELETE"] as const;

let server: LiveServer;

beforeAll(async () => {
  server = await startLiveServer();
  await control(server.baseUrl, "/qa/reset?seed=7");
});

afterAll(async () => {
  await server?.stop();
});

async function call(method: string, path: string) {
  const response = await fetch(`${server.baseUrl}${path}`, {
    method,
    headers: { authorization: `Bearer ${QA_KEY}` },
  });
  return { status: response.status, body: await response.text() };
}

describe("the QA backend refuses non-GET on the read route exactly as the real route does", () => {
  /**
   * red-proof: in `serve.ts`, delete the `if (request.method !== "GET")` guard
   * from the recall dispatch. Every mutating method then returns 200 with a full
   * page body, and all four cases here fail on both the status and the body.
   */
  test.each(MUTATING_METHODS)("%s /v1/memories is byte-identical to an unknown route's 404", async (method) => {
    // The arbiter: what THIS live process answers for a route it does not serve.
    // Not a literal typed in this file — a literal would keep passing if the real
    // refusal body drifted, which is the divergence this test exists to catch.
    const unknownRoute = await call("GET", UNKNOWN_PATH);
    expect(unknownRoute.status).toBe(404);

    const mutating = await call(method, RECALL_PATH);
    expect(mutating.status).toBe(unknownRoute.status);
    expect(mutating.body).toBe(unknownRoute.body);

    // No leak: the refusal must not carry the method, the route, or any hint
    // that a different verb would have worked.
    expect(mutating.body.toLowerCase()).not.toContain("method");
    expect(mutating.body.toLowerCase()).not.toContain("allowed");
  });

  /**
   * The pair. Without this, a server that refused EVERYTHING would satisfy every
   * assertion above — "not 200" is not evidence of a working fence.
   *
   * red-proof: make the guard `request.method !== "HEAD"` instead. GET then 404s
   * and this test fails while the four above still pass.
   */
  test("GET on the same route, same process, same credential, still serves a page", async () => {
    const served = await call("GET", RECALL_PATH);
    expect(served.status).toBe(200);
    expect(JSON.parse(served.body)).toHaveProperty("items");
  });
});
