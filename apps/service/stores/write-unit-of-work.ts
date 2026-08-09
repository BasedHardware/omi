// domain-pending(DIV-DOMTASK-001)
// domain-pending(DIV-DOMTASK-002)
// domain-pending(FC-DOMTASK-001)

import type { TasksStore, TasksWriteOp } from "./tasks-store";
import type { RecordedWriteOutcome, WriteIdRegistry } from "./write-id-registry";

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
 * The atomic boundary behind one accepted write attempt.
 *
 * This is deliberately a semantic operation rather than `transaction(callback)`.
 * A callback over independently pooled stores would let a future Postgres adapter
 * begin a transaction on one connection while lookup/apply/record silently ran on
 * others. An implementation of this port owns all three operations and must not
 * resolve until their transaction commits or rolls back.
 *
 * SQLite implements it with one immediate transaction on one `Database`. A
 * Postgres implementation must check out one pool client, execute every operation
 * through that client under SERIALIZABLE (or REPEATABLE READ plus explicit
 * write-id reservation/locking), and retry the complete unit on serialization
 * failure. Merely issuing BEGIN through a pool is not an implementation.
 */
export interface WriteUnitOfWork {
  execute(input: WriteUnitOfWorkInput): Promise<WriteUnitOfWorkOutcome>;
}

/**
 * Storage-independent ordering shared by adapters. The caller supplies the
 * transaction boundary; this function contains no suspension point.
 */
export const executeWriteUnit = (
  tasks: TasksStore,
  registry: WriteIdRegistry,
  input: WriteUnitOfWorkInput,
): WriteUnitOfWorkOutcome => {
  const seen = registry.lookup(input.accountId, input.writeId, input.fingerprintOf);
  if (seen.kind === "reuse") return { kind: "reuse" };
  if (seen.kind === "replay") return { kind: "replay", outcome: seen.outcome };

  const applied = tasks.apply(input.accountId, input.op);
  if (!applied.applied) return { kind: "conflict" };

  const outcome = Object.freeze({
    record_id: applied.record_id,
    revision: applied.revision,
  });
  registry.record({
    accountId: input.accountId,
    writeId: input.writeId,
    fingerprintOf: input.fingerprintOf,
    accountEpoch: input.accountEpoch,
    outcome,
  });
  return { kind: "applied", outcome };
};

/**
 * Process-local implementation. The operation has no `await`, so no observer
 * can interleave between lookup, apply, and record. If the process is killed,
 * all three in-memory stores disappear together; there is no durable half-state.
 */
export const createInMemoryWriteUnitOfWork = (
  tasks: TasksStore,
  registry: WriteIdRegistry,
): WriteUnitOfWork => Object.freeze({
  execute(input: WriteUnitOfWorkInput): Promise<WriteUnitOfWorkOutcome> {
    return Promise.resolve(executeWriteUnit(tasks, registry, input));
  },
});
