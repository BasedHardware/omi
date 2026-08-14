/**
 * TasksStore: the one object a surface talks to. Wires Outbox + Projection +
 * the legacy tasks adapter, owns the server-assigned-id alias map (the
 * ADR-004 D2 gap), and exposes subscribe/read for any view layer.
 *
 * Alias protocol: the legacy backend ignores client ids on create and assigns
 * its own. We keep the LOCAL slug as the record's identity everywhere in the
 * client: server rows arriving under the server id are re-keyed to the local
 * slug on ingest, and outgoing patch/delete ops resolve local → wire id at
 * the transport. When the rewritten backend honors client ids, the alias map
 * is empty and this machinery is inert.
 */

import type { DeadLetter, RecordId, Task, TaskPatch } from "@omi-core/contracts";
import type { Env } from "@omi-core/kernel";
import type { StorageBridge } from "@omi-core/contracts";
import { Outbox, Projection } from "@omi-core/sync";
import {
  fetchIdSnapshot,
  fetchTasks,
  tasksTransport,
} from "@omi-core/adapters-legacy";
import type { HttpClient } from "@omi-core/contracts";
import type { DurableKv } from "@omi-core/contracts";
import { buildCreateTask, buildDeleteTask, buildPatchTask, tasksCodec, taskToPendingOp } from "./tasks-codec.js";
import { RefreshTracker, type StoreStatus } from "./store-status.js";

const ALIAS_KEY = "id-aliases"; // { [serverId]: localSlug }

export class TasksStore {
  private listeners = new Set<() => void>();
  private aliases: Record<string, string> = {};
  private readonly refreshTracker: RefreshTracker;

  private constructor(
    private readonly env: Env,
    private readonly http: HttpClient,
    private readonly outbox: Outbox,
    private readonly projection: Projection<Task>,
    private readonly aliasKv: DurableKv,
    hasSavedData: boolean,
  ) {
    this.refreshTracker = new RefreshTracker(hasSavedData);
  }

  static async open(bridge: StorageBridge, env: Env, http: HttpClient): Promise<TasksStore> {
    const aliasKv = await bridge.openKv("tasks-aliases");
    const projection = await Projection.open(await bridge.openKv("tasks-projection"), tasksCodec);

    let store: TasksStore;
    const transport = tasksTransport(
      http,
      (localId, serverId) => void store.recordAlias(localId, serverId),
      (localId) => store.toWireId(localId),
    );
    const outbox = await Outbox.open(bridge, env, transport, "tasks");
    store = new TasksStore(env, http, outbox, projection, aliasKv, (await projection.read([])).length > 0);
    store.aliases = JSON.parse((await aliasKv.get(ALIAS_KEY)) ?? "{}") as Record<string, string>;
    outbox.onChange = () => store.notify();
    outbox.onOutcome = async (op, outcome) => {
      if (outcome.state !== "confirmed") return;
      const current = (await projection.read([])).find((r) => r.id === op.recordId) ?? null;
      const next = tasksCodec.applyOp(op.payload, current);
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
  async list(): Promise<Task[]> {
    const pending = this.outbox.pendingOps().map((o) => ({ recordId: o.recordId, payload: o.payload }));
    const rows = await this.projection.read(pending);
    return rows.sort((a, b) => Number(a.completed) - Number(b.completed) || b.createdAt - a.createdAt);
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

  async create(description: string, dueAt?: number): Promise<void> {
    await this.outbox.enqueue(taskToPendingOp(buildCreateTask(this.env, description, dueAt)));
    this.notify();
  }

  async patch(id: RecordId, patch: TaskPatch): Promise<void> {
    await this.outbox.enqueue(taskToPendingOp(buildPatchTask(this.env, id, patch)));
    this.notify();
  }

  async delete(id: RecordId): Promise<void> {
    await this.outbox.enqueue(taskToPendingOp(buildDeleteTask(this.env, id)));
    this.notify();
  }

  onAuthRestored(): void {
    this.outbox.onAuthRestored();
  }

  /** Pull server truth: rows + id reconcile. Safe to call on interval; all
   * failures are silent-degrade (offline reads keep serving the projection). */
  async refresh(): Promise<void> {
    const token = this.refreshTracker.begin();
    this.notify();
    let rows: Task[] | null = null;
    let failed = false;
    let thrown: unknown;
    try {
      rows = await fetchTasks(this.http);
      if (rows) {
        await this.refreshTracker.applyIfCurrent(token, () =>
          this.projection.upsertServerRows(rows!.map((r) => this.rekeyed(r))),
        );
      }
      if (this.refreshTracker.isCurrent(token)) {
        const snapshot = await fetchIdSnapshot(this.http);
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

  private rekeyed(row: Task): Task {
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
