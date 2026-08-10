// domain-pending(DIV-CHAT-SESSION-001)

import { createHmac, timingSafeEqual } from "node:crypto";

import type { ChatHistoryKey } from "../stores/chat-messages-store";

const PREFIX = "chat1";
const KEY_ID = /^[A-Za-z0-9_-]{1,64}$/;
const TOKEN_PART = /^[A-Za-z0-9_-]+$/;
const MAX_CURSOR_BYTES = 4_096;
const MAX_TTL_SECONDS = 86_400;

export interface ChatHistoryCursorKey {
  readonly id: string;
  readonly secret: Uint8Array;
}

export interface ChatHistoryCursorKeyset {
  readonly activeId: string;
  readonly keys: readonly ChatHistoryCursorKey[];
}

export interface ChatHistoryCursorClaims {
  readonly snapshotSequence: number;
  readonly olderThan: ChatHistoryKey;
  readonly issuedAtEpochSeconds: number;
}

interface CursorPayload {
  readonly version: 1;
  readonly accountDigest: string;
  readonly accountEpoch: number | null;
  readonly appId: null;
  readonly chatSessionId: null;
  readonly direction: "older";
  readonly snapshotSequence: number;
  readonly olderThan: ChatHistoryKey;
  readonly issuedAt: number;
  readonly expiresAt: number;
}

export class InvalidChatHistoryCursorError extends Error {
  constructor() {
    super("invalid chat history cursor");
    this.name = "InvalidChatHistoryCursorError";
  }
}

export class ExpiredChatHistoryCursorError extends Error {
  constructor() {
    super("expired chat history cursor");
    this.name = "ExpiredChatHistoryCursorError";
  }
}

const invalid = (): never => { throw new InvalidChatHistoryCursorError(); };

const normalizeKeys = (keyset: ChatHistoryCursorKeyset): {
  readonly active: ChatHistoryCursorKey;
  readonly byId: ReadonlyMap<string, ChatHistoryCursorKey>;
} => {
  if (!KEY_ID.test(keyset.activeId) || keyset.keys.length < 1 || keyset.keys.length > 8) {
    throw new TypeError("invalid chat cursor keyset");
  }
  const byId = new Map<string, ChatHistoryCursorKey>();
  for (const key of keyset.keys) {
    if (!KEY_ID.test(key.id) || !(key.secret instanceof Uint8Array)
      || key.secret.byteLength < 32 || byId.has(key.id)) {
      throw new TypeError("invalid chat cursor signing key");
    }
    byId.set(key.id, Object.freeze({ id: key.id, secret: new Uint8Array(key.secret) }));
  }
  const active = byId.get(keyset.activeId);
  if (active === undefined) throw new TypeError("active chat cursor key is absent");
  return { active, byId };
};

const accountDigest = (accountId: string, secret: Uint8Array): string =>
  createHmac("sha256", secret).update("chat-history-account\0", "utf8")
    .update(accountId, "utf8").digest("hex");

const encodePayload = (payload: CursorPayload): string =>
  Buffer.from(JSON.stringify(payload), "utf8").toString("base64url");

const signature = (keyId: string, payload: string, secret: Uint8Array): Buffer =>
  createHmac("sha256", secret).update(`${PREFIX}.${keyId}.${payload}`, "ascii").digest();

const exactPayload = (value: unknown): CursorPayload => {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return invalid();
  const object = value as Record<string, unknown>;
  const keys = Object.keys(object).sort();
  const expected = [
    "accountDigest", "accountEpoch", "appId", "chatSessionId", "direction", "expiresAt",
    "issuedAt", "olderThan", "snapshotSequence", "version",
  ].sort();
  if (keys.length !== expected.length || keys.some((key, index) => key !== expected[index])) {
    return invalid();
  }
  const boundary = object.olderThan;
  if (boundary === null || typeof boundary !== "object" || Array.isArray(boundary)
    || Object.keys(boundary).sort().join(",") !== "createdAt,id") return invalid();
  const olderThan = boundary as Record<string, unknown>;
  if (object.version !== 1 || typeof object.accountDigest !== "string"
    || !/^[a-f0-9]{64}$/.test(object.accountDigest)
    || !(object.accountEpoch === null
      || (Number.isSafeInteger(object.accountEpoch) && (object.accountEpoch as number) >= 0))
    || object.appId !== null || object.chatSessionId !== null
    || object.direction !== "older"
    || !Number.isSafeInteger(object.snapshotSequence) || (object.snapshotSequence as number) < 0
    || !Number.isSafeInteger(olderThan.createdAt) || (olderThan.createdAt as number) < 0
    || typeof olderThan.id !== "string" || olderThan.id.length === 0
    || !Number.isSafeInteger(object.issuedAt) || (object.issuedAt as number) < 0
    || !Number.isSafeInteger(object.expiresAt) || (object.expiresAt as number) < 0
    || (object.expiresAt as number) <= (object.issuedAt as number)) return invalid();
  return object as unknown as CursorPayload;
};

