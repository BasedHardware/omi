export type ActionItemRecord = {
  id: string;
  uid: string;
  description: string;
  completed: boolean;
  dueAt?: number | null;
};

export type ActionItemStore = {
  list(uid: string, limit?: number): Promise<ActionItemRecord[]>;
};

export function originActionItemStore(originBase: string, authHeader: string): ActionItemStore {
  const base = originBase.replace(/\/$/, "");
  return {
    async list(uid, limit = 50) {
      const qs = new URLSearchParams({ limit: String(limit) });
      const res = await fetch(`${base}/v1/action-items?${qs}`, {
        headers: { Authorization: authHeader, "x-omi-edge": "tasks-origin" },
      });
      if (!res.ok) throw new Error(`origin_action_items_${res.status}`);
      const body = (await res.json()) as unknown;
      const arr = Array.isArray(body)
        ? body
        : body && typeof body === "object" && Array.isArray((body as { action_items?: unknown }).action_items)
          ? (body as { action_items: unknown[] }).action_items
          : body && typeof body === "object" && Array.isArray((body as { items?: unknown }).items)
            ? (body as { items: unknown[] }).items
            : [];
      return arr
        .map((row) => {
          const r = row as Record<string, unknown>;
          const id = String(r.id ?? "");
          if (!id) return null;
          return {
            id,
            uid: String(r.uid ?? uid),
            description: String(r.description ?? r.text ?? ""),
            completed: Boolean(r.completed ?? r.done ?? false),
            dueAt: r.due_at != null ? Number(r.due_at) : r.dueAt != null ? Number(r.dueAt) : null,
          } satisfies ActionItemRecord;
        })
        .filter(Boolean) as ActionItemRecord[];
    },
  };
}
