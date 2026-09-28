import { afterEach, describe, expect, test } from "bun:test";

import {
  assertLoopbackOnly,
  extractListenHost,
  inspectLoopbackBind,
  isLoopbackHost,
  isLoopbackListenAddress,
  parseLsofListenAddresses,
} from "./loopback";

const noopFetch = () => new Response("ok");

describe("loopback listen address parsing", () => {
  test("classifies IPv4, IPv6, and wildcard forms", () => {
    expect(extractListenHost("127.0.0.1:4801")).toBe("127.0.0.1");
    expect(extractListenHost("[::1]:4801")).toBe("::1");
    expect(extractListenHost("*:4801")).toBe("*");

    expect(isLoopbackHost("127.0.0.1")).toBe(true);
    expect(isLoopbackHost("::1")).toBe(true);
    expect(isLoopbackHost("localhost")).toBe(true);
    expect(isLoopbackHost("*")).toBe(false);
    expect(isLoopbackHost("0.0.0.0")).toBe(false);

    expect(isLoopbackListenAddress("127.0.0.1:4801")).toBe(true);
    expect(isLoopbackListenAddress("[::1]:4801")).toBe(true);
    expect(isLoopbackListenAddress("*:4801")).toBe(false);
  });

  test("parseLsofListenAddresses reads the NAME column", () => {
    const output = [
      "COMMAND   PID USER   FD   TYPE DEVICE SIZE/OFF NODE NAME",
      "bun     12345 user   10u  IPv4 0x0      0t0  TCP 127.0.0.1:4801 (LISTEN)",
      "bun     12345 user   11u  IPv6 0x0      0t0  TCP [::1]:4801 (LISTEN)",
      "bun     12345 user   12u  IPv4 0x0      0t0  TCP *:4801 (LISTEN)",
    ].join("\n");

    expect(parseLsofListenAddresses(output)).toEqual([
      "127.0.0.1:4801",
      "[::1]:4801",
      "*:4801",
    ]);
  });
});

describe("inspectLoopbackBind", () => {
  test("throws when nothing is listening on the port", async () => {
    let port = 49_999;
    while (port > 40_000) {
      try {
        await inspectLoopbackBind(port);
        port -= 1;
      } catch (error) {
        expect(error).toBeInstanceOf(TypeError);
        expect(String(error)).toContain(String(port));
        return;
      }
    }
    throw new Error("could not find a free high port for the empty-listener test");
  });
});

describe("assertLoopbackOnly", () => {
  const servers: Array<{ stop: () => void }> = [];

  afterEach(() => {
    while (servers.length > 0) {
      servers.pop()?.stop();
    }
  });

  test("accepts a server bound to 127.0.0.1", async () => {
    const server = Bun.serve({
      hostname: "127.0.0.1",
      port: 0,
      fetch: noopFetch,
    });
    servers.push(server);

    const report = await assertLoopbackOnly(server.port);

    expect(report.loopback_only).toBe(true);
    expect(report.lan_unreachable).toBe(true);
    expect(report.listening_addresses.some((address) => isLoopbackListenAddress(address))).toBe(
      true,
    );
  });

  test("rejects a server bound to 0.0.0.0", async () => {
    let server: ReturnType<typeof Bun.serve>;
    try {
      server = Bun.serve({
        hostname: "0.0.0.0",
        port: 0,
        fetch: noopFetch,
      });
    } catch (error) {
      console.warn(
        `skipping 0.0.0.0 bind rejection test: sandbox refused wildcard bind (${String(error)})`,
      );
      return;
    }
    servers.push(server);

    let rejected: unknown;
    try {
      await assertLoopbackOnly(server.port);
    } catch (error) {
      rejected = error;
    }

    expect(rejected).toBeInstanceOf(TypeError);
  // red-proof: treating * as loopback makes this test pass wrongly.
    expect(String(rejected)).toMatch(/\*|0\.0\.0\.0/);
  });
});
