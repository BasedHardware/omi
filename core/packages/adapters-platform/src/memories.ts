/**
 * Platform-generation memory READ adapter — the client half of the ratified
 * contract seam.
 *
 * It speaks `@omi-core/ratified-contracts` 0.1.1 (`SynthesizedMemoryRead`),
 * the same artifact the new backend consumes as a tarball pinned by content
 * hash in `contracts.lock.json`. Both ends validate against the same source,
 * and both ends test against the same six fixture corpora, which is what makes
 * "the backend is ready for memories" a green suite instead of a judgment
 * call (`core/README.md`, the dual-migration rule).
 *
 * WHAT THIS ADAPTER DELIBERATELY DOES NOT DO
 *
 * It has no writes. The ratified scope is the read path only, and the read
 * projection has no editable field to write to. It does not map onto
 * `Memory`; see `contracts/src/domain/synthesized-memories.ts` for why that
 * mapping cannot be made honestly.
 *
 * It never repairs a body. If a page does not satisfy the ratified validator,
 * the outcome is `unreadable` and the caller gets `kind: "unknown"` — never a
 * partially salvaged page, never an empty page, never a `complete` claim. A
 * malformed body is the case the contract was written to catch; salvaging it
 * would discard exactly the signal we paid for.
 *
 * THE PARSE BOUNDARY (see `HttpResponse.text` in contracts/src/http.ts)
 *
 * The contract's authoritative boundary is `parseSynthesizedPageJson(raw)`,
 * defined over the response BYTES: it rejects noncanonical encodings,
 * duplicate keys, and oversized payloads before the contract predicate runs.
 * The `HttpClient` seam historically exposed only a pre-parsed `json`, so we
 * take the raw text when the binding provides it and fall back to the
 * object-level predicate when it does not — and we REPORT which one was used
 * (`PlatformRecallParseBoundary`) rather than treating them as equivalent.
 * `blocked/FE-CORE-http-raw-body.md` carries the finding.
 */

import type { HttpClient, HttpResponse, IdSnapshot } from "@omi-core/contracts";
import type {
  SynthesizedMemoryItem,
  SynthesizedRecallReason,
  SynthesizedRecallState,
  SynthesizedRecallStatus,
} from "@omi-core/contracts";
import {
  MAX_SYNTHESIZED_PAGE_JSON_CODE_UNITS,
  isTrustedSynthesizedPageData,
  parseSynthesizedPageJson,
  type SynthesizedMemoryRead,
} from "@omi-core/ratified-contracts/projections/synthesized";

/**
 * The recall page route. PROVISIONAL: at the time of writing the platform
 * service's Hono shell exposes only `/health` and `/ready`
 * (`apps/service/app.ts` on the backend SoT), so no route is ratified yet.
 * Every entry point takes an override, and nothing in this package hardcodes
 * a base URL — the transport binding owns that (ADR-008 §3).
 * See `blocked/FE-CORE-recall-endpoint-path.md`.
 */
export const PLATFORM_MEMORY_RECALL_PATH = "/v1/memories/recall";

/**
 * The backend's `MAX_PAGE_LIMIT` (`core/retrieve/application-read.ts`). Asking
 * for more is not an error there, it is silently clamped — so asking for more
 * would make our "did the walk terminate" reasoning depend on a clamp we
 * cannot observe. Ask for what the server will actually honor.
 */
export const PLATFORM_MEMORY_RECALL_MAX_LIMIT = 100;

/**
 * Ceiling on a whole-set walk. Not a tuning knob: it is the thing that keeps
 * a server which answers every request with the SAME `hasMore` continuation
 * from spinning this client forever. Hitting it is a failure to terminate, and
 * a walk that did not terminate can never claim completeness.
 */
export const PLATFORM_MEMORY_RECALL_MAX_PAGES = 200;

