// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
import { createHash } from "node:crypto";
import { Database } from "bun:sqlite";
import { Hono } from "hono";

import { createSqliteQaRecallLoader } from "../../../drivers/sqlite/application-recall-read";
import {
  createDevTokenIssuer,
  devPrincipalToAuthorizationRequest,
  type DevPrincipal,
} from "../auth/dev-token";
import { prepareMemoryRead, type CoherentQaLoad } from "../composition/memory-read";
import { createServedCounter } from "../observability/served-count";
import { QA_FIXTURE_TIME_ANCHOR_UTC, resetQaSnapshot, seedQaSnapshot } from "../qa/seed";
import { registerMemoryRoutes } from "../routes/memories";
import { registerQaRoutes } from "../routes/qa";
import { LOOPBACK_HOST, assertPortInRange } from "../net/loopback";

/**
 * One-command local backend for testing a real macOS/iOS app against the new
 * service.
 *
 *   bun run apps/service/bin/dev-server.ts
 *
 * From a cold checkout, with zero required environment variables, this boots a
 * loopback-only HTTP service with deterministic seed data already loaded and
 * prints the base URL, the dev token, and the seed identity.
 *
 * SQLite here is QA fixture storage only and is never production authority. No
 * production store, cloud service, credential, or deployment topology is
 * selected by this file.
 */

/** Ports allocated to this agent by the board's port registry. */
const DEFAULT_PORT = 4811;

/**
 * Fixed, non-secret dev key material.
 *
 * This is NOT a credential. It signs dev tokens for a loopback-only service
 * that serves synthetic fixture data, and it is committed on purpose so a
 * restart issues the SAME token and an app under test keeps working without
 * being re-paired. Override with OMI_DEV_TOKEN_SECRET to rotate. A real
 * deployment replaces the whole dev-token seam, not this constant.
 */
const DEV_KEY_MATERIAL_LABEL = "omi-local-dev-token-not-a-secret-v1";
const DEV_KEY_ID = "dev-local";
const DEV_TOKEN_TTL_SECONDS = 86_400;
const CURSOR_TTL_SECONDS = 3_600;

const DEFAULT_OWNER = "local-dev-user";
const DEFAULT_MEMORY_COUNT = 12;
const DEFAULT_TIMEZONE = "America/Los_Angeles";

const derive32 = (label: string): Uint8Array =>
  new Uint8Array(createHash("sha256").update(label, "utf8").digest());

interface BootConfig {
  readonly port: number;
  readonly ownerAccountId: string;
  readonly memoryCount: number;
  readonly accountTimezone: string;
  readonly databasePath: string;
  readonly devSecretLabel: string;
}

const fail = (message: string): never => {
  // Legible, actionable, and free of any user content.
  process.stderr.write(`\nomi dev-server: ${message}\n\n`);
  process.exit(1);
};

const readConfig = (): BootConfig => {
  const rawPort = process.env.OMI_PORT;
  let port = DEFAULT_PORT;
  if (rawPort !== undefined && rawPort.length > 0) {
    if (!/^[0-9]{2,5}$/.test(rawPort)) fail(`OMI_PORT must be a number, got "${rawPort}".`);
    port = Number(rawPort);
  }
  try {
    assertPortInRange(port);
  } catch {
    fail(
      `port ${port} is not allocated to this service. `
      + `Use 4811 (or 4812), which are this agent's ports in the board registry.`,
    );
  }

  const rawCount = process.env.OMI_SEED_MEMORIES;
  let memoryCount = DEFAULT_MEMORY_COUNT;
  if (rawCount !== undefined && rawCount.length > 0) {
    if (!/^[0-9]{1,4}$/.test(rawCount)) fail(`OMI_SEED_MEMORIES must be a number, got "${rawCount}".`);
    memoryCount = Number(rawCount);
  }

  const accountTimezone = process.env.OMI_ACCOUNT_TIMEZONE || DEFAULT_TIMEZONE;
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: accountTimezone }).format(0);
  } catch {
    fail(
      `OMI_ACCOUNT_TIMEZONE "${accountTimezone}" is not a valid IANA timezone. `
      + `Example: America/Los_Angeles. The zone is required because memories are `
      + `grouped into days in LOCAL time, so a UTC-only fixture drifts by host.`,
    );
  }

  return Object.freeze({
    port,
    ownerAccountId: process.env.OMI_SEED_OWNER || DEFAULT_OWNER,
    memoryCount,
    accountTimezone,
    // In-memory by default so a cold checkout needs no file, no migration step,
    // and no cleanup, and so every boot is byte-identical.
    databasePath: process.env.OMI_QA_DB || ":memory:",
    devSecretLabel: process.env.OMI_DEV_TOKEN_SECRET || DEV_KEY_MATERIAL_LABEL,
  });
};

