import { Database } from "bun:sqlite";
import type { Evidence, Mention, ProvisionalClaim } from "../../core/schema";
import { compareStmOrder, type StmItem } from "../../core/stm";

export interface DurableStmItem extends StmItem {
  claim: ProvisionalClaim;
  evidence: readonly Evidence[];
  argument_origins: Readonly<Record<string, "suggested" | "independent">>;
  settled_window_id: string;
}

/** Small, disposable STM for a harness run. */
export class SqliteStmStore {
  constructor(private readonly db: Database) {
    db.exec(`
      CREATE TABLE IF NOT EXISTS stm_items (
        id TEXT PRIMARY KEY, session_id TEXT NOT NULL, event_time_watermark TEXT NOT NULL,
        capture_sequence INTEGER NOT NULL, revision_lineage TEXT NOT NULL, ingest_sequence INTEGER NOT NULL,
        entity_refs_json TEXT NOT NULL, lexical_terms_json TEXT NOT NULL, vector_key TEXT NOT NULL,
        predicate_id TEXT NOT NULL, bytes INTEGER NOT NULL, claim_json TEXT NOT NULL,
        evidence_json TEXT NOT NULL, argument_origins_json TEXT NOT NULL, settled_window_id TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS stm_items_order ON stm_items(event_time_watermark, capture_sequence, revision_lineage, ingest_sequence, id);
      CREATE INDEX IF NOT EXISTS stm_items_session ON stm_items(session_id);
      CREATE INDEX IF NOT EXISTS stm_items_predicate ON stm_items(predicate_id);
      CREATE INDEX IF NOT EXISTS stm_items_vector ON stm_items(vector_key);
      CREATE TABLE IF NOT EXISTS stm_mentions (mention_id TEXT PRIMARY KEY, claim_revision_id TEXT NOT NULL, content_json TEXT NOT NULL);
    `);
  }

  put(outputs: readonly { item: DurableStmItem; mentions: readonly Mention[] }[]): void {
    this.db.transaction(() => {
      for (const { item, mentions } of outputs) {
        this.db.query("INSERT INTO stm_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)").run(
          item.id, item.session_id, item.event_time_watermark, item.capture_sequence, item.revision_lineage,
          item.ingest_sequence, JSON.stringify(item.entity_refs), JSON.stringify(item.lexical_terms), item.vector_key,
          item.predicate_id, item.bytes, JSON.stringify(item.claim), JSON.stringify(item.evidence),
          JSON.stringify(item.argument_origins), item.settled_window_id,
        );
        for (const mention of mentions) this.db.query("INSERT INTO stm_mentions VALUES (?, ?, ?)").run(mention.mention_id, mention.claim_revision_id, JSON.stringify(mention));
      }
    })();
  }

  all(): readonly DurableStmItem[] {
    return (this.db.query("SELECT * FROM stm_items ORDER BY event_time_watermark, capture_sequence, revision_lineage, ingest_sequence, id").all() as Record<string, unknown>[])
      .map((row) => this.row(row)).sort(compareStmOrder);
  }

  mentions(): readonly Mention[] {
    return (this.db.query("SELECT content_json FROM stm_mentions ORDER BY mention_id").all() as { content_json: string }[])
      .map((row) => JSON.parse(row.content_json) as Mention);
  }

  private row(row: Record<string, unknown>): DurableStmItem {
    return {
      id: String(row.id), session_id: String(row.session_id), event_time_watermark: String(row.event_time_watermark),
      capture_sequence: Number(row.capture_sequence), revision_lineage: String(row.revision_lineage), ingest_sequence: Number(row.ingest_sequence),
      entity_refs: JSON.parse(String(row.entity_refs_json)), lexical_terms: JSON.parse(String(row.lexical_terms_json)),
      vector_key: String(row.vector_key), predicate_id: String(row.predicate_id), bytes: Number(row.bytes),
      claim: JSON.parse(String(row.claim_json)), evidence: JSON.parse(String(row.evidence_json)),
      argument_origins: JSON.parse(String(row.argument_origins_json)), settled_window_id: String(row.settled_window_id),
    };
  }
}
