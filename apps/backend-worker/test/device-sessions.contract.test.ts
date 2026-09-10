import { beforeAll, beforeEach, describe, expect, mock, test } from "bun:test";

import {
  parseDeviceSessionAudio,
  parseDeviceSessionCreate,
} from "../src/device-sessions";
import {
  coreContext,
  handleDeviceSessionAudio,
  handleDeviceSessionComplete,
  handleDeviceSessionOpen,
  handleDeviceSessionRead,
  handleTranscribe,
  handleTranscription,
} from "../src/http-core";
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

test("capture create and audio follow production Listen bounded strings", () => {
  const captureId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  expect(
    parseDeviceSessionCreate({
      captureId,
      deviceId: "pendant\0id",
      codec: 1,
    })
  ).toBeNull();
  expect(
    parseDeviceSessionCreate({
      captureId,
      deviceId: "pendant",
      deviceName: "Omi\0",
      codec: 1,
    })
  ).toBeNull();
  expect(
    parseDeviceSessionCreate({
      captureId,
      deviceId: "pendant",
      codec: 1,
    })
  ).toEqual({
    captureId,
    deviceId: "pendant",
    deviceName: null,
    codec: 1,
  });
  expect(
    parseDeviceSessionAudio({
      chunkIndex: 0,
      bytesBase64: "A".repeat(1_398_105),
    })
  ).toBeNull();
  expect(
    parseDeviceSessionAudio({
      chunkIndex: 0,
      bytesBase64: btoa("\x01\x00\x00payload"),
    })?.bytes.byteLength
  ).toBe(10);
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
            transcription_info: { language: "en" },
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
              chunks: [
                {
                  chunkIndex: 0,
                  bytesBase64: btoa(String.fromCharCode(0, 0, 0, 128, 129)),
                },
              ],
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
    expect(completed.headers.get("retry-after")).toBeNull();
    const completedBody = (await completed.json()) as object;
    expect(completedBody).toEqual({
      transcription: {
        sessionId: session.id,
        state: "completed",
        text: "Recorded speech",
        segments: [{ start: 0, end: 0.1, text: "Recorded speech" }],
        language: null,
        errorCode: null,
        updatedAt: expect.any(Number),
        discardedLeadingPackets: 0,
      },
    });
    const fetched = await fetchWorker(
      `/v1/device-sessions/${session.id}/transcript`,
      { headers: authenticatedHeaders },
      bindings
    );
    expect(fetched.status).toBe(200);
    expect(fetched.headers.get("retry-after")).toBeNull();
    expect((await fetched.json()) as object).toEqual(completedBody);
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
    await bindings.DB.prepare(
      "UPDATE device_transcriptions SET segments = '{' WHERE session_id = ?"
    )
      .bind(session.id)
      .run();
    const unreadable = await fetchWorker(
      `/v1/device-sessions/${session.id}/transcript`,
      { headers: authenticatedHeaders },
      bindings
    );
    expect(unreadable.status).toBe(503);
    expect(unreadable.headers.get("retry-after")).toBeNull();
    expect((await unreadable.json()) as object).toEqual({
      error: {
        code: "service_unavailable",
        retryable: false,
        action: "none",
      },
    });
  });
  test("pending transcript GET and transcribe POST send production Listen retry-after", async () => {
    const opened = await fetchWorker("/v1/device-sessions", {
      method: "POST",
      headers: authenticatedHeaders,
      body: JSON.stringify({
        ...openBody,
        captureId: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        codec: 1,
      }),
    });
    const { session } = (await opened.json()) as { session: { id: string } };
    expect(
      (
        await fetchWorker(`/v1/device-sessions/${session.id}/audio`, {
          method: "POST",
          headers: authenticatedHeaders,
          body: JSON.stringify({
            chunks: [
              {
                chunkIndex: 0,
                bytesBase64: btoa(String.fromCharCode(0, 0, 0, 128, 129)),
              },
            ],
          }),
        })
      ).status
    ).toBe(200);
    expect(
      (
        await fetchWorker(`/v1/device-sessions/${session.id}/complete`, {
          method: "POST",
          headers: authenticatedHeaders,
        })
      ).status
    ).toBe(200);
    const queued = await fetchWorker(
      `/v1/device-sessions/${session.id}/transcript`,
      { headers: authenticatedHeaders }
    );
    expect(queued.status).toBe(200);
    expect(queued.headers.get("retry-after")).toBe("2");
    expect(
      ((await queued.json()) as { transcription: { state: string } })
        .transcription.state
    ).toBe("queued");
    await d1Mock
      .prepare(
        "UPDATE device_transcriptions SET available_at = ? WHERE session_id = ?"
      )
      .bind(Date.now() + 900_000, session.id)
      .run();
    const transcribe = await fetchWorker(
      `/v1/device-sessions/${session.id}/transcribe`,
      { method: "POST", headers: authenticatedHeaders }
    );
    expect(transcribe.status).toBe(202);
    expect(transcribe.headers.get("retry-after")).toBe("2");
    expect(
      ((await transcribe.json()) as { transcription: { state: string } })
        .transcription.state
    ).toBe("queued");
  });
  test("missing transcription attachments is nested non-retryable without inventing speech", async () => {
    const opened = await fetchWorker("/v1/device-sessions", {
      method: "POST",
      headers: authenticatedHeaders,
      body: JSON.stringify({ ...openBody, codec: 1 }),
    });
    const { session } = (await opened.json()) as { session: { id: string } };
    const path = `/v1/device-sessions/${session.id}/transcribe`;
    expect(
      (
        await fetchWorker(`/v1/device-sessions/${session.id}/audio`, {
          method: "POST",
          headers: authenticatedHeaders,
          body: JSON.stringify({
            chunks: [
              {
                chunkIndex: 0,
                bytesBase64: btoa(String.fromCharCode(0, 0, 0, 128, 129)),
              },
            ],
          }),
        })
      ).status
    ).toBe(200);
    expect(
      (
        await fetchWorker(`/v1/device-sessions/${session.id}/complete`, {
          method: "POST",
          headers: authenticatedHeaders,
        })
      ).status
    ).toBe(200);
    const transcribe = await fetchWorker(
      path,
      { method: "POST", headers: authenticatedHeaders },
      { ...env, ATTACHMENTS: undefined }
    );
    expect(transcribe.status).toBe(503);
    expect(transcribe.headers.get("retry-after")).toBeNull();
    expect((await transcribe.json()) as object).toEqual({
      error: {
        code: "service_unavailable",
        retryable: false,
        action: "none",
      },
    });
  });

  test("transcript GET retryable 503 sends production Listen retry-after", async () => {
    const missingDb = await handleTranscription(
      coreContext({
        env: { ...env, DB: undefined } as never,
        request: new Request(
          "https://worker.test/v1/device-sessions/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/transcript"
        ),
        routePath: "/v1/device-sessions/:id/transcript",
        params: { id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa" },
        values: { accountId: "test-account", requestId: "test-request" },
      })
    );
    expect(missingDb.status).toBe(503);
    expect(missingDb.headers.get("retry-after")).toBe("1");
    expect((await missingDb.json()) as object).toEqual({
      error: {
        code: "service_unavailable",
        retryable: true,
        action: "retry",
      },
    });
    const missingDbTranscribe = await handleTranscribe(
      coreContext({
        env: { ...env, DB: undefined } as never,
        request: new Request(
          "https://worker.test/v1/device-sessions/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/transcribe",
          { method: "POST" }
        ),
        routePath: "/v1/device-sessions/:id/transcribe",
        params: { id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa" },
        values: { accountId: "test-account", requestId: "test-request" },
      })
    );
    expect(missingDbTranscribe.status).toBe(503);
    expect(missingDbTranscribe.headers.get("retry-after")).toBe("1");
    expect((await missingDbTranscribe.json()) as object).toEqual({
      error: {
        code: "service_unavailable",
        retryable: true,
        action: "retry",
      },
    });
  });

  test("capture open audio and complete retryable 503 send production Listen retry-after", async () => {
    const retryable = {
      error: {
        code: "service_unavailable",
        retryable: true,
        action: "retry",
      },
    };
    const missingDbOpen = await handleDeviceSessionOpen(
      coreContext({
        env: { ...env, DB: undefined } as never,
        request: new Request("https://worker.test/v1/device-sessions", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(openBody),
        }),
        routePath: "/v1/device-sessions",
        params: {},
        values: { accountId: "test-account", requestId: "test-request" },
      })
    );
    expect(missingDbOpen.status).toBe(503);
    expect(missingDbOpen.headers.get("retry-after")).toBe("1");
    expect((await missingDbOpen.json()) as object).toEqual(retryable);
    const missingDbAudio = await handleDeviceSessionAudio(
      coreContext({
        env: { ...env, DB: undefined } as never,
        request: new Request(
          "https://worker.test/v1/device-sessions/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/audio",
          {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
              chunks: [{ chunkIndex: 0, bytesBase64: btoa("abc") }],
            }),
          }
        ),
        routePath: "/v1/device-sessions/:id/audio",
        params: { id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa" },
        values: { accountId: "test-account", requestId: "test-request" },
      })
    );
    expect(missingDbAudio.status).toBe(503);
    expect(missingDbAudio.headers.get("retry-after")).toBe("1");
    expect((await missingDbAudio.json()) as object).toEqual(retryable);
    const missingDbComplete = await handleDeviceSessionComplete(
      coreContext({
        env: { ...env, DB: undefined } as never,
        request: new Request(
          "https://worker.test/v1/device-sessions/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/complete",
          { method: "POST" }
        ),
        routePath: "/v1/device-sessions/:id/complete",
        params: { id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa" },
        values: { accountId: "test-account", requestId: "test-request" },
      })
    );
    expect(missingDbComplete.status).toBe(503);
    expect(missingDbComplete.headers.get("retry-after")).toBe("1");
    expect((await missingDbComplete.json()) as object).toEqual(retryable);
  });

  test("Listen store throw is production retryable unavailable", async () => {
    const throwingDb = {
      prepare() {
        throw new Error("d1 store failed");
      },
    };
    const retryable = {
      error: {
        code: "service_unavailable",
        retryable: true,
        action: "retry",
      },
    };
    const sessionId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
    const storeEnv = { ...env, DB: throwingDb } as never;
    const account = {
      accountId: "test-account",
      requestId: "test-request",
    };
    const opened = await handleDeviceSessionOpen(
      coreContext({
        env: storeEnv,
        request: new Request("https://worker.test/v1/device-sessions", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(openBody),
        }),
        routePath: "/v1/device-sessions",
        params: {},
        values: account,
      })
    );
    expect(opened.status).toBe(503);
    expect(opened.headers.get("retry-after")).toBe("1");
    expect((await opened.json()) as object).toEqual(retryable);
    const audio = await handleDeviceSessionAudio(
      coreContext({
        env: storeEnv,
        request: new Request(
          `https://worker.test/v1/device-sessions/${sessionId}/audio`,
          {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
              chunks: [{ chunkIndex: 0, bytesBase64: btoa("abc") }],
            }),
          }
        ),
        routePath: "/v1/device-sessions/:id/audio",
        params: { id: sessionId },
        values: account,
      })
    );
    expect(audio.status).toBe(503);
    expect(audio.headers.get("retry-after")).toBe("1");
    expect((await audio.json()) as object).toEqual(retryable);
    const completed = await handleDeviceSessionComplete(
      coreContext({
        env: storeEnv,
        request: new Request(
          `https://worker.test/v1/device-sessions/${sessionId}/complete`,
          { method: "POST" }
        ),
        routePath: "/v1/device-sessions/:id/complete",
        params: { id: sessionId },
        values: account,
      })
    );
    expect(completed.status).toBe(503);
    expect(completed.headers.get("retry-after")).toBe("1");
    expect((await completed.json()) as object).toEqual(retryable);
    const metadata = await handleDeviceSessionRead(
      coreContext({
        env: storeEnv,
        request: new Request(
          `https://worker.test/v1/device-sessions/${sessionId}`
        ),
        routePath: "/v1/device-sessions/:id",
        params: { id: sessionId },
        values: account,
      })
    );
    expect(metadata.status).toBe(503);
    expect(metadata.headers.get("retry-after")).toBe("1");
    expect((await metadata.json()) as object).toEqual(retryable);
    const transcript = await handleTranscription(
      coreContext({
        env: storeEnv,
        request: new Request(
          `https://worker.test/v1/device-sessions/${sessionId}/transcript`
        ),
        routePath: "/v1/device-sessions/:id/transcript",
        params: { id: sessionId },
        values: account,
      })
    );
    expect(transcript.status).toBe(503);
    expect(transcript.headers.get("retry-after")).toBe("1");
    expect((await transcript.json()) as object).toEqual(retryable);
    const transcribe = await handleTranscribe(
      coreContext({
        env: storeEnv,
        request: new Request(
          `https://worker.test/v1/device-sessions/${sessionId}/transcribe`,
          { method: "POST" }
        ),
        routePath: "/v1/device-sessions/:id/transcribe",
        params: { id: sessionId },
        values: account,
      })
    );
    expect(transcribe.status).toBe(503);
    expect(transcribe.headers.get("retry-after")).toBe("1");
    expect((await transcribe.json()) as object).toEqual(retryable);
    const malformed = await handleDeviceSessionOpen(
      coreContext({
        env: storeEnv,
        request: new Request("https://worker.test/v1/device-sessions", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: "{",
        }),
        routePath: "/v1/device-sessions",
        params: {},
        values: account,
      })
    );
    expect(malformed.status).toBe(400);
    expect(malformed.headers.get("retry-after")).toBeNull();
  });

  test("audio store unavailable retryable 503 sends production Listen retry-after", async () => {
    const opened = await fetchWorker("/v1/device-sessions", {
      method: "POST",
      headers: authenticatedHeaders,
      body: JSON.stringify(openBody),
    });
    expect(opened.status).toBe(201);
    const created = (await opened.json()) as { session: { id: string } };
    const originalPut = r2Mock.put;
    r2Mock.put = (async () => {
      throw new Error("r2");
    }) as typeof r2Mock.put;
    try {
      const audio = await fetchWorker(
        `/v1/device-sessions/${created.session.id}/audio`,
        {
          method: "POST",
          headers: authenticatedHeaders,
          body: JSON.stringify({
            chunks: [
              {
                chunkIndex: 0,
                bytesBase64: btoa(String.fromCharCode(0, 0, 0, 128, 129)),
              },
            ],
          }),
        }
      );
      expect(audio.status).toBe(503);
      expect(audio.headers.get("retry-after")).toBe("1");
      expect((await audio.json()) as object).toEqual({
        error: {
          code: "service_unavailable",
          retryable: true,
          action: "retry",
        },
      });
    } finally {
      r2Mock.put = originalPut;
    }
  });

  test("missing device session 404s use production Listen device_session_not_found", async () => {
    const missingId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
    const missing = {
      error: {
        code: "device_session_not_found",
        retryable: false,
        action: "none",
      },
    };
    const transcript = await fetchWorker(
      `/v1/device-sessions/${missingId}/transcript`,
      { headers: authenticatedHeaders }
    );
    expect(transcript.status).toBe(404);
    expect(transcript.headers.get("retry-after")).toBeNull();
    expect((await transcript.json()) as object).toEqual(missing);
    const transcribe = await fetchWorker(
      `/v1/device-sessions/${missingId}/transcribe`,
      { method: "POST", headers: authenticatedHeaders }
    );
    expect(transcribe.status).toBe(404);
    expect(transcribe.headers.get("retry-after")).toBeNull();
    expect((await transcribe.json()) as object).toEqual(missing);
    const audio = await fetchWorker(`/v1/device-sessions/${missingId}/audio`, {
      method: "POST",
      headers: authenticatedHeaders,
      body: JSON.stringify({
        chunks: [
          {
            chunkIndex: 0,
            bytesBase64: btoa(String.fromCharCode(0, 0, 0, 128, 129)),
          },
        ],
      }),
    });
    expect(audio.status).toBe(404);
    expect(audio.headers.get("retry-after")).toBeNull();
    expect((await audio.json()) as object).toEqual(missing);
    const complete = await fetchWorker(
      `/v1/device-sessions/${missingId}/complete`,
      { method: "POST", headers: authenticatedHeaders }
    );
    expect(complete.status).toBe(404);
    expect(complete.headers.get("retry-after")).toBeNull();
    expect((await complete.json()) as object).toEqual(missing);
  });

  test("illegal capture session path ids use production Listen not_found", async () => {
    const grammar = {
      error: {
        code: "not_found",
        retryable: false,
        action: "none",
      },
    };
    const audioBody = JSON.stringify({
      chunks: [
        {
          chunkIndex: 0,
          bytesBase64: btoa(String.fromCharCode(0, 0, 0, 128, 129)),
        },
      ],
    });
    for (const illegalId of [
      "not-a-uuid",
      "aaaaaaaa-aaaa-1aaa-8aaa-aaaaaaaaaaaa",
    ]) {
      const transcript = await fetchWorker(
        `/v1/device-sessions/${illegalId}/transcript`,
        { headers: authenticatedHeaders }
      );
      expect(transcript.status).toBe(404);
      expect(transcript.headers.get("retry-after")).toBeNull();
      expect((await transcript.json()) as object).toEqual(grammar);
      const transcribe = await fetchWorker(
        `/v1/device-sessions/${illegalId}/transcribe`,
        { method: "POST", headers: authenticatedHeaders }
      );
      expect(transcribe.status).toBe(404);
      expect(transcribe.headers.get("retry-after")).toBeNull();
      expect((await transcribe.json()) as object).toEqual(grammar);
      const audio = await fetchWorker(
        `/v1/device-sessions/${illegalId}/audio`,
        {
          method: "POST",
          headers: authenticatedHeaders,
          body: audioBody,
        }
      );
      expect(audio.status).toBe(404);
      expect(audio.headers.get("retry-after")).toBeNull();
      expect((await audio.json()) as object).toEqual(grammar);
      const malformedAudio = await fetchWorker(
        `/v1/device-sessions/${illegalId}/audio`,
        {
          method: "POST",
          headers: authenticatedHeaders,
          body: "{",
        }
      );
      expect(malformedAudio.status).toBe(404);
      expect(malformedAudio.headers.get("retry-after")).toBeNull();
      expect((await malformedAudio.json()) as object).toEqual(grammar);
      const complete = await fetchWorker(
        `/v1/device-sessions/${illegalId}/complete`,
        { method: "POST", headers: authenticatedHeaders }
      );
      expect(complete.status).toBe(404);
      expect(complete.headers.get("retry-after")).toBeNull();
      expect((await complete.json()) as object).toEqual(grammar);
    }
  });

  test("capture wrong methods use production Listen not_found", async () => {
    const missing = {
      error: {
        code: "not_found",
        retryable: false,
        action: "none",
      },
    };
    const sessionId = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
    const audio = await fetchWorker(`/v1/device-sessions/${sessionId}/audio`, {
      headers: authenticatedHeaders,
    });
    expect(audio.status).toBe(404);
    expect(audio.headers.get("retry-after")).toBeNull();
    expect((await audio.json()) as object).toEqual(missing);
    const transcript = await fetchWorker(
      `/v1/device-sessions/${sessionId}/transcript`,
      { method: "POST", headers: authenticatedHeaders }
    );
    expect(transcript.status).toBe(404);
    expect(transcript.headers.get("retry-after")).toBeNull();
    expect((await transcript.json()) as object).toEqual(missing);
    const complete = await fetchWorker(
      `/v1/device-sessions/${sessionId}/complete`,
      { headers: authenticatedHeaders }
    );
    expect(complete.status).toBe(404);
    expect(complete.headers.get("retry-after")).toBeNull();
    expect((await complete.json()) as object).toEqual(missing);
    const transcribe = await fetchWorker(
      `/v1/device-sessions/${sessionId}/transcribe`,
      { headers: authenticatedHeaders }
    );
    expect(transcribe.status).toBe(404);
    expect(transcribe.headers.get("retry-after")).toBeNull();
    expect((await transcribe.json()) as object).toEqual(missing);
    const unknown = await fetchWorker("/unknown", {
      headers: authenticatedHeaders,
    });
    expect(unknown.status).toBe(404);
    expect((await unknown.json()) as object).toEqual({
      error: {
        code: "not_found",
        retryable: false,
        action: "edit_request",
      },
    });
  });

  test("GET session metadata returns the stored session without a capture-ownership receipt", async () => {
    const opened = await fetchWorker("/v1/device-sessions", {
      method: "POST",
      headers: authenticatedHeaders,
      body: JSON.stringify({ ...openBody, capturedAtMs: 1_700_000_000_000 }),
    });
    expect(opened.status).toBe(201);
    const created = (await opened.json()) as {
      session: Record<string, unknown>;
    };
    const metadata = await fetchWorker(
      `/v1/device-sessions/${created.session.id as string}`,
      { headers: authenticatedHeaders }
    );
    expect(metadata.status).toBe(200);
    expect(metadata.headers.get("retry-after")).toBeNull();
    expect((await metadata.json()) as object).toEqual({
      session: created.session,
    });
    const missingR2 = await fetchWorker(
      `/v1/device-sessions/${created.session.id as string}`,
      { headers: authenticatedHeaders },
      { ...env, ATTACHMENTS: undefined }
    );
    expect(missingR2.status).toBe(200);
    expect((await missingR2.json()) as object).toEqual({
      session: created.session,
    });
    const missing = await fetchWorker(
      "/v1/device-sessions/bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
      { headers: authenticatedHeaders }
    );
    expect(missing.status).toBe(404);
    expect(missing.headers.get("retry-after")).toBeNull();
    expect((await missing.json()) as object).toEqual({
      error: {
        code: "device_session_not_found",
        retryable: false,
        action: "none",
      },
    });
    const grammar = await fetchWorker("/v1/device-sessions/not-a-uuid", {
      headers: authenticatedHeaders,
    });
    expect(grammar.status).toBe(404);
    expect((await grammar.json()) as object).toEqual({
      error: {
        code: "not_found",
        retryable: false,
        action: "none",
      },
    });
  });

  test("GET session metadata retryable 503 sends production Listen retry-after", async () => {
    const missingDb = await handleDeviceSessionRead(
      coreContext({
        env: { ...env, DB: undefined } as never,
        request: new Request(
          "https://worker.test/v1/device-sessions/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        ),
        routePath: "/v1/device-sessions/:id",
        params: { id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa" },
        values: { accountId: "test-account", requestId: "test-request" },
      })
    );
    expect(missingDb.status).toBe(503);
    expect(missingDb.headers.get("retry-after")).toBe("1");
    expect((await missingDb.json()) as object).toEqual({
      error: {
        code: "service_unavailable",
        retryable: true,
        action: "retry",
      },
    });
  });

  test("open and complete persist session rows without object storage matching production Listen", async () => {
    const missingR2 = { ...env, ATTACHMENTS: undefined };
    const opened = await fetchWorker(
      "/v1/device-sessions",
      {
        method: "POST",
        headers: authenticatedHeaders,
        body: JSON.stringify(openBody),
      },
      missingR2
    );
    expect(opened.status).toBe(201);
    expect(opened.headers.get("retry-after")).toBeNull();
    const created = (await opened.json()) as {
      session: Record<string, unknown>;
    };
    expect(created.session.state).toBe("open");
    const metadata = await fetchWorker(
      `/v1/device-sessions/${created.session.id as string}`,
      { headers: authenticatedHeaders },
      missingR2
    );
    expect(metadata.status).toBe(200);
    expect((await metadata.json()) as object).toEqual({
      session: created.session,
    });
    const completed = await fetchWorker(
      `/v1/device-sessions/${created.session.id as string}/complete`,
      { method: "POST", headers: authenticatedHeaders },
      missingR2
    );
    expect(completed.status).toBe(200);
    expect(completed.headers.get("retry-after")).toBeNull();
    expect((await completed.json()) as object).toMatchObject({
      session: { id: created.session.id, state: "complete" },
    });
    const audio = await fetchWorker(
      `/v1/device-sessions/${created.session.id as string}/audio`,
      {
        method: "POST",
        headers: authenticatedHeaders,
        body: JSON.stringify({
          chunks: [{ chunkIndex: 0, bytesBase64: btoa("abc") }],
        }),
      },
      missingR2
    );
    expect(audio.status).toBe(503);
    expect(audio.headers.get("retry-after")).toBeNull();
    expect((await audio.json()) as object).toEqual({
      error: {
        code: "service_unavailable",
        retryable: false,
        action: "none",
      },
    });
  });

  test("capture write 409s use production Listen device_session_conflict", async () => {
    const conflict = {
      error: {
        code: "device_session_conflict",
        retryable: false,
        action: "edit_request",
      },
    };
    const opened = await fetchWorker("/v1/device-sessions", {
      method: "POST",
      headers: authenticatedHeaders,
      body: JSON.stringify(openBody),
    });
    expect(opened.status).toBe(201);
    const created = (await opened.json()) as { session: { id: string } };
    const metadata = await fetchWorker("/v1/device-sessions", {
      method: "POST",
      headers: authenticatedHeaders,
      body: JSON.stringify({ ...openBody, codec: 20 }),
    });
    expect(metadata.status).toBe(409);
    expect(metadata.headers.get("retry-after")).toBeNull();
    expect((await metadata.json()) as object).toEqual(conflict);
    const transcribe = await fetchWorker(
      `/v1/device-sessions/${created.session.id}/transcribe`,
      { method: "POST", headers: authenticatedHeaders }
    );
    expect(transcribe.status).toBe(409);
    expect(transcribe.headers.get("retry-after")).toBeNull();
    expect((await transcribe.json()) as object).toEqual({
      error: {
        code: "device_session_conflict",
        retryable: false,
        action: "retry",
      },
    });
    const audio = await fetchWorker(
      `/v1/device-sessions/${created.session.id}/audio`,
      {
        method: "POST",
        headers: authenticatedHeaders,
        body: JSON.stringify({
          chunks: [
            {
              chunkIndex: 0,
              bytesBase64: btoa(String.fromCharCode(0, 0, 0, 128, 129)),
            },
          ],
        }),
      }
    );
    expect(audio.status).toBe(200);
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
        body: JSON.stringify({
          chunks: [{ chunkIndex: 1, bytesBase64: btoa("late") }],
        }),
      }
    );
    expect(late.status).toBe(409);
    expect(late.headers.get("retry-after")).toBeNull();
    expect((await late.json()) as object).toEqual(conflict);
  });

  test("illegal capture envelopes use production Listen invalid_request", async () => {
    const invalid = {
      error: {
        code: "invalid_request",
        retryable: false,
        action: "edit_request",
      },
    };
    const opened = await fetchWorker("/v1/device-sessions", {
      method: "POST",
      headers: authenticatedHeaders,
      body: JSON.stringify({ ...openBody, codec: 256 }),
    });
    expect(opened.status).toBe(400);
    expect(opened.headers.get("retry-after")).toBeNull();
    expect((await opened.json()) as object).toEqual(invalid);
    const nulDevice = await fetchWorker("/v1/device-sessions", {
      method: "POST",
      headers: authenticatedHeaders,
      body: JSON.stringify({ ...openBody, deviceId: "AA:BB:\0CC:DD:EE:FF" }),
    });
    expect(nulDevice.status).toBe(400);
    expect(nulDevice.headers.get("retry-after")).toBeNull();
    expect((await nulDevice.json()) as object).toEqual(invalid);
    const malformed = await fetchWorker("/v1/device-sessions", {
      method: "POST",
      headers: authenticatedHeaders,
      body: "{",
    });
    expect(malformed.status).toBe(400);
    expect(malformed.headers.get("retry-after")).toBeNull();
    expect((await malformed.json()) as object).toEqual(invalid);
    const session = await fetchWorker("/v1/device-sessions", {
      method: "POST",
      headers: authenticatedHeaders,
      body: JSON.stringify(openBody),
    });
    expect(session.status).toBe(201);
    const created = (await session.json()) as { session: { id: string } };
    const audio = await fetchWorker(
      `/v1/device-sessions/${created.session.id}/audio`,
      {
        method: "POST",
        headers: authenticatedHeaders,
        body: JSON.stringify({
          chunkIndex: 0,
          bytesBase64: btoa(String.fromCharCode(1, 0, 0, 1)),
        }),
      }
    );
    expect(audio.status).toBe(400);
    expect(audio.headers.get("retry-after")).toBeNull();
    expect((await audio.json()) as object).toEqual(invalid);
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
      error: { code: "device_session_conflict" },
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
  test("ownership requires authentication and stays unavailable without canonical account epochs", async () => {
    expect((await fetchWorker("/v1/device-sessions/ownership")).status).toBe(
      401
    );
    const response = await fetchWorker("/v1/device-sessions/ownership", {
      headers: authenticatedHeaders,
    });
    expect(response.status).toBe(503);
    expect((await response.json()) as object).toEqual({
      error: {
        code: "capture_ownership_unavailable",
        retryable: false,
        action: "none",
      },
    });
  });
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
          chunks: [
            {
              chunkIndex: 0,
              bytesBase64: btoa(String.fromCharCode(...payload)),
            },
          ],
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
        body: JSON.stringify({
          chunks: [{ chunkIndex: 0, bytesBase64: btoa("abc") }],
        }),
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
    expect(missingR2.status).toBe(201);
    expect(missingR2.headers.get("retry-after")).toBeNull();
    expect((await missingR2.json()) as object).toEqual({
      session: created.session,
    });
    const missingR2Audio = await fetchWorker(
      `/v1/device-sessions/${created.session.id}/audio`,
      {
        method: "POST",
        headers: authenticatedHeaders,
        body: JSON.stringify({
          chunks: [{ chunkIndex: 0, bytesBase64: btoa("abc") }],
        }),
      },
      { ...env, ATTACHMENTS: undefined }
    );
    expect(missingR2Audio.status).toBe(503);
    expect(missingR2Audio.headers.get("retry-after")).toBeNull();
    expect((await missingR2Audio.json()) as object).toEqual({
      error: {
        code: "service_unavailable",
        retryable: false,
        action: "none",
      },
    });
    const missingR2Complete = await fetchWorker(
      `/v1/device-sessions/${created.session.id}/complete`,
      { method: "POST", headers: authenticatedHeaders },
      { ...env, ATTACHMENTS: undefined }
    );
    expect(missingR2Complete.status).toBe(200);
    expect(missingR2Complete.headers.get("retry-after")).toBeNull();
    expect((await missingR2Complete.json()) as object).toMatchObject({
      session: { id: created.session.id, state: "complete" },
    });
    const missingR2List = await fetchWorker(
      "/v1/device-sessions",
      { headers: authenticatedHeaders },
      { ...env, ATTACHMENTS: undefined }
    );
    expect(missingR2List.status).toBe(503);
    expect((await missingR2List.json()) as object).toEqual({
      error: {
        code: "service_unavailable",
        retryable: false,
        action: "none",
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
    expect(
      (
        await fetchWorker(`/v1/device-sessions/${created.session.id}/audio`, {
          method: "POST",
          headers: authenticatedHeaders,
          body: JSON.stringify({
            chunkIndex: 0,
            bytesBase64: btoa(String.fromCharCode(...first)),
          }),
        })
      ).status
    ).toBe(400);
    const left = await fetchWorker(
      `/v1/device-sessions/${created.session.id}/audio`,
      {
        method: "POST",
        headers: authenticatedHeaders,
        body: JSON.stringify({
          chunks: [
            {
              chunkIndex: 0,
              bytesBase64: btoa(String.fromCharCode(...first)),
            },
            {
              chunkIndex: 1,
              bytesBase64: btoa(String.fromCharCode(...second)),
            },
          ],
        }),
      }
    );
    const right = await fetchWorker(
      `/v1/device-sessions/${created.session.id}/audio`,
      {
        method: "POST",
        headers: authenticatedHeaders,
        body: JSON.stringify({
          chunks: [
            {
              chunkIndex: 1,
              bytesBase64: btoa(String.fromCharCode(...second)),
            },
          ],
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
        body: JSON.stringify({
          chunks: [{ chunkIndex: 0, bytesBase64: btoa("late") }],
        }),
      }
    );
    expect(late.status).toBe(409);
    const lateBody = (await late.json()) as {
      error: { code: string };
      session?: unknown;
    };
    expect(lateBody.error.code).toBe("device_session_conflict");
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
        body: JSON.stringify({
          chunks: [{ chunkIndex: 0, bytesBase64: btoa("audio") }],
        }),
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
        body: JSON.stringify({
          chunks: [{ chunkIndex: 0, bytesBase64: btoa("audio") }],
        }),
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
        body: JSON.stringify({
          chunks: [{ chunkIndex: 0, bytesBase64: btoa("retry") }],
        }),
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

test("capture provenance preserves absence and exact millisecond bounds", () => {
  const create = {
    captureId: crypto.randomUUID(),
    deviceId: "pendant",
    codec: 1,
  };
  expect(parseDeviceSessionCreate(create)).not.toHaveProperty("capturedAtMs");
  for (const capturedAtMs of [0, 1, 8640000000000000]) {
    expect(
      parseDeviceSessionCreate({ ...create, capturedAtMs })?.capturedAtMs
    ).toBe(capturedAtMs);
  }
  for (const capturedAtMs of [
    null,
    -1,
    0.5,
    NaN,
    Infinity,
    "1",
    8640000000000001,
  ]) {
    expect(parseDeviceSessionCreate({ ...create, capturedAtMs })).toBeNull();
  }
});
