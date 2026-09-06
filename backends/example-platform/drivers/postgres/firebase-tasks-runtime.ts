import { Hono } from "hono";
import { createHash } from "node:crypto";
import {
  WRITE_REFUSALS,
  parseWriteOpEnvelopeJson,
} from "@omi-core/ratified-contracts/write/ops";
import {
  prepareTasksRead,
  resolveTasksWriteRecordId,
} from "../../apps/service/composition/tasks-read";
import { registerTasksReadRoutes } from "../../apps/service/routes/tasks-read";
import { registerTasksOpsRoutes } from "../../apps/service/routes/tasks-ops";
import { createWriteFenceCounter } from "../../apps/service/control/fence-counter";
import { createWriteOpsCounter } from "../../apps/service/observability/write-ops-counter";
import { createServedCounter } from "../../apps/service/observability/served-count";
import type { PreservedEnvelope } from "../../apps/service/stores/straggler-table";
import type { McpCursorSigningKeyset } from "../../apps/mcp/cursor";

import {
  createPostgresFirebaseAuthorizationRuntime,
  type PostgresFirebaseAuthorizationRuntimeOptions,
} from "./firebase-authorized-runtime-support";
import { withAuthorizedTasks } from "./tasks-repository";

export interface PostgresFirebaseTasksOptions {
  readonly authorization: PostgresFirebaseAuthorizationRuntimeOptions;
  readonly codecRootSecret: Uint8Array;
  readonly cursorSigningKeyset: McpCursorSigningKeyset;
}
const fixed = (body: string, status: number) =>
  new Response(body, {
    status,
    headers: {
      "content-type": "application/json",
      "cache-control": "no-store",
    },
  });
export function createPostgresFirebaseTasksRuntime(
  options: PostgresFirebaseTasksOptions
) {
  const read = createPostgresFirebaseAuthorizationRuntime(
    options.authorization,
    "tasks.read"
  );
  const write = createPostgresFirebaseAuthorizationRuntime(
    options.authorization,
    "tasks.write"
  );
  const secret = new Uint8Array(options.codecRootSecret);
  const keys = {
    active_key_id: options.cursorSigningKeyset.active_key_id,
    keys: options.cursorSigningKeyset.keys.map((key) => ({
      key_id: key.key_id,
      secret: new Uint8Array(key.secret),
    })),
  };
  const counter = createServedCounter(),
    fenceCounter = createWriteFenceCounter(),
    writeCounter = createWriteOpsCounter();
  const executeRequest = async (request: Request): Promise<Response> => {
    const writing = request.method === "POST";
    const token =
      request.headers.get("authorization")?.match(/^Bearer (.+)$/)?.[1] ?? "";
    const runtime = writing ? write : read;
    try {
      const authorized = await runtime.authorizer.authorize(
        token,
        Math.floor(Date.now() / 1000)
      );
      if (!authorized.authorized) {
        if (authorized.outcome === "unavailable")
          return fixed('{"error":"unavailable"}', 503);
        if (writing) {
          const refusal = WRITE_REFUSALS[authorized.outcome];
          return fixed(refusal.body, refusal.status);
        }
        return fixed(
          authorized.outcome === "authentication"
            ? '{"error":"unauthorized"}'
            : '{"error":"forbidden"}',
          authorized.outcome === "authentication" ? 401 : 403
        );
      }
      if (request.signal.aborted) return fixed('{"error":"unavailable"}', 503);
      return await withAuthorizedTasks(
        runtime.pool,
        authorized.context,
        request.signal,
        async (transaction) => {
          const authority = authorized.context;
          const { store, unitOfWork } = transaction;
          const projection = Object.freeze({
            account_id: authority.account_id,
            control_revision: transaction.lockedControlRevision,
            account_generation: "new" as const,
            account_epoch: authority.account_epoch,
            lifecycle_state: authority.lifecycle_state,
            deletion_epoch: authority.deletion_epoch,
            activation: {
              activated_epoch: authority.account_epoch,
              at_control_revision: authority.destination_activation_revision,
            },
            conflict: null,
          });
          const control = {
            read(owner: string) {
              if (owner !== authority.account_id)
                throw Error("task_owner_mismatch");
              return projection;
            },
          };
          const prepared = prepareTasksRead({
            store,
            resolveAuthorization: () => ({
              owner_account_id: authority.account_id,
              app_id: authority.application_id,
              key_id: authority.credential_id,
            }),
            codecRootSecret: secret,
            cursorSigningKeyset: keys,
            readTimestampEpochSeconds: transaction.dbNowEpochSeconds,
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
          const app = new Hono();
          const principal = { uid: authority.account_id };
          const preserved: PreservedEnvelope[] = [];
          if (writing) {
            const raw = await request.clone().text();
            const envelope = parseWriteOpEnvelopeJson(raw);
            const priorRecordId = envelope
              ? await transaction.replayRecordId(envelope.write_id)
              : null;
            registerTasksOpsRoutes(app, {
              resolvePrincipal: (submitted) =>
                submitted === token ? principal : null,
              unitOfWork,
              stragglers: {
                preserve(owner, row) {
                  if (owner !== authority.account_id)
                    throw Error("task_owner_mismatch");
                  preserved.push(row);
                },
              },
              fence: {
                store: control,
                entitlement: { readEntitlement: () => null },
                counter: fenceCounter,
              },
              counter: writeCounter,
              now: () => transaction.dbNowEpochSeconds,
              resolveWriteRecordId: (_principal, id) => {
                const resolved = resolveTasksWriteRecordId(
                  prepared.ports,
                  authority.account_id,
                  id
                );
                if (resolved !== null) return resolved;
                if (priorRecordId !== null) return priorRecordId;
                return null;
              },
            });
          } else
            registerTasksReadRoutes(app, {
              resolvePrincipal: (submitted) =>
                submitted === token ? principal : null,
              prepareRead: () => prepared,
              fence: { store: control },
              counter,
            });
          const response = await app.fetch(request);
          await transaction.preserve(preserved);
          return response;
        }
      );
    } catch {
      return fixed('{"error":"unavailable"}', 503);
    }
  };
  return Object.freeze({ executeRequest });
}
