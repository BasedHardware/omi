/**
 * PlatformTasksStore — the platform generation's task READ store.
 *
 * The one object a platform-generation Tasks surface talks to. Structurally the
 * sibling of `SynthesizedMemoriesStore`, and the differences from `TasksStore`
 * (the legacy one) are all consequences of one fact: this store has no writes.
 *
 *  - No `Outbox`. There is nothing to enqueue, so `status().queue` is a
 *    permanently idle `QueueStatus`. It is still REPORTED, because a surface
 *    must render offline/queue state identically across generations — that is
 *    the whole promise of the `ProductionStores` ports, and it is what
 *    `DAVID-tasks-read-epoch-and-ci` D2's parity is FOR. A surface that had to
 *    ask which generation it was on would make the port a lie.
 *  - No `Projection` and no alias map. Writes go through `POST /v1/tasks/ops`,
 *    which is a separate ratified wire with its own idempotency; the local
 *    slug ↔ server id alias `adapters-legacy/src/tasks.ts` maintains does not
 *    cross this wire at all (D2).
 *
 * THE HONESTY RULE, carried over verbatim from the memories read store because
 * it is not a memories-specific rule: cached items survive a reopen, THE
 * COVERAGE STATE DOES NOT. On open, before any refresh, `coverage()` is
 * `{ kind: "unknown" }` even when the cache is full. Coverage is a claim about
 * the server's state at the moment it was made, and a claim persisted yesterday
 * says nothing about today. Restoring a cached `complete` would let a cold start
 * tell a user "that is everything" about a set it has not looked at.
 *
 * It matters more here than it does for memories. A tasks page can be
 * `incomplete` for `pending_writes` — an op the write path applied that this
 * projection has not caught up with — so a restored `complete` could hide the
 * user's own most recent edit and report the set as whole.
 *
 * WHAT THIS STORE DELIBERATELY DOES NOT DO: reconcile or delete. Nothing here
 * removes a local row. `fetchPlatformTaskIdSnapshot` exists for the day a
 * reconciling caller needs one, and it is the thing that carries the
 * `wholeSet` flag; this store only ever replaces or appends what it displays.
 */

import type { DurableKv, StorageBridge } from "@omi-core/contracts";
import type { HttpClient, PlatformTaskCoverageState, PlatformTaskItem } from "@omi-core/contracts";
import type { Env } from "@omi-core/kernel";
import type { QueueStatus } from "@omi-core/sync";
import {
  fetchPlatformTaskPage,
  platformTaskCoverageFromPage,
  platformTaskItemsFromPage,
  type PlatformTasksPageRequest,
} from "@omi-core/adapters-platform";
import { RefreshTracker, type StoreStatus } from "./store-status.js";

const ITEMS_KEY = "items";

/** A read model never queues a write. Reported, never derived by the surface. */
const READ_ONLY_QUEUE: QueueStatus = { phase: "idle", pendingCount: 0 };

export interface PlatformTasksStoreOptions {
  /** Route override; the transport binding still owns the base URL. */
  readonly path?: string;
  readonly limit?: number;
}

export class PlatformTasksStore {
  private listeners = new Set<() => void>();
  private items: readonly PlatformTaskItem[] = [];
  private coverageState: PlatformTaskCoverageState = { kind: "unknown" };
  private nextCursor: string | null = null;
  private readonly refreshTracker: RefreshTracker;

  private constructor(
    private readonly http: HttpClient,
    private readonly kv: DurableKv,
    private readonly options: PlatformTasksStoreOptions,
    hasSavedData: boolean,
  ) {
    this.refreshTracker = new RefreshTracker(hasSavedData);
  }

  static async open(
    bridge: StorageBridge,
    _env: Env,
    http: HttpClient,
    options: PlatformTasksStoreOptions = {},
  ): Promise<PlatformTasksStore> {
    const kv = await bridge.openKv("platform-tasks");
    const cached = readCachedItems(await kv.get(ITEMS_KEY));
    const store = new PlatformTasksStore(http, kv, options, cached.length > 0);
    store.items = cached;
    // Deliberately NOT restored: `coverageState` stays `unknown`. See the header.
    return store;
  }

  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  async list(): Promise<readonly PlatformTaskItem[]> {
    return this.items;
  }

  coverage(): PlatformTaskCoverageState {
    return this.coverageState;
  }

  hasMore(): boolean {
    return this.nextCursor !== null;
  }

  status(): StoreStatus {
    return { refresh: this.refreshTracker.snapshot(), queue: READ_ONLY_QUEUE };
  }

