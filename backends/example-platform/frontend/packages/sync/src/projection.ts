/**
 * A durable read projection: the thing the UI reads, offline or not
 * (ADR-004 D1 — cold offline launch MUST show previously synced records).
 *
 * Server state and optimistic local overlays are stored separately so a
 * failed op never corrupts confirmed data: `read()` = server rows + pending
 * overlays applied in order. Domain packages supply the overlay applier;
 * this file knows nothing about any particular record shape.
 */

import type { DurableKv, IdSnapshot } from "@omi-core/contracts";

export interface ProjectionCodec<T> {
  id(record: T): string;
  /** Apply a serialized pending op to the current view; null = record deleted. */
  applyOp(payload: string, current: T | null): T | null;
}

const ROWS_KEY = "rows";
const SET_VERSION_KEY = "set-version";

export class Projection<T> {
  private constructor(
    private readonly kv: DurableKv,
    private readonly codec: ProjectionCodec<T>,
  ) {}

  static async open<T>(kv: DurableKv, codec: ProjectionCodec<T>): Promise<Projection<T>> {
    return new Projection(kv, codec);
  }

  /** Remove one confirmed-deleted row from server truth. */
  async removeServerRow(id: string): Promise<void> {
    const all = await this.serverRows();
    if (all.delete(id)) await this.kv.set(ROWS_KEY, JSON.stringify([...all.values()]));
  }

  /** Replace/insert confirmed server rows. */
  async upsertServerRows(rows: readonly T[]): Promise<void> {
    const all = await this.serverRows();
    for (const row of rows) all.set(this.codec.id(row), row);
    await this.kv.set(ROWS_KEY, JSON.stringify([...all.values()]));
  }

  /**
   * Whole-set id reconcile — ADR-004 D3 with the red-team finding-9 rule:
   * local rows are deleted ONLY against a `complete` snapshot, and only when
   * its setVersion is new to us. An incomplete snapshot may add knowledge,
   * never remove it — honest clients never delete on partial information.
   */
  async reconcile(snapshot: IdSnapshot): Promise<{ deletedIds: string[] }> {
    if (!snapshot.complete) return { deletedIds: [] };
    const seen = await this.kv.get(SET_VERSION_KEY);
    if (seen === snapshot.setVersion) return { deletedIds: [] };
    const keep = new Set(snapshot.ids);
    const all = await this.serverRows();
    const deletedIds: string[] = [];
    for (const id of all.keys()) {
      if (!keep.has(id)) {
        all.delete(id);
        deletedIds.push(id);
      }
    }
    await this.kv.set(ROWS_KEY, JSON.stringify([...all.values()]));
    await this.kv.set(SET_VERSION_KEY, snapshot.setVersion);
    return { deletedIds };
  }

  /** Server truth + pending overlays, in enqueue order. */
  async read(pendingPayloads: readonly { recordId: string; payload: string }[]): Promise<T[]> {
    const all = await this.serverRows();
    const overlaid = new Map(all);
    for (const p of pendingPayloads) {
      const next = this.codec.applyOp(p.payload, overlaid.get(p.recordId) ?? null);
      if (next === null) overlaid.delete(p.recordId);
      else overlaid.set(p.recordId, next);
    }
    return [...overlaid.values()];
  }

  private async serverRows(): Promise<Map<string, T>> {
    const raw = await this.kv.get(ROWS_KEY);
    const rows = raw ? (JSON.parse(raw) as T[]) : [];
    return new Map(rows.map((r) => [this.codec.id(r), r]));
  }
}
