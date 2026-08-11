import { expect, test } from "bun:test";
import { Database } from "bun:sqlite";
import { canonicalizeRedacted, prepareDerivation, sha256CanonicalRedacted, type AtomicGraphTransition, type GraphRevision } from "../../core/ledger";
import { project } from "../../core/retrieve";
import { walk } from "../../core/retrieve/walk";
import { DeterministicFakeModel } from "../model/port";
import { groundedFormationMentionId } from "../../core/extract/grounded";
import { predicateIdForName } from "../../core/consolidate/predicate-identity";
import { runSqliteDreamCycle, SqliteDreamStore } from "./dream";
import { SqliteLedger } from "./index";

const owner = "dream-test-owner";
const versions = { strategy_version: "test", model_version: "deterministic-fake-v1", prompt_version: "test", policy_version: "test", code_version: "test", schema_version: "test", tokenizer_version: "none", tool_version: "test" };
const temporal = { typed_expression: { kind: "absolute" as const, granularity: "instant" as const, value: "2026-01-01T00:00:00Z" }, resolved_interval: { kind: "instant" as const, start: "2026-01-01T00:00:00Z", end: "2026-01-01T00:00:00Z", timezone: "UTC", granularity: "instant" as const }, derivation: { resolver_version: "test", timezone: "UTC" } };

const seedClaim = (id: string, reprojectable: boolean) => {
  const local = `source-local:${id}`;
  const identity = { namespace_instance_ref: `namespace:${id}`, local_key: id, producer: { producer_ref: "test", contract_ref: "test" }, asserted_identity: { domain: null, scope_ref: null } };
  const event = { event_id: `event:${id}`, event_revision_id: `event:${id}`, owner_account_id: owner, capture_session_id: `session:${id}`, stream_id: "test", event_kind: "text", payload_schema_ref: "test", schema_version: "v1", payload: {}, event_time: "2026-01-01T00:00:00Z", ingest_time: "2026-01-01T00:00:00Z", source_sequence: 0, evidence_addressable_refs: [`evidence:${id}`], source_trust: "test", policy_labels: [], canonical_redacted_hash: `event:${id}` };
  const evidence = { evidence_id: `evidence:${id}`, event_revision_id: event.event_revision_id, source_unit_ref: id, range: { start: 0, end: 4 }, excerpt: id, source_identity_ref: identity, speaker_rendering: null, source_local_mention_ref: id, state: "active" as const, source_trust: "test", policy_labels: [], source_independence_key: `capture:${id}` };
  const argument = reprojectable ? { slot_id: "subject", role: "subject", value: { kind: "source_local_ref" as const, ref: local } } : { slot_id: "subject", role: "subject", value: { kind: "literal" as const, value: id } };
  const provisional = { claim_lineage_id: `lineage:${id}`, claim_revision_id: `provisional:${id}`, owner_account_id: owner, predicate: "test_predicate", arguments: [argument], temporal_scope: { observed_at: "2026-01-01T00:00:00Z", precision: "instant" as const }, evidence_refs: [evidence.evidence_id], policy_labels: [], source_language: "en", scope: { locality: "source_local" as const, scope_ref: null }, lifecycle: "provisional" as const, ambiguity_markers: [], context_packet: { version: "v1", referent_refs: [], topic_refs: [] } };
  const { ambiguity_markers: _ambiguity, context_packet: _context, ...canonicalBase } = provisional;
  const canonical = { ...canonicalBase, claim_revision_id: `canonical:${id}`, temporal_scope: { ...provisional.temporal_scope, valid_time: temporal }, lifecycle: "canonical" as const, canonical_claim_id: `canonical:${id}`, source_provisional_revision_ids: [provisional.claim_revision_id] };
  // All fixture mentions share one surface so candidate blocking clusters
  // them; which of them actually merge is decided by the fake model's answer
  // and the deterministic gates, which is what these tests exercise.
  const mention = { mention_id: `mention:${id}`, owner_account_id: owner, claim_revision_id: provisional.claim_revision_id, span: { start: 0, end: 4 }, evidence_id: evidence.evidence_id, source_identity_ref: identity, speaker_rendering: null, slot_id: "subject", surface: "the recurring referent", antecedent_handle: null, resolution: "unresolved" as const, entity_id: null };
  return { event, evidence, provisional, canonical, mention };
};

