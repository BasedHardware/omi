// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { EventEmitter } from "node:events";

const next = vi.hoisted(() => ({
  request: undefined as { type: "request" } | undefined,
  route: "/api/users/[uid]",
  callbacks: [] as (() => void)[],
}));
vi.mock("next/server", () => ({
  after: (callback: () => void) => next.callbacks.push(callback),
}));
vi.mock("next/dist/server/app-render/work-async-storage.external", () => ({
  workAsyncStorage: { getStore: () => ({ route: next.route }) },
}));
vi.mock("next/dist/server/app-render/work-unit-async-storage.external", () => ({
  workUnitAsyncStorage: { getStore: () => next.request },
}));

import {
  countFirestoreReads,
  firestoreReadCounts,
  withFirestoreReadLedger,
} from "./read-counter";

class Doc {
  constructor(public path: string, public exists = true) {}
  async get() {
    return {
      exists: this.exists,
      ref: this,
      data: () => ({ ok: true }),
      get: () => "field",
    };
  }
  collection(name: string) {
    return new Query(name);
  }
  set(value: object) {
    return value;
  }
}
class Query {
  constructor(public path: string, public size = 2) {}
  doc(id: string) {
    return new Doc(`${this.path}/${id}`, id !== "missing");
  }
  where() {
    return new Query(this.path, this.size);
  }
  limit(size: number) {
    return new Query(this.path, Math.min(this.size, size));
  }
  offset(_amount: number) {
    return new Query(this.path, this.size);
  }
  count() {
    return { get: async () => ({ data: () => ({ count: this.size }) }) };
  }
  async get() {
    return {
      size: this.size,
      docs: Array.from({ length: this.size }, (_, i) => ({
        exists: true,
        ref: new Doc(`${this.path}/${i}`),
      })),
    };
  }
  stream() {
    return new EventEmitter();
  }
}
class Db {
  projectId = "based-hardware";
  collection(name: string) {
    return new Query(name);
  }
  collectionGroup(name: string) {
    return new Query(name);
  }
  doc(path: string) {
    return new Doc(path);
  }
  async getAll(...refs: Doc[]) {
    return Promise.all(refs.map((ref) => ref.get()));
  }
  async runTransaction<T>(run: (tx: object) => Promise<T>) {
    return run({
      get: (ref: Doc | Query) => ref.get(),
      getAll: (...refs: Doc[]) => this.getAll(...refs),
    });
  }
  batch() {
    return {
      set: (ref: Doc, value: object) => {
        expect(ref).toBeInstanceOf(Doc);
        return value;
      },
    };
  }
}

const log = () => vi.spyOn(console, "log").mockImplementation(() => {});
const rows = (spy: ReturnType<typeof log>) =>
  spy.mock.calls.map(([row]) => JSON.parse(String(row)));
afterEach(() => {
  vi.restoreAllMocks();
  next.request = undefined;
  next.callbacks = [];
});

