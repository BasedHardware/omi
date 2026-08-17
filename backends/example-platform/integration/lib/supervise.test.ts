import { expect, test } from "bun:test";
import { mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  ManagedProcess,
  superviseChild,
  waitForHttpReady,
} from "./supervise.ts";

function freePort(): number {
  const server = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    fetch: () => new Response("probe"),
  });
  const port = server.port;
  if (typeof port !== "number") throw new Error("expected numeric port");
  server.stop(true);
  return port;
}

function writeTempScript(name: string, source: string): string {
  const dir = join(tmpdir(), `omi-supervise-${process.pid}`);
  mkdirSync(dir, { recursive: true });
  const path = join(dir, name);
  writeFileSync(path, source, "utf8");
  return path;
}

test("HTTP-ready then nonzero exit is reported as failure via child exit status", async () => {
  // red-proof: treat waitForHttpReady success as overall success and force exitCode to 0 (or skip awaiting child.exited)
  const port = freePort();
  const script = writeTempScript(
    "ready-then-fail.ts",
    `
const port = Number(process.env.PORT);
const server = Bun.serve({
  hostname: "127.0.0.1",
  port,
  fetch() {
    // Become HTTP-ready, THEN fail acceptance by exiting nonzero.
    //
    // The exit must not race the response. A queueMicrotask here runs before
    // the response is flushed, so the client sees "Empty reply from server",
    // readiness is never observed, and the poll runs to its own budget - the
    // test then times out instead of asserting. Give the response time to
    // reach the wire first; the delay is what makes readiness genuinely
    // succeed before the nonzero exit, which is the whole point of the case.
    setTimeout(() => {
      server.stop(true);
      process.exit(1);
    }, 250);
    return new Response("ready");
  },
});
`,
  );

  const supervised = superviseChild({
    command: ["bun", "run", script],
    env: { ...process.env, PORT: String(port) },
    timeoutMs: 15_000,
    killGraceMs: 500,
  });

  // Separate await #1: readiness (must succeed on its own).
  await waitForHttpReady(`http://127.0.0.1:${port}/`, {
    timeoutMs: 10_000,
    pollIntervalMs: 25,
  });

  // Separate await #2: exact child exit (acceptance).
  const result = await supervised;

  expect(result.timedOut).toBe(false);
  // Content only a working exit-propagation path can produce:
  expect(result.exitCode).toBe(1);
  expect(result.signal).toBeNull();
});

test("wedged child is killed and reported timedOut rather than hanging", async () => {
  // red-proof: remove the timeout→escalateKill path so superviseChild awaits forever on a non-exiting child
  const started = Date.now();
  const result = await superviseChild({
    command: [
      "bun",
      "-e",
      // Never exits, never listens — a wedged acceptance probe stand-in.
      "setInterval(() => {}, 1_000_000);",
    ],
    timeoutMs: 400,
    killGraceMs: 200,
  });
  const elapsed = Date.now() - started;

  expect(result.timedOut).toBe(true);
  // Must have been reaped (signal kill), not left as a live hang.
  expect(result.exitCode === null || result.exitCode !== 0).toBe(true);
  expect(result.signal === "SIGTERM" || result.signal === "SIGKILL").toBe(true);
  // Bound: must not hang anywhere near the suite default 60s.
  expect(elapsed).toBeLessThan(10_000);
});

test("SIGTERM-ignoring child is escalated to SIGKILL", async () => {
  // red-proof: escalateKill sends only SIGTERM and never SIGKILL after grace
  const result = await superviseChild({
    command: [
      "bun",
      "-e",
      `
process.on("SIGTERM", () => {});
setInterval(() => {}, 1_000_000);
`,
    ],
    timeoutMs: 300,
    killGraceMs: 200,
  });

  expect(result.timedOut).toBe(true);
  expect(result.signal).toBe("SIGKILL");
  expect(result.exitCode).toBeNull();
});

test("ManagedProcess surfaces ready and exited as separate awaits", async () => {
  // red-proof: make ready() resolve only after awaiting exited and require exitCode===0 inside ready()
  const port = freePort();
  const script = writeTempScript(
    "managed-server.ts",
    `
const port = Number(process.env.PORT);
Bun.serve({
  hostname: "127.0.0.1",
  port,
  fetch: () => new Response("ok"),
});
// Stay alive until supervisor stops us.
await new Promise(() => {});
`,
  );

  const proc = ManagedProcess.start({
    command: ["bun", "run", script],
    env: { ...process.env, PORT: String(port) },
    readyUrl: `http://127.0.0.1:${port}/`,
    readyTimeoutMs: 10_000,
    killGraceMs: 500,
  });

  try {
    await proc.ready();
    // Still running after ready — exit is a distinct future.
    const raced = await Promise.race([
      proc.exited.then(() => "exited"),
      new Promise<"alive">((r) => setTimeout(() => r("alive"), 100)),
    ]);
    expect(raced).toBe("alive");
  } finally {
    await proc.stop();
  }

  const status = await proc.exited;
  // Stopped by signal, not a clean zero exit from the script itself.
  expect(status.exitCode === null || status.exitCode !== 0).toBe(true);
  expect(status.signal === "SIGTERM" || status.signal === "SIGKILL").toBe(true);

  // stop() is idempotent
  await proc.stop();
  await proc.stop();
});

test("superviseChild propagates zero exit and captured stdout", async () => {
  // red-proof: replace stdout capture with a constant empty string regardless of child output
  const result = await superviseChild({
    command: ["bun", "-e", "process.stdout.write('acceptance-token-7f3a');"],
    timeoutMs: 5_000,
  });
  expect(result.exitCode).toBe(0);
  expect(result.timedOut).toBe(false);
  expect(result.stdout).toContain("acceptance-token-7f3a");
});
