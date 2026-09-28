import { beforeAll, describe, expect, mock, test } from "bun:test";

import { createD1Mock } from "./d1-mock";

let handler: typeof import("../src/index")["default"];
let glance: typeof import("../src/desktop-glance");

beforeAll(async () => {
  void mock.module("cloudflare:workers", () => ({
    DurableObject: class {},
  }));
  const worker = await import("../src/index");
  handler = worker.default;
  glance = await import("../src/desktop-glance");
});

const env = {
  ENVIRONMENT: "test",
  API_TOKEN: "test-token",
  STAGING_ACCOUNT_ID: "test-account",
  ACCOUNTS: {
    getByName: (_name: string) => {
      throw new Error("glance must not resolve accounts");
    },
  },
  AI_MODEL: "test-model",
  AI: { run: async () => ({ response: "test response" }) },
  STAGING_DISPLAY_NAME: "Test Account",
  STAGING_EMAIL: "test@example.invalid",
  STAGING_PLAN_LABEL: "Metered",
  STAGING_CHAT_LIMIT: 1,
  OBSERVABILITY_SINK_MODE: "cloudflare_only",
  OPENROUTER_GATEWAY_ENABLED: "false",
  OPENROUTER_MODEL: "openai/gpt-5.6-luna",
  get DB() {
    return d1Mock;
  },
};

const d1Mock = createD1Mock();

const executionContext = {
  waitUntil: (_promise: Promise<unknown>) => undefined,
  passThroughOnException: () => undefined,
  props: {},
};

const fetchWorker = (
  path: string,
  init?: RequestInit,
  withEnv: unknown = env
) =>
  handler.fetch(
    new Request(`https://worker.test${path}`, init),
    withEnv as never,
    executionContext as never
  );

const authenticatedHeaders = {
  authorization: "Bearer test-token",
  "x-omi-client-id": "test-account",
};

// The glance endpoint now fetches public HN front-page headlines on every
// call, so every test that reaches the handler must serve (or fail) that
// request without touching the real network.
const withMockedFetch = async (
  fetchMock: (
    input: RequestInfo | URL,
    init?: RequestInit
  ) => Response | Promise<Response>,
  run: (requestedUrls: string[]) => Promise<void>
) => {
  const originalFetch = globalThis.fetch;
  const requestedUrls: string[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    requestedUrls.push(url);
    return fetchMock(input, init);
  }) as typeof fetch;
  try {
    await run(requestedUrls);
  } finally {
    globalThis.fetch = originalFetch;
  }
};

const hnResponse = (hits: unknown[]) => new Response(JSON.stringify({ hits }));

