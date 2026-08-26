import { beforeAll, beforeEach, describe, expect, mock, test } from "bun:test";

import {
  ATTACHMENT_CAPABILITIES,
  bindAttachmentStatement,
  completeAttachment,
  consumeAttachmentIngest,
  createPresignedR2Url,
  parseAttachmentStageRequest,
  parseSignedUploadConfig,
  resolveAttachmentsForAdmit,
  stageAttachment,
  type AttachmentIngestMessage,
} from "../src/attachments";
import { CHAT_CAPABILITIES } from "../src/wire";
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

const validStageRequest = (opId: string) => ({
  opId,
  displayName: "report.pdf",
  mimeType: "application/pdf",
  sizeBytes: 1024,
});

const sentMessages: unknown[] = [];
let d1Mock: D1Database;
let r2Mock: ReturnType<typeof createR2Mock>;

type R2MockObject = {
  size: number;
  contentType: string | undefined;
};

function createR2Mock(): R2Bucket & {
  objects: Map<string, R2MockObject>;
  putObject(key: string, size: number, contentType: string | undefined): void;
} {
  const objects = new Map<string, R2MockObject>();
  const bucket = {
    objects,
    putObject(key: string, size: number, contentType: string | undefined) {
      objects.set(key, { size, contentType });
    },
    async head(key: string) {
      const obj = objects.get(key);
      if (obj === undefined) return null;
      return {
        key,
        size: obj.size,
        httpMetadata: { contentType: obj.contentType },
      } as never;
    },
    async get() {
      throw new Error("R2 get not supported in mock");
    },
    async put() {
      throw new Error("R2 put not supported in mock");
    },
    async delete() {},
    async list() {
      return { objects: [], truncated: false } as never;
    },
  } as never;
  return bucket;
}

const r2SigningConfig = {
  R2_ACCOUNT_ID: "test-r2-account",
  R2_BUCKET_NAME: "omi-v5-backend-test-attachments",
  R2_ACCESS_KEY_ID: "test-access-key-id",
  R2_SECRET_ACCESS_KEY: "test-secret-access-key",
  R2_SIGNED_URL_TTL_SECONDS: "900",
};

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
  ATTACHMENT_INGEST: {
    send: async (message: unknown) => {
      sentMessages.push(message);
      return {} as never;
    },
  } as unknown as Queue,
  ...r2SigningConfig,
  get DB() {
    return d1Mock;
  },
};

const executionContext = {
  waitUntil: (_promise: Promise<unknown>) => undefined,
  passThroughOnException: () => undefined,
  props: {},
};

const fetchWorker = (path: string, init?: RequestInit) =>
  handler.fetch(
    new Request(`https://worker.test${path}`, init),
    env as never,
    executionContext as never
  );

beforeEach(() => {
  d1Mock = createD1Mock();
  r2Mock = createR2Mock();
  sentMessages.length = 0;
});

describe("attachment staging request validator", () => {
  test("accepts a bounded canonical metadata request", () => {
    expect(
      parseAttachmentStageRequest(validStageRequest("op-1"))
    ).not.toBeNull();
  });

  test.each([
    [null],
    [[]],
    [{ ...validStageRequest("op-1"), opId: "" }],
    [{ ...validStageRequest("op-1"), displayName: "" }],
    [{ ...validStageRequest("op-1"), mimeType: "" }],
    [{ ...validStageRequest("op-1"), mimeType: "text/html" }],
    [{ ...validStageRequest("op-1"), mimeType: "application/x-msdownload" }],
    [{ ...validStageRequest("op-1"), sizeBytes: 0 }],
    [{ ...validStageRequest("op-1"), sizeBytes: -1 }],
    [{ ...validStageRequest("op-1"), sizeBytes: 1.5 }],
    [
      {
        ...validStageRequest("op-1"),
        sizeBytes: ATTACHMENT_CAPABILITIES.maxAttachmentBytes + 1,
      },
    ],
    [{ ...validStageRequest("op-1"), displayName: "x".repeat(257) }],
  ])(
    "rejects unsupported or malformed attachment metadata",
    (value: unknown) => {
      expect(parseAttachmentStageRequest(value)).toBeNull();
    }
  );
});

