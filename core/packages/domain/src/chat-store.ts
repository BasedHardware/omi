/**
 * ChatMessagesStore: the one object a Chat surface talks to. Wires Outbox +
 * Projection + the platform chat adapter, and exposes
 * subscribe/list/status/refresh plus send/rate/delete.
 *
 * Authority (ADR-005 §1): the BACKEND is the chat record on every surface.
 * The local journal is an ADR-004 durable-mirror instance — offline reads and
 * queued sends, NEVER truth. `refresh()` reconciles from the server rather
 * than trusting local state; optimistic overlays are pending ops only.
 *
 * Alias protocol is retained for transport signature parity with the
 * tasks/memories exemplar. Under ADR-005 the server honors
 * `client_message_id` as the document id, so the alias map stays empty when
 * the platform path is correct; the machinery is inert until a mismatch
 * appears.
 */

import type { ChatMessage, DeadLetter, RecordId } from "@omi-core/contracts";
import type { DurableKv, HttpClient, StorageBridge } from "@omi-core/contracts";
import type { Env } from "@omi-core/kernel";
import { Outbox, Projection } from "@omi-core/sync";
import {
  chatMessagesTransport,
  fetchChatMessageIdSnapshot,
  fetchChatMessages,
} from "@omi-core/adapters-platform";
import {
  buildCreateChatMessage,
  buildDeleteChatMessage,
  buildPatchChatMessage,
  chatMessagePayloadHash,
  chatMessageToPendingOp,
  chatMessagesCodec,
} from "./chat-codec.js";
import { RefreshTracker, type StoreStatus } from "./store-status.js";

const ALIAS_KEY = "id-aliases"; // { [serverId]: localSlug }


export class ChatMessagesStore {
  private listeners = new Set<() => void>();
  private aliases: Record<string, string> = {};
  private readonly refreshTracker: RefreshTracker;

  private constructor(
    private readonly env: Env,
    private readonly http: HttpClient,
    private readonly outbox: Outbox,
    private readonly projection: Projection<ChatMessage>,
    private readonly aliasKv: DurableKv,
    hasSavedData: boolean,
  ) {
    this.refreshTracker = new RefreshTracker(hasSavedData);
  }

  static async open(bridge: StorageBridge, env: Env, http: HttpClient): Promise<ChatMessagesStore> {
    const aliasKv = await bridge.openKv("chat-aliases");
    const projection = await Projection.open(
      await bridge.openKv("chat-projection"),
      chatMessagesCodec,
    );

    let store: ChatMessagesStore;
    const transport = chatMessagesTransport(
      http,
      (localId: string, serverId: string) => void store.recordAlias(localId, serverId),
      (localId) => store.toWireId(localId),
    );
    const outbox = await Outbox.open(bridge, env, transport, "chat");
    store = new ChatMessagesStore(
      env,
      http,
      outbox,
      projection,
      aliasKv,
      (await projection.read([])).length > 0,
    );
    store.aliases = JSON.parse((await aliasKv.get(ALIAS_KEY)) ?? "{}") as Record<string, string>;
    outbox.onChange = () => store.notify();
    outbox.onOutcome = async (op, outcome) => {
      if (outcome.state !== "confirmed") return;
      const current = (await projection.read([])).find((r) => r.id === op.recordId) ?? null;
      const next = chatMessagesCodec.applyOp(op.payload, current);
      if (next === null) await projection.removeServerRow(op.recordId);
      else await projection.upsertServerRows([next]);
      store.notify();
    };
    return store;
  }

  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  /** What the screen renders: durable server mirror + pending overlays. */
  async list(): Promise<ChatMessage[]> {
    const pending = this.outbox.pendingOps().map((o) => ({ recordId: o.recordId, payload: o.payload }));
    const rows = await this.projection.read(pending);
    return rows.sort((a, b) => a.createdAt - b.createdAt);
  }

  pendingCount(): number {
    return this.outbox.pendingOps().length;
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

  /** Queue a human send. Local journal mirrors; server is authority. */
  async send(text: string): Promise<void> {
    await this.outbox.enqueue(chatMessageToPendingOp(buildCreateChatMessage(this.env, text)));
    this.notify();
  }

  /**
   * Keyed rating patch. Absent other fields stay untouched (hard rule 7) —
   * only `rating` is writable via ChatMessagePatch.
   */
  async rate(id: RecordId, rating: number | null): Promise<void> {
    await this.outbox.enqueue(
      chatMessageToPendingOp(buildPatchChatMessage(this.env, id, { rating })),
    );
    this.notify();
  }

  async delete(id: RecordId): Promise<void> {
    await this.outbox.enqueue(chatMessageToPendingOp(buildDeleteChatMessage(this.env, id)));
    this.notify();
  }

  onAuthRestored(): void {
    this.outbox.onAuthRestored();
  }

  /**
   * Pull server truth into the local mirror. Safe to call on interval; failures
   * are silent-degrade (offline reads keep serving the projection). Never
   * treats the local journal as authoritative.
   */
  async refresh(): Promise<void> {
    const token = this.refreshTracker.begin();
    this.notify();
    let rows: ChatMessage[] | null = null;
    let failed = false;
    let thrown: unknown;
    try {
      rows = await fetchChatMessages(this.http);
      if (rows) {
        await this.refreshTracker.applyIfCurrent(token, () =>
          this.projection.upsertServerRows(rows!.map((r) => this.rekeyed(r))),
        );
      }
      if (this.refreshTracker.isCurrent(token)) {
        const snapshot = await fetchChatMessageIdSnapshot(this.http);
        if (snapshot && this.refreshTracker.isCurrent(token)) {
          const localIds = snapshot.ids.map((id) => this.aliases[id] ?? id);
          await this.refreshTracker.applyIfCurrent(token, () =>
            this.projection.reconcile({ ...snapshot, ids: localIds }).then(() => undefined),
          );
        }
      }
    } catch (error) {
      failed = true;
      thrown = error;
    }
    if (this.refreshTracker.isCurrent(token)) {
      let hasSavedData = false;
      try {
        // Pending overlays are not durable server truth.
        hasSavedData = (await this.projection.read([])).length > 0;
      } catch (error) {
        failed = true;
        if (thrown === undefined) thrown = error;
      }
      this.refreshTracker.complete(token, !failed && rows !== null, hasSavedData);
    }
    this.notify();
    if (thrown !== undefined) throw thrown;
  }

  private rekeyed(row: ChatMessage): ChatMessage {
    const local = this.aliases[row.id];
    return local ? { ...row, id: local as RecordId } : row;
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
