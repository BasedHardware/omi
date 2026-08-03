import type { Evidence, Mention, ProvisionalClaim, SourceIdentityRef } from "../schema";
import { hasDistinctArgumentSlotIds } from "../schema";

export interface MentionDetectionRequest {
  strategy: "mention-local-handle";
  version: "v1";
  claims: readonly { claim_revision_id: string; predicate: string; observed_speaker_slot_id: string | null; arguments: readonly { slot_id: string; role: string; surface: string }[]; evidence: readonly { evidence_id: string; excerpt: string; source_identity_ref: SourceIdentityRef | null; speaker_rendering: string | null }[] }[];
}
/** Offsets and ids are both derived, never supplied: a model that emits either
 * is doing bookkeeping it is measurably bad at (5.5% of live argument offsets
 * were correct), and a model-minted `mention_id` used to become a durable graph
 * key straight out of the response. */
export interface MentionDetectionResponse { mentions: readonly { claim_revision_id: string; slot_id: string; surface: string; evidence_id: string; antecedent_handle: string | null }[]; }

const forcedUnresolvedPrefix = "forced-unresolved:";
/** A non-speaker mention needs a typed coordinate too.  This is deliberately
 * not the speaker's producer attestation; it is only the capture-local
 * referent coordinate which consolidation can later authorize. */
export const sourceLocalIdentity = (evidenceId: string, sourceLocalRef: string): SourceIdentityRef => ({
  namespace_instance_ref: `source-local:${evidenceId}`,
  local_key: sourceLocalRef,
  producer: { producer_ref: null, contract_ref: null },
  asserted_identity: { domain: null, scope_ref: null },
});

/** A detector omission is evidence of no detected mention, never permission to guess one. */
export const isForcedUnresolvedMention = (mention: Mention): boolean => mention.mention_id.startsWith(forcedUnresolvedPrefix);

/**
 * A durable role binding is authorized by one—and only one—resolved source
 * mention.  Extra rows are not interchangeable evidence: an abstention,
 * conflict, or duplicate detection leaves that role unresolved.
 */
export const durableRoleSlotBindings = (mentions: readonly Mention[]): ReadonlyMap<string, string> => {
  const bySlot = new Map<string, Mention[]>();
  for (const mention of mentions) bySlot.set(mention.slot_id, [...(bySlot.get(mention.slot_id) ?? []), mention]);
  const bindings = new Map<string, string>();
  for (const [slotId, slotMentions] of bySlot) {
    const [mention] = slotMentions;
    if (slotMentions.length === 1 && mention?.resolution === "resolved" && mention.entity_id !== null) bindings.set(slotId, mention.entity_id);
  }
  return bindings;
};

/** Construct only from retained claim/evidence context; missing excerpts fail closed. */
export const buildMentionDetectionRequest = (claims: readonly ProvisionalClaim[], evidence: readonly Evidence[]): MentionDetectionRequest => {
  const evidenceById = new Map(evidence.map((item) => [item.evidence_id, item]));
  return {
    strategy: "mention-local-handle", version: "v1",
    claims: claims.map((claim) => {
      if (!hasDistinctArgumentSlotIds(claim.arguments)) throw new Error(`claim arguments must have distinct slot_ids: ${claim.claim_revision_id}`);
      return {
        claim_revision_id: claim.claim_revision_id, predicate: claim.predicate,
        observed_speaker_slot_id: claim.observed_speaker_slot_id ?? null,
        arguments: claim.arguments.map((argument) => ({ slot_id: argument.slot_id, role: argument.role, surface: argument.surface ?? (argument.value.kind === "entity_ref" || argument.value.kind === "source_local_ref" ? argument.value.ref : String(argument.value.value)) })),
        evidence: claim.evidence_refs.map((evidence_id) => {
          const item = evidenceById.get(evidence_id);
          if (!item?.excerpt) throw new Error(`mention request lacks retained evidence excerpt: ${evidence_id}`);
          return { evidence_id, excerpt: item.excerpt, source_identity_ref: item.source_identity_ref ?? null, speaker_rendering: item.speaker_rendering ?? null };
        }),
      };
    }),
  };
};

