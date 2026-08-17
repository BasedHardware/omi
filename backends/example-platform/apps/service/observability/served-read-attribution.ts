import { AsyncLocalStorage } from "node:async_hooks";

import { resolveRunKey } from "./write-ops-counter";
import type { DomainReadOutcome, ServedCounter } from "./served-count";

/** The existing shell-supplied identity used by the former integration server. */
export const READ_CLIENT_ID_HEADER = "x-omi-client-id";

export interface ServedReadRunTally {
  readonly served: number;
}

export interface ServedReadAttribution {
  /** Binds one request's existing client id to every served outcome it produces. */
  readonly withRun: <Value>(
    rawClientId: string | null | undefined,
    operation: () => Value,
  ) => Value;
  /** Records only after a domain route has produced a served response body. */
  readonly recordServed: () => void;
  /** `null` means this run produced no served read at all. */
  readonly tally: (runId: string) => ServedReadRunTally | null;
}

const MAX_COUNT = Number.MAX_SAFE_INTEGER;

/**
 * Per-request attribution for the aggregate served counter.
 *
 * Async-local request state is essential here: comparing an aggregate before
 * and after dispatch can give run A credit for run B's concurrently completed
 * read. The route's existing producer-side `recordDomainRead("served")` call is
 * the event of record; this context only supplies the join key for that event.
 */
export const createServedReadAttribution = (): ServedReadAttribution => {
  const currentRun = new AsyncLocalStorage<string>();
  const servedByRun = new Map<string, number>();

  return Object.freeze({
    withRun<Value>(
      rawClientId: string | null | undefined,
      operation: () => Value,
    ): Value {
      return currentRun.run(resolveRunKey(rawClientId), operation);
    },

    recordServed(): void {
      const run = currentRun.getStore() ?? resolveRunKey(undefined);
      const previous = servedByRun.get(run) ?? 0;
      if (previous >= MAX_COUNT) {
        throw new TypeError("served read attribution: count would exceed Number.MAX_SAFE_INTEGER");
      }
      servedByRun.set(run, previous + 1);
    },

    tally(runId: string): ServedReadRunTally | null {
      const served = servedByRun.get(resolveRunKey(runId));
      return served === undefined ? null : Object.freeze({ served });
    },
  });
};

/**
 * Adds per-run attribution without changing the aggregate counter or its
 * `ServedCountSnapshot` shape. Denied and failed reads remain aggregate-only.
 */
export const attributeServedReads = (
  aggregate: ServedCounter,
  attribution: ServedReadAttribution,
): ServedCounter => Object.freeze({
  recordDomainRead(outcome: DomainReadOutcome): void {
    aggregate.recordDomainRead(outcome);
    if (outcome === "served") attribution.recordServed();
  },
  recordNonDomainRequest(): void {
    aggregate.recordNonDomainRequest();
  },
  recordDeclaredContractVersion(input: { readonly atFloor: boolean }): void {
    aggregate.recordDeclaredContractVersion(input);
  },
  snapshot: () => aggregate.snapshot(),
});
