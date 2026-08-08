export type DomainReadOutcome = "served" | "denied" | "failed";

export type ServedCountSnapshot = {
  readonly version: "served-count-v1";
  readonly domainReadsServed: number;
  readonly domainReadsDenied: number;
  readonly domainReadsFailed: number;
  readonly nonDomainRequests: number;
  readonly totalRequests: number;
};

export type ServedCounter = {
  recordDomainRead(outcome: DomainReadOutcome): void;
  recordNonDomainRequest(): void;
  snapshot(): ServedCountSnapshot;
};

/** QA-only seed for hermetic boundary tests. Never pass from a request handler. */
export type ServedCounterQaSeed = {
  readonly domainReadsServed?: number;
  readonly domainReadsDenied?: number;
  readonly domainReadsFailed?: number;
  readonly nonDomainRequests?: number;
};

const SNAPSHOT_VERSION = "served-count-v1" as const;
const MAX_COUNT = Number.MAX_SAFE_INTEGER;
const RESET = Symbol("omi.served-counter.reset");

type ServedCounterBuckets = {
  domainReadsServed: number;
  domainReadsDenied: number;
  domainReadsFailed: number;
  nonDomainRequests: number;
};

type ServedCounterInternal = ServedCounter & {
  readonly [RESET]: () => void;
};

const assertSeedCount = (label: string, value: number | undefined): number => {
  if (value === undefined) return 0;
  if (!Number.isInteger(value) || value < 0 || value > MAX_COUNT) {
    throw new TypeError(`served counter: invalid QA seed for ${label}`);
  }
  return value;
};

const increment = (value: number): number => {
  if (value >= MAX_COUNT) {
    throw new TypeError("served counter: count would exceed Number.MAX_SAFE_INTEGER");
  }
  return value + 1;
};

const zeroBuckets = (): ServedCounterBuckets => ({
  domainReadsServed: 0,
  domainReadsDenied: 0,
  domainReadsFailed: 0,
  nonDomainRequests: 0,
});

const snapshotFrom = (buckets: ServedCounterBuckets): ServedCountSnapshot =>
  Object.freeze({
    version: SNAPSHOT_VERSION,
    domainReadsServed: buckets.domainReadsServed,
    domainReadsDenied: buckets.domainReadsDenied,
    domainReadsFailed: buckets.domainReadsFailed,
    nonDomainRequests: buckets.nonDomainRequests,
    totalRequests:
      buckets.domainReadsServed
      + buckets.domainReadsDenied
      + buckets.domainReadsFailed
      + buckets.nonDomainRequests,
  });

export function createServedCounter(qaSeed?: ServedCounterQaSeed): ServedCounter {
  const buckets: ServedCounterBuckets = qaSeed
    ? {
      domainReadsServed: assertSeedCount("domainReadsServed", qaSeed.domainReadsServed),
      domainReadsDenied: assertSeedCount("domainReadsDenied", qaSeed.domainReadsDenied),
      domainReadsFailed: assertSeedCount("domainReadsFailed", qaSeed.domainReadsFailed),
      nonDomainRequests: assertSeedCount("nonDomainRequests", qaSeed.nonDomainRequests),
    }
    : zeroBuckets();

  const counter: ServedCounterInternal = {
    recordDomainRead(outcome: DomainReadOutcome): void {
      switch (outcome) {
        case "served":
          buckets.domainReadsServed = increment(buckets.domainReadsServed);
          return;
        case "denied":
          buckets.domainReadsDenied = increment(buckets.domainReadsDenied);
          return;
        case "failed":
          buckets.domainReadsFailed = increment(buckets.domainReadsFailed);
          return;
        default: {
          // The rejected value is deliberately NOT interpolated. Default
          // telemetry carries opaque references only, and error paths are
          // exactly where caller content leaks into logs.
          void (outcome as never);
          throw new TypeError("served counter: unknown domain read outcome");
        }
      }
    },

    recordNonDomainRequest(): void {
      buckets.nonDomainRequests = increment(buckets.nonDomainRequests);
    },

    snapshot(): ServedCountSnapshot {
      return snapshotFrom(buckets);
    },

    [RESET](): void {
      Object.assign(buckets, zeroBuckets());
    },
  };

  return counter;
}

/**
 * QA-only machinery: zero all counters on the given instance.
 * Never call from a request handler — request paths must only record outcomes.
 */
export function reset(counter: ServedCounter): void {
  (counter as ServedCounterInternal)[RESET]();
}
