// domain-pending(DIV-DOMCORE-013)
// domain-pending(UNK-DOMCORE-002)

/**
 * The app-facing conversations store port.
 *
 * Unlike `tasks-store.ts`, this port intentionally knows its field vocabulary.
 * The adopted legacy wire reads `structured.title` and mutates `starred`,
 * `visibility`, and `folder_id` by name. Making those fields an opaque bag here
 * would not preserve neutrality; it would duplicate the wire's already-decided
 * semantics in every adapter and route.
 *
 * Folder ownership remains outside this port. The injected lookup is the narrow
 * read dependency needed to enforce the existing folder reference atomically
 * with a conversation mutation. The folders backend can replace that lookup
 * without changing this store or its wire.
 *
 * Conversation routes carry no write id. Their mutations therefore do not use
 * the tasks write-id registry or WriteUnitOfWork; every adapter must instead
 * make one mutation and its state-revision increment a single local transaction.
 */

export type ConversationVisibility = "public" | "private" | "shared";

export interface ConversationStructured {
  readonly title: string;
  readonly overview: string;
}

/** The record shape already spoken by the legacy client and QA prototype. */
export interface ConversationRecord {
  readonly id: string;
  readonly structured: ConversationStructured;
  readonly created_at: string;
  readonly updated_at: string;
  readonly started_at: string;
  readonly finished_at: string;
  readonly source: string;
  readonly status: string;
  readonly discarded: boolean;
  readonly starred: boolean;
  readonly visibility: ConversationVisibility;
  readonly is_locked: boolean;
  readonly folder_id: string | null;
}

/** Narrow dependency on the not-yet-served folders domain. */
export interface ConversationFolderReferenceLookup {
  hasFolder(accountId: string, folderId: string): boolean;
}

export const denyAllConversationFolderReferences: ConversationFolderReferenceLookup =
  Object.freeze({ hasFolder: () => false });

export type ConversationUpsertOutcome =
  | { readonly stored: true; readonly record: ConversationRecord }
  | { readonly stored: false; readonly reason: "folder_not_found" };

export type ConversationPatchOutcome =
  | {
      readonly updated: true;
      readonly record: ConversationRecord;
      readonly state_revision: number;
    }
  | { readonly updated: false; readonly reason: "not_found" | "folder_not_found" };

export type ConversationDeleteOutcome =
  | { readonly deleted: true; readonly state_revision: number }
  | { readonly deleted: false; readonly reason: "not_found" };

export interface ConversationFolderReassignmentOutcome {
  readonly reassigned: number;
  readonly state_revision: number | null;
}

/** Narrow write seam used by a folder deletion's enclosing unit of work. */
export interface ConversationFolderReassignment {
  reassignFolderReferences(
    accountId: string,
    fromFolderId: string,
    toFolderId: string,
  ): ConversationFolderReassignmentOutcome;
}

export interface ConversationsStore extends ConversationFolderReassignment {
  /** Stable insertion order, matching the legacy collection's array order. */
  listRecords(accountId: string): readonly ConversationRecord[];
  readRecord(accountId: string, recordId: string): ConversationRecord | null;
  /** Server-originated ingest seam. There is deliberately no client create route. */
  upsert(accountId: string, record: ConversationRecord): ConversationUpsertOutcome;
  updateTitle(
    accountId: string,
    recordId: string,
    title: string,
    updatedAt: string,
  ): ConversationPatchOutcome;
  updateStarred(
    accountId: string,
    recordId: string,
    starred: boolean,
    updatedAt: string,
  ): ConversationPatchOutcome;
  updateVisibility(
    accountId: string,
    recordId: string,
    visibility: ConversationVisibility,
    updatedAt: string,
  ): ConversationPatchOutcome;
  updateFolder(
    accountId: string,
    recordId: string,
    folderId: string | null,
    updatedAt: string,
  ): ConversationPatchOutcome;
  deleteRecord(accountId: string, recordId: string): ConversationDeleteOutcome;
  readStateRevision(accountId: string): number;
  /** QA reset support only. */
  reset(): void;
}

const freezeRecord = (record: ConversationRecord): ConversationRecord => Object.freeze({
  ...record,
  structured: Object.freeze({ ...record.structured }),
});

