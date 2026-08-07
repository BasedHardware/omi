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
 * Two transport shapes are supported, feature-detected in this order. Both
 * satisfy the same contract; the difference is only how a reply comes back.
 *  1. REPLY-CAPABLE — `webkit.messageHandlers[CHANNEL].postMessage()` returns a
 *     promise (macOS `WKScriptMessageHandlerWithReply`).
 *  2. ONE-WAY — `window[CHANNEL].postMessage(string)` carries strings
 *     surface→shell only (a Flutter `JavaScriptChannel`, and the same shape
 *     Android's `addJavascriptInterface` gives). The shell delivers its reply by
 *     invoking `BRIDGE_HTTP_REPLY_FUNCTION` with the request `id`, which this
 *     binding installs and correlates. This is why `id` lives in the message
 *     rather than in a binding.
 *
 * Failure policy: this binding NEVER throws and never invents taxonomy. Every
 * outcome becomes an `HttpResponse`, using the contract's documented
 * `BRIDGE_HTTP_FAILURE_STATUS` mapping so `classifyStatus` in @omi-core/kernel
 * remains the one place a status becomes a `WriteFailure`.
 */

import {
  BRIDGE_HTTP_CHANNEL,
  BRIDGE_HTTP_FAILURE_STATUS,
  BRIDGE_HTTP_REPLY_FUNCTION,
  type BridgeHttpMethod,
  type BridgeHttpReply,
  type BridgeHttpRequest,
  type HttpClient,
  type HttpResponse,
} from "@omi-core/contracts";

/**
 * A one-way reply can be lost (a shell crash, a dropped `runJavaScript`). Without
 * a bound, that request's promise never settles and the domain's outbox stalls
 * until relaunch — so an unanswered request becomes a transport failure the
 * outbox can retry. Reply-capable transports cannot lose a reply and are not
 * subject to this.
 */
const DEFAULT_REPLY_TIMEOUT_MS = 30_000;

/** The reply-capable handler shape (transport 1). */
interface ReplyHandler {
  postMessage(message: unknown): Promise<unknown>;
}

/** The one-way channel shape (transport 2): strings out, no return value. */
interface OneWayChannel {
  postMessage(message: string): void;
}

type Transport =
  | { kind: "reply"; handler: ReplyHandler }
  | { kind: "one-way"; channel: OneWayChannel };

/**
 * ONE-WAY IS CHECKED FIRST, and the order is load-bearing.
 *
 * `webkit.messageHandlers[CHANNEL]` is NOT discriminating: it exists for a
 * reply-capable handler AND for a one-way one, because `webview_flutter`
 * implements its `JavaScriptChannel` on iOS as exactly that — a non-reply
 * WebKit handler plus an injected `window[CHANNEL]` shim that forwards to it.
 * Preferring it therefore mis-detects Flutter as reply-capable, `postMessage`
 * returns `undefined` instead of a promise, and every request silently becomes
 * a transport failure. (Observed on the simulator in wave 9: stores stalled with
 * `pending=1` forever while the shell logged zero requests served.)
 *
 * The `window[CHANNEL]` shim IS discriminating: a reply-capable host installs
 * only the WebKit handler and no such global. So its presence means one-way, and
 * its absence means we can trust the WebKit handler to return a promise.
 */
function detectTransport(): Transport | null {
  const w = globalThis as unknown as {
    webkit?: { messageHandlers?: Record<string, ReplyHandler | undefined> };
  } & Record<string, unknown>;
  const oneWay = w[BRIDGE_HTTP_CHANNEL] as OneWayChannel | undefined;
  if (oneWay && typeof oneWay.postMessage === "function") {
    return { kind: "one-way", channel: oneWay };
  }
  const replyCapable = w.webkit?.messageHandlers?.[BRIDGE_HTTP_CHANNEL];
  if (replyCapable && typeof replyCapable.postMessage === "function") {
    return { kind: "reply", handler: replyCapable };
  }
  return null;
}

/**
 * True when the host shell provides privileged HTTP by either transport. A
 * surface uses this to choose bridge transport over its dev transport; it must
 * never silently proceed unauthenticated when this is false.
 */
export function isBridgeHttpAvailable(): boolean {
  return detectTransport() !== null;
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

/** Pending one-way requests, keyed by correlation id. */
const pending = new Map<string, (raw: unknown) => void>();
let replyInstalled = false;

/**
 * Install the global a one-way shell calls to deliver a reply. Idempotent, and
 * deliberately forgiving: an unknown or duplicate id is DROPPED rather than
 * applied to some other request — a late reply must never resolve the wrong call.
 */
function installReplySink(): void {
  if (replyInstalled) return;
  replyInstalled = true;
  (globalThis as unknown as Record<string, unknown>)[BRIDGE_HTTP_REPLY_FUNCTION] = (
    id: unknown,
    replyJson: unknown,
  ): void => {
    if (typeof id !== "string") return;
    const settle = pending.get(id);
    if (!settle) return; // unknown or already-settled id
    pending.delete(id);
    if (typeof replyJson !== "string") {
      settle(undefined);
      return;
    }
    try {
      settle(JSON.parse(replyJson) as unknown);
    } catch {
      settle(undefined); // unparseable reply -> shell-error, via toHttpResponse
    }
  };
}

/**
 * Bind the `HttpClient` seam to the shell's privileged transport. Throws only
 * if the bridge is absent — call `isBridgeHttpAvailable()` first.
 *
 * `replyTimeoutMs` bounds the one-way wait only; it exists so a lost reply
 * degrades to a retryable transport failure instead of stalling the outbox.
 */
export function bridgeHttpClient(replyTimeoutMs: number = DEFAULT_REPLY_TIMEOUT_MS): HttpClient {
  const transport = detectTransport();
  if (!transport) {
    throw new Error(`bridge HTTP unavailable: no "${BRIDGE_HTTP_CHANNEL}" channel on this host`);
  }
  if (transport.kind === "one-way") installReplySink();

  return {
    async request(method: BridgeHttpMethod, path: string, body?: unknown): Promise<HttpResponse> {
      seq += 1;
      const id = `h${seq}`;
      let timer: ReturnType<typeof setTimeout> | undefined;
      try {
        // Serialization is part of the transport boundary. A circular value
        // (or BigInt) must become the same retryable shell-error as a channel
        // failure, never a rejected HttpClient promise that bypasses the
        // shared failure taxonomy.
        const message: BridgeHttpRequest = {
          id,
          method,
          path,
          ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
        };
        if (transport.kind === "reply") {
          return toHttpResponse(await transport.handler.postMessage(message));
        }
        const raw = await new Promise<unknown>((resolve) => {
          let done = false;
          const settle = (value: unknown): void => {
            if (done) return;
            done = true;
            if (timer !== undefined) {
              clearTimeout(timer);
              timer = undefined;
            }
            resolve(value);
          };
          pending.set(message.id, settle);
          // Keep this timer referenced: a lost reply must settle even when no
          // other work keeps the host event loop alive.
          timer = setTimeout(() => {
            pending.delete(message.id);
            settle(undefined); // no reply in time -> shell-error -> retryable
          }, replyTimeoutMs);
          transport.channel.postMessage(JSON.stringify(message));
        });
        return toHttpResponse(raw);
      } catch {
        // A throwing channel is a transport failure, not a server answer.
        pending.delete(id);
        if (timer !== undefined) {
          clearTimeout(timer);
          timer = undefined;
        }
        return { status: BRIDGE_HTTP_FAILURE_STATUS["shell-error"], json: null };
      }
    },
  };
}
