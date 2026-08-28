import { beforeAll, beforeEach, describe, expect, mock, test } from "bun:test";

import {
  parseDeviceSessionAudio,
  parseDeviceSessionCreate,
} from "../src/device-sessions";
import { createD1Mock } from "./d1-mock";

let handler: typeof import("../src/index")["default"];

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

type StoredObject = { bytes: Uint8Array; contentType: string | undefined };

function createR2Mock(): R2Bucket & { objects: Map<string, StoredObject> } {
  const objects = new Map<string, StoredObject>();
  return {
    objects,
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
    async get(key: string) {
      const object = objects.get(key);
      if (object === undefined) return null;
      return {
        key,
        size: object.bytes.byteLength,
        arrayBuffer: async () =>
          object.bytes.buffer.slice(
            object.bytes.byteOffset,
            object.bytes.byteOffset + object.bytes.byteLength
          ),
      } as never;
    },
    async head(key: string) {
      const object = objects.get(key);
      if (object === undefined) return null;
      return { key, size: object.bytes.byteLength } as never;
    },
    async delete() {},
    async list() {
      return { objects: [], truncated: false } as never;
    },
  } as never;
}

let d1Mock: D1Database;
let r2Mock: ReturnType<typeof createR2Mock>;

const env = {
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
  get ATTACHMENTS() {
    return r2Mock;
  },
  get DB() {
    return d1Mock;
  },
};

const executionContext = {
  waitUntil: (_promise: Promise<unknown>) => undefined,
  passThroughOnException: () => undefined,
  props: {},
};

const fetchWorker = (
  path: string,
  init?: RequestInit,
  bindings: Record<string, unknown> = env
) =>
  handler.fetch(
    new Request(`https://worker.test${path}`, init),
    bindings as never,
    executionContext as never
  );

const openBody = {
  deviceId: "AA:BB:CC:DD:EE:FF",
  deviceName: "Omi",
  codec: 21,
};

beforeEach(() => {
  d1Mock = createD1Mock();
  r2Mock = createR2Mock();
});

describe("device session request validators", () => {
  test("accepts a codec byte and rejects invented transcript fields", () => {
    expect(parseDeviceSessionCreate(openBody)).toEqual({
      deviceId: "AA:BB:CC:DD:EE:FF",
      deviceName: "Omi",
      codec: 21,
    });
    expect(
      parseDeviceSessionCreate({ ...openBody, transcript: "hello" })
    ).toBeNull();
    expect(parseDeviceSessionCreate({ ...openBody, codec: 256 })).toBeNull();
    expect(
      parseDeviceSessionAudio({
        bytesBase64: btoa("\x01\x00\x00payload"),
        transcript: "no",
      })
    ).toBeNull();
  });
});

