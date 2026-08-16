import { spawnSync } from "node:child_process";
import {
  closeSync,
  existsSync,
  mkdirSync,
  openSync,
  readdirSync,
  readFileSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { processStartIdentity } from "./port-lease";

/**
 * Run-scoped exclusive iOS simulator leases. Same mechanism as the port
 * lease: a lock file plus a live-holder check. It never shuts down, erases,
 * or steals a device it did not boot.
 *
 * When a run dies without calling release():
 *   the lock file remains, but the recorded pid is dead. The next acquire
 *   treats that lock as stale, removes it, and takes the device if it is not
 *   a stranger's already-booted simulator. A live holder is skipped, never
 *   evicted.
 *
 * Boot state is not ownership. A booted device with no live lease is treated
 * as someone else's (David's headed simulator, another tool). Shutdown
 * devices with no live lease can be leased and booted. The cap is
 * SIMULATOR_LEASE_MAX_CONCURRENT — an unbounded boot loop on a laptop is
 * its own outage.
 */

export const SIMULATOR_LEASE_SCHEMA = "omi.simulator-lease.v1";
export const DEFAULT_SIMULATOR_LEASE_ROOT = join(tmpdir(), "omi-simulator-leases");

/** Maximum live simulator leases on this machine. The cap. */
export const SIMULATOR_LEASE_MAX_CONCURRENT = 4;

export const SIMULATOR_LEASE_CREATED_NAME_PREFIX = "omi-verification-";

export type SimulatorDeviceState = "Booted" | "Shutdown" | "Booting" | "Shutting Down" | "Creating" | string;

export type SimulatorDevice = {
  readonly udid: string;
  readonly name: string;
  readonly state: SimulatorDeviceState;
  readonly isAvailable: boolean;
  readonly runtime: string;
};

export type SimulatorHost = {
  readonly listDevices: () => readonly SimulatorDevice[];
  readonly bootDevice: (udid: string) => void;
  readonly shutdownDevice: (udid: string) => void;
  readonly createDevice: (name: string) => { readonly udid: string; readonly name: string };
};

export type SimulatorLeaseRecord = {
  readonly schema: typeof SIMULATOR_LEASE_SCHEMA;
  readonly udid: string;
  readonly name: string;
  readonly pid: number;
  readonly startIdentity: string;
  readonly runId: string;
  /** True if this lease chain booted the device and must shut it down on release. */
  readonly bootedByHolder: boolean;
};

export type HeldSimulatorLease = {
  readonly record: SimulatorLeaseRecord;
  readonly lockPath: string;
  readonly bootedByHolder: boolean;
  readonly release: () => void;
};

export type AcquireSimulatorLeaseOptions = {
  readonly runId: string;
  readonly leaseRoot?: string;
  readonly host?: SimulatorHost;
  readonly maxConcurrent?: number;
};

const isObject = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);

export function simulatorLeaseLockPath(udid: string, leaseRoot = DEFAULT_SIMULATOR_LEASE_ROOT): string {
  return join(leaseRoot, `${udid}.lock`);
}

export function parseSimulatorLeaseRecord(value: unknown): SimulatorLeaseRecord | null {
  if (!isObject(value)) return null;
  if (value.schema !== SIMULATOR_LEASE_SCHEMA) return null;
  if (typeof value.udid !== "string" || !isSimulatorUdid(value.udid)) return null;
  if (typeof value.name !== "string" || value.name.trim() === "") return null;
  if (!Number.isSafeInteger(value.pid) || value.pid <= 0) return null;
  if (typeof value.startIdentity !== "string" || value.startIdentity.trim() === "") return null;
  if (typeof value.runId !== "string" || value.runId.length === 0) return null;
  if (typeof value.bootedByHolder !== "boolean") return null;
  return Object.freeze({
    schema: SIMULATOR_LEASE_SCHEMA,
    udid: value.udid,
    name: value.name.trim(),
    pid: value.pid,
    startIdentity: value.startIdentity.trim(),
    runId: value.runId,
    bootedByHolder: value.bootedByHolder,
  });
}

export function isSimulatorUdid(value: string): boolean {
  return /^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$/.test(value);
}

