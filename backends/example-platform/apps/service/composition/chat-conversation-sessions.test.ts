import { describe, expect, test } from "bun:test";
import {
  MAIN_CHAT_CONVERSATION_ID,
  composeChatSessionsIntoConversationPage,
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
