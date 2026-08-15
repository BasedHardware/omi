import { writeFileSync, readFileSync } from "node:fs";

import { LOOPBACK_HOST, type LoopbackServeOptions } from "./loopback";
import {
  APP_FACING_TEST_PORT_MAX,
  APP_FACING_TEST_PORT_MIN,
  acquirePortLease,
  holderIsLive,
  parsePortLeaseRecord,
  processStartIdentity,
  type AcquirePortLeaseOptions,
  type HeldPortLease,
} from "./port-lease";

/**
 * Explicit test-only bind path for the app-facing service.
 *
 * Production `assertPortInRange` / `loopbackServeOptions` still accept 4851
 * and nothing else. A leased test port is reachable only through this module:
 * acquire or load a live `AppFacingTestLease`, then call
 * `loopbackServeOptionsForTestLease`. There is no environment variable that
 * enters this mode.
 */

export const APP_FACING_TEST_LEASE_SCHEMA = "omi.app-facing-test-port-lease.v1";

const liveLeases = new WeakSet<object>();

export type AppFacingTestLease = {
  readonly schema: typeof APP_FACING_TEST_LEASE_SCHEMA;
  readonly port: number;
  readonly lockPath: string;
  readonly runId: string;
  readonly holderPid: number;
  readonly holderStartIdentity: string;
  readonly release: () => void;
};

export type AppFacingTestLeaseFile = {
  readonly schema: typeof APP_FACING_TEST_LEASE_SCHEMA;
  readonly port: number;
  readonly lockPath: string;
  readonly runId: string;
  readonly pid: number;
  readonly startIdentity: string;
};

const isLiveLease = (value: object): value is AppFacingTestLease => liveLeases.has(value);

export function isAppFacingTestPort(port: number): boolean {
  return Number.isInteger(port)
    && port >= APP_FACING_TEST_PORT_MIN
    && port <= APP_FACING_TEST_PORT_MAX;
}

function register(lease: AppFacingTestLease): AppFacingTestLease {
  liveLeases.add(lease);
  return lease;
}

export function acquireAppFacingTestLease(
  options: Pick<AcquirePortLeaseOptions, "runId" | "leaseRoot" | "range">,
): AppFacingTestLease {
  const held = acquirePortLease({
    role: "app-facing",
    runId: options.runId,
    ...(options.leaseRoot === undefined ? {} : { leaseRoot: options.leaseRoot }),
    ...(options.range === undefined ? {} : { range: options.range }),
  });
  return leaseFromHeld(held);
}

function leaseFromHeld(held: HeldPortLease): AppFacingTestLease {
  if (!isAppFacingTestPort(held.record.port)) {
    held.release();
    throw new TypeError(
      `app-facing test lease port ${held.record.port} is outside ${APP_FACING_TEST_PORT_MIN}-${APP_FACING_TEST_PORT_MAX}`,
    );
  }
  const lease: AppFacingTestLease = Object.freeze({
    schema: APP_FACING_TEST_LEASE_SCHEMA,
    port: held.record.port,
    lockPath: held.lockPath,
    runId: held.record.runId,
    holderPid: held.record.pid,
    holderStartIdentity: held.record.startIdentity,
    release: () => {
      liveLeases.delete(lease);
      held.release();
    },
  });
  return register(lease);
}

export function writeAppFacingTestLeaseFile(path: string, lease: AppFacingTestLease): void {
  if (!isLiveLease(lease)) {
    throw new TypeError("app-facing test lease is not live");
  }
  const file: AppFacingTestLeaseFile = {
    schema: APP_FACING_TEST_LEASE_SCHEMA,
    port: lease.port,
    lockPath: lease.lockPath,
    runId: lease.runId,
    pid: lease.holderPid,
    startIdentity: lease.holderStartIdentity,
  };
  writeFileSync(path, `${JSON.stringify(file)}\n`, { encoding: "utf8", mode: 0o600 });
}

/**
 * Load a lease file written by a holder process. The holder must still be
 * live; this does not take ownership of the lock.
 */
export function loadAppFacingTestLease(path: string): AppFacingTestLease {
  let parsed: unknown;
  try {
    parsed = JSON.parse(readFileSync(path, "utf8"));
  } catch {
    throw new TypeError(`app-facing test lease file is unreadable: ${path}`);
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new TypeError("app-facing test lease file is not an object");
  }
  const value = parsed as Record<string, unknown>;
  if (value.schema !== APP_FACING_TEST_LEASE_SCHEMA) {
    throw new TypeError("app-facing test lease file has the wrong schema");
  }
  if (!Number.isInteger(value.port) || !isAppFacingTestPort(value.port as number)) {
    throw new TypeError(
      `app-facing test lease port is outside ${APP_FACING_TEST_PORT_MIN}-${APP_FACING_TEST_PORT_MAX}`,
    );
  }
  if (typeof value.lockPath !== "string" || value.lockPath.length === 0) {
    throw new TypeError("app-facing test lease file is missing lockPath");
  }
  if (typeof value.runId !== "string" || value.runId.length === 0) {
    throw new TypeError("app-facing test lease file is missing runId");
  }
  let lock: unknown;
  try {
    lock = JSON.parse(readFileSync(value.lockPath, "utf8"));
  } catch {
    throw new TypeError("app-facing test lease lock is missing; the holder is gone");
  }
  const record = parsePortLeaseRecord(lock);
  if (record === null || record.role !== "app-facing" || record.port !== value.port) {
    throw new TypeError("app-facing test lease lock does not match the lease file");
  }
  if (!holderIsLive(record)) {
    const now = processStartIdentity(record.pid);
    throw new TypeError(
      `app-facing test lease holder is not live (pid ${record.pid}, recorded ${JSON.stringify(record.startIdentity)}, now ${JSON.stringify(now)})`,
    );
  }
  const lease: AppFacingTestLease = Object.freeze({
    schema: APP_FACING_TEST_LEASE_SCHEMA,
    port: record.port,
    lockPath: value.lockPath,
    runId: record.runId,
    holderPid: record.pid,
    holderStartIdentity: record.startIdentity,
    release: () => {
      liveLeases.delete(lease);
    },
  });
  return register(lease);
}

/**
 * Named seam. Production `loopbackServeOptions` will not accept this port.
 * Forging a lookalike object without going through acquire/load fails closed.
 */
export function loopbackServeOptionsForTestLease(lease: AppFacingTestLease): LoopbackServeOptions {
  if (!isLiveLease(lease)) {
    throw new TypeError("app-facing test lease is not live; enter test allocation through acquireAppFacingTestLease or loadAppFacingTestLease");
  }
  if (!isAppFacingTestPort(lease.port)) {
    throw new TypeError(
      `port ${lease.port} is outside the app-facing test allocation (${APP_FACING_TEST_PORT_MIN}-${APP_FACING_TEST_PORT_MAX})`,
    );
  }
  return {
    hostname: LOOPBACK_HOST,
    port: lease.port,
  };
}
