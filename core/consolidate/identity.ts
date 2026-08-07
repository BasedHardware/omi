import type { Evidence, L1Event, Mention } from "../schema";
import { sha256CanonicalRedacted } from "../ledger";

export interface ReferentProfile {
  mention_id: string;
  claim_revision_id: string;
  source_identity_ref: NonNullable<Mention["source_identity_ref"]>;
  discriminating_claims: readonly {
    predicate: string;
    role: string;
    polarity: "positive" | "negative" | null;
    /** Other role fillers describe the proposition; they are not identity keys. */
    other_arguments: readonly { role: string; value: unknown }[];
    /** Grounding excerpts are evidence, not a name-based identity key (D36/D47). */
    evidence_context: readonly { evidence_ref: string; excerpt: string | null; capture_session_id: string | null; event_time: string | null; source_sequence: number | null }[];
    cooccurring_predicates: readonly string[];
    observed_at: string | null;
    evidence_refs: readonly string[];
  }[];
}
/** retryable=true marks a rejection whose cause can change without the group changing (transient model failure,
 * not-yet-promoted inputs); the driver refuses to record a partition as terminally processed while any remain. */
export interface IdentityProposalRejection { group_mention_ids: readonly string[]; reason: string; retryable: boolean; }
export interface IdentityPartitionProposal {
  partition_hash: string;
  same_groups: readonly (readonly string[])[];
  /** The adjudicator's naming of each group's individual, aligned with same_groups; a rendering for labels, never an identity key. */
  same_group_who: readonly (string | null)[];
  /** The adjudicator's own classification of each group's rendering, aligned with same_groups. */
  same_group_kind: readonly (string | null)[];
  /** Which admission lane accepted each group: adversarially verified, or distinctive-surface recurrence. */
  same_group_lane: readonly ("verified" | "recurrence" | "producer")[];
  uncertain_pairs: readonly (readonly [string, string])[];
  /** Deterministic admission rejections, preserved by the dream cycle for audit. */
  rejected_same_groups: readonly IdentityProposalRejection[];
}
export interface IdentityAdjudicationPort { invoke(request: { strategy: string; version: string; input: unknown }): Promise<unknown>; }

type ProfileClaim = {
  revision_id: string;
  claim: {
    predicate: string;
    polarity?: "positive" | "negative";
    evidence_refs: readonly string[];
    temporal_scope?: { observed_at?: string };
    arguments: readonly { slot_id: string; role: string; value: unknown }[];
  };
};
type ProfileEvidence = { revision_id: string; evidence: Evidence };
type ProfileEvent = { revision_id: string; event: L1Event };

const stableValue = (value: unknown): string => JSON.stringify(value);
const sourceIdentityKey = (identity: NonNullable<Mention["source_identity_ref"]>): string => JSON.stringify([
  identity.namespace_instance_ref, identity.local_key, identity.producer.producer_ref,
  identity.producer.contract_ref, identity.asserted_identity.domain, identity.asserted_identity.scope_ref,
]);

/**
 * Deliberately excludes mention surfaces and names.  Excerpts and other role
 * values are grounding facts, not identity keys: D36 requires quoted source
 * evidence while D47 forbids using a rendered name as the identity key.
 */
export const buildReferentProfiles = (mentions: readonly Mention[], claims: readonly ProfileClaim[], evidence: readonly ProfileEvidence[] = [], events: readonly ProfileEvent[] = []): readonly ReferentProfile[] => {
  const evidenceById = new Map(evidence.flatMap((item) => [[item.revision_id, item], [item.evidence.evidence_id, item]] as const));
  const eventsByRevision = new Map(events.map((item) => [item.revision_id, item.event]));
  const mentionsByClaim = new Map<string, Mention[]>();
  for (const mention of mentions) mentionsByClaim.set(mention.claim_revision_id, [...(mentionsByClaim.get(mention.claim_revision_id) ?? []), mention]);
  const predicatesByIdentity = new Map<string, Set<string>>();
  for (const claim of claims) for (const mention of mentionsByClaim.get(claim.revision_id) ?? []) if (mention.source_identity_ref) {
    const key = sourceIdentityKey(mention.source_identity_ref);
    const predicates = predicatesByIdentity.get(key) ?? new Set<string>();
    predicates.add(claim.claim.predicate); predicatesByIdentity.set(key, predicates);
  }
  return mentions.filter((mention) => mention.source_identity_ref !== null).map((mention) => ({
    mention_id: mention.mention_id,
    claim_revision_id: mention.claim_revision_id,
    source_identity_ref: mention.source_identity_ref!,
    discriminating_claims: claims.filter((claim) => claim.revision_id === mention.claim_revision_id).flatMap((claim) => claim.claim.arguments
      .filter((argument) => argument.slot_id === mention.slot_id).map((argument) => {
        const evidence_context = claim.claim.evidence_refs.map((ref) => {
          const matched = evidenceById.get(ref);
          const event = matched ? eventsByRevision.get(matched.evidence.event_revision_id) : undefined;
          return { evidence_ref: ref, excerpt: matched?.evidence.excerpt ?? null, capture_session_id: event?.capture_session_id ?? null, event_time: event?.event_time ?? null, source_sequence: event?.source_sequence ?? null };
        }).sort((left, right) => left.evidence_ref.localeCompare(right.evidence_ref));
        return {
          predicate: claim.claim.predicate,
          role: argument.role,
          polarity: claim.claim.polarity ?? null,
          other_arguments: claim.claim.arguments.filter((other) => other.slot_id !== mention.slot_id)
            .map((other) => ({ role: other.role, value: other.value })).sort((left, right) => `${left.role}\u0000${stableValue(left.value)}`.localeCompare(`${right.role}\u0000${stableValue(right.value)}`)),
          evidence_context,
          cooccurring_predicates: [...(predicatesByIdentity.get(sourceIdentityKey(mention.source_identity_ref!)) ?? new Set<string>())].filter((predicate) => predicate !== claim.claim.predicate).sort(),
          observed_at: claim.claim.temporal_scope?.observed_at ?? null,
          evidence_refs: [...claim.claim.evidence_refs].sort(),
        };
      })),
  })).sort((left, right) => left.mention_id.localeCompare(right.mention_id));
};

