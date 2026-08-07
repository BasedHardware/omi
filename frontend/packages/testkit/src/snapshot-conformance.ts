/**
 * Shared snapshot-honesty conformance (AGENTS.md hard rule 12, compiled into
 * machinery per the swarm playbook: review findings become harnesses).
 *
 * `complete: true` is the EXCEPTIONAL claim, not the default. On this legacy
 * backend a filtered list is the norm — memories and conversations both hide
 * rows, and memories additionally filters AFTER the page limit, so "short
 * page" proves nothing. A descriptor therefore says nothing about pagination
 * *kind*; it either presents `completeEvidence` for why its source provably
 * returns the whole unfiltered set, or it does not — and without it, the
 * harness requires the fetcher to NEVER claim completeness, for any body.
 *
 * This inversion exists because the previous shape let the fetcher's author
 * self-declare a `kind`, and `kind: "paged"` positively REQUIRED a short page
 * to yield `complete: true`. One wrong word inverted the strongest law and the
 * suite went green over a live data-loss bug in the memories domain.
 *
 * Laws, for every domain:
 *  - non-200 → null
 *  - 200 with a non-list/junk body → null (never a complete empty snapshot)
 *  - paged sources: a full page never claims complete
 *  - NO completeEvidence → complete is never true, on any well-formed body
 *  - completeEvidence present → it must be substantive, AND the fetcher must
 *    actually achieve complete:true on a whole-set body (no dead licenses)
 */

import type { IdSnapshot } from "@omi-core/contracts";
import type { HttpClient, HttpResponse } from "@omi-core/adapters-legacy";

/** Shortest evidence we accept — long enough to force a locator or a reason,
 * not a bare "unfiltered". */
const MIN_EVIDENCE_LENGTH = 30;

export interface SnapshotDescriptor {
  domain: string;
  /** Invoke the fetcher under test against the scripted client. */
  fetch(http: HttpClient): Promise<IdSnapshot | null>;
  /** A well-formed 200 body containing exactly the given ids. */
  okBody(ids: string[]): unknown;
  /** The page size the fetcher requests. Present only for a paged source; its
   * presence is what makes the full-page law applicable. */
  pageSize?: number;
  /**
   * REQUIRED to be allowed to return `complete: true` — a repo-relative
   * locator, or a one-line justification, for why this source provably
   * returns the whole UNFILTERED set. Omit it and the harness proves the
   * fetcher never claims completeness; that is the safe default and the
   * common case.
   *
   * "The endpoint looked complete to me" is not evidence. Name the handler or
   * query that has no filter, no limit, and no post-filter.
   */
  completeEvidence?: string;
}

class OneShotHttp implements HttpClient {
  constructor(private readonly res: HttpResponse) {}
  async request(): Promise<HttpResponse> {
    return this.res;
  }
}

export interface ConformanceFailure {
  domain: string;
  law: string;
  got: string;
}

/** Runs every law against every descriptor; returns failures (empty = pass). */
export async function checkSnapshotConformance(
  descriptors: readonly SnapshotDescriptor[],
): Promise<ConformanceFailure[]> {
  const failures: ConformanceFailure[] = [];
  const fail = (domain: string, law: string, got: unknown): void => {
    failures.push({ domain, law, got: JSON.stringify(got) });
  };

  for (const d of descriptors) {
    const completeCapable = d.completeEvidence !== undefined;

    // A declared license must be substantive, or it is not a license.
    if (completeCapable && d.completeEvidence!.trim().length < MIN_EVIDENCE_LENGTH) {
      fail(
        d.domain,
        `completeEvidence must be a real locator or justification (>=${MIN_EVIDENCE_LENGTH} chars)`,
        d.completeEvidence,
      );
      continue;
    }

    for (const status of [401, 404, 500, 503]) {
      const s = await d.fetch(new OneShotHttp({ status, json: null }));
      if (s !== null) fail(d.domain, `non-200 (${status}) must yield null`, s);
    }
    for (const junk of [null, {}, { unexpected: true }, "nope", 42]) {
      const s = await d.fetch(new OneShotHttp({ status: 200, json: junk }));
      if (s !== null) fail(d.domain, `200 with junk body must yield null, got snapshot for ${JSON.stringify(junk)}`, s);
    }

    // A paged source that filled its page can never be complete, evidence or not.
    const size = d.pageSize ?? 0;
    if (size > 0) {
      const fullPage = Array.from({ length: size }, (_, i) => `id-${i}-x`);
      const s = await d.fetch(new OneShotHttp({ status: 200, json: d.okBody(fullPage) }));
      if (!s || s.complete !== false) fail(d.domain, "a full page never claims complete", s);
    }

    // The inverted default: no evidence => completeness is never claimable.
    const short = await d.fetch(new OneShotHttp({ status: 200, json: d.okBody(["a-b-c"]) }));
    if (!completeCapable) {
      if (!short || short.complete !== false) {
        fail(d.domain, "no completeEvidence declared, so complete must NEVER be true", short);
      }
    } else if (!short || short.complete !== true || short.ids.length !== 1) {
      // Evidence was declared, so it must not be a dead license.
      fail(d.domain, "completeEvidence is declared but the fetcher never achieves complete:true", short);
    }
  }
  return failures;
}
