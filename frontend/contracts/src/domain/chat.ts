/**
 * Chat messages domain contract — ADR-005 write contract as a first-class
 * domain slice (WS-006), built by copying the tasks/memories pair's shape
 * (see `tasks.ts`, `memories.ts`). Where those two differ, the difference is
 * the lesson: names are domain-prefixed, patches are keyed and endpoint-honest,
 * and server-owned fields stay out of the patch type.
 *
 * Field set is grounded in the legacy backend Message model at baseline
 * `e0893286` (`backend/models/chat.py`, `backend/database/chat.py` via
 * adapters-legacy — reference only, never imported), scoped to what ADR-005
 * makes load-bearing: client_message_id-as-doc-id, monotonic journal_revision,
 * payload-hash idempotency, closed sender/type vocabulary (INV-CHAT-001).
 * Attachments are ratified below. chart_data, memories citations, and
 * LangSmith provenance remain foundation gaps — surfaced for the adapter, not
 * silently modeled. In particular, memories citation internals are owned by a
 * separate lane and are deliberately absent here.
 *
 * Authority (ADR-005 §1): the backend is the chat record on every surface.
 * Local journals are ADR-004 durable-mirror instances (offline reads + queued
 * sends), never truth. Terminal stream frames carry the complete canonical
 * message (ADR-005 §3 / INV-CHAT-002), not a delta — declared below so the
 * wire layer cannot invent a parallel "done = last delta" shape.
 */

import type { RecordId } from "../ids.js";
import type { WriteFailure } from "../errors.js";

/**
 * Closed sender vocabulary (INV-CHAT-001 / ADR-005 §4). Legacy backend enum
 * is `MessageSender = { human, ai }` (`backend/models/chat.py`); Windows'
 * internal `role: user | assistant` maps 1:1 at the persistence boundary and
 * is NOT the wire spelling.
 *
 * // domain-pending(DIV-CHAT-SENDER-001) — `sender` (legacy) vs Windows `role`
 */
export type ChatMessageSender = "human" | "ai" | "unknown";

/**
 * What a CLIENT may author. Deliberately narrower than `ChatMessageSender`.
 *
 * `"unknown"` is a READ tolerance — it exists so a sender this client version
 * has never heard of round-trips through the projection instead of being
 * dropped or coerced to `"human"` (which would attribute the model's words to
 * the user). Neither `"unknown"` nor `"ai"` is something a client may WRITE:
 * assistant messages are server-authored. Enforced by construction —
 * `ChatMessageOp`'s create arm takes this type, so the narrowing is a compile
 * error, not a convention.
 */
export type ChatMessageAuthoredSender = "human";

/**
 * Closed type vocabulary (INV-CHAT-001). Legacy `MessageType = { text,
 * day_summary }`; `unknown` is the fail-open sentinel (S2-5).
 *
 * // domain-pending(DIV-CHAT-TYPE-001) — keep legacy `type` vs rename to `kind`
 */
export type ChatMessageType = "text" | "day_summary" | "unknown";

/** null for human/unknown rows; every canonical assistant row states how it ended. */
export type ChatGenerationOutcome = "completed" | "cancelled" | null;

/**
 * One canonical message attachment.
 *
 * `displayName`, `mediaType`, and `sizeBytes` are durable message metadata and
 * survive for the lifetime of the message. `contentReference` is deliberately
 * nullable: `null` is the normal expired-content state, not a transport error
 * and not permission to discard or fabricate the metadata.
 *
 * Server retention invariant (ratified with this contract): unbound staging
 * has a 24-hour TTL which bounds the retry horizon; retained content has a
 * 30-day retention window; metadata is durable forever. A send retry that is
 * still admissible must never fail because its staged attachment expired.
 * Those durations have one server-side constant owner; clients do not restate
 * or enforce them.
 */
export interface ChatAttachment {
  /** Opaque server-issued attachment identity. Never a local path or URL. */
  id: string;
  displayName: string;
  mediaType: string;
  sizeBytes: number;
  /** Opaque retrievable-content reference, or null after content expiry. */
  contentReference: string | null;
}

/**
 * The chat message record. `id` IS the client-supplied `client_message_id`
 * used as the Firestore document id (ADR-005 §2 / INV-CHAT-006) — same
 * client-id-as-record-id shape as Task/Memory create, spelled `id` to match
 * the exemplar pair (the wire field name `client_message_id` is an adapter
 * concern).
 */
