import { spawn, spawnSync } from "node:child_process";
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, test } from "bun:test";

import { processStartIdentity } from "./port-lease";
import {
  SIMULATOR_LEASE_MAX_CONCURRENT,
  SIMULATOR_LEASE_SCHEMA,
  acquireSimulatorLease,
  parseSimctlDeviceList,
  simulatorLeaseLockPath,
  simulatorLeaseRefusalMessage,
  type SimulatorDevice,
  type SimulatorHost,
} from "./simulator-lease";

const scratchDirs: string[] = [];
const occupyChildren: Array<ReturnType<typeof spawn>> = [];

afterEach(() => {
  for (const child of occupyChildren.splice(0)) {
    try {
      child.kill("SIGKILL");
    } catch {
      // gone
    }
  }
  for (const dir of scratchDirs.splice(0)) {
    rmSync(dir, { recursive: true, force: true });
  }
});

function scratch(): string {
  const dir = mkdtempSync(join(tmpdir(), "omi-simulator-lease-"));
  scratchDirs.push(dir);
  return dir;
}

const UDID_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1";
const UDID_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2";
const UDID_C = "cccccccc-cccc-4ccc-8ccc-ccccccccccc3";
const UDID_D = "dddddddd-dddd-4ddd-8ddd-ddddddddddd4";
const UDID_CREATED = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee5";

function device(partial: Partial<SimulatorDevice> & Pick<SimulatorDevice, "udid" | "name">): SimulatorDevice {
  return {
    state: "Shutdown",
    isAvailable: true,
    runtime: "com.apple.CoreSimulator.SimRuntime.iOS-26-5",
    ...partial,
  };
}

function trackingHost(initial: SimulatorDevice[]): SimulatorHost & {
  boots: string[];
  shutdowns: string[];
  creates: string[];
  erases: string[];
} {
  const inventory = initial.map((row) => ({ ...row }));
  const boots: string[] = [];
  const shutdowns: string[] = [];
  const creates: string[] = [];
  const erases: string[] = [];
  return {
    boots,
    shutdowns,
    creates,
    erases,
    listDevices: () => inventory.map((row) => ({ ...row })),
    bootDevice: (udid) => {
      boots.push(udid);
      const row = inventory.find((item) => item.udid === udid);
      if (row) row.state = "Booted";
    },
    shutdownDevice: (udid) => {
      shutdowns.push(udid);
      const row = inventory.find((item) => item.udid === udid);
      if (row) row.state = "Shutdown";
    },
    createDevice: (name) => {
      creates.push(name);
      const created = device({ udid: UDID_CREATED, name, state: "Shutdown" });
      inventory.push(created);
      return { udid: created.udid, name: created.name };
    },
  };
}

describe("parseSimctlDeviceList", () => {
  test("keeps iPhone rows and ignores malformed entries", () => {
    const devices = parseSimctlDeviceList({
      devices: {
        "com.apple.CoreSimulator.SimRuntime.iOS-26-5": [
          { udid: UDID_A, name: "iPhone 17 Pro", state: "Booted", isAvailable: true },
          { udid: UDID_B, name: "iPhone 17", state: "Shutdown" },
          { name: "missing-udid" },
        ],
        "com.apple.CoreSimulator.SimRuntime.watchOS-26-5": [
          { udid: UDID_C, name: "Apple Watch Series 11 (46mm)", state: "Shutdown", isAvailable: true },
        ],
      },
    });
    expect(devices).toEqual([
      {
        udid: UDID_A,
        name: "iPhone 17 Pro",
        state: "Booted",
        isAvailable: true,
        runtime: "com.apple.CoreSimulator.SimRuntime.iOS-26-5",
      },
      {
        udid: UDID_B,
        name: "iPhone 17",
        state: "Shutdown",
        isAvailable: true,
        runtime: "com.apple.CoreSimulator.SimRuntime.iOS-26-5",
      },
      {
        udid: UDID_C,
        name: "Apple Watch Series 11 (46mm)",
        state: "Shutdown",
        isAvailable: true,
        runtime: "com.apple.CoreSimulator.SimRuntime.watchOS-26-5",
      },
    ]);
  });
});