describe("POST /v1/desktop/glance", () => {
  test("refuses an anonymous caller with 401", async () => {
    const response = await fetchWorker("/v1/desktop/glance", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: "{}",
    });
    expect(response.status).toBe(401);
    expect((await response.json()) as Record<string, unknown>).toEqual({
      error: {
        code: "unauthorized",
        retryable: false,
        action: "reauthenticate",
      },
    });
  });

  test("returns a local glance without gateway configuration", async () => {
    await withMockedFetch(
      (input) =>
        String(input).startsWith("https://hn.algolia.com/")
          ? hnResponse([{ title: "A front-page story" }])
          : Promise.reject(new Error("unexpected fetch")),
      async (requestedUrls) => {
        const response = await fetchWorker("/v1/desktop/glance", {
          method: "POST",
          headers: {
            ...authenticatedHeaders,
            "content-type": "application/json",
          },
          body: JSON.stringify({
            frontApp: "Safari",
            windowTitle: "GitHub — PR #12",
          }),
        });
        expect(response.status).toBe(200);
        expect(response.headers.get("cache-control")).toBe("no-store");
        const body = (await response.json()) as Record<string, unknown>;
        expect(body["source"]).toBe("local");
        expect(String(body["title"]).length).toBeLessThanOrEqual(24);
        expect(String(body["title"])).toContain("Safari");
        expect(String(body["copy"]).length).toBeLessThanOrEqual(140);
        // Headline enrichment is keyless and carries nothing user-specific.
        expect(
          requestedUrls.some((url) => url.startsWith("https://hn.algolia.com/"))
        ).toBe(true);
      }
    );
  });

  test("falls back to a rotated fun fact with an empty context", async () => {
    await withMockedFetch(
      () => Promise.reject(new Error("offline")),
      async (requestedUrls) => {
        const response = await fetchWorker("/v1/desktop/glance", {
          method: "POST",
          headers: {
            ...authenticatedHeaders,
            "content-type": "application/json",
          },
          body: "{}",
        });
        expect(response.status).toBe(200);
        const body = (await response.json()) as {
          title: string;
          copy: string;
          source: string;
        };
        expect(body.source).toBe("local");
        expect(body.title.length).toBeGreaterThan(0);
        expect(body.copy.length).toBeGreaterThan(0);
        // Filler is gone: the empty-context line is a real fact, one sentence.
        expect(body.copy.endsWith(".")).toBe(true);
        expect([
          "Nothing urgent",
          "All clear",
          "Quiet now",
          "Steady",
        ]).not.toContain(body.title);
        // Even a failed headline fetch must never break the fallback.
        expect(
          requestedUrls.some((url) => url.startsWith("https://hn.algolia.com/"))
        ).toBe(true);
      }
    );
  });

  test("enriches with mocked Open-Meteo weather and mentions condition and temperature", async () => {
    await withMockedFetch(
      (input) => {
        const url = String(input);
        if (url.startsWith("https://api.open-meteo.com/")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                current: { temperature_2m: 18.4, weather_code: 61 },
              })
            )
          );
        }
        if (url.startsWith("https://hn.algolia.com/")) {
          return Promise.resolve(hnResponse([{ title: "A story" }]));
        }
        return Promise.reject(new Error(`unexpected fetch: ${url}`));
      },
      async (requestedUrls) => {
        const cfRequest = new Request("https://worker.test/v1/desktop/glance", {
          method: "POST",
          headers: {
            ...authenticatedHeaders,
            "content-type": "application/json",
          },
          body: JSON.stringify({ localTimeIso: "2026-09-27T10:30:00+07:00" }),
        });
        (cfRequest as Request & { cf?: unknown }).cf = {
          latitude: 13.75,
          longitude: 100.5,
        };
        const response = handler.fetch(
          cfRequest,
          env as never,
          executionContext as never
        );
        expect((await response).status).toBe(200);
        const body = (await (await response).json()) as {
          title: string;
          copy: string;
          source: string;
        };
        expect(requestedUrls[0]).toContain("api.open-meteo.com");
        expect(requestedUrls[0]).toContain(
          "current=temperature_2m,weather_code"
        );
        expect(
          requestedUrls.some((url) => url.includes("tags=front_page"))
        ).toBe(true);
        expect(requestedUrls.some((url) => url.includes("hitsPerPage=6"))).toBe(
          true
        );
        expect(body.source).toBe("local");
        expect(body.copy).toContain("rain");
        expect(body.copy).toContain("18");
      }
    );
  });

  test("clamps and sanitizes topics", () => {
    const long = "y".repeat(90);
    const parsed = glance.parseGlanceInput({
      topics: ["Rust lifetimes", long, 42, null, "   ", "Sourdough"],
    });
    expect(parsed.topics).toEqual([
      "Rust lifetimes",
      "y".repeat(80),
      "Sourdough",
    ]);
    const tooMany = glance.parseGlanceInput({
      topics: Array.from({ length: 10 }, (_unused, index) => `topic ${index}`),
    });
    expect(tooMany.topics.length).toBe(8);
    expect(glance.parseGlanceInput({ topics: "not-a-list" }).topics).toEqual(
      []
    );
    expect(glance.parseGlanceInput({}).topics).toEqual([]);
  });

  test("parses front-page hits into clamped titles", () => {
    const long = "x".repeat(200);
    expect(
      glance.parseGlanceHeadlines({
        hits: [
          { title: "Real story" },
          { title: 42 },
          { title: "   " },
          { noTitle: true },
          null,
          { title: long },
        ],
      })
    ).toEqual(["Real story", "x".repeat(120)]);
    const eight = Array.from({ length: 8 }, (_unused, index) => ({
      title: `Story ${index + 1}`,
    }));
    expect(glance.parseGlanceHeadlines({ hits: eight })).toEqual(
      Array.from({ length: 6 }, (_unused, index) => `Story ${index + 1}`)
    );
    expect(glance.parseGlanceHeadlines({ hits: "nope" })).toEqual([]);
    expect(glance.parseGlanceHeadlines(null)).toEqual([]);
  });

  test("headline enrichment fails safe", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = (async (
      _input: RequestInfo | URL,
      _init?: RequestInit
    ) => {
      throw new Error("offline");
    }) as unknown as typeof fetch;
    try {
      expect(await glance.fetchGlanceHeadlines()).toEqual([]);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  test("rejects a malformed JSON body with a 400-class error", async () => {
    const response = await fetchWorker("/v1/desktop/glance", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: "{not json",
    });
    expect(response.status).toBe(400);
    expect((await response.json()) as Record<string, unknown>).toEqual({
      error: { code: "bad_request", retryable: false, action: "edit_request" },
    });
  });
});
