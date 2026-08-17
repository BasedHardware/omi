#!/usr/bin/env bun

import { spawnSync } from "node:child_process";

import {
  assertPortInRange,
  enumerateNonLoopbackIPv4Addresses,
  parseLsofListenOutput,
} from "./loopback";

const VERDICT_VERSION = "loopback-assertion-v1";
const LAN_PROBE_TIMEOUT_MS = 750;

type VerdictStatus = "pass" | "fail" | "inconclusive";

type LoopbackAssertionVerdict = {
  readonly version: typeof VERDICT_VERSION;
  readonly port: number;
  readonly lsof: {
    readonly status: "pass" | "fail";
    readonly listenerCount: number;
    readonly reason?: string;
  };
  readonly lanProbe: {
    readonly status: VerdictStatus;
    readonly probedAddresses: readonly string[];
    readonly reason?: string;
  };
  readonly verdict: VerdictStatus;
};

function parsePortArg(raw: string | undefined): number {
  if (!raw) {
    throw new TypeError("usage: bun run apps/service/net/assert-loopback.ts <port>");
  }

  const port = Number(raw);
  if (!Number.isInteger(port) || port < 1 || port > 65_535) {
    throw new TypeError(`invalid port: ${raw}`);
  }

  assertPortInRange(port);
  return port;
}

function runLsof(port: number): LsofListenVerdict {
  const result = spawnSync("lsof", ["-nP", `-iTCP:${port}`, "-sTCP:LISTEN"], {
    encoding: "utf8",
  });

  if (result.error) {
    return {
      pass: false,
      listenerCount: 0,
      reason: "lsof execution failed",
    };
  }

  return parseLsofListenOutput(result.stdout ?? "", port);
}

type LsofListenVerdict = ReturnType<typeof parseLsofListenOutput>;

async function probeLanAddress(address: string, port: number): Promise<"refused" | "timeout" | "connected"> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), LAN_PROBE_TIMEOUT_MS);

  try {
    const response = await fetch(`http://${address}:${port}/health`, {
      signal: controller.signal,
    });
    await response.body?.cancel();
    return "connected";
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      return "timeout";
    }
    return "refused";
  } finally {
    clearTimeout(timeout);
  }
}

async function runLanProbe(port: number): Promise<LoopbackAssertionVerdict["lanProbe"]> {
  const probedAddresses = enumerateNonLoopbackIPv4Addresses();

  if (probedAddresses.length === 0) {
    return {
      status: "inconclusive",
      probedAddresses,
      reason: "no non-loopback IPv4 addresses on host",
    };
  }

  for (const address of probedAddresses) {
    const outcome = await probeLanAddress(address, port);
    if (outcome === "connected") {
      return {
        status: "fail",
        probedAddresses,
        reason: "LAN address reached /health",
      };
    }
  }

  return {
    status: "pass",
    probedAddresses,
  };
}

function combineVerdict(
  lsof: LoopbackAssertionVerdict["lsof"],
  lanProbe: LoopbackAssertionVerdict["lanProbe"],
): VerdictStatus {
  if (lsof.status === "fail") {
    return "fail";
  }
  if (lanProbe.status === "fail") {
    return "fail";
  }
  if (lanProbe.status === "inconclusive") {
    return "inconclusive";
  }
  return "pass";
}

async function main(): Promise<void> {
  const port = parsePortArg(process.argv[2]);
  const lsofResult = runLsof(port);
  const lanProbe = await runLanProbe(port);

  const verdict: LoopbackAssertionVerdict = {
    version: VERDICT_VERSION,
    port,
    lsof: {
      status: lsofResult.pass ? "pass" : "fail",
      listenerCount: lsofResult.listenerCount,
      ...(lsofResult.reason ? { reason: lsofResult.reason } : {}),
    },
    lanProbe,
    verdict: combineVerdict(
      {
        status: lsofResult.pass ? "pass" : "fail",
        listenerCount: lsofResult.listenerCount,
      },
      lanProbe,
    ),
  };

  console.log(JSON.stringify(verdict));
  process.exit(verdict.verdict === "pass" ? 0 : 1);
}

main().catch((error: unknown) => {
  // Fixed message. The caught value can carry lsof output, command lines,
  // process and user names, or filesystem paths, and this script's whole job is
  // to report a verdict without publishing any of that. An unexpected crash is
  // a failure to prove loopback binding, which is all the caller needs to know.
  void error;
  console.error(JSON.stringify({
    version: "loopback-assertion-v1",
    verdict: "fail",
    reason: "assertion_failed_to_run",
  }));
  process.exit(1);
});
