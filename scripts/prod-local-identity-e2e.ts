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

import { spawn, spawnSync } from "node:child_process";
import { existsSync, readFileSync, realpathSync } from "node:fs";
import { resolve } from "node:path";
import { randomBytes } from "node:crypto";

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
  IDENTITY_FIREBASE_JSON,
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
const LISTEN_PORT = 4851;

const fail = (message: string): never => {
  process.stderr.write(`\n${message}\n\n`);
  process.exit(1);
};

const run = (
  args: readonly string[],
  env: NodeJS.ProcessEnv = process.env,
): { readonly status: number | null; readonly out: string } => {
  const result = spawnSync("bun", ["run", ...args], {
    cwd: PROJECT_ROOT,
    encoding: "utf8",
    env,
  });
  return { status: result.status, out: `${result.stdout}${result.stderr}` };
};

const listeners = (port: number): string => {
  const result = spawnSync("lsof", ["-nP", `-iTCP:${port}`, "-sTCP:LISTEN"], {
    encoding: "utf8",
  });
  return result.stdout ?? "";
};

const ownedEmulatorPids = (): string => {
  const result = spawnSync("pgrep", ["-f", IDENTITY_FIREBASE_JSON], { encoding: "utf8" });
  return (result.stdout ?? "").trim();
};

const curl = async (
  path: string,
  headers: Readonly<Record<string, string>> = {},
): Promise<{ readonly status: number; readonly body: string }> => {
  const response = await fetch(`http://127.0.0.1:${LISTEN_PORT}${path}`, { headers });
  return { status: response.status, body: await response.text() };
};

const waitFor = async (probe: () => Promise<boolean>, timeoutMs: number): Promise<boolean> => {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await probe()) return true;
    await Bun.sleep(200);
  }
  return probe();
};

const proveViaProcessFetch = async (
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
  const identity = await createFirebaseAdminIdTokenAdapter({
    project_id: LOCAL_FIREBASE_PROJECT_ID,
    app_name: `omi-prod-local-e2e-${process.pid}`,
    runtime_mode: "local_test",
  });
  const memoryProcess = createPostgresFirebaseAuthorizedMemoryServiceProcess({
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
    },
    readiness: createPostgresProductionRuntimeReadiness(
      pool,
      LOCAL_QUALIFICATION_DATABASE_GENERATION_DIGEST,
    ),
    graceful_shutdown_ms: 4_000,
  });
  try {
    await memoryProcess.start();
    const read = async (path: string, token?: string) => {
      const response = await memoryProcess.fetch(new Request(`http://127.0.0.1${path}`, {
        headers: token === undefined ? {} : { authorization: `Bearer ${token}` },
      }));
      return { status: response.status, body: await response.text() };
    };
    return {
      health: await read("/health"),
      ready: await read("/ready"),
      authorized: await read("/v1/memories?limit=5", seededToken),
      denied: await read("/v1/memories?limit=5", unseededToken),
    };
  } finally {
    await memoryProcess.stop();
    try { await identity.close(); } catch { /* closed failure stays closed */ }
    await ownerPool.close();
  }
};

