/**
 * PlatformTasksStore — the platform generation's task store.
 *
 * Reads carry the server's completeness envelope (never restored from cache,
 * never derived from item counts). Writes go through `POST /v1/tasks/ops` via
 * Outbox, using the established write envelope (`write_id`, `account_epoch`)
 * and the stamps minted at enqueue. `openTasks()` is NOT repointed here —
 * the Tasks route branches to this store by name, as Conversations and
 * Folders already do.
 *
 * THE HONESTY RULE, carried over from the memories read store: cached items
 * survive a reopen, THE COVERAGE STATE DOES NOT. On open, before any refresh,
 * `coverage()` is `{ kind: "unknown" }` even when the cache is full.
 *
 * WRITE IDENTITY. The read wire serves reader-scoped opaque handles
 * (`task1_` + HMAC). The write envelope's `record_id` is the storage id the
 * client minted on create. HMAC is one-way, so the alias that maps a read
 * handle back to a write id is client-private and is joined on the store-owned
 * `revision` returned in `WriteAccepted`. Tasks this client did not create
 * have no write id; a patch against a bare opaque handle is refused rather
 * than upserting a second record.
 */

import type {
  DeadLetter,
  DurableKv,
  HttpClient,
  PlatformTaskCoverageState,
  PlatformTaskItem,
  StorageBridge,
  Task,
  TaskPatch,
} from "@omi-core/contracts";
import type { Env } from "@omi-core/kernel";
import { Outbox } from "@omi-core/sync";
import {
  WRITE_ID_ENTROPY_BYTES,
  createDevAccountEpochProvider,
  createPlatformWriteStamps,
  fetchPlatformTaskPage,
  platformTaskCoverageFromPage,
  platformTaskItemsFromPage,
  platformTasksTransport,
  type MutableAccountEpochProvider,
  type PlatformTasksPageRequest,
} from "@omi-core/adapters-platform";
import { buildCreateTask, buildDeleteTask, buildPatchTask, tasksCodec, taskToPendingOp } from "./tasks-codec.js";
import { RefreshTracker, type StoreStatus } from "./store-status.js";

const ITEMS_KEY = "items";
const ALIAS_KEY = "id-aliases";
const REVISION_KEY = "write-revisions";
const KNOWN_IDS_KEY = "known-record-ids";
/** Grammar of a platform read handle. Not a write `record_id`. */
const OPAQUE_TASK_REF = /^task1_[0-9a-f]{64}$/;

export interface PlatformTasksStoreOptions {
  /** Route override; the transport binding still owns the base URL. */
  readonly path?: string;
  readonly limit?: number;
}

function entropyFromEnv(env: Env): Uint8Array {
  const bytes = new Uint8Array(WRITE_ID_ENTROPY_BYTES);
  for (let index = 0; index < bytes.length; index++) {
    bytes[index] = Math.floor(env.random() * 256) & 0xff;
  }
  return bytes;
}

export class PlatformTasksStore {
  private listeners = new Set<() => void>();
  private items: readonly PlatformTaskItem[] = [];
  private coverageState: PlatformTaskCoverageState = { kind: "unknown" };
  private nextCursor: string | null = null;
  private aliases: Record<string, string> = {};
  private revisionToRecordId: Record<string, string> = {};
  private knownRecordIds = new Set<string>();
  private readonly refreshTracker: RefreshTracker;

  private constructor(
    private readonly env: Env,
    private readonly http: HttpClient,
    private readonly kv: DurableKv,
    private readonly identityKv: DurableKv,
    private readonly outbox: Outbox,
    private readonly epochs: MutableAccountEpochProvider,
    private readonly options: PlatformTasksStoreOptions,
    hasSavedData: boolean,
  ) {
    this.refreshTracker = new RefreshTracker(hasSavedData);
  }

  static async open(
    bridge: StorageBridge,
    env: Env,
    http: HttpClient,
    options: PlatformTasksStoreOptions = {},
  ): Promise<PlatformTasksStore> {
    const kv = await bridge.openKv("platform-tasks");
    const identityKv = await bridge.openKv("platform-tasks-identity");
    const cached = readCachedItems(await kv.get(ITEMS_KEY));
    const epochs = createDevAccountEpochProvider(null);
    let store: PlatformTasksStore | undefined;
    const transport = platformTasksTransport({
      http,
      onControlUnavailable: () => {
        void store?.refresh();
      },
    });
    const outbox = await Outbox.open(
      bridge,
      env,
      transport,
      "platform-tasks",
      createPlatformWriteStamps({
        entropy: () => entropyFromEnv(env),
        epochs,
      }),
    );
    store = new PlatformTasksStore(
      env,
      http,
      kv,
      identityKv,
      outbox,
      epochs,
      options,
      cached.length > 0,
    );
    store.items = cached;
    store.aliases = readStringMap(await identityKv.get(ALIAS_KEY));
    store.revisionToRecordId = readStringMap(await identityKv.get(REVISION_KEY));
    store.knownRecordIds = new Set(readStringList(await identityKv.get(KNOWN_IDS_KEY)));
    outbox.onChange = () => store!.notify();
    outbox.onOutcome = async (op, outcome) => {
      if (outcome.state !== "confirmed") return;
      if (outcome.serverRevision !== undefined) {
        store!.revisionToRecordId[outcome.serverRevision] = op.recordId;
      }
      store!.knownRecordIds.add(op.recordId);
      const current = store!.items.find((row) => row.id === op.recordId) ?? null;
      const next = tasksCodec.applyOp(op.payload, current as Task | null);
      if (next === null) {
        store!.items = store!.items.filter((row) => row.id !== op.recordId);
      } else if (current === null) {
        store!.items = [...store!.items, next as PlatformTaskItem];
      } else {
        store!.items = store!.items.map((row) => (row.id === next.id ? (next as PlatformTaskItem) : row));
      }
      await store!.persistItems();
      await store!.persistIdentity();
      store!.notify();
    };
    return store;
  }

  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  async list(): Promise<readonly PlatformTaskItem[]> {
    const pending = this.outbox.pendingOps().map((o) => ({ recordId: o.recordId, payload: o.payload }));
    const overlaid: PlatformTaskItem[] = [];
    const seen = new Set<string>();
    for (const item of this.items) {
      let current: Task | null = item as Task;
      for (const op of pending.filter((pendingOp) => pendingOp.recordId === item.id)) {
        current = tasksCodec.applyOp(op.payload, current);
        if (current === null) break;
      }
      if (current !== null) {
        overlaid.push(current as PlatformTaskItem);
        seen.add(item.id);
      }
    }
    for (const op of pending) {
      if (seen.has(op.recordId)) continue;
      const created = tasksCodec.applyOp(op.payload, null);
      if (created !== null) overlaid.push(created as PlatformTaskItem);
    }
    return overlaid.sort((a, b) => Number(a.completed) - Number(b.completed) || b.createdAt - a.createdAt);
  }