/** Which of the two contract boundaries actually validated this body. */
export type PlatformRecallParseBoundary =
  /** `parseSynthesizedPageJson` over the raw bytes — the authoritative one. */
  | "canonical-json-text"
  /** `isTrustedSynthesizedPageData` over `JSON.parse` output — weaker. */
  | "trusted-parsed-json";

export type PlatformRecallPageOutcome =
  | {
      readonly kind: "page";
      readonly page: SynthesizedMemoryRead.Page;
      readonly boundary: PlatformRecallParseBoundary;
    }
  /** Transport answered, but not with a 200. Nothing is known about the set. */
  | { readonly kind: "http-error"; readonly status: number }
  /**
   * 200, and the body did not satisfy the ratified contract. This is NOT an
   * empty page and NOT a complete page. It is the absence of knowledge.
   */
  | { readonly kind: "unreadable"; readonly boundary: PlatformRecallParseBoundary };

export interface PlatformRecallPageRequest {
  /** Clamped into `[1, PLATFORM_MEMORY_RECALL_MAX_LIMIT]`. */
  readonly limit?: number;
  /** Opaque server cursor from a previous page's `window.nextCursor`. */
  readonly cursor?: string | null;
  readonly path?: string;
}

/** One recall page, validated at the strongest boundary the transport allows. */
export async function fetchSynthesizedMemoryPage(
  http: HttpClient,
  request: PlatformRecallPageRequest = {},
): Promise<PlatformRecallPageOutcome> {
  const limit = clampLimit(request.limit);
  const path = request.path ?? PLATFORM_MEMORY_RECALL_PATH;
  const query = request.cursor
    ? `?limit=${limit}&cursor=${encodeURIComponent(request.cursor)}`
    : `?limit=${limit}`;

  const res = await http.request("GET", `${path}${query}`);
  if (res.status !== 200) return { kind: "http-error", status: res.status };
  return parseSynthesizedMemoryPageResponse(res);
}

/**
 * Body → page, at the strongest boundary this response supports. Exported so
 * the conformance corpora can drive it directly with a scripted response,
 * which is the only way a hermetic test can prove the boundary selection.
 */
export function parseSynthesizedMemoryPageResponse(res: HttpResponse): PlatformRecallPageOutcome {
  if (typeof res.text === "string") {
    const page = parseSynthesizedPageJson(res.text);
    return page === null
      ? { kind: "unreadable", boundary: "canonical-json-text" }
      : { kind: "page", page, boundary: "canonical-json-text" };
  }
  // No raw body available. The object predicate is the weaker boundary — it
  // cannot see duplicate keys (JSON.parse already dropped them) or a
  // noncanonical encoding. We still enforce the size ceiling the contract
  // defines, so an oversized payload is refused at both boundaries rather
  // than only at the strong one.
  if (!isTrustedSynthesizedPageData(res.json)) {
    return { kind: "unreadable", boundary: "trusted-parsed-json" };
  }
  if (!withinContractSizeCeiling(res.json)) {
    return { kind: "unreadable", boundary: "trusted-parsed-json" };
  }
  return { kind: "page", page: res.json, boundary: "trusted-parsed-json" };
}

function withinContractSizeCeiling(value: unknown): boolean {
  try {
    return JSON.stringify(value).length <= MAX_SYNTHESIZED_PAGE_JSON_CODE_UNITS;
  } catch {
    return false;
  }
}

function clampLimit(requested: number | undefined): number {
  if (requested === undefined || !Number.isSafeInteger(requested) || requested < 1) {
    return PLATFORM_MEMORY_RECALL_MAX_LIMIT;
  }
  return Math.min(requested, PLATFORM_MEMORY_RECALL_MAX_LIMIT);
}

/**
 * Contract page → surface items. A pure projection: it copies the fields the
 * contract permits and nothing else, and it strips the ratified brands, which
 * is the only place that is allowed to happen (the values already passed the
 * validator that created them).
 *
 * Optional metadata is genuinely optional. An item with no `citations` and no
 * `provenance` renders identically to one that has both, and the absent keys
 * stay ABSENT rather than becoming `undefined`/`[]` — a caller must not be
 * able to tell "the server sent no citations" from "the server sent an empty
 * citation list" by accident, because under `exactOptionalPropertyTypes` those
 * are different values and only one of them is a claim.
 */
