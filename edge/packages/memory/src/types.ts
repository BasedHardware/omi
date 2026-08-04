/** Domain contracts — mirror backend/models/memories.py core fields. */

export type MemoryCategory =
  | "interesting"
  | "system"
  | "manual"
  | "workflow"
  | "core"
  | "hobbies"
  | "lifestyle"
  | "interests"
  | "habits"
  | "work"
  | "skills"
  | "learnings"
  | "other"
  | "auto";

export type MemoryRecord = {
  id: string;
  uid: string;
  content: string;
  category: MemoryCategory;
  visibility?: string;
  tags?: string[];
  headline?: string | null;
  createdAt?: number;
  updatedAt?: number;
};

export type ListMemoriesInput = {
  uid: string;
  limit?: number;
  search?: string;
  category?: string;
};

export type MemoryStore = {
  list(input: ListMemoriesInput): Promise<MemoryRecord[]>;
  get(uid: string, id: string): Promise<MemoryRecord | null>;
};

/** Origin (Python API) adapter — no local DB yet. */
export function originMemoryStore(originBase: string, authHeader: string): MemoryStore {
  const base = originBase.replace(/\/$/, "");
  return {
    async list(input) {
      const qs = new URLSearchParams();
      if (input.limit) qs.set("limit", String(input.limit));
      if (input.search) qs.set("search", input.search);
      if (input.category) qs.set("category", input.category);
      const res = await fetch(`${base}/v3/memories?${qs}`, {
        headers: { Authorization: authHeader, "x-omi-edge": "memory-origin" },
      });
      if (!res.ok) throw new Error(`origin_memories_${res.status}`);
      const body = (await res.json()) as unknown;
      return normalizeMemoryList(body, input.uid);
    },
    async get(uid, id) {
      const res = await fetch(`${base}/v3/memories/${id}`, {
        headers: { Authorization: authHeader, "x-omi-edge": "memory-origin" },
      });
      if (res.status === 404) return null;
      if (!res.ok) throw new Error(`origin_memory_${res.status}`);
      const body = (await res.json()) as Record<string, unknown>;
      return normalizeMemory(body, uid);
    },
  };
}

function normalizeMemoryList(body: unknown, uid: string): MemoryRecord[] {
  const arr = Array.isArray(body)
    ? body
    : body && typeof body === "object" && Array.isArray((body as { memories?: unknown }).memories)
      ? (body as { memories: unknown[] }).memories
      : [];
  return arr
    .map((row) => normalizeMemory(row as Record<string, unknown>, uid))
    .filter((m): m is MemoryRecord => m !== null);
}

function normalizeMemory(row: Record<string, unknown>, uid: string): MemoryRecord | null {
  if (!row || typeof row !== "object") return null;
  const id = String(row.id ?? row.memory_id ?? "");
  const content = String(row.content ?? "");
  if (!id && !content) return null;
  return {
    id: id || "unknown",
    uid: String(row.uid ?? uid),
    content,
    category: (String(row.category ?? "interesting") as MemoryCategory) || "interesting",
    visibility: row.visibility != null ? String(row.visibility) : undefined,
    tags: Array.isArray(row.tags) ? row.tags.map(String) : undefined,
    headline: row.headline != null ? String(row.headline) : null,
  };
}
