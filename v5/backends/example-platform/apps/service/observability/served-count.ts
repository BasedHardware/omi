export type DomainReadOutcome = "served" | "denied" | "failed";

export type ServedCountSnapshot = {
  readonly version: "served-count-v1";
  readonly domainReadsServed: number;
  readonly domainReadsDenied: number;
  readonly domainReadsFailed: number;
  readonly nonDomainRequests: number;
  readonly totalRequests: number;
  /**
   * COORD-contract-evolution-policy.md §4's payoff: "counting unknown fields
   * turns 'how many clients are behind the wire' into a population statistic
   * instead of a guess." This is the narrower, available-today slice of that:
   * how many app-facing requests declared NO contract version at all (and so
   * were resolved to the floor), versus how many declared one explicitly.
   * It does not require `FallbackSink` (COORD-degradation-is-unobservable,
   * a different lane's dependency this run) because it counts a request-side
   * header, not a response-side unknown-field degradation.
   */
  readonly declaredContractVersionAtFloor: number;
  readonly declaredContractVersionExplicit: number;
};

export type ServedCounter = {
  recordDomainRead(outcome: DomainReadOutcome): void;
  recordNonDomainRequest(): void;
  /** Whether the request resolved to the floor (no/malformed header) or declared explicitly. */
  recordDeclaredContractVersion(input: { readonly atFloor: boolean }): void;
  snapshot(): ServedCountSnapshot;
};

/** QA-only seed for hermetic boundary tests. Never pass from a request handler. */
export type ServedCounterQaSeed = {
  readonly domainReadsServed?: number;
  readonly domainReadsDenied?: number;
  readonly domainReadsFailed?: number;
  readonly nonDomainRequests?: number;
  readonly declaredContractVersionAtFloor?: number;
  readonly declaredContractVersionExplicit?: number;
};

const SNAPSHOT_VERSION = "served-count-v1" as const;
const MAX_COUNT = Number.MAX_SAFE_INTEGER;
const RESET = Symbol("omi.served-counter.reset");

type ServedCounterBuckets = {
  domainReadsServed: number;
  domainReadsDenied: number;
  domainReadsFailed: number;
  nonDomainRequests: number;
  declaredContractVersionAtFloor: number;
  declaredContractVersionExplicit: number;
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
  declaredContractVersionAtFloor: 0,
  declaredContractVersionExplicit: 0,
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
    declaredContractVersionAtFloor: buckets.declaredContractVersionAtFloor,
    declaredContractVersionExplicit: buckets.declaredContractVersionExplicit,
  });

export function createServedCounter(qaSeed?: ServedCounterQaSeed): ServedCounter {
  const buckets: ServedCounterBuckets = qaSeed
    ? {
      domainReadsServed: assertSeedCount("domainReadsServed", qaSeed.domainReadsServed),
      domainReadsDenied: assertSeedCount("domainReadsDenied", qaSeed.domainReadsDenied),
      domainReadsFailed: assertSeedCount("domainReadsFailed", qaSeed.domainReadsFailed),
      nonDomainRequests: assertSeedCount("nonDomainRequests", qaSeed.nonDomainRequests),
      declaredContractVersionAtFloor: assertSeedCount("declaredContractVersionAtFloor", qaSeed.declaredContractVersionAtFloor),
      declaredContractVersionExplicit: assertSeedCount("declaredContractVersionExplicit", qaSeed.declaredContractVersionExplicit),
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

    recordDeclaredContractVersion({ atFloor }: { readonly atFloor: boolean }): void {
      if (atFloor) {
        buckets.declaredContractVersionAtFloor = increment(buckets.declaredContractVersionAtFloor);
      } else {
        buckets.declaredContractVersionExplicit = increment(buckets.declaredContractVersionExplicit);
      }
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
