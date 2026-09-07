import { createHash } from "node:crypto";
import { Hono } from "hono";
import { prepareConversationsRead } from "../../apps/service/composition/conversations-read";
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
export function createPostgresFirebaseConversationReadRuntime(
  options: PostgresFirebaseConversationReadOptions
) {
  const runtime = createPostgresFirebaseAuthorizationRuntime(
    options.authorization,
    "conversations.read"
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
        return await withAuthorizedConversationRead(
          runtime.pool,
          authority,
          request.signal,
          async (metadata, now, storage) => {
            let snapshot = metadata;
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
            const prepared = prepareConversationsRead({
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
            const readAuthority = prepared.ports.resolveAttempt();
            const bindings = prepared.ports.bindingsFor(readAuthority);
            const digest = createHash("sha256")
              .update(JSON.stringify(bindings))
              .digest("hex");
            const cursorHash = (cursor: string) =>
              createHash("sha256").update(cursor).digest("hex");
            try {
              if (window.cursor !== null)
                prepared.ports.verifyCursor(window.cursor, bindings);
              snapshot = await storage.load(
                window.readLimit,
                window.cursor === null ? null : cursorHash(window.cursor),
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
            const app = new Hono();
            registerConversationReadRoutes(app, {
              store,
              counter,
              prepareRead: () => prepared,
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
                  cursorHash(page.window.nextCursor),
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
