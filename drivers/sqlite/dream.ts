import { Database } from "bun:sqlite";
import { checkStmSufficiency } from "../../core/extract/provisional";
import { prepareDerivation, sha256CanonicalRedacted, type AtomicGraphTransition, type ClaimRevision, type GraphRevision } from "../../core/ledger";
import { endpointsMatch } from "../../core/resolve/identity-authority";
import { scanContradictions } from "../../core/consolidate/contradiction";
import { runDreamCycle } from "../../core/consolidate/dream";
import { invokeBlockedIdentityAdjudication } from "../../core/consolidate/identity";
import { validateAndAllocatePlacement } from "../../core/consolidate/plan";
import { reprojectBoundClaims, reprojectionWitnesses, type ReprojectionBinding } from "../../core/consolidate/reprojection";
import { invokePredicateAlignment } from "../../core/consolidate/relations";
import { diffGraphSnapshots, liveCommittedClaims, type GraphSnapshot } from "../../core/retrieve";
import type { Entity, IdentityAuthorization, IdentityConstraint, Mention } from "../../core/schema";
import { invokeScopeStrategy } from "../model/scope-edge";
import { invokeUnitBoundaryStrategy } from "../model/unit-boundary-edge";
import type { ModelPort } from "../model/port";
import type { DurableStmItem } from "./stm";
import { SqliteLedger } from "./index";

export const DEFAULT_DREAM_MODEL_VERSION = "deterministic-fake-v1";
export const TRUSTED_SOURCE_TRUST = new Set(["user_asserted", "imported_unverified"]);
// model_version is provenance, not decoration: a live-adjudicated commit must
// not claim the deterministic fake produced it.
const versionsFor = (model_version: string) => ({ strategy_version: "dream-consolidation-v1", model_version, prompt_version: "dream-v1", policy_version: "d50-v1", code_version: "dream-v1", schema_version: "stage-b2-v1", tokenizer_version: "none", tool_version: "dream-v1" });
const instant = (at: string) => ({ typed_expression: { kind: "absolute" as const, granularity: "instant" as const, value: at }, resolved_interval: { kind: "instant" as const, start: at, end: at, timezone: "UTC", granularity: "instant" as const }, derivation: { resolver_version: "dream-promotion-v1", timezone: "UTC" } });
const payload = (revision: GraphRevision) => revision.kind === "claim" ? revision.claim : revision.kind === "entity" ? revision.entity : revision.kind === "identity" ? revision.constraint : revision.kind === "identity_authorization" ? revision.authorization : revision.kind === "mention" ? revision.mention : revision.kind === "event" ? revision.event : revision.kind === "evidence" ? revision.evidence : revision.kind === "predicate" ? revision.predicate : revision.kind === "predicate_assertion" ? revision.assertion : revision.support;
const promotionIdempotencyKey = (owner: string, itemId: string) => `dream-promotion:${owner}:${itemId}`;
const passesSubjectOrTrust = (item: DurableStmItem): boolean =>
  item.claim.policy_labels.includes("subject:owner")
  || item.evidence.some((evidence) => TRUSTED_SOURCE_TRUST.has(evidence.source_trust));

/** retryable is set on freshly produced skips; rows re-read from the audit table omit it. */
export interface DreamMergeSkip { group_mention_ids: readonly string[]; reason: string; retryable?: boolean; }
export interface DreamCycleReport { cycle_id: string; promoted: number; deferred: readonly string[]; reprojected: number; committed_merges: number; skipped_merges: readonly DreamMergeSkip[]; trajectory: ReturnType<typeof diffGraphSnapshots>; }