/** A conservative deterministic harness proposer: predicate/role alone never forms a group. */
export const proposeProfileOverlaps = (profiles: readonly ReferentProfile[]): readonly (readonly string[])[] => {
  // A shared excerpt by itself can contain several referents.  Require a
  // complete shared proposition context; this remains deliberately blind to
  // surfaces/names and excludes the base predicate/role-only case.
  const facts = (profile: ReferentProfile): Set<string> => new Set(profile.discriminating_claims.flatMap((claim) => {
    const excerpts = claim.evidence_context.flatMap((item) => item.excerpt === null ? [] : [item.excerpt]);
    return excerpts.map((excerpt) => stableValue({
      predicate: claim.predicate, role: claim.role, polarity: claim.polarity,
      // Source-local reference values change from capture to capture, so the
      // harness compares their proposition roles while retaining full values
      // in the profile for an adjudicator to inspect.
      other_roles: claim.other_arguments.map((argument) => argument.role).sort(), excerpt,
    }));
  }));
  const parent = profiles.map((_, index) => index);
  const root = (index: number): number => parent[index] === index ? index : (parent[index] = root(parent[index]!));
  const join = (left: number, right: number): void => { const a = root(left), b = root(right); if (a !== b) parent[b] = a; };
  for (let left = 0; left < profiles.length; left++) for (let right = left + 1; right < profiles.length; right++) {
    const leftFacts = facts(profiles[left]!); const rightFacts = facts(profiles[right]!);
    if ([...leftFacts].some((fact) => rightFacts.has(fact))) join(left, right);
  }
  const groups = new Map<number, string[]>();
  for (let index = 0; index < profiles.length; index++) groups.set(root(index), [...(groups.get(root(index)) ?? []), profiles[index]!.mention_id]);
  return [...groups.values()].filter((group) => group.length > 1).map((group) => group.sort()).sort((left, right) => left.join("\u0000").localeCompare(right.join("\u0000")));
};

/**
 * Candidate blocking for adjudication at corpus scale.
 *
 * One call carrying every profile grows with the ledger and eventually fits no
 * model context: the first real 200-session run lost its later dream cycles to
 * exactly that. Blocking groups mentions by normalized surface -- a RETRIEVAL
 * choice about which referents are worth asking about together, never an
 * identity decision. D47 is intact: the adjudicator still reasons from the
 * excerpts and the deterministic authority gate still decides admission.
 *
 * The size cap is deliberately generic. A surface shared by dozens of mentions
 * in a corpus without speaker attribution ("I", across two languages) cannot
 * be resolved from propositional context alone; adjudicating it buys either
 * nothing or false merges. Oversize clusters become auditable rejections --
 * no pronoun list, no language table. What a surface cannot answer, a typed
 * producer identity can: see blockIdentityClusters, the sibling pass.
 */
export const blockMentionClusters = (mentions: readonly Mention[], maxClusterSize = 16): { clusters: readonly (readonly Mention[])[]; oversize: readonly (readonly Mention[])[]; single_claim: readonly (readonly Mention[])[] } => {
  const byKey = new Map<string, Mention[]>();
  for (const mention of mentions) {
    if (!mention.source_identity_ref) continue;
    const key = mention.surface.trim().toLowerCase().replace(/\s+/g, " ");
    if (!key) continue;
    byKey.set(key, [...(byKey.get(key) ?? []), mention]);
  }
  const clusters: (readonly Mention[])[] = [];
  const oversize: (readonly Mention[])[] = [];
  const single_claim: (readonly Mention[])[] = [];
  for (const [, group] of [...byKey.entries()].sort(([left], [right]) => left.localeCompare(right))) {
    if (group.length < 2) continue;
    const sorted = [...group].sort((left, right) => left.mention_id.localeCompare(right.mention_id));
    // A cluster whose members all sit in one claim has nothing admissible to
    // merge: the same_claim_revision_id gate would reject any group formed
    // from it. Pre-reject it deterministically -- the audit record survives
    // and no adjudication is spent on an unanswerable question.
    if (new Set(group.map((mention) => mention.claim_revision_id)).size < 2) { single_claim.push(sorted); continue; }
    (group.length > maxClusterSize ? oversize : clusters).push(sorted);
  }
  return { clusters, oversize, single_claim };
};

