import { watch } from "node:fs";
import { spawn as spawnChild } from "node:child_process";
import { mkdtemp, writeFile, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createServer } from "node:http";
import { expect, test } from "bun:test";
import { requestTimeoutMilliseconds, startProductionServer } from "./production-server";

test("transcription has a bounded provider budget while other routes retain their deadline", () => {
  expect(requestTimeoutMilliseconds("POST", "/v1/device-sessions/id/transcribe")).toBe(135000);
  expect(requestTimeoutMilliseconds("GET", "/v1/device-sessions/id/transcribe")).toBe(25000);
  expect(requestTimeoutMilliseconds("POST", "/v1/device-sessions/id/complete")).toBe(25000);
  expect(requestTimeoutMilliseconds("POST", "/v1/device-sessions//transcribe")).toBe(25000);
});

const environment = {
  OMI_TRANSCRIPTION_API_KEY: "test-only", OMI_TRANSCRIPTION_MODEL: "nova-3",
  OMI_ACCOUNT_TIMEZONE: "UTC", OMI_DATABASE_URL: "postgres://test@localhost/test",
  OMI_FIREBASE_PROJECT_ID: "test-project", OMI_APPLICATION_ID: "test-app",
  OMI_DATABASE_GENERATION_DIGEST: "a".repeat(64), OMI_CODEC_KEY_HEX: "b".repeat(64),
  OMI_CURSOR_KEY_HEX: "c".repeat(64), OMI_LLM_GATEWAY_URL: "https://gateway.example",
  OMI_LLM_GATEWAY_SERVICE_TOKEN: "test-only", OMI_MEMORY_RENDER_LANE: "omi:auto:test",
};
type Factories = NonNullable<Parameters<typeof startProductionServer>[1]>;
function resources() {
  const calls: string[] = [];
  const pool: ReturnType<Factories["createPool"]> = {
    async withTransaction() { throw new Error("unexpected database access"); },
    async close() { calls.push("pool.close"); },
  };
  const identity: Awaited<ReturnType<Factories["createIdentity"]>> = {
    adapter: { verification_source: "firebase_production", async verifyIdToken() { throw new Error("unexpected identity verification"); } },
    async close() { calls.push("identity.close"); },
  };
  const runtime: ReturnType<Factories["createRuntime"]> = {
    async fetch() { return new Response("ready"); },
    async start() { calls.push("runtime.start"); return { kind: "ready" }; },
    async stop() { calls.push("runtime.stop"); await pool.close(); return { kind: "stopped", drained: true }; },
    snapshot() { return { version: "production-memory-service-process-v1", phase: "ready", in_flight: 0 }; },
  };
  const factories: Factories = {
    async createIdentity() { calls.push("identity.create"); return identity; },
    createPool() { calls.push("pool.create"); return pool; },
    createRuntime() { calls.push("runtime.create"); return runtime; },
    serve: ((options: Parameters<typeof Bun.serve>[0]) => {
      calls.push("server.create");
      const server = Bun.serve({ ...options, hostname: "127.0.0.1", port: 0 });
      const original = server.stop.bind(server);
      server.stop = ((force?: boolean) => { calls.push("server.stop"); return original(force); }) as typeof server.stop;
      return server;
    }) as typeof Bun.serve,
  };
  return { calls, pool, identity, runtime, factories };
}

test("production startup serves a real request and repeated stop closes each owner once", async () => {
  const fixture = resources();
  const running = await startProductionServer(environment, fixture.factories);
  try { expect(await (await fetch(running.server.url)).text()).toBe("ready"); }
  finally { await Promise.all([running.stop(), running.stop()]); }
  expect(fixture.calls).toEqual(["identity.create", "pool.create", "runtime.create", "server.create", "runtime.start", "runtime.stop", "pool.close", "server.stop", "identity.close"]);
});

test("actual occupied port failure retires constructed runtime and identity", async () => {
  const occupied = createServer((_request, response) => response.end("occupied"));
  await new Promise<void>(resolve => occupied.listen(0, "0.0.0.0", resolve));
  const port = (occupied.address() as { port: number }).port;
  const fixture = resources();
  fixture.factories.serve = Bun.serve;
  try {
    await expect(startProductionServer({ ...environment, PORT: String(port) }, fixture.factories)).rejects.toThrow("production_startup_unavailable");
    expect(fixture.calls).toEqual(["identity.create", "pool.create", "runtime.create", "runtime.stop", "pool.close", "identity.close"]);
    expect(await (await fetch(`http://127.0.0.1:${port}`)).text()).toBe("occupied");
  } finally { await new Promise<void>((resolve, reject) => occupied.close(error => error ? reject(error) : resolve())); }
});

