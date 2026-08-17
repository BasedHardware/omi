#!/usr/bin/env bun
/**
 * Acquire and hold run-scoped harness + app-facing test ports.
 *
 * Usage:
 *   bun integration/lib/stack-port-lease.ts hold \
 *     --run-id <raw-id> --out <lease.json> --app-facing-lease <file> \
 *     --roles service,gateway[,surface] [--gateway-kind test|real] \
 *     [--parent-pid <pid>] [--lease-root <dir>]
 *
 * Stays alive until SIGTERM/SIGINT, or until --parent-pid dies.
 * Releasing the process releases the locks. A crash leaves a stale lock
 * whose dead pid the next acquire replaces, unless a stranger is listening.
 *
 * Surface is the same mechanism as service and gateway, not a second one.
 * 5290 stays the long-lived app origin (IndexedDB persists across relaunch).
 * A verification run leases 15290-15309 so it gets a clean origin. Do not
 * unify those paths: a leased run that cannot acquire a surface port refuses
 * loudly and never falls back to 5290.
 */

import { writeFileSync } from "node:fs";

import {
  acquireAppFacingTestLease,
  writeAppFacingTestLeaseFile,
} from "../../apps/service/net/test-allocation";
import {
  acquirePortLease,
  processStartIdentity,
  type PortLeaseRole,
} from "../../apps/service/net/port-lease";

const SCHEMA = "omi.stack-port-lease.v1";

type GatewayKind = "test" | "real";
type RoleName = "service" | "gateway" | "surface";

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
    "usage: bun integration/lib/stack-port-lease.ts hold --run-id <id> --out <json> --app-facing-lease <file> --roles service,gateway[,surface]\n",
  );
  process.exit(command === "hold" ? 2 : 0);
}

const runId = flag(argv, "--run-id");
const outPath = flag(argv, "--out");
const appFacingPath = flag(argv, "--app-facing-lease");
const rolesRaw = flag(argv, "--roles") ?? "service,gateway";
const gatewayKindRaw = flag(argv, "--gateway-kind") ?? "test";
const parentPidRaw = flag(argv, "--parent-pid");
const leaseRoot = flag(argv, "--lease-root") ?? undefined;

if (!runId || !outPath || !appFacingPath) {
  fail("hold needs --run-id, --out, and --app-facing-lease", 2);
}
if (gatewayKindRaw !== "test" && gatewayKindRaw !== "real") {
  fail("--gateway-kind must be test or real", 2);
}
const gatewayKind = gatewayKindRaw as GatewayKind;
const roles = rolesRaw.split(",").map((role) => role.trim()) as RoleName[];
for (const role of roles) {
  if (role !== "service" && role !== "gateway" && role !== "surface") {
    fail(`unknown role ${role}`, 2);
  }
}
if (!roles.includes("service") || !roles.includes("gateway")) {
  fail("--roles must include service and gateway", 2);
}

const parentPid = parentPidRaw === null ? null : Number(parentPidRaw);
if (parentPidRaw !== null && (!Number.isSafeInteger(parentPid) || parentPid <= 0)) {
  fail("--parent-pid must be a positive integer", 2);
}

const held: Array<{ release: () => void }> = [];
const releaseAll = () => {
  for (const lease of held.splice(0).reverse()) lease.release();
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
  const serviceLease = acquireAppFacingTestLease({
    runId,
    ...(leaseRoot === undefined ? {} : { leaseRoot }),
  });
  held.push(serviceLease);
  writeAppFacingTestLeaseFile(appFacingPath, serviceLease);

  const gatewayRole: PortLeaseRole = gatewayKind === "real" ? "gateway-real" : "gateway-test";
  const gatewayLease = acquirePortLease({
    role: gatewayRole,
    runId,
    ...(leaseRoot === undefined ? {} : { leaseRoot }),
  });
  held.push(gatewayLease);

  let surfacePort: number | null = null;
  if (roles.includes("surface")) {
    // Verification origin. Persistence across relaunch is a property only the
    // long-lived app on 5290 needs. This run wants the opposite: a clean
    // origin, no IndexedDB from a previous run or from the app David clicks.
    // Do not "unify" this acquire with 5290 because the two look similar.
    const surfaceLease = acquirePortLease({
      role: "surface",
      runId,
      ...(leaseRoot === undefined ? {} : { leaseRoot }),
    });
    held.push(surfaceLease);
    surfacePort = surfaceLease.record.port;
  }

  const ports = {
    service: serviceLease.port,
    gateway: gatewayLease.record.port,
    ...(surfacePort === null ? {} : { surface: surfacePort }),
  };
  const urls = {
    service: `http://127.0.0.1:${ports.service}`,
    gateway: `http://127.0.0.1:${ports.gateway}`,
    ...(surfacePort === null ? {} : { surface: `http://127.0.0.1:${surfacePort}` }),
  };
  writeFileSync(outPath, `${JSON.stringify({
    schema: SCHEMA,
    runId,
    gatewayKind,
    ports,
    urls,
    holderPid: process.pid,
  }, null, 2)}\n`, { encoding: "utf8", mode: 0o600 });
} catch (error) {
  releaseAll();
  fail(error instanceof Error ? error.message : "port lease acquire failed");
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