const openDatabase = (path: string): Database => {
  if (path === ":memory:") return new Database(":memory:");
  try {
    return new Database(path, { create: true });
  } catch {
    return fail(
      `cannot open the QA database at "${path}". `
      + `Check the directory exists and is writable, or unset OMI_QA_DB to use `
      + `an in-memory database (the default, and what a cold checkout should use).`,
    );
  }
};

const main = async (): Promise<void> => {
  const config = readConfig();
  const db = openDatabase(config.databasePath);

  const seed = (): void => {
    resetQaSnapshot(db);
    seedQaSnapshot(db, {
      owner_account_id: config.ownerAccountId,
      memory_count: config.memoryCount,
      account_timezone: config.accountTimezone,
    });
  };
  try {
    seed();
  } catch (error) {
    fail(`failed to seed QA data: ${error instanceof Error ? error.message : "unknown error"}`);
  }

  const counter = createServedCounter();
  const issuer = createDevTokenIssuer({
    signing_keyset: {
      active_key_id: DEV_KEY_ID,
      keys: [{ key_id: DEV_KEY_ID, secret: derive32(config.devSecretLabel) }],
    },
    ttl_seconds: DEV_TOKEN_TTL_SECONDS,
  });

  // A fixed issue instant keeps the printed token stable across restarts, so an
  // app under test does not need re-pairing between runs.
  const tokenIssuedAt = Math.floor(Date.parse(QA_FIXTURE_TIME_ANCHOR_UTC) / 1000);
  const devToken = issuer.issue(config.ownerAccountId, tokenIssuedAt);
  // Verification uses the same anchor, so the printed token never expires
  // mid-session on a machine whose wall clock is far from the fixture anchor.
  const resolvePrincipal = (token: string): DevPrincipal | null =>
    issuer.resolve(token, tokenIssuedAt);

  const codecRootSecret = derive32(`${config.devSecretLabel}:codec-root`);
  const cursorSigningKeyset = {
    active_key_id: DEV_KEY_ID,
    keys: [{ key_id: DEV_KEY_ID, secret: derive32(`${config.devSecretLabel}:cursor`) }],
  };

  const prepareRead = async (principal: DevPrincipal) => {
    const loader = createSqliteQaRecallLoader({
      db,
      owner_account_id: principal.uid,
      account_timezone: config.accountTimezone,
      limits: { max_items: 512, max_bytes: 4_000_000 },
      // The seeder owns the entire corpus and writes no accepted work, so
      // "no eligible accepted work" is a declared fact here rather than an
      // assumption. Without this the envelope would honestly report the
      // accepted subsystem as bypassed and every page would be degraded.
      accepted_fixture_state: {
        state: "no_eligible",
        declared_frontier: null,
        searched_frontier: null,
        candidates: [],
      },
    });
    return prepareMemoryRead({
      loadCoherent: loader as unknown as () => CoherentQaLoad,
      authorizationRequest: devPrincipalToAuthorizationRequest(principal, {
        app_id: "omi-local-dev-app",
        key_id: DEV_KEY_ID,
      }),
      codecRootSecret,
      cursorSigningKeyset,
      cursorTtlSeconds: CURSOR_TTL_SECONDS,
      readTimestampEpochSeconds: tokenIssuedAt,
      // Default telemetry carries opaque references only. The trace is
      // deliberately dropped rather than logged: it is content-safe by
      // construction, but a dev server has no reason to persist it.
      traceSink: () => {},
    });
  };

  const app = new Hono({ strict: true });
  app.get("/health", () => {
    counter.recordNonDomainRequest();
    return new Response(JSON.stringify({ status: "ok" }), {
      status: 200,
      headers: { "cache-control": "no-store", "content-type": "application/json" },
    });
  });
  app.get("/ready", () => {
    counter.recordNonDomainRequest();
    return new Response(JSON.stringify({ status: "ready" }), {
      status: 200,
      headers: { "cache-control": "no-store", "content-type": "application/json" },
    });
  });
  registerMemoryRoutes(app, { resolvePrincipal, prepareRead, counter });
  registerQaRoutes(app, {
    counter,
    resetSeed: seed,
    isAuthorizedControlToken: (token) => resolvePrincipal(token) !== null,
    seedIdentity: () => ({
      owner_account_id: config.ownerAccountId,
      memory_count: config.memoryCount,
      account_timezone: config.accountTimezone,
      fixture_time_anchor_utc: QA_FIXTURE_TIME_ANCHOR_UTC,
    }),
  });
  app.notFound(() => {
    counter.recordNonDomainRequest();
    return new Response(JSON.stringify({ error: "not_found" }), {
      status: 404,
      headers: { "cache-control": "no-store", "content-type": "application/json" },
    });
  });

  let server: { stop: (closeActive?: boolean) => void };
  try {
    server = Bun.serve({
      // Loopback ONLY. Omitting hostname makes Bun bind 0.0.0.0, which
      // publishes this service to the LAN. That is the exact bug that shipped
      // silently in an earlier wave.
      hostname: LOOPBACK_HOST,
      port: config.port,
      fetch: app.fetch,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "";
    if (/EADDRINUSE|address already in use/i.test(message)) {
      return fail(
        `port ${config.port} is already in use. Something else is listening.\n`
        + `  Find it:  lsof -nP -iTCP:${config.port} -sTCP:LISTEN\n`
        + `  Or boot on this agent's spare port:  OMI_PORT=4812 bun run apps/service/bin/dev-server.ts`,
      );
    }
    return fail(`failed to bind ${LOOPBACK_HOST}:${config.port}.`);
  }

  const baseUrl = `http://${LOOPBACK_HOST}:${config.port}`;
  process.stdout.write(
    `\nomi local backend is up\n\n`
    + `  base URL      ${baseUrl}\n`
    + `  bound to      ${LOOPBACK_HOST} (loopback only - not reachable from the LAN)\n`
    + `  seed identity ${config.ownerAccountId}, ${config.memoryCount} memories, ${config.accountTimezone}\n`
    + `  time anchor   ${QA_FIXTURE_TIME_ANCHOR_UTC}\n`
    + `  storage       ${config.databasePath} (SQLite, QA fixture only - never production authority)\n\n`
    + `  dev token\n    ${devToken}\n\n`
    + `  try it\n`
    + `    curl -s -H "Authorization: Bearer $TOKEN" "${baseUrl}/v1/memories?limit=5"\n`
    + `    curl -s ${baseUrl}/v1/qa/status\n`
    + `    curl -s -X POST -H "Authorization: Bearer $TOKEN" ${baseUrl}/v1/qa/reset\n\n`
    + `  served-request count prints below whenever it changes.\n`
    + `  if it stays at 0 while the app shows memories, the app is NOT talking to this backend.\n\n`,
  );

  // Runtime served-count visibility for a human watching the demo. This is the
  // wave-9 detector: a bridge that reported itself active while serving zero
  // domain requests looked exactly like a healthy one.
  let lastReported = -1;
  const heartbeat = setInterval(() => {
    const snapshot = counter.snapshot();
    if (snapshot.domainReadsServed === lastReported) return;
    lastReported = snapshot.domainReadsServed;
    process.stdout.write(
      `[served] memories=${snapshot.domainReadsServed}`
      + ` denied=${snapshot.domainReadsDenied}`
      + ` failed=${snapshot.domainReadsFailed}`
      + ` other=${snapshot.nonDomainRequests}\n`,
    );
  }, 1_000);

  const shutdown = (): void => {
    clearInterval(heartbeat);
    server.stop(true);
    process.stdout.write("\nomi dev-server: stopped\n");
    process.exit(0);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
};

await main();
