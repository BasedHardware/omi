/** Shared state for the Omi TV series fill, so up to 100 Cloud Run instances
 * converge instead of each starting its own cold PostHog fill.
 *
 * - Leg docs: last-good value, retry schedule and the UTC day's successful
 *   PostHog reads (keyed by SQL hash). Any instance serves them at once, and a
 *   fill one instance abandons resumes from the persisted reads.
 * - Fenced leases: `acquire` returns a fresh token only when no live lease
 *   exists. Every leg-doc write is a transaction that checks the lease still
 *   carries that token and has not expired, so a holder that lost its lease
 *   can never write. Unknown lease state (timeout, error) is never ownership.
 * - Merge, never replace: writes union the stored reads for the same day
 *   (newer entry per hash wins), so a slow writer cannot drop completed reads.
 *
 * Firestore via the existing admin payload cache (`admin_stats_payload_cache`,
 * `{payload, freshAt}` docs); aggregates only.
 */
import { randomUUID } from "crypto";

export const LEASE_MS = 3 * 60_000;
export const STORE_PREFIX = "wall-series:v1";
export const INSTANCE_ID = `${
  process.env.K_REVISION || "local"
}:${randomUUID().slice(0, 8)}`;

export const legKey = (leg: string) => `${STORE_PREFIX}:leg:${leg}`;
export const leaseKey = (leg: string) => `${STORE_PREFIX}:lease:${leg}`;

export interface StoredRead {
  rows: unknown[][];
  refreshedAt: string | null;
  /** When this instance fetched it (epoch ms); the newer entry wins a merge. */
  at: number;
}
export interface LegDoc<E = unknown> {
  entry: E | null;
  reads: { day: string; rows: Record<string, StoredRead> };
}
/** A write: reads to union in, and the entry to set (omitted = keep stored). */
export interface LegPatch<E = unknown> {
  entry?: E | null;
  reads: { day: string; rows: Record<string, StoredRead> };
}
interface Lease {
  holder: string;
  token: string;
  until: number;
}
export type LeaseResult =
  | { status: "acquired"; token: string }
  | { status: "contended"; holder: string; until: number }
  | { status: "unavailable" };
export type WriteResult = "written" | "fenced" | "unavailable";

export interface SeriesStore {
  /** The leg doc, or null when absent. Throws when the store is unreachable. */
  read<E>(leg: string): Promise<LegDoc<E> | null>;
  /** Never throws: errors are "unavailable", a live lease is "contended". */
  acquire(leg: string, holder: string, now: number): Promise<LeaseResult>;
  /** Extend my lease; false when it is no longer mine or the store failed. */
  renew(leg: string, token: string, now: number): Promise<boolean>;
  /** Fenced merge write: applied only while `token` holds a live lease. */
  write<E>(
    leg: string,
    token: string,
    patch: LegPatch<E>,
    now: number
  ): Promise<WriteResult>;
  /** Delete the lease only if it still carries `token`. */
  release(leg: string, token: string): Promise<void>;
}

/** Union reads for the same UTC day (newer per hash); a newer day replaces. */
export function mergeLegDoc<E>(
  stored: LegDoc<E> | null,
  patch: LegPatch<E>
): LegDoc<E> {
  const base = stored?.reads;
  let reads: LegDoc<E>["reads"];
  if (!base || patch.reads.day > base.day) reads = patch.reads;
  else if (patch.reads.day < base.day) reads = base;
  else {
    const rows = { ...base.rows };
    for (const [hash, read] of Object.entries(patch.reads.rows))
      if (!rows[hash] || read.at >= rows[hash].at) rows[hash] = read;
    reads = { day: base.day, rows };
  }
  return {
    entry: patch.entry !== undefined ? patch.entry : stored?.entry ?? null,
    reads,
  };
}

/** Minimal transactional key–value backend (Firestore or memory). */
interface Txn {
  get(key: string): Promise<unknown | null>;
  set(key: string, value: unknown): void;
  delete(key: string): void;
}
interface Backend {
  get(key: string): Promise<unknown | null>;
  transact<T>(fn: (tx: Txn) => Promise<T>): Promise<T>;
}

const live = (lease: Lease | null, now: number): lease is Lease =>
  Boolean(lease && lease.until > now);