describe("signed upload config parser", () => {
  test("accepts a complete non-secret config plus secret bindings", () => {
    expect(parseSignedUploadConfig(r2SigningConfig)).not.toBeNull();
  });

  test.each([
    [{ ...r2SigningConfig, R2_ACCOUNT_ID: "" }],
    [{ ...r2SigningConfig, R2_ACCOUNT_ID: "bad host!" }],
    [{ ...r2SigningConfig, R2_BUCKET_NAME: "" }],
    [{ ...r2SigningConfig, R2_BUCKET_NAME: "UPPERCASE" }],
    [{ ...r2SigningConfig, R2_ACCESS_KEY_ID: "" }],
    [{ ...r2SigningConfig, R2_ACCESS_KEY_ID: "bad key!" }],
    [{ ...r2SigningConfig, R2_SECRET_ACCESS_KEY: "" }],
    [{ ...r2SigningConfig, R2_SIGNED_URL_TTL_SECONDS: "0" }],
    [{ ...r2SigningConfig, R2_SIGNED_URL_TTL_SECONDS: "-1" }],
    [{ ...r2SigningConfig, R2_SIGNED_URL_TTL_SECONDS: "1.5" }],
    [{ ...r2SigningConfig, R2_SIGNED_URL_TTL_SECONDS: "100000" }],
    [{ ...r2SigningConfig, R2_ACCESS_KEY_ID: undefined }],
    [{ ...r2SigningConfig, R2_SECRET_ACCESS_KEY: undefined }],
    [{ ...r2SigningConfig, R2_ACCOUNT_ID: undefined }],
    [{ ...r2SigningConfig, R2_BUCKET_NAME: undefined }],
  ])("rejects incomplete or malformed signing config", (value: unknown) => {
    expect(parseSignedUploadConfig(value as never)).toBeNull();
  });

  test("applies the default TTL when unset", () => {
    const { R2_SIGNED_URL_TTL_SECONDS: _omit, ...rest } = r2SigningConfig;
    void _omit;
    const config = parseSignedUploadConfig(rest);
    expect(config).not.toBeNull();
    expect(config!.ttlSeconds).toBe(900);
  });
});

describe("attachment staging D1 canonical metadata", () => {
  test("writes canonical metadata to D1 with staged state", async () => {
    const result = await stageAttachment(
      d1Mock,
      "test-account",
      validStageRequest("op-d1-write"),
      ATTACHMENT_CAPABILITIES,
      "attachments"
    );

    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(result.created).toBe(true);
    expect(result.response.attachment.state).toBe("staged");
    expect(result.response.attachment.mimeType).toBe("application/pdf");
    expect(result.response.attachment.sizeBytes).toBe(1024);
    expect(result.response.upload.key).toMatch(
      /^attachments\/test-account\/[0-9a-f-]+$/
    );
    expect(result.response.upload.url).toBeNull();

    const row = await d1Mock
      .prepare(
        "SELECT id, account_id, display_name, media_type, size_bytes, state, r2_key FROM chat_attachments WHERE op_id = ?"
      )
      .bind("op-d1-write")
      .first<{
        id: string;
        account_id: string;
        display_name: string;
        media_type: string;
        size_bytes: number;
        state: string;
        r2_key: string;
      }>();
    expect(row).not.toBeNull();
    expect(row!.account_id).toBe("test-account");
    expect(row!.display_name).toBe("report.pdf");
    expect(row!.media_type).toBe("application/pdf");
    expect(row!.size_bytes).toBe(1024);
    expect(row!.state).toBe("staged");
    expect(row!.r2_key).toBe(result.response.upload.key);
  });

  test("idempotent replay returns the same attachment without duplicating D1 rows", async () => {
    const request = validStageRequest("op-idempotent");
    const first = await stageAttachment(
      d1Mock,
      "test-account",
      request,
      ATTACHMENT_CAPABILITIES,
      "attachments"
    );
    const replay = await stageAttachment(
      d1Mock,
      "test-account",
      request,
      ATTACHMENT_CAPABILITIES,
      "attachments"
    );

    expect(first.kind).toBe("ok");
    expect(replay.kind).toBe("ok");
    if (first.kind !== "ok" || replay.kind !== "ok") return;
    expect(first.created).toBe(true);
    expect(replay.created).toBe(false);
    expect(replay.response.attachment.id).toBe(first.response.attachment.id);
    expect(replay.response.upload.key).toBe(first.response.upload.key);

    const count = await d1Mock
      .prepare("SELECT COUNT(*) as count FROM chat_attachments WHERE op_id = ?")
      .bind("op-idempotent")
      .first<{ count: number }>();
    expect(count!.count).toBe(1);
  });

  test("same opId with different metadata returns conflict", async () => {
    await stageAttachment(
      d1Mock,
      "test-account",
      validStageRequest("op-conflict"),
      ATTACHMENT_CAPABILITIES,
      "attachments"
    );
    const conflict = await stageAttachment(
      d1Mock,
      "test-account",
      { ...validStageRequest("op-conflict"), displayName: "different.pdf" },
      ATTACHMENT_CAPABILITIES,
      "attachments"
    );
    expect(conflict).toEqual({ kind: "conflict" });
  });

  test("account isolation: foreign-account attachments are not visible", async () => {
    await stageAttachment(
      d1Mock,
      "own-account",
      validStageRequest("op-isolation"),
      ATTACHMENT_CAPABILITIES,
      "attachments"
    );
    await d1Mock
      .prepare(
        "INSERT INTO chat_attachments (id, account_id, op_id, display_name, media_type, size_bytes, state, r2_key, expires_at, bound_message_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'staged', ?, ?, NULL, ?, ?)"
      )
      .bind(
        "foreign-id",
        "foreign-account",
        "op-foreign",
        "foreign.pdf",
        "application/pdf",
        512,
        "attachments/foreign-account/foreign-id",
        Date.now() + 86400000,
        Date.now(),
        Date.now()
      )
      .run();

    const ownRow = await d1Mock
      .prepare(
        "SELECT id, account_id FROM chat_attachments WHERE account_id = ? AND op_id = ?"
      )
      .bind("own-account", "op-isolation")
      .first<{ id: string; account_id: string }>();
    expect(ownRow).not.toBeNull();
    expect(ownRow!.account_id).toBe("own-account");

    const crossAccount = await d1Mock
      .prepare(
        "SELECT id FROM chat_attachments WHERE account_id = ? AND op_id = ?"
      )
      .bind("own-account", "op-foreign")
      .first<{ id: string }>();
    expect(crossAccount).toBeNull();
  });
});