/**
 * Identity-keyed blocking: the signal surface blocking is structurally blind to.
 *
 * A producer-resolved identity (`person:owner`) is stable ACROSS sessions, so
 * one owner's "I", "me" and "я" -- three surfaces blocking keeps apart -- carry
 * a single key the producer itself asserts is one subject. Only producer-backed
 * keys qualify: a synthetic span-local identity has a null producer and asserts
 * nothing beyond its own span, so it must never cluster this way.
 *
 * Unlike a high-frequency surface, an oversize identity cluster is not
 * ambiguous, only large, so it is SAMPLED rather than rejected. The sample is
 * deduped by claim (a same-claim pair is inadmissible anyway) and drawn
 * round-robin across capture sessions, so a bounded payload spans the corpus
 * instead of one afternoon; with no session derivable every member falls in one
 * bucket and the draw degrades to first-N by mention_id. The unsampled
 * remainder is NOT a rejection -- a later dream cycle re-adjudicates it and
 * joins it to the entity this sample established via the existing-entity path.
 *
 * Members usually carry different surfaces, so these clusters take the
 * adversarial lane. That is correct and deliberately not special-cased: the
 * producer key strengthens the evidence an adjudicator reasons over, and the
 * deterministic gates still decide admission.
 */
export const blockIdentityClusters = (mentions: readonly Mention[], maxClusterSize = 16, sessionByClaim: ReadonlyMap<string, string | null> = new Map()): { clusters: readonly (readonly Mention[])[]; single_claim: readonly (readonly Mention[])[] } => {
  const byKey = new Map<string, Mention[]>();
  for (const mention of mentions) {
    const identity = mention.source_identity_ref;
    if (!identity || identity.producer.producer_ref === null) continue;
    // The FULL identity coordinate, matching sourceIdentityKey: two producers
    // sharing a namespace and local key are still two authorities (sol #6).
    const key = sourceIdentityKey(identity);
    byKey.set(key, [...(byKey.get(key) ?? []), mention]);
  }
  const clusters: (readonly Mention[])[] = [];
  const single_claim: (readonly Mention[])[] = [];
  for (const [, group] of [...byKey.entries()].sort(([left], [right]) => left.localeCompare(right))) {
    if (group.length < 2) continue;
    const sorted = [...group].sort((left, right) => left.mention_id.localeCompare(right.mention_id));
    if (new Set(group.map((mention) => mention.claim_revision_id)).size < 2) { single_claim.push(sorted); continue; }
    const seenClaims = new Set<string>();
    const bySession = new Map<string, Mention[]>();
    // Unbound members first: with a stable sort alone, the same first-N win
    // every cycle and the tail is never adjudicated (sol #8). Already-bound
    // members still join late via the existing-entity path, so spending the
    // sample budget on the unbound is strictly better -- keep ONE bound
    // representative first so the group targets the established entity.
    const boundFirst = [...sorted.filter((mention) => mention.entity_id !== null).slice(0, 1), ...sorted.filter((mention) => mention.entity_id === null), ...sorted.filter((mention) => mention.entity_id !== null).slice(1)];
    for (const mention of boundFirst) {
      if (seenClaims.has(mention.claim_revision_id)) continue;
      seenClaims.add(mention.claim_revision_id);
      const session = sessionByClaim.get(mention.claim_revision_id) ?? "";
      bySession.set(session, [...(bySession.get(session) ?? []), mention]);
    }
    const rounds = [...bySession.entries()].sort(([left], [right]) => left.localeCompare(right)).map(([, members]) => members);
    const sample: Mention[] = [];
    for (let round = 0; sample.length < maxClusterSize && rounds.some((members) => members.length > round); round++)
      for (const members of rounds) {
        if (sample.length >= maxClusterSize) break;
        const member = members[round];
        if (member) sample.push(member);
      }
    if (sample.length < 2) continue;
    clusters.push(sample.sort((left, right) => left.mention_id.localeCompare(right.mention_id)));
  }
  return { clusters, single_claim };
};

/** First derivable capture session per claim, used only to spread a sample. */
const claimSessionIndex = (claims: readonly ProfileClaim[], evidence: readonly ProfileEvidence[], events: readonly ProfileEvent[]): ReadonlyMap<string, string | null> => {
  const evidenceById = new Map(evidence.flatMap((item) => [[item.revision_id, item], [item.evidence.evidence_id, item]] as const));
  const eventsByRevision = new Map(events.map((item) => [item.revision_id, item.event]));
  return new Map(claims.map((claim) => [claim.revision_id, [...claim.claim.evidence_refs].sort().flatMap((ref) => {
    const matched = evidenceById.get(ref);
    const event = matched ? eventsByRevision.get(matched.evidence.event_revision_id) : undefined;
    return event?.capture_session_id ? [event.capture_session_id] : [];
  })[0] ?? null] as const));
};

