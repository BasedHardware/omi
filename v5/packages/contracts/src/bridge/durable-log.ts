/**
 * Storage bridge contracts — ADR-004 D4 / ADR-008 §3.
 *
 * The core sees these interfaces and nothing else; each shell binds them to
 * its platform store (bridged system SQLite on mobile, node:sqlite or
 * better-sqlite3 on desktop, IndexedDB + Web Locks on web). The core NEVER
 * assumes browser storage is durable — on web these contracts are best-effort
 * and the sync layer's guarantees narrow accordingly (red-team finding 5).
 *
 * Durability semantics a binding MUST provide (and testkit's crash harness
 * verifies): `append` resolves only after the entry is durable; a crash
 * between append and resolve may lose the entry but never corrupts earlier
 * entries; scan order is append order; LSNs are monotonic within a log.
 */

/** Monotonic log sequence number, opaque to the core. */
export type Lsn = number;

export interface LogEntry {
  lsn: Lsn;
  /** Opaque serialized payload. The log stores bytes, not domain shapes. */
  payload: string;
}

/**
 * An append-only durable log, namespaced by (uid, name). Namespacing by uid
 * is the account-switch firewall: a log handle is bound to one uid at open
 * time and can never read or replay another account's entries.
 */
export interface DurableLog {
  append(payload: string): Promise<Lsn>;
  /** Entries with lsn > after, in order. */
  scan(after: Lsn): Promise<LogEntry[]>;
  /** Irrevocably drop entries with lsn <= upTo (confirmed/compacted). */
  truncate(upTo: Lsn): Promise<void>;
}

/** Durable key-value snapshots (projections, cursors), same uid-binding rule. */
export interface DurableKv {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
  delete(key: string): Promise<void>;
}

/**
 * What a shell hands the sync layer at open time. `generation` increments on
 * every login (even to the same account) — stores are keyed by
 * (uid, generation) where cross-login leakage would be possible.
 */
export interface StorageBridge {
  uid: string;
  generation: number;
  openLog(name: string): Promise<DurableLog>;
  openKv(name: string): Promise<DurableKv>;
  /** Wipe everything for this uid. Called by account deletion, never by sync. */
  destroyAll(): Promise<void>;
}
