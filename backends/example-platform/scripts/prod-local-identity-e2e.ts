#!/usr/bin/env bun
/**
 * Acceptance recipe for prod-local emulator identity.
 *
 * PG harness up → owned Auth emulator → mint → seed → prod-local --local-identity
 * → authorized memories.read 200 and unseeded uid denied → teardown with no
 * owned emulator orphans.
 *
 * This script does not start PostgreSQL or release the qualification
 * generation. Those stay `bun run test:postgres:setup` and
 * `bun run test:postgres:preserve`.
 */

import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, realpathSync } from "node:fs";
import { resolve } from "node:path";
import { randomBytes } from "node:crypto";

import type { TreeInputSnapshot } from "../core/retrieve/index";
import { buildDeterministicAnchors } from "../core/retrieve/tree";
import { renderStructuralTree } from "../core/retrieve/render";
import { InvalidMcpCursorError } from "../apps/mcp/cursor";
import { createServedCounter } from "../apps/service/observability/served-count";
import { createFirebaseAdminIdTokenAdapter } from "../drivers/firebase/admin-id-token";
import { createPostgresFirebaseAuthorizedMemoryServiceProcess } from
  "../drivers/postgres/firebase-authorized-memory-service-process";
import { createPostgresJsTransactionPool } from "../drivers/postgres/postgresjs";
import { createPostgresProductionRuntimeReadiness } from
  "../drivers/postgres/production-runtime-readiness";
import {
  AUTH_EMULATOR_PORT,
  FIREBASE_AUTH_EMULATOR_HOST_VALUE,
  IDENTITY_PID_FILE,
  IDENTITY_LOG_FILE,
  mintEmulatorIdentity,
  portHeld,
  withIdentityLease,
} from "./prod-local-identity";
import {
  LOCAL_APPLICATION_ID,
  LOCAL_FIREBASE_PROJECT_ID,
  LOCAL_QUALIFICATION_DATABASE_GENERATION_DIGEST,
  interpretManagedPostgresState,
} from "./prod-local";
import {
  parsePostgresTestState,
  postgresTestConnectionString,
  postgresTestPaths,
} from "./postgres-test-lifecycle";

const PROJECT_ROOT = realpathSync(resolve(import.meta.dir, ".."));


const fail = (message: string): never => { throw new Error(message); };

const run = (args: readonly string[], env: NodeJS.ProcessEnv): void => {
  const result = spawnSync(process.execPath, ["run", ...args], {
    cwd: PROJECT_ROOT, encoding: "utf8", env, timeout: 90_000,
  });
  if (result.status !== 0 || result.error) throw new Error(`identity acceptance command failed: ${args[0]} (exit=${result.status ?? "none"}, signal=${result.signal ?? "none"}, error=${result.error ? "spawn_or_timeout" : "none"}); emulator log: ${IDENTITY_LOG_FILE}`);
};

export const assertIdentityAcceptance = (statuses: { health: number; ready: number; authorized: number; denied: number }): void => {
  if (statuses.health !== 200 || statuses.ready !== 200 || statuses.authorized !== 200 || statuses.denied !== 403)
    throw new Error(`identity acceptance requires health200, ready200, authorized200 and unseeded403; received ${JSON.stringify(statuses)}`);
};

export const runOwnedIdentityAcceptance = async (
  start: () => Promise<void>, prove: () => Promise<void>, stop: () => Promise<void>,
): Promise<void> => {
  let failed = false;
  try { await start(); await prove(); } catch (cause) { failed = true; throw cause; }
  finally {
    try { await stop(); } catch (cause) { if (!failed) throw cause; }
  }
};

export const closeIdentityAcceptance = async (
  stopServer: () => unknown | Promise<unknown>,
  stopProcess: () => Promise<{ kind: string; drained?: boolean } | undefined>,
  closeIdentity: () => unknown | Promise<unknown>, closePool: () => unknown | Promise<unknown>,
): Promise<void> => {
  let failed = false;
  try { await stopServer(); } catch { failed = true; }
  try {
    const outcome = await stopProcess();
    if (outcome && (outcome.kind !== "stopped" || outcome.drained !== true)) failed = true;
  } catch { failed = true; }
  const closed = await Promise.allSettled([
    Promise.resolve().then(closeIdentity), Promise.resolve().then(closePool),
  ]);
  if (failed || closed.some(result => result.status === "rejected"))
    throw new Error("identity acceptance resource cleanup failed");
};

