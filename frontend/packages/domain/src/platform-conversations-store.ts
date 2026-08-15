/**
 * PlatformConversationsStore — platform generation conversations store.
 *
 * Reads carry the server's completeness envelope (never restored from cache).
 * Writes stay the four per-field PATCHes and delete, via Outbox, using the
 * same codec as the legacy store. `openConversations()` is NOT repointed here.
 */

import type {
  Conversation,
  ConversationPatch,
  DeadLetter,
  DurableKv,
  HttpClient,
  PlatformConversationCoverageState,
  PlatformConversationItem,
  RecordId,
  StorageBridge,
} from "@omi-core/contracts";
import type { Env } from "@omi-core/kernel";
import { Outbox } from "@omi-core/sync";
import {
  conversationsTransport,
  fetchPlatformConversationPage,
  platformConversationCoverageFromPage,
  platformConversationItemsFromPage,
  type PlatformConversationsPageRequest,
} from "@omi-core/adapters-platform";
import {
  buildDeleteConversation,
  buildPatchConversation,
  conversationToPendingOp,
  conversationsCodec,
} from "./conversations-codec.js";
import { RefreshTracker, type StoreStatus } from "./store-status.js";

const ITEMS_KEY = "items";

export interface PlatformConversationsStoreOptions {
  readonly path?: string;
  readonly limit?: number;
}

export class PlatformConversationsStore {
  private listeners = new Set<() => void>();
  private items: readonly PlatformConversationItem[] = [];
  private coverageState: PlatformConversationCoverageState = { kind: "unknown" };
  private nextCursor: string | null = null;
  private readonly refreshTracker: RefreshTracker;

  private constructor(
    private readonly env: Env,
    private readonly http: HttpClient,
    private readonly kv: DurableKv,
    private readonly outbox: Outbox,
    private readonly options: PlatformConversationsStoreOptions,
    hasSavedData: boolean,
  ) {
    this.refreshTracker = new RefreshTracker(hasSavedData);
  }

  static async open(
    bridge: StorageBridge,
    env: Env,
    http: HttpClient,
    options: PlatformConversationsStoreOptions = {},
  ): Promise<PlatformConversationsStore> {
    const kv = await bridge.openKv("platform-conversations");
    const cached = readCachedItems(await kv.get(ITEMS_KEY));
    let store: PlatformConversationsStore;
    const transport = conversationsTransport(http, () => undefined);
    const outbox = await Outbox.open(bridge, env, transport, "platform-conversations");
    store = new PlatformConversationsStore(env, http, kv, outbox, options, cached.length > 0);
    store.items = cached;
    outbox.onChange = () => store.notify();
    outbox.onOutcome = async (op, outcome) => {
      if (outcome.state !== "confirmed") return;
      const current = store.items.find((row) => row.id === op.recordId) ?? null;
      const next = conversationsCodec.applyOp(op.payload, current as Conversation | null);
      if (next === null) {
        store.items = store.items.filter((row) => row.id !== op.recordId);
      } else {
        store.items = store.items.map((row) => (row.id === next.id ? next : row));
      }
      await store.kv.set(ITEMS_KEY, JSON.stringify(store.items));
      store.notify();
    };
    return store;
  }

  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  async list(): Promise<readonly PlatformConversationItem[]> {
    const pending = this.outbox.pendingOps().map((o) => ({ recordId: o.recordId, payload: o.payload }));
    const overlaid = this.items.map((item) => {
      let current: Conversation | null = item as Conversation;
      for (const op of pending.filter((pendingOp) => pendingOp.recordId === item.id)) {
        current = conversationsCodec.applyOp(op.payload, current);
        if (current === null) return null;
      }
      return current as PlatformConversationItem | null;
    });
    return overlaid.filter((row): row is PlatformConversationItem => row !== null)
      .sort((a, b) => b.updatedAt - a.updatedAt || b.createdAt - a.createdAt);
  }

  coverage(): PlatformConversationCoverageState {
    return this.coverageState;
  }

  hasMore(): boolean {
    return this.nextCursor !== null;
  }

  status(): StoreStatus {
    return { refresh: this.refreshTracker.snapshot(), queue: this.outbox.queueStatus() };
  }

  deadLetters(): Promise<DeadLetter[]> {
    return this.outbox.deadLetters();
  }

  discardDeadLetter(opId: string): Promise<void> {
    return this.outbox.discardDeadLetter(opId);
  }

  async patch(id: RecordId, patch: ConversationPatch): Promise<void> {
    await this.outbox.enqueue(conversationToPendingOp(buildPatchConversation(this.env, id, patch)));
    this.notify();
  }

  async delete(id: RecordId): Promise<void> {
    await this.outbox.enqueue(conversationToPendingOp(buildDeleteConversation(this.env, id)));
    this.notify();
  }

  onAuthRestored(): void {
    this.outbox.onAuthRestored();
  }

  async refresh(): Promise<void> {
    const token = this.refreshTracker.begin();
    this.notify();
    const outcome = await fetchPlatformConversationPage(this.http, this.pageRequest(null));
    if (!this.refreshTracker.isCurrent(token)) return;

    if (outcome.kind !== "page") {
      this.coverageState = { kind: "unknown" };
      this.refreshTracker.complete(token, false, this.items.length > 0);
      this.notify();
      return;
    }

    const items = platformConversationItemsFromPage(outcome.page);
    await this.refreshTracker.applyIfCurrent(token, async () => {
      this.items = items;
      this.coverageState = platformConversationCoverageFromPage(outcome.page);
      this.nextCursor = outcome.page.window.hasMore ? outcome.page.window.nextCursor : null;
      await this.kv.set(ITEMS_KEY, JSON.stringify(items));
    });
    if (this.refreshTracker.isCurrent(token)) {
      this.refreshTracker.complete(token, true, this.items.length > 0);
    }
    this.notify();
  }

  async loadMore(): Promise<void> {
    if (this.nextCursor === null) return;
    const token = this.refreshTracker.begin();
    this.notify();
    const outcome = await fetchPlatformConversationPage(this.http, this.pageRequest(this.nextCursor));
    if (!this.refreshTracker.isCurrent(token)) return;
    if (outcome.kind !== "page") {
      this.coverageState = { kind: "unknown" };
      this.refreshTracker.complete(token, false, this.items.length > 0);
      this.notify();
      return;
    }
    const incoming = platformConversationItemsFromPage(outcome.page);
    await this.refreshTracker.applyIfCurrent(token, async () => {
      this.items = [...this.items, ...incoming];
      this.coverageState = platformConversationCoverageFromPage(outcome.page);
      this.nextCursor = outcome.page.window.hasMore ? outcome.page.window.nextCursor : null;
      await this.kv.set(ITEMS_KEY, JSON.stringify(this.items));
    });
    if (this.refreshTracker.isCurrent(token)) {
      this.refreshTracker.complete(token, true, this.items.length > 0);
    }
    this.notify();
  }

  private pageRequest(cursor: string | null): PlatformConversationsPageRequest {
    return {
      ...(this.options.limit !== undefined ? { limit: this.options.limit } : {}),
      ...(this.options.path !== undefined ? { path: this.options.path } : {}),
      cursor,
    };
  }

  private notify(): void {
    for (const fn of this.listeners) fn();
  }
}

function readCachedItems(raw: string | null): readonly PlatformConversationItem[] {
  if (raw === null) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed as PlatformConversationItem[] : [];
  } catch {
    return [];
  }
}
