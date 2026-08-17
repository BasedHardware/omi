// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMAPPS-001)
import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";

import { createLocalDevService } from "../app-facing";
import { seedQaSnapshot } from "../qa/seed";

/**
 * Hidden-present versus physically-absent byte identity.
 *
 * A memory hidden by authorization and a memory that does not exist must be
 * indistinguishable on the wire. Any difference - ordering, item count,
 * envelope, cursor, completeness, status code, or headers - is an authorization
 * oracle: it tells a caller that a record they may not see nevertheless exists.
 *
 * This is the property most likely to be quietly wrong, because every
 * implementation that leaks it still looks completely correct in isolation. So
 * the comparison here is on RAW RESPONSE BYTES, not on parsed objects: a parsed
 * comparison would silently tolerate key reordering, whitespace, or a changed
 * cursor payload, which are exactly the channels a leak would travel through.
 *
 * The fixture sets are built so the leak would actually have somewhere to show:
 * every hidden memory shares a local day with a visible one, so the served
 * day-node exists in BOTH fixture sets and only its membership differs. A projection
 * that failed to filter would therefore change the synthesized text of an item
 * that is present in both - not merely add an extra item.
 *
 * Verified separately: with hidden_memory_count 3 and memory_count 5 the
 * database holds 8 claim rows and the durable snapshot carries all 8, while the
 * authorization projection admits 5. The hidden rows are genuinely present.
 */

const OWNER = "local-dev-user";
const TIMEZONE = "America/Los_Angeles";
const DEV_LABEL = "omi-local-dev-token-not-a-secret-v1";
const VISIBLE_MEMORIES = 5;
const PAGE_LIMIT = 2;
const MAX_PAGES = 64;

interface Booted {
  readonly fetch: (request: Request) => Response | Promise<Response>;
  readonly authorization: string;
}

/**
 * Boots the real service over a corpus with `hiddenCount` present-but-hidden
 * memories. Everything else - owner, timezone, dev label, visible count - is
 * held identical so the ONLY difference between two boots is the hidden rows.
 */
const boot = (hiddenCount: number): Booted => {
  const db = new Database(":memory:");
  // createLocalService seeds on construction; re-seed with the hidden rows and
  // then let the service's own reseed path be irrelevant to this test.
  const service = createLocalDevService({
    db,
    ownerAccountId: OWNER,
    memoryCount: VISIBLE_MEMORIES,
    accountTimezone: TIMEZONE,
    devSecretLabel: DEV_LABEL,
  });
  seedQaSnapshot(db, {
    owner_account_id: OWNER,
    memory_count: VISIBLE_MEMORIES,
    account_timezone: TIMEZONE,
    hidden_memory_count: hiddenCount,
  });
  return Object.freeze({
    fetch: (request: Request) => service.app.fetch(request),
    authorization: `Bearer ${service.devToken}`,
  });
};

const url = (cursor: string | null): string => {
  const target = new URL("http://hidden-vs-absent.invalid/v1/memories");
  target.searchParams.set("limit", String(PAGE_LIMIT));
  if (cursor !== null) target.searchParams.set("cursor", cursor);
  return target.toString();
};

interface CapturedPage {
  readonly status: number;
  readonly headers: string;
  readonly body: string;
  readonly nextCursor: string | null;
  readonly itemIds: readonly string[];
}

const capture = async (service: Booted, cursor: string | null): Promise<CapturedPage> => {
  const response = await service.fetch(new Request(url(cursor), {
    method: "GET",
    headers: { authorization: service.authorization },
  }));
  const body = await response.text();
  const headers = [...response.headers.entries()]
    .map(([name, value]) => `${name}: ${value}`)
    .sort()
    .join("\n");
  const parsed = JSON.parse(body) as {
    items: { id: string }[];
    window: { nextCursor: string | null };
  };
  return {
    status: response.status,
    headers,
    body,
    nextCursor: parsed.window.nextCursor,
    itemIds: parsed.items.map((item) => item.id),
  };
};

