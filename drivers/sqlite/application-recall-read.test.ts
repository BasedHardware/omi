import { describe, expect, test } from "bun:test";
import { Database } from "bun:sqlite";

import type { Evidence, L1Event, ProvisionalClaim, SourceIdentityRef } from "../../core/schema";
import type { DurableStmItem } from "./stm";
import { SqliteStmStore } from "./stm";
import { SqliteLedger } from "./index";
import {
  createSqliteQaRecallLoader,
  type AcceptedRecentState,
  type SqliteQaRecallLimits,
} from "./application-recall-read";

const OWNER = "owner:qa";
const FOREIGN_OWNER = "owner:foreign";
const LIMITS: SqliteQaRecallLimits = Object.freeze({ max_items: 8, max_bytes: 10_000 });

interface Fixture {
  readonly db: Database;
  readonly ledger: SqliteLedger;
  readonly stm: SqliteStmStore;
}

const fixture = (): Fixture => {
  const db = new Database(":memory:");
  // Constructors deliberately run before the coherent loader transaction.
  const ledger = new SqliteLedger(db);
  const stm = new SqliteStmStore(db);
  return { db, ledger, stm };
};

const identity = (id: string): SourceIdentityRef => ({
  namespace_instance_ref: `namespace:${id}`,
  local_key: `local:${id}`,
  producer: { producer_ref: "qa-producer", contract_ref: "qa-contract" },
  asserted_identity: { domain: null, scope_ref: null },
});

const event = (id: string, ownerAccountId = OWNER): L1Event => ({
  event_id: `event:${id}`,
  event_revision_id: `event-revision:${id}`,
  owner_account_id: ownerAccountId,
  capture_session_id: `session:${id}`,
  stream_id: "qa-stream",
  event_kind: "text",
  payload_schema_ref: "qa-text-v1",
  schema_version: "v1",
  payload: { fixture: id },
  event_time: `2026-08-07T00:00:${id.padStart(2, "0")}Z`,
  ingest_time: `2026-08-07T00:01:${id.padStart(2, "0")}Z`,
  source_sequence: Number(id),
  evidence_addressable_refs: [`evidence:${id}`],
  source_trust: "qa",
  policy_labels: [],
  canonical_redacted_hash: `hash:${id}`,
});

const evidence = (id: string, eventRevisionId = `event-revision:${id}`): Evidence => ({
  evidence_id: `evidence:${id}`,
  event_revision_id: eventRevisionId,
  source_unit_ref: `unit:${id}`,
  range: { start: 0, end: 4 },
  excerpt: `qa ${id}`,
  source_identity_ref: identity(id),
  speaker_rendering: null,
  source_local_mention_ref: null,
  state: "active",
  source_trust: "qa",
  policy_labels: [],
  source_independence_key: `source:${id}`,
});

// domain-pending(DIV-DOMCORE-008)
const claim = (
  id: string,
  ownerAccountId = OWNER,
  evidenceRefs: readonly string[] = [`evidence:${id}`],
  observedAt = `2026-08-07T00:00:${id.padStart(2, "0")}Z`,
): ProvisionalClaim => ({
  claim_lineage_id: `lineage:${id}`,
  claim_revision_id: `claim:${id}`,
  owner_account_id: ownerAccountId,
  predicate: "qa_predicate",
  arguments: [{
    slot_id: "subject",
    role: "subject",
    value: { kind: "source_local_ref", ref: `source-local:${id}` },
  }],
  temporal_scope: { observed_at: observedAt, precision: "instant" } as ProvisionalClaim["temporal_scope"],
  evidence_refs: [...evidenceRefs],
  policy_labels: [],
  source_language: "en",
  scope: { locality: "source_local", scope_ref: null },
  lifecycle: "provisional",
  ambiguity_markers: [],
  context_packet: null,
});

// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
interface RowOptions {
  readonly owner_account_id?: string;
  readonly row_id?: string;
  readonly claim_revision_id?: string;
  readonly event_time_watermark?: string;
  readonly capture_sequence?: number;
  readonly revision_lineage?: string;
  readonly ingest_sequence?: number;
  readonly bytes?: number;
  readonly row_evidence?: readonly Evidence[];
  readonly claim_evidence_refs?: readonly string[];
  readonly insert_event?: boolean;
  readonly event_content_owner?: string;
  readonly event_column_owner?: string;
}

// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
const addRow = (target: Fixture, id: string, options: RowOptions = {}): DurableStmItem => {
  const ownerAccountId = options.owner_account_id ?? OWNER;
  const sourceEvent = event(id, options.event_content_owner ?? ownerAccountId);
  if (options.insert_event !== false) {
    target.db.query("INSERT INTO event_revisions VALUES (?, ?, ?, ?, ?)").run(
      sourceEvent.event_revision_id,
      options.event_column_owner ?? ownerAccountId,
      JSON.stringify(sourceEvent),
      `event-hash:${id}`,
      `event-commit:${id}`,
    );
  }
  const sourceEvidence = options.row_evidence ?? [evidence(id, sourceEvent.event_revision_id)];
  const observedAt = options.event_time_watermark ?? sourceEvent.event_time;
  const sourceClaim = {
    ...claim(id, ownerAccountId, options.claim_evidence_refs ?? sourceEvidence.map((item) => item.evidence_id), observedAt),
    claim_revision_id: options.claim_revision_id ?? `claim:${id}`,
  };
  const item: DurableStmItem = {
    id: options.row_id ?? sourceClaim.claim_revision_id,
    session_id: sourceEvent.capture_session_id,
    event_time_watermark: observedAt,
    capture_sequence: options.capture_sequence ?? Number(id),
    revision_lineage: options.revision_lineage ?? `revision-lineage:${id}`,
    ingest_sequence: options.ingest_sequence ?? Number(id),
    entity_refs: [],
    lexical_terms: ["qa", id],
    vector_key: `vector:${id}`,
    predicate_id: sourceClaim.predicate,
    bytes: options.bytes ?? 10,
    claim: sourceClaim,
    evidence: [...sourceEvidence],
    argument_origins: { subject: "independent" },
    settled_window_id: `window:${id}`,
  };
  target.stm.put([{ item, mentions: [] }]);
  return item;
};

const insertDerivation = (target: Fixture, commitId: string, ownerAccountId = OWNER, sequence = 1): void => {
  target.db.query("INSERT INTO derivation_commits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)").run(
    commitId,
    ownerAccountId,
    null,
    sequence,
    `idempotency:${commitId}`,
    `input:${commitId}`,
    `input-version:${commitId}`,
    `output:${commitId}`,
    "success",
    JSON.stringify({ commit_id: commitId }),
  );
};

const loadFor = <Candidate = never>(target: Fixture, overrides: {
  readonly limits?: SqliteQaRecallLimits;
  readonly accepted?: (db: Database, ownerAccountId: string, limits: SqliteQaRecallLimits) => unknown;
} = {}) => createSqliteQaRecallLoader<Candidate>({
  db: target.db,
  ledger: target.ledger,
  owner_account_id: OWNER,
  account_timezone: "UTC",
  limits: overrides.limits ?? LIMITS,
  ...(overrides.accepted ? { accepted_recent_state_port: overrides.accepted } : {}),
});

