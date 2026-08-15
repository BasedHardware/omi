import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, test } from "bun:test";

import {
  LOOPBACK_HOST,
  assertPortInRange,
  loopbackServeOptions,
  parseLsofListenOutput,
} from "./loopback";
import {
  acquirePortLease,
  listenerPids,
  portLeaseLockPath,
} from "./port-lease";
import {
  acquireAppFacingTestLease,
  loadAppFacingTestLease,
  loopbackServeOptionsForTestLease,
  writeAppFacingTestLeaseFile,
} from "./test-allocation";

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
  const dir = mkdtempSync(join(tmpdir(), "omi-port-lease-"));
  scratchDirs.push(dir);
  return dir;
}

async function occupy(port: number): Promise<number> {
  const child = spawn(process.execPath, ["-e", `require("net").createServer().listen(${port},"127.0.0.1")`], {
    stdio: "ignore",
  });
  occupyChildren.push(child);
  const deadline = Date.now() + 2_000;
  while (Date.now() < deadline) {
    if (child.pid !== undefined && listenerPids(port).includes(child.pid)) return child.pid;
    await Bun.sleep(20);
  }
  throw new Error(`test listener did not bind ${port}`);
}

describe("production assertPortInRange is unchanged", () => {
  test("allows port 4851", () => {
    expect(() => assertPortInRange(4851)).not.toThrow();
  });

  test("rejects every non-fixed app-facing port with TypeError", () => {
    expect(() => assertPortInRange(3000)).toThrow(TypeError);
    expect(() => assertPortInRange(5290)).toThrow(TypeError);
    expect(() => assertPortInRange(4850)).toThrow(TypeError);
    expect(() => assertPortInRange(4852)).toThrow(TypeError);
  });
});

describe("test allocation is a named seam, not a widened default", () => {
  test("RED-PROOF a service that has not entered test mode refuses a leased port", () => {
    const leaseRoot = scratch();
    const lease = acquireAppFacingTestLease({ runId: "run-refuse-without-enter", leaseRoot });
    try {
      expect(() => assertPortInRange(lease.port)).toThrow(TypeError);
      expect(() => loopbackServeOptions(lease.port)).toThrow(TypeError);
      expect(() => loopbackServeOptions(lease.port)).toThrow(/outside the app-facing service allocation \(allowed: 4851\)/);
    } finally {
      lease.release();
    }
  });

  test("RED-PROOF a forged lease object cannot enter test mode", () => {
    expect(() => loopbackServeOptionsForTestLease({
      schema: "omi.app-facing-test-port-lease.v1",
      port: 14_851,
      lockPath: "/tmp/forged.lock",
      runId: "forged",
      holderPid: 1,
      holderStartIdentity: "forged",
      release: () => undefined,
    })).toThrow(/not live/);
  });

  test("loopback-only binding holds in test mode", async () => {
    const lease = acquireAppFacingTestLease({ runId: "run-loopback-test-mode" });
    let server: { stop: (closeActive?: boolean) => void; port: number } | null = null;
    try {
      const options = loopbackServeOptionsForTestLease(lease);
      expect(options).toEqual({ hostname: LOOPBACK_HOST, port: lease.port });
      server = Bun.serve({
        ...options,
        fetch: () => new Response("ok"),
      });
      const lsof = spawnSync("lsof", ["-nP", `-iTCP:${lease.port}`, "-sTCP:LISTEN"], {
        encoding: "utf8",
      });
      const verdict = parseLsofListenOutput(lsof.stdout ?? "", lease.port);
      expect(verdict.pass).toBe(true);
      expect(verdict.listenerCount).toBeGreaterThanOrEqual(1);
      expect(lsof.stdout ?? "").toContain(`127.0.0.1:${lease.port}`);
      expect(lsof.stdout ?? "").not.toContain(`*:${lease.port}`);
    } finally {
      server?.stop(true);
      lease.release();
    }
  });
});

