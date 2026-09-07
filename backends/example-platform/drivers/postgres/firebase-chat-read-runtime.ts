// domain-pending(DIV-CHAT-SENDER-001)
// domain-pending(DIV-CHAT-TYPE-001)
// domain-pending(DIV-CHAT-SESSION-001)
// domain-pending(DIV-CHAT-REV-001)
// domain-pending(DIV-CHAT-HASH-001)
// domain-pending(DIV-CHAT-SOURCE-001)

import {
  ExpiredChatHistoryCursorError,
  InvalidChatHistoryCursorError,
  createChatHistoryCursorCodec,
} from "../../apps/service/chat/history-cursor";
import { createServedCounter } from "../../apps/service/observability/served-count";
import {
  CHAT_CAPABILITIES,
  parseHistoryQuery,
  projectLoadedHistoryMessage,
} from "../../apps/service/routes/chat-messages";
import type { McpCursorSigningKeyset } from "../../apps/mcp/cursor";
import {
  createPostgresFirebaseAuthorizationRuntime,
  type PostgresFirebaseAuthorizationRuntimeOptions,
} from "./firebase-authorized-runtime-support";
import { withAuthorizedChatRead } from "./chat-read-repository";

export interface PostgresFirebaseChatReadOptions {
  readonly authorization: PostgresFirebaseAuthorizationRuntimeOptions;
  readonly codecRootSecret: Uint8Array;
  readonly cursorSigningKeyset: McpCursorSigningKeyset;
}

const CHAT_CURSOR_TTL_SECONDS = 3_600;
const SERVICE_UNAVAILABLE_RETRY_AFTER_SECONDS = 60;
const JSON_HEADERS = Object.freeze({
  "cache-control": "no-store",
  "content-type": "application/json",
});

const json = (
  body: unknown,
  status: number,
  extra: Readonly<Record<string, string>> = {},
): Response => new Response(
  typeof body === "string" ? body : JSON.stringify(body),
  { status, headers: { ...JSON_HEADERS, ...extra } },
);

const errorResponse = (
  status: number,
  code: string,
  action: string,
  retryable = false,
  extra: Readonly<Record<string, string>> = {},
): Response => json({ error: { code, retryable, action } }, status, extra);

const unavailable = (): Response => errorResponse(
  503,
  "service_unavailable",
  "retry",
  true,
  { "retry-after": String(SERVICE_UNAVAILABLE_RETRY_AFTER_SECONDS) },
);

export function createPostgresFirebaseChatReadRuntime(
  options: PostgresFirebaseChatReadOptions,
) {
  const runtime = createPostgresFirebaseAuthorizationRuntime(
    options.authorization,
    "chat.read",
  );
  void options.codecRootSecret;
  const cursor = createChatHistoryCursorCodec({
    activeId: options.cursorSigningKeyset.active_key_id,
    keys: options.cursorSigningKeyset.keys.map((key) => ({
      id: key.key_id,
      secret: new Uint8Array(key.secret),
    })),
  });
  const counter = createServedCounter();
  return Object.freeze({
    async executeRequest(request: Request): Promise<Response> {
      if (request.method !== "GET" || new URL(request.url).pathname !== "/v1/chat-messages") {
        return errorResponse(404, "not_found", "none");
      }
      try {
        request.signal.throwIfAborted();
        const token = request.headers.get("authorization")?.match(/^Bearer (\S+)$/)?.[1] ?? "";
        const authorization = await runtime.authorizer.authorize(
          token,
          Math.floor(Date.now() / 1000),
        );
        if (!authorization.authorized) {
          if (authorization.outcome === "authentication") {
            return errorResponse(401, "unauthorized", "reauthenticate");
          }
          return authorization.outcome === "unavailable"
            ? unavailable()
            : errorResponse(403, "forbidden", "none");
        }
        const query = parseHistoryQuery(request);
        if (query === null) {
          counter.recordDomainRead("denied");
          return errorResponse(400, "bad_request", "edit_request");
        }
        const authority = authorization.context;
        return await withAuthorizedChatRead(
          runtime.pool,
          authority,
          request.signal,
          async (storage) => {
            const accountEpoch = authority.account_epoch;
            const nowEpochSeconds = Math.floor(Date.now() / 1000);
            try {
              const claims = query.olderCursor === null ? null : cursor.verify(query.olderCursor, {
                accountId: authority.account_id,
                accountEpoch,
                nowEpochSeconds,
              });
              const snapshotSequence = claims?.snapshotSequence
                ?? await storage.readSnapshotSequence();
              const page = await storage.listHistory({
                limit: query.limit,
                snapshotSequence,
                olderThan: claims?.olderThan ?? null,
              });
              const messages = [];
              for (const message of page.messages) {
                const stored = message.sender === "ai"
                  ? await storage.readMessage(message.id)
                  : null;
                const generationEvents = stored?.generationId
                  ? await storage.listGenerationEvents(stored.generationId)
                  : null;
                messages.push(projectLoadedHistoryMessage(message, stored, generationEvents));
              }
              const oldest = messages[0];
              const olderCursor = page.hasOlder && oldest !== undefined
                ? cursor.issue({
                    accountId: authority.account_id,
                    accountEpoch,
                    snapshotSequence,
                    olderThan: { createdAt: oldest.createdAt, id: oldest.id },
                    issuedAtEpochSeconds: claims?.issuedAtEpochSeconds ?? nowEpochSeconds,
                    ttlSeconds: CHAT_CURSOR_TTL_SECONDS,
                  })
                : null;
              counter.recordDomainRead("served");
              return json({
                messages,
                page: { olderCursor, hasOlder: page.hasOlder },
                capabilities: CHAT_CAPABILITIES,
              }, 200);
            } catch (error) {
              if (error instanceof ExpiredChatHistoryCursorError) {
                counter.recordDomainRead("denied");
                return errorResponse(410, "cursor_expired", "refresh_history");
              }
              if (error instanceof InvalidChatHistoryCursorError) {
                counter.recordDomainRead("denied");
                return errorResponse(400, "bad_request", "refresh_history");
              }
              throw error;
            }
          },
        );
      } catch {
        counter.recordDomainRead("failed");
        return unavailable();
      }
    },
  });
}