function storeOver(backend: Backend): SeriesStore {
  return {
    async read<E>(leg: string) {
      return (await backend.get(legKey(leg))) as LegDoc<E> | null;
    },
    async acquire(leg, holder, now) {
      try {
        return await backend.transact(async (tx) => {
          const lease = (await tx.get(leaseKey(leg))) as Lease | null;
          if (live(lease, now))
            return {
              status: "contended" as const,
              holder: lease.holder,
              until: lease.until,
            };
          const token = randomUUID();
          tx.set(leaseKey(leg), { holder, token, until: now + LEASE_MS });
          return { status: "acquired" as const, token };
        });
      } catch {
        return { status: "unavailable" };
      }
    },
    async renew(leg, token, now) {
      try {
        return await backend.transact(async (tx) => {
          const lease = (await tx.get(leaseKey(leg))) as Lease | null;
          if (!live(lease, now) || lease.token !== token) return false;
          tx.set(leaseKey(leg), { ...lease, until: now + LEASE_MS });
          return true;
        });
      } catch {
        return false;
      }
    },
    async write(leg, token, patch, now) {
      try {
        return await backend.transact(async (tx) => {
          const lease = (await tx.get(leaseKey(leg))) as Lease | null;
          const stored = (await tx.get(legKey(leg))) as LegDoc | null;
          if (!live(lease, now) || lease.token !== token)
            return "fenced" as const;
          tx.set(legKey(leg), mergeLegDoc(stored, patch));
          return "written" as const;
        });
      } catch {
        return "unavailable";
      }
    },
    async release(leg, token) {
      try {
        await backend.transact(async (tx) => {
          const lease = (await tx.get(leaseKey(leg))) as Lease | null;
          if (lease?.token === token) tx.delete(leaseKey(leg));
        });
      } catch {
        // the lease lapses on its own
      }
    },
  };
}

const COLLECTION = "admin_stats_payload_cache";
// Same `{payload, freshAt}` shape as lib/payload-cache.ts docs.
const decode = (data: { payload?: string } | undefined) =>
  data?.payload ? JSON.parse(data.payload) : null;
const encode = (value: unknown) => ({
  payload: JSON.stringify(value),
  freshAt: Date.now(),
});

export const firestoreSeriesStore: SeriesStore = storeOver({
  async get(key) {
    const { getDb } = await import("@/lib/firebase/admin");
    const snap = await getDb().collection(COLLECTION).doc(key).get();
    return snap.exists ? decode(snap.data()) : null;
  },
  async transact(fn) {
    const { getDb } = await import("@/lib/firebase/admin");
    const db = getDb();
    const ref = (key: string) => db.collection(COLLECTION).doc(key);
    return db.runTransaction((t) =>
      fn({
        get: async (key) => {
          const snap = await t.get(ref(key));
          return snap.exists ? decode(snap.data()) : null;
        },
        set: (key, value) => void t.set(ref(key), encode(value)),
        delete: (key) => void t.delete(ref(key)),
      })
    );
  },
});

/** In-memory store with the same semantics (tests, per-process fallback). */
export function memorySeriesStore(): SeriesStore & {
  docs: Map<string, unknown>;
} {
  const docs = new Map<string, unknown>();
  let chain: Promise<unknown> = Promise.resolve();
  const copy = (v: unknown) =>
    v === undefined || v === null ? null : JSON.parse(JSON.stringify(v));
  return Object.assign(
    storeOver({
      async get(key) {
        return copy(docs.get(key));
      },
      transact<T>(fn: (tx: Txn) => Promise<T>) {
        // Serialized like Firestore's isolation: writes apply after `fn`.
        const run = chain.then(async () => {
          const writes: [string, unknown][] = [];
          const out = await fn({
            get: async (key) => copy(docs.get(key)),
            set: (key, value) => void writes.push([key, copy(value)]),
            delete: (key) => void writes.push([key, undefined]),
          });
          for (const [key, value] of writes)
            value === undefined ? docs.delete(key) : docs.set(key, value);
          return out;
        });
        chain = run.catch(() => undefined);
        return run;
      },
    }),
    { docs }
  );
}

/** Reads the shared store; leases and writes stay in `local`. A dev server
 * (no `K_REVISION`) serves the TV's shared legs but fills whatever is missing
 * or due in its own memory, so it never writes production docs, whatever
 * identity it runs as. Its own fills win over the shared doc it read. */
export function readThroughStore(
  shared: SeriesStore,
  local: SeriesStore = memorySeriesStore()
): SeriesStore {
  return {
    read: async <E>(leg: string) =>
      (await local.read<E>(leg)) ?? shared.read<E>(leg),
    acquire: (leg, holder, now) => local.acquire(leg, holder, now),
    renew: (leg, token, now) => local.renew(leg, token, now),
    write: (leg, token, patch, now) => local.write(leg, token, patch, now),
    release: (leg, token) => local.release(leg, token),
  };
}