describe("simulator lease is run-scoped and never evicts", () => {
  test.serial("two acquires get different devices and boot the ones they take", () => {
    const leaseRoot = scratch();
    const host = trackingHost([
      device({ udid: UDID_A, name: "iPhone 17" }),
      device({ udid: UDID_B, name: "iPhone 17 Pro" }),
    ]);
    const first = acquireSimulatorLease({ runId: "run-a", leaseRoot, host });
    const second = acquireSimulatorLease({ runId: "run-b", leaseRoot, host });
    try {
      expect(first.record.udid).not.toBe(second.record.udid);
      expect(new Set([first.record.udid, second.record.udid])).toEqual(new Set([UDID_A, UDID_B]));
      expect(host.boots.sort()).toEqual([UDID_A, UDID_B].sort());
      expect(host.erases).toEqual([]);
    } finally {
      first.release();
      second.release();
    }
  });

  test.serial("a booted device with no lease is skipped as someone else's, never shut down", () => {
    const leaseRoot = scratch();
    const host = trackingHost([
      device({ udid: UDID_A, name: "iPhone 17 Pro", state: "Booted" }),
      device({ udid: UDID_B, name: "iPhone 17" }),
    ]);
    const lease = acquireSimulatorLease({ runId: "run-skip-david", leaseRoot, host });
    try {
      expect(lease.record.udid).toBe(UDID_B);
      expect(host.boots).toEqual([UDID_B]);
      expect(host.shutdowns).toEqual([]);
      expect(host.erases).toEqual([]);
    } finally {
      lease.release();
    }
    expect(host.shutdowns).toEqual([UDID_B]);
    expect(host.shutdowns).not.toContain(UDID_A);
  });

  test.serial("a live holder is skipped and never evicted", async () => {
    const leaseRoot = scratch();
    const lockPath = simulatorLeaseLockPath(UDID_A, leaseRoot);
    const holderSource = `
      import { acquireSimulatorLease } from ${JSON.stringify(join(import.meta.dir, "simulator-lease.ts"))};
      const host = {
        listDevices: () => [${JSON.stringify(device({ udid: UDID_A, name: "iPhone 17" }))}].map((row) => ({ ...row })),
        bootDevice: () => {},
        shutdownDevice: () => {},
        createDevice: () => { throw new Error("create must not run"); },
      };
      acquireSimulatorLease({
        runId: "run-live-holder",
        leaseRoot: ${JSON.stringify(leaseRoot)},
        host,
        maxConcurrent: 2,
      });
      process.stdout.write("held\\n");
      await new Promise(() => {});
    `;
    const child = spawn(process.execPath, ["-e", holderSource], { stdio: ["ignore", "pipe", "pipe"] });
    occupyChildren.push(child);
    const deadline = Date.now() + 5_000;
    let output = "";
    while (Date.now() < deadline) {
      output += child.stdout?.read()?.toString() ?? "";
      if (output.includes("held") && existsSync(lockPath)) break;
      await Bun.sleep(25);
    }
    expect(output).toContain("held");
    expect(existsSync(lockPath)).toBe(true);

    const host = trackingHost([
      device({ udid: UDID_A, name: "iPhone 17" }),
      device({ udid: UDID_B, name: "iPhone 17 Pro" }),
    ]);
    const lease = acquireSimulatorLease({ runId: "run-skip-live", leaseRoot, host, maxConcurrent: 2 });
    try {
      expect(lease.record.udid).toBe(UDID_B);
      expect(host.boots).toEqual([UDID_B]);
      expect(host.shutdowns).not.toContain(UDID_A);
      expect(host.erases).toEqual([]);
    } finally {
      lease.release();
    }
  });

  test.serial("kill a holder mid-flight and the next acquire takes the stale lock", async () => {
    const leaseRoot = scratch();
    const lockPath = simulatorLeaseLockPath(UDID_A, leaseRoot);
    const holderSource = `
      import { acquireSimulatorLease } from ${JSON.stringify(join(import.meta.dir, "simulator-lease.ts"))};
      const host = {
        listDevices: () => [${JSON.stringify(device({ udid: UDID_A, name: "iPhone 17" }))}].map((row) => ({ ...row })),
        bootDevice: () => {},
        shutdownDevice: () => {},
        createDevice: () => { throw new Error("create must not run"); },
      };
      acquireSimulatorLease({
        runId: "run-killed-holder",
        leaseRoot: ${JSON.stringify(leaseRoot)},
        host,
      });
      process.stdout.write("held\\n");
      await new Promise(() => {});
    `;
    const child = spawn(process.execPath, ["-e", holderSource], { stdio: ["ignore", "pipe", "pipe"] });
    occupyChildren.push(child);
    const deadline = Date.now() + 5_000;
    let output = "";
    while (Date.now() < deadline) {
      output += child.stdout?.read()?.toString() ?? "";
      if (output.includes("held") && existsSync(lockPath)) break;
      await Bun.sleep(25);
    }
    expect(output).toContain("held");
    child.kill("SIGKILL");
    await new Promise<void>((resolve) => {
      child.once("exit", () => resolve());
    });

    const host = trackingHost([device({ udid: UDID_A, name: "iPhone 17", state: "Booted" })]);
    const next = acquireSimulatorLease({ runId: "run-after-kill", leaseRoot, host });
    try {
      expect(next.record.udid).toBe(UDID_A);
      expect(next.record.runId).toBe("run-after-kill");
      expect(next.bootedByHolder).toBe(true);
      expect(host.boots).toEqual([]);
      expect(host.shutdowns).toEqual([]);
    } finally {
      next.release();
    }
    expect(host.shutdowns).toEqual([UDID_A]);
    expect(existsSync(lockPath)).toBe(false);
  });

  test.serial("RED-PROOF exhausting the cap names the live holders, and does not boot or create", () => {
    const leaseRoot = scratch();
    const startIdentity = processStartIdentity(process.pid);
    expect(startIdentity).not.toBeNull();
    const devices = [
      device({ udid: UDID_A, name: "iPhone 17 Pro", state: "Booted" }),
      device({ udid: UDID_B, name: "iPhone 17" }),
      device({ udid: UDID_C, name: "iPhone Air" }),
      device({ udid: UDID_D, name: "iPhone 17e" }),
    ];
    writeFileSync(simulatorLeaseLockPath(UDID_B, leaseRoot), `${JSON.stringify({
      schema: SIMULATOR_LEASE_SCHEMA,
      udid: UDID_B,
      name: "iPhone 17",
      pid: process.pid,
      startIdentity,
      runId: "run-held-b",
      bootedByHolder: true,
    })}\n`);
    writeFileSync(simulatorLeaseLockPath(UDID_C, leaseRoot), `${JSON.stringify({
      schema: SIMULATOR_LEASE_SCHEMA,
      udid: UDID_C,
      name: "iPhone Air",
      pid: process.pid,
      startIdentity,
      runId: "run-held-c",
      bootedByHolder: true,
    })}\n`);
    const host = trackingHost(devices);
    let thrown: unknown;
    try {
      acquireSimulatorLease({ runId: "run-exhausted", leaseRoot, host, maxConcurrent: 2 });
    } catch (error) {
      thrown = error;
    }
    expect(thrown).toBeInstanceOf(Error);
    const message = (thrown as Error).message;
    const expected = simulatorLeaseRefusalMessage({
      maxConcurrent: 2,
      live: [
        {
          schema: SIMULATOR_LEASE_SCHEMA,
          udid: UDID_B,
          name: "iPhone 17",
          pid: process.pid,
          startIdentity: startIdentity!,
          runId: "run-held-b",
          bootedByHolder: true,
        },
        {
          schema: SIMULATOR_LEASE_SCHEMA,
          udid: UDID_C,
          name: "iPhone Air",
          pid: process.pid,
          startIdentity: startIdentity!,
          runId: "run-held-c",
          bootedByHolder: true,
        },
      ],
      strangers: [devices[0]!],
    });
    expect(message).toBe(expected);
    expect(message).toContain(`pid=${process.pid}`);
    expect(message).toContain("runId=run-held-b");
    expect(message).toContain("runId=run-held-c");
    expect(message).toContain("booted without a lease (treated as someone else's): iPhone 17 Pro");
    expect(message).toContain("This is a refusal, not a fallback.");
    expect(host.boots).toEqual([]);
    expect(host.creates).toEqual([]);
    expect(host.shutdowns).toEqual([]);
    expect(host.erases).toEqual([]);
  });

  test.serial("boots a created device when every existing iPhone is leased or someone else's", () => {
    const leaseRoot = scratch();
    const startIdentity = processStartIdentity(process.pid);
    writeFileSync(simulatorLeaseLockPath(UDID_B, leaseRoot), `${JSON.stringify({
      schema: SIMULATOR_LEASE_SCHEMA,
      udid: UDID_B,
      name: "iPhone 17",
      pid: process.pid,
      startIdentity,
      runId: "run-held-only",
      bootedByHolder: true,
    })}\n`);
    const host = trackingHost([
      device({ udid: UDID_A, name: "iPhone 17 Pro", state: "Booted" }),
      device({ udid: UDID_B, name: "iPhone 17" }),
    ]);
    const lease = acquireSimulatorLease({ runId: "run-create", leaseRoot, host, maxConcurrent: 2 });
    try {
      expect(lease.record.udid).toBe(UDID_CREATED);
      expect(lease.bootedByHolder).toBe(true);
      expect(host.creates).toHaveLength(1);
      expect(host.boots).toEqual([UDID_CREATED]);
      expect(host.shutdowns).not.toContain(UDID_A);
    } finally {
      lease.release();
    }
  });

  test.serial("RED-PROOF the holder CLI names live holders instead of timing out", () => {
    const leaseRoot = scratch();
    const outPath = join(scratch(), "simulator-lease.json");
    const startIdentity = processStartIdentity(process.pid);
    expect(startIdentity).not.toBeNull();
    const held = [
      { udid: UDID_A, name: "iPhone 17 Pro", runId: "run-held-a" },
      { udid: UDID_B, name: "iPhone 17", runId: "run-held-b" },
      { udid: UDID_C, name: "iPhone Air", runId: "run-held-c" },
      { udid: UDID_D, name: "iPhone 17e", runId: "run-held-d" },
    ];
    for (const row of held) {
      writeFileSync(simulatorLeaseLockPath(row.udid, leaseRoot), `${JSON.stringify({
        schema: SIMULATOR_LEASE_SCHEMA,
        udid: row.udid,
        name: row.name,
        pid: process.pid,
        startIdentity,
        runId: row.runId,
        bootedByHolder: true,
      })}\n`);
    }
    const bin = join(scratch(), "bin");
    mkdirSync(bin);
    const xcrun = join(bin, "xcrun");
    writeFileSync(xcrun, `#!/bin/bash
echo '{"devices":{}}'
exit 0
`);
    chmodSync(xcrun, 0o755);
    const result = spawnSync(process.execPath, [
      join(import.meta.dir, "../../../integration/lib/stack-simulator-lease.ts"),
      "hold",
      "--run-id",
      "run-refuse",
      "--out",
      outPath,
      "--lease-root",
      leaseRoot,
    ], {
      encoding: "utf8",
      timeout: 20_000,
      env: { ...process.env, PATH: `${bin}:${process.env.PATH ?? ""}` },
    });
    expect(result.status).toBe(1);
    const stderr = result.stderr ?? "";
    expect(stderr).toContain("ERROR: could not acquire a run-scoped iOS simulator (max 4 concurrent)");
    expect(stderr).toContain(`pid=${process.pid}`);
    expect(stderr).toContain("runId=run-held-a");
    expect(stderr).toContain("runId=run-held-b");
    expect(stderr).toContain("runId=run-held-c");
    expect(stderr).toContain("runId=run-held-d");
    expect(stderr).toContain("This is a refusal, not a fallback.");
    expect(stderr).not.toContain("124");
    expect(existsSync(outPath)).toBe(false);
  });

  test.serial("a failed shutdown leaves the lock so the next acquire reclaims instead of treating it as a stranger", () => {
    const leaseRoot = scratch();
    const inventory = [device({ udid: UDID_A, name: "iPhone 17" })];
    const shutdowns: string[] = [];
    const boots: string[] = [];
    const host: SimulatorHost = {
      listDevices: () => inventory.map((row) => ({ ...row })),
      bootDevice: (udid) => {
        boots.push(udid);
        const row = inventory.find((item) => item.udid === udid);
        if (row) row.state = "Booted";
      },
      shutdownDevice: (udid) => {
        shutdowns.push(udid);
        throw new Error("simctl shutdown lagged");
      },
      createDevice: () => {
        throw new Error("create must not run");
      },
    };
    const lease = acquireSimulatorLease({ runId: "run-shutdown-fail", leaseRoot, host });
    expect(lease.bootedByHolder).toBe(true);
    expect(boots).toEqual([UDID_A]);
    lease.release();
    expect(shutdowns).toEqual([UDID_A]);
    expect(existsSync(simulatorLeaseLockPath(UDID_A, leaseRoot))).toBe(true);
    const left = JSON.parse(readFileSync(simulatorLeaseLockPath(UDID_A, leaseRoot), "utf8"));
    expect(left.runId).toBe("run-shutdown-fail");
    expect(left.bootedByHolder).toBe(true);

    const skipHost = trackingHost([
      device({ udid: UDID_A, name: "iPhone 17", state: "Booted" }),
      device({ udid: UDID_B, name: "iPhone 17 Pro" }),
    ]);
    const other = acquireSimulatorLease({ runId: "run-skip-live-after-failed-shutdown", leaseRoot, host: skipHost });
    try {
      expect(other.record.udid).toBe(UDID_B);
      expect(skipHost.shutdowns).not.toContain(UDID_A);
    } finally {
      other.release();
    }
  });

  test.serial("release of a device we booted shuts it down and does not erase", () => {
    const leaseRoot = scratch();
    const host = trackingHost([device({ udid: UDID_A, name: "iPhone 17" })]);
    const lease = acquireSimulatorLease({ runId: "run-release-shutdown", leaseRoot, host });
    expect(lease.bootedByHolder).toBe(true);
    lease.release();
    expect(host.shutdowns).toEqual([UDID_A]);
    expect(host.erases).toEqual([]);
    expect(existsSync(simulatorLeaseLockPath(UDID_A, leaseRoot))).toBe(false);
  });

  test.serial("watchOS and unavailable rows are not leased", () => {
    const leaseRoot = scratch();
    const host = trackingHost([
      device({
        udid: UDID_A,
        name: "Apple Watch Series 11 (46mm)",
        runtime: "com.apple.CoreSimulator.SimRuntime.watchOS-26-5",
      }),
      device({ udid: UDID_B, name: "iPhone 17", isAvailable: false }),
      device({ udid: UDID_C, name: "iPhone Air" }),
    ]);
    const lease = acquireSimulatorLease({ runId: "run-iphone-only", leaseRoot, host });
    try {
      expect(lease.record.udid).toBe(UDID_C);
    } finally {
      lease.release();
    }
  });
});
