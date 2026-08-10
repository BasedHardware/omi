// domain-pending(DIV-DOMCORE-012)
// domain-pending(UNK-DOMAPPS-001)

import { randomUUID } from "node:crypto";
import type { Hono } from "hono";
import { upgradeWebSocket } from "hono/bun";
import type { WSContext, WSEvents } from "hono/ws";

import type { DevPrincipal } from "../auth/dev-token";
import type {
  SettingsEntitlementProjection,
  SettingsProjectionStore,
} from "../control/settings-projection";
import type { ListenConversationFinalizer } from "../listen/conversation-finalizer";
import type {
  TranscriptionEmission,
  TranscriptionSource,
} from "../listen/transcription-source";
import type {
  ListenSessionRecord,
  ListenStore,
  ListenTranscriptSegment,
} from "../stores/listen-store";
import type { ListenSegmentUnitOfWork } from "../stores/listen-segment-unit-of-work";

export const LISTEN_PATH = "/v4/listen";
export const LISTEN_RESERVED_CLOSE_ENTITLEMENT_EXHAUSTION = 4020;

const JSON_HEADERS = Object.freeze({
  "cache-control": "no-store",
  "content-type": "application/json",
});
const SUPPORTED_CODECS = new Set(["pcm8", "pcm16", "linear16", "opus", "aac", "lc3"]);
const HANDSHAKE_KEYS = new Set([
  "language",
  "sample_rate",
  "codec",
  "channels",
  "include_speech_profile",
  "stt_service",
  "conversation_timeout",
  "source",
  "custom_stt",
  "onboarding",
  "speaker_auto_assign",
  "create_speakers",
  "vad_gate",
  "call_id",
  "client_conversation_id",
]);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

interface ListenHandshake {
  readonly codec: string;
  readonly sampleRate: number;
  readonly channels: number;
  readonly source: string | null;
  readonly clientConversationId: string | null;
}

export interface EntitlementFrame {
  readonly type: "entitlement";
  readonly state: "transcription_paused_capture_continuing" | "limit_reached" | "upgrade_required";
  readonly reason: "free_tier_transcription_limit";
  readonly usage: { readonly amount: number; readonly unit: "seconds" };
  readonly limit:
    | { readonly kind: "metered"; readonly amount: number; readonly unit: "seconds" }
    | { readonly kind: "unmetered" };
  readonly upgrade_target: string;
}

export interface ListenRouteDependencies {
  readonly resolvePrincipal: (token: string) => DevPrincipal | null;
  /** Read and consumed-usage write are the same Settings/fence projection. */
  readonly entitlement: SettingsProjectionStore;
  readonly store: ListenStore;
  readonly segments: ListenSegmentUnitOfWork;
  readonly transcription: TranscriptionSource;
  readonly conversations: ListenConversationFinalizer;
  readonly now: () => string;
  readonly createId?: () => string;
}

const response = (body: Readonly<Record<string, string>>, status: number): Response =>
  new Response(JSON.stringify(body), { status, headers: JSON_HEADERS });

const bearerToken = (header: string | undefined): string | null => {
  if (typeof header !== "string" || !header.startsWith("Bearer ")) return null;
  const token = header.slice("Bearer ".length);
  return token.length === 0 ? null : token;
};

const integerParam = (value: string | null, fallback: number): number | null => {
  if (value === null) return fallback;
  if (!/^-?[0-9]+$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) ? parsed : null;
};

const parseHandshake = (url: URL): ListenHandshake | null => {
  for (const key of url.searchParams.keys()) {
    if (!HANDSHAKE_KEYS.has(key)) return null;
  }
  const codec = url.searchParams.get("codec") ?? "pcm8";
  const sampleRate = integerParam(url.searchParams.get("sample_rate"), 8_000);
  const channels = integerParam(url.searchParams.get("channels"), 1);
  const clientConversationId = url.searchParams.get("client_conversation_id");
  if (!SUPPORTED_CODECS.has(codec) || sampleRate === null || sampleRate <= 0
    || channels === null || channels < 1
    || (clientConversationId !== null && !UUID.test(clientConversationId))) {
    return null;
  }
  return Object.freeze({
    codec,
    sampleRate,
    channels,
    source: url.searchParams.get("source"),
    clientConversationId,
  });
};

export const createEntitlementFrame = (
  projection: SettingsEntitlementProjection,
  state: EntitlementFrame["state"] = "upgrade_required",
): EntitlementFrame => Object.freeze({
  type: "entitlement",
  state,
  reason: "free_tier_transcription_limit",
  usage: Object.freeze({ amount: projection.used, unit: "seconds" }),
  limit: projection.limit === null
    ? Object.freeze({ kind: "unmetered" })
    : Object.freeze({ kind: "metered", amount: projection.limit, unit: "seconds" }),
  // Opaque shell routing identifier, deliberately not a URL.
  upgrade_target: "plan_upgrade",
});

const sendJson = (socket: WSContext, frame: unknown): void => {
  socket.send(JSON.stringify(frame));
};

const rawSocketIsOpen = (socket: WSContext): boolean => {
  const raw = socket.raw as { readonly readyState?: number } | undefined;
  return raw?.readyState === 1;
};

const transcriptBatch = (
  segments: readonly ListenTranscriptSegment[],
): readonly ListenTranscriptSegment[] => Object.freeze([...segments]);

const serviceStatus = (status: string) => Object.freeze({ type: "service_status", status });

const eventsForRejectedFormat = (): WSEvents => ({
  onOpen(_event, socket) {
    socket.close(1003, "unsupported_audio_format");
  },
});

