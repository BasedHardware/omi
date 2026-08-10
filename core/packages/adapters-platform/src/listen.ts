/**
 * Platform-generation Listen transport — the network-owning half of the
 * ratified `/v4/listen` seam.
 *
 * The decoder/accumulator in `@omi-core/wire-listen` stays pure. This module
 * owns WebSocket construction, reconnect scheduling, and the stable
 * `client_conversation_id` that must survive every reconnect of one logical
 * capture. The surface package maps this evidence onto its closed capture
 * vocabulary; keeping that mapping there avoids an adapters -> surfaces
 * dependency cycle.
 *
 * Authentication stays with the host. The client passes a relative canonical
 * path to `openSocket`; a native host can attach credentials without exposing
 * them to JavaScript, while the browser binding below resolves the same path
 * against its current origin.
 */

import type { Env } from "@omi-core/kernel";
import {
  createListenCaptureStreamPort,
  type ListenCaptureStreamPort,
  type ListenEntitlementGeneration,
  type SchemaDocument,
} from "@omi-core/wire-listen";

export const PLATFORM_LISTEN_PATH = "/v4/listen";

export type PlatformListenSocketMessageEvent = { readonly data: unknown };
export type PlatformListenSocketCloseEvent = { readonly code: number };

/** Narrow structural WebSocket surface so this package remains host-neutral. */
export interface PlatformListenSocket {
  addEventListener(type: "open", listener: () => void): void;
  addEventListener(type: "message", listener: (event: PlatformListenSocketMessageEvent) => void): void;
  addEventListener(type: "close", listener: (event: PlatformListenSocketCloseEvent) => void): void;
  addEventListener(type: "error", listener: () => void): void;
  close(code?: number, reason?: string): void;
}

export type PlatformListenSocketFactory = (path: string) => PlatformListenSocket;

export interface PlatformListenWebSocketConstructor {
  new(url: string): PlatformListenSocket;
}

/**
 * Browser transport for a same-origin platform service or authenticated host
 * proxy. No token, backend base URL, or first-frame auth enters this binding.
 */
export function createPlatformListenBrowserSocketFactory(
  origin: string,
  WebSocketClass: PlatformListenWebSocketConstructor,
): PlatformListenSocketFactory {
  const withoutTrailingSlash = origin.replace(/\/+$/, "");
  const socketOrigin = withoutTrailingSlash.startsWith("https://")
    ? `wss://${withoutTrailingSlash.slice("https://".length)}`
    : withoutTrailingSlash.startsWith("http://")
      ? `ws://${withoutTrailingSlash.slice("http://".length)}`
      : withoutTrailingSlash.startsWith("ws://") || withoutTrailingSlash.startsWith("wss://")
        ? withoutTrailingSlash
        : null;
  if (socketOrigin === null) {
    throw new Error("Listen WebSocket origin must use http(s) or ws(s)");
  }
  return (path) => {
    if (!path.startsWith("/")) throw new Error("Listen WebSocket path must be origin-relative");
    return new WebSocketClass(`${socketOrigin}${path}`);
  };
}

export type PlatformListenTransportPhase =
  | "idle"
  | "connecting"
  | "active"
  | "reconnecting"
  | "failed";

export interface PlatformListenTransportSnapshot {
  readonly phase: PlatformListenTransportPhase;
  readonly captureRequested: boolean;
  readonly startedAt: number | null;
  readonly disconnectedAt: number | null;
  readonly failureRetryable: boolean | null;
}

export interface PlatformListenCaptureClient {
  snapshot(): PlatformListenTransportSnapshot;
  stream(): ListenCaptureStreamPort;
  subscribe(listener: () => void): () => void;
  refresh(): Promise<void>;
  start(): Promise<void>;
  stop(): Promise<void>;
}

export interface PlatformListenHandshake {
  readonly language?: string;
  readonly sampleRate?: number;
  readonly codec?: string;
  readonly channels?: number;
  readonly source?: string;
}

export interface PlatformListenCaptureClientOptions {
  readonly env: Env;
  readonly schema: SchemaDocument;
  readonly openSocket: PlatformListenSocketFactory;
  readonly path?: string;
  readonly handshake?: PlatformListenHandshake;
  readonly generation?: ListenEntitlementGeneration;
  readonly reconnectDelayMs?: number;
}

function uuidFromEnv(env: Env): string {
  const bytes = Array.from({ length: 16 }, () => Math.floor(env.random() * 256) & 0xff);
  bytes[6] = (bytes[6]! & 0x0f) | 0x40;
  bytes[8] = (bytes[8]! & 0x3f) | 0x80;
  const hex = bytes.map((byte) => byte.toString(16).padStart(2, "0"));
  return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
}

function listenPath(
  path: string,
  handshake: PlatformListenHandshake,
  clientConversationId: string,
): string {
  const param = (key: string, value: string | number): string =>
    `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`;
  const params = [
    param("language", handshake.language?.trim() || "en"),
    param("sample_rate", handshake.sampleRate ?? 16_000),
    param("codec", handshake.codec?.trim() || "pcm16"),
    param("channels", handshake.channels ?? 1),
    ...(handshake.source?.trim() ? [param("source", handshake.source.trim())] : []),
    param("client_conversation_id", clientConversationId),
  ];
  return `${path}?${params.join("&")}`;
}

/**
 * One logical capture client. Reconnects preserve both the typed port and the
 * resume id; a new explicit start creates both anew.
 */
