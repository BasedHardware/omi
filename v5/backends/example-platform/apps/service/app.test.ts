import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";

import { createServiceApp, type StandardFetchHandler } from "./app";
import { createOperationalTelemetryEmitter } from "../../core/observability/operational-telemetry";

describe("canonical service shell", () => {
  test("exposes content-safe health and readiness only at their exact routes", async () => {
    let mcpCalls = 0;
    const app = createServiceApp(() => {
      mcpCalls += 1;
      return new Response(null, { status: 204 });
    });

    const health = await app.request("/health");
    expect(health.status).toBe(200);
    expect(health.headers.get("cache-control")).toBe("no-store");
    expect(health.headers.get("content-type")).toBe("application/json");
    expect(await health.json()).toEqual({ status: "ok" });

    const ready = await app.request("/ready");
    expect(ready.status).toBe(200);
    expect(ready.headers.get("cache-control")).toBe("no-store");
    expect(ready.headers.get("content-type")).toBe("application/json");
    expect(await ready.json()).toEqual({ status: "ready" });

    for (const path of ["/health/", "/ready/", "/health/details", "/readiness"]) {
      const response = await app.request(path);
      expect(response.status).toBe(404);
      expect(await response.json()).toEqual({ error: "not_found" });
    }

    for (const path of ["/health", "/ready"]) {
      const response = await app.request(path, { method: "POST" });
      expect(response.status).toBe(404);
      expect(await response.json()).toEqual({ error: "not_found" });
    }

    expect(mcpCalls).toBe(0);
  });

  test("forwards the exact MCP Request with its method, URL, headers, and body", async () => {
    const observations: Array<{
      readonly request: Request;
      readonly method: string;
      readonly url: string;
      readonly authorization: string | null;
      readonly contentType: string | null;
      readonly trace: string | null;
      readonly body: string;
    }> = [];
    const responseBody = new Uint8Array([0, 1, 2, 253, 254, 255]);
    const delegatedResponse = new Response(responseBody, {
      status: 207,
      statusText: "Multi-Status",
      headers: {
        "content-type": "application/octet-stream",
        "mcp-protocol-version": "test-version",
        "x-response-fidelity": "preserved",
      },
    });
    const handler: StandardFetchHandler = async (request) => {
      observations.push({
        request,
        method: request.method,
        url: request.url,
        authorization: request.headers.get("authorization"),
        contentType: request.headers.get("content-type"),
        trace: request.headers.get("x-request-trace"),
        body: await request.text(),
      });
      return delegatedResponse;
    };
    const app = createServiceApp(handler);
    const request = new Request("https://service.invalid/mcp?transport=streamable-http", {
      method: "POST",
      headers: {
        authorization: "Bearer opaque-test-credential",
        "content-type": "application/json",
        "x-request-trace": "opaque-test-trace",
      },
      body: '{"jsonrpc":"2.0","id":"request-1"}',
    });

    const response = await app.request(request);

    expect(observations).toEqual([{
      request,
      method: "POST",
      url: "https://service.invalid/mcp?transport=streamable-http",
      authorization: "Bearer opaque-test-credential",
      contentType: "application/json",
      trace: "opaque-test-trace",
      body: '{"jsonrpc":"2.0","id":"request-1"}',
    }]);
    expect(response).toBe(delegatedResponse);
    expect(response.status).toBe(207);
    expect(response.statusText).toBe("Multi-Status");
    expect(response.headers.get("content-type")).toBe("application/octet-stream");
    expect(response.headers.get("mcp-protocol-version")).toBe("test-version");
    expect(response.headers.get("x-response-fidelity")).toBe("preserved");
    expect(new Uint8Array(await response.arrayBuffer())).toEqual(responseBody);
  });

  for (const method of ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"] as const) {
    test(`delegates ${method} /mcp without imposing transport policy`, async () => {
      const seenMethods: string[] = [];
      const app = createServiceApp((request) => {
        seenMethods.push(request.method);
        return new Response(request.method, {
          status: 202,
          headers: { "x-delegated-method": request.method },
        });
      });

      const response = await app.request("/mcp", { method });

      expect(response.status).toBe(202);
      expect(response.headers.get("x-delegated-method")).toBe(method);
      expect(await response.text()).toBe(method);
      expect(seenMethods).toEqual([method]);
    });
  }

  test("preserves a delegated bodyless error response", async () => {
    const delegatedResponse = new Response(null, {
      status: 405,
      statusText: "Method Not Allowed",
      headers: {
        allow: "POST",
        "mcp-protocol-version": "test-version",
        "x-response-fidelity": "bodyless",
      },
    });
    const app = createServiceApp(() => delegatedResponse);

    const response = await app.request("/mcp", { method: "GET" });

    expect(response).toBe(delegatedResponse);
    expect(response.status).toBe(405);
    expect(response.statusText).toBe("Method Not Allowed");
    expect(response.headers.get("allow")).toBe("POST");
    expect(response.headers.get("mcp-protocol-version")).toBe("test-version");
    expect(response.headers.get("x-response-fidelity")).toBe("bodyless");
    expect(response.body).toBeNull();
    expect(await response.text()).toBe("");
  });

  test("preserves bodyless HEAD semantics while forwarding the original method", async () => {
    const seenMethods: string[] = [];
    const app = createServiceApp((request) => {
      seenMethods.push(request.method);
      return new Response(null, {
        status: 405,
        headers: { allow: "POST", "x-delegated-method": request.method },
      });
    });

    const response = await app.request("/mcp", { method: "HEAD" });

    expect(seenMethods).toEqual(["HEAD"]);
    expect(response.status).toBe(405);
    expect(response.headers.get("allow")).toBe("POST");
    expect(response.headers.get("x-delegated-method")).toBe("HEAD");
    expect(response.body).toBeNull();
    expect(await response.text()).toBe("");
  });

  test("does not delegate near-match or unknown routes and does not reflect their content", async () => {
    let mcpCalls = 0;
    const app = createServiceApp(() => {
      mcpCalls += 1;
      return new Response("unexpected");
    });

    for (const path of ["/mcp/", "/mcp/child", "/mcpish", "/unknown-secret?token=secret-value"]) {
      const response = await app.request(path, { method: "POST" });
      const body = await response.text();
      expect(response.status).toBe(404);
      expect(response.headers.get("cache-control")).toBe("no-store");
      expect(response.headers.get("content-type")).toBe("application/json");
      expect(body).toBe('{"error":"not_found"}');
      expect(body).not.toContain("secret");
    }

    expect(mcpCalls).toBe(0);
  });

  test("fails closed without reflecting Error details from the injected handler", async () => {
    const app = createServiceApp(() => {
      throw new Error("opaque-secret-from-error");
    });

    const response = await app.request("/mcp", { method: "POST" });
    const body = await response.text();

    expect(response.status).toBe(500);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(response.headers.get("content-type")).toBe("application/json");
    expect(body).toBe('{"error":"internal_server_error"}');
    expect(body).not.toContain("opaque-secret-from-error");
  });

  test("fails closed without rethrowing or reflecting non-Error rejections", async () => {
    const app = createServiceApp(async () => Promise.reject("opaque-secret-from-rejection"));

    const response = await app.request("/mcp", { method: "POST" });
    const body = await response.text();

    expect(response.status).toBe(500);
    expect(body).toBe('{"error":"internal_server_error"}');
    expect(body).not.toContain("opaque-secret-from-rejection");
  });

  test("emits content-safe service telemetry only after each response exists", async () => {
    const events: unknown[] = [];
    const ticks = [100, 105, 200, 209, 300, 304];
    const telemetry = createOperationalTelemetryEmitter((event) => { events.push(event); });
    const app = createServiceApp(
      () => new Response(null, { status: 503 }),
      { telemetry, nowMilliseconds: () => ticks.shift() ?? 0 },
    );

    expect((await app.request("/health")).status).toBe(200);
    expect((await app.request("/mcp", { method: "POST" })).status).toBe(503);
    expect((await app.request("/secret-path?token=do-not-record")).status).toBe(404);

    expect(events).toEqual([
      {
        version: "operational-telemetry-v1", family: "service", operation: "health",
        outcome: "success", status_class: "2xx", duration_ms: 5, in_flight: 1,
      },
      {
        version: "operational-telemetry-v1", family: "service", operation: "mcp",
        outcome: "unavailable", status_class: "5xx", duration_ms: 9, in_flight: 1,
      },
      {
        version: "operational-telemetry-v1", family: "service", operation: "other",
        outcome: "invalid", status_class: "4xx", duration_ms: 4, in_flight: 1,
      },
    ]);
    expect(JSON.stringify(events)).not.toContain("secret-path");
    expect(JSON.stringify(events)).not.toContain("do-not-record");
  });

  test("telemetry and clock failures cannot change service responses", async () => {
    const telemetry = createOperationalTelemetryEmitter(() => { throw new Error("sink secret"); });
    const app = createServiceApp(
      () => new Response("delegated", { status: 202 }),
      { telemetry, nowMilliseconds: () => { throw new Error("clock secret"); } },
    );

    const response = await app.request("/mcp", { method: "POST" });
    expect(response.status).toBe(202);
    expect(await response.text()).toBe("delegated");
    expect(telemetry.health()).toEqual({
      version: "operational-telemetry-health-v1", emitted: 0, rejected: 0, dropped: 1,
    });
  });

  test("keeps the production shell runtime-neutral and handler-injected", () => {
    const source = readFileSync(new URL("./app.ts", import.meta.url), "utf8");
    const importedModules = [...source.matchAll(/from\s+["']([^"']+)["']/g)]
      .map((match) => match[1]);

    expect(importedModules).toEqual(["hono", "../../core/observability/operational-telemetry"]);
    expect(source).not.toMatch(/\bBun\b/);
    expect(source).not.toMatch(/\b(?:serve|listen)\s*\(/);
  });
});
