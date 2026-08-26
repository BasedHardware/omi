import { Hono } from "hono";
import { SYNTHESIZED_READ_CONTRACT_VERSION } from "@omi-core/ratified-contracts/projections/synthesized";

import { AccountBackend } from "./account";
import { readHistory, readSettings } from "./chat";
import {
  conversationPage,
  paginateConversations,
  readConversations,
  toLegacyConversation,
} from "./conversations";
import {
  gatewayConfig,
  gatewayModeEnabled,
  type GatewaySecretEnv,
} from "./openrouter";
import {
  configurationNotReadyEvent,
  generationAdmittedEvent,
  observabilityConfigured,
  parseObservabilitySinkMode,
  requestCompletedEvent,
  requestFailedEvent,
  type ObservabilityEnv,
} from "./observability";
import {
  ATTACHMENT_CAPABILITIES,
  completeAttachment,
  consumeAttachmentIngest,
  makeR2UploadUrlSigner,
  parseAttachmentStageRequest,
  parseSignedUploadConfig,
  resolveAttachmentsForAdmit,
  stageAttachment,
  type AttachmentIngestMessage,
} from "./attachments";
import { parseTaskLimit, readTasks } from "./tasks";
import { backendError, isChatCreate, json } from "./wire";

type WorkerEnv = Omit<
  Env,
  "DB" | "OBSERVABILITY_SINK_MODE" | "ATTACHMENTS" | "ATTACHMENT_INGEST"
> &
  GatewaySecretEnv &
  ObservabilityEnv & {
    API_TOKEN: string;
    DB?: D1Database;
    ATTACHMENTS?: R2Bucket;
    ATTACHMENT_INGEST?: Queue<AttachmentIngestMessage>;
    R2_ACCOUNT_ID?: string;
    R2_BUCKET_NAME?: string;
    R2_ACCESS_KEY_ID?: string;
    R2_SECRET_ACCESS_KEY?: string;
    R2_SIGNED_URL_TTL_SECONDS?: string | number;
  };
type Variables = { accountId: string; requestId: string };

type ObservableContext = {
  req: { method: string; routePath: string };
  res: { status: number };
  set(key: "requestId", value: string): void;
  get(key: "requestId"): string | undefined;
  header(name: string, value: string): void;
};

const app = new Hono<{ Bindings: WorkerEnv; Variables: Variables }>({
  strict: true,
});

// Emit one small, schema-stable JSON event for every request. Cloudflare
// Workers Observability can retain it natively and Better Stack can ingest the
// same line without a Worker-specific SDK. The event intentionally carries no
// URL, query, authorization header, account identifier, request body, prompt,
// or completion content.
app.use("*", async (context, next) => {
  const requestId = crypto.randomUUID();
  const startedAt = Date.now();
  context.set("requestId", requestId);
  await next();
  context.header("x-omi-request-id", requestId);
  console.log(
    JSON.stringify(
      requestCompletedEvent({
        requestId,
        method: context.req.method,
        route: safeRoute(context),
        status: context.res.status,
        durationMs: Math.max(0, Date.now() - startedAt),
      })
    )
  );
});

app.get("/health", (context) =>
  json({ status: "ok", environment: context.env.ENVIRONMENT })
);
app.get("/ready", (context) =>
  configurationReady(context.env) &&
  parseObservabilitySinkMode(context.env.OBSERVABILITY_SINK_MODE) !== null
    ? json({
        status: "ready",
        environment: context.env.ENVIRONMENT,
        observability_sink_mode: context.env.OBSERVABILITY_SINK_MODE,
      })
    : backendError("service_unavailable", "retry", 503, true)
);