export const produceIdentityAcceptanceRenders = async (projected: TreeInputSnapshot) => {
            if (projected.claims.length !== 0) throw new Error("identity acceptance requires an empty account");
            return renderStructuralTree(buildDeterministicAnchors(projected), projected, {
              render: async () => { throw new Error("identity acceptance must not invoke a model"); },
            }, { strategy: "application-memory-render", model_version: "identity-acceptance-no-model",
              prompt_version: "grounded-memory-v1", policy_version: "authorized-claims-v1", schema_version: "summary-citations-v1" });
};

const proveViaOwnedHttp = async (
  seededToken: string,
  unseededToken: string,
): Promise<{
  readonly health: { readonly status: number; readonly body: string };
  readonly ready: { readonly status: number; readonly body: string };
  readonly authorized: { readonly status: number; readonly body: string };
  readonly denied: { readonly status: number; readonly body: string };
}> => {
  const paths = postgresTestPaths(PROJECT_ROOT);
  if (!existsSync(paths.stateFile)) {
    return fail("omi prod-local-identity-e2e: managed PostgreSQL state is absent.");
  }
  const state = parsePostgresTestState(JSON.parse(readFileSync(paths.stateFile, "utf8")), PROJECT_ROOT);
  const presence = interpretManagedPostgresState(state);
  if (presence.kind !== "configured") {
    return fail("omi prod-local-identity-e2e: managed PostgreSQL is not accepting connections.");
  }
  const passwordLine = readFileSync(presence.state.credentialsFile, "utf8").split("\n")
    .find((entry) => entry.startsWith("POSTGRES_PASSWORD="));
  if (!passwordLine) return fail("omi prod-local-identity-e2e: managed PostgreSQL credentials are missing.");
  const connectionString = postgresTestConnectionString(
    presence.state,
    passwordLine.slice("POSTGRES_PASSWORD=".length),
  );
  const ownerPool = createPostgresJsTransactionPool({ connectionString, maxConnections: 4 });
  const pool = Object.freeze({
    async withTransaction<Result>(
      options: Parameters<typeof ownerPool.withTransaction>[0],
      callback: Parameters<typeof ownerPool.withTransaction>[1],
    ): Promise<Result> {
      return ownerPool.withTransaction(options, async (connection) => {
        await connection.query({
          name: "prod_local_identity_e2e.set_application_role",
          text: "SET LOCAL ROLE omi_platform_application",
          values: [],
        });
        return callback(connection);
      });
    },
    tryWithSessionAdvisoryLock: ownerPool.tryWithSessionAdvisoryLock.bind(ownerPool),
    close: () => ownerPool.close(),
  });
  let identity: Awaited<ReturnType<typeof createFirebaseAdminIdTokenAdapter>> | undefined;
  let memoryProcess: ReturnType<typeof createPostgresFirebaseAuthorizedMemoryServiceProcess> | undefined;
  let server: ReturnType<typeof Bun.serve> | undefined;
  let failed = false;
  try {
  identity = await createFirebaseAdminIdTokenAdapter({
    project_id: LOCAL_FIREBASE_PROJECT_ID,
    app_name: `omi-prod-local-e2e-${process.pid}`,
    runtime_mode: "local_test",
  });
  memoryProcess = createPostgresFirebaseAuthorizedMemoryServiceProcess({
    pool,
    service_options: {
      mcp_handler: async () => new Response(JSON.stringify({ status: "unavailable" }), { status: 503 }),
      memory_read: {
        authorization: {
          pool,
          project_id: LOCAL_FIREBASE_PROJECT_ID,
          runtime_mode: "local_test",
          id_token_adapter: identity.adapter,
          application_id: LOCAL_APPLICATION_ID,
          context_ttl_seconds: 60,
          database_generation_digest: LOCAL_QUALIFICATION_DATABASE_GENERATION_DIGEST,
        },
        product: {
          account_timezone: "UTC",
          codec_root_secret: randomBytes(32),
          produce_renders: produceIdentityAcceptanceRenders,
          verify_cursor: () => { throw new InvalidMcpCursorError(); },
          issue_cursor: () => { throw new InvalidMcpCursorError(); },
          trace_sink: () => undefined,
          accepted_coverage_state: "bypassed" as const,
          stm_coverage_state: "bypassed" as const,
        },
      },
      now_epoch_seconds: () => Math.floor(Date.now() / 1_000),
      counter: createServedCounter(),
    },
    readiness: createPostgresProductionRuntimeReadiness(
      pool,
      LOCAL_QUALIFICATION_DATABASE_GENERATION_DIGEST,
    ),
    graceful_shutdown_ms: 4_000,
  });
    await memoryProcess.start();
    server = Bun.serve({ hostname: "127.0.0.1", port: 0, fetch: request => memoryProcess!.fetch(request) });
    const origin = `http://127.0.0.1:${server.port}`;
    const read = async (path: string, token?: string) => {
      const response = await fetch(`${origin}${path}`, {
        signal: AbortSignal.timeout(10_000),
        headers: token === undefined ? {} : { authorization: `Bearer ${token}` },
      });
      return { status: response.status, body: await response.text() };
    };
    return {
      health: await read("/health"),
      ready: await read("/ready"),
      authorized: await read("/v1/memories?limit=5", seededToken),
      denied: await read("/v1/memories?limit=5", unseededToken),
    };
  } catch (cause) { failed = true; throw cause; } finally {
    try {
      await closeIdentityAcceptance(() => server?.stop(true), async () => memoryProcess?.stop(),
        () => identity?.close(), () => ownerPool.close());
    } catch (cause) { if (!failed) throw cause; }

  }
};

