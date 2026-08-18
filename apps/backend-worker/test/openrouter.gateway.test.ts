import { beforeAll, describe, expect, mock, test } from "bun:test";

let handler: typeof import("../src/index")["default"];

beforeAll(async () => {
  void mock.module("cloudflare:workers", () => ({
    DurableObject: class {},
  }));
  const worker = await import("../src/index");
  handler = worker.default;
});

const baseEnv = {
  ENVIRONMENT: "test",
  API_TOKEN: "test-token",
  STAGING_ACCOUNT_ID: "test-account",
  ACCOUNTS: {
    getByName: () => ({
      configure: async () => undefined,
      settings: async () => ({
        identity: { displayName: "Test", email: "test@example.invalid" },
        entitlement: null,
      }),
    }),
  },
  AI_MODEL: "test-model",
  AI: { run: async () => ({ response: "test response" }) },
  STAGING_DISPLAY_NAME: "Test",
  STAGING_EMAIL: "test@example.invalid",
  STAGING_PLAN_LABEL: "Test",
  STAGING_CHAT_LIMIT: 10,
};

const executionContext = {
  waitUntil: (_promise: Promise<unknown>) => undefined,
  passThroughOnException: () => undefined,
  props: {},
};

const fetchWorker = (
  path: string,
  env: Record<string, unknown>,
  init?: RequestInit
) =>
  handler.fetch(
    new Request(`https://worker.test${path}`, init),
    env as never,
    executionContext as never
  );

const authenticatedHeaders = {
  authorization: "Bearer test-token",
  "x-omi-client-id": "test-client",
};

const captureFetch = (respond: (request: Request) => Response) => {
  const calls: Request[] = [];
  const original = globalThis.fetch;
  globalThis.fetch = mock(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = new Request(input, init);
      calls.push(request);
      return respond(request);
    }
  ) as never;
  return {
    calls,
    restore: () => {
      globalThis.fetch = original;
    },
  };
};

const captureLogs = () => {
  const entries: string[] = [];
  const originalError = console.error;
  console.error = mock((...args: unknown[]) => {
    entries.push(args.map((arg) => String(arg)).join(" "));
  }) as never;
  return {
    entries,
    restore: () => {
      console.error = originalError;
    },
  };
};

describe("openrouter gateway request shape", () => {
  test("posts to the gateway URL with bearer secret, correlation header, and bounded body", async () => {
    const { openrouter } = await import("../src/openrouter");
    const fetchMock = captureFetch(
      () =>
        new Response(
          JSON.stringify({ choices: [{ message: { content: "reply" } }] }),
          { status: 200, headers: { "content-type": "application/json" } }
        )
    );
    try {
      const result = await openrouter.generateViaGateway(
        {
          url: "https://gateway.example.invalid/openrouter",
          model: "test-model",
          secret: "test-secret",
        },
        "what is the weather",
        "corr-shape-1"
      );
      expect(result.kind).toBe("ok");
      if (result.kind === "ok") expect(result.text).toBe("reply");
      expect(fetchMock.calls).toHaveLength(1);
      const request = fetchMock.calls[0];
      if (request === undefined) throw new Error("no fetch call captured");
      expect(request.method).toBe("POST");
      expect(request.url).toBe("https://gateway.example.invalid/openrouter");
      expect(request.headers.get("authorization")).toBe("Bearer test-secret");
      expect(request.headers.get("content-type")).toBe("application/json");
      expect(request.headers.get("x-omi-correlation-id")).toBe("corr-shape-1");
      const body = (await request.json()) as Record<string, unknown>;
      expect(body["model"]).toBe("test-model");
      expect(body["max_tokens"]).toBe(768);
      const messages = body["messages"] as unknown[];
      expect(messages).toHaveLength(2);
      expect((messages[0] as Record<string, unknown>)["role"]).toBe("system");
      expect((messages[1] as Record<string, unknown>)["role"]).toBe("user");
      expect((messages[1] as Record<string, unknown>)["content"]).toBe(
        "what is the weather"
      );
    } finally {
      fetchMock.restore();
    }
  });

  test("truncates oversized response text to a bounded length", async () => {
    const { openrouter } = await import("../src/openrouter");
    const longText = "x".repeat(40_000);
    const fetchMock = captureFetch(
      () =>
        new Response(
          JSON.stringify({ choices: [{ message: { content: longText } }] }),
          { status: 200, headers: { "content-type": "application/json" } }
        )
    );
    try {
      const result = await openrouter.generateViaGateway(
        {
          url: "https://gateway.example.invalid/openrouter",
          model: "test-model",
          secret: "test-secret",
        },
        "prompt",
        "corr-trunc-1"
      );
      expect(result.kind).toBe("ok");
      if (result.kind === "ok")
        expect(result.text.length).toBeLessThanOrEqual(32_768);
    } finally {
      fetchMock.restore();
    }
  });
});