export function createPlatformListenCaptureClient(
  options: PlatformListenCaptureClientOptions,
): PlatformListenCaptureClient {
  const listeners = new Set<() => void>();
  const reconnectDelayMs = options.reconnectDelayMs ?? 1_000;
  const handshake = options.handshake ?? {};
  let handle = createListenCaptureStreamPort({
    sink: options.env.fallbackSink,
    env: options.env,
    schema: options.schema,
    generation: options.generation ?? "platform",
  });
  let unobserve: readonly (() => void)[] = [];
  let socket: PlatformListenSocket | null = null;
  let socketGeneration = 0;
  let cancelReconnect: (() => void) | null = null;
  let captureRequested = false;
  let phase: PlatformListenTransportPhase = "idle";
  let startedAt: number | null = null;
  let disconnectedAt: number | null = null;
  let failureRetryable: boolean | null = null;
  let clientConversationId: string | null = null;
  let terminalCeiling = false;

  const notify = (): void => {
    for (const listener of listeners) listener();
  };

  const observeHandle = (): void => {
    for (const unsubscribe of unobserve) unsubscribe();
    unobserve = [
      handle.port.subscribeTranscriptSegments(notify),
      handle.port.observeConnectionState(notify),
      handle.port.observeEntitlementState(notify),
      handle.port.observeListenCaptureDegradation(notify),
    ];
  };
  observeHandle();

  const scheduleReconnect = (): void => {
    if (!captureRequested || terminalCeiling || cancelReconnect !== null) return;
    phase = "reconnecting";
    cancelReconnect = options.env.delay(reconnectDelayMs, () => {
      cancelReconnect = null;
      if (captureRequested && socket === null) connect(true);
    });
    notify();
  };

  const connect = (reconnecting: boolean): void => {
    if (!captureRequested || terminalCeiling || socket !== null || clientConversationId === null) return;
    const currentGeneration = ++socketGeneration;
    phase = reconnecting ? "reconnecting" : "connecting";
    failureRetryable = null;
    notify();

    let opened: PlatformListenSocket;
    try {
      opened = options.openSocket(
        listenPath(options.path ?? PLATFORM_LISTEN_PATH, handshake, clientConversationId),
      );
    } catch (error) {
      phase = "failed";
      failureRetryable = true;
      disconnectedAt = options.env.now();
      notify();
      scheduleReconnect();
      throw error;
    }
    socket = opened;

    opened.addEventListener("open", () => {
      if (currentGeneration !== socketGeneration || socket !== opened || !captureRequested) return;
      if (handle.port.getConnectionState().status === "closed") handle.ingest.acceptReconnect();
      phase = "active";
      failureRetryable = null;
      disconnectedAt = null;
      notify();
    });
    opened.addEventListener("message", (event) => {
      if (currentGeneration !== socketGeneration || socket !== opened || !captureRequested) return;
      if (typeof event.data !== "string") return;
      handle.ingest.acceptTextFrame(event.data);
      phase = "active";
      failureRetryable = null;
      const entitlement = handle.port.getEntitlementState();
      if (
        entitlement !== null
        && !entitlement.captureContinuing
        && (entitlement.status === "limit_reached" || entitlement.status === "upgrade_required")
      ) {
        terminalCeiling = true;
        phase = "failed";
        failureRetryable = false;
        socketGeneration += 1;
        socket = null;
        opened.close(1000, "capture stopped at entitlement ceiling");
      }
      notify();
    });
    opened.addEventListener("error", () => {
      if (currentGeneration !== socketGeneration || socket !== opened || !captureRequested) return;
      failureRetryable = true;
      notify();
    });
    opened.addEventListener("close", (event) => {
      if (currentGeneration !== socketGeneration || socket !== opened) return;
      socket = null;
      handle.ingest.acceptClose(event.code);
      if (!captureRequested) {
        phase = "idle";
        failureRetryable = null;
        disconnectedAt = null;
        notify();
        return;
      }
      disconnectedAt = options.env.now();
      const advice = handle.port.getListenCaptureCloseAdvice();
      if (advice?.entitlementExhaustion) {
        terminalCeiling = true;
        phase = "failed";
        failureRetryable = false;
        notify();
        return;
      }
      if (advice?.clientShouldRetry ?? true) {
        failureRetryable = true;
        scheduleReconnect();
        return;
      }
      phase = "failed";
      failureRetryable = false;
      notify();
    });
  };

  return {
    snapshot: () => ({
      phase,
      captureRequested,
      startedAt,
      disconnectedAt,
      failureRetryable,
    }),
    stream: () => handle.port,
    subscribe(listener) {
      listeners.add(listener);
      return () => void listeners.delete(listener);
    },
    async refresh() {
      if (captureRequested && !terminalCeiling && socket === null && cancelReconnect === null) connect(true);
      notify();
    },
    async start() {
      if (captureRequested) throw new Error("Listen capture is already running");
      for (const unsubscribe of unobserve) unsubscribe();
      handle = createListenCaptureStreamPort({
        sink: options.env.fallbackSink,
        env: options.env,
        schema: options.schema,
        generation: options.generation ?? "platform",
      });
      observeHandle();
      captureRequested = true;
      startedAt = options.env.now();
      disconnectedAt = null;
      failureRetryable = null;
      terminalCeiling = false;
      clientConversationId = uuidFromEnv(options.env);
      connect(false);
    },
    async stop() {
      if (!captureRequested) throw new Error("Listen capture is not running");
      captureRequested = false;
      cancelReconnect?.();
      cancelReconnect = null;
      socketGeneration += 1;
      const closing = socket;
      socket = null;
      phase = "idle";
      startedAt = null;
      disconnectedAt = null;
      failureRetryable = null;
      terminalCeiling = false;
      clientConversationId = null;
      closing?.close(1000, "capture stopped by user");
      notify();
    },
  };
}
