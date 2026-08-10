import {
  defineFolderDeletionUnitOfWork,
  type FolderDeletionOperations,
  type FolderDeletionTransaction,
} from "../apps/service/stores/folder-deletion-unit-of-work.ts";
import {
  defineWriteUnitOfWork,
  type WriteUnitOfWorkOperations,
  type WriteUnitOfWorkTransaction,
} from "../apps/service/stores/write-unit-of-work.ts";
import {
  createUnitOfWorkContext,
  type UnitOfWorkContext,
} from "../apps/service/stores/unit-of-work-context.ts";

declare const FIRST_CONNECTION: unique symbol;
declare const SECOND_CONNECTION: unique symbol;

interface FirstConnection {
  readonly [FIRST_CONNECTION]: true;
}

interface SecondConnection {
  readonly [SECOND_CONNECTION]: true;
}

const firstConnection = {} as FirstConnection;
const secondConnection = {} as SecondConnection;
const firstContext = createUnitOfWorkContext(firstConnection);
const secondContext = createUnitOfWorkContext(secondConnection);

const folderTransaction: FolderDeletionTransaction<FirstConnection> = {
  execute: (_input, operation) => Promise.resolve(operation(firstContext, () => {})),
};

const correctFolderOperations: FolderDeletionOperations<FirstConnection> = {
  readCurrent: (context) => context.perform(firstConnection, () => ({ isSystem: false })),
  targetExists: (context) => context.perform(firstConnection, () => true),
  findDefaultTarget: (context) => context.perform(firstConnection, () => null),
  reassignConversations: (context) => context.perform(firstConnection, () => {}),
  deleteFolder: (context) => context.perform(firstConnection, () => true),
};

defineFolderDeletionUnitOfWork(folderTransaction, correctFolderOperations);

const splitFolderOperations = {
  ...correctFolderOperations,
  deleteFolder: (_context: UnitOfWorkContext<FirstConnection>) =>
    secondContext.perform(secondConnection, () => true),
};

// @ts-expect-error reassignment and deletion cannot come from different contexts.
defineFolderDeletionUnitOfWork(folderTransaction, splitFolderOperations);

const writeTransaction: WriteUnitOfWorkTransaction<FirstConnection> = {
  execute: (_input, operation) => Promise.resolve(operation(firstContext)),
};

const correctWriteOperations: WriteUnitOfWorkOperations<FirstConnection> = {
  lookup: (context) => context.perform(firstConnection, () => ({ kind: "fresh" })),
  apply: (context, input) => context.perform(firstConnection, () => ({
    applied: true,
    record_id: input.op.record_id,
    revision: null,
  })),
  record: (context) => context.perform(firstConnection, () => {}),
};

defineWriteUnitOfWork(writeTransaction, correctWriteOperations);

const splitWriteOperations = {
  ...correctWriteOperations,
  record: (_context: UnitOfWorkContext<FirstConnection>) =>
    secondContext.perform(secondConnection, () => {}),
};

// @ts-expect-error apply and registry record cannot come from different contexts.
defineWriteUnitOfWork(writeTransaction, splitWriteOperations);
