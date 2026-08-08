import { networkInterfaces } from "node:os";

export const LOOPBACK_HOST = "127.0.0.1";

const ALLOWED_PORTS = new Set([4811, 4812]);

export type LsofListenVerdict = {
  readonly pass: boolean;
  readonly listenerCount: number;
  readonly reason?: string;
};

export type LoopbackServeOptions = {
  readonly hostname: typeof LOOPBACK_HOST;
  readonly port: number;
};

/**
 * Options for `Bun.serve` that bind only to loopback.
 *
 * Omitting `hostname` makes Bun bind `0.0.0.0` (all interfaces), which publishes
 * the listener to the LAN — the failure mode this module prevents.
 */
export function loopbackServeOptions(port: number): LoopbackServeOptions {
  assertPortInRange(port);
  return {
    hostname: LOOPBACK_HOST,
    port,
  };
}

export function assertPortInRange(port: number): void {
  if (!ALLOWED_PORTS.has(port)) {
    throw new TypeError(
      `port ${port} is outside the BE-SURFACE agent range (allowed: 4811, 4812)`,
    );
  }
}

export function enumerateNonLoopbackIPv4Addresses(): string[] {
  const addresses: string[] = [];
  for (const entries of Object.values(networkInterfaces())) {
    if (!entries) {
      continue;
    }
    for (const entry of entries) {
      const isIPv4 = entry.family === "IPv4" || entry.family === 4;
      if (isIPv4 && !entry.internal) {
        addresses.push(entry.address);
      }
    }
  }
  return addresses;
}

const LISTEN_ROW = /\bTCP\s+(\S+):(\d+)\s+\(LISTEN\)/;

function isLoopbackListenAddress(address: string): boolean {
  return address === LOOPBACK_HOST;
}

/**
 * Parse `lsof -nP -iTCP:<port> -sTCP:LISTEN` stdout.
 * PASS only when every listening row for the port is bound to 127.0.0.1.
 */
export function parseLsofListenOutput(output: string, port: number): LsofListenVerdict {
  const portText = String(port);
  let listenerCount = 0;

  for (const line of output.split(/\r?\n/)) {
    const match = line.match(LISTEN_ROW);
    if (!match) {
      continue;
    }

    const [, rawAddress, boundPort] = match;
    if (boundPort !== portText) {
      continue;
    }

    listenerCount += 1;
    const address = rawAddress.startsWith("[") && rawAddress.endsWith("]")
      ? rawAddress.slice(1, -1)
      : rawAddress;

    if (!isLoopbackListenAddress(address)) {
      return {
        pass: false,
        listenerCount,
        reason: "non-loopback listener detected",
      };
    }
  }

  if (listenerCount === 0) {
    return {
      pass: false,
      listenerCount: 0,
      reason: "no listeners on port",
    };
  }

  return {
    pass: true,
    listenerCount,
  };
}