const seed = async (ledger: SqliteLedger, claims: readonly ReturnType<typeof seedClaim>[]) => {
  const revisions: AtomicGraphTransition["revisions"] = claims.flatMap((item) => [
    { kind: "event" as const, revision_id: item.event.event_revision_id, event: item.event },
    { kind: "evidence" as const, revision_id: `evidence-revision:${item.evidence.evidence_id}`, evidence: item.evidence },
    { kind: "claim" as const, revision_id: item.provisional.claim_revision_id, claim: item.provisional, placement_status: "consumed" as const },
    { kind: "claim" as const, revision_id: item.canonical.claim_revision_id, claim: item.canonical, placement_status: "canonical" as const },
    { kind: "mention" as const, revision_id: `mention-revision:${item.mention.mention_id}`, mention: item.mention },
  ]);
  const derivation = prepareDerivation({ attempt_id: "seed-attempt", commit_id: "seed", owner_account_id: owner, parent_commit: null, idempotency_key: "seed", input_revisions: [], output_revisions: revisions.map((revision) => ({ revision_id: revision.revision_id, content: revision.kind === "event" ? revision.event : revision.kind === "evidence" ? revision.evidence : revision.kind === "claim" ? revision.claim : revision.mention })), versions, success_kind: "success" });
  await ledger.appendTransitionPlan({ placement: { offline_experiment: true, allocations: Object.fromEntries(claims.map((item) => [item.provisional.claim_revision_id, item.canonical.claim_revision_id])), results: claims.map((item) => ({ input_provisional_revision_id: item.provisional.claim_revision_id, disposition: "admit" as const, operation: null })) }, derivation, revisions, adjacency: [], artifacts: claims.map((item) => ({ artifact_id: `auto-placement:${item.provisional.claim_revision_id}`, kind: "auto_placement_log" as const, provisional_revision_id: item.provisional.claim_revision_id, canonical_claim_revision_id: item.canonical.claim_revision_id, margin: null, risk_markers: [], unit_boundary_decision: "accept_ltm" as const, scope_locality: "source_local" as const })) });
};

test("P1 two formation works retain distinct grounded mentions in one ledger", async () => {
  const ledger = new SqliteLedger(new Database(":memory:"));
  const raw_mention_id = "mention:e:uses:0:candidate:1:subject";
  const leftBase = seedClaim("grounded-work-left", true);
  const rightBase = seedClaim("grounded-work-right", true);
  const left = { ...leftBase, mention: { ...leftBase.mention, mention_id: groundedFormationMentionId({ owner_account_id: owner, session_id: "same-session", work_id: "work:left", raw_mention_id }) } };
  const right = { ...rightBase, mention: { ...rightBase.mention, mention_id: groundedFormationMentionId({ owner_account_id: owner, session_id: "same-session", work_id: "work:right", raw_mention_id }) } };
  await seed(ledger, [left, right]);
  expect(ledger.mentions(owner).map((mention) => mention.mention_id).sort()).toEqual([left.mention.mention_id, right.mention.mention_id].sort());
});

const dreamModel = (cycleId: string, groups: readonly (readonly string[])[], overrides: {
  boundary?: "accept_ltm" | "abstain";
  scopeLocality?: "durable" | "source_local" | null;
  onBoundary?: () => void;
  predicateAssertions?: readonly { predicate_id: string; target_predicate_id: string }[];
  onPredicate?: () => void;
} = {}) => new DeterministicFakeModel((request) => {
  if (request.strategy === "identity-adjudication") return { partition_hash: cycleId, same_groups: groups, uncertain_pairs: [] };
  if (request.strategy === "identity-verification") return { verdict: "same", who: "the recurring referent" };
  if (request.strategy === "identity-naming-check") return { names_specific_referent: true };
  if (request.strategy === "speaker-self-reference") return { self_referring: ((request.input as { phrases?: readonly string[] }).phrases ?? []).map(() => true) };
  if (request.strategy === "stm-ltm-unit-boundary") {
    overrides.onBoundary?.();
    return overrides.boundary === "abstain" ? { decision: "abstain", reason: "fixture abstain" } : { decision: "accept_ltm" };
  }
  if (request.strategy === "scope-role-binding") {
    return overrides.scopeLocality === null
      ? { bindings: {}, scope: null }
      : { bindings: {}, scope: { locality: overrides.scopeLocality ?? "durable", scope_ref: "fixture:scope" } };
  }
  if (request.strategy === "predicate-alignment") {
    overrides.onPredicate?.();
    return { assertions: overrides.predicateAssertions ?? [] };
  }
  return { assertions: [] };
});

const cycle = (db: Database, ledger: SqliteLedger, cycleId: string, groups: readonly (readonly string[])[]) => runSqliteDreamCycle({
  db, ledger, owner_account_id: owner, stm_items: [], stm_mentions: [], cycle_id: cycleId, trigger_kind: "idle",
  model: dreamModel(cycleId, groups),
});