test.each(["identity", "pool", "runtime"] as const)("%s construction failure releases only acquired owners and preserves original cause", async stage => {
  const fixture = resources();
  const failure = new Error(`${stage} construction failed`);
  if (stage === "identity") fixture.factories.createIdentity = async () => { throw failure; };
  if (stage === "pool") fixture.factories.createPool = () => { throw failure; };
  if (stage === "runtime") fixture.factories.createRuntime = () => { throw failure; };
  fixture.identity.close = async () => { fixture.calls.push("identity.close"); throw new Error("cleanup failed"); };
  await expect(startProductionServer(environment, fixture.factories)).rejects.toMatchObject(stage === "identity" ? { cause: failure } : { cause: { errors: [failure, expect.any(AggregateError)] } });
  expect(fixture.calls.filter(value => value.endsWith(".close"))).toEqual(stage === "identity" ? [] : stage === "pool" ? ["identity.close"] : ["pool.close", "identity.close"]);
});

test.each(["failed", "undrained", "throw", "reject"] as const)("runtime %s shutdown still closes server and identity and never reports success", async outcome => {
  const fixture = resources();
  fixture.runtime.stop = () => {
    fixture.calls.push("runtime.stop");
    if (outcome === "throw") throw new Error("sync failure");
    if (outcome === "reject") return Promise.reject(new Error("async failure"));
    return Promise.resolve(outcome === "failed" ? { kind: "failed" } : { kind: "stopped", drained: false });
  };
  const running = await startProductionServer(environment, fixture.factories);
  await expect(running.stop()).rejects.toThrow("production_shutdown_unavailable");
  await expect(running.stop()).rejects.toThrow("production_shutdown_unavailable");
  expect(fixture.calls.slice(-3)).toEqual(["runtime.stop", "server.stop", "identity.close"]);
  expect(fixture.calls).not.toContain("pool.close");
});

test("failed readiness cleans all resources and cleanup failure cannot replace startup cause", async () => {
  const fixture = resources();
  const failure = new Error("readiness failed");
  fixture.runtime.start = async () => { throw failure; };
  fixture.runtime.stop = async () => ({ kind: "failed" });
  await expect(startProductionServer(environment, fixture.factories)).rejects.toMatchObject({ cause: { errors: [failure, expect.any(AggregateError)] } });
  expect(fixture.calls.slice(-2)).toEqual(["server.stop", "identity.close"]);
});

test("server shutdown rejection does not prevent identity cleanup", async () => {
  const fixture = resources();
  const running = await startProductionServer(environment, fixture.factories);
  const original = running.server.stop.bind(running.server);
  running.server.stop = (async () => { await original(true); fixture.calls.push("server.stop.failed"); throw new Error("server shutdown failed"); }) as typeof running.server.stop;
  await expect(running.stop()).rejects.toThrow("production_shutdown_unavailable");
  expect(fixture.calls.slice(-2)).toEqual(["server.stop.failed", "identity.close"]);
});

test("failed pool fallback still closes identity and retains startup and cleanup errors", async () => {
  const fixture = resources();
  const construction = new Error("runtime construction failed");
  const poolFailure = new Error("pool cleanup failed");
  fixture.factories.createRuntime = () => { throw construction; };
  fixture.pool.close = () => { fixture.calls.push("pool.close"); throw poolFailure; };
  await expect(startProductionServer(environment, fixture.factories)).rejects.toMatchObject({
    cause: { errors: [construction, { errors: [poolFailure] }] },
  });
  expect(fixture.calls.slice(-2)).toEqual(["pool.close", "identity.close"]);
});

test("unavailable startup result closes acquired resources without reporting readiness", async () => {
  const fixture = resources();
  fixture.runtime.start = async () => ({ kind: "unavailable" });
  await expect(startProductionServer(environment, fixture.factories)).rejects.toMatchObject({ cause: { message: "database_readiness_unavailable" } });
  expect(fixture.calls.slice(-4)).toEqual(["runtime.stop", "pool.close", "server.stop", "identity.close"]);
});

test("startup cancellation waits for the pending identity and closes it before rejecting", async () => {
  const fixture = resources();
  const controller = new AbortController();
  let release!: (identity: typeof fixture.identity) => void;
  fixture.factories.createIdentity = () => new Promise(resolve => { release = resolve; });
  const pending = startProductionServer(environment, fixture.factories, controller.signal);
  controller.abort(new Error("cancel startup"));
  expect(fixture.calls).toEqual([]);
  release(fixture.identity);
  await expect(pending).rejects.toMatchObject({ cause: controller.signal.reason });
  expect(fixture.calls).toEqual(["identity.close"]);
});