app.use("/v1/*", async (context, next) => {
  // Authorization is gated on the SAME readiness predicate `/ready` reports,
  // because a readiness signal is not an enforcement point: Cloudflare routes
  // request traffic regardless of what `/ready` returns, so a deployment whose
  // API_TOKEN secret is unset still serves `/v1/*`. That matters here and not
  // merely in principle: TextEncoder yields an EMPTY expectation for an absent
  // or empty secret, and an empty bearer credential ("Authorization: Bearer ")
  // encodes to the same empty value, so the constant-time comparison below
  // returns true and authenticates an anonymous caller. Wrangler does not fail
  // a deploy when a secret referenced solely in code is unset, so this is a
  // reachable configuration, not a hypothetical one. Refuse before comparing.
  if (!configurationReady(context.env)) {
    // Operator-visible, client-opaque: the caller still gets the ordinary
    // refusal, so a misconfigured deployment is not advertised over the wire.
    console.error(
      JSON.stringify(
        configurationNotReadyEvent({
          requestId: context.get("requestId") ?? "unavailable",
          route: safeRoute(context),
        })
      )
    );
    return backendError("unauthorized", "reauthenticate", 401);
  }
  const authorization = context.req.header("authorization");
  if (authorization === undefined || !authorization.startsWith("Bearer ")) {
    return backendError("unauthorized", "reauthenticate", 401);
  }
  const supplied = new TextEncoder().encode(
    authorization.slice("Bearer ".length)
  );
  const expected = new TextEncoder().encode(context.env.API_TOKEN);
  if (!constantTimeEqual(supplied, expected)) {
    return backendError("unauthorized", "reauthenticate", 401);
  }
  const clientId = context.req.header("x-omi-client-id");
  if (clientId === undefined || clientId.length === 0) {
    return backendError("bad_request", "edit_request", 400);
  }
  context.set("accountId", context.env.STAGING_ACCOUNT_ID);
  await next();
});

app.get("/v1/settings", async (context) => {
  const db = context.env.DB;
  if (db === undefined)
    return backendError("service_unavailable", "retry", 503, true);
  return json(
    await readSettings(
      db,
      context.get("accountId"),
      {
        displayName: context.env.STAGING_DISPLAY_NAME,
        email: context.env.STAGING_EMAIL,
      },
      context.env.STAGING_PLAN_LABEL,
      context.env.STAGING_CHAT_LIMIT
    )
  );
});

app.get("/v1/chat-messages", async (context) => {
  const query = new URL(context.req.url).searchParams;
  if (
    [...query.keys()].some((key) => key !== "limit" && key !== "olderCursor") ||
    query.getAll("limit").length > 1 ||
    query.getAll("olderCursor").length > 1
  ) {
    return backendError("bad_request", "edit_request", 400);
  }
  const limit = parseLimit(query.get("limit") ?? undefined);
  const olderCursor = query.get("olderCursor") ?? undefined;
  if (limit === null || olderCursor === "")
    return backendError("bad_request", "edit_request", 400);
  const db = context.env.DB;
  if (db === undefined)
    return backendError("service_unavailable", "retry", 503, true);
  const history = await readHistory(
    db,
    context.get("accountId"),
    limit,
    olderCursor
  );
  return history === "invalid_cursor"
    ? backendError("bad_request", "edit_request", 400)
    : json(history);
});

app.post("/v1/chat-messages", async (context) => {
  const parsed = await readBoundedJson(context.req.raw, 65_536);
  if (parsed.kind === "too_large")
    return backendError("attachment_too_large", "edit_request", 413);
  if (parsed.kind === "invalid")
    return backendError("bad_request", "edit_request", 400);
  const body = parsed.value;
  if (!isChatCreate(body))
    return backendError("validation", "edit_request", 422);
  const db = context.env.DB;
  if (db === undefined)
    return backendError("service_unavailable", "retry", 503, true);
  const resolved = await resolveAttachmentsForAdmit(
    db,
    context.get("accountId"),
    body.attachmentIds,
    body.id
  );
  if (resolved.kind === "rejected")
    return backendError("attachment_rejected", "edit_request", 422);
  const stub = account(context);
  const admission = await stub.admit(
    context.get("accountId"),
    body,
    context.env.STAGING_CHAT_LIMIT
  );
  if (admission === "conflict") {
    return backendError("client_message_id_conflict", "edit_request", 409);
  }
  if (admission === "entitlement") {
    return backendError("entitlement", "upgrade", 402);
  }
  if (admission === "attachment_rejected") {
    return backendError("attachment_rejected", "edit_request", 422);
  }
  console.log(
    JSON.stringify(
      generationAdmittedEvent({
        requestId: context.get("requestId") ?? "unavailable",
        generationId: admission.generation.id,
      })
    )
  );
  return json(
    { message: admission.message, generation: admission.generation },
    admission.created ? 201 : 200
  );
});

