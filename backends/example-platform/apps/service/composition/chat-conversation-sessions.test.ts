import { describe, expect, test } from "bun:test";
import {
  MAIN_CHAT_CONVERSATION_ID,
  composeChatSessionsIntoConversationPage,
  composeConversationUnionPage,
  type ChatConversationSessionItem,
} from "./chat-conversation-sessions";

const session = (
  overrides: Partial<ChatConversationSessionItem> = {},
): ChatConversationSessionItem => Object.freeze({
  id: MAIN_CHAT_CONVERSATION_ID,
  title: "hello",
  overview: "answer",
  createdAt: 1000,
  updatedAt: 2000,
  startedAt: 1000,
  finishedAt: null,
  source: "chat",
  status: "in_progress",
  discarded: false,
  starred: false,
  visibility: "private",
  isLocked: false,
  folderId: null,
  revision: null,
  ...overrides,
});

const page = (
  items: ReadonlyArray<Record<string, unknown>>,
  extras: Record<string, unknown> = {},
) => Object.freeze({
  contractVersion: "1.0.0",
  items,
  window: Object.freeze({
    status: "complete",
    complete: true,
    hasMore: false,
    nextCursor: extras.nextCursor ?? null,
  }),
  completeness: Object.freeze({
    version: "conversations-completeness-v1",
    status: "complete",
    reasons: Object.freeze([]),
  }),
  absence: items.length === 0 ? Object.freeze({ kind: "query_gap" }) : null,
});

describe("chat conversation composition", () => {
  test("does not invent chat:chat-main when no granted sessions exist", () => {
    expect(composeChatSessionsIntoConversationPage(page([]), [])).toBeNull();
    expect(composeChatSessionsIntoConversationPage(page([{
      id: "recording:one",
      updatedAt: 3000,
      title: "Recording",
    }]), [])).toBeNull();
  });

  test("merges a persisted main chat session onto the listen page without changing the cursor", () => {
    const listen = page([
      { id: "recording:newer", updatedAt: 4000, title: "Newer" },
      { id: "recording:older", updatedAt: 500, title: "Older" },
    ], { nextCursor: "listen-cursor" });
    const composed = composeChatSessionsIntoConversationPage(listen, [session()]);
    expect(composed?.window).toEqual(listen.window);
    expect(composed?.absence).toBeNull();
    expect(composed?.items.map((item) => item.id)).toEqual([
      "recording:newer",
      MAIN_CHAT_CONVERSATION_ID,
      "recording:older",
    ]);
  });

  test("replaces a listen-claimed chat id with the granted chat session and clears an empty-page gap", () => {
    const composed = composeChatSessionsIntoConversationPage(
      page([]),
      [session({ title: "saved prompt" })],
    );
    expect(composed?.absence).toBeNull();
    expect(composed?.items).toEqual([session({ title: "saved prompt" })]);
    expect(composeChatSessionsIntoConversationPage(
      page([{ id: MAIN_CHAT_CONVERSATION_ID, updatedAt: 1, title: "stale" }]),
      [session()],
    )?.items).toEqual([session()]);
  });

  test("rejects a malformed listen envelope instead of dropping or inventing rows", () => {
    expect(composeChatSessionsIntoConversationPage(null, [session()])).toBeNull();
    expect(composeChatSessionsIntoConversationPage({ items: "rows" }, [session()])).toBeNull();
    expect(composeChatSessionsIntoConversationPage(
      page([{ id: "recording:one", updatedAt: "later" }]),
      [session()],
    )).toBeNull();
  });

  test("merges a named chat session beside chat:chat-main without inventing extra rows", () => {
    const named = session({
      id: "chat:session-alpha",
      title: "named prompt",
      overview: "named answer",
      createdAt: 1500,
      updatedAt: 3500,
      startedAt: 1500,
    });
    const composed = composeChatSessionsIntoConversationPage(
      page([{ id: "recording:one", updatedAt: 3000, title: "Recording" }]),
      [session(), named],
    );
    expect(composed?.items.map((item) => item.id)).toEqual([
      named.id,
      "recording:one",
      MAIN_CHAT_CONVERSATION_ID,
    ]);
  });
});

const workerPaginate = (
  items: ReadonlyArray<{ id: string; updatedAt: number }>,
  limit: number,
  cursorId: string | undefined,
) => {
  const sorted = [...items].sort((left, right) => {
    if (right.updatedAt !== left.updatedAt) return right.updatedAt - left.updatedAt;
    return left.id < right.id ? -1 : left.id > right.id ? 1 : 0;
  });
  let start = 0;
  if (cursorId !== undefined) {
    const index = sorted.findIndex((item) => item.id === cursorId);
    if (index === -1) return "invalid_cursor" as const;
    start = index + 1;
  }
  const pageRows = sorted.slice(start, start + limit);
  return {
    items: pageRows,
    hasMore: start + pageRows.length < sorted.length,
  };
};

