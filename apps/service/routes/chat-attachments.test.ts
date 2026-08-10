import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";

import {
  createInMemoryLocalServiceStores,
  createLocalDevService,
  type InMemoryLocalServiceStores,
} from "../app-facing";
import type { ChatGenerationSource } from "../chat/generation-source";
import type { ChatGenerationSupervisor } from "../chat/generation-supervisor";
import { sniffChatAttachmentMimeType } from "./chat-attachments";
import {
  ATTACHMENT_STAGING_TTL_MS,
  CHAT_MAX_ATTACHMENT_BYTES,
  CHAT_SEND_RETRY_HORIZON_MS,
  MAIN_CHAT_ATTACHMENT_SCOPE,
} from "../chat/attachment-policy";

const inertSupervisor = (): ChatGenerationSupervisor => Object.freeze({
  onAdmitted: (): void => {},
  cancel: (): void => {},
  recoverInterrupted: (): void => {},
});

const pdf = (): Uint8Array => new Uint8Array([
  0x25, 0x50, 0x44, 0x46, 0x2d, 0x31, 0x2e, 0x37, 0x0a,
]);

const png = (): Uint8Array => new Uint8Array([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00,
]);

const boot = (options: {
  readonly owner?: string;
  readonly stores?: InMemoryLocalServiceStores;
  readonly now?: { value: number };
  readonly ids?: string[];
  readonly references?: string[];
  readonly source?: ChatGenerationSource;
  readonly label?: string;
} = {}) => {
  const db = new Database(":memory:");
  const now = options.now ?? { value: 1_786_352_400_000 };
  const ids = options.ids ?? ["attachment-opaque-01"];
  const references = options.references ?? ["content-opaque-01"];
  const local = createLocalDevService({
    db,
    ...(options.stores === undefined ? {} : { stores: options.stores }),
    ownerAccountId: options.owner ?? "attachment-owner",
    memoryCount: 0,
    accountTimezone: "UTC",
    devSecretLabel: options.label ?? `attachment-route-${options.owner ?? "owner"}`,
    nowEpochMilliseconds: () => now.value,
    attachmentId: () => {
      const id = ids.shift();
      if (id === undefined) throw new TypeError("attachment test id exhausted");
      return id;
    },
    attachmentContentReference: () => {
      const reference = references.shift();
      if (reference === undefined) throw new TypeError("attachment test reference exhausted");
      return reference;
    },
    chatSupervisor: options.source === undefined ? inertSupervisor() : undefined,
    ...(options.source === undefined ? {} : { generationSource: options.source }),
  });
  return { db, local, now };
};

const upload = (
  local: ReturnType<typeof createLocalDevService>,
  file: File,
  extra?: readonly [string, string],
): Promise<Response> => {
  const body = new FormData();
  body.append("file", file);
  if (extra !== undefined) body.append(extra[0], extra[1]);
  return Promise.resolve(local.app.request("/v1/chat-attachments", {
    method: "POST",
    headers: { authorization: `Bearer ${local.devToken}` },
    body,
  }));
};

const send = (
  local: ReturnType<typeof createLocalDevService>,
  messageId: string,
  attachmentIds: readonly string[],
): Promise<Response> => Promise.resolve(local.app.request("/v1/chat-messages", {
  method: "POST",
  headers: {
    authorization: `Bearer ${local.devToken}`,
    "content-type": "application/json",
  },
  body: JSON.stringify({
    op: "create",
    opId: `op-${messageId}`,
    id: messageId,
    at: 1_786_352_400_000,
    text: `message ${messageId}`,
    sender: "human",
    journalRevision: 1,
    type: "text",
    appId: null,
    chatSessionId: null,
    messageSource: "desktop_chat",
    metadata: null,
    attachmentIds,
  }),
}));

