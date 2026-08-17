/**
 * SynthesizedMemoriesStore — the platform generation's memory read store.
 *
 * The one object a platform-generation Memories surface talks to. It is the
 * read-model counterpart of `MemoriesStore`, and the differences from that
 * exemplar are all consequences of one fact: there are no writes.
 *
 *  - No `Outbox`. There is nothing to enqueue, so `status().queue` is a
 *    permanently idle `QueueStatus`. It is still REPORTED, because a surface
 *    must render offline/queue state identically across generations — that is
 *    the whole promise of the `ProductionStores` ports. A surface that had to
 *    ask which generation it was on to know whether `queue` exists would make
 *    the port a lie.
 *  - No `Projection`. `Projection` exists to merge pending write overlays onto
 *    durable server rows and to run `reconcile`. With no writes there is no
 *    overlay, and reconcile's delete path is exactly what rule 12 spends its
 *    effort restraining. The durable cache here is a plain `DurableKv`
 *    snapshot of the last honest read.
 *  - No alias map. The platform wire has no client-supplied create ids to
 *    reconcile, because it has no creates.
 *
 * THE HONESTY RULE THIS STORE ADDS
 *
 * Cached items survive a reopen; the RECALL STATE DOES NOT. On open, before
 * any refresh, `recall()` is `{ kind: "unknown" }` even when the cache is
 * full. Coverage is a claim about the server's state at the moment it was
 * made, and a claim we persisted yesterday says nothing about today. Restoring
 * a cached `complete` would let a cold start tell a user "that is everything"
 * about a set it has not looked at — the same class of failure as inferring
 * completeness from a short page, arriving through the cache instead of
 * through the wire.
 */

import type { DurableKv, StorageBridge } from "@omi-core/contracts";
import type { HttpClient, SynthesizedMemoryItem, SynthesizedRecallState } from "@omi-core/contracts";
import type { Env } from "@omi-core/kernel";
import type { QueueStatus } from "@omi-core/sync";
import {
  fetchSynthesizedMemoryPage,
  synthesizedMemoryItemsFromPage,
  synthesizedRecallStateFromPage,
  type PlatformRecallPageRequest,
} from "@omi-core/adapters-platform";
import { RefreshTracker, type StoreStatus } from "./store-status.js";

const ITEMS_KEY = "items";

/** A read model never queues a write. Reported, never derived by the surface. */
const READ_ONLY_QUEUE: QueueStatus = { phase: "idle", pendingCount: 0 };

export interface SynthesizedMemoriesStoreOptions {
  /** Route override; the transport binding still owns the base URL. */
  readonly path?: string;
  readonly limit?: number;
}

export class SynthesizedMemoriesStore {
  private listeners = new Set<() => void>();
  private items: readonly SynthesizedMemoryItem[] = [];
  private recallState: SynthesizedRecallState = { kind: "unknown" };
  private nextCursor: string | null = null;
  private readonly refreshTracker: RefreshTracker;

  private constructor(
    private readonly http: HttpClient,
    private readonly kv: DurableKv,
    private readonly options: SynthesizedMemoriesStoreOptions,
    hasSavedData: boolean,
  ) {
    this.refreshTracker = new RefreshTracker(hasSavedData);
  }

  static async open(
    bridge: StorageBridge,
    _env: Env,
    http: HttpClient,
    options: SynthesizedMemoriesStoreOptions = {},
  ): Promise<SynthesizedMemoriesStore> {
    const kv = await bridge.openKv("synthesized-memories");
    const cached = readCachedItems(await kv.get(ITEMS_KEY));
    const store = new SynthesizedMemoriesStore(http, kv, options, cached.length > 0);
    store.items = cached;
    // Deliberately NOT restored: `recallState` stays `unknown`. See the file
    // header — a persisted coverage claim is not evidence about today.
    return store;
  }

  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  async list(): Promise<readonly SynthesizedMemoryItem[]> {
    return this.items;
  }

