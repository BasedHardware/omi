import { describe, expect, test } from "bun:test";

import { createServedCounter, reset, type ServedCountSnapshot } from "./served-count";

const emptySnapshot = (): ServedCountSnapshot => ({
  version: "served-count-v1",
  domainReadsServed: 0,
  domainReadsDenied: 0,
  domainReadsFailed: 0,
  nonDomainRequests: 0,
  totalRequests: 0,
  declaredContractVersionAtFloor: 0,
  declaredContractVersionExplicit: 0,
});

describe("createServedCounter", () => {
  test("starts at zero with the served-count-v1 snapshot shape", () => {
    const counter = createServedCounter();
    expect(counter.snapshot()).toEqual(emptySnapshot());
  });

  test("records domain read outcomes into their dedicated buckets", () => {
    const counter = createServedCounter();

    counter.recordDomainRead("served");
    counter.recordDomainRead("served");
    counter.recordDomainRead("denied");
    counter.recordDomainRead("failed");

    expect(counter.snapshot()).toEqual({
      version: "served-count-v1",
      domainReadsServed: 2,
      domainReadsDenied: 1,
      domainReadsFailed: 1,
      nonDomainRequests: 0,
      totalRequests: 4,
      declaredContractVersionAtFloor: 0,
      declaredContractVersionExplicit: 0,
    });
  });

  test("records health, readiness, and unknown routes only in nonDomainRequests", () => {
    const counter = createServedCounter();

    counter.recordNonDomainRequest();
    counter.recordNonDomainRequest();
    counter.recordNonDomainRequest();

    expect(counter.snapshot()).toEqual({
      version: "served-count-v1",
      domainReadsServed: 0,
      domainReadsDenied: 0,
      domainReadsFailed: 0,
      nonDomainRequests: 3,
      totalRequests: 3,
      declaredContractVersionAtFloor: 0,
      declaredContractVersionExplicit: 0,
    });
  });

  test("totalRequests always equals the sum of every bucket", () => {
    const counter = createServedCounter();

    counter.recordDomainRead("served");
    counter.recordDomainRead("denied");
    counter.recordDomainRead("failed");
    counter.recordNonDomainRequest();
    counter.recordDomainRead("served");
    counter.recordNonDomainRequest();

    const snap = counter.snapshot();
    // red-proof: omit nonDomainRequests from totalRequests and this test fails
    expect(snap.totalRequests).toBe(
      snap.domainReadsServed + snap.domainReadsDenied + snap.domainReadsFailed + snap.nonDomainRequests,
    );
    expect(snap).toEqual({
      version: "served-count-v1",
      domainReadsServed: 2,
      domainReadsDenied: 1,
      domainReadsFailed: 1,
      nonDomainRequests: 2,
      totalRequests: 6,
      declaredContractVersionAtFloor: 0,
      declaredContractVersionExplicit: 0,
    });
  });

  test("recording a health check does not increment domainReadsServed", () => {
    const counter = createServedCounter();

    counter.recordNonDomainRequest();
    counter.recordNonDomainRequest();

    const snap = counter.snapshot();
    // red-proof: route health checks through recordDomainRead and this test fails
    expect(snap.domainReadsServed).toBe(0);
    expect(snap.nonDomainRequests).toBe(2);
    expect(snap.totalRequests).toBe(2);
  });

  test("domainReadsServed counts only served outcomes, not denied or failed", () => {
    const counter = createServedCounter();

    counter.recordDomainRead("denied");
    counter.recordDomainRead("failed");
    counter.recordDomainRead("failed");

    const snap = counter.snapshot();
    // red-proof: increment domainReadsServed on denied/failed and this test fails
    expect(snap.domainReadsServed).toBe(0);
    expect(snap.domainReadsDenied).toBe(1);
    expect(snap.domainReadsFailed).toBe(2);
  });

  test("counters are monotonic and never decrease on record", () => {
    const counter = createServedCounter();
    const prior: ServedCountSnapshot[] = [counter.snapshot()];

    counter.recordDomainRead("served");
    prior.push(counter.snapshot());
    counter.recordDomainRead("denied");
    prior.push(counter.snapshot());
    counter.recordNonDomainRequest();
    prior.push(counter.snapshot());
    counter.recordDomainRead("failed");
    prior.push(counter.snapshot());

    for (let index = 1; index < prior.length; index += 1) {
      const before = prior[index - 1]!;
      const after = prior[index]!;
      // red-proof: decrement any bucket on record and this test fails
      expect(after.domainReadsServed).toBeGreaterThanOrEqual(before.domainReadsServed);
      expect(after.domainReadsDenied).toBeGreaterThanOrEqual(before.domainReadsDenied);
      expect(after.domainReadsFailed).toBeGreaterThanOrEqual(before.domainReadsFailed);
      expect(after.nonDomainRequests).toBeGreaterThanOrEqual(before.nonDomainRequests);
      expect(after.totalRequests).toBeGreaterThanOrEqual(before.totalRequests);
    }
  });

  test("reset is QA-only machinery that zeroes every bucket", () => {
    const counter = createServedCounter();

    counter.recordDomainRead("served");
    counter.recordDomainRead("denied");
    counter.recordDomainRead("failed");
    counter.recordNonDomainRequest();
    reset(counter);

    expect(counter.snapshot()).toEqual(emptySnapshot());
  });

  test("snapshot returns a frozen plain object", () => {
    const counter = createServedCounter();
    counter.recordDomainRead("served");

    const snap = counter.snapshot();
    // red-proof: return a mutable snapshot and this test fails
    expect(Object.isFrozen(snap)).toBe(true);
    expect(() => {
      (snap as { domainReadsServed: number }).domainReadsServed = 99;
    }).toThrow();
  });

  test("successive snapshots are independent values", () => {
    const counter = createServedCounter();
    counter.recordDomainRead("served");

    const first = counter.snapshot();
    counter.recordDomainRead("served");
    const second = counter.snapshot();

    // red-proof: reuse one snapshot object across calls and this test fails
    expect(first).not.toBe(second);
    expect(first.domainReadsServed).toBe(1);
    expect(second.domainReadsServed).toBe(2);
  });

  test("two factory calls produce fully independent counters", () => {
    const left = createServedCounter();
    const right = createServedCounter();

    left.recordDomainRead("served");
    left.recordDomainRead("denied");
    left.recordNonDomainRequest();

    // red-proof: share mutable state between factory calls and this test fails
    expect(left.snapshot()).toEqual({
      version: "served-count-v1",
      domainReadsServed: 1,
      domainReadsDenied: 1,
      domainReadsFailed: 0,
      nonDomainRequests: 1,
      totalRequests: 3,
      declaredContractVersionAtFloor: 0,
      declaredContractVersionExplicit: 0,
    });
    expect(right.snapshot()).toEqual(emptySnapshot());
  });

  test("snapshot JSON serialization never contains request-path secret markers", () => {
    const counter = createServedCounter();
    const secretMarkers = [
      "uid:acct-7f3c9e2a-breach-me",
      "query=SELECT+memories+WHERE+owner",
      "memory-text:patient discussed anxiety",
      "evidence:attachment-sha256-deadbeef",
      "error:stack at domainReadHandler.ts:412",
    ] as const;

    counter.recordDomainRead("failed");
    counter.recordDomainRead("denied");
    counter.recordNonDomainRequest();

    const serialized = JSON.stringify(counter.snapshot());
    // red-proof: store any secret marker in the snapshot and this test fails
    for (const marker of secretMarkers) {
      expect(serialized.includes(marker)).toBe(false);
    }
    expect(serialized).toBe(
      '{"version":"served-count-v1","domainReadsServed":0,"domainReadsDenied":1,"domainReadsFailed":1,"nonDomainRequests":1,"totalRequests":3,"declaredContractVersionAtFloor":0,"declaredContractVersionExplicit":0}',
    );
  });

  test("records declared-contract-version outcomes into their dedicated buckets, independent of domain read buckets", () => {
    const counter = createServedCounter();

    counter.recordDeclaredContractVersion({ atFloor: true });
    counter.recordDeclaredContractVersion({ atFloor: true });
    counter.recordDeclaredContractVersion({ atFloor: false });

    const snap = counter.snapshot();
    // red-proof: swap the atFloor/explicit branches in recordDeclaredContractVersion
    // (served-count.ts) and this test fails - it asserts 2 at-floor vs 1 explicit,
    // which flips to 1 vs 2 under the mutation.
    expect(snap.declaredContractVersionAtFloor).toBe(2);
    expect(snap.declaredContractVersionExplicit).toBe(1);
    // Declared-version counts are a population statistic over requests already
    // classified elsewhere (served/denied/failed/nonDomain); they must not
    // silently also bump an unrelated bucket.
    expect(snap.domainReadsServed).toBe(0);
    expect(snap.totalRequests).toBe(0);
  });

  test("rejects increments that would exceed Number.MAX_SAFE_INTEGER", () => {
    const atServedMax = createServedCounter({ domainReadsServed: Number.MAX_SAFE_INTEGER });
    const atDeniedMax = createServedCounter({ domainReadsDenied: Number.MAX_SAFE_INTEGER });
    const atFailedMax = createServedCounter({ domainReadsFailed: Number.MAX_SAFE_INTEGER });
    const atNonDomainMax = createServedCounter({ nonDomainRequests: Number.MAX_SAFE_INTEGER });
    const atFloorMax = createServedCounter({ declaredContractVersionAtFloor: Number.MAX_SAFE_INTEGER });
    const atExplicitMax = createServedCounter({ declaredContractVersionExplicit: Number.MAX_SAFE_INTEGER });

    // red-proof: remove the MAX_SAFE_INTEGER guard and this test fails
    expect(() => atServedMax.recordDomainRead("served")).toThrow(
      "served counter: count would exceed Number.MAX_SAFE_INTEGER",
    );
    expect(() => atDeniedMax.recordDomainRead("denied")).toThrow(
      "served counter: count would exceed Number.MAX_SAFE_INTEGER",
    );
    expect(() => atFailedMax.recordDomainRead("failed")).toThrow(
      "served counter: count would exceed Number.MAX_SAFE_INTEGER",
    );
    expect(() => atNonDomainMax.recordNonDomainRequest()).toThrow(
      "served counter: count would exceed Number.MAX_SAFE_INTEGER",
    );
    expect(() => atFloorMax.recordDeclaredContractVersion({ atFloor: true })).toThrow(
      "served counter: count would exceed Number.MAX_SAFE_INTEGER",
    );
    expect(() => atExplicitMax.recordDeclaredContractVersion({ atFloor: false })).toThrow(
      "served counter: count would exceed Number.MAX_SAFE_INTEGER",
    );
  });
});
