#!/usr/bin/env bun
/**
 * bun run prod-local
 *
 * Boots the production Firebase/PostgreSQL memory process
 * (`drivers/postgres/firebase-authorized-memory-service-process.ts`) against
 * the managed local PostgreSQL harness. This is not the SQLite QA server and
 * not `apps/qa`.
 *
 * What works locally after `bun run test:postgres:setup`:
 *   - Loopback HTTP on 127.0.0.1:4851 through the production process kernel.
 *   - Liveness (`/health`) once the listener is bound.
 *   - Readiness (`/ready`) only after the sealed PostgreSQL startup proof:
 *     PostgreSQL 18.4, the complete checksummed migration manifest, and a
 *     currently released database-generation head. A freshly set-up volume
 *     that has never run the real-PG gate is honest-unavailable (503), not
 *     faked ready. After `bun run test:postgres:preserve` the qualification
 *     generation is released and readiness can become 200.
 *   - Domain requests go through the real authorized memory route. Without a
 *     Firebase ID token they are denied by that composition, never by a
 *     dev-token seam.
 *
 * What this script will not do, because David has not granted it:
 *   - Mint a Firebase identity on the default path. There is no Auth emulator
 *     in deployed mode, no custom-token issuer, and no stub verifier. The
 *     process will say so at startup. A client must present a real Firebase
 *     ID token; this script cannot issue one.
 *   - MCP API-key credentials, production codec key material, a production
 *     synthesizer/model, live GCP deployment, or `https://api.omi.me`.
 *   - Start or replace the managed PostgreSQL harness. PostgreSQL's port
 *     belongs to `bun run test:postgres:setup`. If that runtime is absent,
 *     this script refuses.
 *
 * Opt-in local identity (`--local-identity` or `OMI_PROD_LOCAL_IDENTITY=emulator`)
 * is the one exception: it requires `FIREBASE_AUTH_EMULATOR_HOST`, composes
 * `runtime_mode=local_test`, and still uses the official Admin verifier. It
 * does not weaken deployed mode. Without the flag, behavior is unchanged,
 * including refusal when the emulator env is present.
 *
 * The listener is loopback-only. Secrets, connection URLs, and environment
 * values are never printed.
 */

import { existsSync, readFileSync, realpathSync } from "node:fs";
import { resolve } from "node:path";
import { randomBytes } from "node:crypto";

import { InvalidMcpCursorError } from "../apps/mcp/cursor";
import { createServedCounter } from "../apps/service/observability/served-count";
import { LOOPBACK_HOST, loopbackServeOptions } from "../apps/service/net/loopback";
import { createFirebaseAdminIdTokenAdapter } from "../drivers/firebase/admin-id-token";
import { createPostgresFirebaseAuthorizedMemoryServiceProcess } from
  "../drivers/postgres/firebase-authorized-memory-service-process";
import type { CloseablePostgresTransactionPool } from "../drivers/postgres/postgresjs";
import { createPostgresJsTransactionPool } from "../drivers/postgres/postgresjs";
import { createPostgresProductionRuntimeReadiness } from
  "../drivers/postgres/production-runtime-readiness";
import {
  ambientPostgresSelectors,
  parsePostgresTestState,
  postgresTestConnectionString,
  postgresTestPaths,
  type PostgresTestState,
} from "./postgres-test-lifecycle";

const PROJECT_ROOT = realpathSync(resolve(import.meta.dir, ".."));
const LISTEN_PORT = 4851;
const GRACEFUL_SHUTDOWN_MS = 4_000;
export const LOCAL_FIREBASE_PROJECT_ID = "omi-local-pg";
export const LOCAL_APPLICATION_ID = "app:omi-local-pg";
/** Same fixture digest the real-PG qualification gate releases. Not a production generation. */
export const LOCAL_QUALIFICATION_DATABASE_GENERATION_DIGEST = "d".repeat(64);

export const PROD_LOCAL_PG_ABSENT =
  "omi prod-local: local PostgreSQL runtime is absent.";