/** Validate model output against source context and retain every valid unresolved mention. */
export const planMentionDetection = (owner_account_id: string, request: MentionDetectionRequest, response: MentionDetectionResponse): readonly Mention[] => {
  const claims = new Map(request.claims.map((claim) => [claim.claim_revision_id, claim]));
  const perSlot = new Map<string, number>();
  const mentions = response.mentions.flatMap((item) => {
    const claim = claims.get(item.claim_revision_id);
    const argument = claim?.arguments.find((candidate) => candidate.slot_id === item.slot_id);
    const source = claim?.evidence.find((candidate) => candidate.evidence_id === item.evidence_id);
    // A quoted surface the excerpt does not contain is an ungrounded detection:
    // the role falls through to the forced-unresolved pass below rather than the
    // whole batch throwing.
    const start = source && item.surface ? source.excerpt.indexOf(item.surface) : -1;
    if (!claim || !argument || !source || start < 0) return [];
    // A second row for one slot is a CONFLICT, and is deliberately retained:
    // `durableRoleSlotBindings` refuses a slot with anything other than exactly
    // one resolved mention, so discarding the duplicate here would silently
    // promote a contested role into a confident binding.
    const seen = perSlot.get(`${item.claim_revision_id}\u0000${item.slot_id}`) ?? 0;
    perSlot.set(`${item.claim_revision_id}\u0000${item.slot_id}`, seen + 1);
    const span = { start, end: start + item.surface.length };
    // Segment attestation is only about the observed speaker.  A named person
    // mentioned by that speaker must stay source-local until separately proven.
    const observedSpeaker = claim.observed_speaker_slot_id === item.slot_id;
    const localRef = `source-local:${source.evidence_id}:${span.start}:${span.end}`;
    return [{ mention_id: `mention:${item.claim_revision_id}:${item.slot_id}${seen ? `:${seen}` : ""}`, owner_account_id, claim_revision_id: item.claim_revision_id, span, evidence_id: item.evidence_id, source_identity_ref: observedSpeaker ? source.source_identity_ref ?? sourceLocalIdentity(source.evidence_id, localRef) : sourceLocalIdentity(source.evidence_id, localRef), speaker_rendering: observedSpeaker ? source.speaker_rendering ?? null : null, slot_id: item.slot_id, surface: item.surface, antecedent_handle: item.antecedent_handle, resolution: "unresolved" as const, entity_id: null }];
  });
  for (const claim of request.claims) for (const argument of claim.arguments) {
    if (perSlot.has(`${claim.claim_revision_id}\u0000${argument.slot_id}`)) continue;
    const source = claim.evidence[0]!;
    // Source excerpts are required by request construction.  Preserve a valid,
    // deterministic source span even when a normalized argument surface is not
    // a literal substring of that excerpt.
    const start = Math.max(0, source.excerpt.indexOf(argument.surface));
    const span = { start, end: start + Math.min(Math.max(argument.surface.length, 1), source.excerpt.length - start) };
    mentions.push({
      mention_id: `${forcedUnresolvedPrefix}${claim.claim_revision_id}:${argument.slot_id}`,
      owner_account_id,
      claim_revision_id: claim.claim_revision_id,
      span,
      evidence_id: source.evidence_id,
      source_identity_ref: claim.observed_speaker_slot_id === argument.slot_id ? source.source_identity_ref ?? sourceLocalIdentity(source.evidence_id, `source-local:${source.evidence_id}:${span.start}:${span.end}`) : sourceLocalIdentity(source.evidence_id, `source-local:${source.evidence_id}:${span.start}:${span.end}`),
      speaker_rendering: claim.observed_speaker_slot_id === argument.slot_id ? source.speaker_rendering ?? null : null,
      slot_id: argument.slot_id,
      surface: argument.surface,
      antecedent_handle: null,
      resolution: "unresolved",
      entity_id: null,
    });
  }
  return mentions;
};