  recall(): SynthesizedRecallState {
    return this.recallState;
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
   * Failures are silent-degrade, exactly as `MemoriesStore.refresh` is: the
   * cached items keep serving and the refresh phase reports the failure. What
   * does NOT survive a failure is the recall state — a page we could not read
   * moves us to `unknown`, never leaving a stale `complete` on screen.
   */
  async refresh(): Promise<void> {
    const token = this.refreshTracker.begin();
    this.notify();
    const outcome = await fetchSynthesizedMemoryPage(this.http, this.pageRequest(null));
    if (!this.refreshTracker.isCurrent(token)) return;

    if (outcome.kind !== "page") {
      this.recallState = { kind: "unknown" };
      this.refreshTracker.complete(token, false, this.items.length > 0);
      this.notify();
      return;
    }

    const items = synthesizedMemoryItemsFromPage(outcome.page);
    await this.refreshTracker.applyIfCurrent(token, async () => {
      this.items = items;
      this.recallState = synthesizedRecallStateFromPage(outcome.page);
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
   * A failed continuation does NOT discard what is already loaded — but it
   * does move recall to `unknown`, because the window we hold is now a prefix
   * of something whose coverage we no longer know.
   */
  async loadMore(): Promise<void> {
    const cursor = this.nextCursor;
    if (cursor === null) return;
    const outcome = await fetchSynthesizedMemoryPage(this.http, this.pageRequest(cursor));
    if (outcome.kind !== "page") {
      this.recallState = { kind: "unknown" };
      this.notify();
      return;
    }
    // Dedupe by id, keeping the FIRST occurrence, i.e. the earlier page.
    //
    // `walkSynthesizedMemoryPages` refuses a walk with repeated ids outright,
    // because a broken keyset guarantee makes the whole SET unreliable and a
    // set is what licenses deletion. Here nothing is being deleted — this is
    // incremental display — so refusing to render is the wrong trade: the user
    // would lose a working feed over a server hiccup. Keeping the first
    // occurrence preserves deterministic server order and cannot double a row.
    // The two answers differ because the two decisions differ.
    const appended = dedupeById([...this.items, ...synthesizedMemoryItemsFromPage(outcome.page)]);
    this.items = appended;
    this.recallState = synthesizedRecallStateFromPage(outcome.page);
    this.nextCursor = outcome.page.window.hasMore ? outcome.page.window.nextCursor : null;
    await this.kv.set(ITEMS_KEY, JSON.stringify(appended));
    this.notify();
  }

  /** Symmetry with the write stores: a read model has no paused queue to resume. */
  onAuthRestored(): void {
    // Intentionally empty. Declared so the surface-facing shape is uniform.
  }

  private pageRequest(cursor: string | null): PlatformRecallPageRequest {
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

/**
 * Cache reads never throw and never half-load. A corrupt or foreign cache is
 * treated as no cache: the store starts empty and `unknown`, which a refresh
 * repairs. Salvaging individual rows out of a damaged blob would put items on
 * screen that no server ever sent.
 */
/** First occurrence wins, so deterministic server order survives. */
function dedupeById(items: readonly SynthesizedMemoryItem[]): readonly SynthesizedMemoryItem[] {
  const seen = new Set<string>();
  const out: SynthesizedMemoryItem[] = [];
  for (const item of items) {
    if (seen.has(item.id)) continue;
    seen.add(item.id);
    out.push(item);
  }
  return out;
}

function readCachedItems(raw: string | null): readonly SynthesizedMemoryItem[] {
  if (raw === null) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    const items: SynthesizedMemoryItem[] = [];
    for (const row of parsed) {
      if (typeof row !== "object" || row === null) return [];
      const candidate = row as { id?: unknown; text?: unknown };
      if (typeof candidate.id !== "string" || typeof candidate.text !== "string") return [];
      if (candidate.id.length === 0 || candidate.text.trim().length === 0) return [];
      items.push(row as SynthesizedMemoryItem);
    }
    return items;
  } catch {
    return [];
  }
}