export const PROD_LOCAL_PG_NOT_RUNNING =
  "omi prod-local: local PostgreSQL is configured but not accepting connections.";
export const PROD_LOCAL_AMBIENT_SELECTOR =
  "omi prod-local: ambient DATABASE_URL / PG* selectors are forbidden.";
export const PROD_LOCAL_IDENTITY_CANNOT_MINT =
  "omi prod-local: Firebase identity cannot be minted locally.";
export const PROD_LOCAL_IDENTITY_ADAPTER_UNAVAILABLE =
  "omi prod-local: Firebase Admin ID-token adapter could not be constructed.";
export const PROD_LOCAL_EMULATOR_FORBIDDEN =
  "omi prod-local: deployed Firebase identity forbids the Auth emulator.";
export const PROD_LOCAL_IDENTITY_EMULATOR_NOT_PRODUCTION =
  "omi prod-local: emulator identity — not production.";
export const PROD_LOCAL_LOCAL_IDENTITY_REQUIRES_EMULATOR =
  "omi prod-local: local-identity requires FIREBASE_AUTH_EMULATOR_HOST.";
export const PROD_LOCAL_LOCAL_IDENTITY_ENV_INVALID =
  "omi prod-local: OMI_PROD_LOCAL_IDENTITY must be unset or emulator.";
export const PROD_LOCAL_IDENTITY_FLAG = "--local-identity";
export const PROD_LOCAL_IDENTITY_ENV = "OMI_PROD_LOCAL_IDENTITY";
export const PROD_LOCAL_IDENTITY_ENV_VALUE = "emulator";
export const FIREBASE_AUTH_EMULATOR_HOST_ENV = "FIREBASE_AUTH_EMULATOR_HOST";

export type ProdLocalIdentityRuntimeMode = "deployed" | "local_test";

export type ProdLocalIdentityDecision =
  | { readonly kind: "deployed"; readonly runtime_mode: "deployed" }
  | { readonly kind: "local_test"; readonly runtime_mode: "local_test" }
  | { readonly kind: "refuse"; readonly message: string };

const emulatorHostPresent = (
  env: Readonly<Record<string, string | undefined>>,
): boolean => Object.prototype.hasOwnProperty.call(env, FIREBASE_AUTH_EMULATOR_HOST_ENV);

const localIdentityOptIn = (
  argv: readonly string[],
  env: Readonly<Record<string, string | undefined>>,
): { readonly optedIn: boolean } | { readonly refuse: string } => {
  const flag = argv.includes(PROD_LOCAL_IDENTITY_FLAG);
  const envPresent = Object.prototype.hasOwnProperty.call(env, PROD_LOCAL_IDENTITY_ENV);
  const envValue = env[PROD_LOCAL_IDENTITY_ENV];
  if (envPresent && envValue !== PROD_LOCAL_IDENTITY_ENV_VALUE) {
    return { refuse: PROD_LOCAL_LOCAL_IDENTITY_ENV_INVALID };
  }
  return { optedIn: flag || envValue === PROD_LOCAL_IDENTITY_ENV_VALUE };
};

/**
 * Default (no flag, no env) is deployed mode, including today's emulator
 * refusal. Opt-in is `--local-identity` or `OMI_PROD_LOCAL_IDENTITY=emulator`.
 */
