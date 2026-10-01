import { describe, expect, test } from "bun:test";
import { main, sanitizeDisplayUrl, verifyReady } from "../scripts/verify-ready";

function startServer(
  handler: (request: Request) => Response | Promise<Response>
) {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) =>
    handler(new Request(input, init))) as typeof fetch;
  return {
    server: { stop: async () => (globalThis.fetch = originalFetch) },
    url: "https://ready.test/ready",
  };
}

const readyEnvelope = (environment: string) =>
  new Response(
    JSON.stringify({
      status: "ready",
      environment,
      observability_sink_mode: "cloudflare_only",
    }),
    {
      status: 200,
      headers: {
        "content-type": "application/json",
        "cache-control": "no-store",
      },
    }
  );

describe("sanitizeDisplayUrl", () => {
  test("redacts a valid endpoint", () => {
    expect(
      sanitizeDisplayUrl("https://user:pass@example.com/ready?secret=1#frag")
    ).toBe("[endpoint]");
  });

  test("returns placeholder for invalid url", () => {
    expect(sanitizeDisplayUrl("not a url")).toBe("[invalid]");
  });
});

describe("verifyReady", () => {
  test("accepts a valid /ready envelope", async () => {
    const { server, url } = startServer(() => readyEnvelope("staging"));
    try {
      const result = await verifyReady(url);
      expect(result).toEqual({
        kind: "ready",
        environment: "staging",
        sinkMode: "cloudflare_only",
      });
    } finally {
      await await server.stop();
    }
  });

  test("rejects a 503 not-ready response", async () => {
    const { server, url } = startServer(
      () =>
        new Response(
          JSON.stringify({
            error: {
              code: "service_unavailable",
              retryable: true,
              action: "retry",
            },
          }),
          {
            status: 503,
            headers: {
              "content-type": "application/json",
              "cache-control": "no-store",
            },
          }
        )
    );
    try {
      const result = await verifyReady(url);
      expect(result).toEqual({
        kind: "error",
        reason: expect.stringContaining("503"),
      });
    } finally {
      await await server.stop();
    }
  });

  test("rejects a non-json response", async () => {
    const { server, url } = startServer(
      () =>
        new Response("not json", {
          status: 200,
          headers: {
            "content-type": "text/plain",
            "cache-control": "no-store",
          },
        })
    );
    try {
      const result = await verifyReady(url);
      expect(result.kind).toBe("error");
    } finally {
      await await server.stop();
    }
  });

  test("rejects a missing status field", async () => {
    const { server, url } = startServer(
      () =>
        new Response(JSON.stringify({ environment: "staging" }), {
          status: 200,
          headers: {
            "content-type": "application/json",
            "cache-control": "no-store",
          },
        })
    );
    try {
      const result = await verifyReady(url);
      expect(result.kind).toBe("error");
    } finally {
      await await server.stop();
    }
  });

  test("rejects a wrong status value", async () => {
    const { server, url } = startServer(
      () =>
        new Response(JSON.stringify({ status: "ok", environment: "staging" }), {
          status: 200,
          headers: {
            "content-type": "application/json",
            "cache-control": "no-store",
          },
        })
    );
    try {
      const result = await verifyReady(url);
      expect(result.kind).toBe("error");
    } finally {
      await await server.stop();
    }
  });

  test("rejects a missing or empty environment", async () => {
    const { server, url } = startServer(
      () =>
        new Response(JSON.stringify({ status: "ready" }), {
          status: 200,
          headers: {
            "content-type": "application/json",
            "cache-control": "no-store",
          },
        })
    );
    try {
      const result = await verifyReady(url);
      expect(result.kind).toBe("error");
    } finally {
      await await server.stop();
    }
  });

  test("rejects a missing observability sink mode", async () => {
    const { server, url } = startServer(
      () =>
        new Response(
          JSON.stringify({ status: "ready", environment: "staging" }),
          {
            status: 200,
            headers: {
              "content-type": "application/json",
              "cache-control": "no-store",
            },
          }
        )
    );
    try {
      const result = await verifyReady(url);
      expect(result.kind).toBe("error");
    } finally {
      await server.stop();
    }
  });

  test("rejects a non-200 success status", async () => {
    const { server, url } = startServer(
      () =>
        new Response(
          JSON.stringify({ status: "ready", environment: "staging" }),
          {
            status: 201,
            headers: {
              "content-type": "application/json",
              "cache-control": "no-store",
            },
          }
        )
    );
    try {
      const result = await verifyReady(url);
      expect(result.kind).toBe("error");
    } finally {
      await await server.stop();
    }
  });

  test("rejects a missing no-store cache control", async () => {
    const { server, url } = startServer(
      () =>
        new Response(
          JSON.stringify({ status: "ready", environment: "staging" }),
          {
            status: 200,
            headers: { "content-type": "application/json" },
          }
        )
    );
    try {
      const result = await verifyReady(url);
      expect(result.kind).toBe("error");
    } finally {
      await await server.stop();
    }
  });

  test("rejects a network failure", async () => {
    const result = await verifyReady("http://127.0.0.1:1/ready");
    expect(result.kind).toBe("error");
  });
});

describe("main", () => {
  test("returns 0 for a ready endpoint without logging credentials", async () => {
    const { server, url } = startServer(() => readyEnvelope("ci"));
    const logs: unknown[] = [];
    const originalLog = console.log;
    console.log = (...args: unknown[]) => logs.push(args);
    try {
      const code = await main([url]);
      expect(code).toBe(0);
      expect(logs.length).toBeGreaterThan(0);
      expect(JSON.stringify(logs)).not.toContain("user:pass");
    } finally {
      console.log = originalLog;
      await server.stop();
    }
  });

  test("returns 1 for a missing url argument", async () => {
    const errors: unknown[] = [];
    const originalError = console.error;
    console.error = (...args: unknown[]) => errors.push(args);
    try {
      const code = await main([]);
      expect(code).toBe(1);
    } finally {
      console.error = originalError;
    }
  });

  test("logs no credentials when the endpoint fails", async () => {
    const errors: unknown[] = [];
    const originalError = console.error;
    console.error = (...args: unknown[]) => errors.push(args);
    try {
      const code = await main(["https://user:pass@127.0.0.1:1/ready"]);
      expect(code).toBe(1);
      expect(JSON.stringify(errors)).not.toContain("user:pass");
    } finally {
      console.error = originalError;
    }
  });
});
