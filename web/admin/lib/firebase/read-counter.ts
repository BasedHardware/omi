import { AsyncLocalStorage } from "node:async_hooks";
import { randomUUID } from "node:crypto";
import { after } from "next/server";
// Next 16's stores supply the router-owned template and request identity. Never
// use request.url or headers for labels. Keep these imports covered on upgrades.
import { workAsyncStorage } from "next/dist/server/app-render/work-async-storage.external";
import { workUnitAsyncStorage } from "next/dist/server/app-render/work-unit-async-storage.external";

type Kind = "lookup" | "not_found" | "query";
type Ledger = {
  origin: string;
  epoch: string;
  day: string;
  lookup: number;
  not_found: number;
  query: number;
  reads_by_collection: Record<string, number>;
  unscoped: number;
};
type Meta = {
  kind: string;
  collection: string;
  offset: number;
  count?: boolean;
  client?: any;
};
const scopes = new AsyncLocalStorage<Ledger>();
const requests = new WeakMap<object, Ledger>();
const proxies = new WeakMap<object, object>();
const originals = new WeakMap<object, object>();
const metadata = new WeakMap<object, Meta>();
const origins = new Set<string>();
const totals = new Map<string, number>();
const MAX_ORIGINS = 400;
let overflow = 0;
// Reviewed static collection names from admin routes. Dynamic collection names
// collapse to other. Document IDs never enter these labels.
const collections = new Set([
  "users",
  "adminData",
  "adminAuditLog",
  "adminProposals",
  "adminProposalLocks",
  "csat_ratings",
  "desktop_prompts",
  "plugins_data",
  "conversations",
  "distributors",
  "fair_use_events",
  "fair_use_state",
  "goals",
  "memories",
  "messages",
  "organisations",
  "questions",
  "versions",
  "fcm_tokens",
  "llm_usage",
]);

function boundedOrigin(origin: string): string {
  if (origin === "unset" || origin === "overflow") return origin;
  if (origins.has(origin)) return origin;
  if (origins.size >= MAX_ORIGINS) {
    overflow++;
    return "overflow";
  }
  origins.add(origin);
  return origin;
}

function ledger(origin: string): Ledger {
  return {
    origin: boundedOrigin(origin),
    epoch: randomUUID(),
    day: new Date().toISOString().slice(0, 10),
    lookup: 0,
    not_found: 0,
    query: 0,
    reads_by_collection: {},
    unscoped: 0,
  };
}

function emit(value: Ledger): void {
  try {
    console.log(
      JSON.stringify({
        event: "firestore_read_ledger",
        schema: 2,
        service: "web-admin",
        ...value,
        seq: 1,
        reads_by_origin: {
          [value.origin]: value.lookup + value.not_found + value.query,
        },
      })
    );
  } catch {
    /* Metrics cannot break a response or precompute. */
  }
}

function requestLedger(): Ledger | undefined {
  try {
    const explicit = scopes.getStore();
    if (explicit) return explicit;
    const request = workUnitAsyncStorage.getStore();
    if (!request || request.type !== "request") return undefined;
    let value = requests.get(request);
    if (!value) {
      const route = workAsyncStorage.getStore()?.route;
      value = ledger(route ? `http:${route}` : "unset");
      requests.set(request, value);
      const captured = value;
      after(() => emit(captured));
    }
    return value;
  } catch {
    return undefined;
  }
}

/** Explicit boundary for scripts/non-Next precompute runs (constant name only). */
export function withFirestoreReadLedger<T>(origin: string, run: () => T): T {
  const value = ledger(origin);
  return scopes.run(value, () => {
    try {
      const result = run();
      if (result && typeof (result as any).then === "function") {
        return Promise.resolve(result).finally(() => emit(value)) as T;
      }
      emit(value);
      return result;
    } catch (error) {
      emit(value);
      throw error;
    }
  });
}

/** Snapshot of bounded in-process billed-read counters, useful to diagnostics. */
export function firestoreReadCounts() {
  return { counts: new Map(totals), originLabelOverflow: overflow };
}

function record(
  value: Ledger | undefined,
  collection: string,
  kind: Kind,
  amount: number,
  client?: any
) {
  try {
    if (amount <= 0) return;
    const boundedCollection = collections.has(collection)
      ? collection
      : "other";
    const origin = value?.origin ?? "unset";
    const key = `${origin}|${boundedCollection}|${kind}`;
    totals.set(key, (totals.get(key) ?? 0) + amount);
    if (value) {
      let project: string | undefined;
      try {
        project = client?.projectId;
      } catch {
        /* SDK has not discovered it yet. */
      }
      if (project && project !== "based-hardware") return;
      if (!project) value.unscoped = 1;
      value[kind] += amount;
      value.reads_by_collection[boundedCollection] =
        (value.reads_by_collection[boundedCollection] ?? 0) + amount;
    }
  } catch {
    /* Never change SDK behavior on instrumentation failure. */
  }
}

function unwrap(value: any): any {
  return value && typeof value === "object"
    ? originals.get(value) ?? value
    : value;
}

function resultReads(value: Ledger | undefined, meta: Meta, result: any) {
  try {
    if (meta.kind === "aggregate") {
      const count = meta.count ? Number(result.data().count) : 0;
      record(
        value,
        meta.collection,
        "query",
        Math.max(1, Math.ceil((count || 0) / 1000)),
        meta.client
      );
    } else if (meta.kind === "query") {
      record(
        value,
        meta.collection,
        "query",
        Math.max(1, result.size + meta.offset),
        meta.client
      );
    } else if (meta.kind === "doc") {
      record(
        value,
        meta.collection,
        result.exists ? "lookup" : "not_found",
        1,
        meta.client
      );
    } else if (Array.isArray(result)) {
      for (const doc of result) {
        const parts = String(doc.ref?.path ?? "").split("/");
        record(
          value,
          parts.length > 1 ? parts[parts.length - 2] : "other",
          doc.exists ? "lookup" : "not_found",
          1,
          meta.client
        );
      }
    }
  } catch {
    /* Snapshot inspection is best effort. */
  }
}

