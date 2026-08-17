// GENERATED FILE — DO NOT EDIT.
// Source: core/contracts/wire/listen/listen-protocol.schema.json
// Generator: packages/wire-listen/scripts/generate.mjs
// Protocol baseline: e0893286f94ecc75aacb4cbc441f653f347e382b
// Schema version: 0.3.0
// Ported from prototypes/listen-schema/codegen/generate.mjs

import type { FallbackSink, MaybeDegraded } from "@omi-core/contracts";
import { degrade } from "@omi-core/kernel";

export interface Translation {
  "lang": string;
  "text": string;
}

/** Producer: omi:backend/models/transcript_segment.py:26 */
export interface TranscriptSegment {
  "id"?: string | null;
  "text": string;
  "speaker"?: string | null;
  "speaker_id"?: number | null;
  "is_user": boolean;
  "person_id"?: string | null;
  "start": number;
  "end": number;
  "translations"?: Translation[];
  "speech_profile_processed"?: boolean;
  "stt_provider"?: string | null;
}

/** Consumed quantity for the entitlement decision. Always a real non-negative amount — never overloaded to encode 'unlimited'. */
export interface EntitlementUsage {
  "amount": number;
  "unit": "seconds";
}

export interface EntitlementMeteredLimit {
  "kind": "metered";
  "amount": number;
  "unit": "seconds";
}

/** Paid / unlimited plans. Explicit kind — NEVER encode unlimited as amount=-1 or 0. */
export interface EntitlementUnmeteredLimit {
  "kind": "unmetered";
}

/** Server could not determine a numeric ceiling (partial entitlement data). Distinct from unmetered. */
export interface EntitlementUnknownLimit {
  "kind": "unknown";
}

/** Closed tagged union for the ceiling opposite usage.amount. Sentinel numbers are forbidden. */
export type EntitlementLimit = EntitlementMeteredLimit | EntitlementUnmeteredLimit | EntitlementUnknownLimit;

// ---------------------------------------------------------- server -> client

/** Producer: omi:backend/routers/transcribe.py:195,204 */
export interface AuthResponseFrame {
  "type": "auth_response";
  "success": boolean;
}

/** Lifecycle status pushes during bootstrap plus the terminal stt_failed status immediately before an STT-triggered 1011 close. Serialized with exclude_none, so absent optional keys are normal, not a schema violation. */
/** Producer: omi:backend/models/message_event.py:92 */
export interface ServiceStatusEvent {
  "type": "service_status";
  "status": "initiating" | "in_progress_conversations_processing" | "stt_initiating" | "ready" | "stt_failed" | (string & {});
  "status_text"?: string | null;
  "outcome"?: string | null;
  "provider"?: string | null;
  "retryable"?: boolean | null;
  "reason"?: string | null;
}

/** Producer: omi:backend/models/message_event.py:110 */
export interface ConversationSessionEvent {
  "type": "conversation_session";
  "conversation_id": string;
  "status"?: string;
  "recording_session_id"?: string | null;
  "lifecycle_version"?: number | null;
  "lifecycle_phase"?: string | null;
  "lifecycle_sequence"?: number | null;
}

/** Declared by PingEvent but never sent: the real heartbeat is the bare text frame "ping". Kept in the canonical enum so the string stays claimed; see REPORT.md open question 1 for the requirements-note tension (counted among the 16, also listed among the 5 unemitted classes to exclude). */
/** Producer: omi:backend/models/message_event.py:125 */
export interface PingEvent {
  "type": "ping";
}

/** Producer: omi:backend/models/message_event.py:136 */
export interface LastConversationEvent {
  "type": "last_memory";
  "memory_id": string;
}

/** Producer: omi:backend/models/message_event.py:147 */
export interface TranslationEvent {
  "type": "translating";
  "segments": TranscriptSegment[];
}

/** Producer: omi:backend/models/message_event.py:158 */
export interface PhotoProcessingEvent {
  "type": "photo_processing";
  "temp_id": string;
  "photo_id": string;
}

/** Producer: omi:backend/models/message_event.py:170 */
export interface PhotoDescribedEvent {
  "type": "photo_described";
  "photo_id": string;
  "description": string;
  "discarded": boolean;
}

/** Producer: omi:backend/models/message_event.py:183 */
export interface SpeakerLabelSuggestionEvent {
  "type": "speaker_label_suggestion";
  "speaker_id": number;
  "person_id": string;
  "person_name": string;
  "segment_id": string;
}

