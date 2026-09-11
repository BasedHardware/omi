import { beforeEach, describe, expect, test } from "bun:test";

import {
  composeGenerationPrompt,
  GENERATION_ATTACHMENT_TEXT_BUDGET,
  GENERATION_HISTORY_TEXT_BUDGET,
  GENERATION_HISTORY_MESSAGE_LIMIT,
  isGenerationTextMimeType,
  isVisibleGenerationText,
  visibleGenerationTrim,
} from "../src/generation-prompt";
import {
  admitMessage,
  completeGeneration,
  failGeneration,
  readPendingGeneration,
  terminalEvent,
} from "../src/chat";
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
        size: obj.bytes.byteLength,
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
  test("uses only earlier messages from the same account, app, and chat session", async () => {
    const rows = [
      [
        "human",
        "acct-a",
        "human",
        "My name is Ana",
        1,
        "session-a",
        null,
        null,
      ],
      [
        "assistant",
        "acct-a",
        "ai",
        "Hello Ana",
        2,
        "session-a",
        null,
        "completed",
      ],
      [
        "foreign",
        "acct-b",
        "human",
        "foreign account",
        3,
        "session-a",
        null,
        null,
      ],
      [
        "other-session",
        "acct-a",
        "human",
        "other session",
        4,
        "session-b",
        null,
        null,
      ],
      [
        "other-app",
        "acct-a",
        "human",
        "other app",
        5,
        "session-a",
        "app-b",
        null,
      ],
      [
        "cancelled",
        "acct-a",
        "ai",
        "cancelled reply",
        6,
        "session-a",
        null,
        "cancelled",
      ],
      [
        "current",
        "acct-a",
        "human",
        "What is my name?",
        7,
        "session-a",
        null,
        null,
      ],
      [
        "future",
        "acct-a",
        "human",
        "future message",
        8,
        "session-a",
        null,
        null,
      ],
    ];
    for (const [
      id,
      account,
      sender,
      text,
      position,
      chatSessionId,
      appId,
      outcome,
    ] of rows) {
      await db
        .prepare(
          "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload, generation_outcome) VALUES (?, ?, ?, ?, ?, 1, ?, ?)"
        )
        .bind(
          id,
          account,
          sender,
          text,
          position,
          JSON.stringify({ chatSessionId, appId }),
          outcome
        )
        .run();
    }
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "current",
      "What is my name?"
    );
    expect(result).toEqual({
      kind: "ok",
      prompt: "What is my name?",
      history: [
        { role: "user", content: "My name is Ana" },
        { role: "assistant", content: "Hello Ana" },
      ],
    });
  });

  test("generation history follows created_at then position", async () => {
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload, generation_outcome) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
      )
      .bind(
        "later-clock",
        "acct-a",
        "human",
        "Later clock first position",
        1,
        500,
        JSON.stringify({ chatSessionId: "clock-skew", appId: null }),
        null
      )
      .run();
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload, generation_outcome) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
      )
      .bind(
        "earlier-clock",
        "acct-a",
        "human",
        "Earlier clock last position",
        2,
        100,
        JSON.stringify({ chatSessionId: "clock-skew", appId: null }),
        null
      )
      .run();
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload, generation_outcome) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
      )
      .bind(
        "current-clock",
        "acct-a",
        "human",
        "What is my name?",
        3,
        900,
        JSON.stringify({ chatSessionId: "clock-skew", appId: null }),
        null
      )
      .run();
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "current-clock",
      "What is my name?"
    );
    expect(result).toEqual({
      kind: "ok",
      prompt: "What is my name?",
      history: [
        { role: "user", content: "Earlier clock last position" },
        { role: "user", content: "Later clock first position" },
      ],
    });
  });

  test("generation history keeps a later-clock assistant admitted before the current turn", async () => {
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload, generation_outcome) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
      )
      .bind(
        "stale-first",
        "acct-a",
        "human",
        "My name is Ana",
        1,
        1,
        JSON.stringify({ chatSessionId: null, appId: null }),
        null
      )
      .run();
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload, generation_outcome) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
      )
      .bind(
        "server-assistant",
        "acct-a",
        "ai",
        "Hello Ana",
        2,
        500,
        JSON.stringify({ chatSessionId: null, appId: null }),
        "completed"
      )
      .run();
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload, generation_outcome) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
      )
      .bind(
        "stale-second",
        "acct-a",
        "human",
        "What is my name?",
        3,
        1,
        JSON.stringify({ chatSessionId: null, appId: null }),
        null
      )
      .run();
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "stale-second",
      "What is my name?"
    );
    expect(result).toEqual({
      kind: "ok",
      prompt: "What is my name?",
      history: [
        { role: "user", content: "My name is Ana" },
        { role: "assistant", content: "Hello Ana" },
      ],
    });
  });

  test("generation history uses the last duplicate chatSessionId like conversation grouping", async () => {
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload, generation_outcome) VALUES (?, ?, ?, ?, ?, 1, ?, ?)"
      )
      .bind(
        "main",
        "acct-a",
        "human",
        "main session words",
        1,
        JSON.stringify({ chatSessionId: null }),
        null
      )
      .run();
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload, generation_outcome) VALUES (?, ?, ?, ?, ?, 1, ?, ?)"
      )
      .bind(
        "named-prior",
        "acct-a",
        "human",
        "My name is Ana",
        2,
        '{"chatSessionId":"wrong","chatSessionId":"session-a"}',
        null
      )
      .run();
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload, generation_outcome) VALUES (?, ?, ?, ?, ?, 1, ?, ?)"
      )
      .bind(
        "current",
        "acct-a",
        "human",
        "What is my name?",
        3,
        JSON.stringify({ chatSessionId: "session-a" }),
        null
      )
      .run();
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "current",
      "What is my name?"
    );
    expect(result).toEqual({
      kind: "ok",
      prompt: "What is my name?",
      history: [{ role: "user", content: "My name is Ana" }],
    });
  });

  test("generation history treats stored chat-main as the main session", async () => {
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload, generation_outcome) VALUES (?, ?, ?, ?, ?, 1, ?, ?)"
      )
      .bind(
        "main-key",
        "acct-a",
        "human",
        "stored as chat-main",
        1,
        JSON.stringify({ chatSessionId: "chat-main" }),
        null
      )
      .run();
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload, generation_outcome) VALUES (?, ?, ?, ?, ?, 1, ?, ?)"
      )
      .bind(
        "padded-main",
        "acct-a",
        "human",
        "stored as space-padded chat-main",
        2,
        JSON.stringify({ chatSessionId: " chat-main " }),
        null
      )
      .run();
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload, generation_outcome) VALUES (?, ?, ?, ?, ?, 1, ?, ?)"
      )
      .bind(
        "space-main",
        "acct-a",
        "human",
        "stored as space-only chatSessionId",
        3,
        JSON.stringify({ chatSessionId: "  " }),
        null
      )
      .run();
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload, generation_outcome) VALUES (?, ?, ?, ?, ?, 1, ?, ?)"
      )
      .bind(
        "named-prior",
        "acct-a",
        "human",
        "named session words",
        4,
        JSON.stringify({ chatSessionId: "session-a" }),
        null
      )
      .run();
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload, generation_outcome) VALUES (?, ?, ?, ?, ?, 1, ?, ?)"
      )
      .bind(
        "padded-named",
        "acct-a",
        "human",
        "padded named stays named",
        5,
        JSON.stringify({ chatSessionId: " session-a " }),
        null
      )
      .run();
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload, generation_outcome) VALUES (?, ?, ?, ?, ?, 1, ?, ?)"
      )
      .bind(
        "current",
        "acct-a",
        "human",
        "What is on main?",
        6,
        JSON.stringify({ chatSessionId: null }),
        null
      )
      .run();
    const fromNull = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "current",
      "What is on main?"
    );
    expect(fromNull).toEqual({
      kind: "ok",
      prompt: "What is on main?",
      history: [
        { role: "user", content: "stored as chat-main" },
        { role: "user", content: "stored as space-padded chat-main" },
        { role: "user", content: "stored as space-only chatSessionId" },
      ],
    });

    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload, generation_outcome) VALUES (?, ?, ?, ?, ?, 1, ?, ?)"
      )
      .bind(
        "current-key",
        "acct-a",
        "human",
        "Continue on main",
        7,
        JSON.stringify({ chatSessionId: "chat-main" }),
        null
      )
      .run();
    const fromKey = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "current-key",
      "Continue on main"
    );
    expect(fromKey).toEqual({
      kind: "ok",
      prompt: "Continue on main",
      history: [
        { role: "user", content: "stored as chat-main" },
        { role: "user", content: "stored as space-padded chat-main" },
        { role: "user", content: "stored as space-only chatSessionId" },
        { role: "user", content: "What is on main?" },
      ],
    });
  });

  test("keeps named-session history when the current payload JSON is unreadable", async () => {
    const rows = [
      ["main", "acct-a", "human", "main session words", 1, null, null, null],
      [
        "human",
        "acct-a",
        "human",
        "My name is Ana",
        2,
        "session-a",
        null,
        null,
      ],
      [
        "assistant",
        "acct-a",
        "ai",
        "Hello Ana",
        3,
        "session-a",
        null,
        "completed",
      ],
      [
        "other-session",
        "acct-a",
        "human",
        "other session",
        4,
        "session-b",
        null,
        null,
      ],
      [
        "current",
        "acct-a",
        "human",
        "What is my name?",
        5,
        "session-a",
        null,
        null,
      ],
    ];
    for (const [
      id,
      account,
      sender,
      text,
      position,
      chatSessionId,
      appId,
      outcome,
    ] of rows) {
      await db
        .prepare(
          "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload, generation_outcome) VALUES (?, ?, ?, ?, ?, 1, ?, ?)"
        )
        .bind(
          id,
          account,
          sender,
          text,
          position,
          id === "current"
            ? "{broken"
            : JSON.stringify({ chatSessionId, appId }),
          outcome
        )
        .run();
    }
    await db
      .prepare(
        "INSERT INTO chat_admissions (message_id, account_id, op_id, payload, generation_id) VALUES (?, ?, ?, ?, ?)"
      )
      .bind(
        "current",
        "acct-a",
        "op-current",
        JSON.stringify({
          op: "create",
          opId: "op-current",
          id: "current",
          at: 1,
          text: "What is my name?",
          sender: "human",
          journalRevision: 0,
          attachmentIds: [],
          chatSessionId: "session-a",
        }),
        "gen-current"
      )
      .run();
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "current",
      "What is my name?"
    );
    expect(result).toEqual({
      kind: "ok",
      prompt: "What is my name?",
      history: [
        { role: "user", content: "My name is Ana" },
        { role: "assistant", content: "Hello Ana" },
      ],
    });
  });

  test("keeps named-session history when the current payload is JSON null", async () => {
    const rows = [
      ["main", "acct-a", "human", "main session words", 1, null, null, null],
      [
        "human",
        "acct-a",
        "human",
        "My name is Ana",
        2,
        "session-a",
        null,
        null,
      ],
      [
        "assistant",
        "acct-a",
        "ai",
        "Hello Ana",
        3,
        "session-a",
        null,
        "completed",
      ],
      [
        "other-session",
        "acct-a",
        "human",
        "other session",
        4,
        "session-b",
        null,
        null,
      ],
      [
        "current",
        "acct-a",
        "human",
        "What is my name?",
        5,
        "session-a",
        null,
        null,
      ],
    ];
    for (const [
      id,
      account,
      sender,
      text,
      position,
      chatSessionId,
      appId,
      outcome,
    ] of rows) {
      await db
        .prepare(
          "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload, generation_outcome) VALUES (?, ?, ?, ?, ?, 1, ?, ?)"
        )
        .bind(
          id,
          account,
          sender,
          text,
          position,
          id === "current" ? "null" : JSON.stringify({ chatSessionId, appId }),
          outcome
        )
        .run();
    }
    await db
      .prepare(
        "INSERT INTO chat_admissions (message_id, account_id, op_id, payload, generation_id) VALUES (?, ?, ?, ?, ?)"
      )
      .bind(
        "current",
        "acct-a",
        "op-current",
        JSON.stringify({
          op: "create",
          opId: "op-current",
          id: "current",
          at: 1,
          text: "What is my name?",
          sender: "human",
          journalRevision: 0,
          attachmentIds: [],
          chatSessionId: "session-a",
        }),
        "gen-current"
      )
      .run();
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "current",
      "What is my name?"
    );
    expect(result).toEqual({
      kind: "ok",
      prompt: "What is my name?",
      history: [
        { role: "user", content: "My name is Ana" },
        { role: "assistant", content: "Hello Ana" },
      ],
    });
  });

  test("omits an unreadable named-session assistant from main-session generation history", async () => {
    const generationId = "11111111-1111-4111-8111-111111111111";
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload, generation_outcome) VALUES (?, 'acct-a', 'human', 'main session words', 1, 1, ?, NULL)"
      )
      .bind("main", JSON.stringify({ chatSessionId: null, appId: null }))
      .run();
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload, generation_outcome) VALUES (?, 'acct-a', 'ai', 'named session answer', 2, 1, '{broken', 'completed')"
      )
      .bind(generationId)
      .run();
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload, generation_outcome) VALUES (?, 'acct-a', 'human', 'What is my name?', 3, 1, ?, NULL)"
      )
      .bind("current", JSON.stringify({ chatSessionId: null, appId: null }))
      .run();
    await db
      .prepare(
        "INSERT INTO chat_admissions (message_id, account_id, op_id, payload, generation_id) VALUES (?, 'acct-a', ?, ?, ?)"
      )
      .bind(
        "named-human",
        "op-named-human",
        JSON.stringify({
          op: "create",
          opId: "op-named-human",
          id: "named-human",
          at: 1,
          text: "named session words",
          sender: "human",
          journalRevision: 0,
          attachmentIds: [],
          chatSessionId: "session-a",
        }),
        generationId
      )
      .run();
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "current",
      "What is my name?"
    );
    expect(result).toEqual({
      kind: "ok",
      prompt: "What is my name?",
      history: [{ role: "user", content: "main session words" }],
    });
  });

  test("omits whitespace-only earlier messages from generation history", async () => {
    const rows = [
      ["human", "acct-a", "human", "My name is Ana", 1, null],
      ["blank-human", "acct-a", "human", " \t\n", 2, null],
      ["blank-assistant", "acct-a", "ai", " \t\n", 3, "completed"],
      ["assistant", "acct-a", "ai", "Hello Ana", 4, "completed"],
      ["padded", "acct-a", "human", "  still visible  ", 5, null],
      ["current", "acct-a", "human", "What is my name?", 6, null],
    ];
    for (const [id, account, sender, text, position, outcome] of rows) {
      await db
        .prepare(
          "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload, generation_outcome) VALUES (?, ?, ?, ?, ?, 1, ?, ?)"
        )
        .bind(
          id,
          account,
          sender,
          text,
          position,
          JSON.stringify({ chatSessionId: "session-a", appId: null }),
          outcome
        )
        .run();
    }
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "current",
      "What is my name?"
    );
    expect(result).toEqual({
      kind: "ok",
      prompt: "What is my name?",
      history: [
        { role: "user", content: "My name is Ana" },
        { role: "assistant", content: "Hello Ana" },
        { role: "user", content: "still visible" },
      ],
    });
  });

  test("whitespace-only rows do not consume the generation history message limit", async () => {
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, 1, 1, NULL)"
      )
      .bind("kept-visible", "kept visible")
      .run();
    for (
      let position = 2;
      position <= GENERATION_HISTORY_MESSAGE_LIMIT + 1;
      position += 1
    ) {
      await db
        .prepare(
          "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, ?, 1, NULL)"
        )
        .bind(`blank-${position}`, " \t\n", position)
        .run();
    }
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, ?, 1, NULL)"
      )
      .bind(
        "current-limit",
        "What is my name?",
        GENERATION_HISTORY_MESSAGE_LIMIT + 2
      )
      .run();
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "current-limit",
      "What is my name?"
    );
    expect(result).toEqual({
      kind: "ok",
      prompt: "What is my name?",
      history: [{ role: "user", content: "kept visible" }],
    });
  });

  test("NEXT LINE-only rows do not consume the generation history message limit", async () => {
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, 1, 1, NULL)"
      )
      .bind("kept-nel", "kept visible")
      .run();
    for (
      let position = 2;
      position <= GENERATION_HISTORY_MESSAGE_LIMIT + 1;
      position += 1
    ) {
      await db
        .prepare(
          "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, ?, 1, NULL)"
        )
        .bind(`nel-${position}`, "\u0085", position)
        .run();
    }
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, ?, 1, NULL)"
      )
      .bind(
        "current-nel",
        "What is my name?",
        GENERATION_HISTORY_MESSAGE_LIMIT + 2
      )
      .run();
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "current-nel",
      "What is my name?"
    );
    expect(result).toEqual({
      kind: "ok",
      prompt: "What is my name?",
      history: [{ role: "user", content: "kept visible" }],
    });
  });

  test("bounds default-session history by message count and UTF-8 bytes", async () => {
    for (let position = 1; position <= 43; position += 1) {
      await db
        .prepare(
          "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, ?, 1, NULL)"
        )
        .bind(`message-${position}`, String(position), position)
        .run();
    }
    const counted = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "message-43",
      "current"
    );
    if (counted.kind !== "ok") throw new Error("missing prompt");
    expect(counted.history).toHaveLength(GENERATION_HISTORY_MESSAGE_LIMIT);
    expect(counted.history[0]?.content).toBe("3");
    await db
      .prepare("UPDATE chat_messages SET text = ? WHERE position < 43")
      .bind("界".repeat(1000))
      .run();
    const bounded = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "message-43",
      "current"
    );
    if (bounded.kind !== "ok") throw new Error("missing prompt");
    const fullTurns = Math.floor(GENERATION_HISTORY_TEXT_BUDGET / 3000);
    const leftover = GENERATION_HISTORY_TEXT_BUDGET - fullTurns * 3000;
    expect(bounded.history).toHaveLength(fullTurns + (leftover > 0 ? 1 : 0));
    const used = bounded.history.reduce(
      (sum, item) => sum + new TextEncoder().encode(item.content).byteLength,
      0
    );
    expect(used).toBeLessThanOrEqual(GENERATION_HISTORY_TEXT_BUDGET);
    expect(used).toBeGreaterThan(fullTurns * 3000);
    expect(bounded.history[0]?.content).toBe(
      "界".repeat(Math.floor(leftover / 3))
    );
  });

  test("keeps a UTF-8 prefix of an oversized prior turn instead of composing with empty history", async () => {
    const euro = "€";
    const completeCount = Math.floor(
      GENERATION_HISTORY_TEXT_BUDGET / new TextEncoder().encode(euro).byteLength
    );
    const oversized = euro.repeat(completeCount + 8);
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, 1, 1, NULL)"
      )
      .bind("message-oversize", oversized)
      .run();
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, 2, 1, NULL)"
      )
      .bind("message-now", "current")
      .run();
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "message-now",
      "current"
    );
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(result.history).toEqual([
      { role: "user", content: euro.repeat(completeCount) },
    ]);
    expect(
      new TextEncoder().encode(result.history[0]!.content).byteLength
    ).toBeLessThanOrEqual(GENERATION_HISTORY_TEXT_BUDGET);
    expect(result.history[0]?.content).not.toBe(oversized);
  });

  test("keeps a UTF-8 prefix of leftover budget that cannot fit the next full turn", async () => {
    const euro = "€";
    const euroBytes = new TextEncoder().encode(euro).byteLength;
    const completeCount = Math.floor(
      GENERATION_HISTORY_TEXT_BUDGET / euroBytes
    );
    const oversized = euro.repeat(completeCount + 8);
    const recent = "recent";
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, 1, 1, NULL)"
      )
      .bind("message-older", oversized)
      .run();
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, 2, 1, NULL)"
      )
      .bind("message-recent", recent)
      .run();
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, 3, 1, NULL)"
      )
      .bind("message-now", "current")
      .run();
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "message-now",
      "current"
    );
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    const leftover =
      GENERATION_HISTORY_TEXT_BUDGET -
      new TextEncoder().encode(recent).byteLength;
    const prefix = euro.repeat(Math.floor(leftover / euroBytes));
    expect(result.history).toEqual([
      { role: "user", content: prefix },
      { role: "user", content: recent },
    ]);
    expect(prefix).not.toBe(oversized);
    expect(prefix.length).toBeGreaterThan(0);
    expect(
      result.history.reduce(
        (sum, item) => sum + new TextEncoder().encode(item.content).byteLength,
        0
      )
    ).toBeLessThanOrEqual(GENERATION_HISTORY_TEXT_BUDGET);
  });

  test("keeps older visible history when leftover prefix is only whitespace", async () => {
    const leftover = 2;
    const recent = "a".repeat(GENERATION_HISTORY_TEXT_BUDGET - leftover);
    const padded = `  ${"b".repeat(64)}`;
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, 1, 1, NULL)"
      )
      .bind("message-older", "ok")
      .run();
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, 2, 1, NULL)"
      )
      .bind("message-padded", padded)
      .run();
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, 3, 1, NULL)"
      )
      .bind("message-recent", recent)
      .run();
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, 4, 1, NULL)"
      )
      .bind("message-now", "current")
      .run();
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "message-now",
      "current"
    );
    expect(result).toEqual({
      kind: "ok",
      prompt: "current",
      history: [
        { role: "user", content: "ok" },
        { role: "user", content: recent },
      ],
    });
  });

  test("keeps older visible history when leftover prefix is only NEXT LINE", async () => {
    const leftover = 2;
    const recent = "a".repeat(GENERATION_HISTORY_TEXT_BUDGET - leftover);
    const padded = `\u0085${"b".repeat(64)}`;
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, 1, 1, NULL)"
      )
      .bind("message-older", "ok")
      .run();
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, 2, 1, NULL)"
      )
      .bind("message-padded", padded)
      .run();
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, 3, 1, NULL)"
      )
      .bind("message-recent", recent)
      .run();
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, 4, 1, NULL)"
      )
      .bind("message-now", "current")
      .run();
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "message-now",
      "current"
    );
    expect(result).toEqual({
      kind: "ok",
      prompt: "current",
      history: [
        { role: "user", content: "ok" },
        { role: "user", content: recent },
      ],
    });
  });

  test("keeps visible speech from an oversized prior turn after a NEXT LINE prefix longer than the history budget", async () => {
    const oversized = `${"\u0085".repeat(
      GENERATION_HISTORY_TEXT_BUDGET / 2
    )}Recorded words`;
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, 1, 1, NULL)"
      )
      .bind("message-oversize-nel", oversized)
      .run();
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, 2, 1, NULL)"
      )
      .bind("message-now", "current")
      .run();
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "message-now",
      "current"
    );
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(result.history).toEqual([
      { role: "user", content: "Recorded words" },
    ]);
  });

  test("a NEXT LINE prefix on a fitting prior turn does not evict older visible history", async () => {
    const older = "o".repeat(8_000);
    const padded = `${"\u0085".repeat(14_000)}recent-words`;
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, 1, 1, NULL)"
      )
      .bind("message-older-visible", older)
      .run();
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, 2, 1, NULL)"
      )
      .bind("message-padded-fit", padded)
      .run();
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, 3, 1, NULL)"
      )
      .bind("message-now", "current")
      .run();
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "message-now",
      "current"
    );
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(result.history).toEqual([
      { role: "user", content: older },
      { role: "user", content: "recent-words" },
    ]);
  });

  test("a NEXT LINE-padded prior turn whose raw size exceeds the budget still keeps later speech when older history remains", async () => {
    const older = "Recorded earlier";
    const padded = `${"\u0085".repeat(
      GENERATION_HISTORY_TEXT_BUDGET / 2
    )}middle-words`;
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, 1, 1, NULL)"
      )
      .bind("message-older-visible", older)
      .run();
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, 2, 1, NULL)"
      )
      .bind("message-padded-oversize", padded)
      .run();
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, sender, text, position, created_at, payload) VALUES (?, 'acct-a', 'human', ?, 3, 1, NULL)"
      )
      .bind("message-now", "current")
      .run();
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "message-now",
      "current"
    );
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(result.history).toEqual([
      { role: "user", content: older },
      { role: "user", content: "middle-words" },
    ]);
  });

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

  test("omits foreign-account attachments without leaking bytes", async () => {
    await insertBound(db, {
      id: "att-own",
      accountId: "acct-a",
      messageId: "msg-1",
      mimeType: "text/plain",
      displayName: "notes.txt",
    });
    await insertBound(db, {
      id: "att-foreign",
      accountId: "acct-other",
      messageId: "msg-1",
      mimeType: "text/plain",
      displayName: "foreign.txt",
    });
    r2.putBytes(
      "attachments/acct-a/att-own",
      new TextEncoder().encode("own file bytes")
    );
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
    expect(result.prompt).toContain("hello");
    expect(result.prompt).toContain("own file bytes");
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

  test("fails when a bound text object is missing instead of dropping it from a visible prompt", async () => {
    await insertBound(db, {
      id: "att-missing-visible",
      accountId: "acct-a",
      messageId: "msg-missing-visible",
      mimeType: "text/plain",
      displayName: "notes.txt",
    });
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "msg-missing-visible",
      "summarize this"
    );
    expect(result).toEqual({ kind: "fail" });
  });

  test("fails when object storage throws for a bound text file instead of dropping it", async () => {
    await insertBound(db, {
      id: "att-throw",
      accountId: "acct-a",
      messageId: "msg-throw",
      mimeType: "text/plain",
    });
    const throwing = {
      async get() {
        throw new Error("r2");
      },
    } as unknown as R2Bucket;
    const result = await composeGenerationPrompt(
      db,
      throwing,
      "acct-a",
      "msg-throw",
      "summarize this"
    );
    expect(result).toEqual({ kind: "fail" });
  });

  test("visible user text omits an empty bound text file", async () => {
    await insertBound(db, {
      id: "att-empty-file",
      accountId: "acct-a",
      messageId: "msg-empty-file",
      mimeType: "text/plain",
      displayName: "notes.txt",
    });
    r2.putBytes("attachments/acct-a/att-empty-file", new Uint8Array());
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "msg-empty-file",
      "summarize this"
    );
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(result.prompt).toBe("summarize this");
    expect(result.prompt).not.toContain("notes.txt");
  });

  test("fails when a bound text object contains NUL bytes instead of dropping it from a visible prompt", async () => {
    await insertBound(db, {
      id: "att-nul",
      accountId: "acct-a",
      messageId: "msg-nul",
      mimeType: "text/plain",
      displayName: "notes.txt",
    });
    r2.putBytes(
      "attachments/acct-a/att-nul",
      new Uint8Array([0x68, 0x69, 0x00, 0x21])
    );
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "msg-nul",
      "summarize this"
    );
    expect(result).toEqual({ kind: "fail" });
  });

  test("fails when a bound text object is invalid UTF-8 instead of dropping it from a visible prompt", async () => {
    await insertBound(db, {
      id: "att-bad-utf8",
      accountId: "acct-a",
      messageId: "msg-bad-utf8",
      mimeType: "text/plain",
      displayName: "notes.txt",
    });
    r2.putBytes(
      "attachments/acct-a/att-bad-utf8",
      new Uint8Array([0xff, 0xfe])
    );
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "msg-bad-utf8",
      "summarize this"
    );
    expect(result).toEqual({ kind: "fail" });
  });

  test("keeps a valid UTF-8 prefix when the excerpt budget cuts a multi-byte character", async () => {
    const euro = new TextEncoder().encode("€");
    const completeCount = Math.floor(
      GENERATION_ATTACHMENT_TEXT_BUDGET / euro.byteLength
    );
    const bytes = new Uint8Array((completeCount + 1) * euro.byteLength);
    for (let i = 0; i < completeCount + 1; i++) {
      bytes.set(euro, i * euro.byteLength);
    }
    await insertBound(db, {
      id: "att-budget-utf8",
      accountId: "acct-a",
      messageId: "msg-budget-utf8",
      mimeType: "text/plain",
      displayName: "notes.txt",
    });
    r2.putBytes("attachments/acct-a/att-budget-utf8", bytes);
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "msg-budget-utf8",
      "summarize this"
    );
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(result.prompt).toContain("summarize this");
    expect(result.prompt).toContain("€".repeat(completeCount));
    expect(result.prompt).not.toContain("€".repeat(completeCount + 1));
  });

  test("fails when a truncated range still contains invalid UTF-8", async () => {
    const bytes = new Uint8Array(GENERATION_ATTACHMENT_TEXT_BUDGET + 8);
    bytes.fill(0x61);
    bytes[16] = 0xff;
    await insertBound(db, {
      id: "att-trunc-bad-utf8",
      accountId: "acct-a",
      messageId: "msg-trunc-bad-utf8",
      mimeType: "text/plain",
      displayName: "notes.txt",
    });
    r2.putBytes("attachments/acct-a/att-trunc-bad-utf8", bytes);
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "msg-trunc-bad-utf8",
      "summarize this"
    );
    expect(result).toEqual({ kind: "fail" });
  });

  test("fails when a complete bound text object ends with a truncated UTF-8 sequence", async () => {
    await insertBound(db, {
      id: "att-incomplete-utf8",
      accountId: "acct-a",
      messageId: "msg-incomplete-utf8",
      mimeType: "text/plain",
      displayName: "notes.txt",
    });
    r2.putBytes(
      "attachments/acct-a/att-incomplete-utf8",
      new Uint8Array([0x63, 0x61, 0x66, 0xc3])
    );
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "msg-incomplete-utf8",
      "summarize this"
    );
    expect(result).toEqual({ kind: "fail" });
  });

  test("fails when the user text is only whitespace and no attachment bytes load", async () => {
    const blank = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "msg-whitespace",
      " \t\n"
    );
    await insertBound(db, {
      id: "att-gone-whitespace",
      accountId: "acct-a",
      messageId: "msg-whitespace-files",
      mimeType: "text/plain",
    });
    const unreadable = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "msg-whitespace-files",
      " \t\n"
    );
    expect(blank).toEqual({ kind: "fail" });
    expect(unreadable).toEqual({ kind: "fail" });
  });

  test("fails when user text and loaded attachment excerpts are only whitespace", async () => {
    await insertBound(db, {
      id: "att-whitespace-excerpt",
      accountId: "acct-a",
      messageId: "msg-whitespace-excerpt",
      mimeType: "text/plain",
      displayName: "notes.txt",
    });
    r2.putBytes(
      "attachments/acct-a/att-whitespace-excerpt",
      new TextEncoder().encode(" \t\n")
    );
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "msg-whitespace-excerpt",
      " \t\n"
    );
    expect(result).toEqual({ kind: "fail" });
  });

  test("visible user text omits whitespace-only attachment excerpts", async () => {
    await insertBound(db, {
      id: "att-whitespace-omit",
      accountId: "acct-a",
      messageId: "msg-whitespace-omit",
      mimeType: "text/plain",
      displayName: "notes.txt",
    });
    r2.putBytes(
      "attachments/acct-a/att-whitespace-omit",
      new TextEncoder().encode(" \t\n")
    );
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "msg-whitespace-omit",
      "summarize this"
    );
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(result.prompt).toBe("summarize this");
    expect(result.prompt).not.toContain("notes.txt");
  });

  test("keeps visible attachment speech after a NEXT LINE prefix longer than the excerpt budget", async () => {
    const prefix = "\u0085".repeat(GENERATION_ATTACHMENT_TEXT_BUDGET / 2);
    await insertBound(db, {
      id: "att-nel-budget",
      accountId: "acct-a",
      messageId: "msg-nel-budget",
      mimeType: "text/plain",
      displayName: "notes.txt",
    });
    r2.putBytes(
      "attachments/acct-a/att-nel-budget",
      new TextEncoder().encode(`${prefix}Recorded words`)
    );
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "msg-nel-budget",
      "summarize this"
    );
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(result.prompt).toContain("summarize this");
    expect(result.prompt).toContain("Recorded words");
    expect(result.prompt).toContain("notes.txt");
  });

  test("quotes a NEXT LINE-prefixed attachment name without padding the prompt label", async () => {
    await insertBound(db, {
      id: "att-nel-name",
      accountId: "acct-a",
      messageId: "msg-nel-name",
      mimeType: "text/plain",
      displayName: `\u0085notes.txt`,
    });
    r2.putBytes(
      "attachments/acct-a/att-nel-name",
      new TextEncoder().encode("visible file bytes")
    );
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "msg-nel-name",
      "summarize this"
    );
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(result.prompt).toContain("summarize this");
    expect(result.prompt).toContain("visible file bytes");
    expect(result.prompt).toContain('Attachment "notes.txt":');
    expect(result.prompt).not.toContain("\u0085");
  });

  test("omits a NEXT LINE-only attachment name while keeping visible file bytes", async () => {
    await insertBound(db, {
      id: "att-nel-blank-name",
      accountId: "acct-a",
      messageId: "msg-nel-blank-name",
      mimeType: "text/plain",
      displayName: "\u0085",
    });
    r2.putBytes(
      "attachments/acct-a/att-nel-blank-name",
      new TextEncoder().encode("visible file bytes")
    );
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "msg-nel-blank-name",
      "summarize this"
    );
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(result.prompt).toContain("summarize this");
    expect(result.prompt).toContain("visible file bytes");
    expect(result.prompt).not.toContain('Attachment "');
  });

  test("omits a whitespace-only attachment name while keeping visible file bytes", async () => {
    await insertBound(db, {
      id: "att-blank-name",
      accountId: "acct-a",
      messageId: "msg-blank-name",
      mimeType: "text/plain",
      displayName: " \t\n",
    });
    r2.putBytes(
      "attachments/acct-a/att-blank-name",
      new TextEncoder().encode("visible file bytes")
    );
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "msg-blank-name",
      "summarize this"
    );
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(result.prompt).toContain("summarize this");
    expect(result.prompt).toContain("visible file bytes");
    expect(result.prompt).not.toContain('Attachment "');
  });

  test("whitespace-only user text still composes when a bound text file loads", async () => {
    await insertBound(db, {
      id: "att-whitespace-ok",
      accountId: "acct-a",
      messageId: "msg-whitespace-ok",
      mimeType: "text/plain",
      displayName: "notes.txt",
    });
    r2.putBytes(
      "attachments/acct-a/att-whitespace-ok",
      new TextEncoder().encode("visible file bytes")
    );
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "msg-whitespace-ok",
      " \t\n"
    );
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(result.prompt).toContain("visible file bytes");
    expect(result.prompt).toContain("notes.txt");
    expect(result.prompt).not.toContain(" \t\n");
  });

  test("keeps visible user text that still has surrounding whitespace", async () => {
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "msg-padded",
      "  hello  "
    );
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(result.prompt).toBe("  hello  ");
  });

  test("text attachments without object storage are unavailable instead of dropping bytes", async () => {
    await insertBound(db, {
      id: "att-unbound",
      accountId: "acct-a",
      messageId: "msg-unbound",
      mimeType: "text/plain",
    });
    const nonempty = await composeGenerationPrompt(
      db,
      undefined,
      "acct-a",
      "msg-unbound",
      "summarize this"
    );
    const empty = await composeGenerationPrompt(
      db,
      undefined,
      "acct-a",
      "msg-unbound",
      ""
    );
    expect(nonempty).toEqual({ kind: "unavailable" });
    expect(empty).toEqual({ kind: "unavailable" });
  });

  test("text-only prompts still compose without object storage", async () => {
    const result = await composeGenerationPrompt(
      db,
      undefined,
      "acct-a",
      "msg-text-only",
      "hello"
    );
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(result.prompt).toBe("hello");
  });

  test("non-text attachments still compose without object storage", async () => {
    await insertBound(db, {
      id: "att-pdf",
      accountId: "acct-a",
      messageId: "msg-pdf",
      mimeType: "application/pdf",
      displayName: "notes.pdf",
    });
    const result = await composeGenerationPrompt(
      db,
      undefined,
      "acct-a",
      "msg-pdf",
      "look at this"
    );
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(result.prompt).toBe("look at this");
    expect(result.prompt).not.toContain("notes.pdf");
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

  test("fails when a later bound text object is missing after the excerpt budget is spent", async () => {
    const first = "a".repeat(GENERATION_ATTACHMENT_TEXT_BUDGET);
    await insertBound(db, {
      id: "att-budget-spent",
      accountId: "acct-a",
      messageId: "msg-later-missing",
      mimeType: "text/plain",
      displayName: "a.txt",
    });
    await insertBound(db, {
      id: "att-later-gone",
      accountId: "acct-a",
      messageId: "msg-later-missing",
      mimeType: "text/plain",
      displayName: "b.txt",
    });
    r2.putBytes(
      "attachments/acct-a/att-budget-spent",
      new TextEncoder().encode(first)
    );
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "msg-later-missing",
      "cap"
    );
    expect(result).toEqual({ kind: "fail" });
  });

  test("keeps the excerpt cap when later bound text objects still exist", async () => {
    const first = "a".repeat(GENERATION_ATTACHMENT_TEXT_BUDGET);
    const second = "b".repeat(20);
    await insertBound(db, {
      id: "att-budget-full",
      accountId: "acct-a",
      messageId: "msg-later-present",
      mimeType: "text/plain",
      displayName: "a.txt",
    });
    await insertBound(db, {
      id: "att-later-present",
      accountId: "acct-a",
      messageId: "msg-later-present",
      mimeType: "text/plain",
      displayName: "b.txt",
    });
    r2.putBytes(
      "attachments/acct-a/att-budget-full",
      new TextEncoder().encode(first)
    );
    r2.putBytes(
      "attachments/acct-a/att-later-present",
      new TextEncoder().encode(second)
    );
    const result = await composeGenerationPrompt(
      db,
      r2,
      "acct-a",
      "msg-later-present",
      "cap"
    );
    expect(result.kind).toBe("ok");
    if (result.kind !== "ok") return;
    expect(result.prompt).toContain(first);
    expect(result.prompt).not.toContain(second);
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

describe("isVisibleGenerationText", () => {
  test("rejects empty and whitespace-only provider text", () => {
    expect(visibleGenerationTrim("\u0085hello\u0085")).toBe("hello");
    expect(visibleGenerationTrim("\u0085")).toBe("");
    expect(isVisibleGenerationText("")).toBe(false);
    expect(isVisibleGenerationText(" \t\n")).toBe(false);
    expect(isVisibleGenerationText("\u0085")).toBe(false);
    expect(isVisibleGenerationText(" \u0085 ")).toBe(false);
    expect(isVisibleGenerationText(null)).toBe(false);
    expect(isVisibleGenerationText(undefined)).toBe(false);
  });

  test("accepts provider text that still has visible characters", () => {
    expect(isVisibleGenerationText("ok")).toBe(true);
    expect(isVisibleGenerationText("  ok  ")).toBe(true);
  });
});

describe("failGeneration retryability", () => {
  test("provider failures stay retryable", async () => {
    const event = await failGeneration(db, "acct-a", "gen-retry");
    expect(event).toEqual({
      id: "2",
      kind: "failed",
      error: { code: "generation_failed", retryable: true },
    });
  });

  test("missing object storage does not advertise retry", async () => {
    const event = await failGeneration(db, "acct-a", "gen-store", false);
    expect(event).toEqual({
      id: "2",
      kind: "failed",
      error: { code: "generation_failed", retryable: false },
    });
  });
});

const seedAdmittedHuman = async (
  database: D1Database,
  accountId: string,
  messageId: string,
  generationId: string
) => {
  await database
    .prepare(
      "INSERT INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, 'human', 1, NULL, 1, NULL)"
    )
    .bind(messageId, accountId, "hello")
    .run();
  await database
    .prepare(
      "INSERT INTO chat_admissions (message_id, account_id, op_id, payload, generation_id) VALUES (?, ?, ?, ?, ?)"
    )
    .bind(messageId, accountId, "op-1", "{}", generationId)
    .run();
};

const countAssistantRows = async (
  database: D1Database,
  accountId: string
): Promise<number> => {
  const row = await database
    .prepare(
      "SELECT COUNT(*) AS count FROM chat_messages WHERE account_id = ? AND sender = 'ai'"
    )
    .bind(accountId)
    .first<{ count: number }>();
  return row?.count ?? 0;
};

describe("completeGeneration visibility", () => {
  test("fails empty text instead of persisting a blank assistant", async () => {
    await seedAdmittedHuman(db, "acct-a", "msg-empty", "gen-empty");
    const event = await completeGeneration(db, "acct-a", "gen-empty", "");
    expect(event).toEqual({
      id: "2",
      kind: "failed",
      error: { code: "generation_failed", retryable: true },
    });
    expect(await countAssistantRows(db, "acct-a")).toBe(0);
  });

  test("fails whitespace-only text instead of persisting a blank assistant", async () => {
    await seedAdmittedHuman(db, "acct-a", "msg-blank", "gen-blank");
    const event = await completeGeneration(db, "acct-a", "gen-blank", " \t\n");
    expect(event).toEqual({
      id: "2",
      kind: "failed",
      error: { code: "generation_failed", retryable: true },
    });
    expect(await countAssistantRows(db, "acct-a")).toBe(0);
  });

  test("persists visible padded text as a completed assistant", async () => {
    await seedAdmittedHuman(db, "acct-a", "msg-padded", "gen-padded");
    const event = await completeGeneration(
      db,
      "acct-a",
      "gen-padded",
      "  ok  "
    );
    expect(event.kind).toBe("done");
    if (event.kind !== "done") throw new Error("expected done event");
    expect(event.message.text).toBe("  ok  ");
    expect(await countAssistantRows(db, "acct-a")).toBe(1);
  });

  test("completeGeneration copies the human session onto the assistant", async () => {
    const human = {
      id: "msg-session",
      text: "hello",
      sender: "human",
      type: "text",
      createdAt: 1,
      updatedAt: 1,
      chatSessionId: "named-session",
      appId: null,
      journalRevision: 0,
      payloadHash: "sha256:test",
      messageSource: "desktop_chat",
      rating: null,
      reported: false,
      generationOutcome: null,
      revision: "1",
      attachments: [],
    };
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, 'human', ?, NULL, 1, ?)"
      )
      .bind(
        human.id,
        "acct-a",
        human.text,
        human.createdAt,
        JSON.stringify(human)
      )
      .run();
    await db
      .prepare(
        "INSERT INTO chat_admissions (message_id, account_id, op_id, payload, generation_id) VALUES (?, ?, ?, ?, ?)"
      )
      .bind(human.id, "acct-a", "op-session", "{}", "gen-session")
      .run();
    const event = await completeGeneration(db, "acct-a", "gen-session", "ok");
    expect(event.kind).toBe("done");
    if (event.kind !== "done") throw new Error("expected done event");
    expect(event.message.chatSessionId).toBe("named-session");
    expect(event.message).not.toHaveProperty("fromColumns");
  });

  test("completeGeneration of a stored createdAt that fails detach is unavailable", async () => {
    const human = {
      id: "msg-negative-created-at-complete",
      text: "hello",
      sender: "human",
      type: "text",
      createdAt: -1,
      updatedAt: -1,
      chatSessionId: "named-session",
      appId: null,
      journalRevision: 0,
      payloadHash: "sha256:test",
      messageSource: "desktop_chat",
      rating: null,
      reported: false,
      generationOutcome: null,
      revision: "1",
      attachments: [],
    };
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, 'human', ?, NULL, 1, ?)"
      )
      .bind(human.id, "acct-a", human.text, 1, JSON.stringify(human))
      .run();
    await db
      .prepare(
        "INSERT INTO chat_admissions (message_id, account_id, op_id, payload, generation_id) VALUES (?, ?, ?, ?, ?)"
      )
      .bind(
        human.id,
        "acct-a",
        "op-negative-complete",
        "{}",
        "gen-negative-created-at-complete"
      )
      .run();
    await expect(
      completeGeneration(
        db,
        "acct-a",
        "gen-negative-created-at-complete",
        "visible reply"
      )
    ).rejects.toThrow("invalid chat message record");
    expect(await countAssistantRows(db, "acct-a")).toBe(0);
  });

  test("empty text still requires admission", async () => {
    await expect(
      completeGeneration(db, "acct-a", "gen-missing", "")
    ).rejects.toThrow("admission not found for generation");
  });

  test("fails instead of throwing when the admitted human payload disagrees with columns", async () => {
    const human = {
      id: "msg-mismatch-complete",
      text: "hello",
      sender: "human",
      type: "text",
      createdAt: 1,
      updatedAt: 1,
      chatSessionId: null,
      appId: null,
      journalRevision: 0,
      payloadHash: "sha256:test",
      messageSource: "desktop_chat",
      rating: null,
      reported: false,
      generationOutcome: null,
      revision: "1",
      attachments: [],
    };
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, 'human', ?, NULL, 1, ?)"
      )
      .bind(
        human.id,
        "acct-a",
        human.text,
        human.createdAt,
        JSON.stringify({ ...human, id: "other-id" })
      )
      .run();
    await db
      .prepare(
        "INSERT INTO chat_admissions (message_id, account_id, op_id, payload, generation_id) VALUES (?, ?, ?, ?, ?)"
      )
      .bind(human.id, "acct-a", "op-mismatch", "{}", "gen-mismatch-complete")
      .run();
    const event = await completeGeneration(
      db,
      "acct-a",
      "gen-mismatch-complete",
      "visible reply"
    );
    expect(event).toEqual({
      id: "2",
      kind: "failed",
      error: { code: "generation_failed", retryable: true },
    });
    expect(await countAssistantRows(db, "acct-a")).toBe(0);
  });
});