function wrap<T extends object>(target: T, meta: Meta): T {
  if (!target || typeof target !== "object") return target;
  const existing = proxies.get(target);
  if (existing) return existing as T;
  metadata.set(target, meta);
  const proxy = new Proxy(target, {
    get(object: any, property) {
      const member = Reflect.get(object, property, object);
      // Snapshot references must come back through the facade for later reads.
      if (property === "ref" && member) {
        const parts = String(member.path ?? "").split("/");
        return wrap(member, {
          ...meta,
          kind: "doc",
          collection: parts[parts.length - 2] ?? meta.collection,
        });
      }
      if (
        (property === "parent" || property === "firestore") &&
        member &&
        typeof member === "object"
      ) {
        const parts = String(member.path ?? "").split("/");
        const kind =
          property === "firestore"
            ? "db"
            : typeof member.doc === "function"
            ? "query"
            : "doc";
        return wrap(member, {
          ...meta,
          kind,
          collection:
            kind === "query"
              ? parts[parts.length - 1]
              : parts[parts.length - 2],
          offset: 0,
        });
      }
      if (property === "docs" && Array.isArray(member)) {
        return member.map((doc) => wrap(doc, { ...meta, kind: "snapshot" }));
      }
      if (typeof member !== "function") return member;
      return (...input: any[]) => {
        const args = input.map(unwrap);
        if (property === "forEach" && meta.kind === "snapshot") {
          args[0] = (doc: object) =>
            input[0](wrap(doc, { ...meta, kind: "snapshot" }));
        }
        if (property === "runTransaction") {
          args[0] = (transaction: object) =>
            input[0](wrap(transaction, { ...meta, kind: "transaction" }));
        }
        if (
          (property === "get" &&
            ["doc", "query", "aggregate", "transaction"].includes(meta.kind)) ||
          property === "getAll"
        ) {
          const value = requestLedger();
          const readMeta =
            meta.kind === "transaction" && property === "get"
              ? metadata.get(args[0]) ?? meta
              : meta;
          // Invoke once, retaining SDK errors/retries. SDK internals see original
          // objects, so get()->stream() and transaction reads cannot double count.
          return member.apply(object, args).then(
            (result: any) => {
              resultReads(value, readMeta, result);
              if (Array.isArray(result))
                return result.map((doc) =>
                  wrap(doc, { ...readMeta, kind: "snapshot" })
                );
              return wrap(result, { ...readMeta, kind: "snapshot" });
            },
            (error: unknown) => {
              if (readMeta.kind === "query" || readMeta.kind === "aggregate") {
                record(
                  value,
                  readMeta.collection,
                  "query",
                  Math.max(1, readMeta.offset),
                  meta.client
                );
              }
              throw error;
            }
          );
        }
        const result = member.apply(object, args);
        if (property === "stream" && meta.kind === "query") {
          const value = requestLedger();
          let seen = 0;
          let finished = false;
          const originalEmit = result.emit;
          result.emit = function (event: string, ...events: any[]) {
            if (event === "data") {
              seen++;
              record(value, meta.collection, "query", 1, meta.client);
            }
            if (
              !finished &&
              (event === "end" || event === "close" || event === "error")
            ) {
              finished = true;
              record(
                value,
                meta.collection,
                "query",
                meta.offset || (seen ? 0 : 1),
                meta.client
              );
            }
            return originalEmit.call(this, event, ...events);
          };
          return result;
        }
        if (
          property === "collection" ||
          property === "collectionGroup" ||
          property === "doc"
        ) {
          const parts = String(args[0] ?? "").split("/");
          const collection =
            property === "doc"
              ? meta.kind === "db"
                ? parts[parts.length - 2]
                : meta.collection
              : parts[
                  parts.length % 2 === 1 ? parts.length - 1 : parts.length - 2
                ];
          return wrap(result, {
            ...meta,
            kind: property === "doc" ? "doc" : "query",
            collection,
            offset: 0,
          });
        }
        if (property === "count" || property === "aggregate") {
          // Arbitrary sum/avg aggregates have unknown scanned entries: floor 1.
          return wrap(result, {
            ...meta,
            kind: "aggregate",
            count: property === "count",
          });
        }
        if (property === "batch")
          return wrap(result, { ...meta, kind: "batch" });
        // Query builders return a new Query; batch/transaction writes return self.
        if (
          result &&
          typeof result === "object" &&
          typeof result.get === "function" &&
          (meta.kind === "query" ||
            (meta.kind === "doc" && property === "withConverter") ||
            result === object)
        ) {
          return wrap(result, {
            ...meta,
            offset: property === "offset" ? Number(args[0]) || 0 : meta.offset,
          });
        }
        return result;
      };
    },
  });
  proxies.set(target, proxy);
  originals.set(proxy, target);
  return proxy;
}

export function countFirestoreReads<T extends object>(db: T): T {
  // Register an after() even if this request only writes; the cached proxy can
  // safely be used by overlapping requests because attribution is read-time.
  requestLedger();
  return wrap(db, { kind: "db", collection: "other", offset: 0, client: db });
}
