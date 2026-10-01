/**
 * Platform-generation task READ adapter — the client half of the ratified
 * tasks read seam.
 *
 * It speaks `@omi-core/ratified-contracts` 0.6.0 (`TaskRead`), the same
 * artifact the new backend consumes as a tarball pinned by content hash in
 * `contracts.lock.json`, and it is checked against the same corpus of record
 * (`fixtures/tasks-read-conformance.json`) that the server side is checked
 * against — rule 15's seam, registered in
 * `core/scripts/check-wire-conformance.mjs`. A test that hand-authors the
 * counterpart's payload is testing its author's memory of the wire, which is
 * the thing that was wrong all three times rule 15 exists for.
 *
 * WHY THIS IS A NEAR-TWIN OF `./memories.ts` RATHER THAN A SHARED GENERIC
 *
 * The two wires share a pagination law and a coverage discipline, and they
 * share nothing else: different item shapes, different envelope versions,
 * different reason vocabularies, different completeness evidence. Factoring the
 * walk into a generic over both would put the two domains' laws in one place
 * where a change made for one silently applies to the other — which is the
 * two-doors defect one layer up. What IS shared is the ratified package: both
 * adapters call the contract's own validator and neither reimplements it.
 *
 * The parts that are genuinely identical are identical on purpose and are
 * commented where they are subtle, so a reader comparing the two files can see
 * that the sameness is a decision.
 *
 * WHAT THIS ADAPTER DELIBERATELY DOES NOT DO
 *
 * It has no writes. Writes go through `POST /v1/tasks/ops`
 * (`./write-ops.ts`), which is a separate ratified wire with its own envelope
 * and its own idempotency; a read adapter that also wrote would be two
 * contracts in one module.
 *
 * It never repairs a body. If a page does not satisfy the ratified validator
 * the outcome is `unreadable` and the caller gets `kind: "unknown"` — never a
 * partially salvaged page, never an empty page, never a `complete` claim.
 *
 * It never maps an opaque `id` onto a `RecordId`. D2 is explicit that the
 * legacy slug/server-id alias does not cross this wire, and the surface type
 * (`PlatformTaskItem`) is separate from `Task` for precisely that one field.
 */

import type { HttpClient, HttpResponse, IdSnapshot } from "@omi-core/contracts";
import type {
  PlatformTaskCoverageReason,
  PlatformTaskCoverageState,
  PlatformTaskCoverageStatus,
  PlatformTaskItem,
} from "@omi-core/contracts";
import {
  MAX_TASKS_PAGE_JSON_CODE_UNITS,
  isTrustedTaskPageData,
  parseTaskPageJson,
  type TaskRead,
} from "@omi-core/ratified-contracts/projections/tasks";

/**
 * The tasks read route.
 *
 * `GET /v1/tasks?limit=&cursor=`, `Authorization: Bearer <token>`. The
 * spelling mirrors `/v1/memories` for the same reason that one won: this is a
 * paginated collection read with no query input, so a noun is the honest name
 * and a verb would misdescribe it.
 *
 * Auth is deliberately absent from this package: the transport binding owns the
 * base URL and the token (ADR-008 §3), which is what lets a shell repoint at a
 * local backend without a rebuild. Every entry point still takes a `path`
 * override.
 */
export const PLATFORM_TASKS_READ_PATH = "/v1/tasks";

/**
 * The server's page-limit ceiling. Asking for more is not an error there, it is
 * silently CLAMPED — so asking for more would make our "did the walk
 * terminate" reasoning depend on a clamp we cannot observe. Ask for what the
 * server will actually honor.
 */
export const PLATFORM_TASKS_MAX_LIMIT = 100;

/**
 * Ceiling on a whole-set walk. Not a tuning knob: it is what keeps a server
 * that answers every request with the SAME continuation from spinning this
 * client forever. Hitting it is a failure to terminate, and a walk that did not
 * terminate can never claim completeness.
 */
export const PLATFORM_TASKS_MAX_PAGES = 200;

/**
 * Ceiling on items accumulated across a whole-set walk. Each page is already
 * bounded by the contract's byte ceiling; 200 maximal pages is not a bound any
 * client should agree to hold. A walk that exceeds this FAILS rather than
 * truncating — a truncated walk that still terminated would look exactly like a
 * complete one.
 */
export const PLATFORM_TASKS_MAX_WALK_ITEMS = 20_000;