app.get("/v1/chat-generations/:id/events", async (context) => {
  const generationId = context.req.param("id");
  const target = new URL("https://account.internal/events");
  target.searchParams.set("generationId", generationId);
  const response = await account(context).fetch(
    new Request(target, { headers: context.req.raw.headers })
  );
  return response.status === 404
    ? backendError("not_found", "refresh_history", 404)
    : response;
});

app.delete("/v1/chat-generations/:id", async (context) => {
  const cancellation = await account(context).cancel(
    context.get("accountId"),
    context.req.param("id")
  );
  if (cancellation === "not_found")
    return backendError("not_found", "refresh_history", 404);
  return cancellation === "terminal"
    ? new Response(null, {
        status: 204,
        headers: { "cache-control": "no-store" },
      })
    : json({ cancellation: { state: "accepted" } }, 202);
});

app.post("/v1/chat-attachments", async (context) => {
  const r2 = context.env.ATTACHMENTS;
  if (r2 === undefined)
    return backendError("service_unavailable", "retry", 503, true);
  const parsed = await readBoundedJson(context.req.raw, 65_536);
  if (parsed.kind === "too_large")
    return backendError("attachment_too_large", "edit_request", 413);
  if (parsed.kind === "invalid")
    return backendError("bad_request", "edit_request", 400);
  const request = parseAttachmentStageRequest(parsed.value);
  if (request === null)
    return backendError("attachment_rejected", "edit_request", 422);
  const db = context.env.DB;
  if (db === undefined)
    return backendError("service_unavailable", "retry", 503, true);
  const signedConfig = parseSignedUploadConfig(context.env);
  if (signedConfig === null)
    return backendError("service_unavailable", "retry", 503, true);
  const signer = makeR2UploadUrlSigner(signedConfig);
  const result = await stageAttachment(
    db,
    context.get("accountId"),
    request,
    ATTACHMENT_CAPABILITIES,
    "attachments",
    signer
  );
  if (result.kind === "conflict")
    return backendError("attachment_rejected", "edit_request", 409);
  return json(result.response, result.created ? 201 : 200);
});

app.post("/v1/chat-attachments/:id/complete", async (context) => {
  const r2 = context.env.ATTACHMENTS;
  const ingest = context.env.ATTACHMENT_INGEST;
  const db = context.env.DB;
  if (r2 === undefined || ingest === undefined || db === undefined)
    return backendError("service_unavailable", "retry", 503, true);
  const attachmentId = context.req.param("id");
  if (
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(
      attachmentId
    )
  )
    return backendError("bad_request", "edit_request", 400);
  const outcome = await completeAttachment(
    db,
    r2,
    ingest,
    context.get("accountId"),
    attachmentId,
    Date.now()
  );
  switch (outcome.kind) {
    case "accepted":
      return json({ attachment: outcome.attachment }, 202);
    case "queued":
      return json({ attachment: outcome.attachment }, 202);
    case "ingested":
      return json({ attachment: outcome.attachment }, 200);
    case "not_found":
      return backendError("not_found", "refresh_history", 404);
    case "expired":
      return backendError("attachment_expired", "edit_request", 410);
    case "absent":
      return backendError("attachment_not_uploaded", "retry", 422, true);
    case "mismatch":
      return backendError("attachment_metadata_mismatch", "edit_request", 422);
    case "conflict":
      return backendError("attachment_rejected", "edit_request", 409);
  }
});

