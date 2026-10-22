/**
 * In-memory stand-in for the slice of the Firestore Admin SDK and Firebase
 * Auth that the team roster uses. Transactions buffer writes and apply them
 * on success, so a throw inside one leaves nothing behind.
 */
type Data = Record<string, any>;

export class FakeFirestore {
  readonly store = new Map<string, Map<string, Data>>();
  private nextId = 1;

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

  autoId() {
    return `auto-${String(this.nextId++).padStart(4, "0")}`;
  }

  async runTransaction<T>(fn: (tx: FakeTransaction) => Promise<T>): Promise<T> {
    const tx = new FakeTransaction();
    const result = await fn(tx);
    await tx.apply();
    return result;
  }
}

export class FakeDocRef {
  constructor(
    private readonly db: FakeFirestore,
    readonly collection: string,
    readonly id: string
  ) {}

  async get() {
    const data = this.db.table(this.collection).get(this.id);
    return {
      id: this.id,
      exists: data !== undefined,
      data: () => (data ? structuredClone(data) : undefined),
    };
  }

  async set(data: Data) {
    this.db.table(this.collection).set(this.id, structuredClone(data));
  }

  async update(data: Data) {
    const table = this.db.table(this.collection);
    const current = table.get(this.id);
    if (!current) throw new Error(`No document to update: ${this.id}`);
    table.set(this.id, { ...current, ...structuredClone(data) });
  }

  async delete() {
    this.db.table(this.collection).delete(this.id);
  }
}

class FakeQuery {
  constructor(
    private readonly db: FakeFirestore,
    private readonly name: string,
    private readonly filters: [string, unknown][],
    private readonly order: [string, "asc" | "desc"] | null,
    private readonly max: number | null
  ) {}

  doc(id?: string) {
    return new FakeDocRef(this.db, this.name, id ?? this.db.autoId());
  }

  where(field: string, op: string, value: unknown) {
    if (op !== "==")
      throw new Error(`FakeFirestore supports == only, got ${op}`);
    return new FakeQuery(
      this.db,
      this.name,
      [...this.filters, [field, value]],
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
    let rows = Array.from(this.db.table(this.name)).filter(([, data]) =>
      this.filters.every(([field, value]) => data[field] === value)
    );
    if (this.order) {
      const [field, direction] = this.order;
      rows.sort(([, a], [, b]) =>
        a[field] === b[field]
          ? 0
          : (a[field] < b[field] ? -1 : 1) * (direction === "desc" ? -1 : 1)
      );
    }
    if (this.max !== null) rows = rows.slice(0, this.max);
    const docs = rows.map(([id, data]) => ({
      id,
      data: () => structuredClone(data),
    }));
    return { docs, empty: docs.length === 0, size: docs.length };
  }
}

export class FakeTransaction {
  private readonly writes: (() => Promise<void>)[] = [];
  private wrote = false;

  async get(ref: FakeDocRef) {
    // Firestore requires every read before the first write.
    if (this.wrote)
      throw new Error("Firestore transactions must read before writing");
    return ref.get();
  }

  set(ref: FakeDocRef, data: Data) {
    this.wrote = true;
    this.writes.push(() => ref.set(data));
    return this;
  }

  update(ref: FakeDocRef, data: Data) {
    this.wrote = true;
    this.writes.push(() => ref.update(data));
    return this;
  }

  delete(ref: FakeDocRef) {
    this.wrote = true;
    this.writes.push(() => ref.delete());
    return this;
  }

  async apply() {
    for (const write of this.writes) await write();
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
