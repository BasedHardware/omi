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
  DurableLog,
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
  observeAgentRun,
  observeChatGeneration,
  parseStoredAgentRunUiEvent,
  wireToChatMessage,
} from "@omi-core/adapters-platform";
import type {
  AgentRunObservation,
  AgentRunUiEvent,
  ChatGenerationObservation,
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
  readonly failure: "observation-failed" | "stream-unavailable" | null;
}

export interface ChatHistoryWindow {
  readonly hasOlder: boolean;
  readonly olderCursor: string | null;
}

export interface StoredChatAgentRunTimeline {
  readonly generationId: string;
  readonly clientMessageId: RecordId;
  readonly events: readonly AgentRunUiEvent[];
  readonly lastEventId: string | null;
  readonly observationState: "observing" | "complete" | "failed";
}

interface StoredAgentRunLogEntry {
  readonly generationId: string;
  readonly clientMessageId: RecordId;
  readonly eventId: string;
  readonly event: AgentRunUiEvent;
}

const STORED_TOKEN = /^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$/u;

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]): boolean {
  return Object.keys(value).sort().join(",") === [...keys].sort().join(",");
}

function parseStoredGenerationDelivery(value: unknown): StoredChatGenerationDelivery | null {
  if (!isPlainRecord(value) || !hasExactKeys(value, ["generationId", "clientMessageId", "terminal"])) {
    return null;
  }
  if (
    typeof value["generationId"] !== "string" || !STORED_TOKEN.test(value["generationId"]) ||
    typeof value["clientMessageId"] !== "string" || !STORED_TOKEN.test(value["clientMessageId"])
  ) return null;
  const terminal = value["terminal"];
  if (!isPlainRecord(terminal) || typeof terminal["kind"] !== "string") return null;

  let parsedTerminal: ChatTerminalFrame;
  if (terminal["kind"] === "failed") {
    if (!hasExactKeys(terminal, ["kind", "error"]) || !isPlainRecord(terminal["error"])) return null;
    const error = terminal["error"];
    if (
      !hasExactKeys(error, ["code", "retryable"]) ||
      typeof error["code"] !== "string" || !STORED_TOKEN.test(error["code"]) ||
      typeof error["retryable"] !== "boolean"
    ) return null;
    parsedTerminal = { kind: "failed", error: { code: error["code"], retryable: error["retryable"] } };
  } else if (terminal["kind"] === "done" || terminal["kind"] === "cancelled") {
    if (!hasExactKeys(terminal, ["kind", "message"])) return null;
    if (terminal["kind"] === "cancelled" && terminal["message"] === null) {
      parsedTerminal = { kind: "cancelled", message: null };
    } else {
      const message = wireToChatMessage(terminal["message"]);
      if (message === null || message.sender !== "ai") return null;
      if (terminal["kind"] === "done" && message.generationOutcome === "completed") {
        parsedTerminal = { kind: "done", message };
      } else if (terminal["kind"] === "cancelled" && message.generationOutcome === "cancelled") {
        parsedTerminal = { kind: "cancelled", message };
      } else {
        return null;
      }
    }
  } else {
    return null;
  }
  return {
    generationId: value["generationId"],
    clientMessageId: value["clientMessageId"] as RecordId,
    terminal: parsedTerminal,
  };
}

export class ChatMessagesStore {
  private listeners = new Set<() => void>();
  private readonly refreshTracker: RefreshTracker;
  private readonly active = new Map<string, ActiveChatGeneration>();
  private readonly observations = new Map<string, ChatGenerationObservation>();
  private readonly agentRuns = new Map<string, StoredChatAgentRunTimeline>();
  private readonly agentRunEventIds = new Map<string, Set<string>>();
  private readonly agentObservations = new Map<string, AgentRunObservation>();
  private chatCapabilities: ChatCapabilitiesWire | null = null;
  private historyWindow: ChatHistoryWindow = { hasOlder: false, olderCursor: null };