export const createInMemoryConversationsStore = (
  folders: ConversationFolderReferenceLookup = denyAllConversationFolderReferences,
): ConversationsStore => {
  const accounts = new Map<string, Map<string, ConversationRecord>>();
  const revisions = new Map<string, number>();

  const recordsOf = (accountId: string): Map<string, ConversationRecord> => {
    const existing = accounts.get(accountId);
    if (existing !== undefined) return existing;
    const created = new Map<string, ConversationRecord>();
    accounts.set(accountId, created);
    return created;
  };

  const bumpRevision = (accountId: string): number => {
    const next = (revisions.get(accountId) ?? 0) + 1;
    revisions.set(accountId, next);
    return next;
  };

  const update = (
    accountId: string,
    recordId: string,
    updatedAt: string,
    change: (record: ConversationRecord) => ConversationRecord,
  ): ConversationPatchOutcome => {
    const records = accounts.get(accountId);
    const current = records?.get(recordId);
    if (records === undefined || current === undefined) {
      return { updated: false, reason: "not_found" };
    }
    const record = freezeRecord({ ...change(current), updated_at: updatedAt });
    records.set(recordId, record);
    return { updated: true, record, state_revision: bumpRevision(accountId) };
  };

  return Object.freeze({
    listRecords(accountId: string): readonly ConversationRecord[] {
      const records = accounts.get(accountId);
      if (records === undefined) return Object.freeze([]);
      return Object.freeze([...records.values()]);
    },

    readRecord(accountId: string, recordId: string): ConversationRecord | null {
      return accounts.get(accountId)?.get(recordId) ?? null;
    },

    upsert(accountId: string, record: ConversationRecord): ConversationUpsertOutcome {
      if (record.folder_id !== null && !folders.hasFolder(accountId, record.folder_id)) {
        return { stored: false, reason: "folder_not_found" };
      }
      const stored = freezeRecord(record);
      recordsOf(accountId).set(record.id, stored);
      return { stored: true, record: stored };
    },

    updateTitle(accountId, recordId, title, updatedAt): ConversationPatchOutcome {
      return update(accountId, recordId, updatedAt, (record) => ({
        ...record,
        structured: { ...record.structured, title },
      }));
    },

    updateStarred(accountId, recordId, starred, updatedAt): ConversationPatchOutcome {
      return update(accountId, recordId, updatedAt, (record) => ({ ...record, starred }));
    },

    updateVisibility(accountId, recordId, visibility, updatedAt): ConversationPatchOutcome {
      return update(accountId, recordId, updatedAt, (record) => ({ ...record, visibility }));
    },

    updateFolder(accountId, recordId, folderId, updatedAt): ConversationPatchOutcome {
      const current = accounts.get(accountId)?.get(recordId);
      if (current === undefined) return { updated: false, reason: "not_found" };
      if (folderId !== null && !folders.hasFolder(accountId, folderId)) {
        return { updated: false, reason: "folder_not_found" };
      }
      return update(accountId, recordId, updatedAt, (record) => ({
        ...record,
        folder_id: folderId,
      }));
    },

    deleteRecord(accountId: string, recordId: string): ConversationDeleteOutcome {
      const records = accounts.get(accountId);
      if (records === undefined || !records.delete(recordId)) {
        return { deleted: false, reason: "not_found" };
      }
      return { deleted: true, state_revision: bumpRevision(accountId) };
    },

    reassignFolderReferences(
      accountId: string,
      fromFolderId: string,
      toFolderId: string,
    ): ConversationFolderReassignmentOutcome {
      const records = accounts.get(accountId);
      if (records === undefined) return { reassigned: 0, state_revision: null };
      let reassigned = 0;
      for (const [recordId, record] of records) {
        if (record.folder_id !== fromFolderId) continue;
        records.set(recordId, freezeRecord({ ...record, folder_id: toFolderId }));
        reassigned += 1;
      }
      return {
        reassigned,
        state_revision: reassigned === 0 ? null : bumpRevision(accountId),
      };
    },

    readStateRevision(accountId: string): number {
      return revisions.get(accountId) ?? 0;
    },

    reset(): void {
      accounts.clear();
      revisions.clear();
    },
  });
};
