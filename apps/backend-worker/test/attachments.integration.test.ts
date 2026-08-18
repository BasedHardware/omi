import {
  createExecutionContext,
  createMessageBatch,
  getQueueResult,
} from "cloudflare:test";
import { env } from "cloudflare:workers";
import { beforeEach, describe, expect, test } from "vitest";

import handler from "../src/index";
import type { AttachmentIngestMessage } from "../src/attachments";

const attachmentSchema = [
  "CREATE TABLE IF NOT EXISTS chat_attachments (id TEXT PRIMARY KEY, account_id TEXT NOT NULL, op_id TEXT NOT NULL, display_name TEXT NOT NULL, media_type TEXT NOT NULL, size_bytes INTEGER NOT NULL, state TEXT NOT NULL CHECK (state IN ('staged', 'uploaded', 'ingesting', 'ingested', 'invalid', 'bound', 'expired')), r2_key TEXT NOT NULL, expires_at INTEGER NOT NULL, bound_message_id TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)",
  "CREATE INDEX IF NOT EXISTS chat_attachments_account ON chat_attachments (account_id)",
  "CREATE INDEX IF NOT EXISTS chat_attachments_account_state ON chat_attachments (account_id, state)",
  "CREATE UNIQUE INDEX IF NOT EXISTS chat_attachments_account_op ON chat_attachments (account_id, op_id)",
  "CREATE UNIQUE INDEX IF NOT EXISTS chat_attachments_r2_key ON chat_attachments (r2_key)",
];

const authenticatedHeaders = {
  authorization: "Bearer test-token",
  "x-omi-client-id": "test-client",
};

const validStageRequest = (opId: string) => ({
  opId,
  displayName: "photo.png",
  mimeType: "image/png",
  sizeBytes: 2048,
});

const fetchWorker = (path: string, init?: RequestInit) =>
  handler.fetch(
    new Request(`https://worker.test${path}`, init),
    {
      ...env,
      API_TOKEN: "test-token",
      AI: { run: async () => ({ response: "AI reply" }) },
      R2_ACCESS_KEY_ID: "test-access-key-id",
      R2_SECRET_ACCESS_KEY: "test-secret-access-key",
    } as never,
    createExecutionContext()
  );

beforeEach(async () => {
  for (const statement of attachmentSchema) {
    await env.DB.exec(statement);
  }
  await env.DB.prepare("DELETE FROM chat_attachments").run();
});

describe("D1-authoritative attachment staging integration", () => {
  test("staging writes canonical metadata to D1 and returns a staging contract", async () => {
    const response = await fetchWorker("/v1/chat-attachments", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify(validStageRequest("int-stage-1")),
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
      upload: { method: string; url: string | null; key: string };
    };
    expect(body.attachment.state).toBe("staged");
    expect(body.attachment.mimeType).toBe("image/png");
    expect(body.attachment.sizeBytes).toBe(2048);
    expect(body.upload.method).toBe("PUT");
    expect(body.upload.url).not.toBeNull();
    expect(body.upload.url).toMatch(
      /^https:\/\/test-r2-account\.r2\.cloudflarestorage\.com\/omi-v5-backend-test-attachments\/attachments\/test-account\//
    );
    expect(body.upload.key).toMatch(/^attachments\/test-account\//);

    const row = await env.DB.prepare(
      "SELECT id, account_id, display_name, media_type, size_bytes, state, r2_key FROM chat_attachments WHERE op_id = ?"
    )
      .bind("int-stage-1")
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
    expect(row!.display_name).toBe("photo.png");
    expect(row!.media_type).toBe("image/png");
    expect(row!.size_bytes).toBe(2048);
    expect(row!.state).toBe("staged");
    expect(row!.r2_key).toBe(body.upload.key);
    expect(row!.id).toBe(body.attachment.id);
  });

  test("idempotent replay returns 200 and the same attachment id without duplication", async () => {
    const init = {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify(validStageRequest("int-replay-1")),
    } as const;

    const first = await fetchWorker("/v1/chat-attachments", init);
    expect(first.status).toBe(201);
    const firstBody = (await first.json()) as { attachment: { id: string } };

    const replay = await fetchWorker("/v1/chat-attachments", init);
    expect(replay.status).toBe(200);
    const replayBody = (await replay.json()) as { attachment: { id: string } };
    expect(replayBody.attachment.id).toBe(firstBody.attachment.id);

    const count = await env.DB.prepare(
      "SELECT COUNT(*) as count FROM chat_attachments WHERE op_id = ?"
    )
      .bind("int-replay-1")
      .first<{ count: number }>();
    expect(count!.count).toBe(1);
  });

  test("account isolation excludes foreign-account staged attachments", async () => {
    await fetchWorker("/v1/chat-attachments", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify(validStageRequest("int-own-1")),
    });

    await env.DB.prepare(
      "INSERT INTO chat_attachments (id, account_id, op_id, display_name, media_type, size_bytes, state, r2_key, expires_at, bound_message_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'staged', ?, ?, NULL, ?, ?)"
    )
      .bind(
        "foreign-attachment-id",
        "other-account",
        "op-foreign",
        "foreign.png",
        "image/png",
        512,
        "attachments/other-account/foreign-attachment-id",
        Date.now() + 86400000,
        Date.now(),
        Date.now()
      )
      .run();

    const ownRow = await env.DB.prepare(
      "SELECT id FROM chat_attachments WHERE account_id = ? AND op_id = ?"
    )
      .bind("test-account", "int-own-1")
      .first<{ id: string }>();
    expect(ownRow).not.toBeNull();

    const foreignLeak = await env.DB.prepare(
      "SELECT id FROM chat_attachments WHERE account_id = ? AND op_id = ?"
    )
      .bind("test-account", "op-foreign")
      .first<{ id: string }>();
    expect(foreignLeak).toBeNull();
  });

  test("unsupported MIME type is rejected with 422 attachment_rejected", async () => {
    const response = await fetchWorker("/v1/chat-attachments", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify({
        ...validStageRequest("int-bad-mime"),
        mimeType: "text/html",
      }),
    });

    expect(response.status).toBe(422);
    const body = (await response.json()) as {
      error: { code: string; action: string };
    };
    expect(body.error.code).toBe("attachment_rejected");
    expect(body.error.action).toBe("edit_request");

    const count = await env.DB.prepare(
      "SELECT COUNT(*) as count FROM chat_attachments WHERE op_id = ?"
    )
      .bind("int-bad-mime")
      .first<{ count: number }>();
    expect(count!.count).toBe(0);
  });

  test("oversized attachment is rejected before D1 write", async () => {
    const response = await fetchWorker("/v1/chat-attachments", {
      method: "POST",
      headers: { ...authenticatedHeaders, "content-type": "application/json" },
      body: JSON.stringify({
        ...validStageRequest("int-oversized"),
        sizeBytes: 52_428_801,
      }),
    });

    expect(response.status).toBe(422);
  });
});

