import { SYNTHESIZED_READ_CONTRACT_VERSION } from "@omi-core/ratified-contracts/projections/synthesized";

import { readHistory, readSettings, type Admission } from "./chat";
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
  type ObservabilityEnv,
} from "./observability";
import {
  ATTACHMENT_CAPABILITIES,
  completeAttachment,
  makeR2UploadUrlSigner,
  parseAttachmentStageRequest,
  parseSignedUploadConfig,
  resolveAttachmentsForAdmit,
  stageAttachment,
  type AttachmentIngestMessage,
  type SignedUploadEnv,
} from "./attachments";
import {
  appendDeviceSessionAudio,
  completeDeviceSession,
  listDeviceSessions,
  openDeviceSession,
  parseDeviceSessionAudio,
  parseDeviceSessionCreate,
} from "./device-sessions";
import {
  createVectorizeRetrievalBoundary,
  noCanonicalMemoryStore,
  type RetrievalEnv,
} from "./retrieval";
import { parseTaskLimit, readTasks } from "./tasks";
import {
  backendError,
  isChatCreate,
  isClientId,
  json,
  type ChatCreate,
} from "./wire";

export type AccountPort = {
  admit(
    accountId: string,
    input: ChatCreate,
    chatLimit: number
  ): Promise<Admission | "conflict" | "entitlement" | "attachment_rejected">;
  cancel(
    accountId: string,
    generationId: string
  ): Promise<"not_found" | "accepted" | "terminal">;
  fetch(request: Request): Promise<Response>;
};

export type AccountLocator = {
  getByName(name: string): AccountPort;
};

export type CoreEnv = SignedUploadEnv &
  GatewaySecretEnv &
  ObservabilityEnv & {
    ENVIRONMENT: string;
    API_TOKEN: string;
    STAGING_ACCOUNT_ID: string;
    STAGING_DISPLAY_NAME: string;
    STAGING_EMAIL: string;
    STAGING_PLAN_LABEL: string;
    STAGING_CHAT_LIMIT: number;
    AI_MODEL: string;
    OPENROUTER_GATEWAY_ENABLED?: string;
    OPENROUTER_MODEL?: string;
    DB?: D1Database;
    ATTACHMENTS?: R2Bucket;
    ATTACHMENT_INGEST?: Queue<AttachmentIngestMessage>;
    ACCOUNTS?: AccountLocator;
    AI?: RetrievalEnv["AI"];
    VECTORIZE?: RetrievalEnv["VECTORIZE"];
  };

export type CoreContext = {
  env: CoreEnv;
  req: {
    method: string;
    url: string;
    raw: Request;
    routePath: string;
    header(name: string): string | undefined;
    param(name: string): string;
  };
  get(key: "accountId" | "requestId"): string;
  set(key: "accountId" | "requestId", value: string): void;
};

export type RouteMethod = "GET" | "POST" | "DELETE";

export type CoreRoute = {
  method: RouteMethod;
  path: string;
  handle: (context: CoreContext) => Response | Promise<Response>;
};

export function coreContext(input: {
  env: CoreEnv;
  request: Request;
  routePath: string;
  params: Record<string, string>;
  values: { accountId?: string; requestId: string };
}): CoreContext {
  const values = { ...input.values };
  return {
    env: input.env,
    req: {
      method: input.request.method,
      url: input.request.url,
      raw: input.request,
      routePath: input.routePath,
      header: (name) => input.request.headers.get(name) ?? undefined,
      param: (name) => input.params[name] ?? "",
    },
    get: (key) => values[key] ?? "",
    set: (key, value) => {
      values[key] = value;
    },
  };
}

export function safeRoute(routePath: string): string {
  return routePath.startsWith("/") && routePath.length <= 200
    ? routePath
    : "unmatched";
}

