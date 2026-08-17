import type { AccountLifecycleState } from "../../../core/control/account-control";

/** Authentication-facing account existence/lifecycle source. */
export interface AccountLifecyclePort {
  /** Missing or unavailable source state is not authority to admit an account. */
  readLifecycle(accountId: string): AccountLifecycleState | null;
}

/** Writable adapter seam for source ingestion and hermetic tests. */
export interface AccountLifecycleStore extends AccountLifecyclePort {
  setLifecycle(accountId: string, state: AccountLifecycleState): void;
  /** Clears QA-local lifecycle overrides; missing rows resolve to active. */
  reset(): void;
}

const STATES: ReadonlySet<AccountLifecycleState> = new Set([
  "active",
  "deletion_pending",
  "deleted",
]);

export const assertAccountLifecycleState = (
  state: unknown,
): AccountLifecycleState => {
  if (typeof state !== "string" || !STATES.has(state as AccountLifecycleState)) {
    throw new TypeError("invalid account lifecycle state");
  }
  return state as AccountLifecycleState;
};

/** In-memory local/QA adapter. The composition must seed every admitted account. */
export const createInMemoryAccountLifecycleStore = (): AccountLifecycleStore => {
  const states = new Map<string, AccountLifecycleState>();
  return Object.freeze({
    readLifecycle(accountId: string): AccountLifecycleState | null {
      return states.get(accountId) ?? null;
    },

    setLifecycle(accountId: string, state: AccountLifecycleState): void {
      states.set(accountId, assertAccountLifecycleState(state));
    },

    reset(): void {
      states.clear();
    },
  });
};
