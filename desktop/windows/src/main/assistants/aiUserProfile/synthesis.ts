// AI User Profile — pure client-side helpers (no better-sqlite3, no electron, no
// network): the generation cadence, the source bookkeeping and the stored-text
// cap. The prompts and the two-stage consolidation live in the backend behind
// POST /v1/users/ai-profile/synthesize, so Mac and Windows synthesize the same
// document from the same managed model.
//
// Inspired by the ContextAgent paper (arXiv:2505.14668): a once-daily,
// LLM-synthesized "what we know about this user" document, injected as grounding
// context into other AI pipelines (task/goal/memory extraction) — NOT a raw
// memories list.

/** Hard safety-truncate cap on a stored/synced profile. The backend prompt asks
 *  the model for <2000 chars and applies the same ceiling; this is the local
 *  guard so a slight overshoot isn't stored uncapped. (Backend accepts
 *  profile_text up to 50000 chars, so 10000 is safe.) */
export const MAX_PROFILE_CHARS = 10000

/** >24h since the last generation. */
export const GENERATION_INTERVAL_MS = 86_400_000

/** The five data sources, already formatted into display lines by the
 *  orchestrator. A missing/failed source is simply an empty array. */
export type ProfileSources = {
  memories: string[]
  tasks: string[]
  goals: string[]
  conversations: string[]
  messages: string[]
}

/** Should we generate a new profile? True when never generated, or >24h ago. */
export function shouldGenerate(latestGeneratedAtMs: number | null, nowMs: number): boolean {
  if (latestGeneratedAtMs == null) return true
  return nowMs - latestGeneratedAtMs > GENERATION_INTERVAL_MS
}

/** Total number of data items across all sources. This is Mac's
 *  `dataSourcesUsed` — used both to detect the "insufficient data" case (all
 *  sources empty) and as the exact value sent to the backend's
 *  `data_sources_used` int field (Mac parity: a total item count, not a count
 *  of source *types*). */
export function totalSourceItems(sources: ProfileSources): number {
  return (
    sources.memories.length +
    sources.tasks.length +
    sources.goals.length +
    sources.conversations.length +
    sources.messages.length
  )
}

/** Names of the sources that contributed at least one item — the "rich array"
 *  stored locally in AiUserProfileRecord.dataSourcesUsed. */
export function usedSourceNames(sources: ProfileSources): string[] {
  const names: string[] = []
  if (sources.memories.length) names.push('memories')
  if (sources.tasks.length) names.push('tasks')
  if (sources.goals.length) names.push('goals')
  if (sources.conversations.length) names.push('conversations')
  if (sources.messages.length) names.push('messages')
  return names
}

/** Hard-cap a profile at `cap` characters (trailing whitespace trimmed). Mirrors
 *  the backend's enforce_char_cap. */
export function enforceCharCap(text: string, cap: number = MAX_PROFILE_CHARS): string {
  if (text.length <= cap) return text
  return text.slice(0, cap).trimEnd()
}