export interface BlockedAdjudicationInput {
  mentions: readonly Mention[];
  claims: readonly ProfileClaim[];
  evidence?: readonly ProfileEvidence[];
  events?: readonly ProfileEvent[];
  max_cluster_size?: number;
  /** Per-call profile payload budget in JSON characters, not a truncation: whole clusters move to the next call. */
  batch_profile_budget?: number;
  /** Concurrent model calls per phase (adjudicate, verify, card). Results are applied in deterministic order regardless. */
  model_concurrency?: number;
}

/**
 * STANDING RULE for any future input reduction here: a reduction may SELECT
 * whole clusters and must never PRUNE members inside a selected cluster.
 * Both prior attempts to reduce within a cluster failed the same way -- sol #7
 * restricted admission supports to newly bound members and manufactured false
 * `non_independent_support_set`, and sol #8's fixed-prefix sampling starved the
 * tail forever. Admission supports derive from all coherent members, bound and
 * new, and a bound representative is what anchors a group to its existing
 * entity; drop either and late joins stop working.
 *
 * Note also that `batch_profile_budget` bounds bytes per phase-1 call and
 * NOTHING else: phases 2 and 3 are per-group calls whose count no budget
 * bounds, and they are ~87% of a cycle's model calls at corpus scale
 * (harness/identity-cost.ts). Reducing payload size alone does not reduce them.
 */
/**
 * Blocked, batched adjudication. Each call stays under a fixed payload budget;
 * a batch that cannot be adjudicated (model error, oversize response) loses
 * only its own candidates for this cycle, recorded as a durable rejection the
 * next cycle can retry -- never the whole cycle. The partition hash is
 * computed over the union so two runs that agree on the answer agree on the
 * key regardless of how the batches fell.
 */
/** Bounded-concurrency map that fills results by INDEX: callers apply the
 * results in the original order afterwards, so parallel model latency never
 * changes which rejection lands first or how ties break. */
const mapLimit = async <T, R>(items: readonly T[], limit: number, task: (item: T, index: number) => Promise<R>): Promise<R[]> => {
  const results = new Array<R>(items.length);
  let next = 0;
  await Promise.all(Array.from({ length: Math.max(1, Math.min(limit, items.length)) }, async () => {
    while (next < items.length) { const index = next++; results[index] = await task(items[index]!, index); }
  }));
  return results;
};

