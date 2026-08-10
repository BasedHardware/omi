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

import type {
  BridgeStreamPort,
  ChatAdmissionEnvelope,
  ChatCapabilitiesWire,
  ChatMessage,
  ChatMessageOp,
  ChatTerminalFrame,
  DeadLetter,
  DurableKv,
  RecordId,
} from "@omi-core/contracts";
import type { HttpClient, StorageBridge } from "@omi-core/contracts";
import type { Env } from "@omi-core/kernel";
import { Outbox, Projection } from "@omi-core/sync";
import {
  chatMessagesTransport,
  fetchChatMessageIdSnapshot,
  fetchChatMessageReconcilePage,
  cancelChatGeneration,
  observeChatGeneration,
} from "@omi-core/adapters-platform";
import type { ChatGenerationObservation } from "@omi-core/adapters-platform";
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
const ACTIVE_GENERATIONS_KEY = "active-generations";

export interface StoredChatGenerationDelivery {
  readonly generationId: string;
  readonly clientMessageId: RecordId;
  readonly terminal: ChatTerminalFrame;
}

export interface ActiveChatGeneration {
  readonly generationId: string;
  readonly clientMessageId: RecordId;
  readonly text: string;
  readonly lastEventId: string | null;
  readonly observationState: "streaming" | "failed";
  readonly failure: "observation-failed" | null;
}

export interface ChatHistoryWindow {
  readonly hasOlder: boolean;
  readonly olderCursor: string | null;
}

export class ChatMessagesStore {
  private listeners = new Set<() => void>();
  private readonly refreshTracker: RefreshTracker;
  private readonly active = new Map<string, ActiveChatGeneration>();
  private readonly observations = new Map<string, ChatGenerationObservation>();
  private chatCapabilities: ChatCapabilitiesWire | null = null;
  private historyWindow: ChatHistoryWindow = { hasOlder: false, olderCursor: null };

  private constructor(
    private readonly env: Env,
    private readonly http: HttpClient,
    private readonly outbox: Outbox,
    private readonly projection: Projection<ChatMessage>,
    private readonly generationKv: DurableKv,
    private readonly streamPort: BridgeStreamPort | null,
    hasSavedData: boolean,
  ) {
    this.refreshTracker = new RefreshTracker(hasSavedData);
  }

