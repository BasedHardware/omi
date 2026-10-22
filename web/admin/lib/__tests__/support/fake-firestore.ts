/**
 * In-memory stand-in for the slice of the Firestore Admin SDK and Firebase
 * Auth that the admin routes use. Transactions buffer writes and apply them
 * on success, so a throw inside one leaves nothing behind. Like Firestore,
 * a transaction retries when a document it read changed before it committed;
 * query results are not protected that way (no phantom detection).
 */
type Data = Record<string, any>;

/** Sentinel FieldPath.documentId() for tests whose mock supplies one. */
export const DOCUMENT_ID = "__document_id__";

type Row = { id: string; data: Data; path: string };

function match(row: Row, field: string, op: string, value: unknown): boolean {
  const cell = field === DOCUMENT_ID ? row.id : row.data[field];
  switch (op) {
    case "==":
      return cell === value;
    case "!=":
      return cell !== value;
    case "in":
      return Array.isArray(value) && value.includes(cell);
    default:
      throw new Error(`FakeFirestore supports ==, != and in, got ${op}`);
  }
}

function toSnapshot(rows: Row[]) {
  const docs = rows.map((row) => ({
    id: row.id,
    ref: { path: row.path },
    data: () => structuredClone(row.data),
  }));
  return {
    docs,
    empty: docs.length === 0,
    size: docs.length,
    forEach(cb: (doc: (typeof docs)[number]) => void) {
      docs.forEach(cb);
    },
  };
}

export class FakeFirestore {
  readonly store = new Map<string, Map<string, Data>>();
  private readonly versions = new Map<string, number>();
  private nextId = 1;

  version(collection: string, id: string) {
    return this.versions.get(`${collection}/${id}`) ?? 0;
  }

  bump(collection: string, id: string) {
    this.versions.set(`${collection}/${id}`, this.version(collection, id) + 1);
  }

  table(name: string) {
    let table = this.store.get(name);
    if (!table) this.store.set(name, (table = new Map()));
    return table;
  }

  rows(name: string): (Data & { id: string })[] {
    return Array.from(this.table(name), ([id, data]) => ({ id, ...data }));
  }

  collection(name: string) {
    return new FakeQuery(this, name, [], null, null);
  }

  /**
   * Every collection named `name`, including subcollections stored as
   * "parent/{docId}/name" tables. Snapshot docs carry `ref.path` so
   * collection-group callers can tell which parent each row came from.
   */
  collectionGroup(name: string) {
    const rows: Row[] = Array.from(this.store.keys())
      .filter((table) => table === name || table.endsWith(`/${name}`))
      .flatMap((table) =>
        Array.from(this.table(table)).map(([id, data]) => ({
          id,
          data,
          path: `${table}/${id}`,
        }))
      );
    return new FakeGroupQuery(rows, [], null, null);
  }

  autoId() {
    return `auto-${String(this.nextId++).padStart(4, "0")}`;
  }

  async runTransaction<T>(fn: (tx: FakeTransaction) => Promise<T>): Promise<T> {
    for (let attempt = 0; attempt < 50; attempt++) {
      const tx = new FakeTransaction(this);
      const result = await fn(tx);
      if (tx.commit()) return result;
    }
    throw new Error("FakeFirestore transaction contention");
  }
}

export class FakeDocRef {
  constructor(
    private readonly db: FakeFirestore,
    /** The owning collection (or "parent/doc/sub" path); not a method. */
    readonly collectionName: string,
    readonly id: string
  ) {}

  /** A subcollection, stored as a "collection/{id}/name" table. */
  collection(name: string) {
    return new FakeQuery(
      this.db,
      `${this.collectionName}/${this.id}/${name}`,
      [],
      null,
      null
    );
  }

  async get() {
    const data = this.db.table(this.collectionName).get(this.id);
    return {
      id: this.id,
      exists: data !== undefined,
      data: () => (data ? structuredClone(data) : undefined),
    };
  }

  async set(data: Data) {
    this.setNow(data);
  }

  async update(data: Data) {
    this.updateNow(data);
  }

  async delete() {
    this.deleteNow();
  }

  setNow(data: Data) {
    this.db.table(this.collectionName).set(this.id, structuredClone(data));
    this.db.bump(this.collectionName, this.id);
  }

  updateNow(data: Data) {
    const table = this.db.table(this.collectionName);
    const current = table.get(this.id);
    if (!current) throw new Error(`No document to update: ${this.id}`);
    table.set(this.id, { ...current, ...structuredClone(data) });
    this.db.bump(this.collectionName, this.id);
  }

  deleteNow() {
    this.db.table(this.collectionName).delete(this.id);
    this.db.bump(this.collectionName, this.id);
  }
}

type Filter = [field: string, op: string, value: unknown];
type Order = [field: string, direction: "asc" | "desc"] | null;

function rowsOf(db: FakeFirestore, name: string): Row[] {
  return Array.from(db.table(name)).map(([id, data]) => ({
    id,
    data,
    path: `${name}/${id}`,
  }));
}

function applyFilters(rows: Row[], filters: Filter[]): Row[] {
  return rows.filter((row) =>
    filters.every(([field, op, value]) => match(row, field, op, value))
  );
}