export const invokeBlockedIdentityAdjudication = async (model: IdentityAdjudicationPort, input: BlockedAdjudicationInput): Promise<IdentityPartitionProposal> => {
  const maxClusterSize = input.max_cluster_size ?? 16;
  const modelConcurrency = input.model_concurrency ?? 6;
  const { clusters, oversize, single_claim } = blockMentionClusters(input.mentions, maxClusterSize);
  const identityBlocks = blockIdentityClusters(input.mentions, maxClusterSize, claimSessionIndex(input.claims, input.evidence ?? [], input.events ?? []));
  const clusterKey = (cluster: readonly Mention[]): string => JSON.stringify(cluster.map((mention) => mention.mention_id).sort());
  // A mention may legitimately sit in both a surface and an identity cluster;
  // only an IDENTICAL cluster is redundant work and a duplicated group.
  const blockedKeys = new Set(clusters.map(clusterKey));
  const blocked = [...clusters, ...identityBlocks.clusters.filter((cluster) => !blockedKeys.has(clusterKey(cluster)))];
  const rejected_same_groups: IdentityProposalRejection[] = [
    ...[...new Map([...single_claim, ...identityBlocks.single_claim].map((group) => [clusterKey(group), group] as const)).values()]
      .map((group) => ({ group_mention_ids: group.map((mention) => mention.mention_id).sort(), retryable: false, reason: "same_claim_revision_id" })),
    ...oversize.map((group) => ({ group_mention_ids: group.map((mention) => mention.mention_id).sort(), retryable: false, reason: "ambiguous_high_frequency_surface" })),
  ];
  const budget = input.batch_profile_budget ?? 24_000;
  const prepared = blocked
    .map((cluster) => { const profiles = buildReferentProfiles(cluster, input.claims, input.evidence ?? [], input.events ?? []); return { profiles, cost: JSON.stringify(profiles).length }; })
    .filter((entry) => entry.profiles.length > 1);
  const batches: (typeof prepared)[] = [];
  let current: typeof prepared = [];
  let size = 0;
  for (const entry of prepared) {
    if (current.length && size + entry.cost > budget) { batches.push(current); current = []; size = 0; }
    current.push(entry); size += entry.cost;
  }
  if (current.length) batches.push(current);
  const sameGroups: (readonly string[])[] = [];
  const whoByGroup = new Map<string, string | null>();
  const kindByGroup = new Map<string, string | null>();
  const laneByGroup = new Map<string, "verified" | "recurrence" | "producer">();
  const uncertainPairs: (readonly [string, string])[] = [];
  const profileByMention = new Map(prepared.flatMap((entry) => entry.profiles.map((profile) => [profile.mention_id, profile] as const)));
  const key = (group: readonly string[]): string => JSON.stringify([...group].sort());
  const batchOutcomes = await mapLimit(batches, modelConcurrency, async (batch) => {
    const profiles = batch.flatMap((entry) => entry.profiles);
    try { return { profiles, proposal: await invokeIdentityAdjudication(model, profiles), error: null }; }
    catch (error) { return { profiles, proposal: null, error }; }
  });
  for (const outcome of batchOutcomes) {
    if (outcome.proposal) {
      const proposal = outcome.proposal;
      proposal.same_groups.forEach((group, index) => { sameGroups.push(group); whoByGroup.set(key(group), proposal.same_group_who[index] ?? null); kindByGroup.set(key(group), proposal.same_group_kind[index] ?? null); });
      uncertainPairs.push(...proposal.uncertain_pairs);
      rejected_same_groups.push(...proposal.rejected_same_groups);
    } else {
      rejected_same_groups.push({ group_mention_ids: outcome.profiles.map((profile) => profile.mention_id).sort(), retryable: true, reason: `adjudication_failed: ${outcome.error instanceof Error ? outcome.error.message.slice(0, 120) : "unknown"}` });
    }
  }
  // Second, adversarial pass per surviving group. The grouping frame
  // over-merges whatever shares a sentence; this frame sees ONE named merge
  // and is asked to refute it, defaulting to not_proven. A verification
  // ERROR (as opposed to a refutation) is recorded as retryable.
  // D36 for identity: the verifier's naming must occur, verbatim by token, in
  // at least two members' own evidence (their surfaces or excerpts). A name
  // the evidence never utters -- however confident the model -- is a
  // hallucinated individual, and a merge justified by it is inadmissible.
  // Deterministic, language-agnostic, no word lists.
  const tokens = (value: string): string[] => value.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter((token) => token.length > 1);
  const surfaceByMention = new Map(input.mentions.map((mention) => [mention.mention_id, mention.surface] as const));
  const identityRefByMention = new Map(input.mentions.map((mention) => [mention.mention_id, mention.source_identity_ref] as const));
  // D48: when every member carries the SAME producer-backed identity
  // coordinate (a diarized speaker, person:owner), the producer's authority
  // relates the members -- their surfaces never will ("I" / "я"). For such a
  // group the verified name may stand as the label even though no surface
  // renders it; otherwise the owner's own entity would forever fall back to a
  // deictic surface and die at the card test below.
  const producerBacked = (group: readonly string[]): boolean => {
    const keys = new Set<string | null>();
    for (const id of group) {
      const ref = identityRefByMention.get(id);
      keys.add(ref && ref.producer.producer_ref ? sourceIdentityKey(ref) : null);
    }
    return keys.size === 1 && !keys.has(null);
  };
  const whoGrounded = (who: string, group: readonly string[]): boolean => {
    const whoTokens = tokens(who);
    if (!whoTokens.length) return false;
    let supported = 0;
    for (const id of group) {
      const profile = profileByMention.get(id);
      // Exact TOKEN equality, never substring: "Ann" grounding in "planning"
      // let a hallucinated individual pass the verbatim gate.
      const evidenceTokens = new Set([surfaceByMention.get(id) ?? "", ...(profile?.discriminating_claims ?? []).flatMap((claim) => claim.evidence_context.flatMap((item) => item.excerpt ? [item.excerpt] : []))].flatMap((text) => tokens(text)));
      if (whoTokens.some((token) => evidenceTokens.has(token))) supported += 1;
    }
    return supported >= 2;
  };
  const verified: (readonly string[])[] = [];
  const candidateGroups = [...new Map(sameGroups.map((item) => [key(item), item])).values()];
  // Lane B -- distinctive recurrence. In one owner's corpus, the same
  // distinctive rendering recurring across independent sessions is the same
  // individual at well above the accepted confidence floor, and a wrong one
  // is SPLITTABLE later (unlike a deictic merge, which nothing can ever
  // re-adjudicate). Requires: one shared normalized surface, the
  // adjudicator classified it a named individual, and its naming grounds in
  // that surface. Commits without the adversarial pass -- and without its
  // cost. D50 cross-session independence still gates downstream.
  // Verification calls run concurrently (each group's verdict depends only on
  // its own members) and are applied strictly in candidate order below.
  const verifications = await mapLimit(candidateGroups, modelConcurrency, async (group) => {
    // Lane C -- producer-backed admission (D48). When every member carries the
    // SAME producer-backed identity coordinate, the producer has already
    // asserted co-reference; surfaces ("\u044f", "I") can never prove it and the
    // adversarial verifier -- shown only surfaces and excerpts -- rightly
    // refuses. The coordinate IS the evidence, and checking it is
    // deterministic, so this lane needs no model verdict at all. The card
    // test below still runs, but as label SELECTION, not admission.
    if (producerBacked(group)) return { kind: "producer" as const };
    const normalized = new Set(group.map((id) => (surfaceByMention.get(id) ?? "").trim().toLowerCase().replace(/\s+/g, " ")).filter(Boolean));
    const sharedSurface = normalized.size === 1 ? [...normalized][0]! : null;
    const adjudicatedWho = whoByGroup.get(key(group)) ?? null;
    if (sharedSurface && adjudicatedWho && kindByGroup.get(key(group)) === "named_individual" && tokens(adjudicatedWho).some((token) => tokens(sharedSurface).includes(token))) return { kind: "recurrence" as const };
    const profiles = group.map((id) => profileByMention.get(id)).filter((item): item is ReferentProfile => !!item);
    const surfaces = [...new Set(group.map((id) => surfaceByMention.get(id)).filter((surface): surface is string => !!surface))].sort();
    try { return { kind: "verdict" as const, verdict: await model.invoke({ strategy: "identity-verification", version: "dream-identity-verify-v2", input: { who: adjudicatedWho, surfaces, profiles } }) as { verdict?: string; who?: string | null } }; }
    catch (error) { return { kind: "error" as const, error }; }
  });
  for (const [index, group] of candidateGroups.entries()) {
    const outcome = verifications[index]!;
    if (outcome.kind === "producer") { verified.push(group); laneByGroup.set(key(group), "producer"); continue; }
    if (outcome.kind === "recurrence") { verified.push(group); laneByGroup.set(key(group), "recurrence"); continue; }
    if (outcome.kind === "error") { rejected_same_groups.push({ group_mention_ids: [...group].sort(), retryable: true, reason: `verification_failed: ${outcome.error instanceof Error ? outcome.error.message.slice(0, 120) : "unknown"}` }); continue; }
    const verdict = outcome.verdict;
    const who = verdict?.who ?? whoByGroup.get(key(group)) ?? null;
    if (verdict?.verdict !== "same") { rejected_same_groups.push({ group_mention_ids: [...group].sort(), retryable: false, reason: "identity_not_proven_on_verification" }); continue; }
    if (!who || !whoGrounded(who, group)) { rejected_same_groups.push({ group_mention_ids: [...group].sort(), retryable: false, reason: "identity_naming_ungrounded_in_evidence" }); continue; }
    // The LABEL is held to a stricter standard than admission: it must name
    // what the members' own surfaces render, not merely someone uttered
    // nearby. "New York"x2 merged but named after the person in the same
    // sentence is a right merge wearing the wrong name -- keep the merge,
    // label it by its dominant surface instead.
    const whoTokens = new Set(tokens(who));
    const surfaceGrounded = group.filter((id) => tokens(surfaceByMention.get(id) ?? "").some((token) => whoTokens.has(token))).length >= 2;
    const dominantSurface = [...group.reduce((counts, id) => { const surface = (surfaceByMention.get(id) ?? "").trim(); if (surface) counts.set(surface.toLowerCase(), (counts.get(surface.toLowerCase()) ?? 0) + 1); return counts; }, new Map<string, number>()).entries()].sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))[0]?.[0] ?? null;
    verified.push(group); whoByGroup.set(key(group), surfaceGrounded || producerBacked(group) ? who : dominantSurface ?? who); laneByGroup.set(key(group), "verified");
  }
  // Member-level pruning: a verified group may still carry same-sentence
  // hitchhikers -- members whose OWN surface shares nothing with the identity
  // the group was admitted as ("not that" riding along with "new york"). Shed
  // them (durably, retryable next cycle) when at least two coherent members
  // remain; when pruning would leave fewer than two, keep the group whole and
  // let the verifier's judgment stand.
  const pruned = verified.map((group) => {
    const who = whoByGroup.get(key(group));
    if (!who) return group;
    const whoTokens = new Set(tokens(who));
    const coherent = group.filter((id) => tokens(surfaceByMention.get(id) ?? "").some((token) => whoTokens.has(token)));
    if (coherent.length < 2 || coherent.length === group.length) return group;
    const shed = group.filter((id) => !coherent.includes(id));
    rejected_same_groups.push({ group_mention_ids: [...shed].sort(), retryable: true, reason: "member_surface_unrelated_to_verified_identity" });
    whoByGroup.set(key(coherent), who);
    kindByGroup.set(key(coherent), kindByGroup.get(key(group)) ?? null);
    laneByGroup.set(key(coherent), laneByGroup.get(key(group)) ?? "verified");
    return coherent;
  });
  // Final gate, both lanes: the card test. Every earlier gate grounds the
  // name in the members' own evidence -- and a deictic grounds in itself
  // ("him" appears verbatim in "him"), so grounding alone can never reject
  // one. This gate asks the one question grounding cannot: shown the chosen
  // label ALONE, stripped of all conversation, does it name one specific
  // referent? It runs on the FINAL label (who, or the dominant surface it
  // fell back to) because the fallback is exactly where a right merge ends up
  // wearing a deictic name. Fail closed: an unanswerable check is a rejection
  // that returns next cycle, never an admission.
  const admitted: (readonly string[])[] = [];
  const finalGroups = [...new Map(pruned.map((item) => [key(item), item])).values()];
  const renderingByEvidence = new Map((input.evidence ?? []).map((row) => [row.evidence.evidence_id, row.evidence.speaker_rendering] as const));
  const evidenceByMention = new Map(input.mentions.map((mention) => [mention.mention_id, mention.evidence_id] as const));
  const checks = await mapLimit(finalGroups, modelConcurrency, async (group) => {
    if (laneByGroup.get(key(group)) === "producer") {
      // Doc 47 (d) guard: the extraction model CHOSE which slot is the
      // speaker, and this lane is about to bind those words with producer
      // authority -- so each distinct surface must first pass one question: is
      // the speaker referring to themself with it? A topic phrase mis-marked
      // as the speaker slot ("owning the embedding layer") is shed here,
      // retryably, before it can pollute a person. Fail closed: an
      // unanswerable check rejects the group for this cycle.
      const groupSurfaces = [...new Set(group.map((id) => surfaceByMention.get(id)).filter((surface): surface is string => !!surface))].sort();
      const renderingOf = (id: string): string | null => renderingByEvidence.get(evidenceByMention.get(id) ?? "") ?? null;
      const dominantOf = (members: readonly string[]): string | null => [...members.flatMap((id) => { const rendering = renderingOf(id); return rendering ? [rendering] : []; }).reduce((counts, rendering) => counts.set(rendering, (counts.get(rendering) ?? 0) + 1), new Map<string, number>()).entries()].sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))[0]?.[0] ?? null;
      let coherent: readonly string[];
      try {
        const verdict = await model.invoke({ strategy: "speaker-self-reference", version: "dream-self-reference-v1", input: { speaker: dominantOf(group), phrases: groupSurfaces } }) as { self_referring?: readonly boolean[] };
        const selfReferring = new Set(groupSurfaces.filter((_, index) => verdict?.self_referring?.[index] === true));
        coherent = group.filter((id) => selfReferring.has(surfaceByMention.get(id) ?? ""));
      } catch (error) {
        return { kind: "producer_rejected" as const, reason: `self_reference_check_failed: ${error instanceof Error ? error.message.slice(0, 120) : "unknown"}` };
      }
      if (coherent.length < 2) return { kind: "producer_rejected" as const, reason: "speaker_slot_not_self_reference" };
      const shed = group.filter((id) => !coherent.includes(id));
      // The card test picks a NAME rather than gating admission: the dominant
      // speaker rendering (diarization already names the speaker), then the
      // adjudicator's naming -- first that names a specific referent. When
      // neither does, fall back to the coordinate's own neutral rendering; a
      // plain label never blocks a producer-authorized identity.
      const coherentSurfaces = [...new Set(coherent.map((id) => surfaceByMention.get(id)).filter((surface): surface is string => !!surface))].sort();
      for (const candidate of [...new Set([dominantOf(coherent), whoByGroup.get(key(group)) ?? null].filter((candidate): candidate is string => !!candidate))]) {
        try {
          const check = await model.invoke({ strategy: "identity-naming-check", version: "dream-naming-check-v1", input: { label: candidate, surfaces: coherentSurfaces } }) as { names_specific_referent?: boolean };
          if (check?.names_specific_referent === true) return { kind: "producer_labelled" as const, label: candidate, members: coherent, shed };
        } catch { /* a failed label check falls through to the next candidate, never to a rejection */ }
      }
      const ref = identityRefByMention.get(coherent[0]!);
      return { kind: "producer_labelled" as const, label: ref?.local_key === "person:owner" ? "owner" : (ref?.local_key ?? "person").replace(/^person:/, "person ").slice(0, 16), members: coherent, shed };
    }
    const label = whoByGroup.get(key(group)) ?? null;
    if (!label) return { kind: "no_label" as const };
    const groupSurfaces = [...new Set(group.map((id) => surfaceByMention.get(id)).filter((surface): surface is string => !!surface))].sort();
    try { return { kind: "check" as const, check: await model.invoke({ strategy: "identity-naming-check", version: "dream-naming-check-v1", input: { label, surfaces: groupSurfaces } }) as { names_specific_referent?: boolean } }; }
    catch (error) { return { kind: "error" as const, error }; }
  });
  for (const [index, group] of finalGroups.entries()) {
    const outcome = checks[index]!;
    if (outcome.kind === "producer_labelled") {
      if (outcome.shed.length) rejected_same_groups.push({ group_mention_ids: [...outcome.shed].sort(), reason: "speaker_slot_not_self_reference", retryable: true });
      whoByGroup.set(key(outcome.members), outcome.label); laneByGroup.set(key(outcome.members), "producer"); kindByGroup.set(key(outcome.members), kindByGroup.get(key(group)) ?? null);
      admitted.push(outcome.members); continue;
    }
    if (outcome.kind === "producer_rejected") { rejected_same_groups.push({ group_mention_ids: [...group].sort(), reason: outcome.reason, retryable: true }); continue; }
    if (outcome.kind === "error") { rejected_same_groups.push({ group_mention_ids: [...group].sort(), retryable: true, reason: `naming_check_failed: ${outcome.error instanceof Error ? outcome.error.message.slice(0, 120) : "unknown"}` }); continue; }
    if (outcome.kind === "no_label" || outcome.check?.names_specific_referent !== true) { rejected_same_groups.push({ group_mention_ids: [...group].sort(), retryable: false, reason: "identity_reference_context_dependent" }); continue; }
    admitted.push(group);
  }
  const same_groups = [...admitted].sort((left, right) => key(left).localeCompare(key(right)));
  const uncertain_pairs = [...new Map(uncertainPairs.map((pair) => [pair.join("|"), pair])).values()].sort((left, right) => left.join("|").localeCompare(right.join("|")));
  return { partition_hash: `partition:${sha256CanonicalRedacted({ same_groups })}`, same_groups, same_group_who: same_groups.map((group) => whoByGroup.get(key(group)) ?? null), same_group_kind: same_groups.map((group) => kindByGroup.get(key(group)) ?? null), same_group_lane: same_groups.map((group) => laneByGroup.get(key(group)) ?? "verified"), uncertain_pairs, rejected_same_groups };
};

