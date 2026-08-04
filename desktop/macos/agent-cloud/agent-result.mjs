// Typed inter-agent result contract.
//
// Subagent handoff was prose-only everywhere (kernel DelegateAgentResult.summary
// and the SDK Task result are both free text), so a parent could silently
// misread a child's numbers. This makes a subagent's answer machine-checkable:
// the child emits one fenced ```json block matching AGENT_RESULT_SCHEMA, and
// parseAgentResult() validates it — falling back to prose (never throwing) so a
// non-conforming child degrades instead of breaking the turn.

import { z } from "zod";

// A distilled finding: a headline answer plus the evidence that backs it.
// Kept deliberately small — the point is a lossless handoff of the conclusion,
// not a schema the model has to fight.
export const AgentResultSchema = z.object({
  answer: z.string().min(1).describe("The distilled answer, one to three sentences."),
  findings: z
    .array(
      z.object({
        claim: z.string().min(1),
        evidence: z.string().min(1).describe("Concrete numbers / counts / ranges backing the claim."),
      }),
    )
    .default([]),
  confidence: z.enum(["high", "medium", "low"]).default("medium"),
  data_found: z.boolean().default(true).describe("false when the query returned no relevant data."),
});

// The exact instruction appended to a subagent prompt so its final message
// carries a parseable result. One fenced block, nothing after it.
export const RESULT_INSTRUCTION = `\nFINAL MESSAGE FORMAT — end your reply with exactly one fenced json block and nothing after it:
\`\`\`json
{"answer": "<1-3 sentence distilled answer>",
 "findings": [{"claim": "<what you found>", "evidence": "<concrete counts/ranges>"}],
 "confidence": "high|medium|low",
 "data_found": true}
\`\`\`
The prose before the block is for the human; the json block is consumed by another agent — it must be valid json.`;

const FENCE_RE = /```(?:json)?\s*([\s\S]*?)```/gi;

// Extract the LAST fenced json object from a text blob (the result instruction
// puts it at the end; taking the last avoids grabbing an example the model
// echoed earlier).
function extractLastJsonBlock(text) {
  let match;
  let last = null;
  while ((match = FENCE_RE.exec(text)) !== null) {
    const body = match[1].trim();
    if (body.startsWith("{")) last = body;
  }
  if (last) return last;
  // No fence — try a bare trailing {...} object.
  const brace = text.lastIndexOf("{");
  if (brace !== -1) return text.slice(brace).trim();
  return null;
}

/**
 * Parse a subagent's final text into a validated result.
 * Never throws. Returns:
 *   { ok: true,  value }          on a valid structured result
 *   { ok: false, fallbackText }   on anything else (parent uses the prose)
 */
export function parseAgentResult(text) {
  if (typeof text !== "string" || text.trim() === "") {
    return { ok: false, fallbackText: "" };
  }
  const block = extractLastJsonBlock(text);
  if (!block) return { ok: false, fallbackText: text.trim() };

  let raw;
  try {
    raw = JSON.parse(block);
  } catch {
    return { ok: false, fallbackText: text.trim() };
  }
  const parsed = AgentResultSchema.safeParse(raw);
  if (!parsed.success) return { ok: false, fallbackText: text.trim() };
  return { ok: true, value: parsed.data };
}
