/**
 * FoldersStore: the one object a surface talks to. Wires Outbox + Projection +
 * the legacy folders adapter, owns the server-assigned-id alias map (the
 * ADR-004 D2 gap), and exposes subscribe/read for any view layer.
 *
 * Alias protocol: the legacy backend ignores client ids on create and assigns
 * its own. We keep the LOCAL slug as the record's identity everywhere in the
 * client: server rows arriving under the server id are re-keyed to the local
 * slug on ingest, and outgoing patch/delete ops resolve local → wire id at
 * the transport. When the rewritten backend honors client ids, the alias map
 * is empty and this machinery is inert.
 */

import type { DeadLetter, Folder, FolderPatch, RecordId } from "@omi-core/contracts";
import type { DurableKv, StorageBridge } from "@omi-core/contracts";
import type { Env } from "@omi-core/kernel";
import { Outbox, Projection } from "@omi-core/sync";
import {
  fetchFolderIdSnapshot,
  fetchFolders,
  foldersTransport,
  type HttpClient,
} from "@omi-core/adapters-legacy";
import {
  buildCreateFolder,
  buildDeleteFolder,
  buildPatchFolder,
  foldersCodec,
  folderToPendingOp,
} from "./folders-codec.js";

const ALIAS_KEY = "id-aliases"; // { [serverId]: localSlug }

export class FoldersStore {
  private listeners = new Set<() => void>();
  private aliases: Record<string, string> = {};

  private constructor(
    private readonly env: Env,
    private readonly http: HttpClient,
    private readonly outbox: Outbox,
    private readonly projection: Projection<Folder>,
    private readonly aliasKv: DurableKv,
  ) {}

  static async open(bridge: StorageBridge, env: Env, http: HttpClient): Promise<FoldersStore> {
    const aliasKv = await bridge.openKv("folders-aliases");
    const projection = await Projection.open(await bridge.openKv("folders-projection"), foldersCodec);

    let store: FoldersStore;
    const transport = foldersTransport(
      http,
      (localId, serverId) => void store.recordAlias(localId, serverId),
      (localId) => store.toWireId(localId),
    );
    const outbox = await Outbox.open(bridge, env, transport, "folders");
    store = new FoldersStore(env, http, outbox, projection, aliasKv);
    store.aliases = JSON.parse((await aliasKv.get(ALIAS_KEY)) ?? "{}") as Record<string, string>;
    outbox.onChange = () => store.notify();
    outbox.onOutcome = async (op, outcome) => {
      if (outcome.state !== "confirmed") return;
      const current = (await projection.read([])).find((r) => r.id === op.recordId) ?? null;
      const next = foldersCodec.applyOp(op.payload, current);
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
  async list(): Promise<Folder[]> {
    const pending = this.outbox.pendingOps().map((o) => ({ recordId: o.recordId, payload: o.payload }));
    const rows = await this.projection.read(pending);
    return rows.sort((a, b) => a.order - b.order || a.createdAt - b.createdAt);
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

  /** Pull server truth: rows + id reconcile. Safe to call on interval; all
   * failures are silent-degrade (offline reads keep serving the projection). */
  async refresh(): Promise<void> {
    const rows = await fetchFolders(this.http);
    if (rows) {
      await this.projection.upsertServerRows(rows.map((r) => this.rekeyed(r)));
    }
    const snapshot = await fetchFolderIdSnapshot(this.http);
    if (snapshot) {
      const localIds = snapshot.ids.map((id) => this.aliases[id] ?? id);
      await this.projection.reconcile({ ...snapshot, ids: localIds });
    }
    this.notify();
  }

  private rekeyed(row: Folder): Folder {
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
