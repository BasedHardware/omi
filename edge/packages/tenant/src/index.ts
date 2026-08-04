/**
 * Per-user tenant routing: control-plane map uid → logical DB + vector index.
 * Provider-agnostic: store is injected (KV, D1 control table, memory Map).
 */

import type { KvStore } from "@omi/platform";

export type TenantRecord = {
  uid: string;
  /** Logical DB id (D1 uuid, shard id, or other provider handle) */
  d1DatabaseId: string;
  vectorizeIndex: string;
  aiSearchIndex?: string;
  createdAt: number;
  status: "active" | "migrating" | "disabled";
};

export type TenantStore = {
  get(uid: string): Promise<TenantRecord | null>;
  put(record: TenantRecord): Promise<void>;
};

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

export function kvTenantStore(kv: KvStore): TenantStore {
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