describe("attachment staging route fail-closed behavior", () => {
  test("returns 503 when R2 binding is absent", async () => {
    const response = await handler.fetch(
      new Request("https://worker.test/v1/chat-attachments", {
        method: "POST",
        headers: {
          ...authenticatedHeaders,
          "content-type": "application/json",
        },
        body: JSON.stringify(validStageRequest("op-no-r2")),
      }),
      { ...env, ATTACHMENTS: undefined } as never,
      executionContext as never
    );

    expect(response.status).toBe(503);
    const body = (await response.json()) as {
      error: { code: string; retryable: boolean };
    };
    expect(body.error.code).toBe("service_unavailable");
    expect(body.error.retryable).toBe(true);
  });

  test("stages successfully when Queue binding is absent and sends no queue message (no queue send at staging)", async () => {
    const response = await handler.fetch(
      new Request("https://worker.test/v1/chat-attachments", {
        method: "POST",
        headers: {
          ...authenticatedHeaders,
          "content-type": "application/json",
        },
        body: JSON.stringify(validStageRequest("op-no-queue")),
      }),
      { ...env, ATTACHMENT_INGEST: undefined } as never,
      executionContext as never
    );

    expect(response.status).toBe(201);
    expect(sentMessages).toHaveLength(0);
  });

  test("returns 503 and writes no D1 row or queue message when R2 signing config is absent", async () => {
    const { R2_ACCESS_KEY_ID: _omit, ...envWithoutSecret } = env;
    void _omit;
    const response = await handler.fetch(
      new Request("https://worker.test/v1/chat-attachments", {
        method: "POST",
        headers: {
          ...authenticatedHeaders,
          "content-type": "application/json",
        },
        body: JSON.stringify(validStageRequest("op-no-signing-config")),
      }),
      envWithoutSecret as never,
      executionContext as never
    );

    expect(response.status).toBe(503);
    const body = (await response.json()) as {
      error: { code: string; retryable: boolean };
    };
    expect(body.error.code).toBe("service_unavailable");
    expect(body.error.retryable).toBe(true);

    const row = await d1Mock
      .prepare("SELECT id FROM chat_attachments WHERE op_id = ?")
      .bind("op-no-signing-config")
      .first<{ id: string }>();
    expect(row).toBeNull();
    expect(sentMessages).toHaveLength(0);
  });

  test("returns 503 and writes no D1 row when R2 account id is empty", async () => {
    const response = await handler.fetch(
      new Request("https://worker.test/v1/chat-attachments", {
        method: "POST",
        headers: {
          ...authenticatedHeaders,
          "content-type": "application/json",
        },
        body: JSON.stringify(validStageRequest("op-empty-r2-account")),
      }),
      { ...env, R2_ACCOUNT_ID: "" } as never,
      executionContext as never
    );

    expect(response.status).toBe(503);
    const row = await d1Mock
      .prepare("SELECT id FROM chat_attachments WHERE op_id = ?")
      .bind("op-empty-r2-account")
      .first<{ id: string }>();
    expect(row).toBeNull();
    expect(sentMessages).toHaveLength(0);
  });

  test("returns 422 for unsupported MIME type through the route", async () => {
    const response = await fetchWorker("/v1/chat-attachments", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify({
        ...validStageRequest("op-bad-mime"),
        mimeType: "text/html",
      }),
    });

    expect(response.status).toBe(422);
    const body = (await response.json()) as {
      error: { code: string; action: string };
    };
    expect(body.error.code).toBe("attachment_rejected");
    expect(body.error.action).toBe("edit_request");
  });

  test("returns 422 for oversized attachment through the route", async () => {
    const response = await fetchWorker("/v1/chat-attachments", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify({
        ...validStageRequest("op-oversized"),
        sizeBytes: ATTACHMENT_CAPABILITIES.maxAttachmentBytes + 1,
      }),
    });

    expect(response.status).toBe(422);
  });

  test("stages successfully when all bindings and signing config are present, returns a usable signed URL, and sends no queue message", async () => {
    const response = await fetchWorker("/v1/chat-attachments", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify(validStageRequest("op-happy")),
    });

    expect(response.status).toBe(201);
    const body = (await response.json()) as {
      attachment: {
        id: string;
        mimeType: string;
        sizeBytes: number;
        state: string;
        expiresAt: string;
      };
      upload: {
        method: string;
        url: string | null;
        key: string;
        expiresAt: string;
      };
    };
    expect(body.attachment.state).toBe("staged");
    expect(body.attachment.mimeType).toBe("application/pdf");
    expect(body.upload.method).toBe("PUT");
    expect(body.upload.url).not.toBeNull();
    expect(body.upload.url).toMatch(
      /^https:\/\/test-r2-account\.r2\.cloudflarestorage\.com\/omi-v5-backend-test-attachments\/attachments\/test-account\/[0-9a-f-]+\?/
    );
    const url = new URL(body.upload.url!);
    expect(url.searchParams.get("X-Amz-Algorithm")).toBe("AWS4-HMAC-SHA256");
    expect(url.searchParams.get("X-Amz-Credential")).toContain(
      "test-access-key-id"
    );
    expect(url.searchParams.get("X-Amz-Expires")).toBe("900");
    expect(url.searchParams.get("X-Amz-Signature")).toMatch(/^[0-9a-f]{64}$/);
    expect(body.upload.key).toMatch(/^attachments\/test-account\//);
    expect(body.upload.key).toBe(
      body.upload
        .url!.split("?")[0]!
        .replace(
          "https://test-r2-account.r2.cloudflarestorage.com/omi-v5-backend-test-attachments/",
          ""
        )
    );

    expect(sentMessages).toHaveLength(0);
  });

  test("idempotent replay through the route returns 200, same attachment id, and a fresh signed URL", async () => {
    const init = {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify(validStageRequest("op-route-idempotent")),
    } as const;

    const first = await fetchWorker("/v1/chat-attachments", init);
    const firstBody = (await first.json()) as {
      attachment: { id: string };
      upload: { url: string | null };
    };
    expect(first.status).toBe(201);
    expect(firstBody.upload.url).not.toBeNull();

    const replay = await fetchWorker("/v1/chat-attachments", init);
    const replayBody = (await replay.json()) as {
      attachment: { id: string };
      upload: { url: string | null };
    };
    expect(replay.status).toBe(200);
    expect(replayBody.attachment.id).toBe(firstBody.attachment.id);
    expect(replayBody.upload.url).not.toBeNull();
    expect(replayBody.upload.url).toMatch(
      /^https:\/\/test-r2-account\.r2\.cloudflarestorage\.com\//
    );
  });

  test("does not leak credentials or signed URL to logs", async () => {
    const logCalls: string[] = [];
    const errorCalls: string[] = [];
    const originalLog = console.log;
    const originalError = console.error;
    console.log = (...args: unknown[]) => {
      logCalls.push(args.map(String).join(" "));
    };
    console.error = (...args: unknown[]) => {
      errorCalls.push(args.map(String).join(" "));
    };
    try {
      const response = await fetchWorker("/v1/chat-attachments", {
        method: "POST",
        headers: {
          ...authenticatedHeaders,
          "content-type": "application/json",
        },
        body: JSON.stringify(validStageRequest("op-no-leak")),
      });
      expect(response.status).toBe(201);
    } finally {
      console.log = originalLog;
      console.error = originalError;
    }

    const allLogs = [...logCalls, ...errorCalls];
    for (const line of allLogs) {
      expect(line).not.toContain("test-access-key-id");
      expect(line).not.toContain("test-secret-access-key");
      expect(line).not.toContain("r2.cloudflarestorage.com");
      expect(line).not.toContain("X-Amz-Signature");
    }
  });

  test("capabilities reflect the ratified attachment policy", () => {
    expect(CHAT_CAPABILITIES.maxAttachmentsPerMessage).toBe(4);
    expect(CHAT_CAPABILITIES.maxAttachmentBytes).toBe(52_428_800);
    expect(CHAT_CAPABILITIES.allowedAttachmentMimeTypes).toContain(
      "application/pdf"
    );
    expect(CHAT_CAPABILITIES.allowedAttachmentMimeTypes).toContain(
      "text/plain"
    );
  });
});

