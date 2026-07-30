import type { EntityProposal, EntityResolutionRequest } from "../../core/resolve/entities";
import type { ModelPort } from "./port";

const entityStrategy = "local-handle-durable-entity";

const readContent = (payload: unknown): string => {
  if (!payload || typeof payload !== "object") throw new Error("GLM returned an invalid chat completion payload");
  const content = (payload as { choices?: Array<{ message?: { content?: unknown } }> }).choices?.[0]?.message?.content;
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    const text = content.map((part) => typeof part === "object" && part !== null && "text" in part ? (part as { text?: unknown }).text : "")
      .filter((part): part is string => typeof part === "string").join("");
    if (text) return text;
  }
  throw new Error("GLM chat completion contained no text response");
};

const parseProposal = (content: string): EntityProposal => {
  const json = content.trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  let parsed: unknown;
  try { parsed = JSON.parse(json); } catch { throw new Error(`GLM entity-resolution response was not JSON: ${content.slice(0, 200)}`); }
  if (!parsed || typeof parsed !== "object") throw new Error("GLM entity-resolution response must be an object");
  const proposal = parsed as { decision?: unknown; entity_id?: unknown };
  if (proposal.decision === "same" && typeof proposal.entity_id === "string" && proposal.entity_id.length > 0) return { decision: "same", entity_id: proposal.entity_id };
  if (proposal.decision === "distinct") return { decision: "distinct" };
  if (proposal.decision === "abstain") return { decision: "abstain" };
  throw new Error('GLM entity-resolution response must be {"decision":"same","entity_id":"..."}, {"decision":"distinct"}, or {"decision":"abstain"}');
};

const promptFor = (request: EntityResolutionRequest): string => JSON.stringify({
  task: "Decide how ONE source-local mention resolves, for one personal-memory graph owner.",
  candidates_with_labels: (request.candidate_entities ?? []).map((candidate) => ({ entity_id: candidate.entity_id, labels: candidate.labels })),
  mention_evidence: request.evidence_refs,
  rules: [
    "SAME (return {\"decision\":\"same\",\"entity_id\":<candidate id>}): the mention is clearly the SAME real entity as exactly ONE candidate above. MATCH BY LABEL + CONTEXT, and DO include name variants, diminutives, and spelling/transcription differences when context is consistent (e.g. 'Kristinka'/'Kristin' -> a 'Kristina' candidate; 'omi' -> an 'Omi' candidate). Do not be shy about merging an obvious same-entity variant.",
    "OWNER: the graph owner is the primary speaker. If the mention is the owner's own name, 'the user'/'me', or the primary-speaker / diarization-zero channel ('SPEAKER_00','Speaker 0','Speaker 00'), return same with the OWNER candidate's id.",
    "ABSTAIN (return {\"decision\":\"abstain\"}) for anything that is NOT a specific NAMED person or organization. This includes pronouns ('he','she','him'), generic or relational role nouns ('friend','roommate','the other man','employee','the recipient','current roommate'), categories or plurals ('AI providers','big tech companies','many startups','providers'), non-owner diarization labels ('SPEAKER_01'), 'Unknown'/'Assistant', or insufficient evidence. These are NOT entities — do NOT mint an entity for them.",
    "DISTINCT (return {\"decision\":\"distinct\"}) ONLY for a SPECIFIC NAMED person or organization that matches no candidate. If the mention has no proper name, it is NOT distinct — it is abstain.",
    "Never merge two DIFFERENT real people who merely share a name; if evidence indicates distinct same-named people, return distinct.",
    "Return JSON only: exactly one of {\"decision\":\"same\",\"entity_id\":\"...\"}, {\"decision\":\"distinct\"}, {\"decision\":\"abstain\"}.",
  ],
}, null, 2);

/** Thin OpenAI-compatible GLM edge. The core resolver remains pure. */
export class GlmModel implements ModelPort {
  private readonly baseUrl: string;
  private readonly apiKey: string | undefined;
  private readonly model: string;

  constructor(options: { baseUrl?: string; apiKey?: string; model?: string } = {}) {
    this.baseUrl = (options.baseUrl ?? process.env.OMI_BENCH_OPENAI_BASE_URL ?? "https://api.z.ai/api/paas/v4").replace(/\/$/, "");
    this.apiKey = options.apiKey ?? process.env.GLM_API_KEY ?? process.env.ZAI_API_KEY ?? process.env.OMI_BENCH_OPENAI_API_KEY;
    this.model = options.model ?? process.env.OMI_BENCH_OPENAI_MODEL ?? "glm-4.7";
  }

  async invoke(request: { strategy: string; version: string; input: unknown }): Promise<unknown> {
    if (request.strategy !== entityStrategy) throw new Error(`GlmModel does not support strategy: ${request.strategy}`);
    if (!this.apiKey) throw new Error("GLM API key missing: set GLM_API_KEY, ZAI_API_KEY, or OMI_BENCH_OPENAI_API_KEY");
    const response = await fetch(`${this.baseUrl}/chat/completions`, {
      method: "POST",
      headers: { authorization: `Bearer ${this.apiKey}`, "content-type": "application/json" },
      body: JSON.stringify({ model: this.model, temperature: 0, thinking: { type: "disabled" }, messages: [{ role: "user", content: promptFor(request.input as EntityResolutionRequest) }] }),
    });
    if (!response.ok) throw new Error(`GLM chat completion failed (${response.status}): ${(await response.text()).slice(0, 500)}`);
    return parseProposal(readContent(await response.json()));
  }
}
