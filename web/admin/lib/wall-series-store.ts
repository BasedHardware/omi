/** Shared state for the Omi TV series fill, so up to 100 Cloud Run instances
 * converge instead of each starting its own cold PostHog fill.
 *
 * - Leg last-good docs: any instance serves the latest shared value at once.
 * - Leases: one instance refreshes a leg at a time; the holder renews while it
 *   runs, and a dead holder's lease lapses after `LEASE_MS`.
 * - Read memo: each successful PostHog read is kept for its UTC day, so a fill
 *   abandoned by one instance resumes on the next without re-reading.
 *
 * Firestore via the existing admin payload cache (`admin_stats_payload_cache`);
 * aggregates only. Every call fails open to process-local behaviour.
 */
import { createHash, randomUUID } from "crypto";
import { getPayload, setPayload } from "./payload-cache";

export const LEASE_MS = 3 * 60_000;
export const STORE_PREFIX = "wall-series:v1";
export const INSTANCE_ID = `${
  process.env.K_REVISION || "local"
}:${randomUUID().slice(0, 8)}`;

export interface SeriesStore {
  get<T>(key: string): Promise<{ data: T; freshAt: number } | null>;
  set(key: string, data: unknown): Promise<void>;
  /** Take or renew the lease; true when `holder` owns it afterwards. */
  lease(key: string, holder: string, now: number): Promise<boolean>;
  release(key: string, holder: string): Promise<void>;
}

export const legKey = (leg: string) => `${STORE_PREFIX}:leg:${leg}`;
export const leaseKey = (leg: string) => `${STORE_PREFIX}:lease:${leg}`;
export const readKey = (day: string, sql: string) =>
  `${STORE_PREFIX}:read:${day}:${createHash("sha1").update(sql).digest("hex")}`;

const LEASE_COLLECTION = "admin_stats_payload_cache";

export const firestoreSeriesStore: SeriesStore = {
  get: (key) => getPayload(key),
  set: (key, data) => setPayload(key, data),
  async lease(key, holder, now) {
    try {
      const { getDb } = await import("@/lib/firebase/admin");
      const db = getDb();
      const ref = db.collection(LEASE_COLLECTION).doc(key);
      return await db.runTransaction(async (tx) => {
        const doc = await tx.get(ref);
        const lease = doc.exists
          ? (doc.data() as { holder?: string; until?: number })
          : null;
        if (lease && lease.holder !== holder && (lease.until ?? 0) > now)
          return false;
        tx.set(ref, { holder, until: now + LEASE_MS });
        return true;
      });
    } catch {
      return true; // no shared store: refresh locally, as before
    }
  },
  async release(key, holder) {
    try {
      const { getDb } = await import("@/lib/firebase/admin");
      const db = getDb();
      const ref = db.collection(LEASE_COLLECTION).doc(key);
      await db.runTransaction(async (tx) => {
        const doc = await tx.get(ref);
        if (doc.exists && doc.data()?.holder === holder) tx.delete(ref);
      });
    } catch {
      // the lease lapses on its own
    }
  },
};

/** In-memory store with the same semantics (tests, local runs). */
export function memorySeriesStore(): SeriesStore & {
  docs: Map<string, { data: unknown; freshAt: number }>;
  leases: Map<string, { holder: string; until: number }>;
} {
  const docs = new Map<string, { data: unknown; freshAt: number }>();
  const leases = new Map<string, { holder: string; until: number }>();
  return {
    docs,
    leases,
    async get<T>(key: string) {
      const hit = docs.get(key);
      return hit
        ? {
            data: JSON.parse(JSON.stringify(hit.data)) as T,
            freshAt: hit.freshAt,
          }
        : null;
    },
    async set(key, data) {
      docs.set(key, {
        data: JSON.parse(JSON.stringify(data)),
        freshAt: Date.now(),
      });
    },
    async lease(key, holder, now) {
      const lease = leases.get(key);
      if (lease && lease.holder !== holder && lease.until > now) return false;
      leases.set(key, { holder, until: now + LEASE_MS });
      return true;
    },
    async release(key, holder) {
      if (leases.get(key)?.holder === holder) leases.delete(key);
    },
  };
}
