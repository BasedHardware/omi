import { DeterministicFakeModel, type ModelInvokeRequest, type ModelPort } from "../../../drivers/model/port";

const EVIDENCE_BLOCK = /\[BEGIN [^\]]+ evidence_id=([A-Za-z0-9]+)[^\]]*\]\n([\s\S]*?)\n\[END /g;
/** Printable ASCII token: formation outcome ids cannot contain spaces. */
const SCRIPTED_RELATION = "notes";

const claimFromExcerpt = (excerpt: string): { surface: string } | null => {
  const text = excerpt.trim();
  if (text.length === 0) return null;
  return { surface: text };
};

const groundedFromPrompt = (prompt: string): { claims: readonly Record<string, unknown>[] } => {
  const claims: Record<string, unknown>[] = [];
  for (const match of prompt.matchAll(EVIDENCE_BLOCK)) {
    const evidence = match[1]!;
    const excerpt = match[2] ?? "";
    const fact = claimFromExcerpt(excerpt);
    if (fact === null) continue;
    claims.push({
      relation: SCRIPTED_RELATION,
      arguments: [{ slot_id: "subject", role: "subject", surface: fact.surface }],
      polarity: "positive",
      temporal_expression: { kind: "imprecise", bucket: "unknown", precision: "coarse" },
      evidence,
      observed_speaker_slot_id: null,
    });
  }
  return { claims };
};

/**
 * Local canned model. It never calls a network provider.
 *
 * Grounded extraction copies the excerpt verbatim into the argument surface so
 * the QA synthesizer can speak the user's words after promotion. The relation
 * is the ASCII token `notes` because `claim_revision_id` is a printable-ASCII
 * token (no spaces) in the formation outcome envelope. This is structure, not
 * a filter: the user's content is kept.
 */
export const createScriptedFormationModel = (): ModelPort =>
  new DeterministicFakeModel((request: ModelInvokeRequest) => {
    if (request.strategy === "grounded-extraction") {
      const prompt = typeof request.input === "object" && request.input !== null
        && "prompt" in request.input && typeof (request.input as { prompt?: unknown }).prompt === "string"
        ? (request.input as { prompt: string }).prompt
        : typeof request.input === "string" ? request.input : "";
      return groundedFromPrompt(prompt);
    }
    if (request.strategy === "local-handle-durable-entity") {
      return { decision: "abstain" };
    }
    if (request.strategy === "scope-role-binding") {
      const input = request.input as { entity_role_slots?: readonly unknown[] } | undefined;
      const slots = Array.isArray(input?.entity_role_slots)
        ? input.entity_role_slots.filter((slot): slot is string => typeof slot === "string")
        : [];
      return {
        bindings: Object.fromEntries(slots.map((slot) => [slot, null])),
        scope: { locality: "durable", scope_ref: "global" },
      };
    }
    if (request.strategy === "stm-ltm-unit-boundary") {
      return { decision: "accept_ltm" };
    }
    throw new Error(`scripted formation model has no response for ${request.strategy}`);
  });
