// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-007)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMCORE-012)
// domain-pending(DIV-DOMTASK-004)
// domain-pending(DIV-DOMX-001)
// domain-pending(DIV-DOMX-005)
import { createHash } from "node:crypto";
import { describe, expect, test } from "bun:test";
import { Database } from "bun:sqlite";

import {
  createSqliteQaRecallLoader,
  type SqliteQaRecallLimits,
} from "../../../drivers/sqlite/application-recall-read";
import {
  QA_FIXTURE_TIME_ANCHOR_UTC,
  resetQaSnapshot,
  seedQaSnapshot,
  type SeedQaSnapshotOptions,
} from "./seed";

const OWNER = "owner:qa-seed";
const TIMEZONE = "America/Los_Angeles";
const LIMITS: SqliteQaRecallLimits = Object.freeze({ max_items: 64, max_bytes: 1_000_000 });

const options = (overrides: Partial<SeedQaSnapshotOptions> = {}): SeedQaSnapshotOptions => ({
  owner_account_id: OWNER,
  memory_count: 3,
  account_timezone: TIMEZONE,
  ...overrides,
});

const openDb = (): Database => new Database(":memory:");

/**
 * Full database *content* digest over every user table (ordered rows) plus
 * `sqlite_sequence`. Prefer this over `db.serialize()`: DELETE/DROP churn can
 * leave free pages that change the image bytes while row content is identical.
 */
const hashDatabaseContent = (db: Database): string => {
  const hash = createHash("sha256");
  const tables = (
    db.query(
      "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name",
    ).all() as { name: string }[]
  ).map((row) => row.name);
  for (const table of tables) {
    const columns = (
      db.query(`PRAGMA table_info("${table}")`).all() as { name: string }[]
    ).map((row) => row.name);
    const orderBy = columns.map((name) => `"${name}"`).join(", ");
    const rows = db.query(`SELECT * FROM "${table}" ORDER BY ${orderBy}`).all();
    hash.update(table);
    hash.update(JSON.stringify(rows));
  }
  const hasSequence = db.query(
    "SELECT 1 AS present FROM sqlite_master WHERE type = 'table' AND name = 'sqlite_sequence'",
  ).get();
  if (hasSequence) {
    hash.update("sqlite_sequence");
    hash.update(JSON.stringify(
      db.query("SELECT name, seq FROM sqlite_sequence ORDER BY name").all(),
    ));
  }
  return hash.digest("hex");
};

const load = (db: Database, accountTimezone = TIMEZONE) => createSqliteQaRecallLoader({
  db,
  owner_account_id: OWNER,
  account_timezone: accountTimezone,
  limits: LIMITS,
});

const GENERIC = new Set(["subject:generic", "sensitivity:generic", "capture:generic"]);

