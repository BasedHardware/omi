/**
 * The ACCOUNT EPOCH PROVIDER PORT — where the client's knowledge of its own
 * account epoch comes from, and the one place a different wire can replace it.
 *
 * ── WHY A PORT AND NOT A FETCH ─────────────────────────────────────────────
 *
 * `DAVID-tasks-read-epoch-and-ci` D3 ratifies that the account epoch rides on
 * the ratified READ response as an additive field: no new endpoint, no second
 * auth path, no separate availability signal. That settles WHERE the value
 * rides. It does not settle whether an epoch visible to its own account's
 * client leaks migration progress against `backend:ADR-012` §4 — a question a
 * NON-AUTHOR answers in writing before the additive contract bump lands
 * (D3's own "one thing that must be CHECKED, not assumed"; `FABLE-wave3-
 * review-rulings` R10 gives that check its two-question shape).
 *
 * So this file deliberately contains no wire. It is the seam that ruling can
 * land behind: a provider is a function of one method, the ratified-read
 * implementation replaces the dev one, and nothing that consumes an epoch —
 * the op-sender, the outbox stamp, the L3 write journey — changes when it
 * does. R10 keeps this port a live deliverable precisely so a parked gate
 * parks the bump and never the night.
 *
 * ── WHY `null` IS A VALUE AND NOT AN EXCEPTION ─────────────────────────────
 *
 * "I do not know this account's epoch yet" is an ordinary state — a cold
 * client that has not completed a read. It is not an error, and it must not
 * be represented as one, because the two have opposite handling: an unknown
 * epoch means *do not stamp an op yet*, while an error would tempt a caller
 * into stamping a guess. There is no defaulting to zero anywhere in this file
 * for the same reason: `account_epoch: 0` is a claim about a generation, and
 * a fabricated one is exactly the straggler the fence cannot catch.
 */

/**
 * The port. One method, deliberately synchronous: the value is cached client
 * state maintained by whatever read the client already performs, never an I/O
 * call made at write time. A write path that had to await the network before
 * it could journal an op would be offline-hostile for no gain.
 */
export interface AccountEpochProvider {
  /** The account epoch this client currently believes it is on, or `null`. */
  currentAccountEpoch(): number | null;
}

/** A provider whose value is pushed in by whoever learns it. */
export interface MutableAccountEpochProvider extends AccountEpochProvider {
  /**
   * Record an epoch observed from an authoritative source. Ignores a value
   * that is not a safe non-negative integer, and — deliberately — ignores a
   * value that moves BACKWARDS: epochs advance, and a client that accepted a
   * regression would start stamping ops with an epoch the server has already
   * moved past, manufacturing stragglers out of a transport reorder. Returns
   * whether the observation was accepted, so a caller can tell "ignored" from
   * "applied" instead of inferring it.
   */
  observeAccountEpoch(epoch: unknown): boolean;
}

function isEpoch(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
}

/**
 * The DEV provider: an in-memory cell, seeded and then pushed to.
 *
 * This is the implementation the local stack and the hermetic tests bind. It
 * is not a stub in the pejorative sense — it is the whole of the port's
 * behaviour that does not depend on a wire, which is why the ratified-read
 * implementation will be a thin thing that calls `observeAccountEpoch` rather
 * than a reimplementation of anything here.
 */
export function createDevAccountEpochProvider(initial: number | null = null): MutableAccountEpochProvider {
  let epoch: number | null = isEpoch(initial) ? initial : null;
  return {
    currentAccountEpoch: () => epoch,
    observeAccountEpoch: (value: unknown): boolean => {
      if (!isEpoch(value)) return false;
      if (epoch !== null && value < epoch) return false;
      epoch = value;
      return true;
    },
  };
}