test("already cancelled startup acquires nothing", async () => {
  const fixture = resources();
  const controller = new AbortController(); controller.abort();
  await expect(startProductionServer(environment, fixture.factories, controller.signal)).rejects.toMatchObject({ cause: controller.signal.reason });
  expect(fixture.calls).toEqual([]);
});

test("startup cancellation reaches the real readiness transaction and closes all acquired owners", async () => {
  const fixture = resources();
  const controller = new AbortController();
  let entered!: () => void;
  const waiting = new Promise<void>(resolve => { entered = resolve; });
  fixture.pool.withTransaction = options => new Promise((_resolve, reject) => {
    expect(options.signal).toBe(controller.signal);
    options.signal!.addEventListener("abort", () => reject(options.signal!.reason), { once: true });
    entered();
  });
  const factory = fixture.factories.createRuntime;
  fixture.factories.createRuntime = options => {
    const runtime = factory(options);
    runtime.start = async () => ({ kind: await options.readiness.check() ? "ready" : "unavailable" });
    return runtime;
  };
  const pending = startProductionServer(environment, fixture.factories, controller.signal);
  await waiting;
  controller.abort(new Error("cancel readiness"));
  await expect(pending).rejects.toMatchObject({ cause: controller.signal.reason });
  expect(fixture.calls.slice(-4)).toEqual(["runtime.stop", "pool.close", "server.stop", "identity.close"]);
});

test.each([["SIGTERM", false], ["SIGINT", false], ["SIGTERM", true]] as const)("real %s during identity acquisition waits for cleanup (failure=%s)", async (signal, failCleanup) => {
  const directory = await mkdtemp(join(tmpdir(), "omi-production-signal-"));
  const path = join(directory, "signal.ts");
  const log = join(directory, "events");
  const source = `
import {appendFileSync} from "node:fs";
const record=value=>appendFileSync(${JSON.stringify(log)}, value+"\\n");
import {runProductionServer} from ${JSON.stringify(import.meta.dir + "/production-server.ts")};
const factories={
  createIdentity:()=>new Promise(resolve=>{
    process.once(${JSON.stringify(signal)},()=>resolve({adapter:{verification_source:'firebase_production',verifyIdToken:async()=>{throw Error('unexpected')}},close:async()=>{record('identity.closed');if(${failCleanup})throw Error('cleanup failed')}}));
    record('identity.pending');
  }),
  createPool:()=>{throw Error('pool must not be acquired')},
  createRuntime:()=>{throw Error('runtime must not be acquired')},
  serve:()=>{throw Error('server must not be acquired')},
};
const code=await runProductionServer(${JSON.stringify(environment)},factories);
record('exit.code='+code);
process.exit(code);
`;
  let child: ReturnType<typeof spawnChild> | undefined;
  let watcher: ReturnType<typeof watch> | undefined;
  let timeout: ReturnType<typeof setTimeout> | undefined;
  try {
    await writeFile(path, source);
    const ready = new Promise<void>((resolve, reject) => {
      watcher = watch(directory, () => {
        readFile(log, "utf8").then(text => { if (text.includes("identity.pending")) resolve(); }, () => {});
      });
      watcher.on("error", reject);
    });
    child = spawnChild(process.execPath, [path], { stdio: "ignore" });
    const exited = new Promise<number | null>((resolve, reject) => {
      child!.once("error", reject);
      child!.once("exit", resolve);
    });
    const deadline = new Promise<never>((_resolve, reject) => { timeout = setTimeout(() => reject(new Error("signal fixture deadline exceeded")), 10000); });
    await Promise.race([ready, exited.then(code => { throw new Error(`child exited before readiness: ${code}`); }), deadline]);
    child.kill(signal);
    expect(await Promise.race([exited, deadline])).toBe(failCleanup ? 1 : 0);
    const output = await readFile(log, "utf8");
    expect(output).toContain("identity.closed");
    expect(output).toContain(`exit.code=${failCleanup ? 1 : 0}`);
  } finally {
    if (timeout !== undefined) clearTimeout(timeout);
    watcher?.close();
    if (child && child.exitCode === null && child.signalCode === null) {
      const closed = new Promise<void>(resolve => child!.once("exit", () => resolve()));
      child.kill("SIGKILL");
      await closed;
    }
    await rm(directory, { recursive: true, force: true });
  }
}, 15000);
