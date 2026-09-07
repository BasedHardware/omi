import { createHash } from "node:crypto";
import { Hono } from "hono";
import {
  prepareConversationsRead,
  readConversationsPage,
} from "../../apps/service/composition/conversations-read";
import { composeConversationUnionPage } from "../../apps/service/composition/chat-conversation-sessions";
import {
  parseConversationReadWindow,
  registerConversationReadRoutes,
} from "../../apps/service/routes/conversations";
import { createServedCounter } from "../../apps/service/observability/served-count";
import type { McpCursorSigningKeyset } from "../../apps/mcp/cursor";
import {
  createPostgresFirebaseAuthorizationRuntime,
  type PostgresFirebaseAuthorizationRuntimeOptions,
} from "./firebase-authorized-runtime-support";
import { withAuthorizedConversationRead } from "./conversation-read-repository";
import { withAuthorizedChatRead } from "./chat-read-repository";
import type { ConversationReadSnapshot } from "./conversation-read-projection";
import type { AuthorizedLedgerWriteContext } from "../../apps/service/auth/authorized-context";

export interface PostgresFirebaseConversationReadOptions {
  readonly authorization: PostgresFirebaseAuthorizationRuntimeOptions;
  readonly codecRootSecret: Uint8Array;
  readonly cursorSigningKeyset: McpCursorSigningKeyset;
}
const failed = (status: number, error: string) =>
  Response.json(
    { error },
    { status, headers: { "cache-control": "no-store" } }
  );
const cursorHashOf = (cursor: string) =>
  createHash("sha256").update(cursor).digest("hex");