describe("presigned R2 upload contract seam", () => {
  test("produces a well-formed presigned PUT URL with SigV4 parameters", async () => {
    const url = await createPresignedR2Url({
      r2AccountId: "test-account-id",
      bucketName: "test-bucket",
      key: "attachments/test-account/attachment-1",
      accessKeyId: "test-access-key",
      secretAccessKey: "test-secret-key",
      expiresIn: 3600,
    });

    expect(url).toMatch(
      /^https:\/\/test-account-id\.r2\.cloudflarestorage\.com\/test-bucket\/attachments\/test-account\/attachment-1\?/
    );
    const params = new URL(url).searchParams;
    expect(params.get("X-Amz-Algorithm")).toBe("AWS4-HMAC-SHA256");
    expect(params.get("X-Amz-Credential")).toContain("test-access-key");
    expect(params.get("X-Amz-Date")).toMatch(/^\d{8}T\d{6}Z$/);
    expect(params.get("X-Amz-Expires")).toBe("3600");
    expect(params.get("X-Amz-SignedHeaders")).toBe("host");
    expect(params.get("X-Amz-Signature")).toMatch(/^[0-9a-f]{64}$/);
  });

  test("different keys produce different signatures", async () => {
    const urlA = await createPresignedR2Url({
      r2AccountId: "acct",
      bucketName: "bucket",
      key: "attachments/acct/a",
      accessKeyId: "key",
      secretAccessKey: "secret",
      expiresIn: 3600,
    });
    const urlB = await createPresignedR2Url({
      r2AccountId: "acct",
      bucketName: "bucket",
      key: "attachments/acct/b",
      accessKeyId: "key",
      secretAccessKey: "secret",
      expiresIn: 3600,
    });
    const sigA = new URL(urlA).searchParams.get("X-Amz-Signature");
    const sigB = new URL(urlB).searchParams.get("X-Amz-Signature");
    expect(sigA).not.toBe(sigB);
  });
});