describe("openrouter gateway redaction", () => {
  test("HTTP error logs carry correlation and status but never secret, prompt, or URL", async () => {
    const { openrouter } = await import("../src/openrouter");
    const fetchMock = captureFetch(
      () => new Response("upstream error", { status: 502 })
    );
    const logs = captureLogs();
    try {
      const result = await openrouter.generateViaGateway(
        {
          url: "https://gateway.example.invalid/openrouter",
          model: "test-model",
          secret: "leak-me-never",
        },
        "sensitive prompt content",
        "corr-redact-1"
      );
      expect(result.kind).toBe("error");
      const combined = logs.entries.join("\n");
      expect(combined).toContain("corr-redact-1");
      expect(combined).not.toContain("leak-me-never");
      expect(combined).not.toContain("sensitive prompt content");
      expect(combined).not.toContain("gateway.example.invalid");
    } finally {
      fetchMock.restore();
      logs.restore();
    }
  });

  test("fetch exception logs carry correlation but never secret, prompt, or URL", async () => {
    const { openrouter } = await import("../src/openrouter");
    const fetchMock = captureFetch(() => {
      throw new Error("network unreachable");
    });
    const logs = captureLogs();
    try {
      const result = await openrouter.generateViaGateway(
        {
          url: "https://gateway.example.invalid/openrouter",
          model: "test-model",
          secret: "leak-me-never",
        },
        "sensitive prompt content",
        "corr-redact-2"
      );
      expect(result.kind).toBe("error");
      const combined = logs.entries.join("\n");
      expect(combined).toContain("corr-redact-2");
      expect(combined).not.toContain("leak-me-never");
      expect(combined).not.toContain("sensitive prompt content");
      expect(combined).not.toContain("gateway.example.invalid");
    } finally {
      fetchMock.restore();
      logs.restore();
    }
  });

  test("malformed response body yields a bounded error without leaking upstream detail", async () => {
    const { openrouter } = await import("../src/openrouter");
    const fetchMock = captureFetch(
      () => new Response(JSON.stringify({ unexpected: true }), { status: 200 })
    );
    const logs = captureLogs();
    try {
      const result = await openrouter.generateViaGateway(
        {
          url: "https://gateway.example.invalid/openrouter",
          model: "test-model",
          secret: "leak-me-never",
        },
        "sensitive prompt content",
        "corr-redact-3"
      );
      expect(result.kind).toBe("error");
      const combined = logs.entries.join("\n");
      expect(combined).not.toContain("leak-me-never");
      expect(combined).not.toContain("sensitive prompt content");
    } finally {
      fetchMock.restore();
      logs.restore();
    }
  });
});

describe("openrouter gateway fail-closed validation", () => {
  test("gatewayConfig accepts the declared Luna model and rejects missing, unsafe, or drifted configuration", async () => {
    const { openrouter } = await import("../src/openrouter");
    const valid = {
      OPENROUTER_GATEWAY_ENABLED: "true",
      OPENROUTER_GATEWAY_URL: "https://gateway.example.invalid/openrouter",
      OPENROUTER_API_KEY: "secret",
      OPENROUTER_MODEL: openrouter.LUNA_MODEL,
    };
    expect(openrouter.gatewayConfig(valid)).not.toBeNull();
    expect(
      openrouter.gatewayConfig({ ...valid, OPENROUTER_GATEWAY_URL: "" })
    ).toBeNull();
    expect(
      openrouter.gatewayConfig({ ...valid, OPENROUTER_API_KEY: "" })
    ).toBeNull();
    expect(
      openrouter.gatewayConfig({ ...valid, OPENROUTER_MODEL: "" })
    ).toBeNull();
    expect(
      openrouter.gatewayConfig({
        ...valid,
        OPENROUTER_MODEL: "openai/gpt-5.6-luna-experimental",
      })
    ).toBeNull();
    expect(
      openrouter.gatewayConfig({
        ...valid,
        OPENROUTER_GATEWAY_URL: "http://insecure.example.invalid/openrouter",
      })
    ).toBeNull();
    expect(
      openrouter.gatewayConfig({
        ...valid,
        OPENROUTER_GATEWAY_ENABLED: "false",
      })
    ).not.toBeNull();
  });

  test("gatewayReady is false when enabled but config is incomplete", async () => {
    const { openrouter } = await import("../src/openrouter");
    expect(
      openrouter.gatewayReady({
        OPENROUTER_GATEWAY_ENABLED: "true",
        OPENROUTER_GATEWAY_URL: "",
        OPENROUTER_API_KEY: "",
        OPENROUTER_MODEL: "",
      })
    ).toBe(false);
    expect(
      openrouter.gatewayReady({
        OPENROUTER_GATEWAY_ENABLED: "false",
        OPENROUTER_GATEWAY_URL: "https://gateway.example.invalid/openrouter",
        OPENROUTER_API_KEY: "secret",
        OPENROUTER_MODEL: "test-model",
      })
    ).toBe(false);
  });

  test("worker /ready returns 503 when gateway mode is enabled but config is absent", async () => {
    const response = await fetchWorker("/ready", {
      ...baseEnv,
      OPENROUTER_GATEWAY_ENABLED: "true",
      OPENROUTER_GATEWAY_URL: "",
      OPENROUTER_API_KEY: "",
      OPENROUTER_MODEL: "",
    });
    expect(response.status).toBe(503);
    const body = (await response.json()) as Record<string, unknown>;
    const error = body["error"] as Record<string, unknown>;
    expect(error["code"]).toBe("service_unavailable");
  });

  test("worker /v1/* refuses with 401 when gateway mode is enabled but config is absent", async () => {
    const response = await fetchWorker(
      "/v1/settings",
      {
        ...baseEnv,
        OPENROUTER_GATEWAY_ENABLED: "true",
        OPENROUTER_GATEWAY_URL: "",
        OPENROUTER_API_KEY: "",
        OPENROUTER_MODEL: "",
      },
      { headers: authenticatedHeaders }
    );
    expect(response.status).toBe(401);
    const body = (await response.json()) as Record<string, unknown>;
    const error = body["error"] as Record<string, unknown>;
    expect(error["code"]).toBe("unauthorized");
  });

  test("worker /ready stays 200 when gateway mode is disabled even without gateway config", async () => {
    const response = await fetchWorker("/ready", {
      ...baseEnv,
      OPENROUTER_GATEWAY_ENABLED: "false",
    });
    expect(response.status).toBe(200);
  });
});