export function createPostgresFirebaseConversationReadRuntime(
  options: PostgresFirebaseConversationReadOptions
) {
  const runtime = createPostgresFirebaseAuthorizationRuntime(
    options.authorization,
    "conversations.read"
  );
  const chatRuntime = createPostgresFirebaseAuthorizationRuntime(
    options.authorization,
    "chat.read"
  );
  const secret = new Uint8Array(options.codecRootSecret);
  const keys = {
    active_key_id: options.cursorSigningKeyset.active_key_id,
    keys: options.cursorSigningKeyset.keys.map((key) => ({
      key_id: key.key_id,
      secret: new Uint8Array(key.secret),
    })),
  };
  const counter = createServedCounter();
  const preparedRead = (
    authority: AuthorizedLedgerWriteContext,
    snapshot: ConversationReadSnapshot,
    now: number,
    cursorPolicyVersion:
      | "conversations-read-cursor-v1"
      | "conversations-read-union-cursor-v1"
  ) => {
    const owner = (account: string) => {
      if (account !== authority.account_id)
        throw new TypeError("conversation_owner_mismatch");
    };
    const store = Object.freeze({
      listRecords(account: string) {
        owner(account);
        return snapshot.records.map((row) => row.record);
      },
      listOrderedRecords(account: string) {
        owner(account);
        return snapshot.records;
      },
      readStateRevision(account: string) {
        owner(account);
        return snapshot.revision;
      },
    });
    return prepareConversationsRead({
      store,
      resolveAuthorization: () => ({
        owner_account_id: authority.account_id,
        app_id: authority.application_id,
        key_id: authority.credential_id,
      }),
      codecRootSecret: secret,
      cursorSigningKeyset: keys,
      readTimestampEpochSeconds: now,
      appliedFrontierState: "caught_up",
      cursorPolicyVersion,
      authorityBinding: {
        kind: "persisted",
        authorizationDigest: authority.authorization_state_digest,
        grantDigest: createHash("sha256")
          .update(
            JSON.stringify([
              authority.grant_id,
              authority.grant_version,
              authority.credential_generation,
            ])
          )
          .digest("hex"),
        accountEpoch: authority.account_epoch,
      },
    });
  };
  return Object.freeze({
    async executeRequest(request: Request): Promise<Response> {
      if (
        request.method !== "GET" ||
        new URL(request.url).pathname !== "/v1/conversations"
      )
        return failed(404, "not_found");
      try {
        request.signal.throwIfAborted();
        const token =
          request.headers.get("authorization")?.match(/^Bearer (\S+)$/)?.[1] ??
          "";
        const authorization = await runtime.authorizer.authorize(
          token,
          Math.floor(Date.now() / 1000)
        );
        if (!authorization.authorized) {
          if (authorization.outcome === "authentication")
            return failed(401, "unauthorized");
          return authorization.outcome === "unavailable"
            ? failed(503, "unavailable")
            : failed(403, "forbidden");
        }
        const authority = authorization.context;
        const window = parseConversationReadWindow(request);
        if (window === null) return failed(400, "bad_request");
        const chatAuthorization = await chatRuntime.authorizer.authorize(
          token,
          Math.floor(Date.now() / 1000)
        );
        if (
          !window.legacy &&
          !chatAuthorization.authorized &&
          chatAuthorization.outcome !== "authorization"
        ) {
          return failed(503, "unavailable");
        }
        if (!window.legacy && chatAuthorization.authorized) {
          const chat = await withAuthorizedChatRead(
            chatRuntime.pool,
            chatAuthorization.context,
            request.signal,
            async (storage) =>
              Object.freeze({
                sessions: await storage.listConversationSessions(),
                snapshotSequence: await storage.readSnapshotSequence(),
              })
          );
          return withAuthorizedConversationRead(
            runtime.pool,
            authority,
            request.signal,
            async (metadata, now, storage) => {
              const prepared = preparedRead(
                authority,
                metadata,
                now,
                "conversations-read-union-cursor-v1"
              );
              const bindings = prepared.ports.bindingsFor(
                prepared.ports.resolveAttempt()
              );
              const digest = createHash("sha256")
                .update(
                  JSON.stringify([
                    "conversations-read-union-cursor-v1",
                    bindings,
                    chat.snapshotSequence,
                  ])
                )
                .digest("hex");
              let loaded;
              try {
                if (window.cursor !== null)
                  prepared.ports.verifyCursor(window.cursor, bindings);
                loaded = await storage.loadUnion(
                  window.limit + 1,
                  window.cursor === null ? null : cursorHashOf(window.cursor),
                  digest,
                  metadata.revision,
                  chat.snapshotSequence
                );
              } catch (error) {
                if (
                  error !== null &&
                  typeof error === "object" &&
                  "code" in error &&
                  error.code === "invalid_cursor"
                ) {
                  counter.recordDomainRead("denied");
                  return failed(400, "bad_request");
                }
                throw error;
              }
              const unionPrepared = preparedRead(
                authority,
                loaded.snapshot,
                now,
                "conversations-read-union-cursor-v1"
              );
              const projected = JSON.parse(
                readConversationsPage(
                  {
                    limit: Math.max(loaded.snapshot.records.length, 1),
                    cursor: null,
                  },
                  unionPrepared
                ).canonical_json
              ) as {
                contractVersion: unknown;
                items: Record<string, unknown>[];
                completeness: unknown;
              };
              const composed = composeConversationUnionPage(
                projected.items,
                chat.sessions,
                window.limit,
                loaded.after
              );
              if (composed === null) return failed(503, "unavailable");
              counter.recordDomainRead("served");
              let nextCursor: string | null = null;
              if (composed.hasMore) {
                const last = composed.items[composed.items.length - 1];
                if (
                  last === undefined ||
                  typeof last.id !== "string" ||
                  typeof last.updatedAt !== "number"
                ) {
                  throw new TypeError("conversation_cursor_position_missing");
                }
                nextCursor = unionPrepared.ports.issueCursor(
                  last.id,
                  unionPrepared.ports.bindingsFor(
                    unionPrepared.ports.resolveAttempt()
                  )
                );
                const kind = chat.sessions.some(
                  (session) => session.id === last.id
                )
                  ? "chat"
                  : "listen";
                const lastUpdatedAt =
                  kind === "listen"
                    ? loaded.snapshot.records.find(
                        (row) => row.record.id === last.id
                      )?.record.updated_at
                    : new Date(last.updatedAt).toISOString();
                if (lastUpdatedAt === undefined)
                  throw new TypeError("conversation_cursor_position_missing");
                await storage.saveUnion(
                  cursorHashOf(nextCursor),
                  digest,
                  metadata.revision,
                  chat.snapshotSequence,
                  lastUpdatedAt,
                  last.updatedAt,
                  last.id,
                  kind,
                  now + 900
                );
              }
              return new Response(
                JSON.stringify({
                  contractVersion: projected.contractVersion,
                  items: composed.items,
                  window: {
                    status: composed.hasMore ? "more" : "complete",
                    complete: !composed.hasMore,
                    hasMore: composed.hasMore,
                    nextCursor,
                  },
                  completeness: projected.completeness,
                  absence:
                    composed.items.length === 0
                      ? { kind: "query_gap" }
                      : null,
                }),
                {
                  status: 200,
                  headers: {
                    "cache-control": "no-store",
                    "content-type": "application/json",
                  },
                }
              );
            }
          );
        }
        return withAuthorizedConversationRead(
          runtime.pool,
          authority,
          request.signal,
          async (metadata, now, storage) => {
            let snapshot = metadata;
            const prepared = preparedRead(
              authority,
              snapshot,
              now,
              "conversations-read-cursor-v1"
            );
            const bindings = prepared.ports.bindingsFor(
              prepared.ports.resolveAttempt()
            );
            const digest = createHash("sha256")
              .update(JSON.stringify(bindings))
              .digest("hex");
            try {
              if (window.cursor !== null)
                prepared.ports.verifyCursor(window.cursor, bindings);
              snapshot = await storage.load(
                window.readLimit,
                window.cursor === null ? null : cursorHashOf(window.cursor),
                digest,
                metadata.revision
              );
            } catch (error) {
              if (
                error !== null &&
                typeof error === "object" &&
                "code" in error &&
                error.code === "invalid_cursor"
              )
                return failed(400, "bad_request");
              throw error;
            }
            const sequenced = preparedRead(
              authority,
              snapshot,
              now,
              "conversations-read-cursor-v1"
            );
            const app = new Hono();
            registerConversationReadRoutes(app, {
              store: {
                listRecords(account: string) {
                  if (account !== authority.account_id)
                    throw new TypeError("conversation_owner_mismatch");
                  return snapshot.records.map((row) => row.record);
                },
                listOrderedRecords(account: string) {
                  if (account !== authority.account_id)
                    throw new TypeError("conversation_owner_mismatch");
                  return snapshot.records;
                },
                readStateRevision(account: string) {
                  if (account !== authority.account_id)
                    throw new TypeError("conversation_owner_mismatch");
                  return snapshot.revision;
                },
              },
              counter,
              prepareRead: () => sequenced,
              resolvePrincipal: (submitted) =>
                submitted === token ? { uid: authority.account_id } : null,
            });
            const response = await app.fetch(request);
            if (response.status === 200 && !window.legacy) {
              const page = (await response.clone().json()) as {
                items: { id: string }[];
                window: { nextCursor: string | null };
              };
              if (page.window.nextCursor !== null) {
                const last = snapshot.records.find(
                  (row) =>
                    row.record.id === page.items[page.items.length - 1]?.id
                );
                if (last === undefined)
                  throw new TypeError("conversation_cursor_position_missing");
                await storage.save(
                  cursorHashOf(page.window.nextCursor),
                  digest,
                  metadata.revision,
                  last.sequence,
                  now + 900
                );
              }
            }
            return response;
          }
        );
      } catch {
        return failed(503, "unavailable");
      }
    },
  });
}