const eventsForExhaustedEntitlement = (
  projection: SettingsEntitlementProjection,
): WSEvents => ({
  onOpen(_event, socket) {
    sendJson(socket, createEntitlementFrame(projection));
    socket.close(LISTEN_RESERVED_CLOSE_ENTITLEMENT_EXHAUSTION, "entitlement_exhausted");
  },
});

const eventsForSession = (
  deps: ListenRouteDependencies,
  principal: DevPrincipal,
  session: ListenSessionRecord,
  pendingSegments: readonly ListenTranscriptSegment[],
  handshake: ListenHandshake,
): WSEvents => {
  let socket: WSContext | null = null;
  let terminal = false;
  let processing = Promise.resolve();

  const finalize = (status: "completed" | "entitlement_exhausted", locked: boolean): void => {
    if (terminal) return;
    terminal = true;
    const closed = deps.store.closeSession(principal.uid, session.id, status, deps.now());
    if (closed !== null) deps.conversations.finalize({ accountId: principal.uid, session: closed, locked });
  };

  const fail = (): void => {
    if (terminal) return;
    terminal = true;
    const activeSocket = socket;
    if (activeSocket !== null && rawSocketIsOpen(activeSocket)) {
      sendJson(activeSocket, Object.freeze({
        type: "service_status",
        status: "stt_failed",
        retryable: true,
      }));
      activeSocket.close(1011, "stt_failed");
    }
  };

  const handleEmission = async (emission: TranscriptionEmission): Promise<void> => {
    if (terminal) return;
    const reservation = await deps.segments.reserve({
      accountId: principal.uid,
      sessionId: session.id,
      segment: emission.segment,
      consumedSeconds: emission.consumedSeconds,
      at: deps.now(),
    });
    const appended = reservation;
    const projection = reservation.entitlement;

    const activeSocket = socket;
    if (activeSocket !== null && rawSocketIsOpen(activeSocket)) {
      sendJson(activeSocket, transcriptBatch([appended.segment]));
      deps.store.markDelivered(principal.uid, session.id, [appended.segment.id]);
    }

    if (projection?.limitReached === true) {
      if (activeSocket !== null && rawSocketIsOpen(activeSocket)) {
        sendJson(activeSocket, createEntitlementFrame(projection));
      }
      finalize("entitlement_exhausted", true);
      if (activeSocket !== null && rawSocketIsOpen(activeSocket)) {
        activeSocket.close(
          LISTEN_RESERVED_CLOSE_ENTITLEMENT_EXHAUSTION,
          "entitlement_exhausted",
        );
      }
    }
  };

  const transcription = deps.transcription.connect({
    sessionId: session.id,
    sampleRate: handshake.sampleRate,
    codec: handshake.codec,
    channels: handshake.channels,
    onEmission(emission) {
      processing = processing.then(() => handleEmission(emission)).catch(() => fail());
    },
    onError: fail,
  });

  return {
    onOpen(_event, openedSocket) {
      socket = openedSocket;
      sendJson(openedSocket, serviceStatus("initiating"));
      sendJson(openedSocket, serviceStatus("in_progress_conversations_processing"));
      sendJson(openedSocket, Object.freeze({
        type: "conversation_session",
        conversation_id: session.conversationId,
        recording_session_id: session.id,
      }));
      sendJson(openedSocket, serviceStatus("stt_initiating"));
      sendJson(openedSocket, serviceStatus("ready"));
      if (pendingSegments.length > 0) {
        sendJson(openedSocket, transcriptBatch(pendingSegments));
        deps.store.markDelivered(
          principal.uid,
          session.id,
          pendingSegments.map((segment) => segment.id),
        );
      }
    },

    onMessage(event) {
      if (terminal || typeof event.data === "string") return;
      if (event.data instanceof Blob) {
        void event.data.arrayBuffer().then((data) => transcription.writeAudio(new Uint8Array(data)));
        return;
      }
      transcription.writeAudio(new Uint8Array(event.data as ArrayBufferLike));
    },

    onClose(event) {
      transcription.finish();
      socket = null;
      if (event.code === LISTEN_RESERVED_CLOSE_ENTITLEMENT_EXHAUSTION) {
        finalize("entitlement_exhausted", true);
      } else if (event.code === 1000) {
        finalize("completed", false);
      } else if (!terminal) {
        deps.store.closeSession(principal.uid, session.id, "interrupted", deps.now());
      }
    },

    onError() {
      fail();
    },
  };
};

/** Registers the authenticated native WebSocket handshake at the ratified path. */
export const registerListenRoutes = (app: Hono, deps: ListenRouteDependencies): void => {
  app.get(LISTEN_PATH, async (context) => {
    const token = bearerToken(context.req.header("authorization"));
    const principal = token === null ? null : deps.resolvePrincipal(token);
    if (principal === null) return response({ error: "unauthorized" }, 401);
    if (context.req.header("upgrade")?.toLowerCase() !== "websocket") {
      return response({ error: "upgrade_required" }, 426);
    }

    const handshake = parseHandshake(new URL(context.req.url));
    if (handshake === null) {
      return upgradeWebSocket(context, eventsForRejectedFormat());
    }

    const entitlement = deps.entitlement.readEntitlement(principal.uid);
    if (entitlement?.limitReached === true) {
      return upgradeWebSocket(context, eventsForExhaustedEntitlement(entitlement));
    }

    const id = handshake.clientConversationId ?? (deps.createId ?? randomUUID)();
    const opened = deps.store.openOrResume({
      accountId: principal.uid,
      id,
      conversationId: id,
      clientConversationId: handshake.clientConversationId,
      at: deps.now(),
      source: handshake.source,
      codec: handshake.codec,
      sampleRate: handshake.sampleRate,
      channels: handshake.channels,
    });
    return upgradeWebSocket(context, eventsForSession(
      deps,
      principal,
      opened.session,
      opened.pendingSegments,
      handshake,
    ));
  });
};
