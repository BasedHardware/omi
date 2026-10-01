const CONTEXT_CONNECTION: unique symbol = Symbol("unit-of-work-context-connection");
const EFFECT_CONNECTION: unique symbol = Symbol("unit-of-work-effect-connection");
const EFFECT_OWNER: unique symbol = Symbol("unit-of-work-effect-owner");

/**
 * Raised before an operation runs when it presents a different runtime
 * connection from the one that owns the transaction context.
 */
export class UnitOfWorkConnectionMismatchError extends Error {
  constructor() {
    super("unit-of-work operation used a different connection context");
    this.name = "UnitOfWorkConnectionMismatchError";
  }
}

/** An opaque result that can only be opened by the context that produced it. */
export interface UnitOfWorkEffect<Connection extends object, Value> {
  readonly [EFFECT_CONNECTION]: (connection: Connection) => Connection;
  readonly [EFFECT_OWNER]: UnitOfWorkContext<Connection>;
  readonly value: Value;
}

/**
 * One checked-out connection capability.
 *
 * `Connection` is invariant, so independently branded adapter contexts cannot
 * be combined by inference. `perform` additionally compares object identity at
 * runtime because TypeScript cannot distinguish two instances of the same
 * client class. Every adapter operation must return the opaque effect produced
 * here; a result from another same-typed context is rejected by `resolve`.
 */
export interface UnitOfWorkContext<Connection extends object> {
  readonly [CONTEXT_CONNECTION]: (connection: Connection) => Connection;
  perform<Value>(
    connection: NoInfer<Connection>,
    operation: (connection: Connection) => Value,
  ): UnitOfWorkEffect<Connection, Value>;
  resolve<Value>(effect: UnitOfWorkEffect<NoInfer<Connection>, Value>): Value;
}

export const createUnitOfWorkContext = <Connection extends object>(
  connection: Connection,
): UnitOfWorkContext<Connection> => {
  let context: UnitOfWorkContext<Connection>;
  context = Object.freeze({
    [CONTEXT_CONNECTION]: (candidate: Connection): Connection => candidate,
    perform<Value>(
      candidate: NoInfer<Connection>,
      operation: (connection: Connection) => Value,
    ): UnitOfWorkEffect<Connection, Value> {
      if (candidate !== connection) throw new UnitOfWorkConnectionMismatchError();
      return Object.freeze({
        [EFFECT_CONNECTION]: (effectConnection: Connection): Connection => effectConnection,
        [EFFECT_OWNER]: context,
        value: operation(candidate),
      });
    },
    resolve<Value>(effect: UnitOfWorkEffect<NoInfer<Connection>, Value>): Value {
      if (effect[EFFECT_OWNER] !== context) throw new UnitOfWorkConnectionMismatchError();
      return effect.value;
    },
  });
  return context;
};
