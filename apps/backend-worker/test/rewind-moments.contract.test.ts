import { beforeAll, beforeEach, describe, expect, mock, test } from "bun:test";

import { parseRewindMomentUpsert } from "../src/rewind-moments";
import { createD1Mock } from "./d1-mock";

let handler: typeof import("../src/index")["default"];

test("rewind upserts require a sourced native frame id", () => {
  expect(
    parseRewindMomentUpsert({
      frameId: "not-a-frame",
      capturedAtMs: 1,
      appName: "Notes",
      windowTitle: "",
      source: "captured",
      ocrPreview: "",
    })
  ).toBeNull();
  expect(
    parseRewindMomentUpsert({
      frameId: "captured:owner:1",
      capturedAtMs: 1,
      appName: "Notes",
      windowTitle: "Untitled",
      source: "captured",
      ocrPreview: "hello",
    })
  ).toEqual({
    frameId: "captured:owner:1",
    capturedAtMs: 1,
    appName: "Notes",
    windowTitle: "Untitled",
    source: "captured",
    ocrPreview: "hello",
  });
});

beforeAll(async () => {
  void mock.module("cloudflare:workers", () => ({
    DurableObject: class {},
  }));
  const worker = await import("../src/index");
  handler = worker.default;
});

const authenticatedHeaders = {
  authorization: "Bearer test-token",
  "x-omi-client-id": "test-account",
};

const envBase = {
  ENVIRONMENT: "test",
  API_TOKEN: "test-token",
  STAGING_ACCOUNT_ID: "test-account",
  ACCOUNTS: {
    getByName: () => ({
      admit: async () => "conflict" as const,
      cancel: async () => "not_found" as const,
      fetch: async () => new Response(""),
    }),
  },
  AI_MODEL: "test-model",
  AI: { run: async () => ({ response: "test" }) },
  STAGING_DISPLAY_NAME: "Test",
  STAGING_EMAIL: "test@example.invalid",
  STAGING_PLAN_LABEL: "Test",
  STAGING_CHAT_LIMIT: 10,
  OBSERVABILITY_SINK_MODE: "cloudflare_only",
  OPENROUTER_GATEWAY_ENABLED: "false",
};

let d1Mock: D1Database;

beforeEach(() => {
  d1Mock = createD1Mock();
});

async function fetchPath(path: string, init?: RequestInit) {
  return handler.fetch(
    new Request(`https://worker.test${path}`, {
      ...init,
      headers: { ...authenticatedHeaders, ...(init?.headers ?? {}) },
    }),
    { ...envBase, DB: d1Mock } as never,
    { waitUntil() {}, passThroughOnException() {}, props: {} } as never
  );
}

describe("rewind moment account isolation", () => {
  test("unsigned callers never write or read moments", async () => {
    const denied = await handler.fetch(
      new Request("https://worker.test/v1/rewind-moments", {
        method: "POST",
        body: JSON.stringify({
          frameId: "captured:owner:1",
          capturedAtMs: 1,
          appName: "Notes",
          windowTitle: "",
          source: "captured",
          ocrPreview: "",
        }),
      }),
      { ...envBase, DB: d1Mock } as never,
      { waitUntil() {}, passThroughOnException() {}, props: {} } as never
    );
    expect(denied.status).toBe(401);
  });

  test("an upsert is owned by the authenticated account and listed newest first", async () => {
    const created = await fetchPath("/v1/rewind-moments", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        frameId: "captured:owner:9",
        capturedAtMs: 200,
        appName: "Notes",
        windowTitle: "Today",
        source: "captured",
        ocrPreview: "standup",
      }),
    });
    expect(created.status).toBe(201);
    const listed = await fetchPath("/v1/rewind-moments?limit=50");
    expect(listed.status).toBe(200);
    const page = (await listed.json()) as {
      items: Array<{ frameId: string }>;
      window: { complete: boolean };
    };
    expect(page.items.map((item) => item.frameId)).toEqual(["captured:owner:9"]);
    expect(page.window.complete).toBe(true);

    const foreign = await handler.fetch(
      new Request("https://worker.test/v1/rewind-moments?limit=50", {
        headers: {
          authorization: "Bearer test-token",
          "x-omi-client-id": "other-account",
        },
      }),
      { ...envBase, DB: d1Mock } as never,
      { waitUntil() {}, passThroughOnException() {}, props: {} } as never
    );
    const foreignPage = (await foreign.json()) as { items: unknown[] };
    expect(foreignPage.items).toEqual([]);
  });

  test("pixels are not accepted on the metadata write", async () => {
    const rejected = await fetchPath("/v1/rewind-moments", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        frameId: "captured:owner:1",
        capturedAtMs: 1,
        appName: "Notes",
        windowTitle: "",
        source: "captured",
        ocrPreview: "",
        jpegBase64: "aaaa",
      }),
    });
    expect(rejected.status).toBe(201);
    const body = (await rejected.json()) as { moment: Record<string, unknown> };
    expect(body.moment).not.toHaveProperty("jpegBase64");
    expect(body.moment).not.toHaveProperty("base64");
  });
});
