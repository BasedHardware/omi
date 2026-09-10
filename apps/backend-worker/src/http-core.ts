import { readHistory, readSettings, type Admission } from "./chat";
import {
  conversationPage,
  MAIN_CONVERSATION_ID,
  paginateConversations,
  readConversations,
  toLegacyConversation,
} from "./conversations";
import {
  gatewayConfig,
  gatewayModeEnabled,
  type GatewayEnv,
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
  appendDeviceSessionAudioBatch,
  completeDeviceSession,
  DEVICE_SESSION_ID,
  listDeviceSessions,
  openDeviceSession,
  parseDeviceSessionAudioBatch,
  parseDeviceSessionCreate,
  readDeviceSession,
} from "./device-sessions";
import { type RetrievalEnv } from "./retrieval";
import { type CanonicalService } from "./canonical-service";
import { readCanonicalMemoryPage } from "./memory-service";
import { requestCanonicalTasks } from "./canonical-tasks";
import {
  readDeviceTranscription,
  processDeviceTranscriptions,
  projectDeviceTranscription,
  type DeviceTranscriptionProjection,
  type TranscriptionAI,
} from "./device-transcriptions";
import { parseTaskLimit, readTasks } from "./tasks";
import {
  backendError,
  isClientId,
  json,
  parseChatCreate,
  type ChatCreate,
  withTimeout,
} from "./wire";

export type AccountPort = {
  admit(
    accountId: string,
    input: ChatCreate,
    chatLimit: number
  ): Promise<
    | Admission
    | "conflict"
    | "entitlement"
    | "attachment_rejected"
    | "attachment_not_found"
    | "attachment_invalid"
  >;
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
  GatewayEnv &
  ObservabilityEnv & {
    ENVIRONMENT: string;
    API_TOKEN: string;
    FIREBASE_API_KEY?: string;
    STAGING_ACCOUNT_ID: string;
    STAGING_DISPLAY_NAME: string;
    STAGING_EMAIL: string;
    STAGING_PLAN_LABEL: string;
    STAGING_CHAT_LIMIT: number;
    AI_MODEL: string;
    DB?: D1Database;
    ATTACHMENTS?: R2Bucket;
    ATTACHMENT_INGEST?: Queue<AttachmentIngestMessage>;
    ACCOUNTS?: AccountLocator;
    AI?: RetrievalEnv["AI"] | { run: (...args: never[]) => Promise<unknown> };
    VECTORIZE?: RetrievalEnv["VECTORIZE"];
    CANONICAL_SERVICE?: CanonicalService;
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
  return credentialsReady(env) && env.DB !== undefined;
}

function credentialsReady(env: CoreEnv): boolean {
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
    observabilityConfigured(env);
  if (!base) return false;
  if (gatewayModeEnabled(env)) return gatewayConfig(env) !== null;
  return true;
}

export function parseLimit(
  value: string | undefined,
  omitted = 50
): number | null {
  if (value === undefined) return omitted;
  if (!/^(?:[1-9]|[1-9][0-9]|100)$/.test(value)) return null;
  return Number(value);
}

export function parseEnvelopeLimit(
  value: string | undefined,
  omitted = 25
): number | null {
  if (value === undefined) return omitted;
  if (!/^[0-9]{1,3}$/.test(value)) return null;
  const limit = Number(value);
  if (!Number.isSafeInteger(limit) || limit < 1 || limit > 100) return null;
  return limit;
}

export function parseOffset(value: string | undefined): number {
  if (value === undefined) return 0;
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 0) return 0;
  return parsed;
}

function parseOffsetModeLimit(value: string | undefined): number {
  if (value === undefined) return 50;
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 0) return 50;
  return Math.min(parsed, 100);
}

function forwardedListQuery(
  query: URLSearchParams
): URLSearchParams | "duplicate" {
  if (query.getAll("limit").length > 1 || query.getAll("cursor").length > 1) {
    return "duplicate";
  }
  const forwarded = new URLSearchParams();
  const limit = query.get("limit");
  const cursor = query.get("cursor");
  if (limit !== null) forwarded.set("limit", limit);
  if (cursor !== null) forwarded.set("cursor", cursor);
  return forwarded;
}

