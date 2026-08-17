/**
 * Privileged HTTP over the bridge — ADR-008 §3 / ADR-009 §3.
 *
 * This is the ship-mode counterpart to the DEV-ONLY `devHttpClient`: the
 * surface never performs authenticated network I/O itself. It hands the shell
 * a method, an ORIGIN-RELATIVE path, and an optional JSON body; the shell owns
 * the base URL, the credential, and the socket.
 *
 * Deliberately shaped to serve the EXISTING `HttpClient` seam in
 * `@omi-core/adapters-legacy` (method, path, body -> status + json), not an
 * aspirational HTTP surface. Anything the seam does not need is absent.
 *
 * TOKEN CUSTODY (the point of this contract): no credential and no absolute
 * base URL ever crosses into JS, in either direction.
 * - Outbound: `path` is origin-relative by construction; the shell rejects
 *   anything that parses as absolute. `headers` may never carry auth — see
 *   `BRIDGE_HTTP_FORBIDDEN_HEADERS`, which the shell enforces rather than trusts.
 * - Inbound: only `status`, body text, and a retry hint come back. Response
 *   headers are NOT forwarded, so `set-cookie` / `www-authenticate` and any
 *   other credential material cannot leak into the surface.
 *
 * Streaming stays out of scope: `stream.ts` already reserves that lifecycle.
 * This contract is request/response only, so a body is a whole string.
 */

/** Exactly the methods the `HttpClient` seam exposes — no more. */
export type BridgeHttpMethod = "GET" | "POST" | "PATCH" | "DELETE";

/**
 * The name of the message channel the shell installs and the surface
 * feature-detects. A surface hosted without it falls back to its dev
 * transport; a surface must never silently proceed unauthenticated.
 */
export const BRIDGE_HTTP_CHANNEL = "omiHttp";

/**
 * The global function the surface installs for shells whose channel cannot
 * reply, and which such a shell calls to deliver one reply.
 *
 * Two transport shapes satisfy this contract, which is why `id` is part of the
 * message rather than of a binding:
 * - REPLY-CAPABLE (macOS `WKScriptMessageHandlerWithReply`): `postMessage`
 *   returns a promise and this function is unused.
 * - ONE-WAY (a Flutter `JavaScriptChannel`, an Android `addJavascriptInterface`):
 *   the channel only carries strings surface→shell, so the shell delivers its
 *   reply by invoking this function with the request `id` and the JSON-encoded
 *   `BridgeHttpReply`. The surface correlates it to the pending request.
 *
 * A shell MUST deliver exactly one reply per `id`. A late or duplicate reply is
 * dropped by the surface, never applied to a different request.
 */
export const BRIDGE_HTTP_REPLY_FUNCTION = "__omiHttpReply";

/**
 * Reserved local-navigation query parameter carrying a shell-minted,
 * non-secret document coordinate. One-way hosts use it to distinguish the
 * same document-local request id (for example `h1`) across WebView
 * navigations. It identifies neither a user nor a backend authority.
 */
export const BRIDGE_HTTP_DOCUMENT_QUERY = "__omiHttpDocument";

/**
 * Header names a surface may NEVER set: the shell owns auth and identity.
 * The shell drops these (case-insensitively) instead of trusting callers —
 * a compromised or buggy surface must not be able to forge or override
 * credentials. Lowercase, for direct comparison after normalization.
 */
export const BRIDGE_HTTP_FORBIDDEN_HEADERS = ["authorization", "cookie", "proxy-authorization"] as const;

export interface BridgeHttpRequest {
  /**
   * Correlates a reply to its request. Redundant on transports with built-in
   * reply correlation (macOS `WKScriptMessageHandlerWithReply` returns a
   * promise), but required by transports without it (a Flutter MethodChannel,
   * a Windows named pipe), so it is part of the message rather than the
   * binding.
   */
  id: string;
  /**
   * The current page's non-secret, shell-minted document coordinate. A
   * one-way host rejects requests whose coordinate is not owned by the active
   * navigation before performing any HTTP side effect.
   */
  documentId: string;
  method: BridgeHttpMethod;
  /**
   * ORIGIN-RELATIVE path including any query string — a leading `/` followed by
   * the adapter's own route and query. Never absolute, never scheme-qualified:
   * the shell resolves it against the base URL it alone holds. A shell MUST
   * reject a path it cannot treat as relative rather than guess. (Concrete
   * routes live only in `adapters-legacy` and shells — rule 3.)
   */
  path: string;
  /**
   * Non-privileged headers only (content-type is set by the shell when a body
   * is present). Absent for the common case.
   */
  headers?: Record<string, string>;
  /**
   * JSON-encoded request body, or absent for a bodyless request. A string
   * rather than `unknown` so the message is transport-encodable as-is and the
   * shell never re-serializes the surface's data.
   */
  body?: string;
}

/** A real HTTP reply. `status` is whatever the server said, unmodified. */
export interface BridgeHttpResponse {
  id: string;
  status: number;
  /** Raw body text; `null` when empty. The web binding parses JSON. */
  body: string | null;
  /** Retry-After, already normalized to milliseconds by the shell. */
  retryAfterMs?: number;
}

/**
 * The request never produced an HTTP status: no socket, no reply, or the shell
 * declined. Named reasons rather than a shell-chosen status, so the shell
 * cannot invent taxonomy — `BRIDGE_HTTP_FAILURE_STATUS` is the single
 * documented mapping back onto the existing one in `classifyStatus`.
 */
export type BridgeHttpFailureReason =
  | "offline"
  | "timeout"
  | "cancelled"
  /** The shell could not perform the request (bad path, internal error). */
  | "shell-error"
  /** The shell holds no usable credential — NOT a server rejection. */
  | "not-authenticated";

export interface BridgeHttpFailure {
  id: string;
  reason: BridgeHttpFailureReason;
  detail: string;
}

/**
 * Transport failure -> the synthetic status the web binding reports to the
 * `HttpClient` seam, so `classifyStatus` stays the ONE place statuses become
 * taxonomy (see `adapters-legacy/src/http.ts`).
 *
 * `not-authenticated` maps to 401 on purpose: per the `auth-invalid` rules the
 * outbox must PAUSE and wait for re-authentication, never retry-spin and never
 * drop. Every other reason is transient, so 503 -> `retryable` with backoff.
 */
export const BRIDGE_HTTP_FAILURE_STATUS: Readonly<Record<BridgeHttpFailureReason, number>> = {
  offline: 503,
  timeout: 503,
  cancelled: 503,
  "shell-error": 503,
  "not-authenticated": 401,
};

/** What a shell returns for one request: an HTTP reply or a transport failure. */
export type BridgeHttpReply =
  | { ok: true; response: BridgeHttpResponse }
  | { ok: false; failure: BridgeHttpFailure };