test("dream commits a reprojectable merge atomically and reaches its claim from the durable entity", async () => {
  const db = new Database(":memory:"), ledger = new SqliteLedger(db);
  const left = seedClaim("good-left", true), right = seedClaim("good-right", true);
  await seed(ledger, [left, right]);

  const report = await cycle(db, ledger, "good", [[left.mention.mention_id, right.mention.mention_id]]);
  expect(report).toMatchObject({ committed_merges: 1, reprojected: 2, skipped_merges: [] });
  const snapshot = ledger.snapshot(owner), entity = snapshot.entities[0]!.entity.entity_id;
  const result = walk(project(snapshot, { reader_account_id: owner, grant: { grant_id: "owner", policy_classes: [] } }), { anchor: `entity:${entity}`, max_hops: 2, relation_kinds: ["entity-shared"] });
  expect(result.paths.some((path) => path.nodes.some((node) => node.startsWith("claim:reprojected:")))).toBe(true);
  expect(db.query("SELECT COUNT(*) AS count FROM derivation_commits WHERE commit_id LIKE 'dream-merge:%'").get() as { count: number }).toEqual({ count: 1 });
  const commits = db.query("SELECT commit_id FROM entity_revisions WHERE commit_id LIKE 'dream-merge:%' UNION SELECT commit_id FROM identity_authorization_revisions WHERE commit_id LIKE 'dream-merge:%' UNION SELECT commit_id FROM identity_revisions WHERE commit_id LIKE 'dream-merge:%' UNION SELECT commit_id FROM mention_revisions WHERE commit_id LIKE 'dream-merge:%' UNION SELECT commit_id FROM claim_revisions WHERE commit_id LIKE 'dream-merge:%' UNION SELECT commit_id FROM generated_adjacency WHERE commit_id LIKE 'dream-merge:%'").all() as { commit_id: string }[];
  expect(commits).toHaveLength(1);
  expect(db.query("SELECT COUNT(*) AS count FROM candidate_derivation_artifacts WHERE commit_id LIKE 'dream-merge:%'").get()).toEqual({ count: 2 });
});

test("dream refuses a same-claim proposal and commits no merge", async () => {
  const db = new Database(":memory:"), ledger = new SqliteLedger(db);
  const left = seedClaim("same-claim-left", true), rightBase = seedClaim("same-claim-right", true);
  // Two distinct source-local slots may never be identity candidates merely
  // because a model placed them in the same partition.
  const right = { ...rightBase, mention: { ...rightBase.mention, claim_revision_id: left.provisional.claim_revision_id } };
  await seed(ledger, [left, right]);

  const report = await cycle(db, ledger, "same-claim", [[left.mention.mention_id, right.mention.mention_id]]);
  expect(report).toMatchObject({ committed_merges: 0, skipped_merges: [{ reason: "same_claim_revision_id", retryable: false }] });
  expect(ledger.snapshot(owner).entities).toEqual([]);
  expect(db.query("SELECT COUNT(*) AS count FROM derivation_commits WHERE commit_id LIKE 'dream-merge:%'").get()).toEqual({ count: 0 });
});

test("dream refuses a proposed merge whose support roots are not independent", async () => {
  const db = new Database(":memory:"), ledger = new SqliteLedger(db);
  const left = seedClaim("shared-root-left", true), rightBase = seedClaim("shared-root-right", true);
  const right = { ...rightBase, evidence: { ...rightBase.evidence, source_independence_key: left.evidence.source_independence_key } };
  await seed(ledger, [left, right]);

  const report = await cycle(db, ledger, "shared-root", [[left.mention.mention_id, right.mention.mention_id]]);
  expect(report).toMatchObject({ committed_merges: 0, skipped_merges: [{ reason: "non_independent_support_set" }] });
  expect(ledger.snapshot(owner).entities).toEqual([]);
});

test("dream skips a merge without a reprojectable claim and records why", async () => {
  const db = new Database(":memory:"), ledger = new SqliteLedger(db);
  const left = seedClaim("bad-left", false), right = seedClaim("bad-right", false);
  await seed(ledger, [left, right]);

  const report = await cycle(db, ledger, "bad", [[left.mention.mention_id, right.mention.mention_id]]);
  expect(report).toMatchObject({ committed_merges: 0, reprojected: 0, skipped_merges: [{ reason: "no_reprojectable_canonical_claim" }] });
  expect(ledger.snapshot(owner).entities).toEqual([]);
  // The audit table persists ids+reason; the in-memory retryable bit is report-only.
  expect(new SqliteDreamStore(db).mergeSkips("bad", owner)).toEqual(report.skipped_merges.map(({ group_mention_ids, reason }) => ({ group_mention_ids, reason })));
});