export function synthesizedMemoryItemsFromPage(
  page: SynthesizedMemoryRead.Page,
): readonly SynthesizedMemoryItem[] {
  return page.items.map((item): SynthesizedMemoryItem => ({
    id: item.id,
    text: item.text,
    ...(item.citations !== undefined ? { citations: [...item.citations] } : {}),
    ...(item.provenance !== undefined
      ? {
          provenance: {
            synthesisVersion: item.provenance.synthesisVersion,
            inputDigest: item.provenance.inputDigest,
            outputDigest: item.provenance.outputDigest,
          },
        }
      : {}),
  }));
}

/**
 * Contract page → the honest recall state a surface renders.
 *
 * Every field here is CARRIED, never derived. `complete` is the server's
 * declared `completeness.status`, not an inference from `items.length`, page
 * fullness, or `window.hasMore`. The window and the completeness envelope are
 * two different claims — a page can be the terminal window of a walk whose
 * recall was `degraded` — and collapsing them is how a client ends up telling
 * a user "that is everything" about a projection the server said was stale.
 */
export function synthesizedRecallStateFromPage(
  page: SynthesizedMemoryRead.Page,
): SynthesizedRecallState {
  // No casts. `status` and `reasons` are assigned across the seam by
  // STRUCTURAL ASSIGNABILITY, so the day the ratified contract adds a
  // completeness status or a limitation reason, this file stops compiling and
  // a human decides how a surface explains it. A cast here would silently
  // widen the new value into the old union and ship an unexplained page.
  const status: SynthesizedRecallStatus = page.completeness.status;
  const reasons: readonly SynthesizedRecallReason[] = [...page.completeness.reasons];
  return {
    kind: "known",
    status,
    reasons,
    complete: page.completeness.status === "complete",
    queryGap: page.absence !== null,
    hasMore: page.window.hasMore,
  };
}

/** What a whole-set walk learned. `complete` here is load-bearing: see below. */
export interface SynthesizedMemoryWalk {
  readonly items: readonly SynthesizedMemoryItem[];
  /** State of the LAST page walked — the one that terminated (or did not). */
  readonly recall: SynthesizedRecallState;
  /** Pages actually fetched. `0` is impossible; the walk always reads one. */
  readonly pages: number;
  /**
   * True only under every condition in `fetchSynthesizedMemoryIdSnapshot`'s
   * contract. This is the flag that licenses deleting local rows.
   */
  readonly wholeSet: boolean;
}