function applyOrder(rows: Row[], order: Order): Row[] {
  if (!order) return rows;
  const [field, direction] = order;
  return [...rows].sort((a, b) => {
    const av = a.data[field];
    const bv = b.data[field];
    return (av === bv ? 0 : av < bv ? -1 : 1) * (direction === "desc" ? -1 : 1);
  });
}

class FakeQuery {
  constructor(
    private readonly db: FakeFirestore,
    private readonly name: string,
    private readonly filters: Filter[],
    private readonly order: Order,
    private readonly max: number | null
  ) {}

  doc(id?: string) {
    return new FakeDocRef(this.db, this.name, id ?? this.db.autoId());
  }

  where(field: string, op: string, value: unknown) {
    return new FakeQuery(
      this.db,
      this.name,
      [...this.filters, [field, op, value]],
      this.order,
      this.max
    );
  }

  orderBy(field: string, direction: "asc" | "desc" = "asc") {
    return new FakeQuery(
      this.db,
      this.name,
      this.filters,
      [field, direction],
      this.max
    );
  }

  limit(n: number) {
    return new FakeQuery(this.db, this.name, this.filters, this.order, n);
  }

  async get() {
    let rows = applyFilters(rowsOf(this.db, this.name), this.filters);
    rows = applyOrder(rows, this.order);
    if (this.max !== null) rows = rows.slice(0, this.max);
    return toSnapshot(rows);
  }
}

class FakeGroupQuery {
  constructor(
    private readonly rows: Row[],
    private readonly filters: Filter[],
    private readonly order: Order,
    private readonly max: number | null
  ) {}

  where(field: string, op: string, value: unknown) {
    return new FakeGroupQuery(
      this.rows,
      [...this.filters, [field, op, value]],
      this.order,
      this.max
    );
  }

  orderBy(field: string, direction: "asc" | "desc" = "asc") {
    return new FakeGroupQuery(
      this.rows,
      this.filters,
      [field, direction],
      this.max
    );
  }

  limit(n: number) {
    return new FakeGroupQuery(this.rows, this.filters, this.order, n);
  }

  async get() {
    let rows = applyFilters(this.rows, this.filters);
    rows = applyOrder(rows, this.order);
    if (this.max !== null) rows = rows.slice(0, this.max);
    return toSnapshot(rows);
  }
}

export class FakeTransaction {
  private readonly writes: (() => void)[] = [];
  private readonly reads = new Map<FakeDocRef, number>();
  private wrote = false;

  constructor(private readonly db: FakeFirestore) {}

  async get(target: FakeDocRef | { get: () => Promise<any> }) {
    // Firestore requires every read before the first write.
    if (this.wrote)
      throw new Error("Firestore transactions must read before writing");
    if (target instanceof FakeDocRef) {
      this.reads.set(target, this.db.version(target.collectionName, target.id));
    }
    return target.get();
  }

  set(ref: FakeDocRef, data: Data) {
    this.wrote = true;
    this.writes.push(() => ref.setNow(data));
    return this;
  }

  update(ref: FakeDocRef, data: Data) {
    this.wrote = true;
    this.writes.push(() => ref.updateNow(data));
    return this;
  }

  delete(ref: FakeDocRef) {
    this.wrote = true;
    this.writes.push(() => ref.deleteNow());
    return this;
  }

  /** Synchronous, so the version check and the writes are atomic. */
  commit(): boolean {
    for (const [ref, version] of Array.from(this.reads)) {
      if (this.db.version(ref.collectionName, ref.id) !== version) return false;
    }
    for (const write of this.writes) write();
    return true;
  }
}

export interface FakeUser {
  uid: string;
  email: string;
  displayName?: string;
  lastSignInTime?: string;
}

/** Firebase Auth: lookup by email, provisioning and sign-in metadata. */
export class FakeAuth {
  readonly users = new Map<string, FakeUser>();
  /** uids this fake deleted, so tests can prove no code path deletes accounts. */
  readonly deleted: string[] = [];
  private nextUid = 1;

  add(user: FakeUser) {
    this.users.set(user.uid, user);
  }

  async getUserByEmail(email: string) {
    const user = Array.from(this.users.values()).find((u) => u.email === email);
    if (!user)
      throw Object.assign(new Error("not found"), {
        code: "auth/user-not-found",
      });
    return user;
  }

  async createUser({ email }: { email: string }) {
    const user = { uid: `new-uid-${this.nextUid++}`, email };
    this.users.set(user.uid, user);
    return user;
  }

  async deleteUser(uid: string) {
    if (!this.users.has(uid))
      throw Object.assign(new Error("not found"), {
        code: "auth/user-not-found",
      });
    this.users.delete(uid);
    this.deleted.push(uid);
  }

  async getUsers(ids: { uid: string }[]) {
    return {
      users: ids
        .map(({ uid }) => this.users.get(uid))
        .filter((u): u is FakeUser => !!u)
        .map((u) => ({
          uid: u.uid,
          metadata: { lastSignInTime: u.lastSignInTime },
        })),
    };
  }
}