export const resolveProdLocalIdentity = (
  argv: readonly string[],
  env: Readonly<Record<string, string | undefined>>,
): ProdLocalIdentityDecision => {
  const optIn = localIdentityOptIn(argv, env);
  if ("refuse" in optIn) {
    return {
      kind: "refuse",
      message: `${optIn.refuse}\n`
        + `  Supported opt-in: ${PROD_LOCAL_IDENTITY_FLAG}`
        + ` or ${PROD_LOCAL_IDENTITY_ENV}=${PROD_LOCAL_IDENTITY_ENV_VALUE}.`,
    };
  }
  const emulatorPresent = emulatorHostPresent(env);
  if (!optIn.optedIn) {
    if (!emulatorPresent) return { kind: "deployed", runtime_mode: "deployed" };
    return {
      kind: "refuse",
      message: `${PROD_LOCAL_EMULATOR_FORBIDDEN}\n`
        + "  Unset the emulator host. Production composition is runtime_mode=deployed.",
    };
  }
  const emulatorHost = env[FIREBASE_AUTH_EMULATOR_HOST_ENV];
  if (!emulatorPresent || typeof emulatorHost !== "string" || emulatorHost.length < 1) {
    return {
      kind: "refuse",
      message: `${PROD_LOCAL_LOCAL_IDENTITY_REQUIRES_EMULATOR}\n`
        + "  Start the owned Auth emulator, then export FIREBASE_AUTH_EMULATOR_HOST.\n"
        + "  bun run scripts/prod-local-identity.ts --start",
    };
  }
  return { kind: "local_test", runtime_mode: "local_test" };
};

export type ManagedPostgresPresence =
  | { readonly kind: "absent" }
  | { readonly kind: "not_ready" }
  | { readonly kind: "configured"; readonly state: PostgresTestState; readonly hostPort: number };

export const interpretManagedPostgresState = (
  state: PostgresTestState | null,
): ManagedPostgresPresence => {
  if (state === null) return { kind: "absent" };
  if (state.hostPort === null) return { kind: "not_ready" };
  return { kind: "configured", state, hostPort: state.hostPort };
};

const fail = (message: string): never => {
  process.stderr.write(`\n${message}\n\n`);
  process.exit(1);
};

const closedError = (message: string): never => fail(message);

const loadState = (): PostgresTestState | null => {
  const paths = postgresTestPaths(PROJECT_ROOT);
  if (!existsSync(paths.stateFile)) return null;
  try {
    return parsePostgresTestState(JSON.parse(readFileSync(paths.stateFile, "utf8")), PROJECT_ROOT);
  } catch {
    return closedError("omi prod-local: invalid managed PostgreSQL test state.");
  }
};

const passwordFrom = (state: PostgresTestState): string => {
  const line = readFileSync(state.credentialsFile, "utf8").split("\n")
    .find((entry) => entry.startsWith("POSTGRES_PASSWORD="));
  if (!line) return closedError("omi prod-local: managed PostgreSQL credentials are missing.");
  return line.slice("POSTGRES_PASSWORD=".length);
};

const portHeld = (port: number): boolean => {
  const result = Bun.spawnSync(["lsof", "-nP", `-iTCP:${port}`, "-sTCP:LISTEN"], {
    stdout: "pipe",
    stderr: "pipe",
  });
  return result.exitCode === 0 && result.stdout.toString().includes("(LISTEN)");
};

const withApplicationRole = (
  pool: CloseablePostgresTransactionPool,
): CloseablePostgresTransactionPool => Object.freeze({
  async withTransaction<Result>(
    options: Parameters<CloseablePostgresTransactionPool["withTransaction"]>[0],
    callback: Parameters<CloseablePostgresTransactionPool["withTransaction"]>[1],
  ): Promise<Result> {
    return pool.withTransaction(options, async (connection) => {
      await connection.query({
        name: "prod_local.set_application_role",
        text: "SET LOCAL ROLE omi_platform_application",
        values: [],
      });
      return callback(connection);
    });
  },
  tryWithSessionAdvisoryLock: (
    key: Parameters<CloseablePostgresTransactionPool["tryWithSessionAdvisoryLock"]>[0],
    callback: Parameters<CloseablePostgresTransactionPool["tryWithSessionAdvisoryLock"]>[1],
  ) => pool.tryWithSessionAdvisoryLock(key, callback),
  close: () => pool.close(),
});

const probeLoopbackPostgres = async (connectionString: string): Promise<boolean> => {
  const probe = createPostgresJsTransactionPool({
    connectionString,
    maxConnections: 1,
    connectTimeoutSeconds: 5,
  });
  try {
    return await probe.withTransaction(
      { isolationLevel: "serializable", accessMode: "read only" },
      async (connection) => {
        const rows = await connection.query<{ ok: number }>({
          name: "prod_local.probe",
          text: "SELECT 1 AS ok",
          values: [],
        });
        return rows[0]?.ok === 1;
      },
    );
  } catch {
    return false;
  } finally {
    await probe.close();
  }
};

