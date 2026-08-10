import type {
  InMemoryConversationsAccountSnapshot,
  InMemoryConversationsStore,
} from "./conversations-store";
import type {
  InMemoryFoldersAccountSnapshot,
  InMemoryFoldersStore,
} from "./folders-store";
import {
  createUnitOfWorkContext,
  type UnitOfWorkContext,
  type UnitOfWorkEffect,
} from "./unit-of-work-context";

const FOLDER_DELETION_PORT: unique symbol = Symbol("folder-deletion-unit-of-work");

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
 * The sealed atomic boundary behind one folder deletion.
 *
 * Adapters cannot structurally implement this port. They must use
 * `defineFolderDeletionUnitOfWork`, whose operation signatures carry one
 * invariant connection capability through validation, reassignment, and
 * deletion. Independently branded contexts therefore fail to type-check.
 * TypeScript cannot distinguish two runtime instances of the same client
 * class, so physical identity is also checked at runtime before an operation
 * executes and again when its opaque effect is consumed.
 *
 * SQLite executes the complete operation on one immediate transaction. A
 * Postgres implementation must check out one pool client, create exactly one
 * context for it, and perform every operation through `context.perform`. It
 * must keep the chosen target live through commit with a row lock or equivalent
 * constraint compatible with the deliberate no-target dangling-reference
 * behavior. Issuing BEGIN through a pool is invalid.
 */
export interface FolderDeletionUnitOfWork {
  readonly [FOLDER_DELETION_PORT]: true;
  execute(input: FolderDeletionInput): Promise<FolderDeletionOutcome>;
}

interface FolderDeletionCurrent {
  readonly isSystem: boolean;
}

export interface FolderDeletionTransaction<Connection extends object> {
  execute<Result>(
    input: FolderDeletionInput,
    operation: (
      context: UnitOfWorkContext<Connection>,
      checkpointBeforeFirstWrite: () => void,
    ) => Result,
  ): Promise<Result>;
}

export interface FolderDeletionOperations<Connection extends object> {
  readCurrent(
    context: UnitOfWorkContext<Connection>,
    input: FolderDeletionInput,
  ): UnitOfWorkEffect<Connection, FolderDeletionCurrent | null>;
  targetExists(
    context: UnitOfWorkContext<Connection>,
    input: FolderDeletionInput,
    targetFolderId: string,
  ): UnitOfWorkEffect<Connection, boolean>;
  findDefaultTarget(
    context: UnitOfWorkContext<Connection>,
    input: FolderDeletionInput,
  ): UnitOfWorkEffect<Connection, string | null>;
  reassignConversations(
    context: UnitOfWorkContext<Connection>,
    input: FolderDeletionInput,
    targetFolderId: string,
  ): UnitOfWorkEffect<Connection, void>;
  deleteFolder(
    context: UnitOfWorkContext<Connection>,
    input: FolderDeletionInput,
  ): UnitOfWorkEffect<Connection, boolean>;
}

/** The only constructor for the sealed folder-deletion port. */
export const defineFolderDeletionUnitOfWork = <Connection extends object>(
  transaction: FolderDeletionTransaction<Connection>,
  operations: FolderDeletionOperations<NoInfer<Connection>>,
): FolderDeletionUnitOfWork => Object.freeze({
  [FOLDER_DELETION_PORT]: true as const,
  execute(input: FolderDeletionInput): Promise<FolderDeletionOutcome> {
    return transaction.execute(input, (context, checkpoint) => {
      const current = context.resolve(operations.readCurrent(context, input));
      if (current === null) return { deleted: false, reason: "not_found" };
      if (current.isSystem) return { deleted: false, reason: "system_folder" };
      if (input.requestedTarget === input.folderId) {
        return { deleted: false, reason: "self_move" };
      }
      if (
        input.requestedTarget !== null
        && !context.resolve(operations.targetExists(context, input, input.requestedTarget))
      ) {
        return { deleted: false, reason: "target_not_found" };
      }

      const target = input.requestedTarget
        ?? context.resolve(operations.findDefaultTarget(context, input));
      checkpoint();
      if (target !== null) {
        context.resolve(operations.reassignConversations(context, input, target));
      }
      if (!context.resolve(operations.deleteFolder(context, input))) {
        throw new Error("folder disappeared inside deletion unit of work");
      }
      return { deleted: true, moved_to_folder_id: target };
    });
  },
});