const stageAndReturn = async (
  opId: string,
  mimeType = "application/pdf",
  sizeBytes = 1024
) => {
  const response = await fetchWorker("/v1/chat-attachments", {
    method: "POST",
    headers: { ...authenticatedHeaders, "content-type": "application/json" },
    body: JSON.stringify({
      opId,
      displayName: "report.pdf",
      mimeType,
      sizeBytes,
    }),
  });
  expect(response.status).toBe(201);
  const body = (await response.json()) as {
    attachment: { id: string };
    upload: { key: string };
  };
  return body;
};

const completeRoute = (id: string) =>
  fetchWorker(`/v1/chat-attachments/${id}/complete`, {
    method: "POST",
    headers: { ...authenticatedHeaders, "content-type": "application/json" },
  });

const attachmentState = async (id: string) => {
  const row = await d1Mock
    .prepare("SELECT state FROM chat_attachments WHERE id = ?")
    .bind(id)
    .first<{ state: string }>();
  return row?.state ?? null;
};

function makeMessageBatch(
  messages: { id: string; body: AttachmentIngestMessage }[]
) {
  const acked: string[] = [];
  const retried: string[] = [];
  const batch = {
    queue: "omi-v5-test-attachment-ingest",
    messages: messages.map((m) => ({
      id: m.id,
      timestamp: new Date(0),
      attempts: 1,
      body: m.body,
      ack() {
        acked.push(m.id);
      },
      retry() {
        retried.push(m.id);
      },
    })),
    retryAll() {},
    ackAll() {},
    metadata: { metrics: {} },
  } as never;
  return { batch, acked, retried };
}