const jsonUnavailable = (): Response => new Response(
  JSON.stringify({ status: "unavailable" }),
  {
    status: 503,
    headers: {
      "cache-control": "no-store",
      "content-type": "application/json",
    },
  },
);

const main = async (): Promise<void> => {
  if (ambientPostgresSelectors(process.env).length > 0) {
    return fail(
      `${PROD_LOCAL_AMBIENT_SELECTOR}\n`
      + "  Unset them. This script uses only the managed local PostgreSQL harness.",
    );
  }

  const presence = interpretManagedPostgresState(loadState());
  if (presence.kind === "absent") {
    return fail(
      `${PROD_LOCAL_PG_ABSENT}\n`
      + "  configured=false runtime=absent container=absent volume=absent\n"
      + "  Start it with: bun run test:postgres:setup",
    );
  }
  if (presence.kind === "not_ready") {
    return fail(
      `${PROD_LOCAL_PG_NOT_RUNNING}\n`
      + "  The managed harness has no loopback port yet.\n"
      + "  Start it with: bun run test:postgres:setup",
    );
  }

  const connectionString = postgresTestConnectionString(
    presence.state,
    passwordFrom(presence.state),
  );
  if (!await probeLoopbackPostgres(connectionString)) {
    return fail(
      `${PROD_LOCAL_PG_NOT_RUNNING}\n`
      + "  configured=true container is not reachable on loopback.\n"
      + "  Start it with: bun run test:postgres:setup",
    );
  }

  const identity = resolveProdLocalIdentity(process.argv, process.env);
  if (identity.kind === "refuse") {
    return fail(identity.message);
  }

  if (portHeld(LISTEN_PORT)) {
    return fail(
      `omi prod-local: port ${LISTEN_PORT} is already in use. Something else is listening.\n`
      + `  Find it:  lsof -nP -iTCP:${LISTEN_PORT} -sTCP:LISTEN\n`
      + "  Stop the existing listener before booting the production process.",
    );
  }

  const ownerPool = createPostgresJsTransactionPool({
    connectionString,
    maxConnections: 4,
  });
  const pool = withApplicationRole(ownerPool);

  let identityHandle;
  try {
    identityHandle = await createFirebaseAdminIdTokenAdapter({
      project_id: LOCAL_FIREBASE_PROJECT_ID,
      app_name: `omi-prod-local-${process.pid}`,
      runtime_mode: identity.runtime_mode,
    });
  } catch {
    await ownerPool.close();
    return fail(
      `${PROD_LOCAL_IDENTITY_ADAPTER_UNAVAILABLE}\n`
      + "  Application Default Credentials are required to construct the official\n"
      + "  Firebase Admin verifier. This script will not install a stub verifier.",
    );
  }

  const codecRootSecret = randomBytes(32);
  const service_options = {
    mcp_handler: async () => jsonUnavailable(),
    memory_read: {
      authorization: {
        pool,
        project_id: LOCAL_FIREBASE_PROJECT_ID,
        runtime_mode: identity.runtime_mode,
        id_token_adapter: identityHandle.adapter,
        application_id: LOCAL_APPLICATION_ID,
        context_ttl_seconds: 60,
        database_generation_digest: LOCAL_QUALIFICATION_DATABASE_GENERATION_DIGEST,
      },
      product: {
        account_timezone: "UTC",
        codec_root_secret: codecRootSecret,
        produce_renders: async () => [],
        verify_cursor: () => { throw new InvalidMcpCursorError(); },
        issue_cursor: () => { throw new InvalidMcpCursorError(); },
        trace_sink: () => undefined,
        accepted_coverage_state: "bypassed" as const,
        stm_coverage_state: "bypassed" as const,
      },
    },
    now_epoch_seconds: () => Math.floor(Date.now() / 1_000),
    counter: createServedCounter(),
  };

  const memoryProcess = createPostgresFirebaseAuthorizedMemoryServiceProcess({
    pool,
    service_options,
    readiness: createPostgresProductionRuntimeReadiness(
      pool,
      LOCAL_QUALIFICATION_DATABASE_GENERATION_DIGEST,
    ),
    graceful_shutdown_ms: GRACEFUL_SHUTDOWN_MS,
  });

  const started = await memoryProcess.start();
  const bind = loopbackServeOptions(LISTEN_PORT);
  let server: ReturnType<typeof Bun.serve>;
  try {
    server = Bun.serve({
      hostname: bind.hostname,
      port: bind.port,
      fetch: (request) => memoryProcess.fetch(request),
    });
  } catch (error) {
    await memoryProcess.stop();
    try { await identityHandle.close(); } catch { /* closed failure stays closed */ }
    const message = error instanceof Error ? error.message : "";
    if (/EADDRINUSE|address already in use/i.test(message)) {
      return fail(
        `omi prod-local: port ${LISTEN_PORT} is already in use. Something else is listening.\n`
        + `  Find it:  lsof -nP -iTCP:${LISTEN_PORT} -sTCP:LISTEN\n`
        + "  Stop the existing listener before booting the production process.",
      );
    }
    return fail(`omi prod-local: failed to bind ${LOOPBACK_HOST}:${LISTEN_PORT}.`);
  }

  const baseUrl = `http://${LOOPBACK_HOST}:${LISTEN_PORT}`;
  const ready = started.kind === "ready";
  const identityBanner = identity.kind === "local_test"
    ? `  ${PROD_LOCAL_IDENTITY_EMULATOR_NOT_PRODUCTION}\n`
      + "  runtime_mode=local_test with the official Admin verifier against the Auth\n"
      + "  emulator. This is not production. Mint a user with\n"
      + "  bun run scripts/prod-local-identity.ts --mint, then seed authorization\n"
      + "  rows with bun run scripts/prod-local-identity-seed.ts --uid <uid>.\n\n"
    : `  ${PROD_LOCAL_IDENTITY_CANNOT_MINT}\n`
      + "  David has not granted a token-minting credential. This process will not\n"
      + "  install a stub verifier, a dev token, or the Auth emulator. Present a\n"
      + "  real Firebase ID token to exercise verification; this script cannot issue one.\n\n";
  process.stdout.write(
    `\nomi prod-local is up\n\n`
    + `  base URL      ${baseUrl}\n`
    + `  bound to      ${LOOPBACK_HOST} (loopback only - not reachable from the LAN)\n`
    + `  composition   PostgreSQL Firebase production memory process\n`
    + `  process phase ${ready ? "ready" : "unavailable"}\n`
    + `  postgres      127.0.0.1 (managed harness; credentials not printed)\n\n`
    + identityBanner
    + "  MCP credentials, production codec key material, and a production\n"
    + "  synthesizer are also not granted. MCP answers 503. Renders are empty\n"
    + "  rather than QA-synthesized.\n\n"
    + "  try it\n"
    + `    curl -s ${baseUrl}/health\n`
    + `    curl -s ${baseUrl}/ready\n\n`,
  );

  let stopping = false;
  const shutdown = async (): Promise<void> => {
    if (stopping) return;
    stopping = true;
    server.stop(true);
    const stopped = await memoryProcess.stop();
    try { await identityHandle.close(); } catch { /* closed failure stays closed */ }
    process.stdout.write(
      `\nomi prod-local: stopped (${stopped.kind}`
      + `${stopped.kind === "stopped" ? `, drained=${stopped.drained}` : ""})\n`,
    );
    process.exit(stopped.kind === "failed" ? 1 : 0);
  };
  process.on("SIGINT", () => { void shutdown(); });
  process.on("SIGTERM", () => { void shutdown(); });
};

if (import.meta.main) {
  await main();
}
