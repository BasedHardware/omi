/**
 * PlatformFoldersStore — platform generation folders store.
 *
 * Reads carry the server's completeness envelope (never restored from cache).
 * Writes stay create/patch/delete on the four verbs already served. There is
 * no maximum-folder cap. `openFolders()` is NOT repointed here.
 */

import type {
  DeadLetter,
  DurableKv,
  Folder,
  FolderPatch,
  HttpClient,
  PlatformFolderCoverageState,
  PlatformFolderItem,
  RecordId,
  StorageBridge,
} from "@omi-core/contracts";
import type { Env } from "@omi-core/kernel";
import { Outbox } from "@omi-core/sync";
import {
  fetchPlatformFolderPage,
  foldersTransport,
  platformFolderCoverageFromPage,
  platformFolderItemsFromPage,
  type PlatformFoldersPageRequest,
} from "@omi-core/adapters-platform";
import {
  buildCreateFolder,
  buildDeleteFolder,
  buildPatchFolder,
  foldersCodec,
  folderToPendingOp,
} from "./folders-codec.js";
import { RefreshTracker, type StoreStatus } from "./store-status.js";

const ITEMS_KEY = "items";
const ALIAS_KEY = "id-aliases";

export interface PlatformFoldersStoreOptions {
  readonly path?: string;
  readonly limit?: number;
}

export class PlatformFoldersStore {
  private listeners = new Set<() => void>();
  private items: readonly PlatformFolderItem[] = [];
  private coverageState: PlatformFolderCoverageState = { kind: "unknown" };
  private nextCursor: string | null = null;
  private aliases: Record<string, string> = {};
  private readonly refreshTracker: RefreshTracker;

  private constructor(
    private readonly env: Env,
    private readonly http: HttpClient,
    private readonly kv: DurableKv,
    private readonly aliasKv: DurableKv,
    private readonly outbox: Outbox,
    private readonly options: PlatformFoldersStoreOptions,
    hasSavedData: boolean,
  ) {
    this.refreshTracker = new RefreshTracker(hasSavedData);
  }

