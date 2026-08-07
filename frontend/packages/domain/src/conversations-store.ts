/**
 * ConversationsStore: the one object a surface talks to. Wires Outbox +
 * Projection + the legacy conversations adapter, and exposes
 * subscribe/read/patch/delete/refresh for any view layer.
 *
 * No create: conversations are server-originated (contract header / ADR-004
 * amendment 2026-08-07). New rows arrive only via refresh/snapshot reconcile.
 *
 * Alias protocol is retained for transport signature parity with
 * tasks/memories (`onServerAssignedId`); with create omitted the map stays
 * empty and rekey/resolve are identity. When a rewrite adds client create,
 * this machinery becomes live without a store reshape.
 */

import type { Conversation, ConversationPatch, DeadLetter, RecordId } from "@omi-core/contracts";
import type { DurableKv, StorageBridge } from "@omi-core/contracts";
import type { Env } from "@omi-core/kernel";
import { Outbox, Projection } from "@omi-core/sync";
import {
  conversationsTransport,
  fetchConversationIdSnapshot,
  fetchConversations,
} from "@omi-core/adapters-legacy";
import type { HttpClient } from "@omi-core/contracts";
import {
  buildDeleteConversation,
  buildPatchConversation,
  conversationToPendingOp,
  conversationsCodec,
} from "./conversations-codec.js";

const ALIAS_KEY = "id-aliases"; // { [serverId]: localSlug }

export class ConversationsStore {
  private listeners = new Set<() => void>();
  private aliases: Record<string, string> = {};

  private constructor(
    private readonly env: Env,
    private readonly http: HttpClient,
    private readonly outbox: Outbox,
    private readonly projection: Projection<Conversation>,
    private readonly aliasKv: DurableKv,
  ) {}

  static async open(bridge: StorageBridge, env: Env, http: HttpClient): Promise<ConversationsStore> {
    const aliasKv = await bridge.openKv("conversations-aliases");
    const projection = await Projection.open(
      await bridge.openKv("conversations-projection"),
      conversationsCodec,
    );

    let store: ConversationsStore;
    const transport = conversationsTransport(http, (localId, serverId) => void store.recordAlias(localId, serverId));
    const outbox = await Outbox.open(bridge, env, transport, "conversations");
    store = new ConversationsStore(env, http, outbox, projection, aliasKv);
    store.aliases = JSON.parse((await aliasKv.get(ALIAS_KEY)) ?? "{}") as Record<string, string>;
    outbox.onChange = () => store.notify();
    outbox.onOutcome = async (op, outcome) => {
      if (outcome.state !== "confirmed") return;
      const current = (await projection.read([])).find((r) => r.id === op.recordId) ?? null;
      const next = conversationsCodec.applyOp(op.payload, current);
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

  /** What the screen renders: durable server truth + pending overlays. */
  async list(): Promise<Conversation[]> {
    const pending = this.outbox.pendingOps().map((o) => ({ recordId: o.recordId, payload: o.payload }));
    const rows = await this.projection.read(pending);
    return rows.sort((a, b) => b.updatedAt - a.updatedAt || b.createdAt - a.createdAt);
  }

  pendingCount(): number {
    return this.outbox.pendingOps().length;
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

  /** Pull server truth: rows + id reconcile. Safe to call on interval; all
   * failures are silent-degrade (offline reads keep serving the projection).
   * Snapshot is never complete on the legacy wire (status-filtered list) —
   * reconcile only adds knowledge, never deletes filtered-out local rows. */
  async refresh(): Promise<void> {
    const rows = await fetchConversations(this.http);
    if (rows) {
      await this.projection.upsertServerRows(rows.map((r) => this.rekeyed(r)));
    }
    const snapshot = await fetchConversationIdSnapshot(this.http);
    if (snapshot) {
      const localIds = snapshot.ids.map((id) => this.aliases[id] ?? id);
      await this.projection.reconcile({ ...snapshot, ids: localIds });
    }
    this.notify();
  }

  private rekeyed(row: Conversation): Conversation {
    const local = this.aliases[row.id];
    return local ? { ...row, id: local as RecordId } : row;
  }

  private async recordAlias(localId: string, serverId: string): Promise<void> {
    this.aliases[serverId] = localId;
    await this.aliasKv.set(ALIAS_KEY, JSON.stringify(this.aliases));
  }

  private notify(): void {
    for (const fn of this.listeners) fn();
  }
}