export async function readBoundedJson(
  request: Request,
  maxBytes: number
): Promise<
  | { kind: "ok"; value: unknown; raw: string }
  | { kind: "invalid" }
  | { kind: "too_large" }
> {
  return readBoundedJsonStream(
    request.body,
    request.headers.get("content-length"),
    maxBytes
  );
}

async function readBoundedJsonStream(
  body: ReadableStream<Uint8Array> | null,
  declaredLength: string | null,
  maxBytes: number
): Promise<
  | { kind: "ok"; value: unknown; raw: string }
  | { kind: "invalid" }
  | { kind: "too_large" }
> {
  if (
    declaredLength !== null &&
    (!/^\d+$/.test(declaredLength) || Number(declaredLength) > maxBytes)
  ) {
    return { kind: "too_large" };
  }
  if (body === null) return { kind: "invalid" };
  const reader = body.getReader();
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
    const raw = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    return { kind: "ok", value: JSON.parse(raw) as unknown, raw };
  } catch {
    return { kind: "invalid" };
  }
}

async function firebaseAccountId(
  token: string,
  apiKey: string
): Promise<string | "invalid" | "unavailable"> {
  if (token.length === 0 || token.length > 16_384 || apiKey.length === 0)
    return "invalid";
  try {
    return await withTimeout(5_000, async (signal) => {
      const response = await fetch(
        `https://identitytoolkit.googleapis.com/v1/accounts:lookup?key=${encodeURIComponent(
          apiKey
        )}`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ idToken: token }),
          redirect: "manual",
          signal,
        }
      );
      if (response.status !== 200) {
        const unavailable =
          response.status === 0 ||
          response.status === 429 ||
          response.status >= 500 ||
          (response.status >= 300 && response.status < 400);
        if (unavailable) {
          console.error(
            JSON.stringify({
              event: "firebase_lookup_failed",
              status: response.status,
            })
          );
        }
        return unavailable ? "unavailable" : "invalid";
      }
      const parsed = await readBoundedJsonStream(
        response.body,
        response.headers.get("content-length"),
        65_536
      );
      if (
        parsed.kind !== "ok" ||
        parsed.value === null ||
        typeof parsed.value !== "object"
      )
        return "unavailable";
      const users = (parsed.value as Record<string, unknown>)["users"];
      if (!Array.isArray(users) || users.length !== 1) return "invalid";
      const user = users[0];
      if (user === null || typeof user !== "object" || Array.isArray(user))
        return "invalid";
      const localId = (user as Record<string, unknown>)["localId"];
      return typeof localId === "string" && isClientId(localId)
        ? `firebase:${localId}`
        : "invalid";
    });
  } catch (error) {
    console.error(
      JSON.stringify({
        event: "firebase_lookup_failed",
        name: error instanceof Error ? error.name : "Unknown",
      })
    );
    return "unavailable";
  }
}

function firebaseUnavailableRetryAfter(
  method: string,
  url: string
): string | undefined {
  let pathname: string;
  try {
    pathname = new URL(url).pathname;
  } catch {
    return undefined;
  }
  if (method === "GET" && pathname === "/v1/chat-messages") return "60";
  if (method === "GET" && pathname === "/v1/settings") return "60";
  if (
    method === "GET" &&
    /^\/v1\/chat-generations\/[^/]+\/events$/.test(pathname)
  ) {
    return "60";
  }
  if (method === "GET" && pathname === "/v1/device-sessions/ownership") {
    return "1";
  }
  if (method === "GET" && pathname === "/v1/device-sessions") {
    return "1";
  }
  if (method === "GET" && /^\/v1\/device-sessions\/[^/]+$/.test(pathname)) {
    return "1";
  }
  if (
    method === "GET" &&
    /^\/v1\/device-sessions\/[^/]+\/transcript$/.test(pathname)
  ) {
    return "1";
  }
  if (method === "POST" && pathname === "/v1/device-sessions") {
    return "1";
  }
  if (
    method === "POST" &&
    /^\/v1\/device-sessions\/[^/]+\/audio$/.test(pathname)
  ) {
    return "1";
  }
  if (
    method === "POST" &&
    /^\/v1\/device-sessions\/[^/]+\/complete$/.test(pathname)
  ) {
    return "1";
  }
  if (
    method === "POST" &&
    /^\/v1\/device-sessions\/[^/]+\/transcribe$/.test(pathname)
  ) {
    return "1";
  }
  if (method === "POST" && pathname === "/v1/chat-attachments") {
    return "60";
  }
  if (
    method === "POST" &&
    /^\/v1\/chat-attachments\/[^/]+\/complete$/.test(pathname)
  ) {
    return "60";
  }
  return undefined;
}