type AdjudicationGroup = readonly string[] | { members: readonly string[]; who?: string | null; kind?: string | null };
type AdjudicationResponse = { same_groups: readonly AdjudicationGroup[]; uncertain_pairs?: readonly (readonly string[])[] };
const groupMembers = (group: AdjudicationGroup): readonly string[] => Array.isArray(group) ? group : (group as { members: readonly string[] }).members;
const groupWho = (group: AdjudicationGroup): string | null => Array.isArray(group) ? null : ((group as { who?: string | null }).who ?? null);
const groupKind = (group: AdjudicationGroup): string | null => Array.isArray(group) ? null : ((group as { kind?: string | null }).kind ?? null);
const isGroup = (group: unknown): group is AdjudicationGroup =>
  (Array.isArray(group) && group.every((id) => typeof id === "string"))
  || (!!group && typeof group === "object" && Array.isArray((group as { members?: unknown }).members) && ((group as { members: unknown[] }).members).every((id) => typeof id === "string") && ((group as { who?: unknown }).who === undefined || (group as { who?: unknown }).who === null || typeof (group as { who?: unknown }).who === "string"));
const isProposal = (value: unknown): value is AdjudicationResponse => {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<AdjudicationResponse>;
  return Array.isArray(item.same_groups)
    && item.same_groups.every(isGroup)
    && (item.uncertain_pairs === undefined || (Array.isArray(item.uncertain_pairs) && item.uncertain_pairs.every((pair) => Array.isArray(pair) && pair.length === 2 && pair.every((id) => typeof id === "string"))));
};