describe("seedQaSnapshot", () => {
  // storage-provenance-ok(test assertion on the loader's own output; a test that inspects storage state proves the seeder and loader agree, and emits nothing to a wire)
  test("loader returns a non-empty durable_snapshot of application-visible claims", () => {
    // red-proof: set claim.scope.locality to "source_local" (or lifecycle/placement non-canonical) and the visibility assertions fail; omit claim_revisions inserts and durable_snapshot.claims is empty
    const db = openDb();
    seedQaSnapshot(db, options({ memory_count: 3 }));
    const result = load(db)();

    // storage-provenance-ok(test assertion on the loader's own output; a test that inspects storage state proves the seeder and loader agree, and emits nothing to a wire)
    expect(result.durable_snapshot.claims.length).toBe(3);
    // storage-provenance-ok(test assertion on the loader's own output; a test that inspects storage state proves the seeder and loader agree, and emits nothing to a wire)
    expect(result.durable_snapshot.claims.map((item) => item.revision_id)).toEqual([
      "claim:qa:000000",
      "claim:qa:000001",
      "claim:qa:000002",
    ]);

    // storage-provenance-ok(test assertion on the loader's own output; a test that inspects storage state proves the seeder and loader agree, and emits nothing to a wire)
    for (const item of result.durable_snapshot.claims) {
      expect(item.placement_status).toBe("canonical");
      expect(item.claim.lifecycle).toBe("canonical");
      expect(item.claim.scope.locality).toBe("durable");
      expect(item.claim.policy_labels.every((label) => GENERIC.has(label))).toBe(true);
      expect(item.claim.evidence_refs.length).toBeGreaterThan(0);
    }

    // storage-provenance-ok(test assertion on the loader's own output; a test that inspects storage state proves the seeder and loader agree, and emits nothing to a wire)
    expect(result.durable_snapshot.evidence?.length).toBe(3);
    // storage-provenance-ok(test assertion on the loader's own output; a test that inspects storage state proves the seeder and loader agree, and emits nothing to a wire)
    expect(result.durable_snapshot.events?.length).toBe(3);
    // storage-provenance-ok(test assertion on the loader's own output; a test that inspects storage state proves the seeder and loader agree, and emits nothing to a wire)
    for (const claim of result.durable_snapshot.claims) {
      for (const evidenceId of claim.claim.evidence_refs) {
        // storage-provenance-ok(test assertion on the loader's own output; a test that inspects storage state proves the seeder and loader agree, and emits nothing to a wire)
        const evidenceRows = (result.durable_snapshot.evidence ?? []).filter(
          (row) => row.evidence.evidence_id === evidenceId,
        );
        expect(evidenceRows).toHaveLength(1);
        const evidence = evidenceRows[0]!.evidence;
        // storage-provenance-ok(test assertion on the loader's own output; a test that inspects storage state proves the seeder and loader agree, and emits nothing to a wire)
        const events = (result.durable_snapshot.events ?? []).filter(
          (row) => row.revision_id === evidence.event_revision_id,
        );
        expect(events).toHaveLength(1);
        expect(events[0]!.event.owner_account_id).toBe(OWNER);
        expect(
          events[0]!.event.evidence_addressable_refs.filter((ref) => ref === evidenceId),
        ).toHaveLength(1);
      }
    }
  });

  test("same options always produce byte-identical database content", () => {
    // red-proof: insert Date.now() / Math.random() / randomUUID into any seeded id or payload and the digests diverge
    const first = openDb();
    const second = openDb();
    seedQaSnapshot(first, options({ memory_count: 4 }));
    seedQaSnapshot(second, options({ memory_count: 4 }));
    expect(hashDatabaseContent(second)).toBe(hashDatabaseContent(first));
    // storage-provenance-ok(test assertion on the loader's own output; a test that inspects storage state proves the seeder and loader agree, and emits nothing to a wire)
    expect(load(first)().coherent_snapshot_digest).toBe(load(second)().coherent_snapshot_digest);
  });

  test("fixture time is anchored and account_timezone is required and validated", () => {
    // red-proof: pass account_timezone "Not/A_Real_Zone" and seed throws; change QA_FIXTURE_TIME_ANCHOR_UTC and observed_at assertions fail
    expect(QA_FIXTURE_TIME_ANCHOR_UTC).toBe("2026-08-07T12:00:00.000Z");
    const db = openDb();
    expect(() => seedQaSnapshot(db, options({ account_timezone: "Not/A_Real_Zone" }))).toThrow(
      "account_timezone is invalid",
    );
    seedQaSnapshot(db, options({ memory_count: 2, account_timezone: "UTC" }));
    const result = load(db, "UTC")();
    // storage-provenance-ok(test assertion on the loader's own output; a test that inspects storage state proves the seeder and loader agree, and emits nothing to a wire)
    expect(result.durable_snapshot.claims[0]!.claim.temporal_scope.observed_at).toBe(
      QA_FIXTURE_TIME_ANCHOR_UTC,
    );
    // storage-provenance-ok(test assertion on the loader's own output; a test that inspects storage state proves the seeder and loader agree, and emits nothing to a wire)
    expect(result.durable_snapshot.claims[0]!.claim.temporal_scope.valid_time?.derivation.timezone)
      .toBe("UTC");
    expect(result.account_timezone).toBe("UTC");
  });

  test("resetQaSnapshot then reseed is byte-identical to a fresh seed", () => {
    // red-proof: leave a row in consumed_markers / sqlite_sequence / claim_revisions during reset and the digests diverge
    const fresh = openDb();
    seedQaSnapshot(fresh, options({ memory_count: 5 }));
    const freshDigest = hashDatabaseContent(fresh);

    const cycled = openDb();
    seedQaSnapshot(cycled, options({ memory_count: 5 }));
    // Mutate seeder-owned tables so a shallow reset would leave residue.
    cycled.query("INSERT INTO consumed_markers VALUES (?, ?, ?)").run(
      "claim:qa:000000",
      "commit:qa:000000",
      "admit",
    );
    expect(hashDatabaseContent(cycled)).not.toBe(freshDigest);

    resetQaSnapshot(cycled);
    expect(
      (cycled.query("SELECT COUNT(*) AS count FROM consumed_markers").get() as { count: number }).count,
    ).toBe(0);
    expect(
      (cycled.query("SELECT COUNT(*) AS count FROM claim_revisions").get() as { count: number }).count,
    ).toBe(0);
    seedQaSnapshot(cycled, options({ memory_count: 5 }));
    expect(hashDatabaseContent(cycled)).toBe(freshDigest);
    // storage-provenance-ok(test assertion on the loader's own output; a test that inspects storage state proves the seeder and loader agree, and emits nothing to a wire)
    expect(load(cycled)().durable_snapshot.claims).toHaveLength(5);
  });

  test("memory_count controls the visible durable claim count the loader returns", () => {
    // red-proof: hard-code a fixed INSERT count ignoring memory_count and this equality fails
    const db = openDb();
    seedQaSnapshot(db, options({ memory_count: 0 }));
    // storage-provenance-ok(test assertion on the loader's own output; a test that inspects storage state proves the seeder and loader agree, and emits nothing to a wire)
    expect(load(db)().durable_snapshot.claims).toEqual([]);

    seedQaSnapshot(db, options({ memory_count: 7 }));
    // storage-provenance-ok(test assertion on the loader's own output; a test that inspects storage state proves the seeder and loader agree, and emits nothing to a wire)
    expect(load(db)().durable_snapshot.claims).toHaveLength(7);
  });
});