export interface PlatformRecallWalkRequest {
  readonly limit?: number;
  readonly path?: string;
  readonly maxPages?: number;
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
 *   4. the terminal page's window is the complete-terminal variant
 *      (`status: "complete"`, `hasMore: false`, `nextCursor: null`);
 *   5. the walk terminated inside `maxPages`.
 *
 * Condition 3 is the one that is easy to get wrong and expensive to get
 * wrong. `window` describes THIS PAGE's pagination; `completeness` describes
 * how much of the user's memory the server searched. The ratified status
 * matrix (`fixtures/status-matrix.json`) permits `complete_terminal` paired
 * with `degraded` completeness and marks it SAFE — safe to serialize, not
 * safe to reconcile against. A walk that ANDs only the windows would end on a
 * complete-terminal page, claim the whole set, and delete every local row the
 * degraded projection failed to return.
 *
 * Returns `null` when the walk could not be completed honestly at all (any
 * `http-error` or `unreadable`), because a partial walk's items are not a
 * page and must not be presented as one.
 */
export async function walkSynthesizedMemoryPages(
  http: HttpClient,
  request: PlatformRecallWalkRequest = {},
): Promise<SynthesizedMemoryWalk | null> {
  const maxPages = request.maxPages ?? PLATFORM_MEMORY_RECALL_MAX_PAGES;
  const items: SynthesizedMemoryItem[] = [];
  let cursor: string | null = null;
  let pages = 0;
  let everyPageCompleteRecall = true;
  let lastRecall: SynthesizedRecallState = { kind: "unknown" };

  while (pages < maxPages) {
    const pageRequest: PlatformRecallPageRequest = {
      ...(request.limit !== undefined ? { limit: request.limit } : {}),
      ...(request.path !== undefined ? { path: request.path } : {}),
      cursor,
    };
    const outcome = await fetchSynthesizedMemoryPage(http, pageRequest);
    if (outcome.kind !== "page") return null;
    pages += 1;

    items.push(...synthesizedMemoryItemsFromPage(outcome.page));
    lastRecall = synthesizedRecallStateFromPage(outcome.page);
    if (outcome.page.completeness.status !== "complete") everyPageCompleteRecall = false;

    const window = outcome.page.window;
    if (!window.hasMore) {
      return {
        items,
        recall: lastRecall,
        pages,
        // Condition 4: only the complete-terminal variant. An
        // incomplete-terminal window ends the walk without proving the set.
        wholeSet: everyPageCompleteRecall && window.status === "complete",
      };
    }
    // The contract guarantees a continuation window carries a cursor; the
    // validator already rejected `hasMore` without one, so this is total.
    cursor = window.nextCursor;
  }

  // Ran out of pages without terminating. Everything read is still real, but
  // it is explicitly not the whole set.
  return { items, recall: lastRecall, pages, wholeSet: false };
}

export interface PlatformSnapshotRequest extends PlatformRecallWalkRequest {}

/**
 * Whole-set id snapshot for the platform generation (ADR-004 D3).
 *
 * HARD RULE 12. On the legacy backend no memories source could ever back
 * `complete: true`, so `fetchMemoryIdSnapshot` hardcodes `complete: false`.
 * The ratified contract changes that — but only because the SERVER declares
 * its coverage, with frontiers and typed reasons, rather than the client
 * inferring it from a short page. The declaration is the evidence; the
 * `SnapshotDescriptor` in the shared law suite cites it.
 *
 * `null` (not an empty snapshot) for anything we did not fully understand:
 * a non-200, an unparseable body, or a walk that never terminated. A
 * `complete: true` empty snapshot would delete every local row.
 */
export async function fetchSynthesizedMemoryIdSnapshot(
  http: HttpClient,
  request: PlatformSnapshotRequest = {},
): Promise<IdSnapshot | null> {
  const walk = await walkSynthesizedMemoryPages(http, request);
  if (walk === null) return null;
  const ids = walk.items.map((item) => item.id);
  return {
    setVersion: platformSetVersion(ids, walk.recall),
    complete: walk.wholeSet,
    ids,
  };
}

/**
 * A set version that changes whenever the set does. FNV-1a over the sorted
 * ids, matching the legacy adapter's shape so `Projection.reconcile`'s
 * "same version, skip the work" fast path behaves identically across
 * generations. It is a content hash, not a server token: a server-issued
 * version would be better, but the ratified contract does not expose one for
 * the whole set (`declaredFrontier` describes accepted-work coverage, not the
 * id set), so deriving it from what we actually hold is the honest option.
 */
function platformSetVersion(ids: readonly string[], recall: SynthesizedRecallState): string {
  let h = 0x811c9dc5;
  const feed = (s: string): void => {
    for (let i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 0x01000193);
    }
    h ^= 0x2c; // separator
    h = Math.imul(h, 0x01000193);
  };
  for (const id of [...ids].sort()) feed(id);
  // Fold in the declared status so a set that is byte-identical but was
  // gathered under different coverage does not reuse a version.
  feed(recall.kind === "known" ? recall.status : "unknown");
  return `plat1-${(h >>> 0).toString(16)}`;
}