describe("POST /v1/chat-attachments", () => {
  test("stages sniffed content, normalizes the basename, and returns only opaque staging metadata", async () => {
    const { db, local, now } = boot();
    const response = await upload(local, new File([pdf()], "C:\\fakepath\\notes.pdf", {
      type: "application/pdf",
    }));

    expect(response.status).toBe(201);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(await response.json()).toEqual({
      attachment: {
        id: "attachment-opaque-01",
        mimeType: "application/pdf",
        sizeBytes: pdf().byteLength,
        state: "staged",
        expiresAt: new Date(now.value + ATTACHMENT_STAGING_TTL_MS).toISOString(),
      },
    });

    const admitted = await send(local, "message-with-file", ["attachment-opaque-01"]);
    expect(admitted.status).toBe(201);
    expect((await admitted.json()).message.attachments).toEqual([{
      id: "attachment-opaque-01",
      displayName: "notes.pdf",
      mediaType: "application/pdf",
      sizeBytes: pdf().byteLength,
      contentReference: "content-opaque-01",
    }]);
    db.close();
  });

  test("rejects magic mismatch, empty, oversized, extra-field, unsupported and binary-text bodies", async () => {
    const cases: readonly { readonly name: string; readonly file: File; readonly extra?: [string, string] }[] = [
      { name: "magic mismatch", file: new File([pdf()], "wrong.png", { type: "image/png" }) },
      { name: "empty", file: new File([], "empty.txt", { type: "text/plain" }) },
      { name: "empty name", file: new File([pdf()], "", { type: "application/pdf" }) },
      {
        name: "oversized name",
        file: new File([pdf()], `${"n".repeat(256)}.pdf`, { type: "application/pdf" }),
      },
      {
        name: "oversized",
        file: new File([new Uint8Array(CHAT_MAX_ATTACHMENT_BYTES + 1)], "huge.png", {
          type: "image/png",
        }),
      },
      {
        name: "extra field",
        file: new File([pdf()], "notes.pdf", { type: "application/pdf" }),
        extra: ["accountId", "someone-else"],
      },
      {
        name: "unsupported",
        file: new File([new Uint8Array([0x50, 0x4b, 0x03, 0x04])], "archive.zip", {
          type: "application/zip",
        }),
      },
      {
        name: "binary text",
        file: new File([new Uint8Array([0x61, 0x00, 0x62])], "binary.txt", {
          type: "text/plain",
        }),
      },
    ];
    for (const candidate of cases) {
      const { db, local } = boot({ label: `reject-${candidate.name}` });
      const response = await upload(local, candidate.file, candidate.extra);
      expect(response.status, candidate.name).toBe(422);
      expect(await response.json(), candidate.name).toEqual({
        error: { code: "validation", retryable: false, action: "edit_request" },
      });
      db.close();
    }
  });

  test("sniffs valid UTF-8 plain text and Markdown without trusting their names", async () => {
    const { db, local } = boot({
      ids: ["plain-id", "markdown-id"],
      references: ["plain-ref", "markdown-ref"],
    });
    const plain = await upload(local, new File(["hello, UTF-8: ✓\n"], "wrong.bin", {
      type: "text/plain",
    }));
    const markdown = await upload(local, new File(["# Heading\n\n- one\n"], "wrong.txt", {
      type: "text/markdown",
    }));
    expect([plain.status, markdown.status]).toEqual([201, 201]);
    expect([(await plain.json()).attachment.mimeType, (await markdown.json()).attachment.mimeType])
      .toEqual(["text/plain", "text/markdown"]);
    db.close();
  });

  test("the detector recognizes exactly every MIME family the history policy advertises", () => {
    expect([
      sniffChatAttachmentMimeType(new Uint8Array([0xff, 0xd8, 0xff, 0x00])),
      sniffChatAttachmentMimeType(png()),
      sniffChatAttachmentMimeType(new TextEncoder().encode("GIF89a")),
      sniffChatAttachmentMimeType(new TextEncoder().encode("RIFF0000WEBPVP8X")),
      sniffChatAttachmentMimeType(pdf()),
      sniffChatAttachmentMimeType(new TextEncoder().encode("plain UTF-8 ✓")),
      sniffChatAttachmentMimeType(new TextEncoder().encode("# Markdown\n")),
    ]).toEqual([
      "image/jpeg", "image/png", "image/gif", "image/webp",
      "application/pdf", "text/plain", "text/markdown",
    ]);
  });
});