test("dream commits the good merge and skips the bad merge in one cycle", async () => {
  const db = new Database(":memory:"), ledger = new SqliteLedger(db);
  const goodLeft = seedClaim("mixed-good-left", true), goodRight = seedClaim("mixed-good-right", true), badLeft = seedClaim("mixed-bad-left", false), badRight = seedClaim("mixed-bad-right", false);
  await seed(ledger, [goodLeft, goodRight, badLeft, badRight]);

  const report = await cycle(db, ledger, "mixed", [[goodLeft.mention.mention_id, goodRight.mention.mention_id], [badLeft.mention.mention_id, badRight.mention.mention_id]]);
  expect(report).toMatchObject({ committed_merges: 1, reprojected: 2, skipped_merges: [{ reason: "no_reprojectable_canonical_claim" }] });
  expect(ledger.snapshot(owner).entities).toHaveLength(1);
});

test("dream commits each of multiple adjudicated merges in its own atomic transition", async () => {
  const db = new Database(":memory:"), ledger = new SqliteLedger(db);
  const a = seedClaim("multi-a", true), b = seedClaim("multi-b", true), c = seedClaim("multi-c", true), d = seedClaim("multi-d", true);
  await seed(ledger, [a, b, c, d]);

  const report = await cycle(db, ledger, "multiple", [[a.mention.mention_id, b.mention.mention_id], [c.mention.mention_id, d.mention.mention_id]]);
  expect(report).toMatchObject({ committed_merges: 2, reprojected: 4, skipped_merges: [] });
  expect(ledger.snapshot(owner).entities).toHaveLength(2);
  expect(db.query("SELECT COUNT(*) AS count FROM derivation_commits WHERE commit_id LIKE 'dream-merge:%'").get() as { count: number }).toEqual({ count: 2 });
});

test("a claim bound in an earlier cycle can be reprojected again: carried authority replays as witnesses", async () => {
  const db = new Database(":memory:"), ledger = new SqliteLedger(db);
  // One claim with TWO source-local slots, each merging in a DIFFERENT cycle.
  const base = seedClaim("carried-x", true);
  const objectLocal = "source-local:carried-x-object";
  const withObject = {
    ...base,
    provisional: { ...base.provisional, arguments: [...base.provisional.arguments, { slot_id: "object", role: "object", value: { kind: "source_local_ref" as const, ref: objectLocal } }] },
    canonical: { ...base.canonical, arguments: [...base.canonical.arguments, { slot_id: "object", role: "object", value: { kind: "source_local_ref" as const, ref: objectLocal } }] },
  };
  const objectMention = { ...base.mention, mention_id: "mention:carried-x-object", slot_id: "object", source_identity_ref: { ...base.mention.source_identity_ref!, local_key: "carried-x-object" } };
  const partnerA = seedClaim("carried-a", true), partnerB = seedClaim("carried-b", true);
  await seed(ledger, [withObject, partnerA, partnerB]);
  const head = ledger.graphHead(owner);
  const derivation = prepareDerivation({ attempt_id: "carried-object-mention", commit_id: "carried-object-mention", owner_account_id: owner, parent_commit: head?.commit_id ?? null, idempotency_key: "carried-object-mention", input_revisions: [], output_revisions: [{ revision_id: `mention-revision:${objectMention.mention_id}`, content: objectMention }], versions, success_kind: "success" });
  await ledger.appendTransitionPlan({ placement: { offline_experiment: true, allocations: {}, results: [] }, derivation, revisions: [{ kind: "mention", revision_id: `mention-revision:${objectMention.mention_id}`, mention: objectMention }], adjacency: [], artifacts: [] });

  const first = await cycle(db, ledger, "carried-1", [[withObject.mention.mention_id, partnerA.mention.mention_id]]);
  expect(first).toMatchObject({ committed_merges: 1 });
  const second = await cycle(db, ledger, "carried-2", [[objectMention.mention_id, partnerB.mention.mention_id]]);
  expect(second).toMatchObject({ committed_merges: 1, skipped_merges: [] });

  // The live head of the twice-reprojected claim carries BOTH entity bindings.
  const snapshot = ledger.snapshot(owner);
  expect(snapshot.entities).toHaveLength(2);
  const heads = snapshot.claims.filter((item) => item.claim.lifecycle === "canonical" && item.claim.claim_lineage_id === withObject.canonical.claim_lineage_id && item.claim.arguments.every((argument) => argument.value.kind === "entity_ref"));
  expect(heads.length).toBeGreaterThanOrEqual(1);
});