const main = async (): Promise<void> => {
  const portLease = listeners(LISTEN_PORT);
  const started = run(["scripts/prod-local-identity.ts", "--start"]);
  if (started.status !== 0) return fail(started.out);
  process.stdout.write(started.out);

  const env: NodeJS.ProcessEnv = {
    ...process.env,
    FIREBASE_AUTH_EMULATOR_HOST: FIREBASE_AUTH_EMULATOR_HOST_VALUE,
  };
  let server: ReturnType<typeof spawn> | null = null;
  try {
    const seededMint = run(["scripts/prod-local-identity.ts", "--mint"], env);
    if (seededMint.status !== 0) return fail(seededMint.out);
    process.stdout.write(seededMint.out);
    const seededUid = /uid\s+(\S+)/.exec(seededMint.out)?.[1];
    const seededToken = /Authorization: Bearer (\S+)/.exec(seededMint.out)?.[1];
    if (!seededUid || !seededToken) return fail("omi prod-local-identity-e2e: mint did not print uid and bearer.");

    const unseededMint = run(["scripts/prod-local-identity.ts", "--mint"], env);
    if (unseededMint.status !== 0) return fail(unseededMint.out);
    const unseededUid = /uid\s+(\S+)/.exec(unseededMint.out)?.[1];
    const unseededToken = /Authorization: Bearer (\S+)/.exec(unseededMint.out)?.[1];
    if (!unseededUid || !unseededToken) {
      return fail("omi prod-local-identity-e2e: second mint did not print uid and bearer.");
    }

    const seeded = run(["scripts/prod-local-identity-seed.ts", "--uid", seededUid], env);
    if (seeded.status !== 0) return fail(seeded.out);
    process.stdout.write(seeded.out);

    let health: { readonly status: number; readonly body: string };
    let ready: { readonly status: number; readonly body: string };
    let authorized: { readonly status: number; readonly body: string };
    let denied: { readonly status: number; readonly body: string };

    if (portLease.includes("(LISTEN)")) {
      process.stdout.write(
        `omi prod-local-identity-e2e: port ${LISTEN_PORT} is leased; proving via the same fetch handler prod-local serves.\n`
        + portLease
        + `  Find it: lsof -nP -iTCP:${LISTEN_PORT} -sTCP:LISTEN\n`,
      );
      const proof = await proveViaProcessFetch(seededToken, unseededToken);
      health = proof.health;
      ready = proof.ready;
      authorized = proof.authorized;
      denied = proof.denied;
    } else {
      server = spawn("bun", ["run", "scripts/prod-local.ts", "--local-identity"], {
        cwd: PROJECT_ROOT,
        env,
        stdio: ["ignore", "pipe", "pipe"],
      });
      let boot = "";
      server.stdout?.on("data", (chunk: Buffer | string) => { boot += chunk.toString(); });
      server.stderr?.on("data", (chunk: Buffer | string) => { boot += chunk.toString(); });
      const booted = await waitFor(async () => boot.includes("omi prod-local is up"), 20_000);
      if (!booted) return fail(`omi prod-local-identity-e2e: prod-local did not boot.\n${boot}`);
      process.stdout.write(boot);
      health = await curl("/health");
      ready = await curl("/ready");
      authorized = await curl("/v1/memories?limit=5", {
        authorization: `Bearer ${seededToken}`,
      });
      denied = await curl("/v1/memories?limit=5", {
        authorization: `Bearer ${unseededToken}`,
      });
    }

    process.stdout.write(
      `\nE2E_HEALTH ${health.status} ${health.body}\n`
      + `E2E_READY ${ready.status} ${ready.body}\n`
      + `E2E_SEEDED_UID ${seededUid} ${authorized.status} ${authorized.body}\n`
      + `E2E_UNSEEDED_UID ${unseededUid} ${denied.status} ${denied.body}\n`,
    );

    if (authorized.status !== 200) {
      return fail(`omi prod-local-identity-e2e: seeded uid did not return 200 (${authorized.status}).`);
    }
    if (denied.status === 200) {
      return fail("omi prod-local-identity-e2e: unseeded uid was not denied.");
    }
  } finally {
    if (server?.pid) {
      try { process.kill(server.pid, "SIGTERM"); } catch { /* already exited */ }
      await waitFor(async () => !listeners(LISTEN_PORT).includes("(LISTEN)"), 8_000);
    }
    const stopped = run(["scripts/prod-local-identity.ts", "--stop"]);
    process.stdout.write(stopped.out);
  }

  const leftoverPorts = listeners(AUTH_EMULATOR_PORT);
  const leftoverPids = ownedEmulatorPids();
  process.stdout.write(
    `E2E_TEARDOWN_LSOF ${leftoverPorts.trim() || "none"}\n`
    + `E2E_TEARDOWN_PGREP ${leftoverPids || "none"}\n`,
  );
  if (leftoverPorts.includes("(LISTEN)") || leftoverPids.length > 0) {
    return fail("omi prod-local-identity-e2e: owned emulator leaked after --stop.");
  }
};

if (import.meta.main) {
  await main();
}
