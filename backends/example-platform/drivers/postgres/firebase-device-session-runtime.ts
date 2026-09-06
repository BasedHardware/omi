import { createPostgresFirebaseAuthorizationRuntime, type PostgresFirebaseAuthorizationRuntimeOptions } from "./firebase-authorized-runtime-support";
import { createPostgresDeviceSessionUploadRepository } from "./listen-finalization-repository";
import { PostgresRepositoryError } from "./transaction";
import { DEVICE_UPLOAD_MAX_BODY, DEVICE_UPLOAD_SESSION_ID, parseDeviceSessionUploadAudio, parseDeviceSessionUploadCreate } from "../../apps/service/stores/device-session-upload";

const error = (status: number, code: string) => Response.json({ error: { code } }, {
  status, headers: { "cache-control": "no-store", ...(status === 503 ? { "retry-after": "1" } : {}) },
});
async function body(request: Request): Promise<unknown> {
  if (request.body === null) throw new TypeError("invalid_device_request");
  const reader = request.body.getReader();
  const cancel = () => { void reader.cancel().catch(() => undefined); };
  request.signal.addEventListener("abort", cancel, { once: true });
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let bytes = 0, text = "";
  try {
    request.signal.throwIfAborted();
    while (true) {
      const chunk = await reader.read();
      request.signal.throwIfAborted();
      if (chunk.done) break;
      bytes += chunk.value.length;
      if (bytes > DEVICE_UPLOAD_MAX_BODY) throw new TypeError("invalid_device_request");
      text += decoder.decode(chunk.value, { stream: true });
    }
    return JSON.parse(text + decoder.decode());
  } finally {
    request.signal.removeEventListener("abort", cancel);
    await reader.cancel().catch(() => undefined);
  }
}
export function createPostgresFirebaseDeviceSessionRuntime(options: PostgresFirebaseAuthorizationRuntimeOptions) {
  const authority = createPostgresFirebaseAuthorizationRuntime(options, "listen.capture.write");
  return Object.freeze({
    async fetch(request: Request): Promise<Response> {
      const path = new URL(request.url).pathname;
      const match = /^\/v1\/device-sessions\/([^/]+)(?:\/(audio|complete))?$/.exec(path);
      const opening = path === "/v1/device-sessions" && request.method === "POST";
      if (!opening && (!match || !DEVICE_UPLOAD_SESSION_ID.test(match[1]!)
        || (match[2] ? request.method !== "POST" : request.method !== "GET"))) return error(404, "not_found");
      try {
        request.signal.throwIfAborted();
        const token = request.headers.get("authorization")?.match(/^Bearer (\S+)$/)?.[1] ?? "";
        const authorized = await authority.authorizer.authorize(token, Math.floor(Date.now() / 1000));
        if (!authorized.authorized) return error(authorized.outcome === "authentication" ? 401 : authorized.outcome === "unavailable" ? 503 : 403,
          authorized.outcome === "authentication" ? "unauthorized" : authorized.outcome === "unavailable" ? "unavailable" : "forbidden");
        request.signal.throwIfAborted();
        const repository = createPostgresDeviceSessionUploadRepository({ pool: Object.freeze<typeof authority.pool>({
          withTransaction: (options, callback) => authority.pool.withTransaction({ ...options, signal: request.signal }, callback),
        }) });
        const context = authorized.context;
        const session = opening ? await repository.open(context, parseDeviceSessionUploadCreate(await body(request)))
          : match![2] === "audio" ? await (async () => {
            const chunk = parseDeviceSessionUploadAudio(await body(request));
            return repository.append(context, match![1]!, chunk.index, chunk.bytes);
          })()
          : match![2] === "complete" ? await repository.complete(context, match![1]!)
          : await repository.read(context, match![1]!);
        if (session === null) return error(404, "device_session_not_found");
        return Response.json({ session }, { status: opening ? 201 : 200, headers: { "cache-control": "no-store" } });
      } catch (cause) {
        if (request.signal.aborted) return error(503, "unavailable");
        if (cause instanceof TypeError || cause instanceof SyntaxError) return error(400, "invalid_request");
        if (cause instanceof PostgresRepositoryError) {
          if (cause.code === "idempotency_conflict" || cause.code === "transition_invalid") return error(409, "device_session_conflict");
          if (["authorization_state_denied", "expired_context", "stale_epoch", "destination_inactive", "lifecycle_inactive", "credential_inactive", "grant_inactive", "capability_denied"].includes(cause.code)) return error(403, "forbidden");
        }
        return error(503, "unavailable");
      }
    },
  });
}
