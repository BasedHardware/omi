// domain-pending(DIV-DOMCORE-012)

/**
 * Durable service-side state for the legacy /listen capture vocabulary.
 *
 * A recording session is bound to one conversation id before the first
 * transcript segment is accepted. Delivery is tracked independently from
 * persistence so an interrupted socket can replay uncertain segments with the
 * same ids rather than asking a transcription adapter to mint replacements.
 */

export type ListenSessionStatus =
  | "active"
  | "interrupted"
  | "completed"
  | "entitlement_exhausted";

export interface ListenSessionRecord {
  readonly id: string;
  readonly conversationId: string;
  readonly clientConversationId: string | null;
  readonly startedAt: string;
  readonly updatedAt: string;
  readonly endedAt: string | null;
  readonly status: ListenSessionStatus;
  readonly source: string | null;
  readonly codec: string;
  readonly sampleRate: number;
  readonly channels: number;
}

/** The persisted subset is also a valid TranscriptSegment wire object. */
export interface ListenTranscriptSegment {
  readonly id: string;
  readonly text: string;
  readonly is_user: boolean;
  readonly start: number;
  readonly end: number;
}

export interface OpenListenSessionInput {
  readonly accountId: string;
  readonly id: string;
  readonly conversationId: string;
  readonly clientConversationId: string | null;
  readonly at: string;
  readonly source: string | null;
  readonly codec: string;
  readonly sampleRate: number;
  readonly channels: number;
}

export interface OpenListenSessionOutcome {
  readonly session: ListenSessionRecord;
  readonly resumed: boolean;
  readonly pendingSegments: readonly ListenTranscriptSegment[];
}

export interface AppendListenSegmentOutcome {
  readonly segment: ListenTranscriptSegment;
  readonly inserted: boolean;
}

export interface ListenStore {
  openOrResume(input: OpenListenSessionInput): OpenListenSessionOutcome;
  appendSegment(
    accountId: string,
    sessionId: string,
    segment: ListenTranscriptSegment,
    at: string,
  ): AppendListenSegmentOutcome;
  markDelivered(accountId: string, sessionId: string, segmentIds: readonly string[]): void;
  pendingSegments(accountId: string, sessionId: string): readonly ListenTranscriptSegment[];
  closeSession(
    accountId: string,
    sessionId: string,
    status: Exclude<ListenSessionStatus, "active">,
    at: string,
  ): ListenSessionRecord | null;
  readSession(accountId: string, sessionId: string): ListenSessionRecord | null;
  listSegments(accountId: string, sessionId: string): readonly ListenTranscriptSegment[];
  reset(): void;
}

const freezeSession = (session: ListenSessionRecord): ListenSessionRecord =>
  Object.freeze({ ...session });

const freezeSegment = (segment: ListenTranscriptSegment): ListenTranscriptSegment =>
  Object.freeze({ ...segment });

const assertSegment = (segment: ListenTranscriptSegment): ListenTranscriptSegment => {
  if (typeof segment.id !== "string" || segment.id.length === 0
    || typeof segment.text !== "string"
    || typeof segment.is_user !== "boolean"
    || typeof segment.start !== "number" || !Number.isFinite(segment.start)
    || typeof segment.end !== "number" || !Number.isFinite(segment.end)
    || segment.start < 0 || segment.end < segment.start) {
    throw new TypeError("invalid listen transcript segment");
  }
  return freezeSegment(segment);
};

const sameSegment = (
  left: ListenTranscriptSegment,
  right: ListenTranscriptSegment,
): boolean => left.id === right.id
  && left.text === right.text
  && left.is_user === right.is_user
  && left.start === right.start
  && left.end === right.end;

interface StoredSegment {
  readonly value: ListenTranscriptSegment;
  delivered: boolean;
}

