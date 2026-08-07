/**
 * Web-tier binding for privileged HTTP over the bridge (ADR-008 §3 /
 * ADR-009 §3). Implements the `HttpClient` seam by handing each request to the
 * shell, which owns the base URL, the credential, and the socket.
 *
 * This file holds NO token and NO base URL, by construction — there is nowhere
 * in it for either to live. That is the whole point of the seam: in bridge mode
 * a credential is never present in JS-visible state, so it cannot leak through
 * the bundle, localStorage, IndexedDB, or a devtools heap dump.
 *
 * Transport: the shell installs a reply-capable message handler under
 * `BRIDGE_HTTP_CHANNEL` (macOS: `WKScriptMessageHandlerWithReply`, which makes
 * `postMessage` return a promise). Transports without built-in reply
 * correlation use the request's `id`.
 *
 * Failure policy: this binding NEVER throws and never invents taxonomy. Every
 * outcome becomes an `HttpResponse`, using the contract's documented
 * `BRIDGE_HTTP_FAILURE_STATUS` mapping so `classifyStatus` in adapters-legacy
 * remains the one place a status becomes a `WriteFailure`.
 */

import {
  BRIDGE_HTTP_CHANNEL,
  BRIDGE_HTTP_FAILURE_STATUS,
  type BridgeHttpMethod,
  type BridgeHttpReply,
  type BridgeHttpRequest,
} from "@omi-core/contracts";
// Type-only: the seam lives with the adapters that consume it. Erased at
// runtime, so this adds no dependency edge to the bundle.
import type { HttpClient, HttpResponse } from "@omi-core/adapters-legacy";

/** The reply-capable handler a shell installs. Narrow by design. */
interface ReplyHandler {
  postMessage(message: unknown): Promise<unknown>;
}

function handler(): ReplyHandler | null {
  const w = globalThis as unknown as {
    webkit?: { messageHandlers?: Record<string, ReplyHandler | undefined> };
  };
  const h = w.webkit?.messageHandlers?.[BRIDGE_HTTP_CHANNEL];
  return h && typeof h.postMessage === "function" ? h : null;
}

/**
 * True when the host shell provides privileged HTTP. A surface uses this to
 * choose bridge transport over its dev transport; it must never silently
 * proceed unauthenticated when this is false.
 */
export function isBridgeHttpAvailable(): boolean {
  return handler() !== null;
}

/** Monotonic per-document correlation ids. No randomness needed or wanted. */
let seq = 0;

function parseBody(body: string | null): unknown {
  if (body === null || body === "") return null;
  try {
    return JSON.parse(body) as unknown;
  } catch {
    return null; // matches the seam's contract: unparseable body => null
  }
}

/** Shape-check the shell's reply rather than trusting it. */
function toHttpResponse(raw: unknown): HttpResponse {
  const reply = raw as BridgeHttpReply | undefined;
  if (!reply || typeof reply !== "object" || !("ok" in reply)) {
    return { status: BRIDGE_HTTP_FAILURE_STATUS["shell-error"], json: null };
  }
  if (reply.ok === true) {
    const r = reply.response;
    if (!r || typeof r.status !== "number") {
      return { status: BRIDGE_HTTP_FAILURE_STATUS["shell-error"], json: null };
    }
    const base: HttpResponse = { status: r.status, json: parseBody(r.body ?? null) };
    return typeof r.retryAfterMs === "number" ? { ...base, retryAfterMs: r.retryAfterMs } : base;
  }
  const reason = reply.failure?.reason;
  const status =
    reason !== undefined && reason in BRIDGE_HTTP_FAILURE_STATUS
      ? BRIDGE_HTTP_FAILURE_STATUS[reason]
      : BRIDGE_HTTP_FAILURE_STATUS["shell-error"];
  return { status, json: null };
}

/**
 * Bind the `HttpClient` seam to the shell's privileged transport. Throws only
 * if the bridge is absent — call `isBridgeHttpAvailable()` first.
 */
export function bridgeHttpClient(): HttpClient {
  const h = handler();
  if (!h) {
    throw new Error(
      `bridge HTTP unavailable: no reply-capable "${BRIDGE_HTTP_CHANNEL}" message handler on this host`,
    );
  }
  return {
    async request(method: BridgeHttpMethod, path: string, body?: unknown): Promise<HttpResponse> {
      seq += 1;
      const message: BridgeHttpRequest = {
        id: `h${seq}`,
        method,
        path,
        ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
      };
      try {
        return toHttpResponse(await h.postMessage(message));
      } catch {
        // A rejected handler is a transport failure, not a server answer.
        return { status: BRIDGE_HTTP_FAILURE_STATUS["shell-error"], json: null };
      }
    },
  };
}