const main = async (): Promise<void> => withIdentityLease(async lease => {
  if (existsSync(IDENTITY_PID_FILE) || portHeld(AUTH_EMULATOR_PORT))
    throw new Error("identity acceptance requires an unused owned emulator slot; existing services were not changed");
  const previousHost = process.env.FIREBASE_AUTH_EMULATOR_HOST;
  process.env.FIREBASE_AUTH_EMULATOR_HOST = FIREBASE_AUTH_EMULATOR_HOST_VALUE;
  const env = { ...process.env, OMI_IDENTITY_LIFECYCLE_LEASE: lease };
  try {
    await runOwnedIdentityAcceptance(
      async () => run(["scripts/prod-local-identity.ts", "--start"], env),
      async () => {
        const seeded = await mintEmulatorIdentity();
        const unseeded = await mintEmulatorIdentity();
        run(["scripts/prod-local-identity-seed.ts", "--uid", seeded.uid], env);
        const proof = await proveViaOwnedHttp(seeded.idToken, unseeded.idToken);
        const statuses = { health: proof.health.status, ready: proof.ready.status,
          authorized: proof.authorized.status, denied: proof.denied.status };
        assertIdentityAcceptance(statuses);
        process.stdout.write(`${JSON.stringify({ proof: "local-emulator-identity-admission-only", ...statuses })}\n`);
      },
      async () => run(["scripts/prod-local-identity.ts", "--stop"], env),
    );
    if (portHeld(AUTH_EMULATOR_PORT) || existsSync(IDENTITY_PID_FILE))
      throw new Error("identity acceptance emulator cleanup incomplete");
    process.stdout.write("identity acceptance owned emulator cleanup passed\n");
  } finally {
    if (previousHost === undefined) delete process.env.FIREBASE_AUTH_EMULATOR_HOST;
    else process.env.FIREBASE_AUTH_EMULATOR_HOST = previousHost;
  }
});

if (import.meta.main) {
  try { await main(); } catch (cause) {
    process.stderr.write(`${cause instanceof Error ? cause.message : "identity acceptance failed"}\n`);
    process.exitCode = 1;
  }
}