  coverage(): PlatformTaskCoverageState {
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

  async create(description: string, dueAt?: number): Promise<void> {
    const op = buildCreateTask(this.env, description, dueAt);
    this.knownRecordIds.add(op.id);
    await this.persistIdentity();
    await this.outbox.enqueue(taskToPendingOp(op));
    this.notify();
  }

  async patch(id: string, patch: TaskPatch): Promise<void> {
    const recordId = this.toWireId(id);
    this.assertWritableId(recordId);
    await this.outbox.enqueue(taskToPendingOp(buildPatchTask(this.env, recordId as Task["id"], patch)));
    this.notify();
  }

  async delete(id: string): Promise<void> {
    const recordId = this.toWireId(id);
    this.assertWritableId(recordId);
    await this.outbox.enqueue(taskToPendingOp(buildDeleteTask(this.env, recordId as Task["id"])));
    this.notify();
  }

  onAuthRestored(): void {
    this.outbox.onAuthRestored();
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

    this.observeEpoch(outcome.page.accountEpoch);
    const items = platformTaskItemsFromPage(outcome.page).map((item) => this.rekey(item));
    await this.refreshTracker.applyIfCurrent(token, async () => {
      this.items = items;
      this.coverageState = platformTaskCoverageFromPage(outcome.page);
      this.nextCursor = outcome.page.window.hasMore ? outcome.page.window.nextCursor : null;
      await this.persistItems();
      await this.persistIdentity();
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
    this.observeEpoch(outcome.page.accountEpoch);
    const appended = dedupeById([
      ...this.items,
      ...platformTaskItemsFromPage(outcome.page).map((item) => this.rekey(item)),
    ]);
    this.items = appended;
    this.coverageState = platformTaskCoverageFromPage(outcome.page);
    this.nextCursor = outcome.page.window.hasMore ? outcome.page.window.nextCursor : null;
    await this.persistItems();
    await this.persistIdentity();
    this.notify();
  }

  private observeEpoch(epoch: unknown): void {
    this.epochs.observeAccountEpoch(epoch);
  }

  private rekey(item: PlatformTaskItem): PlatformTaskItem {
    const byRevision = item.revision !== null ? this.revisionToRecordId[item.revision] : undefined;
    const byOpaque = this.aliases[item.id];
    const local = byRevision ?? byOpaque;
    if (local === undefined || local === item.id) return item;
    this.aliases[item.id] = local;
    this.knownRecordIds.add(local);
    return { ...item, id: local };
  }

  private toWireId(id: string): string {
    return this.aliases[id] ?? id;
  }

  private assertWritableId(id: string): void {
    if (OPAQUE_TASK_REF.test(id) && !this.knownRecordIds.has(id)) {
      throw new Error("platform task write refused: opaque read handle has no write id");
    }
  }

  private pageRequest(cursor: string | null): PlatformTasksPageRequest {
    return {
      ...(this.options.path !== undefined ? { path: this.options.path } : {}),
      ...(this.options.limit !== undefined ? { limit: this.options.limit } : {}),
      cursor,
    };
  }

  private async persistItems(): Promise<void> {
    await this.kv.set(ITEMS_KEY, JSON.stringify(this.items));
  }

  private async persistIdentity(): Promise<void> {
    await this.identityKv.set(ALIAS_KEY, JSON.stringify(this.aliases));
    await this.identityKv.set(REVISION_KEY, JSON.stringify(this.revisionToRecordId));
    await this.identityKv.set(KNOWN_IDS_KEY, JSON.stringify([...this.knownRecordIds]));
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

function readStringMap(raw: string | null): Record<string, string> {
  if (raw === null) return {};
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return {};
    const out: Record<string, string> = {};
    for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof value === "string") out[key] = value;
    }
    return out;
  } catch {
    return {};
  }
}

function readStringList(raw: string | null): readonly string[] {
  if (raw === null) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((entry): entry is string => typeof entry === "string");
  } catch {
    return [];
  }
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
