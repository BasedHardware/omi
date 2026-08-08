/**
 * Bind-safety assertions: a harness server must not be LAN-reachable.
 */

import { networkInterfaces } from "node:os";

export type LsofListenCheck = "passed" | "failed";
/** Skipped is intentionally distinct from passed — never report skip as pass. */
export type LanProbeCheck = "passed" | "failed" | "lan_probe_skipped";

export type LoopbackAssertResult = {
  port: number;
  /** Which checks ran and their outcomes. `lan_probe_skipped` is not a pass. */
  checks: {
    lsof_listen_bind: LsofListenCheck;
    lan_http_unreachable: LanProbeCheck;
  };
  /** Listen addresses observed by lsof (host portion only). */
  listenAddresses: string[];
  /** Non-loopback IPv4 used for the LAN probe, if any. */
  lanIp: string | null;
};

export type AssertLoopbackOnlyOptions = {
  /** Override LAN IPv4 discovery (test seam). `null` forces lan_probe_skipped. */
  resolveLanIpv4?: () => string | null;
  /** Timeout for the LAN reachability probe. Default 750ms. */
  lanFetchTimeoutMs?: number;
};

export class LoopbackAssertError extends Error {
  readonly result: LoopbackAssertResult;

  constructor(message: string, result: LoopbackAssertResult) {
    super(message);
    this.name = "LoopbackAssertError";
    this.result = result;
  }
}

const LOOPBACK_HOSTS = new Set(["127.0.0.1", "::1"]);

/**
 * Discover a non-loopback LAN IPv4, skipping internal interfaces.
 * Returns null when the host has none (caller must label lan_probe_skipped).
 */
export function discoverLanIpv4(): string | null {
  const ifaces = networkInterfaces();
  for (const addrs of Object.values(ifaces)) {
    if (!addrs) continue;
    for (const addr of addrs) {
      const family = addr.family;
      const isV4 = family === "IPv4" || family === 4;
      if (isV4 && !addr.internal) {
        return addr.address;
      }
    }
  }
  return null;
}

/**
 * Parse host portion from an lsof NAME field like `127.0.0.1:8080`,
 * `*:8080`, or `[::1]:8080`.
 */
export function parseLsofListenHost(nameToken: string): string {
  if (nameToken.startsWith("[")) {
    const end = nameToken.indexOf("]");
    if (end !== -1) return nameToken.slice(1, end);
  }
  // Bare `*` (no port) or `*:port` / `0.0.0.0:port` / `127.0.0.1:port`
  if (nameToken === "*") return "*";
  const colon = nameToken.lastIndexOf(":");
  if (colon === -1) return nameToken;
  return nameToken.slice(0, colon);
}

/**
 * Extract listen hosts from `lsof -nP -iTCP:<port> -sTCP:LISTEN` stdout.
 */
export function parseLsofListenHosts(lsofStdout: string): string[] {
  const hosts: string[] = [];
  for (const line of lsofStdout.split("\n")) {
    if (!line.includes("(LISTEN)")) continue;
    // NAME column ends with: TCP <addr> (LISTEN)
    const match = /\bTCP\s+(\S+)\s+\(LISTEN\)\s*$/.exec(line);
    if (!match?.[1]) continue;
    hosts.push(parseLsofListenHost(match[1]));
  }
  return hosts;
}

function runLsofListen(port: number): string {
  const result = Bun.spawnSync(
    ["lsof", "-nP", `-iTCP:${port}`, "-sTCP:LISTEN"],
    { stdout: "pipe", stderr: "pipe" },
  );
  // lsof exits 1 when there are no matching sockets — treat as empty.
  return result.stdout.toString();
}

/**
 * Assert a listening port is loopback-only.
 *
 * Does BOTH:
 *   (a) lsof LISTEN rows must bind 127.0.0.1 or [::1] — fail on 0.0.0.0 / `*`
 *   (b) HTTP GET to a non-loopback LAN IPv4 MUST fail (refused/timeout).
 *       Success is a hard failure: the server is LAN-reachable.
 *
 * If the host has no non-loopback IPv4, returns `lan_probe_skipped` rather than
 * silently passing that check. A skipped probe is never reported as a pass.
 */
export async function assertLoopbackOnly(
  port: number,
  opts: AssertLoopbackOnlyOptions = {},
): Promise<LoopbackAssertResult> {
  const listenAddresses = parseLsofListenHosts(runLsofListen(port));

  const result: LoopbackAssertResult = {
    port,
    checks: {
      lsof_listen_bind: "failed",
      lan_http_unreachable: "lan_probe_skipped",
    },
    listenAddresses,
    lanIp: null,
  };

  if (listenAddresses.length === 0) {
    throw new LoopbackAssertError(
      `assertLoopbackOnly(${port}): no TCP LISTEN sockets found via lsof`,
      result,
    );
  }

  for (const host of listenAddresses) {
    if (host === "0.0.0.0" || host === "*" || host === "::") {
      result.checks.lsof_listen_bind = "failed";
      throw new LoopbackAssertError(
        `assertLoopbackOnly(${port}): non-loopback listen bind '${host}' (refuse 0.0.0.0 / * / ::)`,
        result,
      );
    }
    if (!LOOPBACK_HOSTS.has(host)) {
      result.checks.lsof_listen_bind = "failed";
      throw new LoopbackAssertError(
        `assertLoopbackOnly(${port}): listen address '${host}' is not loopback`,
        result,
      );
    }
  }
  result.checks.lsof_listen_bind = "passed";

  const resolveLan = opts.resolveLanIpv4 ?? discoverLanIpv4;
  const lanIp = resolveLan();
  result.lanIp = lanIp;

  if (lanIp === null) {
    // Explicit skip — NOT a pass.
    result.checks.lan_http_unreachable = "lan_probe_skipped";
    return result;
  }

  const lanFetchTimeoutMs = opts.lanFetchTimeoutMs ?? 750;
  const url = `http://${lanIp}:${port}/`;
  let reachable = false;
  let reachDetail = "";

  try {
    const response = await fetch(url, {
      signal: AbortSignal.timeout(lanFetchTimeoutMs),
    });
    reachable = true;
    reachDetail = `HTTP ${response.status}`;
  } catch (err) {
    // Connection refused / timeout / network error ⇒ not LAN-reachable ⇒ good.
    reachable = false;
    reachDetail = err instanceof Error ? err.message : String(err);
  }

  if (reachable) {
    result.checks.lan_http_unreachable = "failed";
    throw new LoopbackAssertError(
      `assertLoopbackOnly(${port}): LAN probe SUCCEEDED via ${url} (${reachDetail}) — server is LAN-reachable`,
      result,
    );
  }

  result.checks.lan_http_unreachable = "passed";
  return result;
}
