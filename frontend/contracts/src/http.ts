/**
 * The injected HTTP seam — a pure declaration, so it lives here rather than in
 * the adapter package that used to own it.
 *
 * Placement: top-level, NOT under `bridge/`. This seam is transport-neutral —
 * the privileged bridge binds it, the DEV harness binds a direct fetch, tests
 * bind a script, and a future desktop shell binds its own net module.
 * `bridge/http.ts` is ONE implementation contract for crossing the bridge;
 * putting the seam itself in there would imply the bridge owns it. So it sits
 * beside the other cross-cutting declarations (`errors.ts`, `ids.ts`,
 * `snapshot.ts`).
 *
 * Adapters never construct absolute URLs and never touch tokens — auth and the
 * base URL are the transport binding's job (ADR-008 §3 / ADR-009 §3).
 *
 * The status → taxonomy mapping (`classifyStatus`) is executable, so it cannot
 * live here (nothing in `contracts/` executes). It lives in `@omi-core/kernel`.
 */

export interface HttpResponse {
  status: number;
  /** Parsed JSON body, or null when the body was empty/unparseable. */
  json: unknown;
  /** Retry-After in milliseconds when the server sent one. */
  retryAfterMs?: number;
}

export interface HttpClient {
  request(method: "GET" | "POST" | "PATCH" | "DELETE", path: string, body?: unknown): Promise<HttpResponse>;
}
