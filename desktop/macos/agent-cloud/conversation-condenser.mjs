// Non-destructive conversation condensation.
//
// The persistent session feeds one growing conversation into a single long
// SDK query(); it grows until "prompt too long" (or hits maxTurns) and the
// session dies. The field pattern (OpenHands condenser; Anthropic compaction)
// is: when history grows too large, summarize the OLD turns and reinitialize a
// smaller context — but keep the raw turns retrievable so nothing is lost
// (the recency memory research: verbatim beats summary by 15-22 pts, so we
// keep recent turns verbatim and archive — never discard — the rest).
//
// This module is pure and deterministic: it decides WHAT to condense and
// builds the reseed prompt. The actual summary text comes from an injected
// summarizer (real model in prod, stub in tests), so the policy is testable
// without a live model.

// Rough token proxy: ~4 chars/token. Good enough for a budget trigger.
export function estimateChars(turns) {
  return turns.reduce((n, t) => n + (t.user?.length || 0) + (t.assistant?.length || 0), 0);
}

/**
 * Decide whether to condense, and how.
 * @param turns  [{ user, assistant }]  full conversation so far (oldest first)
 * @param opts   { maxChars, keepRecent }
 * @returns { condense:false } OR
 *          { condense:true, summarize:[turns], keep:[turns], archive:[turns] }
 *          - summarize: old turns to fold into a summary
 *          - keep: recent turns preserved VERBATIM (never summarized)
 *          - archive: same turns as `summarize`, retained for retrieval
 */
export function planCondensation(turns, { maxChars = 60000, keepRecent = 4 } = {}) {
  if (!Array.isArray(turns) || turns.length === 0) return { condense: false };
  // Only condense when over budget AND there is something old enough to fold.
  if (estimateChars(turns) <= maxChars) return { condense: false };
  if (turns.length <= keepRecent) return { condense: false }; // nothing old to summarize yet
  const cut = turns.length - keepRecent;
  const summarize = turns.slice(0, cut);
  const keep = turns.slice(cut);
  return { condense: true, summarize, keep, archive: summarize };
}

/**
 * Build the reseed prompt for a fresh query: a compact summary of old turns
 * followed by the recent turns verbatim. This becomes the first user message
 * of the new context window.
 */
export function buildCondensedSeed(summaryText, keptTurns) {
  const recent = keptTurns
    .map((t) => `User: ${t.user}\nAssistant: ${t.assistant}`)
    .join("\n\n");
  return (
    `# Conversation so far (condensed)\n${summaryText}\n\n` +
    `# Most recent exchanges (verbatim)\n${recent}\n\n` +
    `Continue the conversation using this context. If you need older detail not in the summary, ` +
    `say so — the full history is archived and retrievable.`
  );
}

/**
 * Non-destructive archive: append the condensed-away turns so they remain
 * retrievable verbatim. Returns the new archive (does not mutate input).
 */
export function appendArchive(archive, turns) {
  return [...(archive || []), ...turns];
}

/**
 * Retrieve raw archived turns matching a query (case-insensitive substring
 * over user+assistant text). This is the "the summary dropped a detail — go
 * get it verbatim" escape hatch that makes condensation non-destructive.
 */
export function searchArchive(archive, query, limit = 5) {
  if (!archive?.length || !query) return [];
  const q = query.toLowerCase();
  return archive
    .filter((t) => `${t.user || ""}\n${t.assistant || ""}`.toLowerCase().includes(q))
    .slice(-limit);
}