/** Latched: sent at most once per session, when remaining credit drops to/below 180s, or pre-emptively at connect when already exhausted/paywalled (remaining_seconds 0, immediately before a 1008 trial_expired close). */
/** Producer: omi:backend/models/message_event.py:197 */
export interface FreemiumThresholdReachedEvent {
  "type": "freemium_threshold_reached";
  "remaining_seconds": number;
  "action": "setup_on_device_stt" | "none" | (string & {});
}

/** Producer: omi:backend/models/message_event.py:209 */
export interface SegmentsDeletedEvent {
  "type": "segments_deleted";
  "segment_ids": string[];
}

/** Finalization completed. event_type is caller-supplied on ConversationEvent, so the string exists only at the call site, not on any model class. */
/** Producer: omi:backend/routers/listen/conversations.py:88 */
export interface ConversationCreatedEvent {
  "type": "memory_created";
  "memory": Record<string, unknown>;
  "messages"?: Record<string, unknown>[] | null;
  "recording_session_id"?: string | null;
  "conversation_id"?: string | null;
  "lifecycle_version"?: number | null;
  "lifecycle_phase"?: "completed";
  "lifecycle_sequence"?: number | null;
}

/** Producer: omi:backend/routers/listen/conversations.py:88 */
export interface ConversationProcessingStartedEvent {
  "type": "memory_processing_started";
  "memory": Record<string, unknown>;
  "messages"?: Record<string, unknown>[] | null;
  "recording_session_id"?: string | null;
  "conversation_id"?: string | null;
  "lifecycle_version"?: number | null;
  "lifecycle_phase"?: "processing";
  "lifecycle_sequence"?: number | null;
}

/** Producer: omi:backend/utils/onboarding.py:246 */
export interface OnboardingQuestionEvent {
  "type": "onboarding_question";
  "question": string;
  "question_index": number;
  "total_questions": number;
  "question_segment_id"?: string | null;
}

/** Producer: omi:backend/utils/onboarding.py:194 */
export interface OnboardingQuestionAnsweredEvent {
  "type": "question_answered";
  "question_index": number;
  "answered": boolean;
}

/** Producer: omi:backend/utils/onboarding.py:149 */
export interface OnboardingQuestionSkippedEvent {
  "type": "question_skipped";
  "question_index": number;
}

/** Producer: omi:backend/utils/onboarding.py:266 */
export interface OnboardingCompleteEvent {
  "type": "onboarding_complete";
  "answers_count": number;
}

/** Unified entitlement payload on the /listen wire (WS-003 gate / WS-005). Reserved, not emitted at baseline. Distinguishes deferred-transcription (state=transcription_paused_capture_continuing) from entitlement-forced session close (code 4020). */
/** Producer: docs/backend-handoff-requirements.md#entitlements */
export interface EntitlementEvent {
  "type": "entitlement";
  "state": "transcription_paused_capture_continuing" | "limit_reached" | "upgrade_required";
  "reason": "free_tier_transcription_limit" | "free_tier_chat_limit" | "trial_expired" | "paywalled";
  "usage": EntitlementUsage;
  "limit": EntitlementLimit;
  "upgrade_target": string;
}

export type ListenServerEvent =
  | AuthResponseFrame
  | ServiceStatusEvent
  | ConversationSessionEvent
  | PingEvent
  | LastConversationEvent
  | TranslationEvent
  | PhotoProcessingEvent
  | PhotoDescribedEvent
  | SpeakerLabelSuggestionEvent
  | FreemiumThresholdReachedEvent
  | SegmentsDeletedEvent
  | ConversationCreatedEvent
  | ConversationProcessingStartedEvent
  | OnboardingQuestionEvent
  | OnboardingQuestionAnsweredEvent
  | OnboardingQuestionSkippedEvent
  | OnboardingCompleteEvent
  | EntitlementEvent;

// ---------------------------------------------------------- client -> server

/** Handled by the route before the session starts, so it is NOT one of the 4 session-scoped client message types. On the native path any such frame is ignored. */
/** Producer: omi:backend/routers/transcribe.py:190 */
export interface ClientAuthMessage {
  "type": "auth";
  "token": string;
}

/** Chunked base64 image upload, reassembled server-side and fed to an image describer. A malformed payload closes the socket with 1008. */
/** Producer: omi:backend/routers/listen/receiver.py:418 */
export interface ClientImageChunkMessage {
  "type": "image_chunk";
  "id": string;
  "index": number;
  "total": number;
  "data": string;
}