describe("the seeder writes no short-term overlay material", () => {
  test("stm_items is empty after seeding, and after reset+reseed", () => {
    // This is what warrants app-facing.ts DECLARING stmCoverageState
    // "no_eligible" instead of deriving it from a row count.
    //
    // That distinction is a security property, not a style preference. The
    // loader's eligible-STM count filters only on owner and consumption: it
    // applies no policy-label filter, and STM rows hold PROVISIONAL claims,
    // which can never enter this projection's authorized closure (the closure
    // requires canonical placement, canonical lifecycle, durable locality and
    // generic policy labels). A coverage state computed from that count is
    // therefore 100% storage-scoped and 0% authorization-scoped, and it lands
    // in a wire-visible completeness field. Declaring the state from a property
    // of the seeder cannot vary with rows the reader may not see.
    //
    // red-proof: make the seeder insert one stm_items row, or drop "stm_items"
    // from QA_SEED_TABLES so a foreign row survives reset, and this fails -
    // which is precisely when the declaration would stop being warranted.
    const db = new Database(":memory:");
    const countStm = (): number =>
      (db.query("SELECT COUNT(*) AS total FROM stm_items").get() as { total: number }).total;

    seedQaSnapshot(db, {
      owner_account_id: "stm-check-owner",
      memory_count: 4,
      account_timezone: "America/Los_Angeles",
    });
    expect(countStm()).toBe(0);

    resetQaSnapshot(db);
    expect(countStm()).toBe(0);

    seedQaSnapshot(db, {
      owner_account_id: "stm-check-owner",
      memory_count: 4,
      account_timezone: "America/Los_Angeles",
    });
    expect(countStm()).toBe(0);
  });
});