type ResolvedV1Account =
  | { readonly kind: "account"; readonly accountId: string }
  | { readonly kind: "unauthorized" }
  | { readonly kind: "bad_request" }
  | { readonly kind: "unavailable"; readonly retryAfter: string | undefined };

async function resolveV1Account(
  context: CoreContext,
  requireDatabase = true
): Promise<ResolvedV1Account> {
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
  if (
    !(requireDatabase
      ? configurationReady(context.env)
      : credentialsReady(context.env))
  ) {
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
    return { kind: "unauthorized" };
  }
  const authorization = context.req.header("authorization");
  if (authorization === undefined || !authorization.startsWith("Bearer ")) {
    return { kind: "unauthorized" };
  }
  const supplied = new TextEncoder().encode(
    authorization.slice("Bearer ".length)
  );
  const expected = new TextEncoder().encode(context.env.API_TOKEN);
  if (constantTimeEqual(supplied, expected)) {
    const clientId = context.req.header("x-omi-client-id");
    // Staging isolation by client id, not production multi-tenant auth.
    // After Bearer auth, each validated x-omi-client-id is its own data
    // partition for chat, tasks, attachments, conversations, and device
    // sessions. Settings display name/email/plan stay staging labels.
    if (
      clientId === undefined ||
      !isClientId(clientId) ||
      clientId.startsWith("firebase:")
    ) {
      return { kind: "bad_request" };
    }
    return { kind: "account", accountId: clientId };
  }
  const firebaseApiKey = context.env.FIREBASE_API_KEY;
  if (typeof firebaseApiKey !== "string" || firebaseApiKey.length === 0)
    return { kind: "unauthorized" };
  const accountId = await firebaseAccountId(
    authorization.slice("Bearer ".length),
    firebaseApiKey
  );
  if (accountId === "unavailable") {
    return {
      kind: "unavailable",
      retryAfter: firebaseUnavailableRetryAfter(
        context.req.method,
        context.req.url
      ),
    };
  }
  if (accountId === "invalid") return { kind: "unauthorized" };
  return { kind: "account", accountId };
}

export function requiresV1Authorization(context: CoreContext): boolean {
  try {
    if (new URL(context.req.url).pathname === "/v1/settings") return false;
  } catch {
    return true;
  }
  return true;
}

export async function authorizeV1(
  context: CoreContext
): Promise<Response | null> {
  const resolved = await resolveV1Account(context);
  if (resolved.kind === "account") {
    context.set("accountId", resolved.accountId);
    return null;
  }
  if (resolved.kind === "unauthorized")
    return backendError("unauthorized", "reauthenticate", 401);
  if (resolved.kind === "bad_request")
    return backendError("bad_request", "edit_request", 400);
  return backendError(
    "service_unavailable",
    "retry",
    503,
    true,
    resolved.retryAfter === undefined
      ? undefined
      : { "retry-after": resolved.retryAfter }
  );
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
  const url = new URL(context.req.url);
  if ([...url.searchParams].length > 0) {
    return json({ error: "bad_request" }, 400);
  }
  const contentLength = context.req.header("content-length");
  if (contentLength !== undefined && contentLength !== "0") {
    return json({ error: "bad_request" }, 400);
  }
  if (context.req.header("transfer-encoding") !== undefined) {
    return json({ error: "bad_request" }, 400);
  }
  if (context.req.header("authorization") === undefined) {
    return json({ identity: null, entitlement: null });
  }
  const resolved = await resolveV1Account(context, false);
  if (resolved.kind === "unauthorized")
    return json({ error: "unauthorized" }, 401);
  if (resolved.kind === "bad_request")
    return json({ error: "bad_request" }, 400);
  if (resolved.kind === "unavailable")
    return backendError(
      "service_unavailable",
      "retry",
      503,
      true,
      resolved.retryAfter === undefined
        ? undefined
        : { "retry-after": resolved.retryAfter }
    );
  const db = context.env.DB;
  if (db === undefined)
    return backendError("service_unavailable", "retry", 503, true, {
      "retry-after": "60",
    });
  try {
    return json(
      await readSettings(db, resolved.accountId, context.env.STAGING_CHAT_LIMIT)
    );
  } catch {
    return backendError("service_unavailable", "retry", 503, true, {
      "retry-after": "60",
    });
  }
}

