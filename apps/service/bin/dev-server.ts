// domain-pending(DIV-DOMCORE-001)
import { Database } from "bun:sqlite";

import { createLocalService } from "../app-facing";
import { LOOPBACK_HOST, assertPortInRange } from "../net/loopback";
import { QA_FIXTURE_TIME_ANCHOR_UTC } from "../qa/seed";

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
 * This file owns ONLY process concerns - config, socket, printing, signals. The
 * routes and their wiring live in `../app-facing.ts` so that tests exercise the
 * same app this serves, rather than a lookalike that could agree with a wrong
 * binding.
 *
 * SQLite here is QA fixture storage only, never production authority. No
 * production store, cloud service, credential, or deployment topology is
 * selected by this file.
 */

/** Ports allocated to this agent by the board's port registry. */
const DEFAULT_PORT = 4851;

/**
 * Fixed, non-secret dev key material.
 *
 * NOT a credential. It signs dev tokens for a loopback-only service that serves
 * synthetic fixture data, and it is committed on purpose so a restart issues the
 * SAME token and an app under test keeps working without re-pairing. Override
 * with OMI_DEV_TOKEN_SECRET to rotate. A real deployment replaces the whole
 * dev-token seam, not this constant.
 */
const DEV_KEY_MATERIAL_LABEL = "omi-local-dev-token-not-a-secret-v1";

const DEFAULT_OWNER = "local-dev-user";
const DEFAULT_MEMORY_COUNT = 12;
const DEFAULT_TIMEZONE = "America/Los_Angeles";

const fail = (message: string): never => {
  // Legible, actionable, and free of any user content.
  process.stderr.write(`\nomi dev-server: ${message}\n\n`);
  process.exit(1);
};

interface BootConfig {
  readonly port: number;
  readonly ownerAccountId: string;
  readonly memoryCount: number;
  readonly accountTimezone: string;
  readonly databasePath: string;
  readonly devSecretLabel: string;
}

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
      `port ${port} is not allocated to this service. Use 4851, the one app-facing door.`,
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

const main = (): void => {
  const config = readConfig();
  const db = openDatabase(config.databasePath);

  let service: ReturnType<typeof createLocalService>;
  try {
    service = createLocalService({
      db,
      ownerAccountId: config.ownerAccountId,
      memoryCount: config.memoryCount,
      accountTimezone: config.accountTimezone,
      devSecretLabel: config.devSecretLabel,
    });
  } catch (error) {
    return fail(`failed to seed QA data: ${error instanceof Error ? error.message : "unknown error"}`);
  }

  let server: { stop: (closeActive?: boolean) => void };
  try {
    server = Bun.serve({
      // Loopback ONLY. Omitting hostname makes Bun bind 0.0.0.0, which publishes
      // this service to the LAN. That exact bug shipped silently in an earlier
      // wave and a loopback curl did not catch it, because a loopback curl
      // succeeds either way.
      hostname: LOOPBACK_HOST,
      port: config.port,
      fetch: service.app.fetch,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "";
    if (/EADDRINUSE|address already in use/i.test(message)) {
      return fail(
        `port ${config.port} is already in use. Something else is listening.\n`
        + `  Find it:  lsof -nP -iTCP:${config.port} -sTCP:LISTEN\n`
        + `  Stop the existing listener before booting the one service door.`,
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
    + `  dev token\n    ${service.devToken}\n\n`
    + `  try it\n`
    + `    TOKEN='${service.devToken}'\n`
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
    const snapshot = service.counter.snapshot();
    if (snapshot.domainReadsServed === lastReported) return;
    lastReported = snapshot.domainReadsServed;
    process.stdout.write(
      `[served] domain-reads=${snapshot.domainReadsServed}`
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

main();
