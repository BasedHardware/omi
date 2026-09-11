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
  DB: {} as D1Database,
  OBSERVABILITY_SINK_MODE: "cloudflare_only",
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
  "x-omi-client-id": "test-account",
};

const postLive = (env: Record<string, unknown>, body: string) =>
  fetchWorker("/v1/live/sessions", env, {
    method: "POST",
    headers: { ...authenticatedHeaders, "content-type": "application/json" },
    body,
  });

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

const liveResponse = (sessionId = "live_123", sdp = "v=0\r\na=answer\r\n") =>
  new Response(
    JSON.stringify({
      session: { id: sessionId },
      transport: { type: "webrtc", sdp },
    }),
    { status: 201, headers: { "content-type": "application/json" } }
  );

const geminiTokenResponse = (name = "auth_tokens/ephemeral-1") =>
  new Response(JSON.stringify({ name }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });

describe("live session provider request shape", () => {
  test("posts the gpt-live-1 WebRTC session with the api key only on the server", async () => {
    const { live } = await import("../src/live");
    const fetchMock = captureFetch(() => liveResponse());
    try {
      const result = await live.createLiveSession(
        { OPENAI_API_KEY: "test-openai-key" },
        { provider: "gpt_live", sdp: "v=0\r\no=- offer\r\n" },
        "corr-live-1"
      );
      expect(result.kind).toBe("ok");
      if (result.kind === "ok") {
        expect(result.provider).toBe("gpt_live");
        if (result.provider === "gpt_live") {
          expect(result.sessionId).toBe("live_123");
          expect(result.answerSdp).toBe("v=0\r\na=answer\r\n");
        }
      }
      expect(fetchMock.calls).toHaveLength(1);
      const request = fetchMock.calls[0];
      if (request === undefined) throw new Error("no fetch call captured");
      expect(request.method).toBe("POST");
      expect(request.url).toBe(live.LIVE_SESSIONS_URL);
      expect(request.url).toBe("https://api.openai.com/v1/live/sessions");
      expect(request.redirect).toBe("manual");
      expect(request.headers.get("authorization")).toBe(
        "Bearer test-openai-key"
      );
      expect(request.headers.get("content-type")).toBe("application/json");
      expect(request.headers.get("x-omi-correlation-id")).toBe("corr-live-1");
      const body = (await request.json()) as Record<string, unknown>;
      const session = body["session"] as Record<string, unknown>;
      expect(session["model"]).toBe("gpt-live-1");
      expect(typeof session["instructions"]).toBe("string");
      const delegation = session["delegation"] as Record<string, unknown>;
      expect(delegation["type"]).toBe("responses");
      const responses = delegation["responses"] as Record<string, unknown>;
      expect(responses["model"]).toBe("gpt-5.6-terra");
      expect(responses["tool_choice"]).toBe("auto");
      expect(responses["tools"]).toEqual([{ type: "web_search" }]);
      const transport = body["transport"] as Record<string, unknown>;
      expect(transport["type"]).toBe("webrtc");
      expect(transport["sdp"]).toBe("v=0\r\no=- offer\r\n");
    } finally {
      fetchMock.restore();
    }
  });

  test("fails closed and retryable when OPENAI_API_KEY is unset for gpt_live", async () => {
    const { live } = await import("../src/live");
    const fetchMock = captureFetch(() => liveResponse());
    try {
      expect(live.liveConfigured({})).toBe(false);
      expect(live.liveConfigured({ OPENAI_API_KEY: "" })).toBe(false);
      expect(live.liveConfigured({ OPENAI_API_KEY: "key" })).toBe(true);
      const result = await live.createLiveSession(
        {},
        { provider: "gpt_live", sdp: "v=0\r\n" },
        "corr-live-2"
      );
      expect(result).toEqual({
        kind: "error",
        status: 503,
        code: "provider_not_configured",
        retryable: true,
      });
      expect(fetchMock.calls).toHaveLength(0);
    } finally {
      fetchMock.restore();
    }
  });

  test("mints a Gemini ephemeral token without returning the project key", async () => {
    const { live } = await import("../src/live");
    const fetchMock = captureFetch(() =>
      geminiTokenResponse("auth_tokens/secret-token")
    );
    try {
      expect(live.geminiLiveConfigured({})).toBe(false);
      expect(live.geminiLiveConfigured({ GEMINI_API_KEY: "gkey" })).toBe(true);
      const result = await live.createLiveSession(
        { GEMINI_API_KEY: "test-gemini-key" },
        { provider: "gemini_live" },
        "corr-gemini-1"
      );
      expect(result.kind).toBe("ok");
      if (result.kind === "ok" && result.provider === "gemini_live") {
        expect(result.token).toBe("auth_tokens/secret-token");
        expect(result.model).toBe("models/gemini-3.1-flash-live-preview");
        expect(result.url).toBe(live.GEMINI_LIVE_WS_URL);
        expect(result.url).not.toContain("key=");
        expect(typeof result.sessionId).toBe("string");
        expect(result.sessionId.length).toBeGreaterThan(0);
      }
      expect(fetchMock.calls).toHaveLength(1);
      const request = fetchMock.calls[0];
      if (request === undefined) throw new Error("no fetch call captured");
      expect(request.method).toBe("POST");
      expect(request.url.startsWith(live.GEMINI_AUTH_TOKENS_URL)).toBe(true);
      expect(new URL(request.url).searchParams.get("key")).toBe(
        "test-gemini-key"
      );
      expect(request.headers.get("authorization")).toBeNull();
      const body = (await request.json()) as Record<string, unknown>;
      expect(body["uses"]).toBe(1);
      expect(typeof body["expireTime"]).toBe("string");
      expect(typeof body["newSessionExpireTime"]).toBe("string");
    } finally {
      fetchMock.restore();
    }
  });

  test("fails closed when GEMINI_API_KEY is unset for gemini_live", async () => {
    const { live } = await import("../src/live");
    const fetchMock = captureFetch(() => geminiTokenResponse());
    try {
      const result = await live.createLiveSession(
        { OPENAI_API_KEY: "openai-only" },
        { provider: "gemini_live" },
        "corr-gemini-2"
      );
      expect(result).toEqual({
        kind: "error",
        status: 503,
        code: "provider_not_configured",
        retryable: true,
      });
      expect(fetchMock.calls).toHaveLength(0);
    } finally {
      fetchMock.restore();
    }
  });

  test("maps upstream failures and malformed answers to bounded errors", async () => {
    const { live } = await import("../src/live");
    const upstream = captureFetch(() => new Response("nope", { status: 401 }));
    const logs = captureLogs();
    try {
      const result = await live.createLiveSession(
        { OPENAI_API_KEY: "leak-me-never" },
        { provider: "gpt_live", sdp: "v=0\r\nsecret-offer" },
        "corr-live-3"
      );
      expect(result).toEqual({
        kind: "error",
        status: 502,
        code: "provider_error",
        retryable: false,
      });
      const combined = logs.entries.join("\n");
      expect(combined).toContain("corr-live-3");
      expect(combined).not.toContain("leak-me-never");
      expect(combined).not.toContain("secret-offer");
      expect(combined).not.toContain("api.openai.com");
    } finally {
      upstream.restore();
      logs.restore();
    }

    const malformed = captureFetch(
      () => new Response(JSON.stringify({ session: {} }), { status: 201 })
    );
    try {
      const result = await live.createLiveSession(
        { OPENAI_API_KEY: "test-openai-key" },
        { provider: "gpt_live", sdp: "v=0\r\n" },
        "corr-live-4"
      );
      expect(result.kind).toBe("error");
      if (result.kind === "error") {
        expect(result.status).toBe(502);
        expect(result.retryable).toBe(true);
      }
    } finally {
      malformed.restore();
    }
  });

  test("rejects non-webrtc transports and oversized session ids", async () => {
    const { live } = await import("../src/live");
    expect(
      live.parseLiveSessionResponse({
        session: { id: "live_1" },
        transport: { type: "websocket", sdp: "v=0" },
      })
    ).toBeNull();
    expect(
      live.parseLiveSessionResponse({
        session: { id: "x".repeat(300) },
        transport: { type: "webrtc", sdp: "v=0" },
      })
    ).toBeNull();
    expect(live.parseLiveSessionResponse({})).toBeNull();
    expect(live.parseLiveSessionResponse(null)).toBeNull();
    expect(live.parseGeminiAuthToken({})).toBeNull();
    expect(live.parseGeminiAuthToken({ name: "auth_tokens/ok" })).toBe(
      "auth_tokens/ok"
    );
  });

  test("parses provider-aware live session requests", async () => {
    const { live } = await import("../src/live");
    expect(live.parseLiveSessionRequest({ sdp: "v=0\r\n" })).toEqual({
      provider: "gpt_live",
      sdp: "v=0\r\n",
    });
    expect(
      live.parseLiveSessionRequest({ provider: "gpt_live", sdp: "v=0\r\n" })
    ).toEqual({ provider: "gpt_live", sdp: "v=0\r\n" });
    expect(live.parseLiveSessionRequest({ provider: "gemini_live" })).toEqual({
      provider: "gemini_live",
    });
    expect(
      live.parseLiveSessionRequest({ provider: "gemini_live", sdp: "" })
    ).toEqual({
      provider: "gemini_live",
    });
    expect(live.parseLiveSessionRequest({ provider: "nope" })).toBeNull();
    expect(live.parseLiveSessionRequest({ provider: "gpt_live" })).toBeNull();
    expect(live.parseLiveSessionRequest({})).toBeNull();
  });
});