export async function handleChatHistory(
  context: CoreContext
): Promise<Response> {
  const query = new URL(context.req.url).searchParams;
  if (
    [...query.keys()].some(
      (key) =>
        key !== "limit" && key !== "olderCursor" && key !== "chatSessionId"
    ) ||
    query.getAll("limit").length > 1 ||
    query.getAll("olderCursor").length > 1 ||
    query.getAll("chatSessionId").length > 1
  ) {
    return backendError("bad_request", "edit_request", 400);
  }
  const limit = parseLimit(query.get("limit") ?? undefined);
  const olderCursor = query.get("olderCursor") ?? undefined;
  const requestedSession = query.get("chatSessionId") ?? undefined;
  if (
    limit === null ||
    olderCursor === "" ||
    requestedSession === "" ||
    (requestedSession !== undefined && requestedSession.length > 128)
  )
    return backendError("bad_request", "edit_request", 400);
  const chatSessionId =
    requestedSession === MAIN_CONVERSATION_ID.slice("chat:".length)
      ? undefined
      : requestedSession;
  const db = context.env.DB;
  if (db === undefined)
    return backendError("service_unavailable", "retry", 503, true, {
      "retry-after": "60",
    });
  try {
    const history = await readHistory(
      db,
      context.get("accountId"),
      limit,
      olderCursor,
      chatSessionId
    );
    if (history === "invalid_cursor")
      return backendError("bad_request", "refresh_history", 400);
    if (history === "cursor_expired")
      return backendError("cursor_expired", "refresh_history", 410);
    if (history === "unavailable")
      return backendError("service_unavailable", "retry", 503, true, {
        "retry-after": "60",
      });
    return json(history);
  } catch {
    return backendError("service_unavailable", "retry", 503, true, {
      "retry-after": "60",
    });
  }
}