export function constantTimeEqual(
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

export function configurationReady(env: CoreEnv): boolean {
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

export function parseLimit(value: string | undefined): number | null {
  if (value === undefined) return 50;
  if (!/^(?:[1-9]|[1-9][0-9]|100)$/.test(value)) return null;
  return Number(value);
}

export function parseOffset(value: string | undefined): number | null {
  if (value === undefined) return 0;
  if (!/^(?:0|[1-9][0-9]{0,8})$/.test(value)) return null;
  return Number(value);
}

export async function readBoundedJson(
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

export function emptyPage(
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

export function authorizeV1(context: CoreContext): Response | null {
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
          requestId: context.get("requestId") || "unavailable",
          route: safeRoute(context.req.routePath),
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
  // Staging isolation by client id, not production multi-tenant auth.
  // After Bearer auth, each validated x-omi-client-id is its own data
  // partition for chat, tasks, attachments, conversations, and device
  // sessions. Settings display name/email/plan stay staging labels.
  if (clientId === undefined || !isClientId(clientId)) {
    return backendError("bad_request", "edit_request", 400);
  }
  context.set("accountId", clientId);
  return null;
}

export function handleHealth(context: CoreContext): Response {
  return json({ status: "ok", environment: context.env.ENVIRONMENT });
}

export function handleReady(context: CoreContext): Response {
  return configurationReady(context.env) &&
    parseObservabilitySinkMode(context.env.OBSERVABILITY_SINK_MODE) !== null
    ? json({
        status: "ready",
        environment: context.env.ENVIRONMENT,
        observability_sink_mode: context.env.OBSERVABILITY_SINK_MODE,
      })
    : backendError("service_unavailable", "retry", 503, true);
}

export async function handleSettings(context: CoreContext): Promise<Response> {
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
}

export async function handleChatHistory(
  context: CoreContext
): Promise<Response> {
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
}

export async function handleChatCreate(
  context: CoreContext
): Promise<Response> {
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
        requestId: context.get("requestId") || "unavailable",
        generationId: admission.generation.id,
      })
    )
  );
  return json(
    { message: admission.message, generation: admission.generation },
    admission.created ? 201 : 200
  );
}

export async function handleGenerationEvents(
  context: CoreContext
): Promise<Response> {
  const generationId = context.req.param("id");
  const target = new URL("https://account.internal/events");
  target.searchParams.set("generationId", generationId);
  const response = await account(context).fetch(
    new Request(target, { headers: context.req.raw.headers })
  );
  return response.status === 404
    ? backendError("not_found", "refresh_history", 404)
    : response;
}

export async function handleGenerationCancel(
  context: CoreContext
): Promise<Response> {
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
}

export async function handleAttachmentStage(
  context: CoreContext
): Promise<Response> {
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
}

export async function handleAttachmentComplete(
  context: CoreContext
): Promise<Response> {
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
}

export async function handleDeviceSessionOpen(
  context: CoreContext
): Promise<Response> {
  const r2 = context.env.ATTACHMENTS;
  const db = context.env.DB;
  if (r2 === undefined || db === undefined)
    return backendError("service_unavailable", "retry", 503, true);
  const parsed = await readBoundedJson(context.req.raw, 65_536);
  if (parsed.kind === "too_large")
    return backendError("attachment_too_large", "edit_request", 413);
  if (parsed.kind === "invalid")
    return backendError("bad_request", "edit_request", 400);
  const request = parseDeviceSessionCreate(parsed.value);
  if (request === null) return backendError("validation", "edit_request", 422);
  return json(
    {
      session: await openDeviceSession(
        db,
        context.get("accountId"),
        request,
        Date.now()
      ),
    },
    201
  );
}

export async function handleDeviceSessionAudio(
  context: CoreContext
): Promise<Response> {
  const r2 = context.env.ATTACHMENTS;
  const db = context.env.DB;
  if (r2 === undefined || db === undefined)
    return backendError("service_unavailable", "retry", 503, true);
  const parsed = await readBoundedJson(context.req.raw, 1_572_864);
  if (parsed.kind === "too_large")
    return backendError("attachment_too_large", "edit_request", 413);
  if (parsed.kind === "invalid")
    return backendError("bad_request", "edit_request", 400);
  const request = parseDeviceSessionAudio(parsed.value);
  if (request === null) return backendError("validation", "edit_request", 422);
  const outcome = await appendDeviceSessionAudio(
    db,
    r2,
    context.get("accountId"),
    context.req.param("id"),
    request.bytes,
    Date.now()
  );
  switch (outcome.kind) {
    case "ok":
      return json({ session: outcome.session });
    case "not_found":
      return backendError("not_found", "refresh_history", 404);
    case "conflict":
      return backendError("conflict", "edit_request", 409);
    case "too_large":
      return backendError("attachment_too_large", "edit_request", 413);
  }
}

