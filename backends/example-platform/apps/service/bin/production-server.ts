import { createPostgresRenderResponseRepository } from "../../../drivers/postgres/product-projection-repository";
import { createDeepgramTranscriptionSource } from "../../../drivers/model/deepgram-transcription";
import type { PostgresFirebaseAuthorizationRuntimeOptions } from "../../../drivers/postgres/firebase-authorized-runtime-support";
import { createPersistedRenderModel } from "../../../drivers/model/persisted-render";
import { createFirebaseAdminIdTokenAdapter } from "../../../drivers/firebase/admin-id-token";
import { createHttpRenderModel } from "../../../drivers/model/http-render";
import { createPostgresFirebaseAuthorizedMemoryServiceProcess } from "../../../drivers/postgres/firebase-authorized-memory-service-process";
import { createPostgresJsTransactionPool } from "../../../drivers/postgres/postgresjs";
import { createPostgresProductionRuntimeReadiness } from "../../../drivers/postgres/production-runtime-readiness";
import { renderStructuralTree } from "../../../core/retrieve/render";
import { buildDeterministicAnchors } from "../../../core/retrieve/tree";
import { createServedCounter } from "../observability/served-count";
import { readDeployedConfig } from "../composition/deployed-config";
import { createProductionCursor } from "../composition/production-cursor";

export function requestTimeoutMilliseconds(method: string, path: string): number {
  return method === "POST" && /^\/v1\/device-sessions\/[^/]+\/transcribe$/.test(path) ? 135000 : 25000;
}

export async function startProductionServer(env: Readonly<Record<string, string | undefined>>) {
  const config = readDeployedConfig(env);
  const identity = await createFirebaseAdminIdTokenAdapter({
    project_id: config.projectId, app_name: "omi-platform-deployed", runtime_mode: "deployed",
  });
  const pool = createPostgresJsTransactionPool({
    connectionString: config.databaseUrl, databaseSocketDirectory: config.databaseSocketDirectory, maxConnections: 4, connectTimeoutSeconds: 10,
  });
  const cursorSigningKeyset = { active_key_id: "v1", keys: [{ key_id: "v1", secret: config.cursorKey }] };
  const cursor = createProductionCursor(cursorSigningKeyset);
  const authorization: PostgresFirebaseAuthorizationRuntimeOptions = {
    pool, project_id: config.projectId, application_id: config.applicationId,
    runtime_mode: "deployed", id_token_adapter: identity.adapter,
    database_generation_digest: config.databaseGeneration, context_ttl_seconds: 60,
  };
  const runtime = createPostgresFirebaseAuthorizedMemoryServiceProcess({
    pool,
    readiness: createPostgresProductionRuntimeReadiness(pool, config.databaseGeneration),
    graceful_shutdown_ms: 4000,
    service_options: {
      counter: createServedCounter(),
      now_epoch_seconds: () => Math.floor(Date.now() / 1000),
      mcp_handler: () => Response.json({ error: "unavailable" }, { status: 503, headers: { "cache-control": "no-store" } }),
      tasks: { authorization, codecRootSecret: config.codecKey, cursorSigningKeyset },
      conversations: { authorization, codecRootSecret: config.codecKey, cursorSigningKeyset },
      device_sessions: authorization,
      device_ownership_key: config.codecKey,
      transcription_source: createDeepgramTranscriptionSource({
        apiKey: config.transcriptionApiKey, model: config.transcriptionModel, timeoutMilliseconds: 120000,
      }),
      memory_read: {
        authorization,
        product: {
          account_timezone: config.accountTimezone, codec_root_secret: config.codecKey,
          verify_cursor: cursor.verifyCursor, issue_cursor: cursor.issueCursor,
          accepted_coverage_state: "unavailable", stm_coverage_state: "unavailable",
          trace_sink: () => undefined,
          async produce_renders(projected, caller) {
            const tree = buildDeterministicAnchors(projected);
            const options = {
              strategy: "application-memory-render", model_version: config.laneId,
              prompt_version: "grounded-memory-v1", policy_version: "authorized-claims-v1", schema_version: "summary-citations-v1",
            };
            const cachePool = Object.freeze<typeof pool>({
              ...pool,
              withTransaction: (options, callback) => pool.withTransaction({ ...options, ...(caller.signal ? { signal: caller.signal } : {}) }, callback),
            });
            const cache = createPostgresRenderResponseRepository(cachePool);
            const model = createPersistedRenderModel({
              projected, options,
              model: createHttpRenderModel({
                endpoint: config.gatewayEndpoint, apiKey: config.gatewayToken,
                laneId: config.laneId, firebaseUid: caller.firebase_uid, signal: caller.signal,
              }),
              read: (key) => cache.read(caller.authority_context, key),
              publish: (key, response) => cache.publish(caller.authority_context, key, response),
            });
            const renders = await renderStructuralTree(tree, projected, model, options);
            if (renders.some(render => render.status !== "ready" || render.citations.length === 0 || render.stale)) throw new Error("render_unavailable");
            return renders;
          },
        },
      },
    },
  });
  let inFlight = 0;
  const server = Bun.serve({
    hostname: "0.0.0.0", port: config.port, idleTimeout: 150, maxRequestBodySize: 2 * 1024 * 1024,
    async fetch(request) {
      const path = new URL(request.url).pathname;
      if (path === "/health" || path === "/ready") return runtime.fetch(request);
      if (inFlight >= 2) return Response.json({ error: "unavailable" }, { status: 503, headers: { "retry-after": "1" } });
      inFlight += 1;
      const controller = new AbortController();
      const cancel = () => controller.abort();
      request.signal.addEventListener("abort", cancel, { once: true });
      if (request.signal.aborted) controller.abort();
      const deadline = setTimeout(cancel, requestTimeoutMilliseconds(request.method, path));
      try { return await runtime.fetch(new Request(request, { signal: controller.signal })); }
      finally {
        clearTimeout(deadline);
        request.signal.removeEventListener("abort", cancel);
        inFlight -= 1;
      }
    },
  });
  let stopping: Promise<void> | undefined;
  const stop = () => stopping ??= (async () => {
    await runtime.stop();
    await server.stop(true);
    await identity.close();
  })();
  try {
    const startup = await runtime.start();
    if (startup.kind !== "ready") throw new Error("database_readiness_unavailable");
  } catch {
    await stop();
    throw new Error("production_startup_unavailable");
  }
  return { server, stop };
}

if (import.meta.main) {
  const startupDeadline = setTimeout(() => {
    console.error("omi-platform startup deadline exceeded");
    process.exit(1);
  }, 45000);
  startProductionServer(process.env).then(({ stop }) => {
    clearTimeout(startupDeadline);
    console.info("omi-platform ready: memories.read, tasks, device audio uploads");
    const shutdown = () => {
      const deadline = setTimeout(() => process.exit(1), 8000);
      stop().then(() => { clearTimeout(deadline); process.exit(0); }, () => process.exit(1));
    };
    process.once("SIGTERM", shutdown);
    process.once("SIGINT", shutdown);
  }).catch(() => {
    clearTimeout(startupDeadline);
    console.error("omi-platform startup unavailable: check required configuration and database readiness");
    process.exit(1);
  });
}