/** Hermetic adapter used by the local service and WebSocket tests. */
export const createInMemoryListenStore = (): ListenStore => {
  const sessions = new Map<string, ListenSessionRecord>();
  const segments = new Map<string, Map<string, StoredSegment>>();
  const key = (accountId: string, sessionId: string): string => `${accountId}\0${sessionId}`;

  return Object.freeze({
    openOrResume(input: OpenListenSessionInput): OpenListenSessionOutcome {
      const sessionKey = key(input.accountId, input.id);
      const existing = sessions.get(sessionKey);
      if (existing !== undefined) {
        if (existing.conversationId !== input.conversationId
          || existing.clientConversationId !== input.clientConversationId) {
          throw new TypeError("listen session binding conflict");
        }
        const resumed = freezeSession({
          ...existing,
          status: "active",
          endedAt: null,
          updatedAt: input.at,
        });
        sessions.set(sessionKey, resumed);
        return Object.freeze({
          session: resumed,
          resumed: true,
          pendingSegments: this.pendingSegments(input.accountId, input.id),
        });
      }
      const session = freezeSession({
        id: input.id,
        conversationId: input.conversationId,
        clientConversationId: input.clientConversationId,
        startedAt: input.at,
        updatedAt: input.at,
        endedAt: null,
        status: "active",
        source: input.source,
        codec: input.codec,
        sampleRate: input.sampleRate,
        channels: input.channels,
      });
      sessions.set(sessionKey, session);
      segments.set(sessionKey, new Map());
      return Object.freeze({ session, resumed: false, pendingSegments: Object.freeze([]) });
    },

    appendSegment(
      accountId: string,
      sessionId: string,
      segment: ListenTranscriptSegment,
      at: string,
    ): AppendListenSegmentOutcome {
      const sessionKey = key(accountId, sessionId);
      const currentSession = sessions.get(sessionKey);
      if (currentSession === undefined) throw new TypeError("listen session not found");
      const detached = assertSegment(segment);
      const accountSegments = segments.get(sessionKey)!;
      const existing = accountSegments.get(detached.id);
      if (existing !== undefined) {
        if (!sameSegment(existing.value, detached)) {
          throw new TypeError("listen segment id conflict");
        }
        return Object.freeze({ segment: existing.value, inserted: false });
      }
      accountSegments.set(detached.id, { value: detached, delivered: false });
      sessions.set(sessionKey, freezeSession({ ...currentSession, updatedAt: at }));
      return Object.freeze({ segment: detached, inserted: true });
    },

    markDelivered(accountId: string, sessionId: string, segmentIds: readonly string[]): void {
      const accountSegments = segments.get(key(accountId, sessionId));
      if (accountSegments === undefined) return;
      for (const id of segmentIds) {
        const stored = accountSegments.get(id);
        if (stored !== undefined) stored.delivered = true;
      }
    },

    pendingSegments(accountId: string, sessionId: string): readonly ListenTranscriptSegment[] {
      const accountSegments = segments.get(key(accountId, sessionId));
      if (accountSegments === undefined) return Object.freeze([]);
      return Object.freeze(
        [...accountSegments.values()].filter((stored) => !stored.delivered).map((stored) => stored.value),
      );
    },

    closeSession(accountId, sessionId, status, at): ListenSessionRecord | null {
      const sessionKey = key(accountId, sessionId);
      const current = sessions.get(sessionKey);
      if (current === undefined) return null;
      const closed = freezeSession({ ...current, status, endedAt: at, updatedAt: at });
      sessions.set(sessionKey, closed);
      return closed;
    },

    readSession(accountId: string, sessionId: string): ListenSessionRecord | null {
      return sessions.get(key(accountId, sessionId)) ?? null;
    },

    listSegments(accountId: string, sessionId: string): readonly ListenTranscriptSegment[] {
      const accountSegments = segments.get(key(accountId, sessionId));
      return Object.freeze(accountSegments === undefined
        ? []
        : [...accountSegments.values()].map((stored) => stored.value));
    },

    reset(): void {
      sessions.clear();
      segments.clear();
    },
  });
};