app.get("/v1/conversations", async (context) => {
  const query = new URL(context.req.url).searchParams;
  const keys = [...query.keys()];
  const hasOffset = query.has("offset");
  if (hasOffset) {
    if (
      keys.some((key) => key !== "limit" && key !== "offset") ||
      query.getAll("limit").length > 1 ||
      query.getAll("offset").length > 1
    ) {
      return backendError("bad_request", "edit_request", 400);
    }
    const limit = parseLimit(query.get("limit") ?? undefined);
    const offset = parseOffset(query.get("offset") ?? undefined);
    if (limit === null || offset === null)
      return backendError("bad_request", "edit_request", 400);
    const db = context.env.DB;
    if (db === undefined) return json([]);
    const items = await readConversations(db, context.get("accountId"));
    return json(
      items
        .slice(offset, offset + limit)
        .map((item) => toLegacyConversation(item))
    );
  }
  if (
    keys.some((key) => key !== "limit" && key !== "cursor") ||
    query.getAll("limit").length > 1 ||
    query.getAll("cursor").length > 1
  ) {
    return backendError("bad_request", "edit_request", 400);
  }
  const limit = parseLimit(query.get("limit") ?? undefined);
  const cursor = query.get("cursor") ?? undefined;
  if (limit === null || cursor === "")
    return backendError("bad_request", "edit_request", 400);
  const db = context.env.DB;
  if (db === undefined) return json(conversationPage([], false, null));
  const page = paginateConversations(
    await readConversations(db, context.get("accountId")),
    limit,
    cursor
  );
  return page === "invalid_cursor"
    ? backendError("bad_request", "edit_request", 400)
    : json(page);
});
app.get("/v1/memories", (context) => {
  const query = new URL(context.req.url).searchParams;
  if (
    [...query.keys()].some((key) => key !== "limit" && key !== "cursor") ||
    query.getAll("limit").length > 1 ||
    query.getAll("cursor").length > 1
  ) {
    return backendError("bad_request", "edit_request", 400);
  }
  const limit = parseTaskLimit(query.get("limit"));
  const cursor = query.get("cursor") ?? undefined;
  if (cursor === "") return backendError("bad_request", "edit_request", 400);
  void limit;
  return json(emptyPage("recall-completeness-v1"));
});
app.get("/v1/tasks", async (context) => {
  const query = new URL(context.req.url).searchParams;
  if (
    [...query.keys()].some((key) => key !== "limit" && key !== "cursor") ||
    query.getAll("limit").length > 1 ||
    query.getAll("cursor").length > 1
  ) {
    return backendError("bad_request", "edit_request", 400);
  }
  const db = context.env.DB;
  if (db === undefined) return json(emptyPage("tasks-completeness-v1"));
  const limit = parseTaskLimit(query.get("limit"));
  const cursor = query.get("cursor") ?? undefined;
  return json(await readTasks(db, context.get("accountId"), limit, cursor));
});

app.notFound(() => backendError("not_found", "edit_request", 404));
app.onError((error, context) => {
  console.error(
    JSON.stringify(
      requestFailedEvent({
        requestId: context.get("requestId") ?? "unavailable",
        name: error.name,
        route: safeRoute(context),
      })
    )
  );
  return backendError("internal_server_error", "retry", 500, true);
});

const handler = {
  fetch: app.fetch,
  queue: async (batch, env) => {
    const db = env.DB;
    const r2 = env.ATTACHMENTS;
    if (db === undefined || r2 === undefined) {
      batch.retryAll();
      return;
    }
    await Promise.all(
      batch.messages.map(async (message) => {
        try {
          await consumeAttachmentIngest(
            db,
            r2,
            message.body as AttachmentIngestMessage,
            Date.now()
          );
          message.ack();
        } catch (error) {
          console.error(
            JSON.stringify({
              event: "attachment_ingest_failed",
              name: error instanceof Error ? error.name : "unknown",
            })
          );
          message.retry();
        }
      })
    );
  },
} satisfies ExportedHandler<WorkerEnv, AttachmentIngestMessage>;