  /**
   * Re-read from the FIRST page, replacing what we hold.
   *
   * Failures silent-degrade exactly as the legacy store's refresh does: cached
   * items keep serving and the refresh phase reports the failure. What does NOT
   * survive a failure is the coverage state — a page we could not read moves us
   * to `unknown`, never leaving a stale `complete` on screen.
   */
  async refresh(): Promise<void> {
    const token = this.refreshTracker.begin();
    this.notify();
    const outcome = await fetchPlatformTaskPage(this.http, this.pageRequest(null));
    if (!this.refreshTracker.isCurrent(token)) return;

    if (outcome.kind !== "page") {
      this.coverageState = { kind: "unknown" };
      this.refreshTracker.complete(token, false, this.items.length > 0);
      this.notify();
      return;
    }

    const items = platformTaskItemsFromPage(outcome.page);
    await this.refreshTracker.applyIfCurrent(token, async () => {
      this.items = items;
      this.coverageState = platformTaskCoverageFromPage(outcome.page);
      this.nextCursor = outcome.page.window.hasMore ? outcome.page.window.nextCursor : null;
      await this.kv.set(ITEMS_KEY, JSON.stringify(items));
    });
    if (this.refreshTracker.isCurrent(token)) {
      this.refreshTracker.complete(token, true, this.items.length > 0);
    }
    this.notify();
  }

  /**
   * Append the next keyset page. A no-op when there is no continuation, so a
   * surface may call it on scroll without tracking `hasMore()` itself.
   *
   * A failed continuation does NOT discard what is already loaded — but it does
   * move coverage to `unknown`, because the window we hold is now a prefix of
   * something whose coverage we no longer know.
   */
  async loadMore(): Promise<void> {
    const cursor = this.nextCursor;
    if (cursor === null) return;
    const outcome = await fetchPlatformTaskPage(this.http, this.pageRequest(cursor));
    if (outcome.kind !== "page") {
      this.coverageState = { kind: "unknown" };
      this.notify();
      return;
    }
    // Dedupe by id, keeping the FIRST occurrence, i.e. the earlier page.
    //
    // `walkPlatformTaskPages` refuses a walk with repeated ids OUTRIGHT, and the
    // two answers differ because the two decisions differ: a walk's product is a
    // SET, and a set is what licenses deleting local rows, so an unreliable one
    // must produce no answer at all. Nothing is being deleted here — this is
    // incremental display — and refusing to render would lose a user their
    // working list over a server hiccup. Keeping the first occurrence preserves
    // deterministic server order and cannot double a row.
    const appended = dedupeById([...this.items, ...platformTaskItemsFromPage(outcome.page)]);
    this.items = appended;
    this.coverageState = platformTaskCoverageFromPage(outcome.page);
    this.nextCursor = outcome.page.window.hasMore ? outcome.page.window.nextCursor : null;
    await this.kv.set(ITEMS_KEY, JSON.stringify(appended));
    this.notify();
  }

  /** Symmetry with the write stores: a read model has no paused queue to resume. */
  onAuthRestored(): void {
    // Intentionally empty. Declared so the surface-facing shape is uniform.
  }

  private pageRequest(cursor: string | null): PlatformTasksPageRequest {
    return {
      ...(this.options.path !== undefined ? { path: this.options.path } : {}),
      ...(this.options.limit !== undefined ? { limit: this.options.limit } : {}),
      cursor,
    };
  }

  private notify(): void {
    for (const fn of this.listeners) fn();
  }
}

/** First occurrence wins, so deterministic server order survives. */
function dedupeById(items: readonly PlatformTaskItem[]): readonly PlatformTaskItem[] {
  const seen = new Set<string>();
  const out: PlatformTaskItem[] = [];
  for (const item of items) {
    if (seen.has(item.id)) continue;
    seen.add(item.id);
    out.push(item);
  }
  return out;
}

/**
 * Cache reads never throw and never half-load. A corrupt or foreign cache is
 * treated as no cache: the store starts empty and `unknown`, which a refresh
 * repairs. Salvaging individual rows out of a damaged blob would put items on
 * screen that no server ever sent.
 *
 * The field check is ALL THIRTEEN, not a spot check on `id`. A cache written by
 * an older build could hold a narrower row, and a narrower row rendered beside a
 * full one is exactly the visible difference D2's parity exists to prevent — so
 * a cache that cannot produce the full record class is discarded wholesale
 * rather than partially trusted.
 */
function readCachedItems(raw: string | null): readonly PlatformTaskItem[] {
  if (raw === null) return [];
  const REQUIRED = [
    "id", "description", "completed", "completedAt", "dueAt", "owner", "source",
    "provenance", "sortOrder", "indentLevel", "createdAt", "updatedAt", "revision",
  ] as const;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    const items: PlatformTaskItem[] = [];
    for (const row of parsed) {
      if (typeof row !== "object" || row === null) return [];
      const candidate = row as Record<string, unknown>;
      for (const key of REQUIRED) {
        if (!Object.hasOwn(candidate, key)) return [];
      }
      if (typeof candidate["id"] !== "string" || candidate["id"].length === 0) return [];
      items.push(row as PlatformTaskItem);
    }
    return items;
  } catch {
    return [];
  }
}