/** Onboarding flow control. Ignored unless an onboarding handler exists and is incomplete. */
/** Producer: omi:backend/routers/listen/receiver.py:424 */
export interface ClientSkipQuestionMessage {
  "type": "skip_question";
}

/** Custom-STT clients push their own segments; the server incorporates them instead of producing its own. Ignored unless custom_stt=enabled. */
/** Producer: omi:backend/routers/listen/receiver.py:426 */
export interface ClientSuggestedTranscriptMessage {
  "type": "suggested_transcript";
  "segments": TranscriptSegment[];
  "stt_provider"?: string | null;
}

/** Producer: omi:backend/routers/listen/receiver.py:432 */
export interface ClientSpeakerAssignedMessage {
  "type": "speaker_assigned";
  "speaker_id": number;
  "person_id": string;
  "person_name"?: string | null;
  "segment_ids"?: string[];
}

export type ListenClientMessage =
  | ClientAuthMessage
  | ClientImageChunkMessage
  | ClientSkipQuestionMessage
  | ClientSuggestedTranscriptMessage
  | ClientSpeakerAssignedMessage;

// ------------------------------------------------------------------ constants

/** Canonical server->client event enum (16 values). */
export const LISTEN_SERVER_EVENT_TYPES = [
  "service_status",
  "conversation_session",
  "ping",
  "last_memory",
  "translating",
  "photo_processing",
  "photo_described",
  "speaker_label_suggestion",
  "freemium_threshold_reached",
  "segments_deleted",
  "memory_created",
  "memory_processing_started",
  "onboarding_question",
  "question_answered",
  "question_skipped",
  "onboarding_complete"
] as const;

/** Session-scoped client->server message enum (4 values; the web-path `auth` frame is handshake-only and not counted). */
export const LISTEN_CLIENT_MESSAGE_TYPES = [
  "image_chunk",
  "skip_question",
  "suggested_transcript",
  "speaker_assigned"
] as const;

/** Types the schema claims but the baseline server never sends (or reserves for a future producer). */
export const LISTEN_RESERVED_UNEMITTED_TYPES = [
  "ping",
  "entitlement"
] as const;

export interface ListenCloseCodeInfo {
  readonly code: number;
  readonly name: string;
  readonly emittedByListen: boolean;
  readonly clientShouldRetry: boolean;
  readonly meaning: string;
}

export const LISTEN_CLOSE_CODES: Readonly<Record<number, ListenCloseCodeInfo>> = {
  "1000": {
    "code": 1000,
    "name": "normal",
    "emittedByListen": true,
    "clientShouldRetry": true,
    "meaning": "Client-initiated close, or the server echoing the ASGI disconnect frame's own code verbatim. Drives clean desktop finalization."
  },
  "1001": {
    "code": 1001,
    "name": "going_away",
    "emittedByListen": true,
    "clientShouldRetry": true,
    "meaning": "Default close code. Heartbeat-detected staleness (no inbound activity for 90s), or the fallback at teardown when nothing overrode it (including after the 300s ws_receive_timeout silently breaks the receive loop)."
  },
  "1003": {
    "code": 1003,
    "name": "unsupported_audio_format",
    "emittedByListen": true,
    "clientShouldRetry": false,
    "meaning": "Bad codec/sample_rate combination, rejected at admission after accept."
  },
  "1008": {
    "code": 1008,
    "name": "policy_violation",
    "emittedByListen": true,
    "clientShouldRetry": false,
    "meaning": "Missing uid, trial expired/paywalled, unknown user, unsupported language, malformed image_chunk payload, or web-path auth timeout/failure."
  },
  "1011": {
    "code": 1011,
    "name": "internal_error",
    "emittedByListen": true,
    "clientShouldRetry": true,
    "meaning": "STT provider init failure, detected upstream STT death (~1s poll), or an unhandled exception in the receive loop. Always preceded by service_status{status:\"stt_failed\"} (INV-LISTEN-003)."
  },
  "4001": {
    "code": 4001,
    "name": "refresh_token",
    "emittedByListen": false,
    "clientShouldRetry": false,
    "meaning": "Documented in spec section 2.5 as an auth-refinement code, but NOT emitted anywhere in /listen at baseline (UNK-LISTEN-007 requirement 4). Retained here as reserved so no future code reuses the number."
  },
  "4004": {
    "code": 4004,
    "name": "force_relogin",
    "emittedByListen": false,
    "clientShouldRetry": false,
    "meaning": "As 4001 — reserved, not emitted by /listen at baseline."
  },
  "4020": {
    "code": 4020,
    "name": "entitlement_upgrade_required",
    "emittedByListen": false,
    "clientShouldRetry": false,
    "meaning": "RESERVED (WS-005 / entitlements contract): WebSocket closed for entitlement exhaustion / upgrade-required. DISTINCT from the mid-session entitlement frame with state=transcription_paused_capture_continuing (transcription paused, capture continuing — socket stays open). A preceding entitlement event carries upgrade advice. Number 4020 avoids collision with reserved-but-dead 4001/4004. Server emit is not implemented at baseline."
  }
};

