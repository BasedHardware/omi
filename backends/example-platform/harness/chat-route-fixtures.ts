// domain-pending(DIV-CHAT-SENDER-001)
// domain-pending(DIV-CHAT-TYPE-001)
// domain-pending(DIV-CHAT-SESSION-001)
// domain-pending(DIV-CHAT-REV-001)
// domain-pending(DIV-CHAT-HASH-001)
// domain-pending(DIV-CHAT-SOURCE-001)

import type { createLocalDevService } from "../apps/service/app-facing";

/** Fixed wall-clock every chat route test posts with, so journal ordering is deterministic. */
export const CHAT_ROUTE_TEST_AT = 1_786_352_400_000;

/**
 * The canonical synthetic /v1/chat-messages create body shared by the chat route
 * test files. One copy so a new required field cannot be added to some tests'
 * payloads and not others; per-test divergence goes through `overrides`.
 */
export const chatCreatePayload = (
  id: string,
  at: number = CHAT_ROUTE_TEST_AT,
  overrides: Readonly<Record<string, unknown>> = {},
): Readonly<Record<string, unknown>> => Object.freeze({
  op: "create",
  opId: `op-${id}`,
  id,
  at,
  text: `message ${id}`,
  sender: "human",
  journalRevision: 1,
  type: "text",
  appId: null,
  chatSessionId: null,
  messageSource: "desktop_chat",
  metadata: null,
  attachmentIds: [],
  ...overrides,
});

/** POST a payload to the loopback chat route of a booted local dev service. */
export const postChatMessage = (
  local: ReturnType<typeof createLocalDevService>,
  body: unknown,
): Promise<Response> => Promise.resolve(local.app.request("/v1/chat-messages", {
  method: "POST",
  headers: { authorization: `Bearer ${local.devToken}`, "content-type": "application/json" },
  body: JSON.stringify(body),
}));
