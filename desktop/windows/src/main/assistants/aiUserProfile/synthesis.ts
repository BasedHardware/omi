// AI User Profile — pure synthesis logic (no better-sqlite3, no electron, no
// network). This is the faithful Windows port of the macOS
// Services/AIUserProfileService.swift prompt/consolidation layer. Everything
// here is deterministic and unit-tested; the orchestrator (service.ts) owns the
// data fetching, DB writes, and backend sync (which pull in electron/better-
// sqlite3 and can't run under plain-node vitest — the same split as
// taskEmbeddingVector).
//
// Inspired by the ContextAgent paper (arXiv:2505.14668): a once-daily,
// LLM-synthesized "what we know about this user" document, injected as grounding
// context into other AI pipelines (task/goal/memory extraction) — NOT a raw
// memories list.

/** OpenAI-shaped chat message (system/user only — no assistant turns here). */
export type ChatMessage = { role: 'system' | 'user'; content: string }

/** Hard safety-truncate cap on a stored/synced profile. Mac's prompt asks the
 *  model for <2000 chars, but the enforced hard cap is 10000 — a generous
 *  ceiling so a slight model overshoot isn't cut mid-sentence. (Backend
 *  accepts profile_text up to 50000 chars, so 10000 is safe.) */
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

// Stage-1 system prompt — ported verbatim from AIUserProfileService.swift
// (generateProfile → systemPrompt). Third person, only directly-evidenced
// facts, no adjectives/personality, no hallucinated contact info, <2000 chars.
export const STAGE1_SYSTEM_PROMPT = `You are generating a structured user profile that will be injected as context into AI pipelines (task extraction, goal extraction, memory extraction) that analyze the user's screen and audio activity.

OUTPUT FORMAT:
- A flat list of factual statements, one per line, prefixed with "- "
- Each statement must be a concrete fact directly supported by the provided data
- No prose, no paragraphs, no headers, no markdown formatting
- No adjectives like "passionate", "dedicated", "impressive"
- Write in third person ("User works at...", not "You work at...")

WHAT TO INCLUDE (only if clearly supported by the data):
- Full name, role, company, industry
- Current projects and what tools/apps they use for each
- Key people they interact with (names, roles, relationship)
- Active goals and their progress
- Recurring meetings, deadlines, routines
- Communication platforms they use (Slack, email, iMessage, etc.)
- Technical stack, programming languages, frameworks
- Topics they frequently discuss or research
- Pending tasks and commitments to others
- Time zone, work schedule patterns

CRITICAL RULES:
- ONLY include facts that are directly evidenced in the provided data
- If a category has no supporting data, skip it entirely — do not guess or infer
- Do NOT hallucinate names, roles, companies, or relationships not present in the data
- Do NOT add personality descriptions or subjective assessments
- When uncertain, omit rather than speculate
- NEVER fabricate email addresses, phone numbers, URLs, or contact information
- The provided data contains NO email addresses — do not invent any
- If you cannot find a piece of information verbatim in the data, do not include it

The output MUST be under 2000 characters total.`

// Stage-2 system prompt — ported verbatim from AIUserProfileService.swift
// (consolidationSystemPrompt). Accumulate stable knowledge, drop stale items.
export const STAGE2_SYSTEM_PROMPT = `You are merging a newly generated user profile with historical profiles to create one holistic, up-to-date user profile. This profile is injected as context into AI pipelines (task extraction, goal extraction, memory extraction) that analyze the user's screen and audio activity.

OUTPUT FORMAT:
- A flat list of factual statements, one per line, prefixed with "- "
- Each statement must be a concrete fact
- No prose, no paragraphs, no headers, no markdown formatting
- No adjectives or subjective assessments
- Write in third person

MERGE RULES:
- The NEW profile reflects today's data and takes priority for current state
- Past profiles provide historical context — retain facts that are still relevant
- If a fact from the past contradicts the new profile, use the new one
- Remove outdated information (completed tasks, past deadlines, old routines)
- Keep stable facts (name, role, company, key relationships, tech stack)
- Accumulate knowledge: if past profiles mention people, projects, or patterns not in today's data, keep them if they seem ongoing
- Do NOT hallucinate — only include facts present in the provided profiles
- Do NOT add commentary about changes or evolution over time

The output MUST be under 2000 characters total.`

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

// Build the stage-1 data-dump user prompt — ported from Swift buildPrompt: only
// non-empty sections, each under a "## " header.
function buildStage1UserPrompt(sources: ProfileSources): string {
  const sections: string[] = []
  if (sources.memories.length)
    sections.push(`## Memories about the user\n${sources.memories.join('\n')}`)
  if (sources.tasks.length) sections.push(`## Recent tasks\n${sources.tasks.join('\n')}`)
  if (sources.goals.length) sections.push(`## Active goals\n${sources.goals.join('\n')}`)
  if (sources.conversations.length)
    sections.push(`## Recent conversations (past 7 days)\n${sources.conversations.join('\n')}`)
  if (sources.messages.length)
    sections.push(`## Recent AI chat messages\n${sources.messages.join('\n')}`)

  return `Generate a factual user profile from the following data. Output a flat list of concrete facts (one per line, prefixed with "- "). This profile will be used as context for AI pipelines that analyze the user's screen and audio activity to extract tasks, goals, and memories. Focus on facts that help identify who is who, what projects are active, and what the user's current priorities are. Under 2000 characters.

${sections.join('\n\n')}`
}

/** Stage 1: synthesize a fresh profile from the raw data sources. */
export function buildStage1Messages(sources: ProfileSources): ChatMessage[] {
  return [
    { role: 'system', content: STAGE1_SYSTEM_PROMPT },
    { role: 'user', content: buildStage1UserPrompt(sources) }
  ]
}

// Build the stage-2 consolidation user prompt — ported from Swift
// buildConsolidationPrompt. `pastProfiles` is oldest→newest (up to 5).
function buildStage2UserPrompt(freshProfileText: string, pastProfiles: string[]): string {
  const pastSection = pastProfiles
    .map((text, i) => `--- Profile ${i + 1} ---\n${text}`)
    .join('\n\n')

  return `Merge the following into one holistic user profile. Under 2000 characters.

=== NEW PROFILE (generated today from latest data) ===
${freshProfileText}

=== PAST PROFILES (oldest to newest, up to 5) ===
${pastSection}`
}

/** Stage 2: consolidate the fresh profile with up to 5 past profiles
 *  (oldest→newest) so knowledge accumulates. */
export function buildStage2Messages(
  freshProfileText: string,
  pastProfiles: string[]
): ChatMessage[] {
  return [
    { role: 'system', content: STAGE2_SYSTEM_PROMPT },
    { role: 'user', content: buildStage2UserPrompt(freshProfileText, pastProfiles) }
  ]
}

/** Hard-cap a profile at `cap` characters (trailing whitespace trimmed). Mirrors
 *  Swift's String(text.prefix(maxProfileLength)). */
export function enforceCharCap(text: string, cap: number = MAX_PROFILE_CHARS): string {
  if (text.length <= cap) return text
  return text.slice(0, cap).trimEnd()
}