/**
 * The partition hash is computed here, never requested.
 *
 * It is a stable digest used to recognise a partition this owner has already
 * seen, so a model-supplied one is both unverifiable and unreliable: hashing is
 * the class of task a model cannot do, and a wrong hash silently defeats the
 * cycle-repetition guard it exists to power. Deriving it from the admitted
 * groups also makes two adapters that agree on the answer agree on the key.
 */
export const invokeIdentityAdjudication = async (model: IdentityAdjudicationPort, profiles: readonly ReferentProfile[]): Promise<IdentityPartitionProposal> => {
  const response = await model.invoke({ strategy: "identity-adjudication", version: "dream-identity-v1", input: { profiles } });
  if (!isProposal(response)) throw new Error("identity adjudication returned invalid partition proposal");
  const profileByMention = new Map(profiles.map((profile) => [profile.mention_id, profile]));
  const rejected_same_groups: IdentityProposalRejection[] = [];
  const claimed = new Set<string>();
  const admitted = response.same_groups
    .map((group) => ({ members: [...new Set(groupMembers(group))].sort(), who: groupWho(group), kind: groupKind(group) }))
    .filter((group) => group.members.length > 1)
    // A partition of the INPUT, nothing else: a member the request never
    // contained is a hallucinated referent, and a member in two groups makes
    // the answer not a partition -- both void the group (sol #12).
    .filter((group) => {
      if (!group.members.every((id) => profileByMention.has(id))) { rejected_same_groups.push({ group_mention_ids: group.members, retryable: true, reason: "member_outside_adjudicated_input" }); return false; }
      if (group.members.some((id) => claimed.has(id))) { rejected_same_groups.push({ group_mention_ids: group.members, retryable: true, reason: "overlapping_partition_groups" }); return false; }
      for (const id of group.members) claimed.add(id);
      return true;
    })
    .filter((group) => {
      const claimIds = new Set<string>();
      for (const mentionId of group.members) {
        const claimId = profileByMention.get(mentionId)?.claim_revision_id;
        if (claimId && claimIds.has(claimId)) { rejected_same_groups.push({ group_mention_ids: group.members, retryable: false, reason: "same_claim_revision_id" }); return false; }
        if (claimId) claimIds.add(claimId);
      }
      return true;
    });
  const same_groups = admitted.map((group) => group.members);
  const uncertain_pairs = (response.uncertain_pairs ?? []).map((pair) => [pair[0], pair[1]!].sort() as [string, string]).sort((left, right) => left.join("\u0000").localeCompare(right.join("\u0000")));
  return { partition_hash: `partition:${sha256CanonicalRedacted({ same_groups })}`, same_groups, same_group_who: admitted.map((group) => group.who), same_group_kind: admitted.map((group) => group.kind), same_group_lane: admitted.map(() => "verified" as const), uncertain_pairs, rejected_same_groups };
};