  private constructor(
    private readonly env: Env,
    private readonly http: HttpClient,
    private readonly outbox: Outbox,
    private readonly projection: Projection<ChatMessage>,
    private readonly generationKv: DurableKv,
    private readonly generationDeliveryLog: DurableLog,
    private readonly agentRunLog: DurableLog,
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
    const generationDeliveryLog = await bridge.openLog("chat-generation-terminal-deliveries");
    const agentRunLog = await bridge.openLog("chat-agent-run-events");

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
      generationDeliveryLog,
      agentRunLog,
      streamPort ?? null,
      (await projection.read([])).length > 0,
    );
    outbox.onChange = () => store.notify();
    outbox.onOutcome = async (op, outcome) => {
      if (outcome.state === "dead") {
        store.notify();
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
    await store.restoreAgentRuns();
    await store.restoreActiveGenerations();
    await store.resumeTerminalAgentRuns();
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

  agentRunTimelines(): readonly StoredChatAgentRunTimeline[] {
    return [...this.agentRuns.values()].map((timeline) => ({
      ...timeline,
      events: [...timeline.events],
    }));
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
    const deliveries = new Map<string, StoredChatGenerationDelivery>();
    const raw = await this.generationKv.get(GENERATION_DELIVERIES_KEY);
    if (raw !== null) {
      try {
        const parsed = JSON.parse(raw) as unknown;
        if (Array.isArray(parsed)) {
          for (const value of parsed) {
            const delivery = parseStoredGenerationDelivery(value);
            if (delivery !== null) deliveries.set(delivery.generationId, delivery);
          }
        }
      } catch {
        // A malformed legacy whole-value snapshot is ignored. New writes use
        // the append-only log below, so one corrupt legacy value cannot poison
        // future terminal outcomes.
      }
    }
    for (const entry of await this.generationDeliveryLog.scan(0)) {
      try {
        const delivery = parseStoredGenerationDelivery(JSON.parse(entry.payload) as unknown);
        if (delivery !== null) deliveries.set(delivery.generationId, delivery);
      } catch {
        // One malformed append is isolated from every other generation.
      }
    }
    return [...deliveries.values()];
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
      observationState: this.streamPort === null ? "failed" : "streaming",
      failure: this.streamPort === null ? "stream-unavailable" : null,
    };
    this.active.set(generationId, state);
    await this.persistActiveGenerations();
    this.notify();
    this.startObservation(state);
    this.startAgentRunObservation(state.generationId, state.clientMessageId);
  }

  private async recordGenerationTerminal(
    generationId: string,
    clientMessageId: RecordId,
    terminal: ChatTerminalFrame,
  ): Promise<void> {
    const next: StoredChatGenerationDelivery = {
      generationId,
      clientMessageId,
      terminal,
    };
    // Per-generation terminal records are append-only. A whole-value KV
    // read/modify/write loses one generation when two streams finish together.
    await this.generationDeliveryLog.append(JSON.stringify(next));
    if (terminal.kind === "done") {
      await this.projection.upsertServerRows([terminal.message]);
    } else if (terminal.kind === "cancelled" && terminal.message !== null) {
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

  private startAgentRunObservation(generationId: string, clientMessageId: RecordId): void {
    if (this.streamPort === null || this.agentObservations.has(generationId)) return;
    const existing = this.agentRuns.get(generationId);
    if (existing?.observationState === "complete") return;
    const observation = observeAgentRun(
      this.streamPort,
      generationId,
      this.env,
      existing?.lastEventId ?? undefined,
    );
    this.agentObservations.set(generationId, observation);
    this.agentRuns.set(generationId, existing ?? {
      generationId,
      clientMessageId,
      events: [],
      lastEventId: null,
      observationState: "observing",
    });
    void this.consumeAgentRunObservation(generationId, clientMessageId, observation);
  }

  private async consumeAgentRunObservation(
    generationId: string,
    clientMessageId: RecordId,
    observation: AgentRunObservation,
  ): Promise<void> {
    try {
      for await (const incoming of observation.events) {
        if (this.agentObservations.get(generationId) !== observation) return;
        const current = this.agentRuns.get(generationId) ?? {
          generationId,
          clientMessageId,
          events: [],
          lastEventId: null,
          observationState: "observing" as const,
        };
        if (current.clientMessageId !== clientMessageId) {
          throw new Error("agent-run client binding changed");
        }
        if (incoming.kind === "error") {
          this.agentObservations.delete(generationId);
          this.agentRuns.set(generationId, { ...current, observationState: "failed" });
          this.notify();
          return;
        }
        const latestSequence = current.events.at(-1)?.sequence ?? 0;
        if (incoming.event.sequence !== latestSequence + 1
          || (latestSequence === 0 && incoming.event.kind !== "run_accepted")
          || (latestSequence > 0 && incoming.event.kind === "run_accepted")) {
          throw new Error("agent-run sequence is not contiguous");
        }
        const eventIds = this.agentRunEventIds.get(generationId) ?? new Set<string>();
        if (eventIds.has(incoming.id)) {
          throw new Error("agent-run event cursor was reused");
        }
        const entry: StoredAgentRunLogEntry = {
          generationId,
          clientMessageId,
          eventId: incoming.id,
          event: incoming.event,
        };
        await this.agentRunLog.append(JSON.stringify(entry));
        eventIds.add(incoming.id);
        this.agentRunEventIds.set(generationId, eventIds);
        const terminal = incoming.event.kind === "terminal";
        this.agentRuns.set(generationId, {
          generationId,
          clientMessageId,
          events: [...current.events, incoming.event],
          lastEventId: incoming.id,
          observationState: terminal ? "complete" : "observing",
        });
        if (terminal) this.agentObservations.delete(generationId);
        this.notify();
        if (terminal) return;
      }
    } catch {
      if (this.agentObservations.get(generationId) !== observation) return;
      this.agentObservations.delete(generationId);
      const current = this.agentRuns.get(generationId);
      if (current !== undefined) this.agentRuns.set(generationId, { ...current, observationState: "failed" });
      this.notify();
    }
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
      let normalizedUnsupportedStream = false;
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
            (value as ActiveChatGeneration).failure === "observation-failed" ||
            (value as ActiveChatGeneration).failure === "stream-unavailable"
          )
        ) continue;
        const restored = value as ActiveChatGeneration;
        const state: ActiveChatGeneration =
          restored.observationState === "streaming" && this.streamPort === null
            ? {
                ...restored,
                observationState: "failed",
                failure: "stream-unavailable",
              }
            : restored;
        if (state !== restored) normalizedUnsupportedStream = true;
        this.active.set(state.generationId, state);
        if (state.observationState === "streaming") {
          this.startObservation(state);
          this.startAgentRunObservation(state.generationId, state.clientMessageId);
        }
      }
      if (normalizedUnsupportedStream) await this.persistActiveGenerations();
    } catch {
      // Malformed advisory state never corrupts the canonical projection.
    }
  }

  private persistActiveGenerations(): Promise<void> {
    return this.generationKv.set(ACTIVE_GENERATIONS_KEY, JSON.stringify([...this.active.values()]));
  }

  private async restoreAgentRuns(): Promise<void> {
    const entries = await this.agentRunLog.scan(0);
    const invalidGenerations = new Set<string>();
    const storedToken = /^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}$/u;
    const invalidate = (generationId: string): void => {
      invalidGenerations.add(generationId);
      this.agentRuns.delete(generationId);
      this.agentRunEventIds.delete(generationId);
    };
    for (const logEntry of entries) {
      try {
        const raw = JSON.parse(logEntry.payload) as unknown;
        if (raw === null || typeof raw !== "object" || Array.isArray(raw)) continue;
        const keys = Object.keys(raw).sort();
        const candidate = raw as Partial<StoredAgentRunLogEntry>;
        if (typeof candidate.generationId !== "string" || !storedToken.test(candidate.generationId)) continue;
        if (invalidGenerations.has(candidate.generationId)) continue;
        if (keys.join(",") !== "clientMessageId,event,eventId,generationId") {
          invalidate(candidate.generationId);
          continue;
        }
        if (typeof candidate.clientMessageId !== "string" || !storedToken.test(candidate.clientMessageId)
          || typeof candidate.eventId !== "string" || !storedToken.test(candidate.eventId)) {
          invalidate(candidate.generationId);
          continue;
        }
        const event = parseStoredAgentRunUiEvent(candidate.event);
        if (event === null) {
          invalidate(candidate.generationId);
          continue;
        }
        const current = this.agentRuns.get(candidate.generationId);
        const latestSequence = current?.events.at(-1)?.sequence ?? 0;
        const eventIds = this.agentRunEventIds.get(candidate.generationId) ?? new Set<string>();
        const invalid = (current !== undefined && current.clientMessageId !== candidate.clientMessageId)
          || eventIds.has(candidate.eventId)
          || event.sequence !== latestSequence + 1
          || (latestSequence === 0 && event.kind !== "run_accepted")
          || (latestSequence > 0 && event.kind === "run_accepted")
          || current?.observationState === "complete";
        if (invalid) {
          invalidate(candidate.generationId);
          continue;
        }
        eventIds.add(candidate.eventId);
        this.agentRunEventIds.set(candidate.generationId, eventIds);
        this.agentRuns.set(candidate.generationId, {
          generationId: candidate.generationId,
          clientMessageId: candidate.clientMessageId as RecordId,
          events: [...(current?.events ?? []), event],
          lastEventId: candidate.eventId,
          observationState: event.kind === "terminal" ? "complete" : "observing",
        });
      } catch {
        // A malformed advisory run record is skipped without touching Chat truth.
      }
    }
  }

  private async resumeTerminalAgentRuns(): Promise<void> {
    if (this.streamPort === null) return;
    const deliveries = (await this.generationDeliveries()).slice(-8);
    for (const delivery of deliveries) {
      const timeline = this.agentRuns.get(delivery.generationId);
      if (timeline?.observationState !== "complete") {
        this.startAgentRunObservation(delivery.generationId, delivery.clientMessageId);
      }
    }
  }
}
