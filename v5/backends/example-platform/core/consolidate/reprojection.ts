import { sha256CanonicalRedacted, type ClaimRevision, type GeneratedAdjacency, type GraphRevision } from "../ledger";
import { liveCommittedClaims, type GraphSnapshot } from "../retrieve";
import type { CanonicalClaim, Mention } from "../schema";

/** A validated source-local binding at one committed graph frontier. */
export interface ReprojectionBinding {
  mention_id: string;
  entity_id: string;
}
export interface ReprojectionResult {
  revisions: readonly ClaimRevision[];
  adjacency: readonly GeneratedAdjacency[];
  consumed_claim_revision_ids: readonly string[];
  remaining_live_claim_revision_ids: readonly string[];
}

const revisionId = (claim: CanonicalClaim, priorRevisionId: string, bindings: readonly ReprojectionBinding[]): string =>
  `reprojected:${sha256CanonicalRedacted({ prior_revision_id: priorRevisionId, claim_lineage_id: claim.claim_lineage_id, bindings: bindings.map((binding) => [binding.mention_id, binding.entity_id]).sort() }).slice(0, 24)}`;

/**
 * Append-only projection of already-live canonical claims.  It deliberately
 * retains the claim lineage: D35 picks this revision as the sole live head,
 * rather than showing both the disconnected and connected versions.
 */
export const reprojectBoundClaims = (snapshot: GraphSnapshot, bindings: readonly ReprojectionBinding[], maxClaims: number): ReprojectionResult => {
  if (!Number.isInteger(maxClaims) || maxClaims < 1) throw new Error("reprojection maxClaims must be a positive integer");
  const mentions = new Map((snapshot.mentions ?? []).map((item) => [item.mention.mention_id, item.mention]));
  const bound = new Map(bindings.map((binding) => [binding.mention_id, binding]));
  /**
   * A slot can be named by SEVERAL mentions of the same claim lineage (one
   * provisional revision may be mentioned more than once, and a canonical claim
   * aggregates several provisional revisions).  Selecting with `.find()` would
   * hand the slot to whichever mention iteration order happened to reach first:
   * an unbound mention could shadow a bound one -- silently dropping a claim
   * that this pass is supposed to reproject -- and two mentions bound to
   * DIFFERENT entities would silently elect one of them. Collect every
   * candidate instead and decide deterministically.
   */
  const slotBinding = (claim: CanonicalClaim, slotId: string): { binding: ReprojectionBinding | null; conflicted: boolean } => {
    const candidates = [...mentions.values()].filter((candidate) => claim.source_provisional_revision_ids.includes(candidate.claim_revision_id) && candidate.slot_id === slotId);
    const bindings = candidates.map((candidate) => bound.get(candidate.mention_id)).filter((binding): binding is ReprojectionBinding => !!binding);
    if (!bindings.length) return { binding: null, conflicted: false };
    // Two bound mentions disagreeing about the referent of one slot is not a
    // tie to break; nothing here can decide which entity is right, so the whole
    // claim waits for a pass that resolves the disagreement.
    if (new Set(bindings.map((binding) => binding.entity_id)).size > 1) return { binding: null, conflicted: true };
    return { binding: bindings[0]!, conflicted: false };
  };
  const selected: { revision_id: string; claim: CanonicalClaim; bindings: readonly ReprojectionBinding[] }[] = [];
  const remaining: string[] = [];
  for (const item of liveCommittedClaims(snapshot)) {
    if (item.claim.lifecycle !== "canonical" || item.placement_status !== "canonical") continue;
    let conflicted = false;
    const claimBindings = item.claim.arguments.flatMap((argument) => {
      if (argument.value.kind !== "source_local_ref") return [];
      const selection = slotBinding(item.claim, argument.slot_id);
      if (selection.conflicted) conflicted = true;
      return selection.binding ? [selection.binding] : [];
    });
    if (conflicted || !claimBindings.length) continue;
    if (selected.length >= maxClaims) { remaining.push(item.revision_id); continue; }
    selected.push({ revision_id: item.revision_id, claim: item.claim, bindings: claimBindings });
  }
  const revisions: ClaimRevision[] = [];
  const adjacency: GeneratedAdjacency[] = [];
  for (const item of selected) {
    const bySlot = new Map<string, string>();
    for (const argument of item.claim.arguments) {
      const binding = slotBinding(item.claim, argument.slot_id).binding;
      if (binding) bySlot.set(argument.slot_id, binding.entity_id);
    }
    const nextId = revisionId(item.claim, item.revision_id, item.bindings);
    const claim: CanonicalClaim = {
      ...item.claim,
      claim_revision_id: nextId,
      canonical_claim_id: nextId,
      arguments: item.claim.arguments.map((argument) => bySlot.has(argument.slot_id) ? { ...argument, value: { kind: "entity_ref" as const, ref: bySlot.get(argument.slot_id)! } } : argument),
      // Preserve the liveness group and make the projection relation explicit.
      supersedes_revision_ids: [...new Set([...(item.claim.supersedes_revision_ids ?? []), item.revision_id])].sort(),
    };
    revisions.push({ kind: "claim", revision_id: nextId, claim, placement_status: "canonical" });
    // Adjacency covers EVERY entity-bound slot of the new revision, not only
    // the slots bound in this pass: a claim reprojected once already carries
    // entity_ref arguments, and the prior revision's adjacency rows do not
    // transfer to the new revision id. Emitting only the delta fails the
    // ledger's role-binding/adjacency conservation check on the second merge
    // that touches the same claim.
    for (const argument of claim.arguments) {
      if (argument.value.kind === "entity_ref") adjacency.push({ claim_revision_id: nextId, entity_id: argument.value.ref, role_slot_id: argument.slot_id });
    }
  }
  return { revisions, adjacency, consumed_claim_revision_ids: selected.map((item) => item.revision_id), remaining_live_claim_revision_ids: remaining };
};

