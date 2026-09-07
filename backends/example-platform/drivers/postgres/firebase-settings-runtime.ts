import {
  createFirebaseIdentityVerifier,
  isFirebaseIdentityRefreshUnavailable,
} from "../../apps/service/auth/firebase-identity";
import type { PostgresFirebaseAuthorizationRuntimeOptions } from "./firebase-authorized-runtime-support";

export interface PostgresFirebaseSettingsOptions {
  readonly authorization: PostgresFirebaseAuthorizationRuntimeOptions;
}

const JSON_HEADERS = Object.freeze({
  "cache-control": "no-store",
  "content-type": "application/json",
});
const UNAVAILABLE_HEADERS = Object.freeze({
  ...JSON_HEADERS,
  "retry-after": "60",
});
const SIGNED_OUT_BODY = '{"identity":null,"entitlement":null}';
const UNAUTHORIZED_BODY = '{"error":"unauthorized"}';
const BAD_REQUEST_BODY = '{"error":"bad_request"}';
const UNAVAILABLE_BODY = '{"error":"service_unavailable"}';
const NOT_FOUND_BODY = '{"error":"not_found"}';

const response = (
  body: string,
  status: number,
  headers: Readonly<Record<string, string>> = JSON_HEADERS,
): Response => new Response(body, { status, headers });

const bearerToken = (presentHeader: string): string | null => {
  if (!presentHeader.startsWith("Bearer ")) return null;
  const token = presentHeader.slice("Bearer ".length);
  return token.length > 0 ? token : null;
};

const hasInvalidRequestGrammar = (request: Request): boolean => {
  let url: URL;
  try {
    url = new URL(request.url);
  } catch {
    return true;
  }
  if ([...url.searchParams].length > 0) return true;
  const contentLength = request.headers.get("content-length");
  if (contentLength !== null && contentLength !== "0") return true;
  return request.headers.has("transfer-encoding");
};

export function createPostgresFirebaseSettingsRuntime(
  options: PostgresFirebaseSettingsOptions,
) {
  const authorization = options.authorization;
  const verifier = createFirebaseIdentityVerifier({
    project_id: authorization.project_id,
    runtime_mode: authorization.runtime_mode,
    adapter: authorization.id_token_adapter,
  });
  return Object.freeze({
    async executeRequest(request: Request): Promise<Response> {
      if (request.method !== "GET" || new URL(request.url).pathname !== "/v1/settings") {
        return response(NOT_FOUND_BODY, 404);
      }
      if (hasInvalidRequestGrammar(request)) {
        return response(BAD_REQUEST_BODY, 400);
      }
      const header = request.headers.get("authorization");
      if (header === null) {
        return response(SIGNED_OUT_BODY, 200);
      }
      const token = bearerToken(header);
      if (token === null) {
        return response(UNAUTHORIZED_BODY, 401);
      }
      try {
        request.signal.throwIfAborted();
        const identity = await verifier.resolve(token, Math.floor(Date.now() / 1000));
        if (identity === null) {
          return response(UNAUTHORIZED_BODY, 401);
        }
        if (isFirebaseIdentityRefreshUnavailable(identity)) {
          return response(UNAVAILABLE_BODY, 503, UNAVAILABLE_HEADERS);
        }
        return response(UNAVAILABLE_BODY, 503, UNAVAILABLE_HEADERS);
      } catch {
        return response(UNAVAILABLE_BODY, 503, UNAVAILABLE_HEADERS);
      }
    },
  });
}