const totalChanges = (db: Database): number =>
  (db.query("SELECT total_changes() AS count").get() as { count: number }).count;

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
describe("hermetic SQLite QA coherent recall read", () => {
  test("executes durable, STM, and accepted reads synchronously in one deferred transaction", () => {
    const target = fixture();
    addRow(target, "1");
    let durableObserved = false;
    let stmObserved = false;
    let acceptedObserved = false;

    const originalSnapshot = target.ledger.snapshot.bind(target.ledger);
    target.ledger.snapshot = (ownerAccountId: string) => {
      expect(target.db.inTransaction).toBe(true);
      durableObserved = true;
      return originalSnapshot(ownerAccountId);
    };
    const originalQuery = target.db.query.bind(target.db);
    Object.defineProperty(target.db, "query", {
      configurable: true,
      value: (sql: string) => {
        if (sql.includes("FROM stm_items")) {
          expect(target.db.inTransaction).toBe(true);
          stmObserved = true;
        }
        return originalQuery(sql);
      },
    });

    const result = loadFor<{ ref: string }>(target, {
      accepted: (db, ownerAccountId, limits) => {
        expect(db).toBe(target.db);
        expect(db.inTransaction).toBe(true);
        expect(ownerAccountId).toBe(OWNER);
        expect(limits).toEqual(LIMITS);
        expect(Object.isFrozen(limits)).toBe(true);
        acceptedObserved = true;
        return {
          state: "searched",
          declared_frontier: "accepted:1",
          searched_frontier: "accepted:1",
          candidates: [{ ref: "accepted:candidate:1" }],
        };
      },
    })();

    expect({ durableObserved, stmObserved, acceptedObserved }).toEqual({
      durableObserved: true,
      stmObserved: true,
      acceptedObserved: true,
    });
    expect(result.stm_rows.map((item) => item.id)).toEqual(["claim:1"]);
    expect(result.accepted_state.candidates).toEqual([{ ref: "accepted:candidate:1" }]);
    expect(target.db.inTransaction).toBe(false);
  });

  test("filters owner and ledger-decided rows before limit without moving STM coverage coordinates", () => {
    const target = fixture();
    addRow(target, "1", { owner_account_id: FOREIGN_OWNER, capture_sequence: 0 });
    const decided = addRow(target, "2", { capture_sequence: 0 });
    insertDerivation(target, "decision:2");
    target.db.query("INSERT INTO consumed_markers VALUES (?, ?, ?)").run(decided.id, "decision:2", "admit");
    const consumed = addRow(target, "3", { capture_sequence: 0 });
    target.stm.consume([consumed.id]);
    const visible = addRow(target, "4", { capture_sequence: 1 });

    const result = loadFor(target, { limits: { max_items: 1, max_bytes: 100 } })();
    expect(result.stm_rows.map((item) => item.id)).toEqual([visible.id]);
    expect(result.internal_coverage.stm).toEqual({
      selected_items: 1,
      selected_bytes: visible.bytes,
      last_selected_position: {
        event_time_watermark: visible.event_time_watermark,
        capture_sequence: visible.capture_sequence,
        revision_lineage: visible.revision_lineage,
        ingest_sequence: visible.ingest_sequence,
        id: visible.id,
      },
      next_unselected_position: null,
      has_more: false,
      bounds_reached: [],
    });
  });

  test("a foreign-owner derivation marker cannot hide an owner STM row", () => {
    const target = fixture();
    const visible = addRow(target, "1");
    insertDerivation(target, "foreign-decision", FOREIGN_OWNER);
    target.db.query("INSERT INTO consumed_markers VALUES (?, ?, ?)").run(visible.id, "foreign-decision", "admit");
    expect(loadFor(target)().stm_rows.map((item) => item.id)).toEqual([visible.id]);
  });

  test("applies item and byte bounds as deterministic prefixes after SQL", () => {
    const itemBound = fixture();
    const first = addRow(itemBound, "1", { bytes: 4 });
    const second = addRow(itemBound, "2", { bytes: 5 });
    const third = addRow(itemBound, "3", { bytes: 6 });
    const itemResult = loadFor(itemBound, { limits: { max_items: 2, max_bytes: 100 } })();
    expect(itemResult.stm_rows.map((item) => item.id)).toEqual([first.id, second.id]);
    expect(itemResult.internal_coverage.stm).toMatchObject({
      selected_items: 2,
      selected_bytes: 9,
      has_more: true,
      bounds_reached: ["item_limit"],
      next_unselected_position: { id: third.id },
    });

    const byteBound = fixture();
    const byteFirst = addRow(byteBound, "1", { bytes: 4 });
    const byteSecond = addRow(byteBound, "2", { bytes: 5 });
    addRow(byteBound, "3", { bytes: 1 });
    const byteResult = loadFor(byteBound, { limits: { max_items: 8, max_bytes: 4 } })();
    expect(byteResult.stm_rows.map((item) => item.id)).toEqual([byteFirst.id]);
    expect(byteResult.internal_coverage.stm).toMatchObject({
      selected_items: 1,
      selected_bytes: 4,
      has_more: true,
      bounds_reached: ["byte_limit"],
      next_unselected_position: { id: byteSecond.id },
    });
  });

  test("returns selected rows in the existing five-coordinate STM order", () => {
    const target = fixture();
    const watermark = "2026-08-07T12:00:00Z";
    const last = addRow(target, "3", { event_time_watermark: watermark, capture_sequence: 2, revision_lineage: "z", ingest_sequence: 2 });
    const middle = addRow(target, "2", { event_time_watermark: watermark, capture_sequence: 1, revision_lineage: "z", ingest_sequence: 2 });
    const first = addRow(target, "1", { event_time_watermark: watermark, capture_sequence: 1, revision_lineage: "a", ingest_sequence: 1 });
    expect(loadFor(target)().stm_rows.map((item) => item.id)).toEqual([first.id, middle.id, last.id]);
  });

  test("publishes a real ledger-head digest and coherent clock-free snapshot identity", () => {
    const target = fixture();
    addRow(target, "1");
    insertDerivation(target, "head:7", OWNER, 7);
    target.db.query("INSERT INTO graph_heads VALUES (?, ?, ?)").run(OWNER, "head:7", 7);
    const result = loadFor(target)();
    expect(result.internal_coverage.durable).toMatchObject({
      graph_generation: 7,
      ledger_head: { commit_id: "head:7", sequence: 7 },
    });
    expect(result.internal_coverage.durable.ledger_head_digest).toMatch(/^[a-f0-9]{64}$/);
    expect(result.coherent_snapshot_digest).toMatch(/^[a-f0-9]{64}$/);
    expect("read_timestamp" in result).toBe(false);
  });

  test("repeated ASCII reads are deeply immutable, byte-deterministic, and make zero writes", () => {
    const target = fixture();
    addRow(target, "1", { bytes: 12 });
    addRow(target, "2", { bytes: 13 });
    const loader = loadFor<{ a: string; z: string }>(target, {
      accepted: () => ({
        state: "searched",
        declared_frontier: "accepted:2",
        searched_frontier: "accepted:2",
        candidates: [{ z: "last", a: "first" }],
      }),
    });
    const before = totalChanges(target.db);
    const first = loader();
    const middle = totalChanges(target.db);
    const second = loader();
    const after = totalChanges(target.db);

    expect([before, middle, after]).toEqual([before, before, before]);
    expect(JSON.stringify(second)).toBe(JSON.stringify(first));
    expect(second.coherent_snapshot_digest).toBe(first.coherent_snapshot_digest);
    expect(Object.isFrozen(first)).toBe(true);
    expect(Object.isFrozen(first.durable_snapshot)).toBe(true);
    expect(Object.isFrozen(first.stm_rows)).toBe(true);
    expect(Object.isFrozen(first.stm_rows[0]!.claim)).toBe(true);
    expect(Object.isFrozen(first.accepted_state)).toBe(true);
    expect(Object.isFrozen(first.accepted_state.candidates[0]!)).toBe(true);
    expect(Object.isFrozen(first.internal_coverage)).toBe(true);
  });
});

// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
describe("strict STM row integrity", () => {
  test("rejects malformed claims, row/revision mismatch, duplicate references, and malformed evidence", () => {
    const malformedClaim = fixture();
    const malformed = addRow(malformedClaim, "1");
    malformedClaim.db.query("UPDATE stm_items SET claim_json = ? WHERE id = ?").run(
      JSON.stringify({ owner_account_id: OWNER, lifecycle: "provisional" }),
      malformed.id,
    );
    expect(loadFor(malformedClaim)).toThrow("invalid provisional claim");

    const mismatchedId = fixture();
    addRow(mismatchedId, "1", { row_id: "row:not-the-claim" });
    expect(loadFor(mismatchedId)).toThrow("does not match its claim revision id");

    const duplicateRefs = fixture();
    addRow(duplicateRefs, "1", { claim_evidence_refs: ["evidence:1", "evidence:1"] });
    expect(loadFor(duplicateRefs)).toThrow("references must be unique");

    const malformedEvidence = fixture();
    const row = addRow(malformedEvidence, "1");
    malformedEvidence.db.query("UPDATE stm_items SET evidence_json = ? WHERE id = ?").run(
      JSON.stringify([{ evidence_id: "evidence:1", event_revision_id: "event-revision:1" }]),
      row.id,
    );
    expect(loadFor(malformedEvidence)).toThrow("invalid evidence");
  });

  test("rejects missing and cross-owner evidence-to-event closure", () => {
    const missing = fixture();
    addRow(missing, "1", { insert_event: false });
    expect(loadFor(missing)).toThrow("exactly one durable event revision");

    const crossOwner = fixture();
    addRow(crossOwner, "1", { event_content_owner: FOREIGN_OWNER, event_column_owner: OWNER });
    expect(loadFor(crossOwner)).toThrow("cross-owner durable event");
  });

  test("rejects non-active evidence and an event that does not address it exactly once", () => {
    const inactive = fixture();
    addRow(inactive, "1", { row_evidence: [{ ...evidence("1"), state: "security_hidden" }] });
    expect(loadFor(inactive)).toThrow("evidence is not active");

    const unaddressed = fixture();
    addRow(unaddressed, "1");
    const sourceEvent = { ...event("1"), evidence_addressable_refs: ["evidence:other"] };
    unaddressed.db.query("UPDATE event_revisions SET content_json = ? WHERE revision_id = ?").run(
      JSON.stringify(sourceEvent),
      sourceEvent.event_revision_id,
    );
    expect(loadFor(unaddressed)).toThrow("not uniquely addressable");

    const duplicateAddress = fixture();
    addRow(duplicateAddress, "1");
    const duplicateEvent = { ...event("1"), evidence_addressable_refs: ["evidence:1", "evidence:1"] };
    duplicateAddress.db.query("UPDATE event_revisions SET content_json = ? WHERE revision_id = ?").run(
      JSON.stringify(duplicateEvent),
      duplicateEvent.event_revision_id,
    );
    expect(loadFor(duplicateAddress)).toThrow("not uniquely addressable");
  });

  test("fails closed on the legacy producer's unrelated session-evidence bag", () => {
    const target = fixture();
    const extraEvent = event("2");
    target.db.query("INSERT INTO event_revisions VALUES (?, ?, ?, ?, ?)").run(
      extraEvent.event_revision_id,
      OWNER,
      JSON.stringify(extraEvent),
      "event-hash:2",
      "event-commit:2",
    );
    addRow(target, "1", {
      row_evidence: [evidence("1"), evidence("2")],
      claim_evidence_refs: ["evidence:1"],
    });
    expect(loadFor(target)).toThrow("exactly match the claim evidence references");
  });

  test("does not silently drop an owner row whose valid JSON has an invalid claim shape", () => {
    const target = fixture();
    const row = addRow(target, "1");
    target.db.query("UPDATE stm_items SET claim_json = ? WHERE id = ?").run(
      JSON.stringify({ owner_account_id: OWNER, claim_revision_id: row.id }),
      row.id,
    );
    expect(loadFor(target)).toThrow("invalid provisional claim");
  });

  test("rejects syntactically malformed ownerless claim JSON instead of silently filtering it", () => {
    const target = fixture();
    const row = addRow(target, "1");
    target.db.query("UPDATE stm_items SET claim_json = ? WHERE id = ?").run("{", row.id);
    expect(loadFor(target)).toThrow("malformed ownerless claim JSON");
  });
});

// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
describe("accepted recent-state injection", () => {
  test("absence degrades to unavailable and never infers acceptance from durable artifacts", () => {
    const target = fixture();
    addRow(target, "1");
    insertDerivation(target, "successful-memory-looking-commit");
    target.db.query("INSERT INTO placement_artifacts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)").run(
      "placement:1", OWNER, "auto_placement_log", "claim:1", null, null, "[]", "accept_ltm", "source_local", "successful-memory-looking-commit",
    );
    const result = loadFor(target)();
    expect(result.accepted_state).toEqual({
      state: "unavailable",
      declared_frontier: null,
      searched_frontier: null,
      candidates: [],
    });
    expect(result.internal_coverage.accepted).toEqual({
      state: "unavailable",
      declared_frontier: null,
      searched_frontier: null,
      selected_items: 0,
      selected_bytes: 0,
    });
  });

  test("accepts truthful complete and pending shapes without defining acceptance", () => {
    const completeTarget = fixture();
    const complete = loadFor<{ ref: string }>(completeTarget, {
      accepted: () => ({
        state: "searched",
        declared_frontier: "accepted:complete:3",
        searched_frontier: "accepted:complete:3",
        candidates: [{ ref: "candidate:complete" }],
      } satisfies AcceptedRecentState<{ ref: string }>),
    })();
    expect(complete.accepted_state).toEqual({
      state: "searched",
      declared_frontier: "accepted:complete:3",
      searched_frontier: "accepted:complete:3",
      candidates: [{ ref: "candidate:complete" }],
    });

    const pendingTarget = fixture();
    const pending = loadFor<{ ref: string }>(pendingTarget, {
      accepted: () => ({
        state: "pending",
        declared_frontier: "accepted:declared:4",
        searched_frontier: "accepted:searched:3",
        candidates: [{ ref: "candidate:searched" }],
      } satisfies AcceptedRecentState<{ ref: string }>),
    })();
    expect(pending.internal_coverage.accepted).toMatchObject({
      state: "pending",
      declared_frontier: "accepted:declared:4",
      searched_frontier: "accepted:searched:3",
      selected_items: 1,
    });

    const whollyPendingTarget = fixture();
    expect(loadFor(whollyPendingTarget, {
      accepted: () => ({
        state: "pending",
        declared_frontier: "accepted:declared:1",
        searched_frontier: null,
        candidates: [],
      }),
    })().accepted_state.state).toBe("pending");
  });

  test("rejects dishonest frontier/state pairs and accepted over-return", () => {
    const cases: readonly [unknown, string][] = [
      [{ state: "searched", declared_frontier: "accepted:2", searched_frontier: "accepted:1", candidates: [] }, "fully searched"],
      [{ state: "pending", declared_frontier: "accepted:1", searched_frontier: "accepted:1", candidates: [] }, "unsearched declared frontier"],
      [{ state: "no_eligible", declared_frontier: "accepted:1", searched_frontier: null, candidates: [{ ref: "invented" }] }, "cannot carry"],
      [{ state: "unavailable", declared_frontier: null, searched_frontier: null, candidates: [{ ref: "invented" }] }, "require a searched frontier"],
      [{ state: "searched", declared_frontier: "accepted:1", searched_frontier: "accepted:1", candidates: [{ ref: "1" }, { ref: "2" }] }, "item limit"],
    ];
    for (const [accepted, message] of cases) {
      const target = fixture();
      const limits = message === "item limit" ? { max_items: 1, max_bytes: 1_000 } : LIMITS;
      expect(loadFor(target, { limits, accepted: () => accepted })).toThrow(message);
    }

    const byteTarget = fixture();
    expect(loadFor(byteTarget, {
      limits: { max_items: 2, max_bytes: 3 },
      accepted: () => ({
        state: "searched",
        declared_frontier: "accepted:1",
        searched_frontier: "accepted:1",
        candidates: [{ payload: "too-large" }],
      }),
    })).toThrow("byte limit");
  });

  test("rejects accessors, proxies, classes, symbols, hidden fields, extras, sparse arrays, and aliases", () => {
    const valid = () => ({
      state: "searched",
      declared_frontier: "accepted:1",
      searched_frontier: "accepted:1",
      candidates: [{ ref: "candidate:1" }],
    });

    let getterCalls = 0;
    const accessor = valid() as Record<string, unknown>;
    Object.defineProperty(accessor, "state", {
      enumerable: true,
      get() { getterCalls += 1; return "searched"; },
    });
    expect(loadFor(fixture(), { accepted: () => accessor })).toThrow("accessors");
    expect(getterCalls).toBe(0);

    let proxyTraps = 0;
    const proxied = new Proxy(valid(), {
      ownKeys(target) { proxyTraps += 1; return Reflect.ownKeys(target); },
      getPrototypeOf(target) { proxyTraps += 1; return Reflect.getPrototypeOf(target); },
    });
    expect(loadFor(fixture(), { accepted: () => proxied })).toThrow("proxies");
    expect(proxyTraps).toBe(0);

    class AcceptedClass {
      state = "searched";
      declared_frontier = "accepted:1";
      searched_frontier = "accepted:1";
      candidates: unknown[] = [];
    }
    expect(loadFor(fixture(), { accepted: () => new AcceptedClass() })).toThrow("non-plain");

    const symbol = valid() as Record<PropertyKey, unknown>;
    symbol[Symbol("hidden")] = "secret";
    expect(loadFor(fixture(), { accepted: () => symbol })).toThrow("symbol");

    const hidden = valid();
    Object.defineProperty(hidden, "hidden", { enumerable: false, value: "secret" });
    expect(loadFor(fixture(), { accepted: () => hidden })).toThrow("hidden fields");

    expect(loadFor(fixture(), { accepted: () => ({ ...valid(), extra: "secret" }) })).toThrow("invalid shape");

    const sparse = valid();
    sparse.candidates = new Array(1);
    expect(loadFor(fixture(), { accepted: () => sparse })).toThrow("sparse");

    const candidate = { ref: "candidate:shared" };
    expect(loadFor(fixture(), { accepted: () => ({ ...valid(), candidates: [candidate, candidate] }) })).toThrow("shared aliases");
  });
});