describe("attachment ownership, binding and staging boundaries", () => {
  test("send enforces the advertised count and uniqueness without truncation or mutation", async () => {
    const stores = createInMemoryLocalServiceStores();
    const { db, local, now } = boot({ stores });
    for (let index = 0; index < 5; index += 1) {
      stores.chatAttachments.stage({
        id: `count-${index}`,
        contentReference: `count-ref-${index}`,
        accountId: "attachment-owner",
        scope: MAIN_CHAT_ATTACHMENT_SCOPE,
        displayName: `count-${index}.pdf`,
        mimeType: "application/pdf",
        content: pdf(),
        stagedAt: now.value,
        stageExpiresAt: now.value + ATTACHMENT_STAGING_TTL_MS,
      });
    }
    expect((await send(local, "too-many", [
      "count-0", "count-1", "count-2", "count-3", "count-4",
    ])).status).toBe(422);
    expect((await send(local, "duplicate", ["count-0", "count-0"])).status).toBe(422);
    expect(stores.chatMessages.readSnapshotSequence("attachment-owner")).toBe(0);
    expect(stores.chatAttachments.snapshotAccount("attachment-owner").rows
      ?.every((row) => row.state === "staged")).toBe(true);
    db.close();
  });

  test("owner/scope mismatch and unknown id are identical; one bound id cannot be stolen", async () => {
    const stores = createInMemoryLocalServiceStores();
    const first = boot({
      owner: "account-a",
      stores,
      ids: ["owned-a"],
      references: ["owned-a-ref"],
      label: "account-a-service",
    });
    const second = boot({ owner: "account-b", stores, label: "account-b-service" });
    expect((await upload(first.local, new File([pdf()], "a.pdf", {
      type: "application/pdf",
    }))).status).toBe(201);
    stores.chatAttachments.stage({
      id: "wrong-scope",
      contentReference: "wrong-scope-ref",
      accountId: "account-a",
      scope: "not-main",
      displayName: "scope.pdf",
      mimeType: "application/pdf",
      content: pdf(),
      stagedAt: 1_786_352_400_000,
      stageExpiresAt: 1_786_352_400_000 + ATTACHMENT_STAGING_TTL_MS,
    });

    const foreign = await send(second.local, "foreign-attempt", ["owned-a"]);
    const unknown = await send(second.local, "unknown-attempt", ["does-not-exist"]);
    expect(foreign.status).toBe(404);
    expect(await foreign.text()).toBe(await unknown.text());
    expect((await send(first.local, "scope-attempt", ["wrong-scope"])).status).toBe(404);
    expect((await send(first.local, "owner-message", ["owned-a"])).status).toBe(201);
    expect((await send(first.local, "steal-message", ["owned-a"])).status).toBe(404);
    expect(stores.chatMessages.readMessage("account-a", "steal-message")).toBeNull();
    expect(stores.chatMessages.readMessage("account-b", "foreign-attempt")).toBeNull();
    second.db.close();
    first.db.close();
  });

  test("the 24-hour boundary preserves admitted replay and permanently refuses unbound expiry", async () => {
    expect(CHAT_SEND_RETRY_HORIZON_MS).toBe(ATTACHMENT_STAGING_TTL_MS);
    const stores = createInMemoryLocalServiceStores();
    stores.settings.putEntitlement("attachment-owner", {
      planLabel: "Metered",
      limitKey: "chat_messages",
      used: 0,
      limit: 4,
      limitReached: false,
      upgradeAvailable: true,
    });
    const now = { value: 10_000 };
    const { db, local } = boot({
      stores,
      now,
      ids: ["inside", "expires"],
      references: ["inside-ref", "expires-ref"],
    });
    expect((await upload(local, new File([pdf()], "inside.pdf", {
      type: "application/pdf",
    }))).status).toBe(201);
    expect((await upload(local, new File([png()], "expires.png", {
      type: "image/png",
    }))).status).toBe(201);

    now.value = 10_000 + ATTACHMENT_STAGING_TTL_MS - 1;
    expect((await send(local, "inside-message", ["inside"])).status).toBe(201);
    now.value += 1;
    expect((await send(local, "inside-message", ["inside"])).status).toBe(200);
    const before = stores.chatAttachments.snapshotAccount("attachment-owner");
    const expired = await send(local, "expired-message", ["expires"]);
    expect(expired.status).toBe(404);
    expect(stores.chatMessages.readMessage("attachment-owner", "expired-message")).toBeNull();
    expect(stores.settings.readEntitlement("attachment-owner")?.used).toBe(1);
    expect(stores.chatEvents.listUnterminated()).toHaveLength(1);
    expect(stores.chatAttachments.snapshotAccount("attachment-owner")).toEqual(before);
    db.close();
  });

  test("generation observes every admitted attachment descriptor and retained byte sequence in order", async () => {
    const observed: Parameters<ChatGenerationSource["start"]>[0][] = [];
    const source: ChatGenerationSource = Object.freeze({
      start(input) {
        observed.push(input);
        return Object.freeze({ cancel: (): void => {} });
      },
    });
    const { db, local } = boot({
      source,
      ids: ["pdf-id", "png-id"],
      references: ["pdf-ref", "png-ref"],
    });
    await upload(local, new File([pdf()], "one.pdf", { type: "application/pdf" }));
    await upload(local, new File([png()], "two.png", { type: "image/png" }));
    expect((await send(local, "ordered", ["png-id", "pdf-id"])).status).toBe(201);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect((await send(local, "ordered", ["png-id", "pdf-id"])).status).toBe(200);
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(observed).toHaveLength(1);
    expect(observed[0]?.attachments.map((item) => item.id)).toEqual(["png-id", "pdf-id"]);
    expect(observed[0]?.attachments.map((item) => [...(item.content ?? [])])).toEqual([
      [...png()],
      [...pdf()],
    ]);
    db.close();
  });
});