/** The few dream records worth keeping across a run. */
export class SqliteDreamStore {
  constructor(readonly db: Database) { db.exec(`
    CREATE TABLE IF NOT EXISTS dream_cycles (cycle_id TEXT PRIMARY KEY, owner_account_id TEXT NOT NULL, trigger_kind TEXT NOT NULL, before_generation INTEGER NOT NULL, after_generation INTEGER NOT NULL, trajectory_json TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS dream_merge_skips (cycle_id TEXT NOT NULL, owner_account_id TEXT NOT NULL, group_key TEXT NOT NULL, reason TEXT NOT NULL, PRIMARY KEY(cycle_id, owner_account_id, group_key));
    CREATE TABLE IF NOT EXISTS dream_partition_history (owner_account_id TEXT NOT NULL, partition_hash TEXT NOT NULL, PRIMARY KEY(owner_account_id, partition_hash));
  `); }
  priorPartitions(owner: string): readonly string[] { return (this.db.query("SELECT partition_hash FROM dream_partition_history WHERE owner_account_id=? ORDER BY partition_hash").all(owner) as { partition_hash: string }[]).map((row) => row.partition_hash); }
  recordPartition(owner: string, hash: string): void { this.db.query("INSERT OR IGNORE INTO dream_partition_history VALUES (?, ?)").run(owner, hash); }
  recordMergeSkip(cycleId: string, owner: string, groupMentionIds: readonly string[], reason: string): void {
    this.db.query("INSERT OR REPLACE INTO dream_merge_skips VALUES (?, ?, ?, ?)").run(cycleId, owner, JSON.stringify([...groupMentionIds].sort()), reason);
  }
  mergeSkips(cycleId: string, owner: string): readonly DreamMergeSkip[] {
    return (this.db.query("SELECT group_key, reason FROM dream_merge_skips WHERE cycle_id=? AND owner_account_id=? ORDER BY group_key").all(cycleId, owner) as { group_key: string; reason: string }[])
      .map((row) => ({ group_mention_ids: JSON.parse(row.group_key) as string[], reason: row.reason }));
  }
  recordCycle(report: DreamCycleReport, owner: string, trigger: string, before: number, after: number): void { this.db.query("INSERT OR REPLACE INTO dream_cycles VALUES (?, ?, ?, ?, ?, ?)").run(report.cycle_id, owner, trigger, before, after, JSON.stringify(report.trajectory)); }
  trajectories(owner: string): readonly { cycle_id: string; trajectory: ReturnType<typeof diffGraphSnapshots> }[] { return (this.db.query("SELECT cycle_id, trajectory_json FROM dream_cycles WHERE owner_account_id=? ORDER BY cycle_id").all(owner) as { cycle_id: string; trajectory_json: string }[]).map((row) => ({ cycle_id: row.cycle_id, trajectory: JSON.parse(row.trajectory_json) })); }
}