/** Which of the two contract boundaries actually validated this body. */
export type PlatformTasksParseBoundary =
  /** `parseTaskPageJson` over the raw bytes — the authoritative one. */
  | "canonical-json-text"
  /** `isTrustedTaskPageData` over `JSON.parse` output — weaker. */
  | "trusted-parsed-json";

export type PlatformTasksPageOutcome =
  | {
      readonly kind: "page";
      readonly page: TaskRead.Page;
      readonly boundary: PlatformTasksParseBoundary;
    }
  /** Transport answered, but not with a 200. Nothing is known about the set. */
  | { readonly kind: "http-error"; readonly status: number }
  /**
   * 200, and the body did not satisfy the ratified contract. This is NOT an
   * empty page and NOT a complete page. It is the absence of knowledge.
   */
  | { readonly kind: "unreadable"; readonly boundary: PlatformTasksParseBoundary };

export interface PlatformTasksPageRequest {
  /** Clamped into `[1, PLATFORM_TASKS_MAX_LIMIT]`. */
  readonly limit?: number;
  /** Opaque server cursor from a previous page's `window.nextCursor`. */
  readonly cursor?: string | null;
  readonly path?: string;
}

/** One tasks page, validated at the strongest boundary the transport allows. */
export async function fetchPlatformTaskPage(
  http: HttpClient,
  request: PlatformTasksPageRequest = {},
): Promise<PlatformTasksPageOutcome> {
  const limit = clampLimit(request.limit);
  const path = request.path ?? PLATFORM_TASKS_READ_PATH;
  const query = request.cursor
    ? `?limit=${limit}&cursor=${encodeURIComponent(request.cursor)}`
    : `?limit=${limit}`;

  const res = await http.request("GET", `${path}${query}`);
  if (res.status !== 200) return { kind: "http-error", status: res.status };
  return parsePlatformTaskPageResponse(res);
}

/**
 * Body → page, at the strongest boundary this response supports. Exported so
 * the conformance corpus can drive it directly with a scripted response, which
 * is the only way a hermetic test can prove the boundary selection.
 *
 * The contract's authoritative boundary is defined over the response BYTES: it
 * rejects noncanonical encodings, duplicate keys, and oversized payloads before
 * the contract predicate runs. The `HttpClient` seam historically exposed only
 * a pre-parsed `json`, so we take the raw text when the binding provides it and
 * fall back to the object-level predicate when it does not — and we REPORT
 * which one was used rather than treating them as equivalent.
 */
export function parsePlatformTaskPageResponse(res: HttpResponse): PlatformTasksPageOutcome {
  if (typeof res.text === "string") {
    const page = parseTaskPageJson(res.text);
    return page === null
      ? { kind: "unreadable", boundary: "canonical-json-text" }
      : { kind: "page", page, boundary: "canonical-json-text" };
  }
  // No raw body available. The object predicate cannot see duplicate keys
  // (JSON.parse already dropped them) or a noncanonical encoding. The size
  // ceiling is still enforced, so an oversized payload is refused at BOTH
  // boundaries rather than only at the strong one.
  if (!isTrustedTaskPageData(res.json)) {
    return { kind: "unreadable", boundary: "trusted-parsed-json" };
  }
  if (!withinContractSizeCeiling(res.json)) {
    return { kind: "unreadable", boundary: "trusted-parsed-json" };
  }
  return { kind: "page", page: res.json, boundary: "trusted-parsed-json" };
}

function withinContractSizeCeiling(value: unknown): boolean {
  try {
    return JSON.stringify(value).length <= MAX_TASKS_PAGE_JSON_CODE_UNITS;
  } catch {
    return false;
  }
}

function clampLimit(requested: number | undefined): number {
  if (requested === undefined || !Number.isSafeInteger(requested) || requested < 1) {
    return PLATFORM_TASKS_MAX_LIMIT;
  }
  return Math.min(requested, PLATFORM_TASKS_MAX_LIMIT);
}

/**
 * Contract page → surface items. A pure projection that copies all thirteen
 * fields and nothing else.
 *
 * EVERY FIELD IS COPIED EXPLICITLY rather than spread, and that is the point of
 * the file. A spread would carry whatever the server sent — including a
 * fourteenth field a newer contract added — straight onto a surface type that
 * does not declare it, so the client would render a wire it never validated.
 * Naming the thirteen means the day the contract grows a field, this function
 * stops compiling and a human decides what the surface does with it.
 *
 * The brands are stripped here, which is the only place that is allowed to
 * happen: the values already passed the validator that created them.
 */