/** A transition that writes nothing and exists only to carry a witness set. */
const witnessPlan = (ledger: SqliteLedger, key: string, committed: readonly GraphRevision[]): AtomicGraphTransition => {
  const head = ledger.graphHead(owner);
  return {
    placement: { offline_experiment: true, allocations: {}, results: [] },
    derivation: prepareDerivation({ attempt_id: `${key}-attempt`, commit_id: key, owner_account_id: owner, parent_commit: head?.commit_id ?? null, idempotency_key: key, input_revisions: [], output_revisions: [], versions, success_kind: "successful_empty" }),
    revisions: [], adjacency: [], artifacts: [], committed_revisions: committed,
  };
};

const mergedOnce = async (db: Database, ledger: SqliteLedger, name: string) => {
  const left = seedClaim(`${name}-left`, true), right = seedClaim(`${name}-right`, true);
  await seed(ledger, [left, right]);
  expect(await cycle(db, ledger, name, [[left.mention.mention_id, right.mention.mention_id]])).toMatchObject({ committed_merges: 1 });
  return ledger.snapshot(owner).identity_authorizations![0]!;
};

test("the storage boundary refuses a forged or tampered witnessed authorization", async () => {
  const db = new Database(":memory:"), ledger = new SqliteLedger(db);
  const committed = await mergedOnce(db, ledger, "forge");

  // Never committed at all. Its own lifecycle field says "active", which is
  // exactly why core cannot be the one to check it.
  const forged = { ...committed.authorization, authorization_id: `${committed.authorization.authorization_id}:forged` };
  await expect(ledger.appendTransitionPlan(witnessPlan(ledger, "forged-witness", [{ kind: "identity_authorization", revision_id: `identity-authorization:${forged.authorization_id}`, authorization: forged }])))
    .rejects.toThrow(/witnessed revision is not committed: identity-authorization:.*:forged/);

  // A real revision id carrying content the durable row never authorized.
  const tampered = { ...committed.authorization, endpoints: [committed.authorization.endpoints[0], { kind: "entity", entity_id: "entity:attacker" }] };
  await expect(ledger.appendTransitionPlan(witnessPlan(ledger, "tampered-witness", [{ kind: "identity_authorization", revision_id: committed.revision_id, authorization: tampered }])))
    .rejects.toThrow(/witnessed revision does not match its committed content/);

  // Lineage witnesses are checked for existence too, so a fabricated mention
  // cannot supply the typed lineage a role binding needs.
  const invented = { ...ledger.snapshot(owner).mentions![0]!.mention, mention_id: "mention:invented" };
  await expect(ledger.appendTransitionPlan(witnessPlan(ledger, "invented-mention-witness", [{ kind: "mention", revision_id: "mention-revision:mention:invented", mention: invented }])))
    .rejects.toThrow(/witnessed revision is not committed: mention-revision:mention:invented/);
});

test("the storage boundary refuses a witnessed authorization that a later revision superseded", async () => {
  const db = new Database(":memory:"), ledger = new SqliteLedger(db);
  const committed = await mergedOnce(db, ledger, "stale");

  // Stands in for a later revocation/supersession commit: what matters to the
  // witness check is that the authorization_id now has a newer head revision.
  const superseding = { ...committed.authorization, lifecycle: "superseded", superseded_by: `${committed.revision_id}:r2` };
  db.query("INSERT INTO identity_authorization_revisions VALUES (?, ?, ?, ?, ?, ?, ?)")
    .run(`${committed.revision_id}:r2`, owner, canonicalizeRedacted(superseding), sha256CanonicalRedacted(superseding), "supersession", committed.authorization.authorization_id, "superseded");

  // The stale copy still says "active" about itself; storage says otherwise.
  await expect(ledger.appendTransitionPlan(witnessPlan(ledger, "stale-witness", [{ kind: "identity_authorization", revision_id: committed.revision_id, authorization: committed.authorization }])))
    .rejects.toThrow(/witnessed identity authorization is not the durable head/);
});