export function holderIsLive(record: SimulatorLeaseRecord): boolean {
  return processStartIdentity(record.pid) === record.startIdentity;
}

export function isLeaseableIphone(device: SimulatorDevice): boolean {
  if (!device.isAvailable) return false;
  if (!isSimulatorUdid(device.udid)) return false;
  if (!/iOS/i.test(device.runtime)) return false;
  return /iphone/i.test(device.name);
}

/**
 * simctl `list devices -j` shape. Pure so tests do not need a live CoreSimulator.
 */
export function parseSimctlDeviceList(value: unknown): SimulatorDevice[] {
  if (!isObject(value) || !isObject(value.devices)) return [];
  const devices: SimulatorDevice[] = [];
  for (const [runtime, rows] of Object.entries(value.devices)) {
    if (!Array.isArray(rows)) continue;
    for (const row of rows) {
      if (!isObject(row)) continue;
      if (typeof row.udid !== "string" || typeof row.name !== "string") continue;
      const state = typeof row.state === "string" ? row.state : "Shutdown";
      const isAvailable = row.isAvailable !== false;
      devices.push(Object.freeze({
        udid: row.udid,
        name: row.name,
        state,
        isAvailable,
        runtime,
      }));
    }
  }
  return devices;
}

function readLockRecord(lockPath: string): SimulatorLeaseRecord | null {
  try {
    return parseSimulatorLeaseRecord(JSON.parse(readFileSync(lockPath, "utf8")));
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

function tryCreateLock(lockPath: string, record: SimulatorLeaseRecord): boolean {
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

function releaseIfOwned(lockPath: string, expected: SimulatorLeaseRecord): void {
  const current = readLockRecord(lockPath);
  if (current === null) return;
  if (current.pid !== expected.pid || current.startIdentity !== expected.startIdentity) return;
  if (current.udid !== expected.udid) return;
  try {
    unlinkSync(lockPath);
  } catch {
    // already gone
  }
}

function listLockRecords(leaseRoot: string): SimulatorLeaseRecord[] {
  if (!existsSync(leaseRoot)) return [];
  const records: SimulatorLeaseRecord[] = [];
  for (const entry of readdirSync(leaseRoot)) {
    if (!entry.endsWith(".lock")) continue;
    const record = readLockRecord(join(leaseRoot, entry));
    if (record !== null) records.push(record);
  }
  return records;
}

function formatHolder(record: SimulatorLeaseRecord): string {
  return `${record.name} (${record.udid}) pid=${record.pid} runId=${record.runId}`;
}

function formatDevice(device: SimulatorDevice): string {
  return `${device.name} (${device.udid})`;
}

export function simulatorLeaseRefusalMessage(input: {
  readonly maxConcurrent: number;
  readonly live: readonly SimulatorLeaseRecord[];
  readonly strangers: readonly SimulatorDevice[];
}): string {
  const liveText = input.live.length > 0
    ? ` live leases: ${input.live.map(formatHolder).join("; ")}`
    : "";
  const strangerText = input.strangers.length > 0
    ? ` booted without a lease (treated as someone else's): ${input.strangers.map(formatDevice).join("; ")}`
    : "";
  return (
    `could not acquire a run-scoped iOS simulator (max ${input.maxConcurrent} concurrent);`
    + " all candidates are leased or are devices this harness did not boot."
    + `${liveText}${strangerText}`
    + " This is a refusal, not a fallback."
  );
}

function refuse(options: {
  readonly maxConcurrent: number;
  readonly live: readonly SimulatorLeaseRecord[];
  readonly strangers: readonly SimulatorDevice[];
}): never {
  throw new Error(simulatorLeaseRefusalMessage(options));
}

function spawnXcrun(args: readonly string[], timeoutMs: number): string {
  const result = spawnSync("xcrun", args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    timeout: timeoutMs,
  });
  if (result.error) {
    throw new Error(`xcrun ${args.join(" ")} failed: ${result.error.message}`);
  }
  if (result.status !== 0) {
    const detail = `${result.stderr ?? ""}${result.stdout ?? ""}`.trim();
    throw new Error(`xcrun ${args.join(" ")} exited ${result.status}${detail ? `: ${detail}` : ""}`);
  }
  return (result.stdout ?? "").trim();
}

function pickCreateSpec(): { readonly deviceType: string; readonly runtime: string } {
  const typesJson = JSON.parse(spawnXcrun(["simctl", "list", "devicetypes", "-j"], 15_000));
  const runtimesJson = JSON.parse(spawnXcrun(["simctl", "list", "runtimes", "-j"], 15_000));
  const types = Array.isArray(typesJson?.devicetypes) ? typesJson.devicetypes : [];
  const runtimes = Array.isArray(runtimesJson?.runtimes) ? runtimesJson.runtimes : [];
  const iphone = [...types].reverse().find((row: { identifier?: string; name?: string }) =>
    typeof row?.identifier === "string" && /iPhone/i.test(row.identifier) && !/iPhone-SE|Watch/i.test(row.identifier));
  const runtime = [...runtimes].reverse().find((row: { identifier?: string; isAvailable?: boolean; name?: string }) =>
    typeof row?.identifier === "string"
    && /iOS/i.test(row.identifier)
    && row.isAvailable !== false);
  if (typeof iphone?.identifier !== "string" || typeof runtime?.identifier !== "string") {
    throw new Error("could not pick an iPhone device type and iOS runtime to create a verification simulator");
  }
  return { deviceType: iphone.identifier, runtime: runtime.identifier };
}

export function defaultSimulatorHost(): SimulatorHost {
  return {
    listDevices: () => {
      const raw = spawnXcrun(["simctl", "list", "devices", "-j"], 15_000);
      return parseSimctlDeviceList(JSON.parse(raw));
    },
    bootDevice: (udid) => {
      try {
        spawnXcrun(["simctl", "boot", udid], 30_000);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        if (!/current state: Booted/i.test(message)) throw error;
      }
      spawnXcrun(["simctl", "bootstatus", udid, "-b"], 90_000);
    },
    shutdownDevice: (udid) => {
      try {
        spawnXcrun(["simctl", "shutdown", udid], 30_000);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        if (!/current state: Shutdown/i.test(message)) throw error;
      }
    },
    createDevice: (name) => {
      const spec = pickCreateSpec();
      const udid = spawnXcrun(["simctl", "create", name, spec.deviceType, spec.runtime], 30_000);
      if (!isSimulatorUdid(udid)) {
        throw new Error(`simctl create did not return a UDID: ${udid}`);
      }
      return { udid, name };
    },
  };
}

function hold(
  lockPath: string,
  record: SimulatorLeaseRecord,
  bootedByHolder: boolean,
  host: SimulatorHost,
): HeldSimulatorLease {
  let released = false;
  return Object.freeze({
    record,
    lockPath,
    bootedByHolder,
    release: () => {
      if (released) return;
      released = true;
      if (bootedByHolder) {
        try {
          host.shutdownDevice(record.udid);
        } catch {
          // Shutdown failed: leave the lock so the next acquire sees a stale
          // holder and reclaims, instead of treating a still-booted device as
          // someone else's. Never erase.
          return;
        }
      }
      releaseIfOwned(lockPath, record);
    },
  });
}

function tryLeaseDevice(
  device: SimulatorDevice,
  options: {
    readonly runId: string;
    readonly leaseRoot: string;
    readonly startIdentity: string;
    readonly host: SimulatorHost;
    readonly needsBoot: boolean;
  },
): HeldSimulatorLease | null {
  const lockPath = simulatorLeaseLockPath(device.udid, options.leaseRoot);
  let inheritedBootedByHolder = false;
  if (existsSync(lockPath)) {
    const existing = readLockRecord(lockPath);
    if (existing !== null && holderIsLive(existing)) return null;
    inheritedBootedByHolder = existing?.bootedByHolder === true;
    removeStaleLock(lockPath);
  }

  const bootedByHolder = options.needsBoot || inheritedBootedByHolder;
  const record: SimulatorLeaseRecord = Object.freeze({
    schema: SIMULATOR_LEASE_SCHEMA,
    udid: device.udid,
    name: device.name,
    pid: process.pid,
    startIdentity: options.startIdentity,
    runId: options.runId,
    bootedByHolder,
  });

  if (!tryCreateLock(lockPath, record)) {
    const raced = readLockRecord(lockPath);
    if (raced !== null && holderIsLive(raced)) return null;
    return null;
  }

  if (options.needsBoot) {
    try {
      options.host.bootDevice(device.udid);
    } catch {
      try {
        options.host.shutdownDevice(device.udid);
      } catch {
        // we initiated boot; shutdown is ours to attempt. never erase.
      }
      releaseIfOwned(lockPath, record);
      return null;
    }
  }

  return hold(lockPath, record, bootedByHolder, options.host);
}

export function acquireSimulatorLease(options: AcquireSimulatorLeaseOptions): HeldSimulatorLease {
  const maxConcurrent = options.maxConcurrent ?? SIMULATOR_LEASE_MAX_CONCURRENT;
  if (!Number.isSafeInteger(maxConcurrent) || maxConcurrent < 1) {
    throw new Error("simulator lease maxConcurrent is invalid");
  }
  const leaseRoot = options.leaseRoot ?? DEFAULT_SIMULATOR_LEASE_ROOT;
  mkdirSync(leaseRoot, { recursive: true, mode: 0o700 });
  const host = options.host ?? defaultSimulatorHost();

  const startIdentity = processStartIdentity(process.pid);
  if (startIdentity === null) {
    throw new Error("could not read this process start identity; refusing to lease a simulator");
  }

  const devices = host.listDevices().filter(isLeaseableIphone);
  const live: SimulatorLeaseRecord[] = [];
  const liveUdids = new Set<string>();
  for (const record of listLockRecords(leaseRoot)) {
    if (!holderIsLive(record)) continue;
    live.push(record);
    liveUdids.add(record.udid);
  }

  const strangers: SimulatorDevice[] = [];
  const reclaimable: SimulatorDevice[] = [];
  const shutdownFree: SimulatorDevice[] = [];
  for (const device of devices) {
    if (liveUdids.has(device.udid)) continue;
    const existing = existsSync(simulatorLeaseLockPath(device.udid, leaseRoot))
      ? readLockRecord(simulatorLeaseLockPath(device.udid, leaseRoot))
      : null;
    if (existing !== null && holderIsLive(existing)) {
      live.push(existing);
      liveUdids.add(device.udid);
      continue;
    }
    if (existing !== null) {
      reclaimable.push(device);
      continue;
    }
    if (device.state === "Shutdown") {
      shutdownFree.push(device);
      continue;
    }
    strangers.push(device);
  }

  live.sort((a, b) => a.udid.localeCompare(b.udid));
  strangers.sort((a, b) => a.udid.localeCompare(b.udid));

  if (live.length >= maxConcurrent) {
    refuse({ maxConcurrent, live, strangers });
  }

  for (const device of reclaimable) {
    const held = tryLeaseDevice(device, {
      runId: options.runId,
      leaseRoot,
      startIdentity,
      host,
      needsBoot: device.state === "Shutdown",
    });
    if (held !== null) return held;
  }

  for (const device of shutdownFree) {
    const held = tryLeaseDevice(device, {
      runId: options.runId,
      leaseRoot,
      startIdentity,
      host,
      needsBoot: true,
    });
    if (held !== null) return held;
  }

  const createdCount = devices.filter((device) =>
    device.name.startsWith(SIMULATOR_LEASE_CREATED_NAME_PREFIX)).length;
  if (createdCount >= maxConcurrent || live.length + 1 > maxConcurrent) {
    refuse({ maxConcurrent, live, strangers });
  }

  const createdName = `${SIMULATOR_LEASE_CREATED_NAME_PREFIX}${process.pid}`;
  const created = host.createDevice(createdName);
  const createdDevice: SimulatorDevice = {
    udid: created.udid,
    name: created.name,
    state: "Shutdown",
    isAvailable: true,
    runtime: "iOS",
  };
  const held = tryLeaseDevice(createdDevice, {
    runId: options.runId,
    leaseRoot,
    startIdentity,
    host,
    needsBoot: true,
  });
  if (held !== null) return held;
  refuse({ maxConcurrent, live, strangers });
}