const promotionTransition = async (input: {
  ledger: SqliteLedger;
  owner: string;
  items: readonly DurableStmItem[];
  cycleId: string;
  versions: ReturnType<typeof versionsFor>;
  model: ModelPort;
  entities: readonly Entity[];
}): Promise<{ promoted: number; deferred: readonly string[] }> => {
  let promoted = 0;
  const deferred: string[] = [];
  for (const item of input.items) {
    if (input.ledger.isProvisionalConsumed(item.claim.claim_revision_id)) {
      deferred.push(item.id);
      continue;
    }
    // Crash recovery: a prior cycle decided this item but died before STM drain.
    // Do not re-invoke models — the idempotency key has no cycle component.
    if (input.ledger.findCommitByIdempotencyKey(promotionIdempotencyKey(input.owner, item.id))) {
      deferred.push(item.id);
      continue;
    }

    const sufficient = checkStmSufficiency(item.claim, item.evidence, item.claim.arguments.map((argument) => argument.slot_id));
    let disposition: "admit" | "defer_review" = "defer_review";
    let trigger: "new_evidence" | "new_identity_evidence" | "boundary_reconsideration" | null = "new_evidence";
    let unitBoundaryDecision: "accept_ltm" | "abstain" = "abstain";
    let scopeLocality: "durable" | "source_local" | null = null;
    let riskMarkers: ("new_entity" | "resolved_pronoun" | "low_margin")[] = [];

    if (!sufficient.ok) {
      // gate 1
    } else if (!passesSubjectOrTrust(item)) {
      trigger = "new_identity_evidence";
    } else {
      try {
        const boundary = await invokeUnitBoundaryStrategy(input.model, item.claim, item.evidence);
        unitBoundaryDecision = boundary.decision;
        if (boundary.margin === "low") riskMarkers = ["low_margin"];
        if (boundary.decision !== "accept_ltm") {
          trigger = "boundary_reconsideration";
        } else {
          const scope = await invokeScopeStrategy(input.model, item.claim, input.entities, item.evidence);
          scopeLocality = scope.scope?.locality ?? null;
          if (scope.scope?.locality === "durable") {
            disposition = "admit";
            trigger = null;
          } else {
            trigger = "boundary_reconsideration";
          }
        }
      } catch (error) {
        // GlmModel already retried; leaving the item unconsumed would re-burn
        // the same failing call every subsequent cycle. One-shot defer instead.
        console.error(`dream promotion failed for ${item.id}: ${error instanceof Error ? error.message : error}`);
        trigger = "boundary_reconsideration";
        unitBoundaryDecision = "abstain";
      }
    }

    validateAndAllocatePlacement({
      batch_id: `${input.cycleId}:${item.id}`,
      leased_inputs: [{ provisional_revision_id: item.claim.claim_revision_id, entity_id: null, proposition_key: item.claim.proposition_key_raw ?? item.claim.predicate, proposition_key_resolved: item.claim.proposition_key_resolved, alias_frontier_generation: item.claim.predicate_alias_frontier, review_attempt: 0, max_review_attempts: 1 }],
      snapshot: [],
      results: [{ input_provisional_revision_id: item.claim.claim_revision_id, disposition, operation: null, ...(trigger ? { re_resolution_trigger: trigger } : {}) }],
    });
    const canonicalId = `canonical:promotion:${sha256CanonicalRedacted({ cycleId: input.cycleId, provisional: item.claim.claim_revision_id }).slice(0, 24)}`;
    const provisional: ClaimRevision = { kind: "claim", revision_id: item.claim.claim_revision_id, claim: item.claim, placement_status: disposition === "admit" ? "consumed" : "provisional_abstained" };
    const canonical = disposition === "admit" ? (() => {
      const { ambiguity_markers: _ambiguity, context_packet: _context, ...base } = item.claim;
      return { ...base, claim_revision_id: canonicalId, temporal_scope: { ...item.claim.temporal_scope, valid_time: instant(item.claim.temporal_scope.observed_at) }, lifecycle: "canonical" as const, canonical_claim_id: canonicalId, source_provisional_revision_ids: [item.claim.claim_revision_id], ...(scopeLocality ? { scope: { locality: scopeLocality, scope_ref: item.claim.scope.scope_ref } } : {}) };
    })() : null;
    const predicate = item.claim.predicate_id ? [{ kind: "predicate" as const, revision_id: `${item.claim.predicate_id}:initial`, predicate: { predicate_id: item.claim.predicate_id, owner_account_id: input.owner, predicate_revision_id: `${item.claim.predicate_id}:initial`, identity_name: item.claim.predicate, display_name: item.claim.predicate, lifecycle: "canonical" as const, slot_ids: item.claim.arguments.map((argument) => argument.slot_id).sort() } }] : [];
    const revisions: AtomicGraphTransition["revisions"] = [...predicate, provisional, ...(canonical ? [{ kind: "claim" as const, revision_id: canonicalId, claim: canonical, placement_status: "canonical" as const }] : [])];
    const head = input.ledger.graphHead(input.owner);
    const derivation = prepareDerivation({
      attempt_id: `dream-promotion-attempt:${input.cycleId}:${item.id}`,
      commit_id: `dream-promotion:${input.cycleId}:${item.id}`,
      owner_account_id: input.owner,
      parent_commit: head?.commit_id ?? null,
      idempotency_key: promotionIdempotencyKey(input.owner, item.id),
      input_revisions: [{ revision_id: item.claim.claim_revision_id, content: item.claim }],
      output_revisions: revisions.map((revision) => ({ revision_id: revision.revision_id, content: payload(revision) })),
      versions: input.versions,
      success_kind: canonical ? "success" : "successful_empty",
    });
    await input.ledger.appendTransitionPlan({
      placement: {
        offline_experiment: true,
        allocations: canonical ? { [item.claim.claim_revision_id]: canonicalId } : {},
        results: [{ input_provisional_revision_id: item.claim.claim_revision_id, disposition, operation: null, ...(trigger ? { re_resolution_trigger: trigger } : {}) }],
      },
      derivation,
      revisions,
      adjacency: [],
      artifacts: [{
        artifact_id: canonical ? `auto-placement:${item.claim.claim_revision_id}` : `abstention-set:${item.claim.claim_revision_id}`,
        kind: canonical ? "auto_placement_log" : "abstention_set",
        provisional_revision_id: item.claim.claim_revision_id,
        canonical_claim_revision_id: canonical ? canonicalId : null,
        margin: null,
        risk_markers: riskMarkers,
        unit_boundary_decision: unitBoundaryDecision,
        scope_locality: scopeLocality,
      }],
    });
    if (canonical) promoted++;
    else deferred.push(item.id);
  }
  return { promoted, deferred };
};