export interface InMemoryFolderDeletionFaults {
  /** Test-only crash/failure seam at the real boundary between the two writes. */
  readonly afterConversationReassignment?: () => void;
}

interface InMemoryFolderDeletionConnection {
  readonly folders: InMemoryFoldersStore;
  readonly conversations: InMemoryConversationsStore;
}

const restoreInMemoryAccount = (
  connection: InMemoryFolderDeletionConnection,
  accountId: string,
  foldersBefore: InMemoryFoldersAccountSnapshot,
  conversationsBefore: InMemoryConversationsAccountSnapshot,
  operationError: unknown,
): never => {
  const rollbackErrors: unknown[] = [];
  try {
    connection.folders.restoreAccount(accountId, foldersBefore);
  } catch (rollbackError) {
    rollbackErrors.push(rollbackError);
  }
  try {
    connection.conversations.restoreAccount(accountId, conversationsBefore);
  } catch (rollbackError) {
    rollbackErrors.push(rollbackError);
  }
  if (rollbackErrors.length > 0) {
    connection.folders.forceRestoreAccount(accountId, foldersBefore);
    connection.conversations.forceRestoreAccount(accountId, conversationsBefore);
    throw new AggregateError(
      [operationError, ...rollbackErrors],
      "in-memory folder deletion rollback required emergency restoration",
    );
  }
  throw operationError;
};

/**
 * Process-local implementation. Its body has no suspension point, so observers
 * cannot interleave. Exact account snapshots provide the rollback boundary that
 * the individual in-memory stores cannot provide on their own.
 */
export const createInMemoryFolderDeletionUnitOfWork = (
  folders: InMemoryFoldersStore,
  conversations: InMemoryConversationsStore,
  faults: InMemoryFolderDeletionFaults = {},
): FolderDeletionUnitOfWork => {
  const connection = Object.freeze({ folders, conversations });
  const context = createUnitOfWorkContext(connection);
  return defineFolderDeletionUnitOfWork({
    execute<Result>(input: FolderDeletionInput, operation: (
      context: UnitOfWorkContext<InMemoryFolderDeletionConnection>,
      checkpointBeforeFirstWrite: () => void,
    ) => Result): Promise<Result> {
      let foldersBefore: InMemoryFoldersAccountSnapshot | undefined;
      let conversationsBefore: InMemoryConversationsAccountSnapshot | undefined;
      const checkpoint = (): void => {
        if (foldersBefore !== undefined) return;
        foldersBefore = folders.snapshotAccount(input.accountId);
        conversationsBefore = conversations.snapshotAccount(input.accountId);
      };
      try {
        return Promise.resolve(operation(context, checkpoint));
      } catch (error) {
        if (foldersBefore === undefined || conversationsBefore === undefined) throw error;
        return restoreInMemoryAccount(
          connection,
          input.accountId,
          foldersBefore,
          conversationsBefore,
          error,
        );
      }
    },
  }, {
    readCurrent: (workContext, input) => workContext.perform(connection, ({ folders }) => {
      const current = folders.readFolder(input.accountId, input.folderId);
      return current === null ? null : { isSystem: current.is_system };
    }),
    targetExists: (workContext, input, targetFolderId) =>
      workContext.perform(connection, ({ folders }) =>
        folders.hasFolder(input.accountId, targetFolderId)),
    findDefaultTarget: (workContext, input) => workContext.perform(connection, ({ folders }) =>
      folders.listFolders(input.accountId).find((folder) => folder.is_default)?.id ?? null),
    reassignConversations: (workContext, input, targetFolderId) =>
      workContext.perform(connection, ({ conversations }) => {
        conversations.reassignFolderReferences(input.accountId, input.folderId, targetFolderId);
        faults.afterConversationReassignment?.();
      }),
    deleteFolder: (workContext, input) => workContext.perform(connection, ({ folders }) =>
      folders.deleteFolderRecord(input.accountId, input.folderId)),
  });
};