describe("Firestore admin read ledger", () => {
  it("counts documents, empty-query floor, offsets, misses and count/1000 once; preserves data and writes", async () => {
    const spy = log();
    const db = countFirestoreReads(new Db());
    const result = await withFirestoreReadLedger("job:math", async () => {
      const doc = await db.collection("users").doc("private-id").get();
      expect(doc.get()).toBe("field");
      expect(doc.data()).toEqual({ ok: true });
      await db.collection("users").doc("missing").get();
      await db.collection("users").offset(7).where().get();
      await db.collection("users").limit(0).get();
      const large = countFirestoreReads(new Db());
      vi.spyOn(Db.prototype, "collectionGroup").mockReturnValueOnce(
        new Query("llm_usage", 2001)
      );
      expect(
        (await large.collectionGroup("llm_usage").count().get()).data().count
      ).toBe(2001);
      await db.collection("users").limit(0).count().get();
      expect(
        db.collection("users").doc("private-id").set({ ok: true })
      ).toEqual({ ok: true });
      return "unchanged";
    });
    expect(result).toBe("unchanged");
    expect(rows(spy)).toEqual([
      expect.objectContaining({
        event: "firestore_read_ledger",
        service: "web-admin",
        schema: 2,
        origin: "job:math",
        lookup: 1,
        not_found: 1,
        query: 14,
        seq: 1,
        reads_by_collection: { users: 13, llm_usage: 3 },
      }),
    ]);
    expect(firestoreReadCounts().counts.get("job:math|users|query")).toBe(11);
  });

  it("groups getDb-style facade calls by request and uses the route template", async () => {
    const spy = log();
    const raw = new Db();
    next.request = { type: "request" };
    const db = countFirestoreReads(raw);
    await db.collection("users").doc("secret-one").get();
    await countFirestoreReads(raw).collection("users").doc("secret-two").get();
    expect(next.callbacks).toHaveLength(1);
    next.callbacks[0]();
    expect(rows(spy)[0]).toMatchObject({
      origin: "http:/api/users/[uid]",
      lookup: 2,
    });
    expect(spy.mock.calls[0][0]).not.toContain("secret");
    next.request = { type: "request" };
    await db.collectionGroup("llm_usage").count().get();
    expect(next.callbacks).toHaveLength(2);
    next.callbacks[1]();
    expect(rows(spy)[1]).toMatchObject({ lookup: 0, query: 1 });
    expect(rows(spy)[0].epoch).not.toBe(rows(spy)[1].epoch);
  });

  it("isolates overlapping precompute runs through a shared facade", async () => {
    const spy = log();
    const db = countFirestoreReads(new Db());
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const first = withFirestoreReadLedger("job:first", async () => {
      await gate;
      await db.collection("users").get();
    });
    await withFirestoreReadLedger("job:second", () =>
      db.collectionGroup("fcm_tokens").get()
    );
    release();
    await first;
    expect(rows(spy)).toEqual([
      expect.objectContaining({
        origin: "job:second",
        reads_by_collection: { fcm_tokens: 2 },
      }),
      expect.objectContaining({
        origin: "job:first",
        reads_by_collection: { users: 2 },
      }),
    ]);
  });

  it("counts transactions and getAll without double counting, unwrapping references", async () => {
    const spy = log();
    const db = countFirestoreReads(new Db());
    await withFirestoreReadLedger("job:transaction", async () => {
      const doc = db.doc("users/private-id");
      await db.getAll(doc, db.doc("users/missing"));
      await db.runTransaction(async (tx: any) => {
        await tx.get(doc);
        await tx.get(db.collection("users"));
      });
      expect(db.batch().set(doc, { ok: true })).toEqual({ ok: true });
      const snapshot = await doc.get();
      await snapshot.ref.get();
    });
    expect(rows(spy)[0]).toMatchObject({ lookup: 5, query: 2 });
  });

  it("counts streams without changing flow or event delivery", async () => {
    const spy = log();
    await withFirestoreReadLedger("job:stream", async () => {
      const db = countFirestoreReads(new Db());
      const stream = db.collection("users").offset(5).stream();
      const received = vi.fn();
      stream.on("data", received);
      stream.emit("data", { id: "one" });
      stream.emit("end");
      stream.emit("close");
      db.collection("users").stream().emit("end");
      expect(received).toHaveBeenCalledTimes(1);
    });
    expect(rows(spy)[0]).toMatchObject({ query: 7 });
  });

  it("retains application errors, flushes on failure, and swallows logging errors", async () => {
    const spy = log();
    const error = new Error("SDK failure");
    await expect(
      withFirestoreReadLedger("job:failure", async () => {
        throw error;
      })
    ).rejects.toBe(error);
    expect(spy).toHaveBeenCalledTimes(1);
    spy.mockImplementation(() => {
      throw new Error("logger failed");
    });
    await expect(
      withFirestoreReadLedger("job:logging", () =>
        countFirestoreReads(new Db()).collection("users").get()
      )
    ).resolves.toMatchObject({ size: 2 });
    expect(() =>
      withFirestoreReadLedger("job:sync-failure", () => {
        throw error;
      })
    ).toThrow(error);
  });

  it("works with real Admin SDK builders, converters, cursors and batched writes without issuing RPCs", async () => {
    const spy = log();
    const {
      Firestore,
      DocumentReference,
      Query: SdkQuery,
    } = await import("firebase-admin/firestore");
    const sdk = new Firestore({ projectId: "based-hardware" });
    const get = vi
      .spyOn(DocumentReference.prototype, "get")
      .mockImplementation(async function (this: any) {
        return {
          exists: true,
          ref: this,
          data: () => ({ ok: true }),
          get: () => "field",
        } as any;
      });
    vi.spyOn(SdkQuery.prototype, "get").mockResolvedValue({
      size: 2,
      docs: [],
    } as any);
    const db = countFirestoreReads(sdk);
    await withFirestoreReadLedger("job:real-sdk", async () => {
      const ref = db.doc("users/private-user");
      expect(ref.isEqual(db.collection("users").doc("private-user"))).toBe(
        true
      );
      const snapshot = await ref.get();
      expect(snapshot.get("ok")).toBe("field");
      await snapshot.ref.get();
      await ref.withConverter(null).get();
      await db
        .collection("users")
        .where("active", "==", true)
        .orderBy("created_at")
        .offset(3)
        .limit(2)
        .get();
      db.batch().set(ref, { linked: ref }).update(ref, { active: true });
      expect(get).toHaveBeenCalledTimes(3);
    });
    expect(rows(spy)[0]).toMatchObject({ lookup: 3, query: 5 });
  });

  it("preserves SDK rejection identity and the failed-query floor", async () => {
    const spy = log();
    const error = new Error("SDK rejected");
    vi.spyOn(Query.prototype, "get").mockRejectedValue(error);
    await expect(
      withFirestoreReadLedger("job:sdk-error", () =>
        countFirestoreReads(new Db()).collection("users").get()
      )
    ).rejects.toBe(error);
    expect(rows(spy)[0]).toMatchObject({ query: 1 });
  });

  it("keeps the bill ledger scoped to production and flags unknown project identity", async () => {
    const spy = log();
    const development = new Db();
    development.projectId = "s1-development";
    await withFirestoreReadLedger("job:nonprod", () =>
      countFirestoreReads(development).collection("users").get()
    );
    const unknown = new Db();
    Object.defineProperty(unknown, "projectId", {
      get: () => {
        throw new Error("not initialized");
      },
    });
    await withFirestoreReadLedger("job:unknown-project", () =>
      countFirestoreReads(unknown).collection("users").get()
    );
    expect(rows(spy)[0]).toMatchObject({
      query: 0,
      reads_by_collection: {},
      unscoped: 0,
    });
    expect(rows(spy)[1]).toMatchObject({
      query: 2,
      reads_by_collection: { users: 2 },
      unscoped: 1,
    });
  });

  it("bounds origins and dynamic collections", async () => {
    const spy = log();
    for (let i = 0; i < 405; i++) {
      await withFirestoreReadLedger(`job:overflow_${i}`, () =>
        countFirestoreReads(new Db()).collection(`private-${i}`).get()
      );
    }
    expect(rows(spy).at(-1)).toMatchObject({
      origin: "overflow",
      reads_by_collection: { other: 2 },
    });
    expect(firestoreReadCounts().originLabelOverflow).toBeGreaterThan(0);
    expect(
      Array.from(firestoreReadCounts().counts.keys()).some((key) =>
        key.includes("private-")
      )
    ).toBe(false);
  });
});
