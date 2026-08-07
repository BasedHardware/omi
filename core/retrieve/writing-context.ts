import { compareStrings } from "../order";
import { sha256CanonicalRedacted } from "../ledger";
import type { GraphSnapshot } from "./index";
import { projectTreeInputSnapshot } from "./index";

/**
 * Bookkeeping ids (`predicate_id`, `ref`, `canonical_claim_id`) live here for
 * dependency-manifest and invalidation purposes ONLY. No consumer may put them
 * in front of a model: a 72-session run showed a model matching the output
 * field `predicate_ref` to the context field `predicate_id` and copying raw
 * sha256 ids into 36% of its emissions, which were then re-hashed into display
 * names and fed back in as context. Projection to a model happens in
 * `core/extract/grounded`, and it sends names only.
 */
export interface WritingContext {
  frontier: { graph_head: string; policy_version: string; predicate_alias_generation: string; authorization_generation: string; stm_generation: string };
  entity_candidates: readonly { ref: string; lifecycle: "canonical" | "provisional"; renderings: readonly string[]; profile: readonly string[]; provenance: readonly { claim_revision_id: string; evidence_refs: readonly string[] }[] | null; last_seen: string; basis: string }[];
  predicate_signatures: readonly { predicate_id: string; name: string; slots: readonly string[]; use_count: number; example: string }[];
  open_propositions: readonly { proposition_key_resolved: string; canonical_claim_id: string; text: string; valid_time: unknown }[];
}

/** A name that is really an id has lost its provenance; readable text can never round-trip out of a digest. */
export const isOpaqueIdentifier = (value: string): boolean => /^[0-9a-f]{24,}$/i.test(value) || /^[a-z_-]+:[0-9a-f]{24,}$/i.test(value);
export interface WritingContextRequest {
  account_timezone: string; policy_version: string; predicate_alias_generation: string; authorization_generation: string; stm_generation: string;
  /** Current capture terms order candidates; the read projection remains the sole data source. */
  window?: { text: string; start_at?: string; end_at?: string };
}

const terms = (text: string): readonly string[] => [...new Set((text.toLocaleLowerCase().match(/[\p{L}\p{N}_-]+/gu) ?? []).filter((term) => term.length > 1))];
const claimText = (claim: ReturnType<typeof projectTreeInputSnapshot>["claims"][number]): string => `${claim.predicate}(${claim.arguments.map((argument) => `${argument.role}=${argument.surface ?? (argument.value.kind === "literal" ? String(argument.value.value) : argument.value.ref)}`).join(", ")})${claim.polarity === "negative" ? " [not]" : ""}`;
const relevance = (values: readonly string[], queryTerms: readonly string[]): number => queryTerms.reduce((score, term) => score + values.reduce((matches, value) => matches + (value.toLocaleLowerCase().includes(term) ? 1 : 0), 0), 0);

/** Composes the existing read projection; this module intentionally owns no storage reach. */
export const getWritingContext = (snapshot: GraphSnapshot, request: WritingContextRequest): WritingContext => {
  const view = projectTreeInputSnapshot(snapshot, { account_timezone: request.account_timezone });
  const claims = view.claims;
  const queryTerms = terms(request.window?.text ?? "");
  const entities = new Map(snapshot.entities.map(({ entity }) => [entity.entity_id, [entity.handle, ...entity.labels]]));
  const candidates = new Map<string, { ref: string; lifecycle: "canonical" | "provisional"; renderings: string[]; profile: string[]; provenance: { claim_revision_id: string; evidence_refs: readonly string[] }[] | null; last_seen: string; basis: string }>();
  for (const claim of claims) for (const argument of claim.arguments) if (argument.value.kind === "entity_ref" || argument.value.kind === "source_local_ref") {
    // Candidate renderings are derived from this exact revision and its cited
    // sources; the extraction manifest must be able to invalidate both.
    const ref = argument.value.ref; const current = candidates.get(ref) ?? { ref, lifecycle: claim.canonical_claim_id ? "canonical" : "provisional", renderings: argument.value.kind === "entity_ref" ? [...(entities.get(ref) ?? [])] : argument.surface ? [argument.surface] : [], profile: [], provenance: [{ claim_revision_id: claim.claim_revision_id, evidence_refs: claim.evidence_refs }], last_seen: claim.observed_at, basis: "retrieval-claim-role" };
    if (current.provenance && !current.provenance.some((entry) => entry.claim_revision_id === claim.claim_revision_id)) current.provenance.push({ claim_revision_id: claim.claim_revision_id, evidence_refs: claim.evidence_refs });
    const text = claimText(claim); if (!current.profile.includes(text) && current.profile.length < 5) current.profile.push(text); if (claim.observed_at > current.last_seen) current.last_seen = claim.observed_at; candidates.set(ref, current);
  }
  const predicateStats = new Map<string, { count: number; slots: Set<string>; example: string }>();
  for (const claim of claims) { const predicateId = claim.predicate_id ?? `raw:${claim.predicate}`; const current = predicateStats.get(predicateId) ?? { count: 0, slots: new Set<string>(), example: claim.predicate }; current.count++; for (const argument of claim.arguments) current.slots.add(argument.slot_id); predicateStats.set(predicateId, current); }
  const frontier = { graph_head: String(snapshot.graph_generation ?? "snapshot"), policy_version: request.policy_version, predicate_alias_generation: request.predicate_alias_generation, authorization_generation: request.authorization_generation, stm_generation: request.stm_generation };
  return { frontier,
    entity_candidates: [...candidates.values()].sort((a, b) => relevance([...a.renderings, ...a.profile], queryTerms) - relevance([...b.renderings, ...b.profile], queryTerms) || compareStrings(a.ref, b.ref)).reverse().slice(0, 20),
    // `name` falls back to the extracted predicate spelling, never to the
    // predicate_id: a sha256 shown as a name is what let one poisoned emission
    // re-enter the next window's context and poison the cycle after it. A
    // signature whose display name is already an id is dropped rather than
    // shown, which breaks that loop for graphs that were written before this.
    predicate_signatures: [...predicateStats].map(([predicate_id, item]) => ({ predicate_id, name: snapshot.predicates?.find((candidate) => candidate.predicate.predicate_id === predicate_id)?.predicate.display_name ?? item.example, slots: [...item.slots].sort(), use_count: item.count, example: item.example })).filter((signature) => !isOpaqueIdentifier(signature.name)).sort((a, b) => relevance([a.name, a.example, ...a.slots], queryTerms) - relevance([b.name, b.example, ...b.slots], queryTerms) || compareStrings(a.predicate_id, b.predicate_id)).reverse().slice(0, 30),
    open_propositions: claims.filter((claim) => claim.canonical_claim_id !== null).map((claim) => ({ proposition_key_resolved: claim.proposition_key_resolved ?? sha256CanonicalRedacted({ predicate_id: claim.predicate_id ?? `raw:${claim.predicate}`, arguments: claim.arguments }), canonical_claim_id: claim.canonical_claim_id!, text: claimText(claim), valid_time: claim.valid_time })).sort((a, b) => relevance([a.text], queryTerms) - relevance([b.text], queryTerms) || compareStrings(a.canonical_claim_id, b.canonical_claim_id)).reverse().slice(0, 20),
  };
};