export { AccountBackend };
export {
  createVectorizeRetrievalBoundary,
  type CanonicalMemoryStore,
  type RetrievalBoundary,
  type RetrievalEnv,
} from "./retrieval";
export default handler;

function safeRoute(context: Pick<ObservableContext, "req">): string {
  const route = context.req.routePath;
  return route.startsWith("/") && route.length <= 200 ? route : "unmatched";
}

function account(context: { env: WorkerEnv; get(key: "accountId"): string }) {
  return context.env.ACCOUNTS.getByName(context.get("accountId"));
}

function constantTimeEqual(
  supplied: Uint8Array,
  expected: Uint8Array
): boolean {
  const length = Math.max(supplied.byteLength, expected.byteLength);
  let difference = supplied.byteLength ^ expected.byteLength;
  for (let index = 0; index < length; index += 1) {
    difference |= (supplied[index] ?? 0) ^ (expected[index] ?? 0);
  }
  return difference === 0;
}

function configurationReady(env: WorkerEnv): boolean {
  const base =
    typeof env.API_TOKEN === "string" &&
    env.API_TOKEN.length > 0 &&
    typeof env.STAGING_ACCOUNT_ID === "string" &&
    env.STAGING_ACCOUNT_ID.length > 0 &&
    typeof env.AI_MODEL === "string" &&
    env.AI_MODEL.length > 0 &&
    Number.isSafeInteger(env.STAGING_CHAT_LIMIT) &&
    env.STAGING_CHAT_LIMIT >= 0 &&
    env.ACCOUNTS !== undefined &&
    env.AI !== undefined &&
    env.DB !== undefined &&
    observabilityConfigured(env);
  if (!base) return false;
  if (gatewayModeEnabled(env)) return gatewayConfig(env) !== null;
  return true;
}

function parseLimit(value: string | undefined): number | null {
  if (value === undefined) return 50;
  if (!/^(?:[1-9]|[1-9][0-9]|100)$/.test(value)) return null;
  return Number(value);
}

function parseOffset(value: string | undefined): number | null {
  if (value === undefined) return 0;
  if (!/^(?:0|[1-9][0-9]{0,8})$/.test(value)) return null;
  return Number(value);
}

async function readBoundedJson(
  request: Request,
  maxBytes: number
): Promise<
  { kind: "ok"; value: unknown } | { kind: "invalid" } | { kind: "too_large" }
> {
  const declaredLength = request.headers.get("content-length");
  if (
    declaredLength !== null &&
    (!/^\d+$/.test(declaredLength) || Number(declaredLength) > maxBytes)
  ) {
    return { kind: "too_large" };
  }
  if (request.body === null) return { kind: "invalid" };
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let length = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    length += value.byteLength;
    if (length > maxBytes) {
      await reader.cancel();
      return { kind: "too_large" };
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  try {
    return {
      kind: "ok",
      value: JSON.parse(
        new TextDecoder("utf-8", { fatal: true }).decode(bytes)
      ) as unknown,
    };
  } catch {
    return { kind: "invalid" };
  }
}

function emptyPage(
  completenessVersion: "recall-completeness-v1" | "tasks-completeness-v1"
) {
  return {
    contractVersion: SYNTHESIZED_READ_CONTRACT_VERSION,
    items: [],
    window: {
      status: "complete",
      complete: true,
      hasMore: false,
      nextCursor: null,
    },
    completeness: {
      version: completenessVersion,
      status: "complete",
      reasons: [],
      frontiers:
        completenessVersion === "tasks-completeness-v1"
          ? {
              declaredFrontier: "frontier-v1:tasks-declared",
              newestAppliedFrontier: "frontier-v1:tasks-declared",
              missingAppliedFrontierReason: null,
            }
          : {
              declaredFrontier: "frontier-v1:declared",
              newestSearchedAcceptedFrontier: null,
              missingAcceptedFrontierReason: "no_accepted_work",
              newestSearchedStmFrontier: null,
              missingStmFrontierReason: "no_eligible_stm",
            },
    },
    absence: { kind: "query_gap" },
  };
}
