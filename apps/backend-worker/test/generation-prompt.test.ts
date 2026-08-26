import { beforeEach, describe, expect, test } from "bun:test";

import {
  composeGenerationPrompt,
  GENERATION_ATTACHMENT_TEXT_BUDGET,
  isGenerationTextMimeType,
} from "../src/generation-prompt";
import { CHAT_CAPABILITIES } from "../src/wire";
import { createD1Mock } from "./d1-mock";

const SECRET_TEXT = "bound-plain-text-secret-do-not-log";
const FOREIGN_TEXT = "foreign-account-bytes-must-not-leak";

type R2Object = { bytes: Uint8Array };

function createR2GetMock(): R2Bucket & {
  objects: Map<string, R2Object>;
  putBytes(key: string, bytes: Uint8Array): void;
} {
  const objects = new Map<string, R2Object>();
  return {
    objects,
    putBytes(key: string, bytes: Uint8Array) {
      objects.set(key, { bytes });
    },
    async get(
      key: string,
      options?: { range?: { offset: number; length: number } }
    ) {
      const obj = objects.get(key);
      if (obj === undefined) return null;
      const offset = options?.range?.offset ?? 0;
      const length = options?.range?.length ?? obj.bytes.byteLength;
      const slice = obj.bytes.slice(offset, offset + length);
      return {
        size: slice.byteLength,
        arrayBuffer: async () =>
          slice.buffer.slice(
            slice.byteOffset,
            slice.byteOffset + slice.byteLength
          ),
        text: async () => new TextDecoder().decode(slice),
      } as never;
    },
  } as never;
}

const insertBound = async (
  db: D1Database,
  input: {
    id: string;
    accountId: string;
    messageId: string;
    mimeType: string;
    displayName?: string;
    r2Key?: string;
  }
) => {
  const now = Date.now();
  await db
    .prepare(
      "INSERT INTO chat_attachments (id, account_id, op_id, display_name, media_type, size_bytes, state, r2_key, expires_at, bound_message_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'bound', ?, ?, ?, ?, ?)"
    )
    .bind(
      input.id,
      input.accountId,
      `op-${input.id}`,
      input.displayName ?? "notes.txt",
      input.mimeType,
      32,
      input.r2Key ?? `attachments/${input.accountId}/${input.id}`,
      now + 86_400_000,
      input.messageId,
      now,
      now
    )
    .run();
};

let db: D1Database;
let r2: ReturnType<typeof createR2GetMock>;

beforeEach(() => {
  db = createD1Mock();
  r2 = createR2GetMock();
});

describe("generation text mime policy", () => {
  test("allows advertised text types and rejects images and pdf", () => {
    expect(CHAT_CAPABILITIES.allowedAttachmentMimeTypes).toContain(
      "text/plain"
    );
    expect(isGenerationTextMimeType("text/plain")).toBe(true);
    expect(isGenerationTextMimeType("text/markdown")).toBe(true);
    expect(isGenerationTextMimeType("image/png")).toBe(false);
    expect(isGenerationTextMimeType("application/pdf")).toBe(false);
  });
});

describe("composeGenerationPrompt", () => {
  test("appends a bound text/plain R2 object to the prompt", async () => {
    await insertBound(db, {
      id: "att-text",
      accountId: "acct-a",
      messageId: "msg-1",
      mimeType: "text/plain",
    });
    r2.putBytes(
      "attachments/acct-a/att-text",
      new TextEncoder().encode(SECRET_TEXT)
    );

    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "msg-1",
      "summarize this"
    );
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(result.prompt).toContain("summarize this");
    expect(result.prompt).toContain(SECRET_TEXT);
    expect(result.prompt).toContain("notes.txt");
  });

  test("omits foreign-account and missing R2 objects without leaking bytes", async () => {
    await insertBound(db, {
      id: "att-own-missing",
      accountId: "acct-a",
      messageId: "msg-1",
      mimeType: "text/plain",
      displayName: "missing.txt",
    });
    await insertBound(db, {
      id: "att-foreign",
      accountId: "acct-other",
      messageId: "msg-1",
      mimeType: "text/plain",
      displayName: "foreign.txt",
    });
    r2.putBytes(
      "attachments/acct-other/att-foreign",
      new TextEncoder().encode(FOREIGN_TEXT)
    );

    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "msg-1",
      "hello"
    );
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(result.prompt).toBe("hello");
    expect(result.prompt).not.toContain(FOREIGN_TEXT);
    expect(result.prompt).not.toContain("foreign.txt");
  });

  test("omits non-text bytes and does not invent captions", async () => {
    await insertBound(db, {
      id: "att-png",
      accountId: "acct-a",
      messageId: "msg-1",
      mimeType: "image/png",
      displayName: "photo.png",
    });
    r2.putBytes(
      "attachments/acct-a/att-png",
      new Uint8Array([0x89, 0x50, 0x4e])
    );

    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "msg-1",
      "look at this"
    );
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(result.prompt).toBe("look at this");
    expect(result.prompt).not.toContain("photo.png");
  });

  test("fails when every bound text file is unreadable and the user text is empty", async () => {
    await insertBound(db, {
      id: "att-gone",
      accountId: "acct-a",
      messageId: "msg-empty",
      mimeType: "text/plain",
    });
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "msg-empty",
      ""
    );
    expect(result).toEqual({ kind: "fail" });
  });

  test("caps total excerpt bytes across files", async () => {
    const first = "a".repeat(20_000);
    const second = "b".repeat(20_000);
    await insertBound(db, {
      id: "att-1",
      accountId: "acct-a",
      messageId: "msg-cap",
      mimeType: "text/plain",
      displayName: "a.txt",
    });
    await insertBound(db, {
      id: "att-2",
      accountId: "acct-a",
      messageId: "msg-cap",
      mimeType: "text/plain",
      displayName: "b.txt",
    });
    r2.putBytes("attachments/acct-a/att-1", new TextEncoder().encode(first));
    r2.putBytes("attachments/acct-a/att-2", new TextEncoder().encode(second));

    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "msg-cap",
      "cap"
    );
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    const excerptBytes =
      new TextEncoder().encode(result.prompt).byteLength -
      new TextEncoder().encode("cap\n\n").byteLength;
    expect(excerptBytes).toBeLessThanOrEqual(
      GENERATION_ATTACHMENT_TEXT_BUDGET + 80
    );
    expect(result.prompt).toContain("a.txt");
  });

  test("does not log file contents", async () => {
    const lines: string[] = [];
    const log = console.log;
    const error = console.error;
    console.log = (...args: unknown[]) => {
      lines.push(args.map(String).join(" "));
    };
    console.error = (...args: unknown[]) => {
      lines.push(args.map(String).join(" "));
    };
    try {
      await insertBound(db, {
        id: "att-log",
        accountId: "acct-a",
        messageId: "msg-log",
        mimeType: "text/plain",
      });
      r2.putBytes(
        "attachments/acct-a/att-log",
        new TextEncoder().encode(SECRET_TEXT)
      );
      await composeGenerationPrompt(db, r2, "acct-a", "msg-log", "hello");
    } finally {
      console.log = log;
      console.error = error;
    }
    expect(lines.join("\n")).not.toContain(SECRET_TEXT);
  });
});
