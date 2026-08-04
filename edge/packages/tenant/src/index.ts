/**
 * Per-user tenant routing: control-plane map uid → D1 database id + Vectorize index.
 *
 * Phase 1: in-memory / KV map. Phase 2: Cloudflare API create D1 per user (or shard).
 * D1 account limits mean real prod may shard many uids per D1; interface stays per-uid lookup.
 */

export type TenantRecord = {
  uid: string;
  /** Cloudflare D1 database id (UUID) or logical shard id */
  d1DatabaseId: string;
  /** Vectorize index name for this tenant (or shared index + uid filter) */
  vectorizeIndex: string;
  /** AI Search index / namespace when enabled */
  aiSearchIndex?: string;
  createdAt: number;
  status: "active" | "migrating" | "disabled";
};

export type TenantStore = {
  get(uid: string): Promise<TenantRecord | null>;
  put(record: TenantRecord): Promise<void>;
};

/** Deterministic shard key for multi-tenant D1 until 1:1 D1 is viable. */
export function shardIdForUid(uid: string, shardCount: number): string {
  if (shardCount < 1) throw new Error("shardCount must be >= 1");
  let h = 2166136261;
  for (let i = 0; i < uid.length; i++) {
    h ^= uid.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  const n = (h >>> 0) % shardCount;
  return `shard_${String(n).padStart(4, "0")}`;
}

export function defaultTenantRecord(
  uid: string,
  opts: { shardCount?: number; vectorizeIndex?: string; aiSearchIndex?: string } = {},
): TenantRecord {
  const shardCount = opts.shardCount ?? 64;
  const shard = shardIdForUid(uid, shardCount);
  return {
    uid,
    d1DatabaseId: shard,
    vectorizeIndex: opts.vectorizeIndex ?? `omi-memories-${shard}`,
    aiSearchIndex: opts.aiSearchIndex ?? `omi-search-${shard}`,
    createdAt: Date.now(),
    status: "active",
  };
}

/** KV-backed store (Workers). key = `tenant:${uid}` */
export function kvTenantStore(kv: KVNamespace): TenantStore {
  return {
    async get(uid: string) {
      const raw = await kv.get(`tenant:${uid}`, "json");
      return (raw as TenantRecord | null) ?? null;
    },
    async put(record: TenantRecord) {
      await kv.put(`tenant:${record.uid}`, JSON.stringify(record));
    },
  };
}

/** Ensure tenant row exists (lazy provision metadata only — no D1 create API here). */
export async function ensureTenant(
  store: TenantStore,
  uid: string,
  opts?: { shardCount?: number; vectorizeIndex?: string; aiSearchIndex?: string },
): Promise<TenantRecord> {
  const existing = await store.get(uid);
  if (existing) return existing;
  const created = defaultTenantRecord(uid, opts);
  await store.put(created);
  return created;
}

/** Minimal per-user D1 schema (apply via migration runner later). */
export const USER_D1_SCHEMA_SQL = `
CREATE TABLE IF NOT EXISTS memories (
  id TEXT PRIMARY KEY,
  uid TEXT NOT NULL,
  category TEXT,
  content TEXT NOT NULL,
  visibility TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_uid_created ON memories(uid, created_at DESC);

CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY,
  uid TEXT NOT NULL,
  started_at INTEGER,
  finished_at INTEGER,
  summary TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conversations_uid_started ON conversations(uid, started_at DESC);

CREATE TABLE IF NOT EXISTS action_items (
  id TEXT PRIMARY KEY,
  uid TEXT NOT NULL,
  description TEXT NOT NULL,
  completed INTEGER NOT NULL DEFAULT 0,
  due_at INTEGER,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_action_items_uid ON action_items(uid, completed, due_at);
`;