describe("attachment completion + queue ingest vertical slice", () => {
  test("complete returns 404 for an unknown attachment id", async () => {
    const response = await completeRoute(
      "00000000-0000-0000-0000-000000000000"
    );
    expect(response.status).toBe(404);
  });

  test("complete fails for an absent R2 object (never uploaded) and leaves state staged", async () => {
    const staged = await stageAndReturn("op-absent");
    const response = await completeRoute(staged.attachment.id);
    expect(response.status).toBe(422);
    const body = (await response.json()) as {
      error: { code: string; retryable: boolean };
    };
    expect(body.error.code).toBe("attachment_not_uploaded");
    expect(body.error.retryable).toBe(true);
    expect(await attachmentState(staged.attachment.id)).toBe("staged");
    expect(sentMessages).toHaveLength(0);
  });

  test("complete fails for a size-mismatched R2 object and marks state invalid", async () => {
    const staged = await stageAndReturn("op-size-mismatch");
    r2Mock.putObject(staged.upload.key, 999, "application/pdf");
    const response = await completeRoute(staged.attachment.id);
    expect(response.status).toBe(422);
    const body = (await response.json()) as {
      error: { code: string; retryable: boolean };
    };
    expect(body.error.code).toBe("attachment_metadata_mismatch");
    expect(body.error.retryable).toBe(false);
    expect(await attachmentState(staged.attachment.id)).toBe("invalid");
    expect(sentMessages).toHaveLength(0);
  });

  test("complete fails for a content-type-mismatched R2 object and marks state invalid", async () => {
    const staged = await stageAndReturn("op-ctype-mismatch");
    r2Mock.putObject(staged.upload.key, 1024, "image/png");
    const response = await completeRoute(staged.attachment.id);
    expect(response.status).toBe(422);
    expect(await attachmentState(staged.attachment.id)).toBe("invalid");
    expect(sentMessages).toHaveLength(0);
  });

  test("cross-account complete fails with 404 and does not touch the foreign row", async () => {
    const staged = await stageAndReturn("op-cross-account");
    r2Mock.putObject(staged.upload.key, 1024, "application/pdf");
    await d1Mock
      .prepare("UPDATE chat_attachments SET account_id = ? WHERE id = ?")
      .bind("other-account", staged.attachment.id)
      .run();

    const response = await completeRoute(staged.attachment.id);
    expect(response.status).toBe(404);
    const row = await d1Mock
      .prepare("SELECT state, account_id FROM chat_attachments WHERE id = ?")
      .bind(staged.attachment.id)
      .first<{ state: string; account_id: string }>();
    expect(row!.account_id).toBe("other-account");
    expect(row!.state).toBe("staged");
    expect(sentMessages).toHaveLength(0);
  });

  test("complete + queue consumer yields canonical ingested state", async () => {
    const staged = await stageAndReturn("op-e2e");
    r2Mock.putObject(staged.upload.key, 1024, "application/pdf");

    const completeResponse = await completeRoute(staged.attachment.id);
    expect(completeResponse.status).toBe(202);
    expect(await attachmentState(staged.attachment.id)).toBe("uploaded");
    expect(sentMessages).toHaveLength(1);

    const { batch, acked } = makeMessageBatch([
      {
        id: "msg-1",
        body: sentMessages[0] as AttachmentIngestMessage,
      },
    ]);
    await handler.queue!(batch, env as never);
    expect(acked).toEqual(["msg-1"]);
    expect(await attachmentState(staged.attachment.id)).toBe("ingested");
  });

  test("duplicate queue delivery is harmless: second consumer run is a no-op", async () => {
    const staged = await stageAndReturn("op-duplicate");
    r2Mock.putObject(staged.upload.key, 1024, "application/pdf");
    await completeRoute(staged.attachment.id);

    const message = sentMessages[0] as AttachmentIngestMessage;
    const first = makeMessageBatch([{ id: "msg-a", body: message }]);
    await handler.queue!(first.batch, env as never);
    expect(await attachmentState(staged.attachment.id)).toBe("ingested");

    const second = makeMessageBatch([{ id: "msg-b", body: message }]);
    await handler.queue!(second.batch, env as never);
    expect(second.acked).toEqual(["msg-b"]);
    expect(await attachmentState(staged.attachment.id)).toBe("ingested");

    const count = await d1Mock
      .prepare("SELECT COUNT(*) as count FROM chat_attachments WHERE id = ?")
      .bind(staged.attachment.id)
      .first<{ count: number }>();
    expect(count!.count).toBe(1);
  });

  test("re-enqueuing via a second complete call is harmless and consumer still reaches ingested", async () => {
    const staged = await stageAndReturn("op-requeue");
    r2Mock.putObject(staged.upload.key, 1024, "application/pdf");

    const first = await completeRoute(staged.attachment.id);
    expect(first.status).toBe(202);
    const second = await completeRoute(staged.attachment.id);
    expect(second.status).toBe(202);
    expect(sentMessages.length).toBeGreaterThanOrEqual(2);

    const { batch, acked } = makeMessageBatch([
      { id: "msg-r", body: sentMessages[0] as AttachmentIngestMessage },
    ]);
    await handler.queue!(batch, env as never);
    expect(acked).toEqual(["msg-r"]);
    expect(await attachmentState(staged.attachment.id)).toBe("ingested");
  });

  test("consumer marks state invalid when R2 object disappeared before delivery", async () => {
    const staged = await stageAndReturn("op-disappeared");
    r2Mock.putObject(staged.upload.key, 1024, "application/pdf");
    await completeRoute(staged.attachment.id);

    r2Mock.objects.delete(staged.upload.key);
    const { batch, acked } = makeMessageBatch([
      {
        id: "msg-gone",
        body: sentMessages[0] as AttachmentIngestMessage,
      },
    ]);
    await handler.queue!(batch, env as never);
    expect(acked).toEqual(["msg-gone"]);
    expect(await attachmentState(staged.attachment.id)).toBe("invalid");
  });

  test("consumer ignores a message for a non-existent attachment without error", async () => {
    const { batch, acked, retried } = makeMessageBatch([
      {
        id: "msg-ghost",
        body: {
          attachmentId: "00000000-0000-0000-0000-000000000000",
          accountId: "test-account",
          r2Key: "attachments/test-account/ghost",
          mimeType: "application/pdf",
        },
      },
    ]);
    await handler.queue!(batch, env as never);
    expect(acked).toEqual(["msg-ghost"]);
    expect(retried).toEqual([]);
  });

  test("complete returns 410 when staging TTL has expired", async () => {
    const staged = await stageAndReturn("op-expired");
    r2Mock.putObject(staged.upload.key, 1024, "application/pdf");
    await d1Mock
      .prepare("UPDATE chat_attachments SET expires_at = ? WHERE id = ?")
      .bind(Date.now() - 1000, staged.attachment.id)
      .run();

    const response = await completeRoute(staged.attachment.id);
    expect(response.status).toBe(410);
    expect(await attachmentState(staged.attachment.id)).toBe("expired");
    expect(sentMessages).toHaveLength(0);
  });

  test("completeAttachment unit: cross-account direct call does not affect foreign row", async () => {
    const staged = await stageAndReturn("op-unit-cross");
    r2Mock.putObject(staged.upload.key, 1024, "application/pdf");
    const outcome = await completeAttachment(
      d1Mock,
      r2Mock,
      env.ATTACHMENT_INGEST,
      "wrong-account",
      staged.attachment.id,
      Date.now()
    );
    expect(outcome.kind).toBe("not_found");
    expect(await attachmentState(staged.attachment.id)).toBe("staged");
  });

  test("consumeAttachmentIngest unit: cross-account message is skipped", async () => {
    const staged = await stageAndReturn("op-unit-cross-consume");
    r2Mock.putObject(staged.upload.key, 1024, "application/pdf");
    await d1Mock
      .prepare("UPDATE chat_attachments SET account_id = ? WHERE id = ?")
      .bind("other-account", staged.attachment.id)
      .run();
    const outcome = await consumeAttachmentIngest(
      d1Mock,
      r2Mock,
      {
        attachmentId: staged.attachment.id,
        accountId: "test-account",
        r2Key: staged.upload.key,
        mimeType: "application/pdf",
      },
      Date.now()
    );
    expect(outcome.kind).toBe("not_found");
    const row = await d1Mock
      .prepare("SELECT state, account_id FROM chat_attachments WHERE id = ?")
      .bind(staged.attachment.id)
      .first<{ state: string; account_id: string }>();
    expect(row!.account_id).toBe("other-account");
    expect(row!.state).toBe("staged");
  });
});