/** Retry advice for a close code, fail-open: unknown codes are treated as retryable. */
export function shouldRetryAfterClose(code: number): boolean {
  const info = LISTEN_CLOSE_CODES[code];
  return info ? info.clientShouldRetry : true;
}

export const LISTEN_HANDSHAKES = [
  {
    "id": "native",
    "path": "/v4/listen",
    "authMechanism": "dependency",
    "params": [
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
      "client_conversation_id"
    ]
  },
  {
    "id": "web",
    "path": "/v4/web/listen",
    "authMechanism": "first-frame",
    "params": [
      "language",
      "sample_rate",
      "codec",
      "channels",
      "include_speech_profile",
      "conversation_timeout",
      "source",
      "custom_stt",
      "onboarding",
      "call_id",
      "client_conversation_id"
    ]
  }
] as const;

/** Canonical handshake params with server defaults — the single home the two route signatures should derive from. */
export const LISTEN_HANDSHAKE_PARAM_DEFAULTS = {
  "language": "en",
  "sample_rate": 8000,
  "codec": "pcm8",
  "channels": 1,
  "include_speech_profile": true,
  "stt_service": null,
  "conversation_timeout": 120,
  "source": null,
  "custom_stt": "disabled",
  "onboarding": "disabled",
  "speaker_auto_assign": "disabled",
  "create_speakers": true,
  "vad_gate": "",
  "call_id": null,
  "client_conversation_id": null
} as const;

// -------------------------------------------------------------------- decoding

export const LISTEN_HEARTBEAT_TEXT = "ping";

export type DecodedListenFrame =
  | { kind: "event"; event: ListenServerEvent }
  | { kind: "transcript_batch"; segments: TranscriptSegment[] }
  | { kind: "heartbeat" }
  | { kind: "unknown_event"; type: string; raw: Record<string, unknown> }
  | { kind: "invalid"; reason: InvalidFrameReason; raw: unknown };

export type InvalidFrameReason =
  | "not_json"
  | "empty"
  | "no_type_field"
  | "missing_required_fields"
  | "not_an_object";

function hasAll(obj: Record<string, unknown>, keys: readonly string[]): boolean {
  for (const key of keys) if (!(key in obj)) return false;
  return true;
}

/** Required non-discriminator keys per event type. A known type missing these decodes to `invalid`,
 * never to a half-built object. */
const REQUIRED_KEYS: Readonly<Record<string, readonly string[]>> = {
  "auth_response": [
    "success"
  ],
  "service_status": [
    "status"
  ],
  "conversation_session": [
    "conversation_id"
  ],
  "ping": [],
  "last_memory": [
    "memory_id"
  ],
  "translating": [
    "segments"
  ],
  "photo_processing": [
    "temp_id",
    "photo_id"
  ],
  "photo_described": [
    "photo_id",
    "description",
    "discarded"
  ],
  "speaker_label_suggestion": [
    "speaker_id",
    "person_id",
    "person_name",
    "segment_id"
  ],
  "freemium_threshold_reached": [
    "remaining_seconds",
    "action"
  ],
  "segments_deleted": [
    "segment_ids"
  ],
  "memory_created": [
    "memory"
  ],
  "memory_processing_started": [
    "memory"
  ],
  "onboarding_question": [
    "question",
    "question_index",
    "total_questions"
  ],
  "question_answered": [
    "question_index",
    "answered"
  ],
  "question_skipped": [
    "question_index"
  ],
  "onboarding_complete": [
    "answers_count"
  ],
  "entitlement": [
    "state",
    "reason",
    "usage",
    "limit",
    "upgrade_target"
  ]
};

