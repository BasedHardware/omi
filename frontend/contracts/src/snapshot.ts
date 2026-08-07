/**
 * The whole-set id snapshot — ADR-004 D3, one type for every domain
 * (ratchet from swarm wave 1: three workers independently duplicated it).
 *
 * HONESTY CONTRACT (AGENTS.md hard rule 12): `complete: true` is a license to
 * DELETE local rows in `Projection.reconcile`, so it may be claimed only when
 * the source provably returned the whole unfiltered set. A fetcher must
 * return `null` (not a complete empty snapshot) for any response it does not
 * fully understand, `complete: false` for any paged read that filled its
 * page, and `complete: false` unconditionally when the source endpoint
 * applies ANY server-side filter.
 *
 * `complete: false` is the DEFAULT, not the fallback: on the legacy backend a
 * filtered list is the norm, so the shared conformance harness in
 * `@omi-core/testkit` requires a domain to present written `completeEvidence`
 * — a locator for the handler or query that provably has no filter, no limit,
 * and no post-filter — before its fetcher is permitted to claim completeness
 * at all. No evidence, no `complete: true`.
 */
export interface IdSnapshot {
  setVersion: string;
  complete: boolean;
  ids: readonly string[];
}
