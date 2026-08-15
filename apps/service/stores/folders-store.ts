import type { ConversationFolderReferenceLookup } from "./conversations-store";

/**
 * The adopted folder row. Patchable values are deliberately `unknown`: the QA
 * prototype assigns any JSON value for those five keys without validation.
 */
export interface FolderRecord {
  readonly id: string;
  readonly name: unknown;
  readonly description: unknown;
  readonly color: unknown;
  readonly icon: unknown;
  readonly created_at: string;
  readonly updated_at: string;
  readonly order: unknown;
  readonly is_default: boolean;
  readonly is_system: boolean;
}

export interface FolderCreateInput {
  readonly id: string;
  readonly name: string;
  readonly description: string | null;
  readonly color: string;
  readonly icon: string;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface FolderPatch {
  readonly name?: unknown;
  readonly description?: unknown;
  readonly color?: unknown;
  readonly icon?: unknown;
  readonly order?: unknown;
}

export type FolderCreateOutcome =
  | { readonly created: true; readonly record: FolderRecord }
  | { readonly created: false; readonly reason: "already_exists" };

export type FolderPatchOutcome =
  | { readonly updated: true; readonly record: FolderRecord }
  | { readonly updated: false; readonly reason: "not_found" };

/** One stored folder plus its ingest sequence — the ratified cursor's order. */
export interface OrderedFolderRecord {
  readonly record: FolderRecord;
  readonly sequence: number;
}

export interface FoldersStore extends ConversationFolderReferenceLookup {
  listFolders(accountId: string): readonly FolderRecord[];
  listOrderedFolders(accountId: string): readonly OrderedFolderRecord[];
  readFolder(accountId: string, folderId: string): FolderRecord | null;
  /** Server fixture/restore seam; preserves every stored field. */
  upsert(accountId: string, record: FolderRecord): FolderRecord;
  createFolder(accountId: string, input: FolderCreateInput): FolderCreateOutcome;
  patchFolder(
    accountId: string,
    folderId: string,
    patch: FolderPatch,
    updatedAt: string,
  ): FolderPatchOutcome;
  reset(): void;
}

const freezeRecord = (record: FolderRecord): FolderRecord => Object.freeze({ ...record });

const cloneSnapshotRecord = (record: FolderRecord): FolderRecord =>
  freezeRecord(structuredClone(record));

export interface InMemoryFoldersAccountSnapshot {
  readonly records: readonly FolderRecord[] | null;
}

/** Adapter-private capabilities owned by the in-memory folder deletion unit. */
export interface InMemoryFoldersStore extends FoldersStore {
  deleteFolderRecord(accountId: string, folderId: string): boolean;
  snapshotAccount(accountId: string): InMemoryFoldersAccountSnapshot;
  restoreAccount(accountId: string, snapshot: InMemoryFoldersAccountSnapshot): void;
  /** Emergency rollback path; this adapter-private map replacement must not throw. */
  forceRestoreAccount(accountId: string, snapshot: InMemoryFoldersAccountSnapshot): void;
}

export const createInMemoryFoldersStore = (): InMemoryFoldersStore => {
  const accounts = new Map<string, Map<string, FolderRecord>>();
  const sequences = new Map<string, Map<string, number>>();
  const nextSequences = new Map<string, number>();

  const replaceAccount = (
    accountId: string,
    snapshot: InMemoryFoldersAccountSnapshot,
  ): void => {
    if (snapshot.records === null) {
      accounts.delete(accountId);
      sequences.delete(accountId);
      nextSequences.delete(accountId);
    } else {
      accounts.set(accountId, new Map(snapshot.records.map((record) => [record.id, record])));
      const assigned = new Map<string, number>();
      snapshot.records.forEach((record, index) => {
        assigned.set(record.id, index + 1);
      });
      sequences.set(accountId, assigned);
      nextSequences.set(accountId, snapshot.records.length + 1);
    }
  };

  const foldersOf = (accountId: string): Map<string, FolderRecord> => {
    const existing = accounts.get(accountId);
    if (existing !== undefined) return existing;
    const created = new Map<string, FolderRecord>();
    accounts.set(accountId, created);
    return created;
  };

  return Object.freeze({
    listFolders(accountId: string): readonly FolderRecord[] {
      return Object.freeze([...(accounts.get(accountId)?.values() ?? [])]);
    },

    listOrderedFolders(accountId: string): readonly OrderedFolderRecord[] {
      const records = accounts.get(accountId);
      if (records === undefined) return Object.freeze([]);
      const assigned = sequences.get(accountId);
      return Object.freeze([...records.values()].map((record, index) => Object.freeze({
        record,
        sequence: assigned?.get(record.id) ?? index + 1,
      })));
    },

    readFolder(accountId: string, folderId: string): FolderRecord | null {
      return accounts.get(accountId)?.get(folderId) ?? null;
    },

    hasFolder(accountId: string, folderId: string): boolean {
      return accounts.get(accountId)?.has(folderId) ?? false;
    },

    upsert(accountId: string, record: FolderRecord): FolderRecord {
      const stored = freezeRecord(record);
      const existing = foldersOf(accountId);
      if (!existing.has(record.id)) {
        const assigned = sequences.get(accountId) ?? new Map<string, number>();
        sequences.set(accountId, assigned);
        const next = nextSequences.get(accountId) ?? 1;
        assigned.set(record.id, next);
        nextSequences.set(accountId, next + 1);
      }
      existing.set(record.id, stored);
      return stored;
    },

    createFolder(accountId: string, input: FolderCreateInput): FolderCreateOutcome {
      const folders = foldersOf(accountId);
      if (folders.has(input.id)) return { created: false, reason: "already_exists" };
      const record = freezeRecord({
        ...input,
        order: folders.size,
        is_default: false,
        is_system: false,
      });
      const assigned = sequences.get(accountId) ?? new Map<string, number>();
      sequences.set(accountId, assigned);
      const next = nextSequences.get(accountId) ?? 1;
      assigned.set(record.id, next);
      nextSequences.set(accountId, next + 1);
      folders.set(record.id, record);
      return { created: true, record };
    },

    patchFolder(
      accountId: string,
      folderId: string,
      patch: FolderPatch,
      updatedAt: string,
    ): FolderPatchOutcome {
      const folders = accounts.get(accountId);
      const current = folders?.get(folderId);
      if (folders === undefined || current === undefined) {
        return { updated: false, reason: "not_found" };
      }
      const record = freezeRecord({ ...current, ...patch, updated_at: updatedAt });
      folders.set(folderId, record);
      return { updated: true, record };
    },

    deleteFolderRecord(accountId: string, folderId: string): boolean {
      return accounts.get(accountId)?.delete(folderId) ?? false;
    },

    snapshotAccount(accountId: string): InMemoryFoldersAccountSnapshot {
      const records = accounts.get(accountId);
      return Object.freeze({
        records: records === undefined
          ? null
          : Object.freeze([...records.values()].map(cloneSnapshotRecord)),
      });
    },

    restoreAccount(accountId: string, snapshot: InMemoryFoldersAccountSnapshot): void {
      replaceAccount(accountId, snapshot);
    },

    forceRestoreAccount(accountId: string, snapshot: InMemoryFoldersAccountSnapshot): void {
      replaceAccount(accountId, snapshot);
    },

    reset(): void {
      accounts.clear();
      sequences.clear();
      nextSequences.clear();
    },
  });
};