/**
 * Decode one inbound text frame. Total: never throws, never returns undefined.
 * Unrecognised `type` values fail open to `unknown_event` wrapped in Degraded
 * (INV-LISTEN-006 — telemetry by construction via degrade()).
 * Binary frames are audio and are never passed here.
 *
 * `at` is an injected clock reading (Env.now()) — no wall clock in decode.
 */
export function decode(sink: FallbackSink, at: number, raw: string): MaybeDegraded<DecodedListenFrame> {
  if (raw === LISTEN_HEARTBEAT_TEXT) return { kind: "heartbeat" };
  if (raw === "") return { kind: "invalid", reason: "empty", raw };
  let json: unknown;
  try {
    json = JSON.parse(raw);
  } catch {
    return { kind: "invalid", reason: "not_json", raw };
  }
  return decodeValue(sink, at, json);
}

/** Decode an already-parsed frame value (same contract as `decode`). */
export function decodeValue(sink: FallbackSink, at: number, json: unknown): MaybeDegraded<DecodedListenFrame> {
  if (Array.isArray(json)) {
    // Non-envelope frame 1: the bare transcript array.
    return { kind: "transcript_batch", segments: json as TranscriptSegment[] };
  }
  if (json === null || typeof json !== "object") {
    return { kind: "invalid", reason: "not_an_object", raw: json };
  }
  const obj = json as Record<string, unknown>;
  const type = obj["type"];
  if (typeof type !== "string") return { kind: "invalid", reason: "no_type_field", raw: obj };
  const required = REQUIRED_KEYS[type];
  if (required === undefined) {
    // INV-LISTEN-006: unknown frame kinds are Degraded, never a silent skip.
    return degrade(
      sink,
      {
        path: "listen.decode.unknown-frame",
        from: type,
        to: "unknown_event",
        detail: `unrecognized listen frame type: ${type}`,
        at,
      },
      { kind: "unknown_event", type, raw: obj },
    );
  }
  if (!hasAll(obj, required)) return { kind: "invalid", reason: "missing_required_fields", raw: obj };
  switch (type) {
    case "auth_response":
      return { kind: "event", event: obj as unknown as AuthResponseFrame };
    case "service_status":
      return { kind: "event", event: obj as unknown as ServiceStatusEvent };
    case "conversation_session":
      return { kind: "event", event: obj as unknown as ConversationSessionEvent };
    case "ping":
      return { kind: "event", event: obj as unknown as PingEvent };
    case "last_memory":
      return { kind: "event", event: obj as unknown as LastConversationEvent };
    case "translating":
      return { kind: "event", event: obj as unknown as TranslationEvent };
    case "photo_processing":
      return { kind: "event", event: obj as unknown as PhotoProcessingEvent };
    case "photo_described":
      return { kind: "event", event: obj as unknown as PhotoDescribedEvent };
    case "speaker_label_suggestion":
      return { kind: "event", event: obj as unknown as SpeakerLabelSuggestionEvent };
    case "freemium_threshold_reached":
      return { kind: "event", event: obj as unknown as FreemiumThresholdReachedEvent };
    case "segments_deleted":
      return { kind: "event", event: obj as unknown as SegmentsDeletedEvent };
    case "memory_created":
      return { kind: "event", event: obj as unknown as ConversationCreatedEvent };
    case "memory_processing_started":
      return { kind: "event", event: obj as unknown as ConversationProcessingStartedEvent };
    case "onboarding_question":
      return { kind: "event", event: obj as unknown as OnboardingQuestionEvent };
    case "question_answered":
      return { kind: "event", event: obj as unknown as OnboardingQuestionAnsweredEvent };
    case "question_skipped":
      return { kind: "event", event: obj as unknown as OnboardingQuestionSkippedEvent };
    case "onboarding_complete":
      return { kind: "event", event: obj as unknown as OnboardingCompleteEvent };
    case "entitlement":
      return { kind: "event", event: obj as unknown as EntitlementEvent };
    default:
      // Exhaustive over REQUIRED_KEYS today; still fails open (with telemetry) if the two drift.
      return degrade(
        sink,
        {
          path: "listen.decode.unknown-frame",
          from: type,
          to: "unknown_event",
          detail: `unrecognized listen frame type: ${type}`,
          at,
        },
        { kind: "unknown_event", type, raw: obj },
      );
  }
}

/** Narrowing helper: exhaustiveness assertion for consumer switches. */
export function assertNeverListenEvent(event: never): never {
  throw new Error(`unhandled listen event: ${JSON.stringify(event)}`);
}