describe("admit replay attachments", () => {
  test("replay keeps bound attachments when payload JSON is unreadable", async () => {
    const create = {
      op: "create" as const,
      opId: "op-replay-attach",
      id: "msg-replay-attach",
      at: 1,
      text: "hello with file",
      sender: "human" as const,
      journalRevision: 1,
      attachmentIds: ["att-notes"],
      chatSessionId: "named-session",
    };
    const now = 1;
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, 'human', ?, NULL, 1, ?)"
      )
      .bind(create.id, "acct-a", create.text, now, "{broken")
      .run();
    await db
      .prepare(
        "INSERT INTO chat_attachments (id, account_id, op_id, display_name, media_type, size_bytes, state, r2_key, expires_at, bound_message_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'bound', ?, ?, ?, ?, ?)"
      )
      .bind(
        "att-notes",
        "acct-a",
        "op-att-notes",
        "notes.pdf",
        "application/pdf",
        1024,
        "attachments/acct-a/att-notes",
        now + 86_400_000,
        create.id,
        now,
        now
      )
      .run();
    await db
      .prepare(
        "INSERT INTO chat_admissions (message_id, account_id, op_id, payload, generation_id) VALUES (?, ?, ?, ?, ?)"
      )
      .bind(
        create.id,
        "acct-a",
        create.opId,
        JSON.stringify({ ...create, journalRevision: 0 }),
        "gen-replay-attach"
      )
      .run();

    const admitted = await admitMessage(db, "acct-a", create, null);
    expect(admitted).toMatchObject({ created: false });
    if (typeof admitted === "string") throw new Error(admitted);
    expect(admitted.message.attachments).toEqual([
      {
        id: "att-notes",
        displayName: "notes.pdf",
        mediaType: "application/pdf",
        sizeBytes: 1024,
        contentReference: "att-notes",
      },
    ]);
    const stored = await db
      .prepare("SELECT payload FROM chat_messages WHERE id = ?")
      .bind(create.id)
      .first<{ payload: string }>();
    expect(JSON.parse(stored!.payload).attachments).toEqual(
      admitted.message.attachments
    );
    expect(admitted.message.chatSessionId).toBe("named-session");
    expect(JSON.parse(stored!.payload).chatSessionId).toBe("named-session");
  });

  test("admit replay of an unreadable stored ChatCreate is conflict instead of throwing", async () => {
    const create = {
      op: "create" as const,
      opId: "op-replay-broken-admit",
      id: "msg-replay-broken-admit",
      at: 1,
      text: "hello",
      sender: "human" as const,
      journalRevision: 0,
      attachmentIds: [] as string[],
    };
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, 'human', ?, NULL, 1, ?)"
      )
      .bind(create.id, "acct-a", create.text, 1, JSON.stringify(create))
      .run();
    await db
      .prepare(
        "INSERT INTO chat_admissions (message_id, account_id, op_id, payload, generation_id) VALUES (?, ?, ?, ?, ?)"
      )
      .bind(
        create.id,
        "acct-a",
        create.opId,
        "{broken",
        "gen-replay-broken-admit"
      )
      .run();
    await expect(admitMessage(db, "acct-a", create, null)).resolves.toBe(
      "conflict"
    );
  });

  test("admit replay of a stored createdAt that fails detach is unavailable", async () => {
    const create = {
      op: "create" as const,
      opId: "op-replay-negative-created-at",
      id: "msg-replay-negative-created-at",
      at: 1,
      text: "hello",
      sender: "human" as const,
      journalRevision: 0,
      attachmentIds: [] as string[],
    };
    const stored = {
      id: create.id,
      text: create.text,
      sender: "human",
      type: "text",
      createdAt: -1,
      updatedAt: -1,
      chatSessionId: null,
      appId: null,
      journalRevision: 0,
      payloadHash: "sha256:test",
      messageSource: "desktop_chat",
      rating: null,
      reported: false,
      generationOutcome: null,
      revision: "1",
      attachments: [],
    };
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, 'human', ?, NULL, 1, ?)"
      )
      .bind(create.id, "acct-a", create.text, 1, JSON.stringify(stored))
      .run();
    await db
      .prepare(
        "INSERT INTO chat_admissions (message_id, account_id, op_id, payload, generation_id) VALUES (?, ?, ?, ?, ?)"
      )
      .bind(
        create.id,
        "acct-a",
        create.opId,
        JSON.stringify(create),
        "gen-replay-negative-created-at"
      )
      .run();

    await expect(admitMessage(db, "acct-a", create, null)).rejects.toThrow(
      "invalid chat message record"
    );
  });

  test("admit replay of a JSON-null stored ChatCreate is conflict instead of throwing", async () => {
    const create = {
      op: "create" as const,
      opId: "op-replay-null-admit",
      id: "msg-replay-null-admit",
      at: 1,
      text: "hello",
      sender: "human" as const,
      journalRevision: 0,
      attachmentIds: [] as string[],
    };
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, 'human', ?, NULL, 1, ?)"
      )
      .bind(create.id, "acct-a", create.text, 1, JSON.stringify(create))
      .run();
    await db
      .prepare(
        "INSERT INTO chat_admissions (message_id, account_id, op_id, payload, generation_id) VALUES (?, ?, ?, ?, ?)"
      )
      .bind(create.id, "acct-a", create.opId, "null", "gen-replay-null-admit")
      .run();
    await expect(admitMessage(db, "acct-a", create, null)).resolves.toBe(
      "conflict"
    );
  });

  test("admit replay of a column-mismatched human payload is conflict instead of throwing", async () => {
    const create = {
      op: "create" as const,
      opId: "op-replay-mismatch-human",
      id: "msg-replay-mismatch-human",
      at: 1,
      text: "hello",
      sender: "human" as const,
      journalRevision: 0,
      attachmentIds: [] as string[],
    };
    await db
      .prepare(
        "INSERT INTO chat_messages (id, account_id, text, sender, created_at, generation_outcome, position, payload) VALUES (?, ?, ?, 'human', ?, NULL, 1, ?)"
      )
      .bind(
        create.id,
        "acct-a",
        create.text,
        1,
        JSON.stringify({ ...create, id: "other-id" })
      )
      .run();
    await db
      .prepare(
        "INSERT INTO chat_admissions (message_id, account_id, op_id, payload, generation_id) VALUES (?, ?, ?, ?, ?)"
      )
      .bind(
        create.id,
        "acct-a",
        create.opId,
        JSON.stringify(create),
        "gen-replay-mismatch-human"
      )
      .run();
    await expect(admitMessage(db, "acct-a", create, null)).resolves.toBe(
      "conflict"
    );
  });
});