describe("device session ingest", () => {
  test("opens, stores bytes in the bound bucket, and lists metadata only", async () => {
    const opened = await fetchWorker("/v1/device-sessions", {
      method: "POST",
      headers: authenticatedHeaders,
      body: JSON.stringify(openBody),
    });
    expect(opened.status).toBe(201);
    const created = (await opened.json()) as {
      session: {
        id: string;
        codec: number;
        state: string;
        byteCount: number;
        chunkCount: number;
      };
    };
    expect(created.session.codec).toBe(21);
    expect(created.session.state).toBe("open");
    expect(created.session.byteCount).toBe(0);
    expect(JSON.stringify(created)).not.toContain("transcript");
    expect(JSON.stringify(created)).not.toContain("r2_prefix");

    const payload = new Uint8Array([1, 0, 0, 9, 8, 7]);
    const appended = await fetchWorker(
      `/v1/device-sessions/${created.session.id}/audio`,
      {
        method: "POST",
        headers: authenticatedHeaders,
        body: JSON.stringify({
          bytesBase64: btoa(String.fromCharCode(...payload)),
        }),
      }
    );
    expect(appended.status).toBe(200);
    const afterAudio = (await appended.json()) as {
      session: { byteCount: number; chunkCount: number; state: string };
    };
    expect(afterAudio.session.byteCount).toBe(6);
    expect(afterAudio.session.chunkCount).toBe(1);
    expect(afterAudio.session.state).toBe("open");
    expect(r2Mock.objects.size).toBe(1);
    const stored = [...r2Mock.objects.values()][0];
    expect(stored?.bytes).toEqual(payload);

    const completed = await fetchWorker(
      `/v1/device-sessions/${created.session.id}/complete`,
      { method: "POST", headers: authenticatedHeaders }
    );
    expect(completed.status).toBe(200);
    const done = (await completed.json()) as {
      session: { state: string; endedAt: number | null };
    };
    expect(done.session.state).toBe("complete");
    expect(done.session.endedAt).not.toBeNull();
    expect(JSON.stringify(done)).not.toContain("transcript");

    const listed = await fetchWorker("/v1/device-sessions", {
      headers: authenticatedHeaders,
    });
    expect(listed.status).toBe(200);
    const page = (await listed.json()) as {
      sessions: Array<{ id: string; byteCount: number }>;
    };
    expect(page.sessions).toHaveLength(1);
    expect(page.sessions[0]?.id).toBe(created.session.id);
    expect(page.sessions[0]?.byteCount).toBe(6);
    expect(JSON.stringify(page)).not.toContain("transcript");
  });

  test("isolates sessions by x-omi-client-id and fail-closes without bindings", async () => {
    const opened = await fetchWorker("/v1/device-sessions", {
      method: "POST",
      headers: authenticatedHeaders,
      body: JSON.stringify(openBody),
    });
    const created = (await opened.json()) as { session: { id: string } };

    const foreign = await fetchWorker("/v1/device-sessions", {
      headers: {
        authorization: "Bearer test-token",
        "x-omi-client-id": "other-account",
      },
    });
    expect(foreign.status).toBe(200);
    const foreignPage = (await foreign.json()) as { sessions: unknown[] };
    expect(foreignPage).toEqual({ sessions: [] });

    const stolen = await fetchWorker(
      `/v1/device-sessions/${created.session.id}/audio`,
      {
        method: "POST",
        headers: {
          authorization: "Bearer test-token",
          "x-omi-client-id": "other-account",
        },
        body: JSON.stringify({ bytesBase64: btoa("abc") }),
      }
    );
    expect(stolen.status).toBe(404);

    const missingR2 = await fetchWorker(
      "/v1/device-sessions",
      {
        method: "POST",
        headers: authenticatedHeaders,
        body: JSON.stringify(openBody),
      },
      { ...env, ATTACHMENTS: undefined }
    );
    expect(missingR2.status).toBe(503);
    const missingR2Body = (await missingR2.json()) as {
      error: { code: string; retryable: boolean; action: string };
    };
    expect(missingR2Body).toEqual({
      error: {
        code: "service_unavailable",
        retryable: true,
        action: "retry",
      },
    });

    const missingDb = await fetchWorker(
      "/v1/device-sessions",
      {
        method: "POST",
        headers: authenticatedHeaders,
        body: JSON.stringify(openBody),
      },
      { ...env, DB: undefined }
    );
    expect(missingDb.status).not.toBe(200);
    expect(missingDb.status).not.toBe(201);
    const missingDbBody = (await missingDb.json()) as {
      error?: { code?: string };
      session?: unknown;
      transcript?: unknown;
    };
    expect(missingDbBody.session).toBeUndefined();
    expect(missingDbBody.transcript).toBeUndefined();
  });

  test("does not invent a 200 transcript when audio is absent", async () => {
    const opened = await fetchWorker("/v1/device-sessions", {
      method: "POST",
      headers: authenticatedHeaders,
      body: JSON.stringify(openBody),
    });
    const created = (await opened.json()) as { session: { id: string } };
    const completed = await fetchWorker(
      `/v1/device-sessions/${created.session.id}/complete`,
      { method: "POST", headers: authenticatedHeaders }
    );
    const body = (await completed.json()) as {
      session: { byteCount: number; state: string };
    };
    expect(completed.status).toBe(200);
    expect(body.session.byteCount).toBe(0);
    expect(body.session.state).toBe("complete");
    expect(body).not.toHaveProperty("transcript");
    expect(body.session).not.toHaveProperty("transcript");
  });
});
