export interface StmItem {
  id: string; session_id: string; event_time_watermark: string; capture_sequence: number; revision_lineage: string;
  ingest_sequence: number; entity_refs: readonly string[]; lexical_terms: readonly string[]; vector_key: string; predicate_id: string; bytes: number;
}
export const compareStmOrder = (left: StmItem, right: StmItem): number =>
  left.event_time_watermark.localeCompare(right.event_time_watermark) || left.capture_sequence - right.capture_sequence || left.revision_lineage.localeCompare(right.revision_lineage) || left.ingest_sequence - right.ingest_sequence || left.id.localeCompare(right.id);

/** Append-only STM with deterministic secondary indexes. */
export class StmStore {
  private readonly items = new Map<string, StmItem>();
  private readonly time = new Map<string, Set<string>>(); private readonly entity = new Map<string, Set<string>>();
  private readonly lexical = new Map<string, Set<string>>(); private readonly vector = new Map<string, Set<string>>(); private readonly predicate = new Map<string, Set<string>>();
  private add(index: Map<string, Set<string>>, key: string, id: string): void { index.set(key, new Set([...(index.get(key) ?? []), id])); }
  put(item: StmItem): void { if (this.items.has(item.id)) throw new Error(`duplicate STM item: ${item.id}`); this.items.set(item.id, item); this.add(this.time, item.event_time_watermark, item.id); for (const key of item.entity_refs) this.add(this.entity, key, item.id); for (const key of item.lexical_terms) this.add(this.lexical, key, item.id); this.add(this.vector, item.vector_key, item.id); this.add(this.predicate, item.predicate_id, item.id); }
  all(): readonly StmItem[] { return [...this.items.values()].sort(compareStmOrder); }
  query(index: "time" | "entity" | "lexical" | "vector" | "predicate", key: string): readonly StmItem[] { const table = { time: this.time, entity: this.entity, lexical: this.lexical, vector: this.vector, predicate: this.predicate }[index]; return [...(table.get(key) ?? [])].map((id) => this.items.get(id)!).sort(compareStmOrder); }
  generation(): string { return this.all().map((item) => item.id).join(":"); }
}
