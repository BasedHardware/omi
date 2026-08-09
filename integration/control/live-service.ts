#!/usr/bin/env bun
/**
 * The REGISTERED app, bound to a socket, for L2.
 *
 * ── WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT ────────────────────────────
 *
 * It is `apps/service/bin/dev-server.ts` minus the process concerns L2 cannot
 * use: a fixed board-registry port, a human-readable banner, a heartbeat. The
 * app is `createLocalService` — the SAME one wiring the dev server, the route
 * tests and the shipped binding use. There is no route, no handler, no
 * composition and no store constructed here.
 *
 * **It is not a second door.** The file this replaces —
 * `integration/control/fence-server.ts` — answered `/v1/tasks/ops` from its own
 * handler over its own store, applied nothing, and returned bytes the product
 * does not send. R5 pre-ruled that it could not survive the registered route,
 * and it did not. What is left is a socket bind, which is the one thing an L2
 * test genuinely needs a separate process for: the properties under test are
 * properties of the BYTES, and an in-process assertion compares JavaScript
 * objects that can agree while the status line, headers or framing differ.
 *
 * ── WHY AN EPHEMERAL PORT AND NOT 4811/4812 ──────────────────────────────────
 *
 * L2's stated property is that it is safe to run while a stack is live, and
 * lanes run it concurrently. A fixed port makes two honest lanes fight over a
 * socket and reports it as a test failure in whichever lost. Port 0 lets the
 * kernel answer, and the port is printed so the test binds to the one that was
 * actually opened rather than the one it hoped for.
 *
 * Output is a single line of JSON on stdout, because a test parsing prose is a
 * test that breaks when somebody improves the prose.
 */

import { Database } from "bun:sqlite";

import { createLocalService } from "../../apps/service/app-facing";
import { LOOPBACK_HOST } from "../../apps/service/net/loopback";

/** Fixed, non-secret dev key material — the same label the dev server uses. */
const DEV_KEY_MATERIAL_LABEL = "omi-local-dev-token-not-a-secret-v1";

const service = createLocalService({
  db: new Database(":memory:"),
  ownerAccountId: "local-dev-user",
  memoryCount: 4,
  accountTimezone: "America/Los_Angeles",
  devSecretLabel: DEV_KEY_MATERIAL_LABEL,
});

const server = Bun.serve({
  // Loopback ONLY. Omitting hostname makes Bun bind 0.0.0.0, which publishes
  // this service to the LAN — a bug that shipped silently in an earlier wave
  // and that a loopback curl does not catch, because it succeeds either way.
  hostname: LOOPBACK_HOST,
  port: 0,
  fetch: service.app.fetch,
});

process.stdout.write(`${JSON.stringify({
  event: "live_service_listening",
  url: `http://${LOOPBACK_HOST}:${server.port}`,
  devToken: service.devToken,
  ownerAccountId: "local-dev-user",
})}\n`);
