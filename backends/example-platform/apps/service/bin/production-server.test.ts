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
