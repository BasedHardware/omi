import { readFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";

import postgres from "postgres";

const expectedPostgresJsVersion = "3.4.9";
const expectedServerVersion = 180004;
const expectedRuntime = process.env.OMI_TEST_RUNTIME;
if (expectedRuntime === "bun") {
  if (typeof Bun === "undefined" || Bun.version !== "1.3.14") throw new Error("postgres_runtime_parity_bun_version_mismatch");
} else if (expectedRuntime === "node") {
  if (process.version !== "v24.19.0") throw new Error("postgres_runtime_parity_node_version_mismatch");
} else {
  throw new Error("postgres_runtime_parity_runtime_missing");
}
const connectionString = process.env.OMI_TEST_POSTGRES_URL;
if (!connectionString) throw new Error("postgres_runtime_parity_url_missing");
const parsed = new URL(connectionString);
if (parsed.protocol !== "postgres:" || parsed.hostname !== "127.0.0.1" || parsed.port !== "5432") {
  throw new Error("postgres_runtime_parity_not_container_local");
}
const packageMetadata = JSON.parse(await readFile(
  new URL("./node_modules/postgres/package.json", import.meta.url), "utf8",
));
if (packageMetadata.version !== expectedPostgresJsVersion) {
  throw new Error("postgres_runtime_parity_client_version_mismatch");
}

let closeGeneration = 0;
const sql = postgres(connectionString, {
  max: 1, prepare: true, onclose: () => { closeGeneration += 1; },
});
const observer = postgres(connectionString, { max: 1, prepare: true });
try {
  const version = await sql.unsafe("SHOW server_version_num");
  if (Number(version[0]?.server_version_num) !== expectedServerVersion) {
    throw new Error("postgres_runtime_parity_server_version_mismatch");
  }
  let backendPid;
  try {
    await sql.begin("isolation level serializable read write", async (transaction) => {
      const rows = await transaction.unsafe(
        "SELECT pg_backend_pid() AS backend_pid, set_config('omi.parity', $1, true) AS local_value",
        ["set"],
      );
      backendPid = rows[0]?.backend_pid;
      throw new Error("parity_rollback");
    });
  } catch (error) {
    if (!(error instanceof Error) || error.message !== "parity_rollback") throw error;
  }
  await sql.begin("isolation level serializable read write", async (transaction) => {
    const rows = await transaction.unsafe(
      "SELECT pg_backend_pid() AS backend_pid, nullif(current_setting('omi.parity', true), '') AS local_value",
    );
    if (rows[0]?.backend_pid !== backendPid || rows[0]?.local_value !== null) {
      throw new Error("postgres_runtime_parity_transaction_mismatch");
    }
  });

  const terminatedAccount = `account:runtime-termination:${expectedRuntime}:${randomUUID()}`;
  const reserved = await sql.reserve();
  const startingCloseGeneration = closeGeneration;
  let terminatedBackend;
  try {
    await reserved.unsafe("begin isolation level serializable read write");
    const rows = await reserved.unsafe("SELECT pg_backend_pid() AS backend_pid");
    terminatedBackend = rows[0]?.backend_pid;
    await reserved.unsafe(
      "INSERT INTO omi_memory.platform_accounts (account_id) VALUES ($1)",
      [terminatedAccount],
    );
    await observer.unsafe("SELECT pg_terminate_backend($1)", [terminatedBackend]);
    for (let attempt = 0; attempt < 100 && closeGeneration === startingCloseGeneration; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 10));
    }
  } catch {
    // The runtime gate below uses the close generation and observer state, not
    // provider text or the timing-dependent choice of 57P01 vs CONNECTION_CLOSED.
  }
  if (closeGeneration === startingCloseGeneration) {
    throw new Error("postgres_runtime_parity_termination_not_observed");
  }
  const rolledBack = await observer.unsafe(
    "SELECT count(*)::int AS count FROM omi_memory.platform_accounts WHERE account_id = $1",
    [terminatedAccount],
  );
  const recovered = await sql.unsafe("SELECT pg_backend_pid() AS backend_pid");
  if (rolledBack[0]?.count !== 0 || recovered[0]?.backend_pid === terminatedBackend) {
    throw new Error("postgres_runtime_parity_termination_recovery_mismatch");
  }
  process.stdout.write(`${JSON.stringify({
    status: "passed", runtime: expectedRuntime,
    postgres: expectedServerVersion, postgresJs: expectedPostgresJsVersion,
    backendTermination: "reconnected",
  })}\n`);
} finally {
  await observer.end({ timeout: 5 });
  await sql.end({ timeout: 5 });
}
