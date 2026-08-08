import { describe, expect, test } from "bun:test";

import {
  LOOPBACK_HOST,
  assertPortInRange,
  loopbackServeOptions,
  parseLsofListenOutput,
} from "./loopback";

describe("loopbackServeOptions", () => {
  test("returns hostname 127.0.0.1 for an allowed port", () => {
    const options = loopbackServeOptions(4811);
    // red-proof: omit hostname or set it to 0.0.0.0 and this test fails
    expect(options).toEqual({ hostname: LOOPBACK_HOST, port: 4811 });
  });

  test("accepts both BE-SURFACE agent ports", () => {
    // red-proof: drop 4812 from the allowed set and the second assertion fails
    expect(loopbackServeOptions(4811).port).toBe(4811);
    expect(loopbackServeOptions(4812).port).toBe(4812);
  });
});

describe("assertPortInRange", () => {
  test("allows ports 4811 and 4812", () => {
    // red-proof: widen the allowed set to include 8080 and this test no longer guards squatting
    expect(() => assertPortInRange(4811)).not.toThrow();
    expect(() => assertPortInRange(4812)).not.toThrow();
  });

  test("rejects ports outside the BE-SURFACE agent range with TypeError", () => {
    // red-proof: accept port 3000 and this test fails
    expect(() => assertPortInRange(3000)).toThrow(TypeError);
    expect(() => assertPortInRange(4810)).toThrow(TypeError);
    expect(() => assertPortInRange(4813)).toThrow(TypeError);
  });
});

describe("parseLsofListenOutput", () => {
  test("passes when every listener is bound to 127.0.0.1", () => {
    const fixture = [
      "COMMAND   PID USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME",
      "bun     4242 user   11u  IPv4 0xdeadbeef      0t0  TCP 127.0.0.1:4811 (LISTEN)",
    ].join("\n");

    const verdict = parseLsofListenOutput(fixture, 4811);
    // red-proof: accept *:4811 or [::1]:4811 and this test fails
    expect(verdict.pass).toBe(true);
    expect(verdict.listenerCount).toBe(1);
  });

  test("rejects a wildcard *:4811 listener", () => {
    const fixture = [
      "COMMAND   PID USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME",
      "bun     4242 user   11u  IPv6 0xdeadbeef      0t0  TCP *:4811 (LISTEN)",
    ].join("\n");

    const verdict = parseLsofListenOutput(fixture, 4811);
    // red-proof: treat * as loopback-safe and this test fails
    expect(verdict.pass).toBe(false);
    expect(verdict.reason).toBe("non-loopback listener detected");
  });

  test("rejects an IPv6 [::1]:4811 listener", () => {
    const fixture = [
      "COMMAND   PID USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME",
      "bun     4242 user   12u  IPv6 0xdeadbeef      0t0  TCP [::1]:4811 (LISTEN)",
    ].join("\n");

    const verdict = parseLsofListenOutput(fixture, 4811);
    // red-proof: treat [::1] as equivalent to 127.0.0.1 and this test fails
    expect(verdict.pass).toBe(false);
    expect(verdict.reason).toBe("non-loopback listener detected");
  });

  test("fails when lsof reports no listeners for the port", () => {
    const fixture = "COMMAND   PID USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME\n";

    const verdict = parseLsofListenOutput(fixture, 4811);
    // red-proof: treat an empty result as pass and this test fails
    expect(verdict.pass).toBe(false);
    expect(verdict.listenerCount).toBe(0);
    expect(verdict.reason).toBe("no listeners on port");
  });

  test("ignores LISTEN rows for other ports", () => {
    const fixture = [
      "COMMAND   PID USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME",
      "bun     4242 user   11u  IPv4 0xdeadbeef      0t0  TCP *:4812 (LISTEN)",
      "bun     4242 user   12u  IPv4 0xdeadbeef      0t0  TCP 127.0.0.1:4811 (LISTEN)",
    ].join("\n");

    const verdict = parseLsofListenOutput(fixture, 4811);
    // red-proof: match any LISTEN row regardless of port and this test fails on the *:4812 row
    expect(verdict.pass).toBe(true);
    expect(verdict.listenerCount).toBe(1);
  });
});