interface ChatMessageFields {
  id: RecordId;
  text: string;
  /** // domain-pending(DIV-CHAT-TYPE-001) */
  type: ChatMessageType;
  createdAt: number;
  updatedAt: number;
  /**
   * Legacy dual-writes `chat_session_id` / `session_id`; this contract picks
   * the chat.py-facing name. `null` = main/implicit session not yet bound.
   *
   * // domain-pending(DIV-CHAT-SESSION-001) — `chatSessionId` vs `sessionId`
   */
  chatSessionId: string | null;
  /** App/persona scope; `null` = main Omi chat. */
  appId: string | null;
  /**
   * Monotonic journal revision (ADR-005 §2). Integer — not the string
   * `revision` used for cross-domain reconcile comparison.
   *
   * // domain-pending(DIV-CHAT-REV-001) — whether `revision` subsumes this
   */
  journalRevision: number;
  /**
   * Digest of the caller-controlled immutable payload (`sha256:…`), matching
   * `client_message_payload_hash` on the desktop write path. Pure function of
   * the payload — see `chatMessagePayloadHash` in `@omi-core/kernel`.
   *
   * // domain-pending(DIV-CHAT-HASH-001) — field spelling vs wire name
   */
  payloadHash: string;
  /**
   * Provenance of the write path (legacy default `desktop_chat`).
   *
   * // domain-pending(DIV-CHAT-SOURCE-001)
   */
  messageSource: string;
  /** Thumbs: `1` up, `-1` down, `null` unset. AI-sender feedback only on wire. */
  rating: number | null;
  reported: boolean;
  /** Canonical attachment order. Durable metadata remains after content expiry. */
  attachments: readonly ChatAttachment[];
  /**
   * Server revision of the last write we saw; reconcile compares these.
   * Distinct from `journalRevision` until an architect ratchets the encoding
   * (handoff DIV-WIRE-REV-001 / FE-CORE-platform-wire open question). Kept
   * `string | null` to match the exemplar pair.
   */
  revision: string | null;
}

/** Canonical client-authored record admitted before assistant generation. */
export type ChatHumanMessage = ChatMessageFields & {
  sender: "human";
  generationOutcome: null;
};

/** Canonical assistant success. The outcome is part of the discriminator. */
export type ChatCompletedAssistantMessage = ChatMessageFields & {
  sender: "ai";
  generationOutcome: "completed";
};

/** Canonical retained assistant cancellation. */
export type ChatCancelledAssistantMessage = ChatMessageFields & {
  sender: "ai";
  generationOutcome: "cancelled";
};

export type ChatAssistantMessage =
  | ChatCompletedAssistantMessage
  | ChatCancelledAssistantMessage;

/** Read-tolerant record whose future sender semantics are not yet known. */
export type ChatUnknownSenderMessage = ChatMessageFields & {
  sender: "unknown";
  generationOutcome: ChatGenerationOutcome;
};

/** Sender and generation outcome are one discriminated state, never two flags. */
export type ChatMessage = ChatHumanMessage | ChatAssistantMessage | ChatUnknownSenderMessage;

/**
 * Fields a patch may touch. Absent key = unchanged, by construction.
 *
 * Text / sender / type / journalRevision / payloadHash are deliberately
 * excluded: identity and journal enrichment go through create-with-higher-
 * revision on the desktop write path (`backend/database/chat.py` revision
 * arbitration), not a separate PATCH. `reported` has a dedicated report
 * endpoint, not a generic field patch.
 */
export type ChatMessagePatch = Partial<Pick<ChatMessage, "rating">>;

/**
 * The universal write contract (ADR-004 D2 + ADR-005 shape): client-supplied
 * id on create (slug, per ADR-006) equals `client_message_id` on the wire;
 * idempotent by opId on every operation; create also carries the monotonic
 * journal_revision that ADR-005 requires.
 */
