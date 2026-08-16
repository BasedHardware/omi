import { spawnSync } from "node:child_process";
import {
  closeSync,
  existsSync,
  mkdirSync,
  openSync,
  readFileSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

/**
 * Run-scoped exclusive port leases. A lease is a lock file plus a live-holder
 * check; it never kills a listener it does not own.
 *
 * When a run dies without calling release():
 *   the lock file remains, but the recorded pid is dead. The next acquire
 *   treats that lock as stale, removes it, and takes the port if no stranger
 *   is listening. A live listener on a stale lock is skipped, never evicted.
 */

export const PORT_LEASE_SCHEMA = "omi.port-lease.v1";
export const DEFAULT_PORT_LEASE_ROOT = join(tmpdir(), "omi-port-leases");

export const PRODUCTION_APP_FACING_PORT = 4851;
export const APP_FACING_TEST_PORT_MIN = 14_851;
export const APP_FACING_TEST_PORT_MAX = 14_870;

export const PRODUCTION_GATEWAY_TEST_PORT = 8788;
export const GATEWAY_TEST_PORT_MIN = 18_788;
export const GATEWAY_TEST_PORT_MAX = 18_807;

export const PRODUCTION_GATEWAY_REAL_PORT = 8791;
export const GATEWAY_REAL_PORT_MIN = 18_811;
export const GATEWAY_REAL_PORT_MAX = 18_830;

export const PRODUCTION_SURFACE_PORT = 5290;
export const SURFACE_TEST_PORT_MIN = 15_290;
export const SURFACE_TEST_PORT_MAX = 15_309;

/**
 * 5290 is the long-lived app origin: IndexedDB persists across relaunch.
 * 15290-15309 is a verification origin: a clean store is the point. These
 * are different product stores. Do not fold one range into the other.
 */
export function isSurfaceTestPort(port: number): boolean {
  return Number.isInteger(port)
    && port >= SURFACE_TEST_PORT_MIN
    && port <= SURFACE_TEST_PORT_MAX;
}

export type PortLeaseRole = "app-facing" | "gateway-test" | "gateway-real" | "surface";

export type PortRange = {
  readonly min: number;
  readonly max: number;
};

export const PORT_LEASE_RANGES: Readonly<Record<PortLeaseRole, PortRange>> = Object.freeze({
  "app-facing": Object.freeze({ min: APP_FACING_TEST_PORT_MIN, max: APP_FACING_TEST_PORT_MAX }),
  "gateway-test": Object.freeze({ min: GATEWAY_TEST_PORT_MIN, max: GATEWAY_TEST_PORT_MAX }),
  "gateway-real": Object.freeze({ min: GATEWAY_REAL_PORT_MIN, max: GATEWAY_REAL_PORT_MAX }),
  surface: Object.freeze({ min: SURFACE_TEST_PORT_MIN, max: SURFACE_TEST_PORT_MAX }),
});

export type PortLeaseRecord = {
  readonly schema: typeof PORT_LEASE_SCHEMA;
  readonly role: PortLeaseRole;
  readonly port: number;
  readonly pid: number;
  readonly startIdentity: string;
  readonly runId: string;
};

export type HeldPortLease = {
  readonly record: PortLeaseRecord;
  readonly lockPath: string;
  readonly release: () => void;
};

export type AcquirePortLeaseOptions = {
  readonly role: PortLeaseRole;
  readonly runId: string;
  readonly leaseRoot?: string;
  readonly range?: PortRange;
};

const isObject = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);

export function portLeaseLockPath(role: PortLeaseRole, port: number, leaseRoot = DEFAULT_PORT_LEASE_ROOT): string {
  return join(leaseRoot, `${role}-${port}.lock`);
}

export function processStartIdentity(pid: number): string | null {
  if (!Number.isSafeInteger(pid) || pid <= 0) return null;
  try {
    process.kill(pid, 0);
  } catch {
    return null;
  }
  const result = spawnSync("ps", ["-p", String(pid), "-o", "lstart="], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, TZ: "UTC" },
  });
  if (result.status !== 0) return null;
  const identity = (result.stdout ?? "").trim();
  return identity.length > 0 ? identity : null;
}

