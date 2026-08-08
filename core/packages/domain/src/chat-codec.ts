/**
 * Chat messages: op builders + the projection codec + the payload-hash helper.
 * Mirrors tasks-codec.ts / memories-codec.ts over the chat contract (ADR-005).
 *
 * Payload hash is a PURE function of the caller-controlled immutable fields —
 * no Env clock, no Math.random — matching
 * `backend/database/chat.py::_message_idempotency_payload_hash` so client and
 * server agree on identity-conflict detection.
 */

import type {
  ChatIdentityConflictFailure,
  ChatMessageAuthoredSender,
  ChatMessage,
  ChatMessageOp,
  ChatMessagePatch,
  ChatMessageType,
  RecordId,
  WriteFailure,
} from "@omi-core/contracts";
import { generateSlug, type Env } from "@omi-core/kernel";
import type { PendingOp, ProjectionCodec } from "@omi-core/sync";

/** Fields the backend folds into `client_message_payload_hash`. */
export interface ChatMessageHashPayload {
  text: string;
  sender: string;
  appId: string | null;
  /** Wire `session_id` — same value as `chatSessionId` on the record. */
  sessionId: string | null;
  metadata: string | null;
  messageSource: string;
}

const DEFAULT_MESSAGE_SOURCE = "desktop_chat";

/**
 * Stable digest matching the desktop write path:
 * `sha256:` + hex of canonical JSON with sorted keys, no ASCII escapes.
 */
export function chatMessagePayloadHash(payload: ChatMessageHashPayload): string {
  const wire: Record<string, string | null> = {
    app_id: payload.appId,
    message_source: payload.messageSource,
    metadata: payload.metadata,
    sender: payload.sender,
    session_id: payload.sessionId,
    text: payload.text,
  };
  const canonical = JSON.stringify(wire, Object.keys(wire).sort());
  return `sha256:${sha256Hex(utf8Bytes(canonical))}`;
}

export function buildCreateChatMessage(
  env: Env,
  text: string,
  opts?: {
    sender?: ChatMessageAuthoredSender;
    type?: ChatMessageType;
    journalRevision?: number;
    appId?: string | null;
    chatSessionId?: string | null;
    messageSource?: string;
    metadata?: string | null;
  },
): ChatMessageOp {
  const id = generateSlug(() => env.random());
  const base = {
    op: "create" as const,
    opId: generateSlug(() => env.random()),
    id,
    at: env.now(),
    text,
    sender: opts?.sender ?? "human",
    journalRevision: opts?.journalRevision ?? 1,
  };
  return {
    ...base,
    ...(opts?.type !== undefined ? { type: opts.type } : {}),
    ...(opts?.appId !== undefined ? { appId: opts.appId } : {}),
    ...(opts?.chatSessionId !== undefined ? { chatSessionId: opts.chatSessionId } : {}),
    ...(opts?.messageSource !== undefined ? { messageSource: opts.messageSource } : {}),
    ...(opts?.metadata !== undefined ? { metadata: opts.metadata } : {}),
  };
}

export function buildPatchChatMessage(env: Env, id: RecordId, patch: ChatMessagePatch): ChatMessageOp {
  return { op: "patch", opId: generateSlug(() => env.random()), id, at: env.now(), patch };
}

export function buildDeleteChatMessage(env: Env, id: RecordId): ChatMessageOp {
  return { op: "delete", opId: generateSlug(() => env.random()), id, at: env.now() };
}

/** Contract op → outbox record, with the human summary the dead-letter
 * surface renders (a retained op nobody can read is still lost content). */
export function chatMessageToPendingOp(op: ChatMessageOp): PendingOp {
  const summary =
    op.op === "create"
      ? `Send chat: ${op.text.slice(0, 80)}${op.text.length > 80 ? "…" : ""}`
      : op.op === "delete"
        ? `Delete chat message ${op.id}`
        : `Edit chat message ${op.id}: ${Object.keys(op.patch).join(", ")}`;
  return {
    opId: op.opId,
    domain: "chat",
    recordId: op.id,
    payload: JSON.stringify(op),
    summary,
    attempts: 0,
  };
}

/**
 * Fold an HTTP 409 identity conflict onto the WriteFailure taxonomy.
 *
 * Kind is `permanent` / `reason: "conflict"` — NOT retryable. Same
 * client_message_id with a different payload hash will 409 forever if
 * retried; the outbox must dead-letter (user-visible) instead of spinning.
 * See `ChatIdentityConflictFailure` on the contract.
 */
export function foldChatIdentityConflict(detail: string): ChatIdentityConflictFailure {
  return { kind: "permanent", reason: "conflict", detail };
}

/** Narrow helper so adapters can assert the folded shape without casting. */
export function isChatIdentityConflictFailure(
  failure: WriteFailure,
): failure is ChatIdentityConflictFailure {
  return failure.kind === "permanent" && failure.reason === "conflict";
}

