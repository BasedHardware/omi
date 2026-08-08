// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMCORE-012)
import type { RenderModelPort } from "../../../core/retrieve/render";

/**
 * Hermetic QA synthesizer standing in for a production render model.
 *
 * It runs NO model, makes NO network call, reads NO clock, and draws NO
 * randomness: the same projected input yields byte-identical summaries on every
 * host, every run. That determinism is the point - it is what lets the recall
 * flow be proven end to end without a model in the loop.
 *
 * It makes no ranking, phrasing, or product claim. The wording below is
 * placeholder presentation for QA and is expected to be replaced wholesale by a
 * real synthesis strategy.
 */

/** The exact subset of a projected claim this synthesizer is allowed to read. */
interface SynthesizerClaimView {
  readonly claim_revision_id: string;
  readonly predicate: string;
  readonly observed_at: string;
  readonly evidence_refs: readonly string[];
  readonly arguments: readonly { readonly role: string; readonly value: unknown }[];
}

interface SynthesizerNodeView {
  readonly node_id: string;
  readonly view_kind: string;
  readonly anchor_key: string;
}

const compareStrings = (left: string, right: string): number =>
  left < right ? -1 : left > right ? 1 : 0;

const isPlainRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);

/** Renders one argument without ever emitting raw evidence text or an excerpt. */
// domain-pending(DIV-DOMCORE-007)
const argumentPhrase = (value: unknown): string | null => {
  if (!isPlainRecord(value)) return null;
  const kind = value.kind;
  if (kind === "entity_ref" && typeof value.ref === "string" && value.ref.length > 0) return value.ref;
  if (kind === "literal" && typeof value.value === "string" && value.value.length > 0) return value.value;
  return null;
};

/**
 * Builds a stable human-readable proposition from projected claim structure
 * only. Evidence excerpts are deliberately NOT consulted: the summary must be
 * derivable from the authorized projection, never from raw source content.
 */
// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-012)
const summarize = (
  node: SynthesizerNodeView,
  claims: readonly SynthesizerClaimView[],
): string => {
  if (claims.length === 0) return `No proposition is projected for ${node.view_kind} anchor.`;
  const sentences = [...claims]
    .sort((left, right) => compareStrings(left.claim_revision_id, right.claim_revision_id))
    .map((claim) => {
      const subjects = claim.arguments
        .map((argument) => argumentPhrase(argument.value))
        .filter((phrase): phrase is string => phrase !== null);
      const subject = subjects.length > 0 ? subjects.join(", ") : "an unnamed subject";
      return `${subject} ${claim.predicate} (observed ${claim.observed_at})`;
    });
  return `${sentences.join("; ")}.`;
};

const readClaims = (value: unknown): readonly SynthesizerClaimView[] => {
  if (!Array.isArray(value)) return [];
  const claims: SynthesizerClaimView[] = [];
  for (const item of value) {
    if (!isPlainRecord(item)) continue;
    const revision = item.claim_revision_id;
    const predicate = item.predicate;
    const observedAt = item.observed_at;
    const refs = item.evidence_refs;
    if (typeof revision !== "string" || typeof predicate !== "string"
      || typeof observedAt !== "string" || !Array.isArray(refs)) continue;
    const args = Array.isArray(item.arguments) ? item.arguments : [];
    claims.push({
      claim_revision_id: revision,
      predicate,
      observed_at: observedAt,
      evidence_refs: refs.filter((ref): ref is string => typeof ref === "string"),
      arguments: args.filter(isPlainRecord).map((argument) => ({
        role: typeof argument.role === "string" ? argument.role : "",
        value: argument.value,
      })),
    });
  }
  return claims;
};

/**
 * Creates the deterministic QA render model.
 *
 * Citations are the sorted unique union of the node's member-claim evidence
 * references. That is not a stylistic choice: the projection boundary
 * recomputes exactly this set from the authorized projection and rejects any
 * render whose citation set differs, so emitting anything else fails closed.
 */
export const createQaDeterministicSynthesizer = (): RenderModelPort => ({
  render: async (request) => {
    const input = request.input;
    if (!isPlainRecord(input)) {
      throw new TypeError("QA synthesizer requires a plain render request input");
    }
    const rawNode = input.node;
    if (!isPlainRecord(rawNode) || typeof rawNode.node_id !== "string") {
      throw new TypeError("QA synthesizer requires a structural node");
    }
    const node: SynthesizerNodeView = {
      node_id: rawNode.node_id,
      view_kind: typeof rawNode.view_kind === "string" ? rawNode.view_kind : "unknown",
      anchor_key: typeof rawNode.anchor_key === "string" ? rawNode.anchor_key : "",
    };
    const claims = readClaims(input.claims);
    const citations = [...new Set(claims.flatMap((claim) => [...claim.evidence_refs]))].sort(compareStrings);
    return {
      summary_text: summarize(node, claims),
      citations,
    };
  },
});