export function listenerPids(port: number): readonly number[] {
  const result = spawnSync("lsof", ["-t", `-iTCP:${port}`, "-sTCP:LISTEN"], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (result.status !== 0) return [];
  return (result.stdout ?? "")
    .trim()
    .split(/\s+/u)
    .filter(Boolean)
    .map(Number)
    .filter((pid) => Number.isSafeInteger(pid) && pid > 0);
}

export function parsePortLeaseRecord(value: unknown): PortLeaseRecord | null {
  if (!isObject(value)) return null;
  if (value.schema !== PORT_LEASE_SCHEMA) return null;
  if (value.role !== "app-facing" && value.role !== "gateway-test"
    && value.role !== "gateway-real" && value.role !== "surface") {
    return null;
  }
  if (!Number.isSafeInteger(value.port) || value.port < 1 || value.port > 65_535) return null;
  if (!Number.isSafeInteger(value.pid) || value.pid <= 0) return null;
  if (typeof value.startIdentity !== "string" || value.startIdentity.trim() === "") return null;
  if (typeof value.runId !== "string" || value.runId.length === 0) return null;
  return Object.freeze({
    schema: PORT_LEASE_SCHEMA,
    role: value.role,
    port: value.port,
    pid: value.pid,
    startIdentity: value.startIdentity.trim(),
    runId: value.runId,
  });
}

export function holderIsLive(record: PortLeaseRecord): boolean {
  return processStartIdentity(record.pid) === record.startIdentity;
}

function readLockRecord(lockPath: string): PortLeaseRecord | null {
  try {
    return parsePortLeaseRecord(JSON.parse(readFileSync(lockPath, "utf8")));
  } catch {
    return null;
  }
}

function removeStaleLock(lockPath: string): void {
  const record = readLockRecord(lockPath);
  if (record !== null && holderIsLive(record)) return;
  try {
    unlinkSync(lockPath);
  } catch {
    // raced with another acquirer
  }
}

function tryCreateLock(
  lockPath: string,
  record: PortLeaseRecord,
): boolean {
  let fd: number;
  try {
    fd = openSync(lockPath, "wx");
  } catch (error) {
    if (error && typeof error === "object" && "code" in error && error.code === "EEXIST") {
      return false;
    }
    throw error;
  }
  try {
    writeFileSync(fd, `${JSON.stringify(record)}\n`);
    return true;
  } catch (error) {
    try {
      unlinkSync(lockPath);
    } catch {
      // best-effort
    }
    throw error;
  } finally {
    closeSync(fd);
  }
}

function releaseIfOwned(lockPath: string, expected: PortLeaseRecord): void {
  const current = readLockRecord(lockPath);
  if (current === null) return;
  if (current.pid !== expected.pid || current.startIdentity !== expected.startIdentity) return;
  if (current.port !== expected.port || current.role !== expected.role) return;
  try {
    unlinkSync(lockPath);
  } catch {
    // already gone
  }
}

export function acquirePortLease(options: AcquirePortLeaseOptions): HeldPortLease {
  const range = options.range ?? PORT_LEASE_RANGES[options.role];
  if (range.min > range.max || range.min < 1 || range.max > 65_535) {
    throw new Error(`port lease range for ${options.role} is invalid`);
  }
  const leaseRoot = options.leaseRoot ?? DEFAULT_PORT_LEASE_ROOT;
  mkdirSync(leaseRoot, { recursive: true, mode: 0o700 });

  const startIdentity = processStartIdentity(process.pid);
  if (startIdentity === null) {
    throw new Error("could not read this process start identity; refusing to lease a port");
  }

  const occupied: number[] = [];
  const held: number[] = [];

  for (let port = range.min; port <= range.max; port += 1) {
    const listeners = listenerPids(port);
    if (listeners.length > 0) {
      occupied.push(port);
      continue;
    }

    const lockPath = portLeaseLockPath(options.role, port, leaseRoot);
    if (existsSync(lockPath)) {
      const existing = readLockRecord(lockPath);
      if (existing !== null && holderIsLive(existing)) {
        held.push(port);
        continue;
      }
      removeStaleLock(lockPath);
    }

    const record: PortLeaseRecord = Object.freeze({
      schema: PORT_LEASE_SCHEMA,
      role: options.role,
      port,
      pid: process.pid,
      startIdentity,
      runId: options.runId,
    });

    if (!tryCreateLock(lockPath, record)) {
      const raced = readLockRecord(lockPath);
      if (raced !== null && holderIsLive(raced)) {
        held.push(port);
        continue;
      }
      continue;
    }

    const listenersAfter = listenerPids(port);
    if (listenersAfter.length > 0) {
      releaseIfOwned(lockPath, record);
      occupied.push(port);
      continue;
    }

    let released = false;
    return Object.freeze({
      record,
      lockPath,
      release: () => {
        if (released) return;
        released = true;
        releaseIfOwned(lockPath, record);
      },
    });
  }

  const occupiedText = occupied.length > 0 ? ` listeners on ${occupied.join(", ")}` : "";
  const heldText = held.length > 0 ? ` live leases on ${held.join(", ")}` : "";
  throw new Error(
    `could not acquire a run-scoped ${options.role} port (${range.min}-${range.max});`
    + ` all candidates are leased or have listeners this harness does not own.`
    + `${occupiedText}${heldText}`
    + " This is a refusal, not a fallback.",
  );
}