export const createChatHistoryCursorCodec = (keyset: ChatHistoryCursorKeyset) => {
  const keys = normalizeKeys(keyset);
  return Object.freeze({
    issue(input: {
      readonly accountId: string;
      readonly accountEpoch: number | null;
      readonly snapshotSequence: number;
      readonly olderThan: ChatHistoryKey;
      readonly issuedAtEpochSeconds: number;
      readonly ttlSeconds: number;
    }): string {
      if (!Number.isSafeInteger(input.snapshotSequence) || input.snapshotSequence < 0
        || !(input.accountEpoch === null
          || (Number.isSafeInteger(input.accountEpoch) && input.accountEpoch >= 0))
        || !Number.isSafeInteger(input.olderThan.createdAt) || input.olderThan.createdAt < 0
        || !input.olderThan.id
        || !Number.isSafeInteger(input.issuedAtEpochSeconds) || input.issuedAtEpochSeconds < 0
        || !Number.isSafeInteger(input.ttlSeconds) || input.ttlSeconds < 1
        || input.ttlSeconds > MAX_TTL_SECONDS
        || input.issuedAtEpochSeconds > Number.MAX_SAFE_INTEGER - input.ttlSeconds) {
        throw new TypeError("invalid chat history cursor issue request");
      }
      const payload: CursorPayload = {
        version: 1,
        accountDigest: accountDigest(input.accountId, keys.active.secret),
        accountEpoch: input.accountEpoch,
        appId: null,
        chatSessionId: null,
        direction: "older",
        snapshotSequence: input.snapshotSequence,
        olderThan: { createdAt: input.olderThan.createdAt, id: input.olderThan.id },
        issuedAt: input.issuedAtEpochSeconds,
        expiresAt: input.issuedAtEpochSeconds + input.ttlSeconds,
      };
      const encoded = encodePayload(payload);
      const signed = signature(keys.active.id, encoded, keys.active.secret).toString("base64url");
      return `${PREFIX}.${keys.active.id}.${encoded}.${signed}`;
    },

    verify(cursor: string, input: {
      readonly accountId: string;
      readonly accountEpoch: number | null;
      readonly nowEpochSeconds: number;
    }): ChatHistoryCursorClaims {
      if (typeof cursor !== "string" || Buffer.byteLength(cursor, "utf8") > MAX_CURSOR_BYTES) {
        return invalid();
      }
      const parts = cursor.split(".");
      if (parts.length !== 4 || parts[0] !== PREFIX || !KEY_ID.test(parts[1] ?? "")
        || !TOKEN_PART.test(parts[2] ?? "") || !TOKEN_PART.test(parts[3] ?? "")) return invalid();
      const key = keys.byId.get(parts[1]!);
      let supplied: Buffer;
      try {
        supplied = Buffer.from(parts[3]!, "base64url");
      } catch {
        return invalid();
      }
      if (supplied.toString("base64url") !== parts[3]) return invalid();
      const expected = key === undefined
        ? Buffer.alloc(32)
        : signature(parts[1]!, parts[2]!, key.secret);
      if (supplied.byteLength !== expected.byteLength || !timingSafeEqual(supplied, expected)
        || key === undefined) return invalid();
      let parsed: unknown;
      try {
        const decoded = Buffer.from(parts[2]!, "base64url");
        if (decoded.toString("base64url") !== parts[2]) return invalid();
        parsed = JSON.parse(decoded.toString("utf8"));
      } catch {
        return invalid();
      }
      const payload = exactPayload(parsed);
      if (encodePayload(payload) !== parts[2]
        || payload.accountDigest !== accountDigest(input.accountId, key.secret)
        || payload.accountEpoch !== input.accountEpoch) return invalid();
      if (!Number.isSafeInteger(input.nowEpochSeconds) || input.nowEpochSeconds < 0) {
        throw new TypeError("invalid chat cursor verification clock");
      }
      if (input.nowEpochSeconds >= payload.expiresAt) {
        throw new ExpiredChatHistoryCursorError();
      }
      return Object.freeze({
        snapshotSequence: payload.snapshotSequence,
        olderThan: Object.freeze({ ...payload.olderThan }),
        issuedAtEpochSeconds: payload.issuedAt,
      });
    },
  });
};

export type ChatHistoryCursorCodec = ReturnType<typeof createChatHistoryCursorCodec>;