/** Immutable witnesses used by the ledger validator for a later-cycle bind. */
export const reprojectionWitnesses = (snapshot: GraphSnapshot, bindings: readonly ReprojectionBinding[]): readonly GraphRevision[] => {
  const mentionIds = new Set(bindings.map((binding) => binding.mention_id));
  const mentions = (snapshot.mentions ?? []).filter((item) => mentionIds.has(item.mention.mention_id)).map((item) => ({ kind: "mention" as const, revision_id: item.revision_id, mention: item.mention }));
  const claimIds = new Set(mentions.map((item) => item.mention.claim_revision_id));
  // Reprojection reads both the source provisional revision named by the
  // mention and its canonical successor.  Keep both in D8's immutable input
  // witness set, even when a claim is omitted by a later reprojection cap.
  const claims = snapshot.claims.filter((item) => claimIds.has(item.revision_id) || (item.claim.lifecycle === "canonical" && item.claim.source_provisional_revision_ids.some((id) => claimIds.has(id)))).map((item) => ({ kind: "claim" as const, revision_id: item.revision_id, claim: item.claim, placement_status: item.placement_status }));
  const evidenceIds = new Set(claims.flatMap((item) => item.claim.evidence_refs));
  const evidence = (snapshot.evidence ?? []).filter((item) => evidenceIds.has(item.evidence.evidence_id)).map((item) => ({ kind: "evidence" as const, revision_id: item.revision_id, evidence: item.evidence }));
  const eventIds = new Set(evidence.map((item) => item.evidence.event_revision_id));
  const events = (snapshot.events ?? []).filter((item) => eventIds.has(item.revision_id) || eventIds.has(item.event.event_revision_id)).map((item) => ({ kind: "event" as const, revision_id: item.revision_id, event: item.event }));
  return [...claims, ...evidence, ...events, ...mentions];
};
