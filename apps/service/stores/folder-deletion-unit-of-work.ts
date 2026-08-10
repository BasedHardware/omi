import type { InMemoryConversationsStore } from "./conversations-store";
import type { InMemoryFoldersStore } from "./folders-store";

export interface FolderDeletionInput {
  readonly accountId: string;
  readonly folderId: string;
  readonly requestedTarget: string | null;
}

export type FolderDeletionOutcome =
  | { readonly deleted: true; readonly moved_to_folder_id: string | null }
  | {
      readonly deleted: false;
      readonly reason: "not_found" | "system_folder" | "self_move" | "target_not_found";
    };

/**
 * The atomic boundary behind one folder deletion.
 *
 * This is deliberately a semantic operation rather than `transaction(callback)`
 * or a method on either participating store. An implementation owns source and
 * target validation, conversation reassignment, and deletion, and must not
 * resolve or reject until both writes commit or both roll back. An adapter that
 * accepts independently pooled stores is not an implementation of this port.
 *
 * SQLite executes the complete operation on one immediate transaction. A
 * Postgres implementation must check out one pool client, perform every read
 * and write through that client, and keep the chosen target live through commit
 * with a row lock or an equivalent constraint compatible with the deliberate
 * no-target dangling-reference behavior. It must use SERIALIZABLE with retry of
 * the complete unit, or REPEATABLE READ plus explicit source/target locking and
 * complete-unit retry for serialization/deadlock failures. Issuing BEGIN
 * through a pool or retrying only one write is invalid.
 */
export interface FolderDeletionUnitOfWork {
  execute(input: FolderDeletionInput): Promise<FolderDeletionOutcome>;
}

export interface InMemoryFolderDeletionFaults {
  /** Test-only crash/failure seam at the real boundary between the two writes. */
  readonly afterConversationReassignment?: () => void;
}

/**
 * Process-local implementation. Its body has no suspension point, so observers
 * cannot interleave. Exact account snapshots provide the rollback boundary that
 * the individual in-memory stores cannot provide on their own.
 */
export const createInMemoryFolderDeletionUnitOfWork = (
  folders: InMemoryFoldersStore,
  conversations: InMemoryConversationsStore,
  faults: InMemoryFolderDeletionFaults = {},
): FolderDeletionUnitOfWork => Object.freeze({
  execute(input: FolderDeletionInput): Promise<FolderDeletionOutcome> {
    const current = folders.readFolder(input.accountId, input.folderId);
    if (current === null) return Promise.resolve({ deleted: false, reason: "not_found" });
    if (current.is_system) {
      return Promise.resolve({ deleted: false, reason: "system_folder" });
    }
    if (input.requestedTarget === input.folderId) {
      return Promise.resolve({ deleted: false, reason: "self_move" });
    }
    if (
      input.requestedTarget !== null
      && !folders.hasFolder(input.accountId, input.requestedTarget)
    ) {
      return Promise.resolve({ deleted: false, reason: "target_not_found" });
    }

    const target = input.requestedTarget
      ?? folders.listFolders(input.accountId).find((folder) => folder.is_default)?.id
      ?? null;
    const foldersBefore = folders.snapshotAccount(input.accountId);
    const conversationsBefore = conversations.snapshotAccount(input.accountId);
    try {
      if (target !== null) {
        conversations.reassignFolderReferences(input.accountId, input.folderId, target);
        faults.afterConversationReassignment?.();
      }
      if (!folders.deleteFolderRecord(input.accountId, input.folderId)) {
        throw new Error("folder disappeared inside in-memory deletion unit");
      }
      return Promise.resolve({ deleted: true, moved_to_folder_id: target });
    } catch (error) {
      folders.restoreAccount(input.accountId, foldersBefore);
      conversations.restoreAccount(input.accountId, conversationsBefore);
      throw error;
    }
  },
});