export function platformTaskItemsFromPage(page: TaskRead.Page): readonly PlatformTaskItem[] {
  return page.items.map((item): PlatformTaskItem => ({
    id: item.id,
    description: item.description,
    completed: item.completed,
    completedAt: item.completedAt,
    dueAt: item.dueAt,
    owner: item.owner,
    source: item.source,
    provenance: [...item.provenance],
    sortOrder: item.sortOrder,
    indentLevel: item.indentLevel,
    createdAt: item.createdAt,
    updatedAt: item.updatedAt,
    revision: item.revision,
  }));
}

/**
 * Contract page → the honest coverage state a surface renders.
 *
 * Every field here is CARRIED, never derived. `complete` is the server's
 * declared `completeness.status`, not an inference from `items.length`, page
 * fullness, or `window.hasMore`. The window and the coverage envelope are two
 * different claims — a page can be the terminal window of a walk whose coverage
 * was `degraded` — and collapsing them is how a client ends up telling a user
 * "that is everything" about a projection the server said was stale.
 */
export function platformTaskCoverageFromPage(page: TaskRead.Page): PlatformTaskCoverageState {
  // No casts. `status` and `reasons` are assigned across the seam by STRUCTURAL
  // ASSIGNABILITY, so the day the ratified contract adds a status or a reason,
  // this file stops compiling and a human decides how a surface explains it. A
  // cast here would silently widen the new value into the old union and ship an
  // unexplained page.
  const status: PlatformTaskCoverageStatus = page.completeness.status;
  const reasons: readonly PlatformTaskCoverageReason[] = [...page.completeness.reasons];
  return {
    kind: "known",
    status,
    reasons,
    complete: page.completeness.status === "complete",
    queryGap: page.absence !== null,
    hasMore: page.window.hasMore,
  };
}

/** What a whole-set walk learned. `wholeSet` is load-bearing: see below. */
export interface PlatformTaskWalk {
  readonly items: readonly PlatformTaskItem[];
  /** Coverage of the LAST page walked — the one that terminated (or did not). */
  readonly coverage: PlatformTaskCoverageState;
  /** Pages actually fetched. `0` is impossible; the walk always reads one. */
  readonly pages: number;
  /** True only under every condition below. This is what licenses deletion. */
  readonly wholeSet: boolean;
}

export interface PlatformTaskWalkRequest {
  readonly limit?: number;
  readonly path?: string;
  readonly maxPages?: number;
  readonly maxItems?: number;
}

/**
 * Walk the keyset continuation from the FIRST page to a terminal page.
 *
 * `wholeSet` is true only when ALL of the following held:
 *   1. the walk started at the first page — no caller-supplied cursor, so the
 *      server chose the start and we did not skip a prefix;
 *   2. every page parsed under the ratified validator (no `unreadable`, no
 *      non-200 anywhere in the walk);
 *   3. every page's `completeness.status === "complete"` — one `degraded` or
 *      `partial` page anywhere means the union we assembled is not the set,
 *      even if the last page's window says `complete`;
 *   4. the terminal page's window is the complete-terminal variant;
 *   5. the walk terminated inside `maxPages`.
 *
 * Condition 3 is the one that is easy to get wrong and expensive to get wrong,
 * and it is worse for tasks than for memories: a walk that ANDs only the
 * WINDOWS would end on a complete-terminal page, claim the whole set, and
 * license deleting every local task the lagging projection failed to return.
 * `pending_writes` — an op the write path applied that the read projection has
 * not caught up with — is exactly the state where that deletion would destroy a
 * write the user just made and the server already accepted.
 *
 * Returns `null` when the walk could not be completed honestly at all — any
 * `http-error`, any `unreadable` page, a REPEATED ITEM ID, a repeated cursor,
 * or a walk that exceeded its item ceiling.
 *
 * ON REPEATED IDS. A keyset cursor exists to make a walk duplicate-free. If
 * page two returns an id page one already gave us, the server has broken that
 * guarantee, and the likeliest cause is an unrecognized cursor silently
 * decoding to "start from the beginning" — a bug already found and fixed once
 * in our own fixture server. Against such a server the walk re-reads page one
 * forever, and if it ever lands on a complete-terminal page we would claim the
 * whole set from a duplicate-riddled prefix. `wholeSet: false` is NOT a
 * sufficient response: once ordering is violated the set semantics of the whole
 * walk are unreliable, so the honest answer is that we know nothing, which is
 * `null`.
 */