export async function handleChatCreate(
  context: CoreContext
): Promise<Response> {
  const parsed = await readBoundedJson(context.req.raw, 65_536);
  if (parsed.kind === "too_large")
    return backendError("attachment_too_large", "edit_request", 413);
  if (parsed.kind === "invalid")
    return backendError("bad_request", "edit_request", 400);
  const body = parseChatCreate(parsed.value);
  if (body === null) return backendError("validation", "edit_request", 422);
  const db = context.env.DB;
  if (db === undefined)
    return backendError("service_unavailable", "retry", 503, true, {
      "retry-after": "60",
    });
  if (body.attachmentIds.length > 0 && context.env.ATTACHMENTS === undefined)
    return backendError("service_unavailable", "none", 503);
  try {
    const resolved = await resolveAttachmentsForAdmit(
      db,
      context.get("accountId"),
      body.attachmentIds,
      body.id
    );
    if (resolved.kind === "not_found")
      return backendError("not_found", "edit_request", 404);
    if (resolved.kind === "invalid")
      return backendError("validation", "edit_request", 422);
    if (resolved.kind === "rejected")
      return backendError("attachment_rejected", "edit_request", 422);
    const accountBackend = account(context);
    const admission = await accountBackend.admit(
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
    if (admission === "attachment_not_found") {
      return backendError("not_found", "edit_request", 404);
    }
    if (admission === "attachment_invalid") {
      return backendError("validation", "edit_request", 422);
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
  } catch {
    return backendError("service_unavailable", "retry", 503, true, {
      "retry-after": "60",
    });
  }
}

export async function handleGenerationEvents(
  context: CoreContext
): Promise<Response> {
  const lastEventId = context.req.raw.headers.get("last-event-id");
  const generationId = context.req.param("id");
  const target = new URL("https://account.internal/events");
  target.searchParams.set("generationId", generationId);
  const response = await account(context).fetch(
    new Request(target, { headers: context.req.raw.headers })
  );
  if (response.status === 404)
    return json({ error: { code: "not_found", retryable: false } }, 404);
  if (lastEventId === "")
    return backendError("bad_request", "edit_request", 400);
  if (response.status === 503) {
    const headers = new Headers(response.headers);
    if (!headers.has("retry-after")) headers.set("retry-after", "60");
    return new Response(response.body, { status: 503, headers });
  }
  return response;
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
  if (r2 === undefined) return backendError("service_unavailable", "none", 503);
  const parsed = await readBoundedJson(context.req.raw, 65_536);
  if (parsed.kind === "too_large")
    return backendError("attachment_too_large", "edit_request", 413);
  if (parsed.kind === "invalid")
    return backendError("bad_request", "edit_request", 400);
  const staged = parseAttachmentStageRequest(parsed.value);
  if (staged.kind === "invalid")
    return backendError("validation", "edit_request", 422);
  if (staged.kind === "rejected")
    return backendError("attachment_rejected", "edit_request", 422);
  const request = staged.request;
  const db = context.env.DB;
  if (db === undefined)
    return backendError("service_unavailable", "retry", 503, true, {
      "retry-after": "60",
    });
  const signedConfig = parseSignedUploadConfig(context.env);
  if (signedConfig === null)
    return backendError("service_unavailable", "none", 503);
  try {
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
  } catch {
    return backendError("service_unavailable", "retry", 503, true, {
      "retry-after": "60",
    });
  }
}

export async function handleAttachmentComplete(
  context: CoreContext
): Promise<Response> {
  const r2 = context.env.ATTACHMENTS;
  const ingest = context.env.ATTACHMENT_INGEST;
  const db = context.env.DB;
  if (db === undefined)
    return backendError("service_unavailable", "retry", 503, true, {
      "retry-after": "60",
    });
  if (r2 === undefined || ingest === undefined)
    return backendError("service_unavailable", "none", 503);
  const attachmentId = context.req.param("id");
  if (
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(
      attachmentId
    )
  )
    return backendError("bad_request", "edit_request", 400);
  try {
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
        return backendError("not_found", "edit_request", 404);
      case "expired":
        return backendError("attachment_expired", "edit_request", 410);
      case "absent":
        return backendError("attachment_not_uploaded", "retry", 422, true);
      case "mismatch":
        return backendError(
          "attachment_metadata_mismatch",
          "edit_request",
          422
        );
      case "conflict":
        return backendError("attachment_rejected", "edit_request", 409);
    }
  } catch {
    return backendError("service_unavailable", "retry", 503, true, {
      "retry-after": "60",
    });
  }
}

export async function handleDeviceSessionOpen(
  context: CoreContext
): Promise<Response> {
  const db = context.env.DB;
  if (db === undefined)
    return backendError("service_unavailable", "retry", 503, true, {
      "retry-after": "1",
    });
  const parsed = await readBoundedJson(context.req.raw, 65_536);
  if (parsed.kind === "too_large" || parsed.kind === "invalid")
    return backendError("invalid_request", "edit_request", 400);
  const request = parseDeviceSessionCreate(parsed.value);
  if (request === null)
    return backendError("invalid_request", "edit_request", 400);
  try {
    const session = await openDeviceSession(
      db,
      context.get("accountId"),
      request,
      Date.now()
    );
    return session === null
      ? backendError("device_session_conflict", "edit_request", 409)
      : json({ session }, 201);
  } catch {
    return listenRetryableUnavailable();
  }
}

export async function handleDeviceSessionAudio(
  context: CoreContext
): Promise<Response> {
  const pathError = listenSessionPathError(context.req.param("id"));
  if (pathError !== null) return pathError;
  const r2 = context.env.ATTACHMENTS;
  const db = context.env.DB;
  if (db === undefined)
    return backendError("service_unavailable", "retry", 503, true, {
      "retry-after": "1",
    });
  if (r2 === undefined) return backendError("service_unavailable", "none", 503);
  const parsed = await readBoundedJson(context.req.raw, 2_097_152);
  if (parsed.kind === "too_large" || parsed.kind === "invalid")
    return backendError("invalid_request", "edit_request", 400);
  const request = parseDeviceSessionAudioBatch(parsed.value);
  if (request === null)
    return backendError("invalid_request", "edit_request", 400);
  try {
    const outcome = await appendDeviceSessionAudioBatch(
      db,
      r2,
      context.get("accountId"),
      context.req.param("id"),
      request,
      Date.now()
    );
    switch (outcome.kind) {
      case "ok":
        return json({ session: outcome.session });
      case "unavailable":
        return listenRetryableUnavailable();
      case "not_found":
        return backendError("device_session_not_found", "none", 404);
      case "conflict":
        return backendError("device_session_conflict", "edit_request", 409);
      case "too_large":
        return backendError("invalid_request", "edit_request", 400);
    }
  } catch {
    return listenRetryableUnavailable();
  }
}

export async function handleDeviceSessionComplete(
  context: CoreContext
): Promise<Response> {
  const pathError = listenSessionPathError(context.req.param("id"));
  if (pathError !== null) return pathError;
  const db = context.env.DB;
  if (db === undefined)
    return backendError("service_unavailable", "retry", 503, true, {
      "retry-after": "1",
    });
  try {
    const outcome = await completeDeviceSession(
      db,
      context.get("accountId"),
      context.req.param("id"),
      Date.now()
    );
    if (outcome.kind === "conflict")
      return backendError("device_session_conflict", "edit_request", 409);
    return outcome.kind === "not_found"
      ? backendError("device_session_not_found", "none", 404)
      : json({ session: outcome.session });
  } catch {
    return listenRetryableUnavailable();
  }
}

export async function handleDeviceSessionRead(
  context: CoreContext
): Promise<Response> {
  const pathError = listenSessionPathError(context.req.param("id"));
  if (pathError !== null) return pathError;
  const db = context.env.DB;
  if (db === undefined)
    return backendError("service_unavailable", "retry", 503, true, {
      "retry-after": "1",
    });
  try {
    const session = await readDeviceSession(
      db,
      context.get("accountId"),
      context.req.param("id")
    );
    return session === null
      ? backendError("device_session_not_found", "none", 404)
      : json({ session });
  } catch {
    return listenRetryableUnavailable();
  }
}

export async function handleDeviceSessionList(
  context: CoreContext
): Promise<Response> {
  const db = context.env.DB;
  if (db === undefined)
    return backendError("service_unavailable", "retry", 503, true, {
      "retry-after": "1",
    });
  try {
    return json({
      sessions: await listDeviceSessions(db, context.get("accountId")),
    });
  } catch {
    return listenRetryableUnavailable();
  }
}

export async function handleConversations(
  context: CoreContext
): Promise<Response> {
  const query = new URL(context.req.url).searchParams;
  const hasOffset = query.has("offset");
  if (hasOffset) {
    if (query.getAll("limit").length > 1 || query.getAll("offset").length > 1) {
      return backendError("bad_request", "edit_request", 400);
    }
    const limit = parseOffsetModeLimit(query.get("limit") ?? undefined);
    const offset = parseOffset(query.get("offset") ?? undefined);
    const db = context.env.DB;
    if (db === undefined)
      return backendError("service_unavailable", "retry", 503, true);
    const items = await readConversations(db, context.get("accountId"));
    return json(
      items
        .slice(offset, offset + limit)
        .map((item) => toLegacyConversation(item))
    );
  }
  if (query.getAll("limit").length > 1 || query.getAll("cursor").length > 1) {
    return backendError("bad_request", "edit_request", 400);
  }
  const limit = parseEnvelopeLimit(query.get("limit") ?? undefined);
  const cursor = query.get("cursor") ?? undefined;
  if (limit === null || cursor === "")
    return backendError("bad_request", "edit_request", 400);
  const db = context.env.DB;
  if (db === undefined)
    return backendError("service_unavailable", "retry", 503, true);
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
  const query = forwardedListQuery(new URL(context.req.url).searchParams);
  if (query === "duplicate")
    return backendError("bad_request", "edit_request", 400);
  const limit = parseEnvelopeLimit(query.get("limit") ?? undefined);
  const cursor = query.get("cursor") ?? undefined;
  if (limit === null || cursor === "")
    return backendError("bad_request", "edit_request", 400);
  const contractVersion = context.req.header("x-omi-contract-version");
  const result = await readCanonicalMemoryPage({
    service: context.env.CANONICAL_SERVICE,
    caller: {
      accountId: context.get("accountId"),
      authorization: context.req.header("authorization"),
      stagingApiToken: context.env.API_TOKEN,
    },
    query,
    ...(contractVersion === undefined ? {} : { contractVersion }),
  });
  if (result.kind === "page") return result.response;
  if (result.kind === "denied")
    return new Response(
      JSON.stringify({
        error:
          result.status === 401
            ? "unauthorized"
            : result.status === 403
            ? "forbidden"
            : "bad_request",
      }),
      {
        status: result.status,
        headers: {
          "content-type": "application/json",
          "cache-control": "no-store",
        },
      }
    );
  if (result.kind === "unbound" || result.kind === "unreadable") {
    return backendError("projection_unavailable", "none", 503);
  }
  return backendError("projection_unavailable", "retry", 503, true);
}

export async function handleTasks(context: CoreContext): Promise<Response> {
  const query = forwardedListQuery(new URL(context.req.url).searchParams);
  if (query === "duplicate")
    return backendError("bad_request", "edit_request", 400);
  if (context.env.CANONICAL_SERVICE !== undefined) {
    const contractVersion = context.req.header("x-omi-contract-version");
    return requestCanonicalTasks({
      service: context.env.CANONICAL_SERVICE,
      caller: {
        accountId: context.get("accountId"),
        authorization: context.req.header("authorization"),
        stagingApiToken: context.env.API_TOKEN,
      },
      method: "GET",
      query,
      ...(contractVersion === undefined ? {} : { contractVersion }),
    });
  }
  const db = context.env.DB;
  if (db === undefined)
    return backendError("service_unavailable", "retry", 503, true);
  const limit = parseTaskLimit(query.get("limit"));
  const cursor = query.get("cursor") ?? undefined;
  // Match conversations/memories: empty cursor / invalid limit are bad requests.
  if (limit === null || cursor === "")
    return backendError("bad_request", "edit_request", 400);
  const page = await readTasks(db, context.get("accountId"), limit, cursor);
  if (page === "invalid_cursor")
    return backendError("bad_request", "edit_request", 400);
  if (page === "unavailable")
    return backendError("service_unavailable", "retry", 503, true);
  return json(page);
}

export async function handleTaskWrite(context: CoreContext): Promise<Response> {
  const parsed = await readBoundedJson(context.req.raw, 1_000_000);
  if (parsed.kind !== "ok")
    return backendError("bad_request", "edit_request", 400);
  const contractVersion = context.req.header("x-omi-contract-version");
  return requestCanonicalTasks({
    service: context.env.CANONICAL_SERVICE,
    caller: {
      accountId: context.get("accountId"),
      authorization: context.req.header("authorization"),
      stagingApiToken: context.env.API_TOKEN,
    },
    method: "POST",
    body: parsed.raw,
    ...(contractVersion === undefined ? {} : { contractVersion }),
  });
}

function listenTranscriptResponse(
  transcription: DeviceTranscriptionProjection,
  transcribe: boolean
): Response {
  const pending =
    transcription.state === "queued" || transcription.state === "running";
  return json(
    { transcription },
    transcribe && pending ? 202 : 200,
    pending ? { "retry-after": "2" } : undefined
  );
}

function listenSessionPathError(sessionId: string): Response | null {
  return DEVICE_SESSION_ID.test(sessionId)
    ? null
    : backendError("not_found", "none", 404);
}

function listenRetryableUnavailable(): Response {
  return backendError("service_unavailable", "retry", 503, true, {
    "retry-after": "1",
  });
}

export function unmatchedRouteError(pathname: string): Response {
  if (pathname === "/v1/settings") return json({ error: "not_found" }, 404);
  const listenPath =
    pathname === "/v1/device-sessions" ||
    pathname === "/v1/device-sessions/ownership" ||
    /^\/v1\/device-sessions\/[^/]+(?:\/(?:audio|complete|transcribe|transcript))?$/.test(
      pathname
    );
  return backendError("not_found", listenPath ? "none" : "edit_request", 404);
}

export async function handleTranscription(
  context: CoreContext
): Promise<Response> {
  const pathError = listenSessionPathError(context.req.param("id"));
  if (pathError !== null) return pathError;
  if (context.env.DB === undefined)
    return backendError("service_unavailable", "retry", 503, true, {
      "retry-after": "1",
    });
  try {
    const row = await readDeviceTranscription(
      context.env.DB,
      context.get("accountId"),
      context.req.param("id")
    );
    if (row === null)
      return backendError("device_session_not_found", "none", 404);
    const transcription = projectDeviceTranscription(row);
    if (transcription === null)
      return backendError("service_unavailable", "none", 503);
    return listenTranscriptResponse(transcription, false);
  } catch {
    return listenRetryableUnavailable();
  }
}

export async function handleTranscribe(
  context: CoreContext
): Promise<Response> {
  const pathError = listenSessionPathError(context.req.param("id"));
  if (pathError !== null) return pathError;
  const { DB, ATTACHMENTS, AI } = context.env;
  if (DB === undefined)
    return backendError("service_unavailable", "retry", 503, true, {
      "retry-after": "1",
    });
  if (ATTACHMENTS === undefined || AI === undefined)
    return backendError("service_unavailable", "none", 503);
  const accountId = context.get("accountId"),
    sessionId = context.req.param("id");
  try {
    const session = await DB.prepare(
      "SELECT state FROM device_sessions WHERE id = ? AND account_id = ?"
    )
      .bind(sessionId, accountId)
      .first<{ state: string }>();
    if (session === null)
      return backendError("device_session_not_found", "none", 404);
    if (session.state !== "complete")
      return backendError("device_session_conflict", "retry", 409);
    await processDeviceTranscriptions(
      DB,
      ATTACHMENTS,
      AI as TranscriptionAI,
      Date.now(),
      { accountId, sessionId }
    );
    const response = await handleTranscription(context);
    if (response.status !== 200) return response;
    const payload = (await response.json()) as {
      transcription: DeviceTranscriptionProjection;
    };
    return listenTranscriptResponse(payload.transcription, true);
  } catch {
    return listenRetryableUnavailable();
  }
}

export const publicRoutes: readonly CoreRoute[] = [
  { method: "GET", path: "/health", handle: handleHealth },
  { method: "GET", path: "/ready", handle: handleReady },
];

export const v1Routes: readonly CoreRoute[] = [
  {
    method: "GET",
    path: "/v1/device-sessions/ownership",
    handle: () => backendError("capture_ownership_unavailable", "none", 503),
  },
  {
    method: "POST",
    path: "/v1/device-sessions/:id/transcribe",
    handle: handleTranscribe,
  },
  { method: "POST", path: "/v1/tasks/ops", handle: handleTaskWrite },
  {
    method: "GET",
    path: "/v1/device-sessions/:id/transcript",
    handle: handleTranscription,
  },
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
    path: "/v1/device-sessions/:id",
    handle: handleDeviceSessionRead,
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