test("a late member joins an established entity on a single new independent binding", async () => {
  const db = new Database(":memory:"), ledger = new SqliteLedger(db);
  const a = seedClaim("late-a", true), b = seedClaim("late-b", true), c = seedClaim("late-c", true);
  await seed(ledger, [a, b, c]);

  expect(await cycle(db, ledger, "late-1", [[a.mention.mention_id, b.mention.mention_id]])).toMatchObject({ committed_merges: 1 });
  const entityId = ledger.snapshot(owner).entities[0]!.entity.entity_id;

  // A's mention is already bound, so this group yields ONE new binding. The
  // entity is still corroborated by two independent source roots (A's and C's),
  // which is the question admission actually asks.
  const second = await cycle(db, ledger, "late-2", [[a.mention.mention_id, c.mention.mention_id]]);
  expect(second.committed_merges).toBe(1);
  expect(second.skipped_merges.map((item) => item.reason)).not.toContain("non_independent_support_set");
  const snapshot = ledger.snapshot(owner);
  expect(snapshot.entities).toHaveLength(1);
  expect(snapshot.mentions!.find((item) => item.mention.mention_id === c.mention.mention_id)!.mention.entity_id).toBe(entityId);
});

test("a partition whose only failures are retryable is not recorded as processed and re-adjudicates next cycle", async () => {
  const db = new Database(":memory:"), ledger = new SqliteLedger(db);
  const left = seedClaim("retry-left", false), right = seedClaim("retry-right", false);
  await seed(ledger, [left, right]);
  const first = await cycle(db, ledger, "retry-1", [[left.mention.mention_id, right.mention.mention_id]]);
  expect(first).toMatchObject({ committed_merges: 0, skipped_merges: [{ reason: "no_reprojectable_canonical_claim" }] });
  expect(db.query("SELECT COUNT(*) AS count FROM dream_partition_history").get()).toEqual({ count: 0 });
  // Before the fix the partition was recorded BEFORE the merge loop, so this
  // second, identical proposal was suppressed as a repeat: the retryable skip
  // vanished and the group could never become admissible even after its claim
  // became reprojectable.
  const second = await cycle(db, ledger, "retry-2", [[left.mention.mention_id, right.mention.mention_id]]);
  expect(second).toMatchObject({ committed_merges: 0, skipped_merges: [{ reason: "no_reprojectable_canonical_claim" }] });
});

test("a dream cycle stamps the adjudicating model's identity into its derivation commits", async () => {
  const db = new Database(":memory:"), ledger = new SqliteLedger(db);
  const left = seedClaim("provenance-left", true), right = seedClaim("provenance-right", true);
  await seed(ledger, [left, right]);
  const adjudicate = (cycleId: string) => new DeterministicFakeModel((request) => request.strategy === "identity-adjudication" ? { partition_hash: cycleId, same_groups: [[left.mention.mention_id, right.mention.mention_id]], uncertain_pairs: [] } : request.strategy === "identity-verification" ? { verdict: "same", who: "the recurring referent" } : request.strategy === "identity-naming-check" ? { names_specific_referent: true } : request.strategy === "speaker-self-reference" ? { self_referring: ((request.input as { phrases?: readonly string[] }).phrases ?? []).map(() => true) } : { assertions: [] });

  const report = await runSqliteDreamCycle({ db, ledger, owner_account_id: owner, stm_items: [], stm_mentions: [], cycle_id: "provenance-live", trigger_kind: "volume", model: adjudicate("provenance-live"), model_version: "glm-4.7" });
  expect(report.committed_merges).toBe(1);
  const commits = db.query("SELECT record_json FROM derivation_commits WHERE commit_id LIKE 'dream-%'").all() as { record_json: string }[];
  expect(commits.length).toBeGreaterThan(0);
  for (const commit of commits) {
    expect(commit.record_json).toContain("glm-4.7");
    expect(commit.record_json).not.toContain("deterministic-fake-v1");
  }
});

test("a dream cycle without an explicit model identity keeps the deterministic default", async () => {
  const db = new Database(":memory:"), ledger = new SqliteLedger(db);
  const left = seedClaim("provenance-default-left", true), right = seedClaim("provenance-default-right", true);
  await seed(ledger, [left, right]);
  await cycle(db, ledger, "provenance-default", [[left.mention.mention_id, right.mention.mention_id]]);
  const commits = db.query("SELECT record_json FROM derivation_commits WHERE commit_id LIKE 'dream-%'").all() as { record_json: string }[];
  expect(commits.length).toBeGreaterThan(0);
  for (const commit of commits) expect(commit.record_json).toContain("deterministic-fake-v1");
});

test("a terminally processed partition is recorded, preserving the variance guard", async () => {
  const db = new Database(":memory:"), ledger = new SqliteLedger(db);
  const left = seedClaim("terminal-left", true), right = seedClaim("terminal-right", true);
  await seed(ledger, [left, right]);
  const report = await cycle(db, ledger, "terminal-1", [[left.mention.mention_id, right.mention.mention_id]]);
  expect(report).toMatchObject({ committed_merges: 1, skipped_merges: [] });
  expect(db.query("SELECT COUNT(*) AS count FROM dream_partition_history").get()).toEqual({ count: 1 });
});