describe("port lease is run-scoped and self-releasing", () => {
  test.serial("two acquires in one range get different ports", () => {
    const leaseRoot = scratch();
    const range = { min: 24_900, max: 24_901 };
    const first = acquirePortLease({ role: "app-facing", runId: "run-a", leaseRoot, range });
    const second = acquirePortLease({ role: "app-facing", runId: "run-b", leaseRoot, range });
    try {
      expect(first.record.port).not.toBe(second.record.port);
    } finally {
      first.release();
      second.release();
    }
  });

  test.serial("a held listener is skipped and never killed", async () => {
    const leaseRoot = scratch();
    const range = { min: 24_910, max: 24_911 };
    const occupant = await occupy(24_910);
    const lease = acquirePortLease({
      role: "app-facing",
      runId: "run-skip-occupied",
      leaseRoot,
      range,
    });
    try {
      expect(lease.record.port).toBe(24_911);
      expect(() => process.kill(occupant, 0)).not.toThrow();
      expect(listenerPids(24_910)).toContain(occupant);
    } finally {
      lease.release();
    }
  });

  test.serial("exhausting the range is a loud refusal, not a fallback", async () => {
    const leaseRoot = scratch();
    const range = { min: 24_920, max: 24_920 };
    await occupy(24_920);
    expect(() => acquirePortLease({
      role: "app-facing",
      runId: "run-exhausted",
      leaseRoot,
      range,
    })).toThrow(/could not acquire a run-scoped app-facing port \(24920-24920\).*This is a refusal, not a fallback/);
  });

  test.serial("kill a holder mid-flight and the next acquire takes the stale lock", async () => {
    const leaseRoot = scratch();
    const range = { min: 24_921, max: 24_921 };
    const lockPath = portLeaseLockPath("app-facing", 24_921, leaseRoot);
    const holderSource = `
      import { acquirePortLease } from ${JSON.stringify(join(import.meta.dir, "port-lease.ts"))};
      acquirePortLease({
        role: "app-facing",
        runId: "run-killed-holder",
        leaseRoot: ${JSON.stringify(leaseRoot)},
        range: { min: 24921, max: 24921 },
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
    child.kill("SIGKILL");
    await new Promise<void>((resolve) => {
      child.once("exit", () => resolve());
    });

    const next = acquirePortLease({
      role: "app-facing",
      runId: "run-after-kill",
      leaseRoot,
      range,
    });
    try {
      expect(next.record.port).toBe(24_921);
      expect(next.record.runId).toBe("run-after-kill");
    } finally {
      next.release();
    }
  });
});

describe("loadAppFacingTestLease", () => {
  test("loads a file whose holder is still live", () => {
    const leaseRoot = scratch();
    const directory = scratch();
    const lease = acquireAppFacingTestLease({ runId: "run-load-live", leaseRoot });
    const path = join(directory, "lease.json");
    try {
      writeAppFacingTestLeaseFile(path, lease);
      const loaded = loadAppFacingTestLease(path);
      expect(loaded.port).toBe(lease.port);
      expect(loopbackServeOptionsForTestLease(loaded)).toEqual({
        hostname: LOOPBACK_HOST,
        port: lease.port,
      });
      loaded.release();
    } finally {
      lease.release();
    }
  });
});

describe("dev-server production path refuses a test port", () => {
  test("RED-PROOF OMI_PORT=14851 without --app-facing-test-lease is refused", () => {
    const result = spawnSync(process.execPath, ["apps/service/bin/dev-server.ts"], {
      cwd: process.cwd(),
      encoding: "utf8",
      env: {
        ...process.env,
        OMI_PORT: "14851",
        OMI_STT_ENGINE: "",
        OMI_STT_MODEL: "",
        OMI_STT_VENV: "",
      },
    });
    expect(result.status).toBe(1);
    expect(`${result.stdout}${result.stderr}`).toContain("port 14851 is not allocated to this service");
  });
});
