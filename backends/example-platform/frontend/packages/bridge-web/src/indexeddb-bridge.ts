/**
 * IndexedDB-backed StorageBridge. One database per (uid) — `omi-core-<uid>` —
 * so account isolation is structural (the account-switch failure class);
 * `generation` increments per open via a meta row. Log entries live in an
 * auto-increment store per log name; kv in a keyed store.
 *
 * Durability: IndexedDB commits are best-effort (browser may evict). This
 * binding is for the web surface and DEV shells; native shells bind real
 * SQLite. Guarantee narrowing is by design — see red-team finding 5.
 */

import type { DurableKv, DurableLog, LogEntry, StorageBridge } from "@omi-core/contracts";

const LOGS = "logs";
const KV = "kv";
const META = "meta";

function openDb(uid: string): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(`omi-core-${uid}`, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      const logs = db.createObjectStore(LOGS, { keyPath: ["log", "lsn"] });
      logs.createIndex("byLog", "log");
      db.createObjectStore(KV, { keyPath: ["ns", "key"] });
      db.createObjectStore(META, { keyPath: "key" });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error as Error);
  });
}

function tx<T>(db: IDBDatabase, stores: string | string[], mode: IDBTransactionMode, run: (t: IDBTransaction) => IDBRequest<T> | Promise<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    const t = db.transaction(stores, mode);
    t.onerror = () => reject(t.error as Error);
    const out = run(t);
    if (out instanceof IDBRequest) {
      out.onsuccess = () => resolve(out.result);
      out.onerror = () => reject(out.error as Error);
    } else {
      out.then(resolve, reject);
    }
  });
}

export async function openWebStorageBridge(uid: string): Promise<StorageBridge> {
  const db = await openDb(uid);
  const meta = await tx<{ key: string; value: number } | undefined>(db, META, "readwrite", (t) => {
    return new Promise((resolve, reject) => {
      const get = t.objectStore(META).get("generation");
      get.onsuccess = () => {
        const current = (get.result as { value?: number } | undefined)?.value ?? 0;
        const next = { key: "generation", value: current + 1 };
        const put = t.objectStore(META).put(next);
        put.onsuccess = () => resolve(next);
        put.onerror = () => reject(put.error as Error);
      };
      get.onerror = () => reject(get.error as Error);
    });
  });
  const generation = meta?.value ?? 1;

  return {
    uid,
    generation,
    async openLog(name: string): Promise<DurableLog> {
      return {
        async append(payload: string) {
          const last = await tx<number>(db, LOGS, "readwrite", (t) => {
            return new Promise((resolve, reject) => {
              const idx = t.objectStore(LOGS).index("byLog").openCursor(IDBKeyRange.only(name), "prev");
              idx.onsuccess = () => {
                const lsn = idx.result ? (idx.result.value as { lsn: number }).lsn : 0;
                const put = t.objectStore(LOGS).put({ log: name, lsn: lsn + 1, payload });
                put.onsuccess = () => resolve(lsn + 1);
                put.onerror = () => reject(put.error as Error);
              };
              idx.onerror = () => reject(idx.error as Error);
            });
          });
          return last;
        },
        async scan(after: number): Promise<LogEntry[]> {
          const rows = await tx<{ lsn: number; payload: string }[]>(db, LOGS, "readonly", (t) =>
            t.objectStore(LOGS).index("byLog").getAll(IDBKeyRange.only(name)) as IDBRequest<{ lsn: number; payload: string }[]>,
          );
          return rows.filter((r) => r.lsn > after).sort((a, b) => a.lsn - b.lsn);
        },
        async truncate(upTo: number): Promise<void> {
          await tx<undefined>(db, LOGS, "readwrite", (t) =>
            t.objectStore(LOGS).delete(IDBKeyRange.bound([name, 0], [name, upTo])) as IDBRequest<undefined>,
          );
        },
      };
    },
    async openKv(name: string): Promise<DurableKv> {
      return {
        async get(key: string) {
          const row = await tx<{ value: string } | undefined>(db, KV, "readonly", (t) =>
            t.objectStore(KV).get([name, key]) as IDBRequest<{ value: string } | undefined>,
          );
          return row?.value ?? null;
        },
        async set(key: string, value: string) {
          await tx(db, KV, "readwrite", (t) => t.objectStore(KV).put({ ns: name, key, value }));
        },
        async delete(key: string) {
          await tx(db, KV, "readwrite", (t) => t.objectStore(KV).delete([name, key]));
        },
      };
    },
    async destroyAll(): Promise<void> {
      db.close();
      await new Promise<void>((resolve, reject) => {
        const del = indexedDB.deleteDatabase(`omi-core-${uid}`);
        del.onsuccess = () => resolve();
        del.onerror = () => reject(del.error as Error);
      });
    },
  };
}
