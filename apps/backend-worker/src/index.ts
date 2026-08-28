import { Hono } from "hono";

import { AccountBackend } from "./account";
import {
  consumeAttachmentIngest,
  type AttachmentIngestMessage,
} from "./attachments";
import {
  authorizeV1,
  publicRoutes,
  safeRoute,
  v1Routes,
  type CoreContext,
  type CoreEnv,
} from "./http-core";
import { type GatewaySecretEnv } from "./openrouter";
import {
  requestCompletedEvent,
  requestFailedEvent,
  type ObservabilityEnv,
} from "./observability";
import { backendError } from "./wire";

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
    VECTORIZE?: Vectorize;
    R2_ACCOUNT_ID?: string;
    R2_BUCKET_NAME?: string;
    R2_ACCESS_KEY_ID?: string;
    R2_SECRET_ACCESS_KEY?: string;
    R2_SIGNED_URL_TTL_SECONDS?: string | number;
  };
type Variables = { accountId: string; requestId: string };

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
        route: safeRoute(context.req.routePath),
        status: context.res.status,
        durationMs: Math.max(0, Date.now() - startedAt),
      })
    )
  );
});

for (const route of publicRoutes) {
  app.on(route.method, route.path, (context) =>
    route.handle(fromHono(context))
  );
}

app.use("/v1/*", async (context, next) => {
  const refusal = authorizeV1(fromHono(context));
  if (refusal !== null) return refusal;
  await next();
});

for (const route of v1Routes) {
  app.on(route.method, route.path, (context) =>
    route.handle(fromHono(context))
  );
}

app.notFound(() => backendError("not_found", "edit_request", 404));
app.onError((error, context) => {
  console.error(
    JSON.stringify(
      requestFailedEvent({
        requestId: context.get("requestId") ?? "unavailable",
        name: error.name,
        route: safeRoute(context.req.routePath),
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
  noCanonicalMemoryStore,
  type CanonicalMemoryStore,
  type RetrievalBoundary,
  type RetrievalEnv,
} from "./retrieval";
export default handler;

function fromHono(context: {
  env: WorkerEnv;
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
}): CoreContext {
  return {
    env: context.env as CoreEnv,
    req: {
      method: context.req.method,
      url: context.req.url,
      raw: context.req.raw,
      routePath: context.req.routePath,
      header: (name) => context.req.header(name),
      param: (name) => context.req.param(name),
    },
    get: (key) => context.get(key),
    set: (key, value) => context.set(key, value),
  };
}