describe("conversation union pagination", () => {
  test("does not invent chat:chat-main when no granted sessions exist", () => {
    const empty = composeConversationUnionPage([], [], 1, null);
    expect(empty).toEqual({ items: [], hasMore: false });
    const listenOnly = composeConversationUnionPage(
      [{ id: "recording:one", updatedAt: 3000 }],
      [],
      1,
      null,
    );
    expect(listenOnly?.items.map((item) => item.id)).toEqual(["recording:one"]);
    expect(listenOnly?.hasMore).toBe(false);
  });

  test("keeps exact limit instead of dumping every chat onto the first page", () => {
    const listen = [
      { id: "recording:newer", updatedAt: 4000 },
      { id: "recording:older", updatedAt: 500 },
    ];
    const first = composeConversationUnionPage(listen, [session()], 1, null);
    expect(first?.items.map((item) => item.id)).toEqual(["recording:newer"]);
    expect(first?.hasMore).toBe(true);
    const second = composeConversationUnionPage(
      listen,
      [session()],
      1,
      { id: "recording:newer", updatedAt: 4000 },
    );
    expect(second?.items.map((item) => item.id)).toEqual([MAIN_CHAT_CONVERSATION_ID]);
    expect(second?.hasMore).toBe(true);
    const third = composeConversationUnionPage(
      listen,
      [session()],
      1,
      { id: MAIN_CHAT_CONVERSATION_ID, updatedAt: 2000 },
    );
    expect(third?.items.map((item) => item.id)).toEqual(["recording:older"]);
    expect(third?.hasMore).toBe(false);
  });

  test("matches Worker updatedAt DESC then id ASC paging when the full list is present", () => {
    const named = session({
      id: "chat:session-alpha",
      title: "named prompt",
      overview: "named answer",
      createdAt: 1500,
      updatedAt: 3500,
      startedAt: 1500,
    });
    const listen = [
      { id: "recording:one", updatedAt: 3000, title: "Recording" },
      { id: "recording:two", updatedAt: 100, title: "Older" },
    ];
    const universe = [...listen, session(), named].map((item) => ({
      id: String(item.id),
      updatedAt: Number(item.updatedAt),
    }));
    const workerFirst = workerPaginate(universe, 2, undefined);
    const unionFirst = composeConversationUnionPage(listen, [session(), named], 2, null);
    expect(workerFirst).not.toBe("invalid_cursor");
    if (workerFirst === "invalid_cursor") return;
    expect(unionFirst?.items.map((item) => item.id)).toEqual(
      workerFirst.items.map((item) => item.id),
    );
    expect(unionFirst?.hasMore).toBe(workerFirst.hasMore);
    const last = workerFirst.items[workerFirst.items.length - 1]!;
    const workerSecond = workerPaginate(universe, 2, last.id);
    const unionSecond = composeConversationUnionPage(
      listen,
      [session(), named],
      2,
      { id: last.id, updatedAt: last.updatedAt },
    );
    expect(workerSecond).not.toBe("invalid_cursor");
    if (workerSecond === "invalid_cursor") return;
    expect(unionSecond?.items.map((item) => item.id)).toEqual(
      workerSecond.items.map((item) => item.id),
    );
    expect(unionSecond?.hasMore).toBe(workerSecond.hasMore);
  });

  test("tie-breaks equal updatedAt with UTF-16 id order, matching Worker list paging", () => {
    const macron = session({
      id: "chat:Ā",
      title: "macron prompt",
      overview: "macron answer",
      createdAt: 4000,
      updatedAt: 4000,
      startedAt: 4000,
    });
    const ascii = session({
      id: "chat:session-ascii",
      title: "ascii prompt",
      overview: "ascii answer",
      createdAt: 4000,
      updatedAt: 4000,
      startedAt: 4000,
    });
    expect("chat:Ā" < "chat:session-ascii").toBe(false);
    const first = composeConversationUnionPage([], [macron, ascii], 1, null);
    expect(first?.items.map((item) => item.id)).toEqual(["chat:session-ascii"]);
    expect(first?.hasMore).toBe(true);
    const second = composeConversationUnionPage(
      [],
      [macron, ascii],
      1,
      { id: "chat:session-ascii", updatedAt: 4000 },
    );
    expect(second?.items.map((item) => item.id)).toEqual(["chat:Ā"]);
    expect(second?.hasMore).toBe(false);
    const workerFirst = workerPaginate(
      [macron, ascii].map((item) => ({ id: item.id, updatedAt: item.updatedAt })),
      1,
      undefined,
    );
    expect(workerFirst).not.toBe("invalid_cursor");
    if (workerFirst === "invalid_cursor") return;
    expect(workerFirst.items.map((item) => item.id)).toEqual(["chat:session-ascii"]);
  });

  test("rejects a malformed listen row instead of dropping or inventing rows", () => {
    expect(composeConversationUnionPage(
      [{ id: "recording:one", updatedAt: "later" }],
      [session()],
      1,
      null,
    )).toBeNull();
    expect(composeConversationUnionPage([], [session()], 0, null)).toBeNull();
  });
});
