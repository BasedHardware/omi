import { describe, expect, test } from "bun:test";

import { createServedCounter } from "./observability/served-count";
import { createMemoryServiceApp } from "./memory-service-app";
import { defineMemoryRouteReadPort } from "./routes/memory-read-port";

describe("canonical memory service composition", () => {
  test("passes HTTP disconnect cancellation through the canonical memory route", async () => {
    const controller = new AbortController();
    let signal: AbortSignal | undefined;
    const app = createMemoryServiceApp(() => new Response(null, { status: 503 }), {
      readPort: defineMemoryRouteReadPort(async () => true, async (input) => {
        signal = input.signal;
        return { kind: "unavailable" };
      }),
      nowEpochSeconds: () => 123,
      counter: createServedCounter(),
    });
    await app.fetch(new Request("https://service.example/v1/memories", { headers: { authorization: "Bearer token" }, signal: controller.signal }));
    controller.abort();
    expect(signal?.aborted).toBe(true);
  });
  test("serves the existing REST route and delegates MCP from one Hono root", async () => {
    const counter = createServedCounter();
    const app = createMemoryServiceApp(
      () => new Response("mcp-ok", { status: 202 }),
      {
        readPort: defineMemoryRouteReadPort(
          async () => true,
          async () => ({ kind: "invalid_cursor" }),
        ),
        nowEpochSeconds: () => 123,
        counter,
      },
    );

    const rest = await app.request("/v1/memories", {
      headers: { authorization: "Bearer token" },
    });
    expect(rest.status).toBe(400);
    expect(await rest.text()).toBe('{"error":"bad_request"}');
    expect(counter.snapshot().domainReadsDenied).toBe(1);

    const mcp = await app.request("/mcp", { method: "POST" });
    expect(mcp.status).toBe(202);
    expect(await mcp.text()).toBe("mcp-ok");

    const query = await app.request("/v1/memories/query?question=hello", {
      headers: { authorization: "Bearer token" },
    });
    expect(query.status).toBe(404);
    expect(await query.text()).toBe('{"error":"not_found"}');
    const listedWithQ = await app.request("/v1/memories?q=hello", {
      headers: { authorization: "Bearer token" },
    });
    expect(listedWithQ.status).toBe(400);
    expect(await listedWithQ.text()).toBe('{"error":"bad_request"}');
  });

  test("fails closed on invalid clock and malformed loaded bytes", async () => {
    for (const [now, outcome] of [
      [() => Number.NaN, { kind: "invalid_cursor" }],
      [() => { throw new Error("clock secret"); }, { kind: "invalid_cursor" }],
      [() => 123, { kind: "loaded", canonical_json: '{"raw":"secret"}' }],
    ] as const) {
      const counter = createServedCounter();
      const app = createMemoryServiceApp(
        () => new Response(null, { status: 204 }),
        {
          readPort: defineMemoryRouteReadPort(async () => true, async () => outcome),
          nowEpochSeconds: now,
          counter,
        },
      );
      const response = await app.request("/v1/memories", {
        headers: { authorization: "Bearer token" },
      });
      expect(response.status).toBe(500);
      expect(await response.text()).toBe('{"error":"internal_server_error"}');
      expect(counter.snapshot()).toMatchObject({
        domainReadsServed: 0,
        domainReadsFailed: 1,
      });
    }
  });

  test("never invokes hostile outcome or dependency accessors", async () => {
    for (const hostile of [
      new Proxy({ kind: "loaded", canonical_json: "secret" }, {
        get() { throw new Error("proxy outcome must not be inspected"); },
      }),
      Object.defineProperty({}, "kind", {
        enumerable: true,
        get() { throw new Error("outcome accessor must not run"); },
      }),
    ]) {
      const counter = createServedCounter();
      const app = createMemoryServiceApp(
        () => new Response(null, { status: 204 }),
        {
          readPort: defineMemoryRouteReadPort(async () => true, async () => hostile as never),
          nowEpochSeconds: () => 123,
          counter,
        },
      );
      const response = await app.request("/v1/memories", {
        headers: { authorization: "Bearer token" },
      });
      expect(response.status).toBe(500);
      expect(await response.text()).toBe('{"error":"internal_server_error"}');
    }

    let dependencyGetterCalls = 0;
    const dependencies = Object.defineProperty({
      readPort: defineMemoryRouteReadPort(
        async () => true,
        async () => ({ kind: "unavailable" }),
      ),
      counter: createServedCounter(),
    }, "nowEpochSeconds", {
      enumerable: true,
      get() { dependencyGetterCalls += 1; return () => 123; },
    });
    expect(() => createMemoryServiceApp(
      () => new Response(null, { status: 204 }),
      dependencies as never,
    )).toThrow("invalid memory route dependencies");
    expect(dependencyGetterCalls).toBe(0);
  });
});

test("device upload routes preserve original body and cancellation through the canonical shell", async () => {
  const controller = new AbortController();
  let seenBody = "", seenSignal: AbortSignal | undefined;
  const app = createMemoryServiceApp(() => new Response(null, { status: 503 }), {
    readPort: defineMemoryRouteReadPort(async () => false, async () => ({ kind: "unavailable" })),
    nowEpochSeconds: () => 100, counter: createServedCounter(),
  }, {}, undefined, { async fetch(request) {
    seenBody = await request.text(); seenSignal = request.signal;
    return Response.json({ error: { code: "forbidden" } }, { status: 403 });
  } });
  const raw = ' { "chunkIndex":0, "bytesBase64":"AQ==" } ';
  const response = await app.fetch(new Request("https://service.example/v1/device-sessions/ad99598c-36a8-4e12-a428-63d0a3e06170/audio", {
    method: "POST", body: raw, signal: controller.signal,
  }));
  expect(response.status).toBe(403);
  expect(seenBody).toBe(raw);
  controller.abort();
  expect(seenSignal?.aborted).toBe(true);
  expect((await app.request("/v1/device-sessions/ad99598c-36a8-4e12-a428-63d0a3e06170/transcript")).status).toBe(403);
  expect((await app.request("/v1/device-sessions/ad99598c-36a8-4e12-a428-63d0a3e06170/transcribe", { method: "POST" })).status).toBe(403);
  expect((await app.request("/v1/device-sessions/ad99598c-36a8-4e12-a428-63d0a3e06170/download")).status).toBe(404);
});