describe("configuration bounds", () => {
  test("rejects negative, fractional, unsafe, and limit-plus-one overflow configurations", () => {
    const target = fixture();
    const invalid: readonly SqliteQaRecallLimits[] = [
      { max_items: -1, max_bytes: 1 },
      { max_items: 1.5, max_bytes: 1 },
      { max_items: Number.MAX_SAFE_INTEGER + 1, max_bytes: 1 },
      { max_items: Number.MAX_SAFE_INTEGER, max_bytes: 1 },
      { max_items: 1, max_bytes: Number.MAX_SAFE_INTEGER },
    ];
    for (const limits of invalid) {
      expect(() => loadFor(target, { limits })).toThrow();
    }
  });

  test("rejects an invalid timezone before any read transaction", () => {
    const target = fixture();
    let snapshotCalls = 0;
    const original = target.ledger.snapshot.bind(target.ledger);
    target.ledger.snapshot = (ownerAccountId: string) => { snapshotCalls += 1; return original(ownerAccountId); };
    expect(() => createSqliteQaRecallLoader({
      db: target.db,
      ledger: target.ledger,
      owner_account_id: OWNER,
      account_timezone: "Not/A_Real_Zone",
      limits: LIMITS,
    })).toThrow("timezone is invalid");
    expect(snapshotCalls).toBe(0);
  });
});