export type ChatMessageOp =
  | {
      op: "create";
      opId: string;
      id: RecordId;
      at: number;
      text: string;
      /** The ratified send route admits human-authored messages only. */
      sender: "human";
      journalRevision: number;
      type?: ChatMessageType;
      appId?: string | null;
      chatSessionId?: string | null;
      messageSource?: string;
      /** Opaque desktop journal metadata string; hashed, not projected. */
      metadata?: string | null;
      /**
       * Opaque staged attachment ids in authored order. Exact replay retains
       * this list; it participates in payload-hash idempotency.
       */
      attachmentIds: readonly string[];
    }
  | { op: "patch"; opId: string; id: RecordId; at: number; patch: ChatMessagePatch }
  | { op: "delete"; opId: string; id: RecordId; at: number };

/**
 * Effective upload policy, returned with every history page. The server is
 * still authoritative at send time.
 */
export interface ChatCapabilitiesWire {
  maxAttachmentsPerMessage: number;
  maxAttachmentBytes: number;
  allowedAttachmentMimeTypes: readonly string[];
}

/** Opaque, concurrent-insert-safe backward keyset page metadata. */
export type ChatHistoryPageWire =
  | { olderCursor: string; hasOlder: true }
  | { olderCursor: null; hasOlder: false };

/** Ratified GET /v1/chat-messages success envelope. */
export interface ChatHistoryEnvelope {
  messages: readonly ChatMessage[];
  page: ChatHistoryPageWire;
  capabilities: ChatCapabilitiesWire;
}

/** Fixed Chat failure envelope. No stored content or internal reason enters it. */
export interface ChatErrorEnvelope {
  error: {
    code: string;
    retryable: boolean;
    action?: "reauthenticate" | "refresh_history" | "edit_request";
  };
}

/** Plain-JSON POST admission echoing the canonical human record and generation. */
export interface ChatAdmissionEnvelope {
  message: ChatHumanMessage;
  generation: { id: string };
}

/** Advisory frames never become canonical records. */
export type ChatAdvisoryFrame =
  | { kind: "snapshot"; text: string }
  | { kind: "delta"; text: string };

/**
 * Terminal stream outcome (INV-CHAT-002).
 *
 * `done.message` is the complete canonical assistant message, never the last
 * delta. Cancellation retains its non-empty partial as a complete canonical
 * message and carries it here non-null, so "stopped on purpose" can never be
 * confused with a truncated success. `failed` is the only terminal without a
 * canonical assistant record.
 */
export type ChatTerminalFrame =
  | { kind: "done"; message: ChatCompletedAssistantMessage }
  | { kind: "failed"; error: { code: string; retryable: boolean } }
  | { kind: "cancelled"; message: ChatCancelledAssistantMessage };

/** Complete ratified SSE data-frame grammar. Heartbeat comments are not frames. */
export type ChatGenerationFrame = ChatAdvisoryFrame | ChatTerminalFrame;

/** DELETE /v1/chat-generations/{id} accepted response. */
export type ChatCancellationEnvelope = { cancellation: { state: "accepted" } };

/**
 * HTTP 409 identity conflict (same `client_message_id`, different payload
 * hash — INV-CHAT-006 / `ClientMessageIdPayloadConflict`).
 *
 * WriteFailure kind: `permanent` with `reason: "conflict"`.
 *
 * Why not retryable: retrying the same conflicting payload cannot succeed —
 * the server already bound that id to a different canonical identity. The
 * outbox must NOT spin (FC-permanent-write-rejection-retried-forever); the
 * op moves to the dead-letter surface (`OperationOutcome.state: "dead"`),
 * which is always user-visible. There is no fifth WriteFailure kind; this
 * is exactly the `permanent`/`conflict` slot `classifyStatus` already maps
 * HTTP 409 onto.
 */
export type ChatIdentityConflictFailure = Extract<WriteFailure, { kind: "permanent" }> & {
  reason: "conflict";
};

/**
 * What a backend (real or legacy adapter) must expose for chat — the
 * ADR-004 D3 read side. Deletion of local rows is permitted only against a
 * `complete: true` snapshot. Chat's list reconcile path is keyset and
 * duplicate-free under concurrent insertion (FC-CHAT-005 / backend
 * `get_messages_reconcile_page`); that guarantee is an adapter/read concern,
 * not a completeness claim — do not invent `complete: true` without a
 * SnapshotDescriptor evidence locator (hard rule 12). ADR-005 itself is
 * silent on id-snapshot completeness; default remains `complete: false`.
 */
/** Alias of the shared IdSnapshot (wave-1 ratchet) — use IdSnapshot in new code. */
export type ChatMessageIdSnapshot = import("../snapshot.js").IdSnapshot;
