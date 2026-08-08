// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-007)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMCORE-012)
// domain-pending(DIV-DOMTASK-004)
// domain-pending(DIV-DOMX-001)
// domain-pending(DIV-DOMX-005)
// domain-pending(DIV-DOMX-006)
import { describe, expect, test } from "bun:test";
import { Database } from "bun:sqlite";

import {
  readAfterApplicationAuthorization,
  type ApplicationMemoryReadAuthorizationRequest,
} from "../../core/retrieve/authorization-boundary";
import { buildDeterministicAnchors } from "../../core/retrieve/tree";
import { createSqliteQaRecallLoader, type SqliteQaRecallLimits } from "../../drivers/sqlite/application-recall-read";
import { SqliteLedger } from "../../drivers/sqlite/index";
import { seedQaSnapshot, type QaSeedOptions } from "./seed";

const OWNER = "owner:qa-seed";
const TIMEZONE = "UTC";
const CLAIM_COUNT = 3;
const LIMITS: SqliteQaRecallLimits = Object.freeze({ max_items: 64, max_bytes: 1_000_000 });

const seedOptions = (overrides: Partial<QaSeedOptions> = {}): QaSeedOptions => ({
  owner_account_id: OWNER,
  account_timezone: TIMEZONE,
  claim_count: CLAIM_COUNT,
  ...overrides,
});

const authorizationRequest = (ownerAccountId = OWNER): ApplicationMemoryReadAuthorizationRequest => ({
  owner_account_id: ownerAccountId,
  credential: {
    owner_account_id: ownerAccountId,
    credential_kind: "mcp_api_key",
    app_id: "app:qa-seed",
    key_id: "key:qa-seed",
    scopes: ["memories.read"],
    active: true,
  },
  persisted_grant: {
    owner_account_id: ownerAccountId,
    consumer: "mcp",
    app_id: "app:qa-seed",
    key_id: "key:qa-seed",
    enabled: true,
    default_read: true,
    scopes: ["memories.read"],
  },
});

const seedDatabase = (options: QaSeedOptions = seedOptions()) => {
  const db = new Database(":memory:");
  const result = seedQaSnapshot(db, options);
  const ledger = new SqliteLedger(db);
  return { db, ledger, result, options };
};

describe("seedQaSnapshot", () => {
  test("projects exactly claim_count visible canonical claims with known revision ids", () => {
    const { ledger, result, options } = seedDatabase();
    const snapshot = ledger.snapshot(options.owner_account_id);
    expect(snapshot.graph_generation).toBe(result.graph_generation);
    expect(snapshot.claims.map((item) => item.revision_id)).toEqual([...result.claim_revision_ids]);
    expect(snapshot.claims.every((item) => item.placement_status === "canonical")).toBe(true);
    expect(snapshot.claims.every((item) => item.claim.lifecycle === "canonical")).toBe(true);
    expect(snapshot.claims.every((item) => item.claim.scope.locality === "durable")).toBe(true);

    const projected = readAfterApplicationAuthorization(authorizationRequest(), () => ({
      snapshot,
      options: { account_timezone: options.account_timezone },
    }));
    expect(projected.claims.map((claim) => claim.claim_revision_id)).toEqual([
      "qa-claim:owner:qa-seed:0000",
      "qa-claim:owner:qa-seed:0001",
      "qa-claim:owner:qa-seed:0002",
    ]);
    expect(projected.claims.map((claim) => claim.claim_revision_id)).toEqual([...result.claim_revision_ids]);
    expect(result.evidence_ids).toEqual([
      "qa-evidence:owner:qa-seed:0000",
      "qa-evidence:owner:qa-seed:0001",
      "qa-evidence:owner:qa-seed:0002",
    ]);
    expect(result.event_revision_ids).toEqual([
      "qa-event-revision:owner:qa-seed:0000",
      "qa-event-revision:owner:qa-seed:0001",
      "qa-event-revision:owner:qa-seed:0002",
    ]);
  });

  test("identical options into two databases yield byte-identical ledger snapshots", () => {
    const options = seedOptions();
    const left = seedDatabase(options);
    const right = seedDatabase(options);
    expect(JSON.stringify(left.ledger.snapshot(OWNER))).toBe(JSON.stringify(right.ledger.snapshot(OWNER)));
    expect(left.result).toEqual(right.result);
  });

  test("createSqliteQaRecallLoader succeeds and digests match across identical seeds", () => {
    const options = seedOptions();
    const left = seedDatabase(options);
    const right = seedDatabase(options);

    const loadLeft = createSqliteQaRecallLoader({
      db: left.db,
      owner_account_id: OWNER,
      account_timezone: TIMEZONE,
      limits: LIMITS,
    })();
    const loadRight = createSqliteQaRecallLoader({
      db: right.db,
      owner_account_id: OWNER,
      account_timezone: TIMEZONE,
      limits: LIMITS,
    })();

    expect(loadLeft.durable_snapshot.claims.map((item) => item.revision_id)).toEqual([
      ...left.result.claim_revision_ids,
    ]);
    expect(loadRight.durable_snapshot.claims.map((item) => item.revision_id)).toEqual([
      ...right.result.claim_revision_ids,
    ]);
    expect(loadLeft.coherent_snapshot_digest).toBe(loadRight.coherent_snapshot_digest);
    expect(loadLeft.coherent_snapshot_digest).toMatch(/^[a-f0-9]{64}$/);
  });

  test("buildDeterministicAnchors covers every seeded claim revision id", () => {
    const { ledger, result, options } = seedDatabase();
    const projected = readAfterApplicationAuthorization(authorizationRequest(), () => ({
      snapshot: ledger.snapshot(options.owner_account_id),
      options: { account_timezone: options.account_timezone },
    }));
    const tree = buildDeterministicAnchors(projected);
    expect(tree.nodes.length).toBeGreaterThanOrEqual(result.claim_revision_ids.length);
    expect(tree.nodes.every((node) => node.member_claim_revision_ids.length > 0)).toBe(true);

    const covered = new Set(tree.nodes.flatMap((node) => node.member_claim_revision_ids));
    for (const claimRevisionId of result.claim_revision_ids) {
      expect(covered.has(claimRevisionId)).toBe(true);
    }
    expect([...covered].sort()).toEqual([...result.claim_revision_ids].sort());
  });
});
