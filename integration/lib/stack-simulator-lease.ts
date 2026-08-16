#!/usr/bin/env bun
/**
 * Acquire and hold a run-scoped iOS simulator.
 *
 * Usage:
 *   bun integration/lib/stack-simulator-lease.ts hold \
 *     --run-id <raw-id> --out <lease.json> \
 *     [--parent-pid <pid>] [--lease-root <dir>]
 *
 * Stays alive until SIGTERM/SIGINT, or until --parent-pid dies.
 * Releasing the process releases the lock. A crash leaves a stale lock
 * whose dead pid the next acquire replaces, unless a live holder still
 * owns the device. A live holder is skipped, never evicted; a device
 * this process did not boot is never shut down or erased.
 *
 * Cap: 4 concurrent live simulator leases. Exhausting it is a refusal
 * that names the holders, not a timeout.
 */

import { writeFileSync } from "node:fs";

import {
  SIMULATOR_LEASE_MAX_CONCURRENT,
  acquireSimulatorLease,
} from "../../apps/service/net/simulator-lease";
import { processStartIdentity } from "../../apps/service/net/port-lease";

const SCHEMA = "omi.stack-simulator-lease.v1";

const flag = (argv: readonly string[], name: string): string | null => {
  const index = argv.indexOf(name);
  return index === -1 ? null : argv[index + 1] ?? null;
};

const fail = (message: string, code = 1): never => {
  process.stderr.write(`ERROR: ${message}\n`);
  process.exit(code);
};

const argv = process.argv.slice(2);
const command = argv[0];
if (command !== "hold" || argv.includes("--help") || argv.includes("-h")) {
  process.stdout.write(
    "usage: bun integration/lib/stack-simulator-lease.ts hold --run-id <id> --out <json>\n",
  );
  process.exit(command === "hold" ? 2 : 0);
}

const runId = flag(argv, "--run-id");
const outPath = flag(argv, "--out");
const parentPidRaw = flag(argv, "--parent-pid");
const leaseRoot = flag(argv, "--lease-root") ?? undefined;

if (!runId || !outPath) {
  fail("hold needs --run-id and --out", 2);
}

const parentPid = parentPidRaw === null ? null : Number(parentPidRaw);
if (parentPidRaw !== null && (!Number.isSafeInteger(parentPid) || parentPid <= 0)) {
  fail("--parent-pid must be a positive integer", 2);
}

let held: { release: () => void } | null = null;
const releaseAll = () => {
  held?.release();
  held = null;
};

process.on("SIGINT", () => {
  releaseAll();
  process.exit(130);
});
process.on("SIGTERM", () => {
  releaseAll();
  process.exit(0);
});

try {
  const lease = acquireSimulatorLease({
    runId,
    ...(leaseRoot === undefined ? {} : { leaseRoot }),
  });
  held = lease;
  writeFileSync(outPath, `${JSON.stringify({
    schema: SCHEMA,
    runId,
    udid: lease.record.udid,
    name: lease.record.name,
    holderPid: process.pid,
    bootedByHolder: lease.bootedByHolder,
    maxConcurrent: SIMULATOR_LEASE_MAX_CONCURRENT,
  }, null, 2)}\n`, { encoding: "utf8", mode: 0o600 });
} catch (error) {
  releaseAll();
  fail(error instanceof Error ? error.message : "simulator lease acquire failed");
}

if (parentPid !== null) {
  const timer = setInterval(() => {
    if (processStartIdentity(parentPid) === null) {
      clearInterval(timer);
      releaseAll();
      process.exit(0);
    }
  }, 250);
}

await new Promise(() => {});