export async function walkPlatformTaskPages(
  http: HttpClient,
  request: PlatformTaskWalkRequest = {},
): Promise<PlatformTaskWalk | null> {
  const maxPages = request.maxPages ?? PLATFORM_TASKS_MAX_PAGES;
  const maxItems = request.maxItems ?? PLATFORM_TASKS_MAX_WALK_ITEMS;
  const items: PlatformTaskItem[] = [];
  const seenIds = new Set<string>();
  const seenCursors = new Set<string>();
  let cursor: string | null = null;
  let pages = 0;
  let everyPageComplete = true;
  let lastCoverage: PlatformTaskCoverageState = { kind: "unknown" };

  while (pages < maxPages) {
    const pageRequest: PlatformTasksPageRequest = {
      ...(request.limit !== undefined ? { limit: request.limit } : {}),
      ...(request.path !== undefined ? { path: request.path } : {}),
      cursor,
    };
    const outcome = await fetchPlatformTaskPage(http, pageRequest);
    if (outcome.kind !== "page") return null;
    pages += 1;

    const pageItems = platformTaskItemsFromPage(outcome.page);
    for (const task of pageItems) {
      // Duplicate across pages: the keyset guarantee is broken. See the header.
      if (seenIds.has(task.id)) return null;
      seenIds.add(task.id);
    }
    if (items.length + pageItems.length > maxItems) return null;
    items.push(...pageItems);
    lastCoverage = platformTaskCoverageFromPage(outcome.page);
    if (outcome.page.completeness.status !== "complete") everyPageComplete = false;

    const window = outcome.page.window;
    if (!window.hasMore) {
      return {
        items,
        coverage: lastCoverage,
        pages,
        // Condition 4: only the complete-terminal variant. An
        // incomplete-terminal window ends the walk without proving the set.
        wholeSet: everyPageComplete && window.status === "complete",
      };
    }
    // The contract guarantees a continuation window carries a cursor; the
    // validator already rejected `hasMore` without one, so this is total.
    //
    // A cursor we have already followed means the server is cycling us through
    // one window. Duplicate ids usually catch this first, but not when the
    // repeated page is EMPTY of new ids for another reason, so the cursor cycle
    // is checked independently rather than relied on transitively.
    if (seenCursors.has(window.nextCursor)) return null;
    seenCursors.add(window.nextCursor);
    cursor = window.nextCursor;
  }

  // Ran out of pages without terminating. Everything read is still real, but it
  // is explicitly not the whole set.
  return { items, coverage: lastCoverage, pages, wholeSet: false };
}

export interface PlatformTaskSnapshotRequest extends PlatformTaskWalkRequest {}

/**
 * Whole-set id snapshot for the platform generation (ADR-004 D3).
 *
 * `null` (not an empty snapshot) for anything we did not fully understand: a
 * non-200, an unparseable body, or a walk that never terminated. A
 * `complete: true` empty snapshot would delete every local row.
 */
export async function fetchPlatformTaskIdSnapshot(
  http: HttpClient,
  request: PlatformTaskSnapshotRequest = {},
): Promise<IdSnapshot | null> {
  const walk = await walkPlatformTaskPages(http, request);
  if (walk === null) return null;
  const ids = walk.items.map((task) => task.id);
  return {
    setVersion: platformTaskSetVersion(ids, walk.coverage),
    complete: walk.wholeSet,
    ids,
  };
}

/**
 * A set version that changes whenever the set does. FNV-1a over the sorted ids,
 * matching the legacy adapter's shape so `Projection.reconcile`'s "same
 * version, skip the work" fast path behaves identically across generations. It
 * is a content hash, not a server token: the ratified contract exposes no
 * whole-set version (`declaredFrontier` describes coverage, not the id set), so
 * deriving it from what we actually hold is the honest option.
 */
function platformTaskSetVersion(ids: readonly string[], coverage: PlatformTaskCoverageState): string {
  let h = 0x811c9dc5;
  const feed = (value: string): void => {
    for (let index = 0; index < value.length; index++) {
      h ^= value.charCodeAt(index);
      h = Math.imul(h, 0x01000193);
    }
    h ^= 0x2c; // separator
    h = Math.imul(h, 0x01000193);
  };
  for (const id of [...ids].sort()) feed(id);
  // Fold in the declared status so a set that is byte-identical but was
  // gathered under different coverage does not reuse a version.
  feed(coverage.kind === "known" ? coverage.status : "unknown");
  return `ptask1-${(h >>> 0).toString(16)}`;
}
