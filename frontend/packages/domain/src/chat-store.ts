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
 * The ratified wire echoes the client message id as the durable record id, so
 * there is no alias protocol or server-assigned-id compatibility path.
 */

import type { ChatMessage, ChatMessageOp, ChatTerminalFrame, DeadLetter, DurableKv, RecordId } from "@omi-core/contracts";
import type { HttpClient, StorageBridge } from "@omi-core/contracts";
import type { Env } from "@omi-core/kernel";
import { Outbox, Projection } from "@omi-core/sync";
import {
  chatMessagesTransport,
  fetchChatMessageIdSnapshot,
  fetchChatMessages,
} from "@omi-core/adapters-platform";
import type {
  ChatGenerationReconnectTransport,
  ChatGenerationTerminalDelivery,
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

const GENERATION_DELIVERIES_KEY = "generation-deliveries";

export interface StoredChatGenerationDelivery {
  readonly generationId: string;
  readonly clientMessageId: RecordId;
  readonly terminal: ChatTerminalFrame;
}

export class ChatMessagesStore {
  private listeners = new Set<() => void>();
  private readonly refreshTracker: RefreshTracker;

  private constructor(
    private readonly env: Env,
    private readonly http: HttpClient,
    private readonly outbox: Outbox,
    private readonly projection: Projection<ChatMessage>,
    private readonly generationKv: DurableKv,
    hasSavedData: boolean,
  ) {
    this.refreshTracker = new RefreshTracker(hasSavedData);
  }

  static async open(
    bridge: StorageBridge,
    env: Env,
    http: HttpClient,
    reconnect?: ChatGenerationReconnectTransport,
  ): Promise<ChatMessagesStore> {
    const projection = await Projection.open(
      await bridge.openKv("chat-projection"),
      chatMessagesCodec,
    );
    const generationKv = await bridge.openKv("chat-generation-deliveries");

    let store: ChatMessagesStore;
    const transport = chatMessagesTransport(
      http,
      async (delivery) => store.recordGenerationTerminal(delivery),
      reconnect,
    );
    const outbox = await Outbox.open(bridge, env, transport, "chat");
    store = new ChatMessagesStore(
      env,
      http,
      outbox,
      projection,
      generationKv,
      (await projection.read([])).length > 0,
    );
    outbox.onChange = () => store.notify();
    outbox.onOutcome = async (op, outcome) => {
      if (outcome.state !== "confirmed") return;
      const domainOp = JSON.parse(op.payload) as ChatMessageOp;
      // The required terminal-delivery callback persisted the canonical
      // admitted human row before the transport reported admission success.
      if (domainOp.op === "create") return;
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

  /** Durable assistant outcomes, separate from confirmed human admissions. */
  async generationDeliveries(): Promise<readonly StoredChatGenerationDelivery[]> {
    const raw = await this.generationKv.get(GENERATION_DELIVERIES_KEY);
    if (raw === null) return [];
    try {
      const parsed = JSON.parse(raw) as unknown;
      return Array.isArray(parsed) ? parsed as StoredChatGenerationDelivery[] : [];
    } catch {
      return [];
    }
  }

  discardDeadLetter(opId: string): Promise<void> {
    return this.outbox.discardDeadLetter(opId);
  }

  /** Queue a human send. Local journal mirrors; server is authority. */
  async send(text: string, attachmentIds: readonly string[] = []): Promise<void> {
    await this.outbox.enqueue(
      chatMessageToPendingOp(buildCreateChatMessage(this.env, text, { attachmentIds })),
    );
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
          this.projection.upsertServerRows(rows!),
        );
      }
      if (this.refreshTracker.isCurrent(token)) {
        const snapshot = await fetchChatMessageIdSnapshot(this.http);
        if (snapshot && this.refreshTracker.isCurrent(token)) {
          await this.refreshTracker.applyIfCurrent(token, () =>
            this.projection.reconcile(snapshot).then(() => undefined),
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

  private notify(): void {
    for (const fn of this.listeners) fn();
  }

  private async recordGenerationTerminal(
    delivery: ChatGenerationTerminalDelivery,
  ): Promise<void> {
    const generationId = delivery.admission.generation.id;
    const existing = await this.generationDeliveries();
    const next: StoredChatGenerationDelivery = {
      generationId,
      clientMessageId: delivery.admission.message.id,
      terminal: delivery.terminal,
    };
    await this.generationKv.set(
      GENERATION_DELIVERIES_KEY,
      JSON.stringify([...existing.filter((item) => item.generationId !== generationId), next]),
    );
    const canonicalRows = delivery.terminal.kind === "failed"
      ? [delivery.admission.message]
      : [delivery.admission.message, delivery.terminal.message];
    await this.projection.upsertServerRows(canonicalRows);
    this.notify();
  }
}
