import { networkInterfaces } from "node:os";
import { connect, type Socket } from "node:net";

export interface LoopbackBindReport {
  readonly port: number;
  /** Every local address:port the OS reports as listening on this port. */
  readonly listening_addresses: readonly string[];
  /** True when every listening address is a loopback address. */
  readonly loopback_only: boolean;
  /** Non-loopback LAN addresses of this host that were probed. */
  readonly probed_lan_addresses: readonly string[];
  /** True when no LAN address accepted a connection. */
  readonly lan_unreachable: boolean;
}

const LAN_PROBE_TIMEOUT_MS = 250;

/** Extract the host portion from an lsof NAME `address:port` token. */
export const extractListenHost = (addressPort: string): string => {
  if (addressPort.startsWith("[")) {
    const end = addressPort.indexOf("]");
    if (end === -1) {
      throw new TypeError(`invalid listen address: ${addressPort}`);
    }
    return addressPort.slice(1, end);
  }
  const colon = addressPort.lastIndexOf(":");
  if (colon === -1) {
    return addressPort;
  }
  return addressPort.slice(0, colon);
};

/** True when `host` is loopback (`127.0.0.0/8`, `::1`, or `localhost`). */
export const isLoopbackHost = (host: string): boolean => {
  const normalized = host.toLowerCase();
  if (normalized === "localhost" || normalized === "::1") {
    return true;
  }
  if (normalized === "*" || normalized === "0.0.0.0" || normalized === "::") {
    return false;
  }
  if (!normalized.startsWith("127.")) {
    return false;
  }
  const parts = normalized.split(".");
  if (parts.length !== 4) {
    return false;
  }
  return parts.every((part) => /^\d{1,3}$/.test(part) && Number(part) <= 255);
};

/** True when an lsof `address:port` listen entry is loopback-only. */
export const isLoopbackListenAddress = (addressPort: string): boolean =>
  isLoopbackHost(extractListenHost(addressPort));

/** Parse `lsof -nP -iTCP:<port> -sTCP:LISTEN` stdout into `address:port` entries. */
export const parseLsofListenAddresses = (output: string): string[] => {
  const addresses: string[] = [];
  for (const line of output.split("\n")) {
    const listenMarker = "(LISTEN)";
    const listenIndex = line.indexOf(listenMarker);
    if (listenIndex === -1) {
      continue;
    }
    const tcpIndex = line.lastIndexOf("TCP ", listenIndex);
    if (tcpIndex === -1) {
      continue;
    }
    const addressPort = line.slice(tcpIndex + 4, listenIndex).trim();
    if (addressPort.length > 0) {
      addresses.push(addressPort);
    }
  }
  return addresses;
};

const runLsof = async (port: number): Promise<string> => {
  let proc: ReturnType<typeof Bun.spawn>;
  try {
    proc = Bun.spawn(["lsof", "-nP", `-iTCP:${port}`, "-sTCP:LISTEN"], {
      stdout: "pipe",
      stderr: "pipe",
    });
  } catch (error) {
    throw new TypeError(`lsof is unavailable: ${String(error)}`);
  }

  const exitCode = await proc.exited;
  const stdout = await new Response(proc.stdout).text();
  const stderr = await new Response(proc.stderr).text();

  if (exitCode !== 0 && exitCode !== 1) {
    throw new TypeError(
      `lsof failed (exit ${exitCode})${stderr.trim() ? `: ${stderr.trim()}` : ""}`,
    );
  }

  if (stdout.trim().length === 0) {
    throw new TypeError(`no listeners reported by lsof on port ${port}`);
  }

  return stdout;
};

const enumerateLanIpv4Addresses = (): string[] => {
  const addresses = new Set<string>();
  for (const entries of Object.values(networkInterfaces())) {
    if (!entries) {
      continue;
    }
    for (const entry of entries) {
      const family = entry.family;
      const isIpv4 = family === "IPv4" || family === 4;
      if (isIpv4 && !entry.internal) {
        addresses.add(entry.address);
      }
    }
  }
  return [...addresses];
};

const probeTcpReachable = (host: string, port: number, timeoutMs: number): Promise<boolean> =>
  new Promise((resolve) => {
    let settled = false;
    let socket: Socket | undefined;

    const finish = (reachable: boolean) => {
      if (settled) {
        return;
      }
      settled = true;
      socket?.destroy();
      resolve(reachable);
    };

    socket = connect({ host, port, timeout: timeoutMs });
    socket.on("connect", () => finish(true));
    socket.on("timeout", () => finish(false));
    socket.on("error", () => finish(false));
  });

const probeLanAddresses = async (
  addresses: readonly string[],
  port: number,
): Promise<{ lan_unreachable: boolean; reachable: string[] }> => {
  if (addresses.length === 0) {
    return { lan_unreachable: true, reachable: [] };
  }

  const reachable: string[] = [];
  await Promise.all(
    addresses.map(async (address) => {
      if (await probeTcpReachable(address, port, LAN_PROBE_TIMEOUT_MS)) {
        reachable.push(address);
      }
    }),
  );

  return { lan_unreachable: reachable.length === 0, reachable };
};

const buildLoopbackBindReport = async (
  port: number,
): Promise<LoopbackBindReport & { readonly reachable_lan_addresses: readonly string[] }> => {
  const lsofOutput = await runLsof(port);
  const listening_addresses = parseLsofListenAddresses(lsofOutput);

  if (listening_addresses.length === 0) {
    throw new TypeError(`no TCP listeners parsed from lsof for port ${port}`);
  }

  const loopback_only = listening_addresses.every(isLoopbackListenAddress);
  const probed_lan_addresses = enumerateLanIpv4Addresses();
  const { lan_unreachable, reachable } = await probeLanAddresses(probed_lan_addresses, port);

  return {
    port,
    listening_addresses,
    loopback_only,
    probed_lan_addresses,
    lan_unreachable,
    reachable_lan_addresses: reachable,
  };
};

export const inspectLoopbackBind = async (port: number): Promise<LoopbackBindReport> => {
  const { reachable_lan_addresses: _reachable, ...report } = await buildLoopbackBindReport(port);
  return report;
};

export const assertLoopbackOnly = async (port: number): Promise<LoopbackBindReport> => {
  const { reachable_lan_addresses, ...report } = await buildLoopbackBindReport(port);

  if (!report.loopback_only) {
    const offending = report.listening_addresses.filter((address) => !isLoopbackListenAddress(address));
    throw new TypeError(
      `port ${port} is not loopback-only; non-loopback listen addresses: ${offending.join(", ")}`,
    );
  }

  if (!report.lan_unreachable) {
    throw new TypeError(
      `port ${port} is reachable on LAN addresses: ${reachable_lan_addresses.join(", ")}`,
    );
  }

  return report;
};
