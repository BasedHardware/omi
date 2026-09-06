import { CaptureOwnershipChanged, createCaptureOwnershipCodec } from "../../apps/service/codecs/capture-ownership";
import { createPostgresFirebaseAuthorizationRuntime, type PostgresFirebaseAuthorizationRuntimeOptions } from "./firebase-authorized-runtime-support";
import { createPostgresDeviceSessionUploadRepository, createPostgresDeviceTranscriptionRepository } from "./listen-finalization-repository";
import type { PrerecordedTranscriptionSource } from "../../apps/service/listen/prerecorded-transcription";
import { deviceTranscriptionProjection } from "../../apps/service/listen/device-transcription";
import { transcribeDeviceSession } from "./device-transcription";
import { isProxy } from "node:util/types";
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
export function createPostgresFirebaseDeviceSessionRuntime(options: PostgresFirebaseAuthorizationRuntimeOptions, source?: PrerecordedTranscriptionSource, ownershipKey?: Uint8Array) {
  const ownership = ownershipKey === undefined ? undefined : createCaptureOwnershipCodec(ownershipKey);
  if (source !== undefined && (source === null || typeof source !== "object" || isProxy(source)
    || typeof Object.getOwnPropertyDescriptor(source, "transcribe")?.value !== "function"
    || isProxy(Object.getOwnPropertyDescriptor(source, "transcribe")!.value))) throw new TypeError("invalid_transcription_source");
  const transcribe = source === undefined ? undefined : Object.getOwnPropertyDescriptor(source, "transcribe")!.value as PrerecordedTranscriptionSource["transcribe"];
  const stableSource: PrerecordedTranscriptionSource | undefined = source === undefined ? undefined : Object.freeze({ transcribe: transcribe!.bind(source) });
  const authority = createPostgresFirebaseAuthorizationRuntime(options, "listen.capture.write");
  const authorizationOptions = Object.freeze({ ...options, pool: authority.pool });
  const bindPool = (signal: AbortSignal) => Object.freeze<typeof authority.pool>({
    withTransaction: (options, callback) => authority.pool.withTransaction({ ...options, signal }, callback),
  });
  const authorize = (token: string, signal: AbortSignal) => {
    signal.throwIfAborted();
    const runtime = createPostgresFirebaseAuthorizationRuntime({ ...authorizationOptions, pool: bindPool(signal) }, "listen.capture.write");
    return new Promise<Awaited<ReturnType<typeof runtime.authorizer.authorize>>>((resolve, reject) => {
      const abort = () => reject(signal.reason ?? new Error("request_aborted"));
      signal.addEventListener("abort", abort, { once: true });
      if (signal.aborted) { abort(); return; }
      void runtime.authorizer.authorize(token, Math.floor(Date.now()/1000)).then(value => {
        signal.removeEventListener("abort", abort); resolve(value);
      }, cause => { signal.removeEventListener("abort", abort); reject(cause); });
    });
  };
  return Object.freeze({
    async fetch(request: Request): Promise<Response> {
      const path = new URL(request.url).pathname;
      const match = /^\/v1\/device-sessions\/([^/]+)(?:\/(audio|complete|transcribe|transcript))?$/.exec(path);
      const readingOwnership = path === "/v1/device-sessions/ownership" && request.method === "GET";
      const opening = path === "/v1/device-sessions" && request.method === "POST";
      if (!readingOwnership && !opening && (!match || !DEVICE_UPLOAD_SESSION_ID.test(match[1]!)
        || (match[2] && match[2] !== "transcript" ? request.method !== "POST" : request.method !== "GET"))) return error(404, "not_found");
      try {
        request.signal.throwIfAborted();
        const token = request.headers.get("authorization")?.match(/^Bearer (\S+)$/)?.[1] ?? "";
        const authorized = await authorize(token, request.signal);
        if (!authorized.authorized) return error(authorized.outcome === "authentication" ? 401 : authorized.outcome === "unavailable" ? 503 : 403,
          authorized.outcome === "authentication" ? "unauthorized" : authorized.outcome === "unavailable" ? "unavailable" : "forbidden");
        request.signal.throwIfAborted();
        if (ownership === undefined) return error(503, "capture_ownership_unavailable");
        if (readingOwnership) return Response.json({ ownership: ownership.issue(authorized.context) }, { headers: { "cache-control": "no-store" } });
        const receipt = request.headers.get("x-omi-capture-ownership");
        ownership.verify(authorized.context, receipt);
        const pool = bindPool(request.signal);
        if (match?.[2] === "transcribe" || match?.[2] === "transcript") {
          if (match[2] === "transcribe" && source === undefined) return error(503, "unavailable");
          const record = match[2] === "transcript"
            ? await createPostgresDeviceTranscriptionRepository({ pool }).read(authorized.context, match[1]!)
            : await transcribeDeviceSession({ pool: authority.pool, source: stableSource!, sessionId: match[1]!, signal: request.signal,
              authorize: async signal => {
                const current = await authorize(token, signal);
                if (!current.authorized) throw error(current.outcome === "authentication" ? 401 : current.outcome === "unavailable" ? 503 : 403,
                  current.outcome === "authentication" ? "unauthorized" : current.outcome === "unavailable" ? "unavailable" : "forbidden");
                ownership.verify(current.context, receipt);
                return current.context;
              },
            });
          if (record === null) return error(404, "device_session_not_found");
          const pending = record.state === "queued" || record.state === "running";
          return Response.json({ transcription: deviceTranscriptionProjection(record) }, {
            status: match[2] === "transcribe" && pending ? 202 : 200,
            headers: { "cache-control": "no-store", ...(pending ? { "retry-after": "2" } : {}) },
          });
        }
        const repository = createPostgresDeviceSessionUploadRepository({ pool });
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
        if (cause instanceof Response) return cause;
        if (cause instanceof CaptureOwnershipChanged) return error(409, "capture_ownership_changed");
        if (cause instanceof TypeError || cause instanceof SyntaxError) return error(400, "invalid_request");
        if (cause instanceof PostgresRepositoryError) {
          if (cause.code === "capture_ownership_changed") return error(409, "capture_ownership_changed");
          if (cause.code === "idempotency_conflict" || cause.code === "transition_invalid") return error(409, "device_session_conflict");
          if (["authorization_state_denied", "expired_context", "stale_epoch", "destination_inactive", "lifecycle_inactive", "credential_inactive", "grant_inactive", "capability_denied"].includes(cause.code)) return error(403, "forbidden");
        }
        return error(503, "unavailable");
      }
    },
  });
}