const stageViaRoute = async (
  opId: string,
  mimeType = "image/png",
  sizeBytes = 2048
) => {
  const response = await fetchWorker("/v1/chat-attachments", {
    method: "POST",
    headers: { ...authenticatedHeaders, "content-type": "application/json" },
    body: JSON.stringify({
      opId,
      displayName: "photo.png",
      mimeType,
      sizeBytes,
    }),
  });
  expect(response.status).toBe(201);
  return (await response.json()) as {
    attachment: { id: string };
    upload: { key: string };
  };
};

const completeViaRoute = (id: string) =>
  fetchWorker(`/v1/chat-attachments/${id}/complete`, {
    method: "POST",
    headers: { ...authenticatedHeaders, "content-type": "application/json" },
  });

const readState = async (id: string) => {
  const row = await env.DB.prepare(
    "SELECT state, account_id, size_bytes, media_type, r2_key FROM chat_attachments WHERE id = ?"
  )
    .bind(id)
    .first<{
      state: string;
      account_id: string;
      size_bytes: number;
      media_type: string;
      r2_key: string;
    }>();
  return row;
};

async function runConsumer(
  message: AttachmentIngestMessage
): Promise<{ acked: string[]; retried: string[] }> {
  const ctx = createExecutionContext();
  const batch = createMessageBatch<AttachmentIngestMessage>(
    "omi-v5-test-attachment-ingest",
    [
      {
        id: "msg-" + Math.random().toString(36).slice(2),
        timestamp: new Date(0),
        attempts: 1,
        body: message,
      },
    ]
  );
  await handler.queue!(batch, env as never);
  const result = await getQueueResult(batch, ctx);
  return {
    acked: result.explicitAcks,
    retried: result.retryMessages.map((m: { msgId: string }) => m.msgId),
  };
}

