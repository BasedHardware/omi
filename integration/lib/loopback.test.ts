import { expect, test } from "bun:test";

import {
  assertLoopbackOnly,
  LoopbackAssertError,
  parseLsofListenHost,
  parseLsofListenHosts,
} from "./loopback.ts";

function listen(
  hostname: string,
  handler: () => Response = () => new Response("ok"),
): { port: number; stop: () => void } {
  const server = Bun.serve({
    hostname,
    port: 0,
    fetch: handler,
  });
  const port = server.port;
  if (typeof port !== "number") throw new Error("expected numeric port");
  return {
    port,
    stop: () => {
      server.stop(true);
    },
  };
}

test("loopback-bound server passes lsof + LAN-unreachable checks", async () => {
  // red-proof: mark checks.lan_http_unreachable as "passed" even when resolveLanIpv4 returns null (collapse skip into pass)
  const { port, stop } = listen("127.0.0.1");
  try {
    const result = await assertLoopbackOnly(port);
    expect(result.checks.lsof_listen_bind).toBe("passed");
    // Must be a real bind we observed — not a decorative "it returned something".
    expect(result.listenAddresses).toContain("127.0.0.1");
    expect(
      result.checks.lan_http_unreachable === "passed" ||
        result.checks.lan_http_unreachable === "lan_probe_skipped",
    ).toBe(true);
    if (result.checks.lan_http_unreachable === "passed") {
      expect(result.lanIp).toMatch(/^\d+\.\d+\.\d+\.\d+$/);
    }
  } finally {
    stop();
  }
});

test("successful LAN HTTP fetch is a hard failure", async () => {
  // red-proof: treat a successful LAN HTTP fetch as pass (invert the reachable⇒fail rule)
  const { port, stop } = listen("127.0.0.1");
  try {
    // lsof passes (loopback bind). Force the "LAN" target to loopback so the
    // HTTP probe SUCCEEDS — that success must fail the assertion.
    let caught: LoopbackAssertError | null = null;
    try {
      await assertLoopbackOnly(port, {
        resolveLanIpv4: () => "127.0.0.1",
        lanFetchTimeoutMs: 1_000,
      });
    } catch (err) {
      caught = err as LoopbackAssertError;
    }
    expect(caught).toBeInstanceOf(LoopbackAssertError);
    expect(caught!.result.checks.lsof_listen_bind).toBe("passed");
    expect(caught!.result.checks.lan_http_unreachable).toBe("failed");
    expect(caught!.message).toMatch(/LAN probe SUCCEEDED|LAN-reachable/);
  } finally {
    stop();
  }
});

test("all-interfaces bind is rejected by lsof before any pass is reported", async () => {
  // red-proof: allow listen host '0.0.0.0' (or '*') through the lsof allow-list and return checks as passed
  const { port, stop } = listen("0.0.0.0");
  try {
    let caught: LoopbackAssertError | null = null;
    try {
      await assertLoopbackOnly(port, { resolveLanIpv4: () => null });
    } catch (err) {
      caught = err as LoopbackAssertError;
    }
    expect(caught).toBeInstanceOf(LoopbackAssertError);
    expect(caught!.result.checks.lsof_listen_bind).toBe("failed");
    expect(
      caught!.result.listenAddresses.some((h) => h === "0.0.0.0" || h === "*"),
    ).toBe(true);
  } finally {
    stop();
  }
});

test("missing LAN IPv4 is labelled lan_probe_skipped, not passed", async () => {
  // red-proof: set checks.lan_http_unreachable = "passed" when resolveLanIpv4() returns null
  const { port, stop } = listen("127.0.0.1");
  try {
    const result = await assertLoopbackOnly(port, {
      resolveLanIpv4: () => null,
    });
    expect(result.checks.lsof_listen_bind).toBe("passed");
    expect(result.checks.lan_http_unreachable).toBe("lan_probe_skipped");
    expect(result.checks.lan_http_unreachable).not.toBe("passed");
    expect(result.lanIp).toBeNull();
  } finally {
    stop();
  }
});

test("parseLsofListenHosts rejects wildcard and all-interfaces tokens", () => {
  // red-proof: map host '*' / '0.0.0.0' to '127.0.0.1' inside parseLsofListenHost
  expect(parseLsofListenHost("*:8080")).toBe("*");
  expect(parseLsofListenHost("0.0.0.0:8080")).toBe("0.0.0.0");
  expect(parseLsofListenHost("127.0.0.1:8080")).toBe("127.0.0.1");
  expect(parseLsofListenHost("[::1]:8080")).toBe("::1");

  const parsed = parseLsofListenHosts(
    [
      "COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME",
      "bun 1 me 6u IPv4 0x1 0t0 TCP *:9999 (LISTEN)",
      "bun 1 me 7u IPv4 0x2 0t0 TCP 0.0.0.0:9999 (LISTEN)",
      "bun 1 me 8u IPv4 0x3 0t0 TCP 127.0.0.1:9999 (LISTEN)",
    ].join("\n"),
  );
  expect(parsed).toEqual(["*", "0.0.0.0", "127.0.0.1"]);
});
