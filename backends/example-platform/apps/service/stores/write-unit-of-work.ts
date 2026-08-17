// domain-pending(DIV-DOMTASK-001)
// domain-pending(DIV-DOMTASK-002)
// domain-pending(FC-DOMTASK-001)

import type { TasksApplyOutcome, TasksStore, TasksWriteOp } from "./tasks-store";
import type {
  RecordedWriteOutcome,
  WriteIdLookup,
  WriteIdRegistry,
} from "./write-id-registry";
import {
  createUnitOfWorkContext,
  type UnitOfWorkContext,
  type UnitOfWorkEffect,
} from "./unit-of-work-context";

const WRITE_UNIT_OF_WORK_PORT: unique symbol = Symbol("write-unit-of-work");

/** Everything the write door has already authenticated, validated, and fenced. */
export interface WriteUnitOfWorkInput {
  readonly accountId: string;
  readonly writeId: string;
  readonly fingerprintOf: unknown;
  readonly accountEpoch: number;
  readonly op: TasksWriteOp;
}

/** Internal classifications consumed by the existing wire binding. */
export type WriteUnitOfWorkOutcome =
  | { readonly kind: "reuse" }
  | { readonly kind: "replay"; readonly outcome: RecordedWriteOutcome }
  | { readonly kind: "conflict" }
  | { readonly kind: "applied"; readonly outcome: RecordedWriteOutcome };

/**
 * The sealed atomic boundary behind one accepted write attempt.
 *
 * Adapters must use `defineWriteUnitOfWork`; direct structural implementations
 * cannot satisfy the private port brand. The same invariant context and opaque
 * effect mechanism used by folder deletion carries lookup, apply, and record.
 * Independently branded contexts fail to type-check, while different runtime
 * instances of the same client class are rejected by identity checks.
 *
 * A Postgres adapter must check out one client, create one context for it, and
 * perform every operation through `context.perform` under SERIALIZABLE (or
 * REPEATABLE READ plus explicit write-id reservation/locking). Merely issuing
 * BEGIN through a pool is invalid.
 */
export interface WriteUnitOfWork {
  readonly [WRITE_UNIT_OF_WORK_PORT]: true;
  execute(input: WriteUnitOfWorkInput): Promise<WriteUnitOfWorkOutcome>;
}

export interface WriteUnitOfWorkTransaction<Connection extends object> {
  execute<Result>(
    input: WriteUnitOfWorkInput,
    operation: (context: UnitOfWorkContext<Connection>) => Result,
  ): Promise<Result>;
}

export interface WriteUnitOfWorkOperations<Connection extends object> {
  lookup(
    context: UnitOfWorkContext<Connection>,
    input: WriteUnitOfWorkInput,
  ): UnitOfWorkEffect<Connection, WriteIdLookup>;
  apply(
    context: UnitOfWorkContext<Connection>,
    input: WriteUnitOfWorkInput,
  ): UnitOfWorkEffect<Connection, TasksApplyOutcome>;
  record(
    context: UnitOfWorkContext<Connection>,
    input: WriteUnitOfWorkInput,
    outcome: RecordedWriteOutcome,
  ): UnitOfWorkEffect<Connection, void>;
}

/** The only constructor for the sealed tasks write port. */
export const defineWriteUnitOfWork = <Connection extends object>(
  transaction: WriteUnitOfWorkTransaction<Connection>,
  operations: WriteUnitOfWorkOperations<NoInfer<Connection>>,
): WriteUnitOfWork => Object.freeze({
  [WRITE_UNIT_OF_WORK_PORT]: true as const,
  execute(input: WriteUnitOfWorkInput): Promise<WriteUnitOfWorkOutcome> {
    return transaction.execute(input, (context) => {
      const seen = context.resolve(operations.lookup(context, input));
      if (seen.kind === "reuse") return { kind: "reuse" };
      if (seen.kind === "replay") return { kind: "replay", outcome: seen.outcome };

      const applied = context.resolve(operations.apply(context, input));
      if (!applied.applied) return { kind: "conflict" };

      const outcome = Object.freeze({
        record_id: applied.record_id,
        revision: applied.revision,
      });
      context.resolve(operations.record(context, input, outcome));
      return { kind: "applied", outcome };
    });
  },
});

interface InMemoryWriteConnection {
  readonly tasks: TasksStore;
  readonly registry: WriteIdRegistry;
}

/**
 * Process-local implementation. The operation has no `await`, so no observer
 * can interleave between lookup, apply, and record. If the process is killed,
 * both in-memory stores disappear together; there is no durable half-state.
 */
export const createInMemoryWriteUnitOfWork = (
  tasks: TasksStore,
  registry: WriteIdRegistry,
): WriteUnitOfWork => {
  const connection = Object.freeze({ tasks, registry });
  const context = createUnitOfWorkContext(connection);
  return defineWriteUnitOfWork({
    execute<Result>(
      _input: WriteUnitOfWorkInput,
      operation: (context: UnitOfWorkContext<InMemoryWriteConnection>) => Result,
    ): Promise<Result> {
      return Promise.resolve(operation(context));
    },
  }, {
    lookup: (workContext, input) => workContext.perform(connection, ({ registry }) =>
      registry.lookup(input.accountId, input.writeId, input.fingerprintOf)),
    apply: (workContext, input) => workContext.perform(connection, ({ tasks }) =>
      tasks.apply(input.accountId, input.op)),
    record: (workContext, input, outcome) => workContext.perform(connection, ({ registry }) => {
      registry.record({
        accountId: input.accountId,
        writeId: input.writeId,
        fingerprintOf: input.fingerprintOf,
        accountEpoch: input.accountEpoch,
        outcome,
      });
    }),
  });
};