  static async open(
    bridge: StorageBridge,
    env: Env,
    http: HttpClient,
    streamPort?: BridgeStreamPort,
  ): Promise<ChatMessagesStore> {
    const projection = await Projection.open(
      await bridge.openKv("chat-projection"),
      chatMessagesCodec,
    );
    const generationKv = await bridge.openKv("chat-generation-deliveries");

    let store: ChatMessagesStore;
    const transport = chatMessagesTransport(
      http,
      async (admission) => store.recordAdmission(admission),
    );
    const outbox = await Outbox.open(bridge, env, transport, "chat");
    store = new ChatMessagesStore(
      env,
      http,
      outbox,
      projection,
      generationKv,
      streamPort ?? null,
      (await projection.read([])).length > 0,
    );
    outbox.onChange = () => store.notify();
    outbox.onOutcome = async (op, outcome) => {
      if (outcome.state === "dead") {
        // Outbox writes the retained payload immediately after this callback.
        // Notify on the injected next turn so the dead-letter surface reads the
        // durable letter, not the state transition just before it.
        env.delay(0, () => store.notify());
        return;
      }
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
    await store.restoreActiveGenerations();
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

  pendingMessageIds(): readonly RecordId[] {
    return this.outbox.pendingOps().map((op) => op.recordId as RecordId);
  }

  capabilities(): ChatCapabilitiesWire | null {
    return this.chatCapabilities;
  }

  activeGenerations(): readonly ActiveChatGeneration[] {
    return [...this.active.values()];
  }

  historyPage(): ChatHistoryWindow {
    return this.historyWindow;
  }

  async loadOlder(olderCursor: string): Promise<readonly ChatMessage[]> {
    const page = await fetchChatMessageReconcilePage(this.http, { cursor: olderCursor });
    if (page === null) throw new Error("chat older-page read failed");
    this.chatCapabilities = page.capabilities;
    this.historyWindow = { hasOlder: page.hasMore, olderCursor: page.nextCursor };
    await this.projection.upsertServerRows([...page.messages]);
    this.notify();
    return page.messages;
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

  async discardDeadLetter(opId: string): Promise<void> {
    await this.outbox.discardDeadLetter(opId);
    this.notify();
  }

  /** Queue a human send. Local journal mirrors; server is authority. */
  async send(text: string, attachmentIds: readonly string[] = []): Promise<RecordId> {
    const op = buildCreateChatMessage(this.env, text, { attachmentIds });
    await this.outbox.enqueue(
      chatMessageToPendingOp(op),
    );
    this.notify();
    return op.id;
  }

  /** Cancel the old stream immediately, then target the ratified resource. */
  async cancelGeneration(generationId: string): Promise<void> {
    const current = this.active.get(generationId);
    this.observations.get(generationId)?.cancel("user-cancelled-generation");
    this.observations.delete(generationId);
    try {
      const result = await cancelChatGeneration(this.http, generationId);
      if (!result.ok) throw new Error(result.failure.detail);
    } finally {
      // Cancellation is server state. Reopen after the exact cursor to receive
      // the canonical cancelled/done terminal while the old stream stays dead.
      if (current !== undefined && this.active.has(generationId)) {
        this.startObservation(current);
      }
    }
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
      const page = await fetchChatMessageReconcilePage(this.http);
      rows = page === null ? null : [...page.messages];
      if (page !== null) {
        this.chatCapabilities = page.capabilities;
        this.historyWindow = { hasOlder: page.hasMore, olderCursor: page.nextCursor };
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

  private async recordAdmission(admission: ChatAdmissionEnvelope): Promise<void> {
    await this.projection.upsertServerRows([admission.message]);
    const generationId = admission.generation.id;
    const existing = this.active.get(generationId);
    const state: ActiveChatGeneration = existing ?? {
      generationId,
      clientMessageId: admission.message.id,
      text: "",
      lastEventId: null,
      observationState: "streaming",
      failure: null,
    };
    this.active.set(generationId, state);
    await this.persistActiveGenerations();
    this.notify();
    this.startObservation(state);
  }

  private async recordGenerationTerminal(
    generationId: string,
    clientMessageId: RecordId,
    terminal: ChatTerminalFrame,
  ): Promise<void> {
    const existing = await this.generationDeliveries();
    const next: StoredChatGenerationDelivery = {
      generationId,
      clientMessageId,
      terminal,
    };
    await this.generationKv.set(
      GENERATION_DELIVERIES_KEY,
      JSON.stringify([...existing.filter((item) => item.generationId !== generationId), next]),
    );
    if (terminal.kind !== "failed") {
      await this.projection.upsertServerRows([terminal.message]);
    }
    this.active.delete(generationId);
    this.observations.delete(generationId);
    await this.persistActiveGenerations();
    this.notify();
  }

  private startObservation(state: ActiveChatGeneration): void {
    if (this.streamPort === null) return;
    this.observations.get(state.generationId)?.cancel("generation-observation-replaced");
    const observation = observeChatGeneration(
      this.streamPort,
      state.generationId,
      this.env,
      state.lastEventId ?? undefined,
    );
    this.observations.set(state.generationId, observation);
    void this.consumeObservation(state.generationId, observation);
  }

  private async consumeObservation(
    generationId: string,
    observation: ChatGenerationObservation,
  ): Promise<void> {
    try {
      for await (const event of observation.events) {
        if (this.observations.get(generationId) !== observation) return;
        const current = this.active.get(generationId);
        if (current === undefined) return;
        if (event.kind === "snapshot" || event.kind === "delta") {
          const next: ActiveChatGeneration = {
            ...current,
            text: event.kind === "snapshot" ? event.text : `${current.text}${event.text}`,
            lastEventId: event.id,
            observationState: "streaming",
            failure: null,
          };
          this.active.set(generationId, next);
          await this.persistActiveGenerations();
          this.notify();
        } else if (event.kind === "terminal") {
          await this.recordGenerationTerminal(
            generationId,
            current.clientMessageId,
            event.terminal,
          );
          return;
        } else {
          this.observations.delete(generationId);
          this.active.set(generationId, {
            ...current,
            observationState: "failed",
            failure: "observation-failed",
          });
          await this.persistActiveGenerations();
          this.notify();
          return;
        }
      }
    } catch {
      if (this.observations.get(generationId) === observation) {
        this.observations.delete(generationId);
        const current = this.active.get(generationId);
        if (current !== undefined) {
          this.active.set(generationId, {
            ...current,
            observationState: "failed",
            failure: "observation-failed",
          });
          await this.persistActiveGenerations();
        }
        this.notify();
      }
    }
  }

  private async restoreActiveGenerations(): Promise<void> {
    const raw = await this.generationKv.get(ACTIVE_GENERATIONS_KEY);
    if (raw === null) return;
    try {
      const parsed = JSON.parse(raw) as unknown;
      if (!Array.isArray(parsed)) return;
      for (const value of parsed) {
        if (
          typeof value !== "object" || value === null ||
          typeof (value as ActiveChatGeneration).generationId !== "string" ||
          typeof (value as ActiveChatGeneration).clientMessageId !== "string" ||
          typeof (value as ActiveChatGeneration).text !== "string" ||
          !(
            (value as ActiveChatGeneration).lastEventId === null ||
            typeof (value as ActiveChatGeneration).lastEventId === "string"
          ) ||
          !(
            (value as ActiveChatGeneration).observationState === "streaming" ||
            (value as ActiveChatGeneration).observationState === "failed"
          ) ||
          !(
            (value as ActiveChatGeneration).failure === null ||
            (value as ActiveChatGeneration).failure === "observation-failed"
          )
        ) continue;
        const state = value as ActiveChatGeneration;
        this.active.set(state.generationId, state);
        if (state.observationState === "streaming") this.startObservation(state);
      }
    } catch {
      // Malformed advisory state never corrupts the canonical projection.
    }
  }

  private persistActiveGenerations(): Promise<void> {
    return this.generationKv.set(ACTIVE_GENERATIONS_KEY, JSON.stringify([...this.active.values()]));
  }
}