describe("pending generation admission", () => {
  const insertPending = async (
    generationId: string,
    messageId: string,
    payload: string
  ) => {
    await db
      .prepare(
        "INSERT INTO chat_admissions (message_id, account_id, op_id, payload, generation_id) VALUES (?, ?, ?, ?, ?)"
      )
      .bind(messageId, "acct-a", `op-${messageId}`, payload, generationId)
      .run();
    await db
      .prepare(
        "INSERT OR IGNORE INTO chat_generation_events (generation_id, account_id, event_id, ordinal, payload) VALUES (?, ?, '1', 1, ?)"
      )
      .bind(
        generationId,
        "acct-a",
        JSON.stringify({ id: "1", kind: "snapshot", text: "" })
      )
      .run();
  };

  test("readPendingGeneration keeps an unreadable admission payload instead of throwing", async () => {
    await insertPending("gen-broken", "broken-human", "{broken");
    await insertPending(
      "gen-ok",
      "ok-human",
      JSON.stringify({
        op: "create",
        opId: "op-ok-human",
        id: "ok-human",
        at: 1,
        text: "hello",
        sender: "human",
        journalRevision: 0,
        attachmentIds: [],
      })
    );
    await expect(readPendingGeneration(db, "acct-a")).resolves.toEqual({
      generationId: "gen-broken",
      input: "unreadable",
    });
  });

  test("failing an unreadable pending admission unblocks the next generation", async () => {
    await insertPending("gen-broken", "broken-human", "null");
    await insertPending(
      "gen-ok",
      "ok-human",
      JSON.stringify({
        op: "create",
        opId: "op-ok-human",
        id: "ok-human",
        at: 1,
        text: "hello",
        sender: "human",
        journalRevision: 0,
        attachmentIds: [],
      })
    );
    const pending = await readPendingGeneration(db, "acct-a");
    expect(pending).toEqual({
      generationId: "gen-broken",
      input: "unreadable",
    });
    const failed = await failGeneration(db, "acct-a", "gen-broken");
    expect(failed).toEqual({
      id: "2",
      kind: "failed",
      error: { code: "generation_failed", retryable: true },
    });
    const next = await readPendingGeneration(db, "acct-a");
    expect(next).not.toBeNull();
    expect(next).toMatchObject({
      generationId: "gen-ok",
      input: { id: "ok-human", text: "hello", sender: "human" },
    });
  });
});