/** Optimistic overlay: how a pending op changes what the screen shows. */
export const chatMessagesCodec: ProjectionCodec<ChatMessage> = {
  id: (m) => m.id,
  applyOp: (payload, current) => {
    const op = JSON.parse(payload) as ChatMessageOp;
    switch (op.op) {
      case "create": {
        const appId = op.appId ?? null;
        const chatSessionId = op.chatSessionId ?? null;
        const messageSource = op.messageSource ?? DEFAULT_MESSAGE_SOURCE;
        const metadata = op.metadata ?? null;
        return {
          id: op.id,
          text: op.text,
          sender: op.sender,
          type: op.type ?? "text",
          createdAt: op.at,
          updatedAt: op.at,
          chatSessionId,
          appId,
          journalRevision: op.journalRevision,
          payloadHash: chatMessagePayloadHash({
            text: op.text,
            sender: op.sender,
            appId,
            sessionId: chatSessionId,
            metadata,
            messageSource,
          }),
          messageSource,
          rating: null,
          reported: false,
          revision: null,
        };
      }
      case "delete":
        return null;
      case "patch": {
        if (!current) return current;
        // Keyed patch: absent key = unchanged. Never setdefault.
        const next: ChatMessage = { ...current, updatedAt: op.at };
        const p = op.patch;
        if (p.rating !== undefined) next.rating = p.rating;
        return next;
      }
    }
  },
};

// ─── Pure SHA-256 (no wall clock, no Math.random, no ambient Node crypto) ───

/** UTF-8 encode without depending on DOM `TextEncoder` typings in domain. */
function utf8Bytes(s: string): Uint8Array {
  const out: number[] = [];
  for (let i = 0; i < s.length; i++) {
    let c = s.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff && i + 1 < s.length) {
      const d = s.charCodeAt(i + 1);
      if (d >= 0xdc00 && d <= 0xdfff) {
        c = 0x10000 + ((c - 0xd800) << 10) + (d - 0xdc00);
        i++;
      }
    }
    if (c <= 0x7f) out.push(c);
    else if (c <= 0x7ff) {
      out.push(0xc0 | (c >> 6), 0x80 | (c & 0x3f));
    } else if (c <= 0xffff) {
      out.push(0xe0 | (c >> 12), 0x80 | ((c >> 6) & 0x3f), 0x80 | (c & 0x3f));
    } else {
      out.push(
        0xf0 | (c >> 18),
        0x80 | ((c >> 12) & 0x3f),
        0x80 | ((c >> 6) & 0x3f),
        0x80 | (c & 0x3f),
      );
    }
  }
  return Uint8Array.from(out);
}

function sha256Hex(data: Uint8Array): string {
  const H = new Uint32Array([
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
  ]);
  const K = new Uint32Array([
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
  ]);

  const bitLen = data.length * 8;
  const withPad = data.length + 1 + 8;
  const paddedLen = Math.ceil(withPad / 64) * 64;
  const buf = new Uint8Array(paddedLen);
  buf.set(data);
  buf[data.length] = 0x80;
  const view = new DataView(buf.buffer);
  // high 32 bits of length are 0 for messages we hash (<< 2^32 bits)
  view.setUint32(paddedLen - 4, bitLen >>> 0, false);

  const w = new Uint32Array(64);
  for (let i = 0; i < paddedLen; i += 64) {
    for (let j = 0; j < 16; j++) w[j] = view.getUint32(i + j * 4, false);
    for (let j = 16; j < 64; j++) {
      const v1 = w[j - 15]!;
      const v2 = w[j - 2]!;
      const s0 = rotr(v1, 7) ^ rotr(v1, 18) ^ (v1 >>> 3);
      const s1 = rotr(v2, 17) ^ rotr(v2, 19) ^ (v2 >>> 10);
      w[j] = (w[j - 16]! + s0 + w[j - 7]! + s1) >>> 0;
    }
    let [a, b, c, d, e, f, g, h] = H;
    for (let j = 0; j < 64; j++) {
      const S1 = rotr(e!, 6) ^ rotr(e!, 11) ^ rotr(e!, 25);
      const ch = (e! & f!) ^ (~e! & g!);
      const t1 = (h! + S1 + ch + K[j]! + w[j]!) >>> 0;
      const S0 = rotr(a!, 2) ^ rotr(a!, 13) ^ rotr(a!, 22);
      const maj = (a! & b!) ^ (a! & c!) ^ (b! & c!);
      const t2 = (S0 + maj) >>> 0;
      h = g;
      g = f;
      f = e;
      e = (d! + t1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (t1 + t2) >>> 0;
    }
    H[0] = (H[0]! + a!) >>> 0;
    H[1] = (H[1]! + b!) >>> 0;
    H[2] = (H[2]! + c!) >>> 0;
    H[3] = (H[3]! + d!) >>> 0;
    H[4] = (H[4]! + e!) >>> 0;
    H[5] = (H[5]! + f!) >>> 0;
    H[6] = (H[6]! + g!) >>> 0;
    H[7] = (H[7]! + h!) >>> 0;
  }

  let out = "";
  for (let i = 0; i < 8; i++) out += H[i]!.toString(16).padStart(8, "0");
  return out;
}

function rotr(x: number, n: number): number {
  return ((x >>> n) | (x << (32 - n))) >>> 0;
}