export async function handleDeviceSessionComplete(
  context: CoreContext
): Promise<Response> {
  const r2 = context.env.ATTACHMENTS;
  const db = context.env.DB;
  if (r2 === undefined || db === undefined)
    return backendError("service_unavailable", "retry", 503, true);
  const outcome = await completeDeviceSession(
    db,
    context.get("accountId"),
    context.req.param("id"),
    Date.now()
  );
  return outcome.kind === "not_found"
    ? backendError("not_found", "refresh_history", 404)
    : json({ session: outcome.session });
}

export async function handleDeviceSessionList(
  context: CoreContext
): Promise<Response> {
  const r2 = context.env.ATTACHMENTS;
  const db = context.env.DB;
  if (r2 === undefined || db === undefined)
    return backendError("service_unavailable", "retry", 503, true);
  return json({
    sessions: await listDeviceSessions(db, context.get("accountId")),
  });
}

export async function handleConversations(
  context: CoreContext
): Promise<Response> {
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
}

export async function handleMemories(context: CoreContext): Promise<Response> {
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
  if (context.env.AI !== undefined) {
    const recalled = await createVectorizeRetrievalBoundary(
      context.env.VECTORIZE === undefined
        ? { AI: context.env.AI }
        : { AI: context.env.AI, VECTORIZE: context.env.VECTORIZE },
      noCanonicalMemoryStore
    ).query({
      accountId: context.get("accountId"),
      queryText: "",
      topK: limit,
    });
    // No D1 memory table: ids cannot be revalidated, so hits stay empty.
    void recalled;
  }
  return json(emptyPage("recall-completeness-v1"));
}

export async function handleTasks(context: CoreContext): Promise<Response> {
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
}

export const publicRoutes: readonly CoreRoute[] = [
  { method: "GET", path: "/health", handle: handleHealth },
  { method: "GET", path: "/ready", handle: handleReady },
];

export const v1Routes: readonly CoreRoute[] = [
  { method: "GET", path: "/v1/settings", handle: handleSettings },
  { method: "GET", path: "/v1/chat-messages", handle: handleChatHistory },
  { method: "POST", path: "/v1/chat-messages", handle: handleChatCreate },
  {
    method: "GET",
    path: "/v1/chat-generations/:id/events",
    handle: handleGenerationEvents,
  },
  {
    method: "DELETE",
    path: "/v1/chat-generations/:id",
    handle: handleGenerationCancel,
  },
  {
    method: "POST",
    path: "/v1/chat-attachments",
    handle: handleAttachmentStage,
  },
  {
    method: "POST",
    path: "/v1/chat-attachments/:id/complete",
    handle: handleAttachmentComplete,
  },
  {
    method: "POST",
    path: "/v1/device-sessions",
    handle: handleDeviceSessionOpen,
  },
  {
    method: "POST",
    path: "/v1/device-sessions/:id/audio",
    handle: handleDeviceSessionAudio,
  },
  {
    method: "POST",
    path: "/v1/device-sessions/:id/complete",
    handle: handleDeviceSessionComplete,
  },
  {
    method: "GET",
    path: "/v1/device-sessions",
    handle: handleDeviceSessionList,
  },
  { method: "GET", path: "/v1/conversations", handle: handleConversations },
  { method: "GET", path: "/v1/memories", handle: handleMemories },
  { method: "GET", path: "/v1/tasks", handle: handleTasks },
];

function account(context: CoreContext): AccountPort {
  const accounts = context.env.ACCOUNTS;
  if (accounts === undefined) {
    throw new Error("accounts");
  }
  return accounts.getByName(context.get("accountId"));
}