describe("generation event payloads", () => {
  const readableCreate = (id: string) => ({
    op: "create" as const,
    opId: `op-${id}`,
    id,
    at: 1,
    text: "hello",
    sender: "human" as const,
    journalRevision: 0,
    attachmentIds: [] as string[],
  });

  const insertPending = async (
    generationId: string,
    messageId: string,
    eventPayload: string
  ) => {
    await db
      .prepare(
        "INSERT INTO chat_admissions (message_id, account_id, op_id, payload, generation_id) VALUES (?, ?, ?, ?, ?)"
      )
      .bind(
        messageId,
        "acct-a",
        `op-${messageId}`,
        JSON.stringify(readableCreate(messageId)),
        generationId
      )
      .run();
    await db
      .prepare(
        "INSERT OR IGNORE INTO chat_generation_events (generation_id, account_id, event_id, ordinal, payload) VALUES (?, ?, '1', 1, ?)"
      )
      .bind(generationId, "acct-a", eventPayload)
      .run();
  };

  test("terminalEvent keeps an unreadable snapshot instead of throwing", async () => {
    await insertPending("gen-broken-event", "event-human", "{broken");
    await expect(terminalEvent(db, "acct-a", "gen-broken-event")).resolves.toBe(
      "unreadable"
    );
  });

  test("terminalEvent keeps a JSON-null snapshot instead of throwing", async () => {
    await insertPending("gen-null-event", "null-event-human", "null");
    await expect(terminalEvent(db, "acct-a", "gen-null-event")).resolves.toBe(
      "unreadable"
    );
  });

  test("terminalEvent keeps a done event missing its message instead of throwing", async () => {
    await insertPending(
      "gen-done-missing",
      "done-missing-human",
      JSON.stringify({ id: "1", kind: "snapshot", text: "" })
    );
    await db
      .prepare(
        "INSERT INTO chat_generation_events (generation_id, account_id, event_id, ordinal, payload) VALUES (?, ?, '2', 2, ?)"
      )
      .bind(
        "gen-done-missing",
        "acct-a",
        JSON.stringify({ id: "2", kind: "done" })
      )
      .run();
    await expect(terminalEvent(db, "acct-a", "gen-done-missing")).resolves.toBe(
      "unreadable"
    );
  });

  test("failing a pending generation with an unreadable snapshot unblocks the next generation", async () => {
    await insertPending("gen-broken-event", "event-human", "{broken");
    await insertPending(
      "gen-ok-event",
      "ok-event-human",
      JSON.stringify({ id: "1", kind: "snapshot", text: "" })
    );
    await expect(readPendingGeneration(db, "acct-a")).resolves.toMatchObject({
      generationId: "gen-broken-event",
      input: { id: "event-human" },
    });
    await expect(terminalEvent(db, "acct-a", "gen-broken-event")).resolves.toBe(
      "unreadable"
    );
    const failed = await failGeneration(db, "acct-a", "gen-broken-event");
    expect(failed).toEqual({
      id: "2",
      kind: "failed",
      error: { code: "generation_failed", retryable: true },
    });
    await expect(readPendingGeneration(db, "acct-a")).resolves.toMatchObject({
      generationId: "gen-ok-event",
      input: { id: "ok-event-human" },
    });
  });
});