const stmItem = (id: string, overrides: {
  labels?: readonly string[];
  source_trust?: string;
  observed_speaker_slot_id?: string | null;
  local_key?: string;
  predicate?: string;
  predicate_id?: string;
} = {}) => {
  const base = seedClaim(id, false);
  const evidence = { ...base.evidence, source_trust: overrides.source_trust ?? "test", source_identity_ref: { ...base.evidence.source_identity_ref!, local_key: overrides.local_key ?? base.evidence.source_identity_ref!.local_key } };
  const claim = {
    ...base.provisional,
    predicate: overrides.predicate ?? base.provisional.predicate,
    predicate_id: overrides.predicate_id ?? predicateIdForName(overrides.predicate ?? base.provisional.predicate),
    policy_labels: [...(overrides.labels ?? [])],
    observed_speaker_slot_id: overrides.observed_speaker_slot_id === undefined ? "subject" : overrides.observed_speaker_slot_id,
    evidence_refs: [evidence.evidence_id],
  };
  return {
    id: claim.claim_revision_id,
    session_id: `session:${id}`,
    event_time_watermark: "2026-01-01T00:00:00Z",
    capture_sequence: 0,
    revision_lineage: "r1",
    ingest_sequence: 0,
    entity_refs: [],
    lexical_terms: [id],
    vector_key: id,
    predicate_id: claim.predicate,
    bytes: 32,
    claim,
    evidence: [evidence],
    argument_origins: { subject: "independent" as const },
    settled_window_id: "w1",
  };
};

const promoteCycle = (db: Database, ledger: SqliteLedger, cycleId: string, items: readonly ReturnType<typeof stmItem>[], overrides: Parameters<typeof dreamModel>[2] = {}) =>
  runSqliteDreamCycle({
    db, ledger, owner_account_id: owner, stm_items: items, stm_mentions: [], cycle_id: cycleId, trigger_kind: "end_of_stream",
    model: dreamModel(cycleId, [], overrides),
  });

test("promotion defers on boundary abstain and consumes the STM item once", async () => {
  const db = new Database(":memory:"), ledger = new SqliteLedger(db);
  const item = stmItem("boundary-abstain", { labels: ["subject:owner"] });
  let boundaryCalls = 0;
  const first = await promoteCycle(db, ledger, "promo-abstain-1", [item], { boundary: "abstain", onBoundary: () => { boundaryCalls += 1; } });
  expect(first).toMatchObject({ promoted: 0, deferred: [item.id] });
  expect(ledger.isProvisionalConsumed(item.claim.claim_revision_id)).toBe(true);
  expect(boundaryCalls).toBe(1);

  const second = await promoteCycle(db, ledger, "promo-abstain-2", [item], { boundary: "accept_ltm", onBoundary: () => { boundaryCalls += 1; } });
  expect(second.promoted).toBe(0);
  expect(boundaryCalls).toBe(1);
  expect(db.query("SELECT COUNT(*) AS count FROM derivation_commits WHERE idempotency_key = ?").get(`dream-promotion:${owner}:${item.id}`)).toEqual({ count: 1 });
});

test("promotion admits owner + accept_ltm + durable scope", async () => {
  const db = new Database(":memory:"), ledger = new SqliteLedger(db);
  const item = stmItem("promo-admit", { labels: ["subject:owner"] });
  const report = await promoteCycle(db, ledger, "promo-admit-1", [item], { boundary: "accept_ltm", scopeLocality: "durable" });
  expect(report).toMatchObject({ promoted: 1, deferred: [] });
  const snapshot = ledger.snapshot(owner);
  expect(snapshot.claims.some((row) => row.claim.lifecycle === "canonical" && row.claim.source_provisional_revision_ids.includes(item.claim.claim_revision_id))).toBe(true);
  expect(snapshot.predicates?.map((row) => row.predicate)).toEqual([
    expect.objectContaining({ predicate_id: predicateIdForName(item.claim.predicate), identity_version: "name-v2", slot_ids: [], observed_roles: ["subject"] }),
  ]);
});

