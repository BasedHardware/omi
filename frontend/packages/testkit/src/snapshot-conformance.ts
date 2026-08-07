/**
 * Shared snapshot-honesty conformance (AGENTS.md hard rule 12, compiled into
 * machinery per the swarm playbook: review findings become harnesses).
 *
 * Every domain's id-snapshot fetcher registers a descriptor here; one
 * property suite then proves, for all domains at once, that the fetcher can
 * never manufacture the reconcile-wipe:
 *  - non-200 → null
 *  - 200 with a non-list/junk body → null (never a complete empty snapshot)
 *  - paged sources: a full page never claims complete
 *  - filtered sources: complete is NEVER claimed, even on a short page
 */

import type { IdSnapshot } from "@omi-core/contracts";
import type { HttpClient, HttpResponse } from "@omi-core/adapters-legacy";

export interface SnapshotDescriptor {
  domain: string;
  /** How the endpoint reads. `unpaginated`: whole set in one response.
   * `paged`: limit/offset. `paged-filtered`: paged AND server-side filtered. */
  kind: "unpaginated" | "paged" | "paged-filtered";
  /** Invoke the fetcher under test against the scripted client. */
  fetch(http: HttpClient): Promise<IdSnapshot | null>;
  /** A well-formed 200 body containing exactly the given ids. */
  okBody(ids: string[]): unknown;
  /** The page size the fetcher requests, for full-page construction. */
  pageSize?: number;
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
    for (const status of [401, 404, 500, 503]) {
      const s = await d.fetch(new OneShotHttp({ status, json: null }));
      if (s !== null) fail(d.domain, `non-200 (${status}) must yield null`, s);
    }
    for (const junk of [null, {}, { unexpected: true }, "nope", 42]) {
      const s = await d.fetch(new OneShotHttp({ status: 200, json: junk }));
      if (s !== null) fail(d.domain, `200 with junk body must yield null, got snapshot for ${JSON.stringify(junk)}`, s);
    }
    if (d.kind === "unpaginated") {
      const s = await d.fetch(new OneShotHttp({ status: 200, json: d.okBody(["a-b-c", "d-e-f"]) }));
      if (!s || s.complete !== true || s.ids.length !== 2) {
        fail(d.domain, "unpaginated well-formed body yields a complete 2-id snapshot", s);
      }
    } else {
      const size = d.pageSize ?? 0;
      if (size > 0) {
        const fullPage = Array.from({ length: size }, (_, i) => `id-${i}-x`);
        const s = await d.fetch(new OneShotHttp({ status: 200, json: d.okBody(fullPage) }));
        if (!s || s.complete !== false) fail(d.domain, "a full page never claims complete", s);
      }
      const short = await d.fetch(new OneShotHttp({ status: 200, json: d.okBody(["a-b-c"]) }));
      if (d.kind === "paged-filtered") {
        if (!short || short.complete !== false) {
          fail(d.domain, "a filtered source NEVER claims complete, even on a short page", short);
        }
      } else if (!short || short.complete !== true) {
        fail(d.domain, "unfiltered short page yields complete", short);
      }
    }
  }
  return failures;
}