/** Walks every page, following each response's own cursor. */
const walk = async (service: Booted): Promise<readonly CapturedPage[]> => {
  const pages: CapturedPage[] = [];
  let cursor: string | null = null;
  for (let index = 0; index < MAX_PAGES; index += 1) {
    const page = await capture(service, cursor);
    pages.push(page);
    if (page.nextCursor === null) return pages;
    cursor = page.nextCursor;
  }
  throw new Error("pagination did not terminate");
};

describe("hidden-present is byte-identical to physically-absent", () => {
  test("first page bytes, status and headers are identical whether records are hidden or absent", async () => {
    // red-proof: drop the policy-label filter in applicationVisibleClosure (or
    // stop filtering hidden claims in the composition) and the hidden corpus
    // gains an item / changes an item's synthesized text, so the bodies differ.
    const absent = await capture(boot(0), null);
    const hidden = await capture(boot(3), null);

    expect(hidden.body).toBe(absent.body);
    expect(hidden.status).toBe(absent.status);
    expect(hidden.headers).toBe(absent.headers);
  });

  test("the comparison is meaningful: two identical fixture sets also match", async () => {
    // red-proof: make boot() nondeterministic (wall clock, random ids) and this
    // control fails, proving the equality above was not vacuous.
    const first = await capture(boot(0), null);
    const second = await capture(boot(0), null);
    expect(second.body).toBe(first.body);
  });

  test("the fixture sets genuinely differ underneath, so the equality above is not trivial", async () => {
    // red-proof: set hidden_memory_count to 0 in the second boot and this test
    // fails - which would mean the byte-identity test was comparing two
    // identical databases and proving nothing.
    const plainDb = new Database(":memory:");
    seedQaSnapshot(plainDb, {
      owner_account_id: OWNER,
      memory_count: VISIBLE_MEMORIES,
      account_timezone: TIMEZONE,
      hidden_memory_count: 0,
    });
    const hiddenDb = new Database(":memory:");
    seedQaSnapshot(hiddenDb, {
      owner_account_id: OWNER,
      memory_count: VISIBLE_MEMORIES,
      account_timezone: TIMEZONE,
      hidden_memory_count: 3,
    });
    const countClaims = (db: Database): number =>
      (db.query("SELECT COUNT(*) AS total FROM claim_revisions").get() as { total: number }).total;

    expect(countClaims(plainDb)).toBe(VISIBLE_MEMORIES);
    // The hidden rows are really in the database; they are removed by the
    // authorization projection, not by never having been written.
    expect(countClaims(hiddenDb)).toBe(VISIBLE_MEMORIES + 3);
  });

  test("every page in the full pagination walk is byte-identical", async () => {
    // red-proof: bind the hidden rows into the cursor payload (for example by
    // folding an unfiltered row count into the cursor policy digest) and the
    // page bodies diverge from page two onward even though page one matches.
    const absentPages = await walk(boot(0));
    const hiddenPages = await walk(boot(3));

    expect(hiddenPages.length).toBe(absentPages.length);
    for (let index = 0; index < absentPages.length; index += 1) {
      expect(hiddenPages[index]!.body).toBe(absentPages[index]!.body);
      expect(hiddenPages[index]!.itemIds).toEqual(absentPages[index]!.itemIds);
      expect(hiddenPages[index]!.nextCursor).toBe(absentPages[index]!.nextCursor);
    }
  });

  test("item count and order carry no trace of the hidden records", async () => {
    // red-proof: emit hidden records as tombstones, or reserve their ordering
    // slots, and the id sequences stop matching.
    const absentIds = (await walk(boot(0))).flatMap((page) => page.itemIds);
    const hiddenIds = (await walk(boot(3))).flatMap((page) => page.itemIds);

    expect(hiddenIds).toEqual(absentIds);
    expect(absentIds.length).toBeGreaterThan(0);
    expect(new Set(absentIds).size).toBe(absentIds.length);
  });
});