test("promotion preserves queued legacy predicate identity for later migration", async () => {
  const db = new Database(":memory:"), ledger = new SqliteLedger(db);
  const item = stmItem("promo-legacy-predicate", {
    labels: ["subject:owner"],
    predicate: "legacy relation",
    predicate_id: "predicate:legacy-name-plus-window-slots",
  });
  await promoteCycle(db, ledger, "promo-legacy-predicate", [item], { boundary: "accept_ltm", scopeLocality: "durable" });
  expect(ledger.snapshot(owner).predicates?.map((row) => row.predicate)).toEqual([
    expect.objectContaining({
      predicate_id: "predicate:legacy-name-plus-window-slots",
      identity_version: "name-slots-v1",
      slot_ids: ["subject"],
    }),
  ]);
  await promoteCycle(db, ledger, "promo-legacy-predicate-audit", [], {});
  expect(db.query("SELECT code FROM dream_predicate_exclusions").all()).toEqual([{ code: "legacy_identity_version" }]);
});

test("predicate batches settle only after their exact graph result is durable", async () => {
  const db = new Database(":memory:"), ledger = new SqliteLedger(db);
  const alpha = stmItem("predicate-alpha", { labels: ["subject:owner"], predicate: "alpha relation" });
  const bravo = stmItem("predicate-bravo", { labels: ["subject:owner"], predicate: "bravo relation" });
  await promoteCycle(db, ledger, "predicate-promotion", [alpha, bravo], { boundary: "accept_ltm", scopeLocality: "durable" });

  let predicateCalls = 0;
  const predicateAssertions = [{
    predicate_id: predicateIdForName("alpha relation"),
    target_predicate_id: predicateIdForName("bravo relation"),
  }];
  const runAlignment = (cycleId: string) => runSqliteDreamCycle({
    db,
    ledger,
    owner_account_id: owner,
    stm_items: [],
    stm_mentions: [],
    cycle_id: cycleId,
    trigger_kind: "idle",
    model: dreamModel(cycleId, [], { predicateAssertions, onPredicate: () => { predicateCalls += 1; } }),
  });
  await runAlignment("predicate-align-1");
  expect(predicateCalls).toBe(1);
  expect(ledger.snapshot(owner).predicate_assertions).toHaveLength(1);
  expect(db.query("SELECT kind, response_digest, result_digest, error_code FROM dream_predicate_batch_outcomes").all()).toEqual([{
    kind: "success",
    response_digest: expect.any(String),
    result_digest: expect.any(String),
    error_code: null,
  }]);
  expect(db.query("SELECT COUNT(*) AS count FROM dream_settled_predicate_batches").get()).toEqual({ count: 1 });

  // Simulate a process crash after the graph append but before the QA audit
  // and settlement transaction. The exact result must replay through the
  // graph idempotency key, restore settlement, and never duplicate an alias.
  db.exec("DELETE FROM dream_settled_predicate_batches; DELETE FROM dream_predicate_batch_outcomes;");
  await runAlignment("predicate-align-crash-resume");
  expect(predicateCalls).toBe(2);
  expect(ledger.snapshot(owner).predicate_assertions).toHaveLength(1);
  expect(db.query("SELECT COUNT(*) AS count FROM dream_settled_predicate_batches").get()).toEqual({ count: 1 });

  // The assertion commit does not change the vocabulary frontier, so the
  // exact settled question is skipped instead of asking itself forever.
  await runAlignment("predicate-align-2");
  expect(predicateCalls).toBe(2);
  expect(ledger.snapshot(owner).predicate_assertions).toHaveLength(1);
});

test("promotion defers bystander without calling boundary", async () => {
  const db = new Database(":memory:"), ledger = new SqliteLedger(db);
  const item = stmItem("promo-bystander", { labels: ["subject:bystander"] });
  let boundaryCalls = 0;
  const report = await promoteCycle(db, ledger, "promo-bystander-1", [item], { onBoundary: () => { boundaryCalls += 1; } });
  expect(report).toMatchObject({ promoted: 0, deferred: [item.id] });
  expect(boundaryCalls).toBe(0);
});

test("promotion admits trusted import without subject:owner", async () => {
  const db = new Database(":memory:"), ledger = new SqliteLedger(db);
  const item = stmItem("promo-trust", { labels: ["subject:generic"], source_trust: "user_asserted" });
  const report = await promoteCycle(db, ledger, "promo-trust-1", [item], { boundary: "accept_ltm", scopeLocality: "durable" });
  expect(report).toMatchObject({ promoted: 1, deferred: [] });
});

test("promotion defers when scope locality is source_local", async () => {
  const db = new Database(":memory:"), ledger = new SqliteLedger(db);
  const item = stmItem("promo-local", { labels: ["subject:owner"] });
  const report = await promoteCycle(db, ledger, "promo-local-1", [item], { boundary: "accept_ltm", scopeLocality: "source_local" });
  expect(report).toMatchObject({ promoted: 0, deferred: [item.id] });
});