async function insertStoredAttachment(input: {
  id: string;
  accountId: string;
  state: string;
  boundMessageId?: string | null;
  displayName?: string;
  mimeType?: string;
  sizeBytes?: number;
}): Promise<void> {
  const now = Date.now();
  await d1Mock
    .prepare(
      "INSERT INTO chat_attachments (id, account_id, op_id, display_name, media_type, size_bytes, state, r2_key, expires_at, bound_message_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    .bind(
      input.id,
      input.accountId,
      `op-${input.id}`,
      input.displayName ?? "report.pdf",
      input.mimeType ?? "application/pdf",
      input.sizeBytes ?? 1024,
      input.state,
      `attachments/${input.accountId}/${input.id}`,
      now + 86_400_000,
      input.boundMessageId ?? null,
      now,
      now
    )
    .run();
}

describe("attachment admit bind", () => {
  test("zero attachments resolve as an empty bindable list", async () => {
    const resolved = await resolveAttachmentsForAdmit(
      d1Mock,
      "test-account",
      [],
      "message-none"
    );
    expect(resolved).toEqual({ kind: "ok", attachments: [] });
  });

  test("rejects unknown, foreign, and incomplete attachment ids", async () => {
    await insertStoredAttachment({
      id: "att-foreign",
      accountId: "other-account",
      state: "ingested",
    });
    await insertStoredAttachment({
      id: "att-staged",
      accountId: "test-account",
      state: "staged",
    });

    expect(
      await resolveAttachmentsForAdmit(
        d1Mock,
        "test-account",
        ["missing-id"],
        "message-missing"
      )
    ).toEqual({ kind: "rejected" });
    expect(
      await resolveAttachmentsForAdmit(
        d1Mock,
        "test-account",
        ["att-foreign"],
        "message-foreign"
      )
    ).toEqual({ kind: "rejected" });
    expect(
      await resolveAttachmentsForAdmit(
        d1Mock,
        "test-account",
        ["att-staged"],
        "message-staged"
      )
    ).toEqual({ kind: "rejected" });
  });

  test("accepts a completed same-account attachment and binds it", async () => {
    await insertStoredAttachment({
      id: "att-ready",
      accountId: "test-account",
      state: "ingested",
      displayName: "notes.pdf",
      mimeType: "application/pdf",
      sizeBytes: 2048,
    });

    const resolved = await resolveAttachmentsForAdmit(
      d1Mock,
      "test-account",
      ["att-ready"],
      "message-ready"
    );
    expect(resolved).toEqual({
      kind: "ok",
      attachments: [
        {
          id: "att-ready",
          displayName: "notes.pdf",
          mediaType: "application/pdf",
          sizeBytes: 2048,
          contentReference: "att-ready",
        },
      ],
    });

    if (resolved.kind !== "ok") return;
    await bindAttachmentStatement(
      d1Mock,
      "test-account",
      "message-ready",
      "att-ready",
      Date.now()
    ).run();
    const row = await d1Mock
      .prepare(
        "SELECT state, bound_message_id FROM chat_attachments WHERE id = ?"
      )
      .bind("att-ready")
      .first<{ state: string; bound_message_id: string | null }>();
    expect(row).toEqual({
      state: "bound",
      bound_message_id: "message-ready",
    });
  });

  test("replay of an already-bound same-message attachment is accepted", async () => {
    await insertStoredAttachment({
      id: "att-replay",
      accountId: "test-account",
      state: "bound",
      boundMessageId: "message-replay",
    });
    expect(
      await resolveAttachmentsForAdmit(
        d1Mock,
        "test-account",
        ["att-replay"],
        "message-replay"
      )
    ).toMatchObject({ kind: "ok" });
    expect(
      await resolveAttachmentsForAdmit(
        d1Mock,
        "test-account",
        ["att-replay"],
        "message-other"
      )
    ).toEqual({ kind: "rejected" });
  });
});
