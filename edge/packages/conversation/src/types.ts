export type ConversationRecord = {
  id: string;
  uid: string;
  summary?: string | null;
  startedAt?: number | null;
  finishedAt?: number | null;
  createdAt?: number;
};

export type ConversationStore = {
  list(uid: string, limit?: number): Promise<ConversationRecord[]>;
  get(uid: string, id: string): Promise<ConversationRecord | null>;
};

export function originConversationStore(originBase: string, authHeader: string): ConversationStore {
  const base = originBase.replace(/\/$/, "");
  return {
    async list(uid, limit = 20) {
      const qs = new URLSearchParams({ limit: String(limit) });
      const res = await fetch(`${base}/v1/conversations?${qs}`, {
        headers: { Authorization: authHeader, "x-omi-edge": "conversation-origin" },
      });
      if (!res.ok) throw new Error(`origin_conversations_${res.status}`);
      const body = (await res.json()) as unknown;
      const arr = Array.isArray(body)
        ? body
        : body && typeof body === "object" && Array.isArray((body as { conversations?: unknown }).conversations)
          ? (body as { conversations: unknown[] }).conversations
          : [];
      return arr.map((row) => normalize(row as Record<string, unknown>, uid)).filter(Boolean) as ConversationRecord[];
    },
    async get(uid, id) {
      const res = await fetch(`${base}/v1/conversations/${id}`, {
        headers: { Authorization: authHeader, "x-omi-edge": "conversation-origin" },
      });
      if (res.status === 404) return null;
      if (!res.ok) throw new Error(`origin_conversation_${res.status}`);
      return normalize((await res.json()) as Record<string, unknown>, uid);
    },
  };
}

function normalize(row: Record<string, unknown>, uid: string): ConversationRecord | null {
  if (!row) return null;
  const id = String(row.id ?? "");
  if (!id) return null;
  return {
    id,
    uid: String(row.uid ?? uid),
    summary: row.summary != null ? String(row.summary) : null,
    startedAt: row.started_at != null ? Number(row.started_at) : null,
    finishedAt: row.finished_at != null ? Number(row.finished_at) : null,
  };
}
