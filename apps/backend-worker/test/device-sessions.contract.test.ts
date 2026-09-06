import { beforeAll, beforeEach, describe, expect, mock, test } from "bun:test";

import {
  parseDeviceSessionAudio,
  parseDeviceSessionCreate,
} from "../src/device-sessions";
import { createD1Mock } from "./d1-mock";

let handler: typeof import("../src/index")["default"];

test("audio requires a bounded stable chunk index", () => {
  for (const chunkIndex of [undefined, null, -1, 0.5, 65_536, "0"]) {
    expect(
      parseDeviceSessionAudio({ bytesBase64: "AQID", chunkIndex })
    ).toBeNull();
  }
  expect(
    parseDeviceSessionAudio({ bytesBase64: "AQID", chunkIndex: 0 })?.chunkIndex
  ).toBe(0);
});

test("recording creation requires a lowercase UUID v4 capture ID", () => {
  for (const captureId of [
    undefined,
    null,
    "",
    "aaaaaaaa-aaaa-1aaa-8aaa-aaaaaaaaaaaa",
    "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA",
  ]) {
    expect(
      parseDeviceSessionCreate({ deviceId: "pendant", codec: 1, captureId })
    ).toBeNull();
  }
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
  captureId: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  deviceId: "AA:BB:CC:DD:EE:FF",
  deviceName: "Omi",
  codec: 21,
};

beforeEach(() => {
  d1Mock = createD1Mock();
  r2Mock = createR2Mock();
});

describe("device session request validators", () => {
  test("explicit transcription authenticates, targets one owned session, and replays the durable result", async () => {
    let calls = 0;
    const bindings = {
      ...env,
      AI: {
        run: async () => {
          calls += 1;
          return {
            text: "Recorded speech",
            segments: [{ start: 0, end: 0.1, text: "Recorded speech" }],
          };
        },
      },
    };
    const opened = await fetchWorker(
      "/v1/device-sessions",
      {
        method: "POST",
        headers: authenticatedHeaders,
        body: JSON.stringify({ ...openBody, codec: 1 }),
      },
      bindings
    );
    const { session } = (await opened.json()) as { session: { id: string } };
    const path = `/v1/device-sessions/${session.id}/transcribe`;
    expect((await fetchWorker(path, { method: "POST" }, bindings)).status).toBe(
      401
    );
    expect(
      (
        await fetchWorker(
          path,
          { method: "POST", headers: authenticatedHeaders },
          bindings
        )
      ).status
    ).toBe(409);
    expect(
      (
        await fetchWorker(
          `/v1/device-sessions/${session.id}/audio`,
          {
            method: "POST",
            headers: authenticatedHeaders,
            body: JSON.stringify({
              chunkIndex: 0,
              bytesBase64: btoa(String.fromCharCode(0, 0, 0, 128, 129)),
            }),
          },
          bindings
        )
      ).status
    ).toBe(200);
    expect(
      (
        await fetchWorker(
          `/v1/device-sessions/${session.id}/complete`,
          { method: "POST", headers: authenticatedHeaders },
          bindings
        )
      ).status
    ).toBe(200);
    const completed = await fetchWorker(
      path,
      { method: "POST", headers: authenticatedHeaders },
      bindings
    );
    expect(completed.status).toBe(200);
    expect(await completed.json()).toMatchObject({
      transcription: {
        sessionId: session.id,
        state: "completed",
        text: "Recorded speech",
      },
    });
    expect(
      (
        await fetchWorker(
          path,
          { method: "POST", headers: authenticatedHeaders },
          bindings
        )
      ).status
    ).toBe(200);
    expect(calls).toBe(1);
  });
  test("recording create replay returns the original session and conflicting metadata is refused", async () => {
    const post = (body: unknown) =>
      fetchWorker("/v1/device-sessions", {
        method: "POST",
        headers: authenticatedHeaders,
        body: JSON.stringify(body),
      });
    const first = await post(openBody);
    const original = await first.text();
    expect(first.status).toBe(201);
    const replay = await post(openBody);
    expect(replay.status).toBe(201);
    expect(await replay.text()).toBe(original);
    const conflict = await post({ ...openBody, codec: 20 });
    expect(conflict.status).toBe(409);
    expect((await conflict.json()) as unknown).toMatchObject({
      error: { code: "conflict" },
    });
  });
  test("accepts a codec byte and rejects invented transcript fields", () => {
    expect(parseDeviceSessionCreate(openBody)).toEqual({
      captureId: openBody.captureId,
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
        chunkIndex: 0,
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
          chunkIndex: 0,
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
        body: JSON.stringify({ chunkIndex: 0, bytesBase64: btoa("abc") }),
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

  test("claims distinct chunk keys and rejects appends after complete", async () => {
    const opened = await fetchWorker("/v1/device-sessions", {
      method: "POST",
      headers: authenticatedHeaders,
      body: JSON.stringify(openBody),
    });
    const created = (await opened.json()) as { session: { id: string } };
    const first = new Uint8Array([1, 0, 0, 1]);
    const second = new Uint8Array([1, 0, 0, 2]);
    const left = await fetchWorker(
      `/v1/device-sessions/${created.session.id}/audio`,
      {
        method: "POST",
        headers: authenticatedHeaders,
        body: JSON.stringify({
          chunkIndex: 0,
          bytesBase64: btoa(String.fromCharCode(...first)),
        }),
      }
    );
    const right = await fetchWorker(
      `/v1/device-sessions/${created.session.id}/audio`,
      {
        method: "POST",
        headers: authenticatedHeaders,
        body: JSON.stringify({
          chunkIndex: 1,
          bytesBase64: btoa(String.fromCharCode(...second)),
        }),
      }
    );
    expect(left.status).toBe(200);
    expect(right.status).toBe(200);
    expect(r2Mock.objects.size).toBe(2);
    const keys = [...r2Mock.objects.keys()].sort();
    expect(keys[0]?.endsWith("/000000")).toBe(true);
    expect(keys[1]?.endsWith("/000001")).toBe(true);
    const stored = keys.map((key) =>
      Array.from(r2Mock.objects.get(key)?.bytes ?? [])
    );
    expect(stored).toContainEqual(Array.from(first));
    expect(stored).toContainEqual(Array.from(second));

    const completed = await fetchWorker(
      `/v1/device-sessions/${created.session.id}/complete`,
      { method: "POST", headers: authenticatedHeaders }
    );
    expect(completed.status).toBe(200);
    const late = await fetchWorker(
      `/v1/device-sessions/${created.session.id}/audio`,
      {
        method: "POST",
        headers: authenticatedHeaders,
        body: JSON.stringify({ chunkIndex: 0, bytesBase64: btoa("late") }),
      }
    );
    expect(late.status).toBe(409);
    const lateBody = (await late.json()) as {
      error: { code: string };
      session?: unknown;
    };
    expect(lateBody.error.code).toBe("conflict");
    expect(lateBody.session).toBeUndefined();
    expect(r2Mock.objects.size).toBe(2);
  });

  test("completion waits for every claimed audio chunk to reach storage", async () => {
    const opened = await fetchWorker("/v1/device-sessions", {
      method: "POST",
      headers: authenticatedHeaders,
      body: JSON.stringify(openBody),
    });
    const created = (await opened.json()) as { session: { id: string } };
    let release: () => void = () => undefined;
    let entered: () => void = () => undefined;
    const pending = new Promise<void>((resolve) => {
      release = resolve;
    });
    const started = new Promise<void>((resolve) => {
      entered = resolve;
    });
    const put = r2Mock.put.bind(r2Mock);
    r2Mock.put = (async (...args: Parameters<R2Bucket["put"]>) => {
      entered();
      await pending;
      return put(...args);
    }) as R2Bucket["put"];
    const upload = fetchWorker(
      `/v1/device-sessions/${created.session.id}/audio`,
      {
        method: "POST",
        headers: authenticatedHeaders,
        body: JSON.stringify({ chunkIndex: 0, bytesBase64: btoa("audio") }),
      }
    );
    await started;
    try {
      const early = await fetchWorker(
        `/v1/device-sessions/${created.session.id}/complete`,
        {
          method: "POST",
          headers: authenticatedHeaders,
        }
      );
      expect(early.status).toBe(409);
    } finally {
      release();
    }
    expect((await upload).status).toBe(200);
    const completed = await fetchWorker(
      `/v1/device-sessions/${created.session.id}/complete`,
      {
        method: "POST",
        headers: authenticatedHeaders,
      }
    );
    expect(completed.status).toBe(200);
    expect(await completed.json()).toMatchObject({
      session: { state: "complete", chunkCount: 1 },
    });
  });

  test("failed audio storage cannot be finalized as a successful recording", async () => {
    const opened = await fetchWorker("/v1/device-sessions", {
      method: "POST",
      headers: authenticatedHeaders,
      body: JSON.stringify(openBody),
    });
    const created = (await opened.json()) as { session: { id: string } };
    r2Mock.put = async () => {
      throw new Error("storage unavailable");
    };

    const appended = await fetchWorker(
      `/v1/device-sessions/${created.session.id}/audio`,
      {
        method: "POST",
        headers: authenticatedHeaders,
        body: JSON.stringify({ chunkIndex: 0, bytesBase64: btoa("audio") }),
      }
    );
    expect(appended.status).toBe(503);
    const completed = await fetchWorker(
      `/v1/device-sessions/${created.session.id}/complete`,
      { method: "POST", headers: authenticatedHeaders }
    );
    expect(completed.status).toBe(409);
    const listed = await fetchWorker("/v1/device-sessions", {
      headers: authenticatedHeaders,
    });
    expect(await listed.json()).toMatchObject({
      sessions: [{ state: "open" }],
    });
    const late = await fetchWorker(
      `/v1/device-sessions/${created.session.id}/audio`,
      {
        method: "POST",
        headers: authenticatedHeaders,
        body: JSON.stringify({ chunkIndex: 0, bytesBase64: btoa("retry") }),
      }
    );
    expect(late.status).toBe(409);
    expect(r2Mock.objects.size).toBe(0);
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
