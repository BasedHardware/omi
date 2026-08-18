import type { AccountScope, SyntheticDoc } from "../types";

export type StoredDoc = {
  readonly id: string;
  readonly accountId: string;
  readonly embedding: readonly number[];
  readonly terms: readonly string[];
  revoked: boolean;
};

export const cosine = (a: readonly number[], b: readonly number[]): number => {
  let dot = 0;
  let na = 0;
  let nb = 0;
  const len = Math.min(a.length, b.length);
  for (let i = 0; i < len; i++) {
    const av = a[i]!;
    const bv = b[i]!;
    dot += av * bv;
    na += av * av;
    nb += bv * bv;
  }
  if (na === 0 || nb === 0) return 0;
  return dot / (Math.sqrt(na) * Math.sqrt(nb));
};

export const termOverlap = (
  query: readonly string[],
  doc: readonly string[]
): number => {
  if (query.length === 0 || doc.length === 0) return 0;
  const docSet = new Set(doc);
  let shared = 0;
  for (const term of query) if (docSet.has(term)) shared++;
  return shared / Math.sqrt(query.length * doc.length);
};

export const deterministicJitter = (seed: string, range: number): number => {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    hash = (hash * 31 + seed.charCodeAt(i)) | 0;
  }
  return Math.abs(hash) % range;
};

export class InMemoryStore {
  private readonly visible = new Map<string, Map<string, StoredDoc>>();
  private readonly pending = new Map<string, StoredDoc[]>();
  private readonly lagPerDocMs: number;

  constructor(lagPerDocMs: number) {
    this.lagPerDocMs = lagPerDocMs;
  }

  private bucket(scope: AccountScope): Map<string, StoredDoc> {
    let bucket = this.visible.get(scope.accountId);
    if (bucket === undefined) {
      bucket = new Map<string, StoredDoc>();
      this.visible.set(scope.accountId, bucket);
    }
    return bucket;
  }

  upsertPending(scope: AccountScope, doc: SyntheticDoc): void {
    const stored: StoredDoc = {
      id: doc.id,
      accountId: scope.accountId,
      embedding: doc.embedding,
      terms: doc.terms,
      revoked: doc.revoked,
    };
    let queue = this.pending.get(scope.accountId);
    if (queue === undefined) {
      queue = [];
      this.pending.set(scope.accountId, queue);
    }
    queue.push(stored);
  }

  flush(scope: AccountScope): void {
    const queue = this.pending.get(scope.accountId);
    if (queue === undefined) return;
    const bucket = this.bucket(scope);
    for (const doc of queue) bucket.set(doc.id, doc);
    this.pending.set(scope.accountId, []);
  }

  delete(scope: AccountScope, docId: string): boolean {
    const bucket = this.visible.get(scope.accountId);
    if (bucket === undefined) return false;
    return bucket.delete(docId);
  }

  visibleDocs(scope: AccountScope): readonly StoredDoc[] {
    const bucket = this.visible.get(scope.accountId);
    if (bucket === undefined) return [];
    return [...bucket.values()];
  }

  allVisibleDocs(): readonly StoredDoc[] {
    const all: StoredDoc[] = [];
    for (const bucket of this.visible.values()) {
      for (const doc of bucket.values()) all.push(doc);
    }
    return all;
  }

  pendingLagMs(scope: AccountScope): number {
    const queue = this.pending.get(scope.accountId);
    const count = queue === undefined ? 0 : queue.length;
    return count * this.lagPerDocMs;
  }
}
