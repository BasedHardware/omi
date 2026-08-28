import { beforeAll, beforeEach, describe, expect, mock, test } from "bun:test";

import type { CoreEnv } from "../src/http-core";
import { createD1Mock } from "./d1-mock";

let honoFetch: (
  request: Request,
  env: CoreEnv,
  ctx: unknown
) => Response | Promise<Response>;
let createElysiaApp: typeof import("../src/elysia")["createElysiaApp"];

beforeAll(async () => {
  void mock.module("cloudflare:workers", () => ({
    DurableObject: class {},
  }));
  const worker = await import("../src/index");
  honoFetch = worker.default.fetch.bind(worker.default) as typeof honoFetch;
  ({ createElysiaApp } = await import("../src/elysia"));
});

type StoredObject = { bytes: Uint8Array; contentType: string | undefined };

function createR2Mock(): R2Bucket {
  const objects = new Map<string, StoredObject>();
  return {
    async put(
      key: string,
      value: unknown,
      options?: { httpMetadata?: { contentType?: string } }
    ) {
      const bytes =
        value instanceof Uint8Array
          ? value
          : value instanceof ArrayBuffer
          ? new Uint8Array(value)
          : typeof value === "string"
          ? new TextEncoder().encode(value)
          : new Uint8Array();
      objects.set(key, {
        bytes,
        contentType: options?.httpMetadata?.contentType,
      });
      return { key, size: bytes.byteLength } as never;
    },
    async get() {
      return null;
    },
    async head() {
      return null;
    },
    async delete() {},
    async list() {
      return { objects: [], truncated: false } as never;
    },
  } as never;
}

const executionContext = {
  waitUntil: (_promise: Promise<unknown>) => undefined,
  passThroughOnException: () => undefined,
  props: {},
};

const authenticatedHeaders = {
  authorization: "Bearer test-token",
  "x-omi-client-id": "test-account",
};

const openBody = {
  deviceId: "AA:BB:CC:DD:EE:FF",
  deviceName: "Omi",
  codec: 21,
};

let d1Mock: D1Database;
let r2Mock: R2Bucket;

function testEnv(): CoreEnv {
  return {
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
    OPENROUTER_MODEL: "",
    OPENROUTER_GATEWAY_URL: "",
    OPENROUTER_API_KEY: "",
    ATTACHMENTS: r2Mock,
    DB: d1Mock,
  } as CoreEnv;
}

const adapters = [
  {
    name: "hono",
    fetch: (path: string, init?: RequestInit) =>
      honoFetch(
        new Request(`https://worker.test${path}`, init),
        testEnv(),
        executionContext
      ),
  },
  {
    name: "elysia",
    fetch: (path: string, init?: RequestInit) =>
      createElysiaApp(testEnv()).fetch(
        new Request(`https://worker.test${path}`, init)
      ),
  },
] as const;

beforeEach(() => {
  d1Mock = createD1Mock();
  r2Mock = createR2Mock();
});

for (const adapter of adapters) {
  describe(`${adapter.name} shared HTTP core`, () => {
    test("/health matches the worker contract", async () => {
      const response = await adapter.fetch("/health");
      expect(response.status).toBe(200);
      expect(
        (await response.json()) as { status: string; environment: string }
      ).toEqual({
        status: "ok",
        environment: "test",
      });
    });

    test("/ready matches the worker contract", async () => {
      const response = await adapter.fetch("/ready");
      expect(response.status).toBe(200);
      expect(
        (await response.json()) as {
          status: string;
          environment: string;
          observability_sink_mode: string;
        }
      ).toEqual({
        status: "ready",
        environment: "test",
        observability_sink_mode: "cloudflare_only",
      });
    });

    test("device-session open uses the shared handler", async () => {
      const response = await adapter.fetch("/v1/device-sessions", {
        method: "POST",
        headers: authenticatedHeaders,
        body: JSON.stringify(openBody),
      });
      expect(response.status).toBe(201);
      const body = (await response.json()) as {
        session: { deviceId: string; codec: number; state: string };
      };
      expect(body.session.deviceId).toBe("AA:BB:CC:DD:EE:FF");
      expect(body.session.codec).toBe(21);
      expect(body.session.state).toBe("open");
      expect(body.session).not.toHaveProperty("transcript");
    });
  });
}
