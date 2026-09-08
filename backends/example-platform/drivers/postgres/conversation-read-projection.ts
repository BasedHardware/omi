import type {
  ConversationRecord,
  OrderedConversationRecord,
} from "../../apps/service/stores/conversations-store";

export interface ConversationReadSnapshot {
  readonly revision: number;
  readonly records: readonly OrderedConversationRecord[];
}

const integer = (value: unknown): number => {
  const parsed =
    typeof value === "string" && /^[0-9]+$/.test(value) ? Number(value) : value;
  if (typeof parsed !== "number" || !Number.isSafeInteger(parsed) || parsed < 0)
    throw new TypeError("conversation_snapshot_invalid");
  return parsed;
};
const instant = (value: unknown): string => {
  if (typeof value !== "string" || !Number.isFinite(Date.parse(value)))
    throw new TypeError("conversation_snapshot_invalid");
  return new Date(value).toISOString();
};
export function parseConversationReadSnapshot(
  value: unknown
): ConversationReadSnapshot {
  if (value === null || typeof value !== "object" || Array.isArray(value))
    throw new TypeError("conversation_snapshot_invalid");
  const snapshot = value as Record<string, unknown>;
  const revision = integer(snapshot.revision);
  if (!Array.isArray(snapshot.records) || snapshot.records.length > 10000)
    throw new TypeError("conversation_snapshot_unavailable");
  const ids = new Set<string>();
  const visibleIds = new Set<string>();
  let previousSequence = 0;
  const records = snapshot.records.map(
    (value: unknown): OrderedConversationRecord => {
      if (value === null || typeof value !== "object" || Array.isArray(value))
        throw new TypeError("conversation_snapshot_invalid");
      const row = value as Record<string, unknown>;
      if (
        typeof row.session_id !== "string" ||
        !/^[!-~]{1,256}$/.test(row.session_id) ||
        typeof row.device !== "boolean" ||
        typeof row.conversation_id !== "string" ||
        !/^[!-~]{1,256}$/.test(row.conversation_id) ||
        (row.device &&
          !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(
            row.session_id
          )) ||
        !(row.source === null || typeof row.source === "string") ||
        ids.has(row.session_id) ||
        !["queued", "running", "completed", "failed"].includes(
          String(row.state)
        ) ||
        typeof row.locked !== "boolean" ||
        !(row.excerpt === null || typeof row.excerpt === "string") ||
        (typeof row.excerpt === "string" && row.excerpt.length > 480) ||
        (row.state === "completed" && typeof row.excerpt !== "string")
      )
        throw new TypeError("conversation_snapshot_invalid");
      ids.add(row.session_id);
      const sequence = integer(row.sequence);
      if (sequence <= previousSequence)
        throw new TypeError("conversation_snapshot_invalid");
      previousSequence = sequence;
      const startedAt = instant(row.started_at),
        endedAt = instant(row.ended_at),
        updatedAt = instant(row.updated_at);
      const capturedAtMs =
        row.captured_at_ms == null ? undefined : integer(row.captured_at_ms);
      if (
        capturedAtMs !== undefined &&
        (!row.device || capturedAtMs > 8640000000000000)
      )
        throw new TypeError("conversation_snapshot_invalid");
      if (
        Date.parse(endedAt) < Date.parse(startedAt) ||
        Date.parse(updatedAt) < Date.parse(startedAt)
      )
        throw new TypeError("conversation_snapshot_invalid");
      const excerpt =
        row.state === "completed"
          ? String(row.excerpt).trim().slice(0, 240)
          : "";
      const id = row.device
        ? `recording:${row.session_id}`
        : row.conversation_id;
      if (visibleIds.has(id))
        throw new TypeError("conversation_snapshot_invalid");
      visibleIds.add(id);
      const record: ConversationRecord = Object.freeze({
        id,
        structured: Object.freeze({
          title: excerpt ? excerpt.slice(0, 80) : "",
          overview: excerpt,
        }),
        created_at: startedAt,
        started_at: startedAt,
        ...(capturedAtMs === undefined ? {} : { captured_at_ms: capturedAtMs }),
        finished_at: endedAt,
        updated_at: updatedAt,
        source: row.device ? "omi" : (row.source as string | null) ?? "listen",
        status:
          row.state === "failed"
            ? "failed"
            : row.state === "completed" && !row.locked
            ? "completed"
            : "processing",
        discarded: false,
        starred: false,
        visibility: "private",
        is_locked: row.locked,
        folder_id: null,
      });
      return Object.freeze({ record, sequence });
    }
  );
  if (records.length > 0 && revision === 0)
    throw new TypeError("conversation_snapshot_invalid");
  return Object.freeze({ revision, records: Object.freeze(records) });
}