const supportFor = (snapshot: GraphSnapshot, mention: Mention): import("../../core/resolve/identity-authority").ImmutableIdentitySupport | null => {
  const claim = snapshot.claims.find((item) => item.revision_id === mention.claim_revision_id);
  const evidenceId = claim?.claim.evidence_refs[0];
  const evidence = snapshot.evidence?.find((item) => item.evidence.evidence_id === evidenceId);
  return claim && evidence ? { support_ref: `support:${mention.mention_id}:${claim.revision_id}`, owner_account_id: snapshot.owner_account_id, claim_revision_id: claim.revision_id, evidence_ref: evidence.revision_id, source_independence_key: evidence.evidence.source_independence_key, support_origin: "independent" } : null;
};

export const runSqliteDreamCycle = async (input: { db: Database; ledger: SqliteLedger; owner_account_id: string; stm_items: readonly DurableStmItem[]; stm_mentions: readonly Mention[]; model: ModelPort; cycle_id: string; trigger_kind: "volume" | "idle" | "end_of_stream"; model_version?: string; max_reprojection_claims?: number }): Promise<DreamCycleReport> => {
  const state = new SqliteDreamStore(input.db);
  const versions = versionsFor(input.model_version ?? DEFAULT_DREAM_MODEL_VERSION);
    const before = input.ledger.snapshot(input.owner_account_id);
    // One pass follows doc 45's order. New STM work is promoted only after
    // adjudication has examined the committed frontier; it becomes eligible
    // for the next cycle rather than being smuggled into this proposal.
    // `snapshot.claims` is the append-only revision list, so a reprojected claim
    // and the predecessor it superseded are both in it. Scanning both makes one
    // memory contradict or corroborate itself. `liveCommittedClaims` is D35's
    // single head-selection authority; contradiction reads it, not the raw list.
    const facts = liveCommittedClaims(before).flatMap((item) => item.claim.arguments.filter((argument) => argument.value.kind === "entity_ref").map((argument) => ({ claim_revision_id: item.revision_id, entity_id: argument.value.kind === "entity_ref" ? argument.value.ref : "", proposition_key_resolved: item.claim.proposition_key_resolved ?? item.claim.predicate, polarity: item.claim.polarity, valid_time: item.claim.lifecycle === "canonical" ? { start: item.claim.temporal_scope.valid_time.resolved_interval.start, end: item.claim.temporal_scope.valid_time.resolved_interval.end } : null })));
    const contradictions = scanContradictions(facts);
    // Blocked + batched: each adjudication call stays under a fixed payload
    // budget, so the prompt no longer grows with the whole ledger (the first
    // real corpus run lost its later cycles to exactly that).
    const proposal = await invokeBlockedIdentityAdjudication(input.model, { mentions: (before.mentions ?? []).map((item) => item.mention), claims: before.claims, evidence: before.evidence ?? [], events: before.events ?? [] });
    const predicateAssertions = await invokePredicateAlignment(input.model, (before.predicates ?? []).map((item) => item.predicate), String(before.graph_generation ?? 0));
    const gate = runDreamCycle({ cycle_id: input.cycle_id, facts, previous_split_keys: contradictions.map((item) => `${item.entity_id}:${item.claim_revision_ids.join(":")}`), proposals: [{ proposal_id: proposal.partition_hash, partition_hash: proposal.partition_hash, prior_partition_hash: state.priorPartitions(input.owner_account_id).includes(proposal.partition_hash) ? proposal.partition_hash : undefined, new_evidence: true }] });
    // Promotion is content-gated (sufficiency → subject/trust → boundary →
    // durable scope) and intentionally not identity-gated: unresolved
    // source-local arguments become canonical inputs for the next merge cycle.
    const promotion = await promotionTransition({
      ledger: input.ledger,
      owner: input.owner_account_id,
      items: input.stm_items,
      cycleId: input.cycle_id,
      versions,
      model: input.model,
      entities: (before.entities ?? []).map((item) => item.entity),
    });
    const promoted = promotion.promoted;
    const deferred = promotion.deferred;
    let afterPromotion = input.ledger.snapshot(input.owner_account_id);
    const missingMentions = input.stm_mentions.filter((mention) => !(afterPromotion.mentions ?? []).some((stored) => stored.mention.mention_id === mention.mention_id));
    if (missingMentions.length) {
      const head = input.ledger.graphHead(input.owner_account_id);
      const revisions = missingMentions.map((mention) => ({ kind: "mention" as const, revision_id: `mention:${mention.mention_id}`, mention }));
      const derivation = prepareDerivation({ attempt_id: `dream-mentions-attempt:${input.cycle_id}`, commit_id: `dream-mentions:${input.cycle_id}`, owner_account_id: input.owner_account_id, parent_commit: head?.commit_id ?? null, idempotency_key: `dream-mentions:${input.owner_account_id}:${input.cycle_id}`, input_revisions: missingMentions.map((mention) => ({ revision_id: mention.mention_id, content: mention })), output_revisions: revisions.map((revision) => ({ revision_id: revision.revision_id, content: revision.mention })), versions, success_kind: "success" });
      await input.ledger.appendTransitionPlan({ placement: { offline_experiment: true, allocations: {}, results: [] }, derivation, revisions, adjacency: [], artifacts: [] });
      afterPromotion = input.ledger.snapshot(input.owner_account_id);
    }
    if (predicateAssertions.length) {
      const revisions: AtomicGraphTransition["revisions"] = predicateAssertions.map((assertion) => ({ kind: "predicate_assertion" as const, revision_id: `predicate-assertion:${assertion.assertion_id}`, assertion }));
      const head = input.ledger.graphHead(input.owner_account_id);
      const derivation = prepareDerivation({ attempt_id: `dream-predicate-attempt:${input.cycle_id}`, commit_id: `dream-predicate:${input.cycle_id}`, owner_account_id: input.owner_account_id, parent_commit: head?.commit_id ?? null, idempotency_key: `dream-predicate:${input.owner_account_id}:${input.cycle_id}`, input_revisions: [], output_revisions: revisions.map((revision) => ({ revision_id: revision.revision_id, content: payload(revision) })), versions, success_kind: "success" });
      await input.ledger.appendTransitionPlan({ placement: { offline_experiment: true, allocations: {}, results: [] }, derivation, revisions, adjacency: [], artifacts: [] });
      afterPromotion = input.ledger.snapshot(input.owner_account_id);
    }

    let reprojected = 0, committedMerges = 0;
    const skippedMerges: DreamMergeSkip[] = [];
    const skip = (group: readonly string[], reason: string, retryable: boolean): void => {
      const item = { group_mention_ids: [...group].sort(), reason, retryable };
      skippedMerges.push(item); state.recordMergeSkip(input.cycle_id, input.owner_account_id, item.group_mention_ids, reason);
    };
    // This is an admission-policy rejection, not a model warning.  Preserve
    // it in the same durable audit record as other rejected merge attempts.
    for (const rejection of proposal.rejected_same_groups) skip(rejection.group_mention_ids, rejection.reason, rejection.retryable);
    const frontier = Number(before.graph_generation ?? 0);
    for (const [groupIndex, group] of (gate.admitted_proposals.length ? proposal.same_groups : []).entries()) {
      const groupWho = proposal.same_group_who[groupIndex] ?? null;
      const members = group.map((id) => (afterPromotion.mentions ?? []).find((item) => item.mention.mention_id === id)?.mention).filter((item): item is Mention => !!item && item.source_identity_ref !== null);
      if (!members.length) { skip(group, "no_typed_source_identity_members", true); continue; }
      // A late source-local mention joins the already-bound durable entity;
      // it must not mint a parallel entity merely because the partition grew.
      const existingEntities = [...new Set(members.map((mention) => mention.entity_id).filter((entity): entity is string => entity !== null))].sort();
      const entityId = existingEntities[0] ?? `entity:dream:${sha256CanonicalRedacted({ partition: proposal.partition_hash, group: group.slice().sort() }).slice(0, 24)}`;
      let bindings: ReprojectionBinding[] = members.filter((member) => member.entity_id !== entityId).map((mention) => ({ mention_id: mention.mention_id, entity_id: entityId }));
      if (!bindings.length) { skip(group, "already_bound", false); continue; }

      // Admission is deliberately before construction: every authorization we
      // emit below must have a role binding in this exact transition.  A
      // proposed entity with no reachable claim is not a durable merge.
      let reprojection = reprojectBoundClaims(afterPromotion, bindings, input.max_reprojection_claims ?? 128);
      if (!reprojection.revisions.length) { skip(group, "no_reprojectable_canonical_claim", true); continue; }
      const projectable = (candidates: readonly ReprojectionBinding[], projection: typeof reprojection): Set<string> => {
        const projected = new Set<string>();
        for (const binding of candidates) {
          const mention = (afterPromotion.mentions ?? []).find((item) => item.mention.mention_id === binding.mention_id)?.mention;
          if (mention && projection.revisions.some((revision) => revision.claim.source_provisional_revision_ids.includes(mention.claim_revision_id) && revision.claim.arguments.some((argument) => argument.slot_id === mention.slot_id && argument.value.kind === "entity_ref" && argument.value.ref === binding.entity_id))) projected.add(binding.mention_id);
        }
        return projected;
      };
      const projectedBindings = projectable(bindings, reprojection);
      if (projectedBindings.size !== bindings.length) {
        // A member whose claim has no canonical head yet (still deferred in
        // review) must not hold the rest of the group hostage: defer THAT
        // member durably and merge the members that can be wired now. A later
        // cycle re-adjudicates and joins it to the same entity when its claim
        // promotes. Fewer than two wireable members means nothing left that
        // can corroborate, so the whole group defers.
        const deferred = bindings.filter((binding) => !projectedBindings.has(binding.mention_id));
        skip(deferred.map((binding) => binding.mention_id), "binding_not_reprojectable_deferred", true);
        bindings = bindings.filter((binding) => projectedBindings.has(binding.mention_id));
        if (bindings.length < 2 && !existingEntities.length) { skip(group, "not_all_identity_bindings_reprojectable", true); continue; }
        if (!bindings.length) { skip(group, "not_all_identity_bindings_reprojectable", true); continue; }
        reprojection = reprojectBoundClaims(afterPromotion, bindings, input.max_reprojection_claims ?? 128);
        if (!reprojection.revisions.length || projectable(bindings, reprojection).size !== bindings.length) { skip(group, "not_all_identity_bindings_reprojectable", true); continue; }
      }

      // A claim reprojected in an earlier cycle carries entity_ref arguments
      // whose authority lives in prior commits. The validator (rightly)
      // demands that authority be replayable inside THIS transition, so each
      // carried binding travels as witnesses: its resolved mention, its
      // committed authorization, and that authorization's full support
      // lineage. If any piece cannot be found and revalidated, the group is
      // skipped -- never committed on unreplayable authority.
      const carriedWitnesses: GraphRevision[] = [];
      const carriedSupports: import("../../core/resolve/identity-authority").ImmutableIdentitySupport[] = [];
      let carriedReplayable = true;
      for (const revision of reprojection.revisions) {
        for (const argument of revision.claim.arguments) {
          if (argument.value.kind !== "entity_ref") continue;
          const entityRef = argument.value.ref;
          const newlyBound = bindings.some((binding) => {
            const mention = (afterPromotion.mentions ?? []).find((item) => item.mention.mention_id === binding.mention_id)?.mention;
            return mention && binding.entity_id === entityRef && mention.slot_id === argument.slot_id && revision.claim.source_provisional_revision_ids.includes(mention.claim_revision_id);
          });
          if (newlyBound) continue;
          const resolved = (afterPromotion.mentions ?? []).find((item) => revision.claim.source_provisional_revision_ids.includes(item.mention.claim_revision_id) && item.mention.slot_id === argument.slot_id && item.mention.entity_id === entityRef && item.mention.source_identity_ref !== null);
          const authorization = resolved && (afterPromotion.identity_authorizations ?? []).find((item) => item.authorization.lifecycle === "active" && item.authorization.superseded_by === null && item.authorization.relation === "same" && endpointsMatch(item.authorization.endpoints, [{ kind: "source_identity", source_identity_ref: resolved.mention.source_identity_ref! }, { kind: "entity", entity_id: entityRef }]));
          const supportRefs = authorization?.authorization.support.kind === "consolidation_adjudication" ? authorization.authorization.support.support_refs : null;
          const supports = supportRefs?.map((ref) => (afterPromotion.identity_support ?? []).find((item) => item.support_ref === ref));
          if (!resolved || !authorization || !supports || supports.some((item) => !item)) { carriedReplayable = false; break; }
          const lineage = (supports as import("../../core/resolve/identity-authority").ImmutableIdentitySupport[]).flatMap((support): GraphRevision[] => {
            const claim = afterPromotion.claims.find((item) => item.revision_id === support.claim_revision_id);
            const evidence = (afterPromotion.evidence ?? []).find((item) => item.revision_id === support.evidence_ref || item.evidence.evidence_id === support.evidence_ref);
            const event = evidence && (afterPromotion.events ?? []).find((item) => item.revision_id === evidence.evidence.event_revision_id || item.event.event_revision_id === evidence.evidence.event_revision_id);
            if (!claim || !evidence || !event) { carriedReplayable = false; return []; }
            return [{ kind: "claim", revision_id: claim.revision_id, claim: claim.claim, placement_status: claim.placement_status }, { kind: "evidence", revision_id: evidence.revision_id, evidence: evidence.evidence }, { kind: "event", revision_id: event.revision_id, event: event.event }];
          });
          carriedWitnesses.push({ kind: "mention", revision_id: resolved.revision_id, mention: resolved.mention }, { kind: "identity_authorization", revision_id: authorization.revision_id, authorization: authorization.authorization }, ...lineage);
          carriedSupports.push(...(supports as import("../../core/resolve/identity-authority").ImmutableIdentitySupport[]));
        }
        if (!carriedReplayable) break;
      }
      if (!carriedReplayable) { skip(group, "carried_binding_authority_unreplayable", true); continue; }

      // Admission asks whether THIS ENTITY is corroborated by independent
      // source roots, which is a question about the whole membership -- not
      // only about the members joining in this cycle. Deriving the support set
      // from `bindings` alone made a late member unable to ever join an
      // established entity: {already-bound Alice, new Alice} yields one new
      // binding, one support root, and a permanent non_independent_support_set
      // refusal. Already-bound members contribute their support here; only the
      // NEW bindings mint authorizations, constraints, and resolved mentions.
      const admissionMentions = members.filter((member) => member.entity_id === entityId || bindings.some((binding) => binding.mention_id === member.mention_id));
      const supports = admissionMentions.map((mention) => supportFor(afterPromotion, mention));
      if (supports.some((support) => !support)) { skip(group, "missing_independent_identity_support", true); continue; }
      const independentSupports = supports as import("../../core/resolve/identity-authority").ImmutableIdentitySupport[];
      // A singleton or repeated capture root is never corroboration.  Check
      // before constructing revisions so refusal is a clean, non-committing
      // decision rather than a failed partial transition.
      if (independentSupports.length < 2 || new Set(independentSupports.map((support) => support.source_independence_key)).size !== independentSupports.length) {
        skip(group, "non_independent_support_set", true); continue;
      }
      const revisions: AtomicGraphTransition["revisions"] = [];
      // The adjudicator's verified naming becomes a LABEL -- a rendering for
      // humans, never the identity key (D47). The entity_id stays opaque.
      if (!existingEntities.length) revisions.push({ kind: "entity", revision_id: `${entityId}:r1`, entity: { entity_id: entityId, owner_account_id: input.owner_account_id, entity_revision_id: `${entityId}:r1`, handle: `dream-${entityId.slice(-8)}`, labels: groupWho ? [groupWho] : [] } });
      // Two mentions can carry the SAME source identity (one referent seen
      // twice in a session). Authority is per (source identity, entity) pair,
      // so mint one authorization per unique endpoint pair and let every
      // binding's constraint embed it -- a duplicate authorization would fail
      // the validator's no-dangling-authorization check.
      const authorizationByEndpoints = new Map<string, IdentityAuthorization>();
      for (const binding of bindings) {
        const mention = (afterPromotion.mentions ?? []).find((item) => item.mention.mention_id === binding.mention_id)?.mention;
        if (!mention) throw new Error("validated binding mention disappeared before transition construction");
        const endpoints = [{ kind: "source_identity" as const, source_identity_ref: mention.source_identity_ref! }, { kind: "entity" as const, entity_id: entityId }] as const;
        const endpointsKey = sha256CanonicalRedacted({ source: mention.source_identity_ref, entity: entityId });
        let authorization = authorizationByEndpoints.get(endpointsKey);
        if (!authorization) {
          authorization = { authorization_id: `authorization:${mention.mention_id}:${entityId}`, owner_account_id: input.owner_account_id, endpoints, relation: "same", support: { kind: "consolidation_adjudication", support_refs: independentSupports.map((support) => support.support_ref), proposal_lineage_ref: `proposal:${proposal.partition_hash}` }, standing_policy_ref: null, namespace_scope: { namespace_instance_ref: null, identity_domain: null, scope_ref: null }, authority_policy_version: "d50-v1", evaluated_frontier: frontier, actor_provenance: { actor_ref: "dream", producer_ref: null }, lifecycle: "active", superseded_by: null };
          authorizationByEndpoints.set(endpointsKey, authorization);
          revisions.push({ kind: "identity_authorization", revision_id: `identity-authorization:${authorization.authorization_id}`, authorization });
        }
        const constraint: IdentityConstraint = { constraint_id: `constraint:${mention.mention_id}:${entityId}`, owner_account_id: input.owner_account_id, endpoints, left_handle: mention.mention_id, right_handle: entityId, relation: "same", identity_authorization: authorization, effective_at: frontier, reversed_at: null };
        revisions.push({ kind: "identity", revision_id: `identity:${constraint.constraint_id}`, constraint }, { kind: "mention", revision_id: `mention-reprojected:${sha256CanonicalRedacted({ mention_id: binding.mention_id, entity_id: binding.entity_id }).slice(0, 24)}`, mention: { ...mention, resolution: "resolved", entity_id: binding.entity_id } });
      }
      revisions.push(...reprojection.revisions);
      // Witness the lineage of every ADMISSION member, not just the new
      // bindings: the authorization now cites an already-bound member's support,
      // and the validator resolves each support ref through a claim → evidence
      // → event chain that must be present in this transition's input set.
      const baseWitnesses = reprojectionWitnesses(afterPromotion, admissionMentions.map((mention) => ({ mention_id: mention.mention_id, entity_id: entityId })));
      const witnessIds = new Set(baseWitnesses.map((revision) => revision.revision_id));
      const witnesses = [...baseWitnesses, ...carriedWitnesses.filter((revision) => !witnessIds.has(revision.revision_id) && (witnessIds.add(revision.revision_id), true))];
      const supportByRef = new Map([...independentSupports, ...carriedSupports].map((support) => [support.support_ref, support]));
      const head = input.ledger.graphHead(input.owner_account_id);
      const mergeKey = sha256CanonicalRedacted({ partition: proposal.partition_hash, group: group.slice().sort() }).slice(0, 24);
      const derivation = prepareDerivation({ attempt_id: `dream-merge-attempt:${input.cycle_id}:${mergeKey}`, commit_id: `dream-merge:${input.cycle_id}:${mergeKey}`, owner_account_id: input.owner_account_id, parent_commit: head?.commit_id ?? null, idempotency_key: `dream-merge:${input.owner_account_id}:${input.cycle_id}:${mergeKey}`, input_revisions: witnesses.map((revision) => ({ revision_id: revision.revision_id, content: payload(revision) })), output_revisions: revisions.map((revision) => ({ revision_id: revision.revision_id, content: payload(revision) })), versions, success_kind: "success" });
      const artifacts: AtomicGraphTransition["artifacts"] = bindings.map((binding) => ({
        artifact_id: `identity-candidate:${proposal.partition_hash}:${binding.mention_id}:${entityId}`,
        kind: "candidate_derivation" as const,
        owner_account_id: input.owner_account_id,
        source_ref: binding.mention_id,
        candidate_entity_id: entityId,
        strategy_ref: "identity-adjudication-profile-v2",
        // The model proposal is traceable to the immutable claim/evidence
        // supports that the deterministic authority gate subsequently checks.
        input_refs: independentSupports.flatMap((support) => [support.claim_revision_id, support.evidence_ref]).sort(),
      }));
      await input.ledger.appendTransitionPlan({ placement: { offline_experiment: true, allocations: {}, results: [] }, derivation, revisions, adjacency: reprojection.adjacency, artifacts, identity_authority_context: { owner_confirmations: [], producer_assertions: [], standing_policies: [] }, derived_identity_support: [...supportByRef.values()], committed_revisions: witnesses });
      reprojected += reprojection.revisions.length; committedMerges++;
      afterPromotion = input.ledger.snapshot(input.owner_account_id);
    }
    // The partition used to be recorded BEFORE the merge loop, so a cycle
    // whose groups all skipped for retryable reasons (claim not yet
    // reprojectable, transient model error) suppressed the identical
    // partition FOREVER as a repeat -- the equality guard in runDreamCycle is
    // unconditional. Record it only when no retryable work remains: the
    // variance guard still holds for terminally-processed partitions, and a
    // partition with pending work stays re-proposable next cycle.
    if (!skippedMerges.some((item) => item.retryable)) state.recordPartition(input.owner_account_id, proposal.partition_hash);
    const after = input.ledger.snapshot(input.owner_account_id);
    const report: DreamCycleReport = { cycle_id: input.cycle_id, promoted, deferred, reprojected, committed_merges: committedMerges, skipped_merges: skippedMerges, trajectory: diffGraphSnapshots(before, after) };
    state.recordCycle(report, input.owner_account_id, input.trigger_kind, Number(before.graph_generation ?? 0), Number(after.graph_generation ?? 0));
    return report;
};