describe("live session route", () => {
  test("requires authentication", async () => {
    const response = await fetchWorker("/v1/live/sessions", baseEnv, {
      method: "POST",
      body: JSON.stringify({ sdp: "v=0\r\n" }),
    });
    expect(response.status).toBe(401);
  });

  test("returns 503 provider_not_configured when the gpt secret is missing", async () => {
    const response = await postLive(
      baseEnv,
      JSON.stringify({ provider: "gpt_live", sdp: "v=0\r\n" })
    );
    expect(response.status).toBe(503);
    const body = (await response.json()) as Record<string, unknown>;
    const error = body["error"] as Record<string, unknown>;
    expect(error["code"]).toBe("provider_not_configured");
    expect(error["retryable"]).toBe(true);
    expect(error["action"]).toBe("retry");
  });

  test("returns 503 provider_not_configured when the gemini secret is missing", async () => {
    const response = await postLive(
      { ...baseEnv, OPENAI_API_KEY: "openai-only" },
      JSON.stringify({ provider: "gemini_live" })
    );
    expect(response.status).toBe(503);
    const body = (await response.json()) as Record<string, unknown>;
    const error = body["error"] as Record<string, unknown>;
    expect(error["code"]).toBe("provider_not_configured");
  });

  test("mints a gpt session and returns the answer sdp", async () => {
    const fetchMock = captureFetch(() => liveResponse("live_route", "answer"));
    try {
      const response = await postLive(
        { ...baseEnv, OPENAI_API_KEY: "test-openai-key" },
        JSON.stringify({ provider: "gpt_live", sdp: "v=0\r\noffer" })
      );
      expect(response.status).toBe(201);
      expect((await response.json()) as unknown).toEqual({
        provider: "gpt_live",
        session: { id: "live_route" },
        transport: { type: "webrtc", sdp: "answer" },
      });
      expect(fetchMock.calls).toHaveLength(1);
    } finally {
      fetchMock.restore();
    }
  });

  test("mints a gemini session and returns the constrained ws transport", async () => {
    const { live } = await import("../src/live");
    const fetchMock = captureFetch(() =>
      geminiTokenResponse("auth_tokens/route-token")
    );
    try {
      const response = await postLive(
        { ...baseEnv, GEMINI_API_KEY: "test-gemini-key" },
        JSON.stringify({ provider: "gemini_live" })
      );
      expect(response.status).toBe(201);
      const body = (await response.json()) as {
        provider: string;
        session: { id: string };
        transport: {
          type: string;
          token: string;
          model: string;
          url: string;
        };
      };
      expect(body.provider).toBe("gemini_live");
      expect(body.transport).toEqual({
        type: "gemini_ws",
        token: "auth_tokens/route-token",
        model: "models/gemini-3.1-flash-live-preview",
        url: live.GEMINI_LIVE_WS_URL,
      });
      expect(body.transport.url).not.toContain("key=");
      expect(typeof body.session.id).toBe("string");
      expect(fetchMock.calls).toHaveLength(1);
    } finally {
      fetchMock.restore();
    }
  });

  test("rejects malformed offers with a validation error", async () => {
    for (const body of [
      JSON.stringify({}),
      JSON.stringify({ sdp: "" }),
      JSON.stringify({ sdp: 42 }),
      JSON.stringify({ provider: "gpt_live" }),
      JSON.stringify({ provider: "gpt_live", sdp: "" }),
      JSON.stringify({ provider: "nope" }),
      JSON.stringify({ sdp: "x".repeat(262_145) }),
      "not json",
    ]) {
      const response = await postLive(
        { ...baseEnv, OPENAI_API_KEY: "test-openai-key" },
        body
      );
      expect([400, 413, 422]).toContain(response.status);
    }
  });
});