describe("D1-authoritative attachment completion + queue ingest integration", () => {
  test("complete + queue consumer yields canonical ingested state with real R2", async () => {
    const staged = await stageViaRoute("int-complete-1");
    const bytes = new Uint8Array(2048);
    await env.ATTACHMENTS.put(staged.upload.key, bytes, {
      httpMetadata: { contentType: "image/png" },
    });

    const completeResponse = await completeViaRoute(staged.attachment.id);
    expect(completeResponse.status).toBe(202);
    let row = await readState(staged.attachment.id);
    expect(row!.state).toBe("uploaded");

    const outcome = await runConsumer({
      attachmentId: staged.attachment.id,
      accountId: "test-account",
      r2Key: staged.upload.key,
      mimeType: "image/png",
    });
    expect(outcome.acked).toHaveLength(1);
    expect(outcome.retried).toHaveLength(0);

    row = await readState(staged.attachment.id);
    expect(row!.state).toBe("ingested");
    expect(row!.account_id).toBe("test-account");
  });

  test("complete fails for an absent R2 object and leaves state staged", async () => {
    const staged = await stageViaRoute("int-absent-1");
    const response = await completeViaRoute(staged.attachment.id);
    expect(response.status).toBe(422);
    const body = (await response.json()) as {
      error: { code: string; retryable: boolean };
    };
    expect(body.error.code).toBe("attachment_not_uploaded");
    expect(body.error.retryable).toBe(true);
    const row = await readState(staged.attachment.id);
    expect(row!.state).toBe("staged");
  });

  test("complete fails for a size-mismatched R2 object and marks state invalid", async () => {
    const staged = await stageViaRoute("int-mismatch-1");
    await env.ATTACHMENTS.put(staged.upload.key, new Uint8Array(100), {
      httpMetadata: { contentType: "image/png" },
    });
    const response = await completeViaRoute(staged.attachment.id);
    expect(response.status).toBe(422);
    const row = await readState(staged.attachment.id);
    expect(row!.state).toBe("invalid");
  });

  test("complete fails for a content-type-mismatched R2 object and marks state invalid", async () => {
    const staged = await stageViaRoute("int-ctype-1");
    await env.ATTACHMENTS.put(staged.upload.key, new Uint8Array(2048), {
      httpMetadata: { contentType: "application/pdf" },
    });
    const response = await completeViaRoute(staged.attachment.id);
    expect(response.status).toBe(422);
    const row = await readState(staged.attachment.id);
    expect(row!.state).toBe("invalid");
  });

  test("cross-account complete fails with 404 and does not touch the foreign row", async () => {
    const staged = await stageViaRoute("int-cross-1");
    await env.ATTACHMENTS.put(staged.upload.key, new Uint8Array(2048), {
      httpMetadata: { contentType: "image/png" },
    });
    await env.DB.prepare(
      "UPDATE chat_attachments SET account_id = ? WHERE id = ?"
    )
      .bind("other-account", staged.attachment.id)
      .run();

    const response = await completeViaRoute(staged.attachment.id);
    expect(response.status).toBe(404);
    const row = await readState(staged.attachment.id);
    expect(row!.account_id).toBe("other-account");
    expect(row!.state).toBe("staged");
  });

  test("duplicate queue delivery is harmless: second consumer run is a no-op", async () => {
    const staged = await stageViaRoute("int-dup-1");
    await env.ATTACHMENTS.put(staged.upload.key, new Uint8Array(2048), {
      httpMetadata: { contentType: "image/png" },
    });
    await completeViaRoute(staged.attachment.id);

    const message: AttachmentIngestMessage = {
      attachmentId: staged.attachment.id,
      accountId: "test-account",
      r2Key: staged.upload.key,
      mimeType: "image/png",
    };
    await runConsumer(message);
    expect((await readState(staged.attachment.id))!.state).toBe("ingested");

    const second = await runConsumer(message);
    expect(second.acked).toHaveLength(1);
    expect(second.retried).toHaveLength(0);
    expect((await readState(staged.attachment.id))!.state).toBe("ingested");

    const count = await env.DB.prepare(
      "SELECT COUNT(*) as count FROM chat_attachments WHERE id = ?"
    )
      .bind(staged.attachment.id)
      .first<{ count: number }>();
    expect(count!.count).toBe(1);
  });

  test("consumer marks state invalid when the R2 object disappeared before delivery", async () => {
    const staged = await stageViaRoute("int-disappeared-1");
    await env.ATTACHMENTS.put(staged.upload.key, new Uint8Array(2048), {
      httpMetadata: { contentType: "image/png" },
    });
    await completeViaRoute(staged.attachment.id);

    await env.ATTACHMENTS.delete(staged.upload.key);
    const outcome = await runConsumer({
      attachmentId: staged.attachment.id,
      accountId: "test-account",
      r2Key: staged.upload.key,
      mimeType: "image/png",
    });
    expect(outcome.acked).toHaveLength(1);
    expect((await readState(staged.attachment.id))!.state).toBe("invalid");
  });

  test("complete returns 410 when staging TTL has expired", async () => {
    const staged = await stageViaRoute("int-expired-1");
    await env.ATTACHMENTS.put(staged.upload.key, new Uint8Array(2048), {
      httpMetadata: { contentType: "image/png" },
    });
    await env.DB.prepare(
      "UPDATE chat_attachments SET expires_at = ? WHERE id = ?"
    )
      .bind(Date.now() - 1000, staged.attachment.id)
      .run();

    const response = await completeViaRoute(staged.attachment.id);
    expect(response.status).toBe(410);
    expect((await readState(staged.attachment.id))!.state).toBe("expired");
  });
});