  static async open(
    bridge: StorageBridge,
    env: Env,
    http: HttpClient,
    options: PlatformFoldersStoreOptions = {},
  ): Promise<PlatformFoldersStore> {
    const kv = await bridge.openKv("platform-folders");
    const aliasKv = await bridge.openKv("platform-folders-aliases");
    const cached = readCachedItems(await kv.get(ITEMS_KEY));
    let store: PlatformFoldersStore;
    const transport = foldersTransport(
      http,
      (localId, serverId) => void store.recordAlias(localId, serverId),
      (localId) => store.toWireId(localId),
    );
    const outbox = await Outbox.open(bridge, env, transport, "platform-folders");
    store = new PlatformFoldersStore(env, http, kv, aliasKv, outbox, options, cached.length > 0);
    store.items = cached;
    store.aliases = JSON.parse((await aliasKv.get(ALIAS_KEY)) ?? "{}") as Record<string, string>;
    outbox.onChange = () => store.notify();
    outbox.onOutcome = async (op, outcome) => {
      if (outcome.state !== "confirmed") return;
      const current = store.items.find((row) => row.id === op.recordId) ?? null;
      const next = foldersCodec.applyOp(op.payload, current as Folder | null);
      if (next === null) {
        store.items = store.items.filter((row) => row.id !== op.recordId);
      } else if (current === null) {
        store.items = [...store.items, next as PlatformFolderItem];
      } else {
        store.items = store.items.map((row) => (row.id === next.id ? next as PlatformFolderItem : row));
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

  async list(): Promise<readonly PlatformFolderItem[]> {
    const pending = this.outbox.pendingOps().map((o) => ({ recordId: o.recordId, payload: o.payload }));
    const overlaid: PlatformFolderItem[] = [];
    const seen = new Set<string>();
    for (const item of this.items) {
      let current: Folder | null = item as Folder;
      for (const op of pending.filter((pendingOp) => pendingOp.recordId === item.id)) {
        current = foldersCodec.applyOp(op.payload, current);
        if (current === null) break;
      }
      if (current !== null) {
        overlaid.push(current as PlatformFolderItem);
        seen.add(item.id);
      }
    }
    for (const op of pending) {
      if (seen.has(op.recordId)) continue;
      const created = foldersCodec.applyOp(op.payload, null);
      if (created !== null) overlaid.push(created as PlatformFolderItem);
    }
    return overlaid.sort((a, b) => a.order - b.order || a.createdAt - b.createdAt);
  }

  coverage(): PlatformFolderCoverageState {
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

  async create(name: string, opts?: { description?: string; color?: string; icon?: string }): Promise<void> {
    await this.outbox.enqueue(folderToPendingOp(buildCreateFolder(this.env, name, opts)));
    this.notify();
  }

  async patch(id: RecordId, patch: FolderPatch): Promise<void> {
    await this.outbox.enqueue(folderToPendingOp(buildPatchFolder(this.env, id, patch)));
    this.notify();
  }

  async delete(id: RecordId, moveToFolderId?: RecordId): Promise<void> {
    await this.outbox.enqueue(folderToPendingOp(buildDeleteFolder(this.env, id, moveToFolderId)));
    this.notify();
  }

  onAuthRestored(): void {
    this.outbox.onAuthRestored();
  }

  async refresh(): Promise<void> {
    const token = this.refreshTracker.begin();
    this.notify();
    const outcome = await fetchPlatformFolderPage(this.http, this.pageRequest(null));
    if (!this.refreshTracker.isCurrent(token)) return;

    if (outcome.kind !== "page") {
      this.coverageState = { kind: "unknown" };
      this.refreshTracker.complete(token, false, this.items.length > 0);
      this.notify();
      return;
    }

    const items = platformFolderItemsFromPage(outcome.page);
    await this.refreshTracker.applyIfCurrent(token, async () => {
      this.items = items;
      this.coverageState = platformFolderCoverageFromPage(outcome.page);
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
    const outcome = await fetchPlatformFolderPage(this.http, this.pageRequest(this.nextCursor));
    if (!this.refreshTracker.isCurrent(token)) return;
    if (outcome.kind !== "page") {
      this.coverageState = { kind: "unknown" };
      this.refreshTracker.complete(token, false, this.items.length > 0);
      this.notify();
      return;
    }
    const incoming = platformFolderItemsFromPage(outcome.page);
    await this.refreshTracker.applyIfCurrent(token, async () => {
      this.items = [...this.items, ...incoming];
      this.coverageState = platformFolderCoverageFromPage(outcome.page);
      this.nextCursor = outcome.page.window.hasMore ? outcome.page.window.nextCursor : null;
      await this.kv.set(ITEMS_KEY, JSON.stringify(this.items));
    });
    if (this.refreshTracker.isCurrent(token)) {
      this.refreshTracker.complete(token, true, this.items.length > 0);
    }
    this.notify();
  }

  private pageRequest(cursor: string | null): PlatformFoldersPageRequest {
    return {
      ...(this.options.limit !== undefined ? { limit: this.options.limit } : {}),
      ...(this.options.path !== undefined ? { path: this.options.path } : {}),
      cursor,
    };
  }

  private toWireId(localId: string): string {
    for (const [serverId, local] of Object.entries(this.aliases)) {
      if (local === localId) return serverId;
    }
    return localId;
  }

  private async recordAlias(localId: string, serverId: string): Promise<void> {
    this.aliases[serverId] = localId;
    await this.aliasKv.set(ALIAS_KEY, JSON.stringify(this.aliases));
  }

  private notify(): void {
    for (const fn of this.listeners) fn();
  }
}

function readCachedItems(raw: string | null): readonly PlatformFolderItem[] {
  if (raw === null) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed as PlatformFolderItem[] : [];
  } catch {
    return [];
  }
}
