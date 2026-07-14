// AI User Profile — orchestration core (pure-ish, no better-sqlite3, no electron,
// no direct network). Every impurity (HTTP fetch, LLM call, DB read/write,
// backend sync) is injected as a dependency, so this module runs under plain-node
// vitest. service.ts wires the real electron/better-sqlite3 implementations to
// these seams — the same pure-core / electron-wiring split as synthesis.ts (and
// the taskEmbeddingVector pattern the parity audit references).
import type { AiUserProfileInput, AiUserProfileRecord } from '../../../shared/types'
import {
  buildStage1Messages,
  buildStage2Messages,
  enforceCharCap,
  totalSourceItems,
  usedSourceNames,
  type ChatMessage,
  type ProfileSources
} from './synthesis'

/** A source fetch hit an expired/invalid session (HTTP 401/403). Distinct from a
 *  transient/empty source so generation can surface "auth expired" instead of the
 *  misleading "not enough data". Thrown by the injected source fetchers (see
 *  service.ts authedGet) and re-raised out of collectSources. */
export class AuthExpiredError extends Error {
  constructor() {
    super('AI profile: auth expired — awaiting fresh session')
    this.name = 'AuthExpiredError'
  }
}

/** A non-auth HTTP failure. Carries only the status code (never a response body)
 *  so callers can log a status without leaking user data. */
export class HttpError extends Error {
  constructor(readonly status: number) {
    super(`HTTP ${status}`)
    this.name = 'HttpError'
  }
}

/** A safe, PII-free label for a caught fetch/sync error: status code or the error
 *  NAME only — never the message (a malformed-JSON SyntaxError message can echo a
 *  fragment of the user-data response body). */
export function describeError(e: unknown): string {
  if (e instanceof HttpError) return `HTTP ${e.status}`
  return e instanceof Error ? e.name : 'Error'
}

// The two branches below are fail-open: they continue with a UX hit (degraded
// correctness) rather than aborting. Per AGENTS.md ("silent UX healing is allowed;
// silent ops is not") the degraded outcome must be named loudly. There is no
// main-process fallback/telemetry emitter yet (the renderer's PostHog is
// unreachable from main, and Sentry is for hard errors, not fail-open degrades),
// so this is a single structured console.warn for now.
// TODO(track3): route through a Windows recordFallback emitter once one exists.
export function warnDegraded(reason: string, detail: Record<string, unknown> = {}): void {
  console.warn('[ai-profile] fallback', {
    component: 'ai_profile',
    outcome: 'degraded',
    reason,
    ...detail
  })
}

/** Per-source fetchers, each returning already-formatted display lines. A fetcher
 *  throws on failure; collectSources decides how to handle it. */
export type SourceFetchers = {
  memories: () => Promise<string[]>
  tasks: () => Promise<string[]>
  goals: () => Promise<string[]>
  conversations: () => Promise<string[]>
  messages: () => Promise<string[]>
}

// Run one source fetch. A genuine auth expiry aborts the whole generation
// (re-raised); any other failure degrades that single source to [] so a transient
// error on one source never loses the others (Mac parity: per-source resilience).
async function fetchSourceSafe(name: string, fn: () => Promise<string[]>): Promise<string[]> {
  try {
    return await fn()
  } catch (e) {
    if (e instanceof AuthExpiredError) throw e
    // m7: status/name only — never e.message.
    warnDegraded('source_fetch_failed', { source: name, error: describeError(e) })
    return []
  }
}

/** Fetch all five sources in parallel. Rejects with AuthExpiredError if any source
 *  reports an expired session; otherwise degrades failed sources to []. */
export async function collectSources(fetchers: SourceFetchers): Promise<ProfileSources> {
  const [memories, tasks, goals, conversations, messages] = await Promise.all([
    fetchSourceSafe('memories', fetchers.memories),
    fetchSourceSafe('tasks', fetchers.tasks),
    fetchSourceSafe('goals', fetchers.goals),
    fetchSourceSafe('conversations', fetchers.conversations),
    fetchSourceSafe('messages', fetchers.messages)
  ])
  return { memories, tasks, goals, conversations, messages }
}

/** Injected seams for generateProfile — every side effect lives here. */
export type OrchestratorDeps = {
  fetchers: SourceFetchers
  /** Run the synthesis LLM (stage 1, then stage 2 if history exists). */
  chat: (messages: ChatMessage[]) => Promise<string>
  /** Past profile texts, newest-first (up to `limit`), for stage-2 consolidation. */
  listPastProfiles: (limit: number) => string[]
  /** Persist the new profile locally; returns its row id. */
  insertProfile: (rec: AiUserProfileInput) => number
  /** Fire-and-forget backend sync of the generated profile (true item count). */
  syncProfile: (id: number, text: string, generatedAtMs: number, itemCount: number) => Promise<void>
  /** Clock seam (defaults to Date.now). */
  now?: () => number
}

/**
 * Core generation flow (pure-ish; all impurity injected via `deps`):
 *   fetch sources → guard "no data" → stage-1 LLM → stage-2 consolidation (if
 *   history) → char-cap → insert local row → fire-and-forget backend sync.
 *
 * Throws AuthExpiredError when the session is expired, or a "not enough data"
 * Error when every source is empty — in both cases the LLM is never called. A
 * backend sync failure never loses the local row (it is fire-and-forget).
 */
export async function generateProfile(deps: OrchestratorDeps): Promise<AiUserProfileRecord> {
  const sources = await collectSources(deps.fetchers)
  const dataSourcesUsed = usedSourceNames(sources)
  const total = totalSourceItems(sources)
  console.log(
    `[ai-profile] fetched ${total} items (memories=${sources.memories.length}, tasks=${sources.tasks.length}, goals=${sources.goals.length}, convos=${sources.conversations.length}, messages=${sources.messages.length})`
  )
  if (total === 0) throw new Error('AI profile: not enough data to generate a profile')

  const stage1 = await deps.chat(buildStage1Messages(sources))

  // Stage 2: consolidate with up to 5 past profiles (stored newest-first →
  // reverse to oldest-first for the prompt). Skip when there is no history.
  const pastNewestFirst = deps.listPastProfiles(5)
  let finalText = stage1
  if (pastNewestFirst.length > 0) {
    finalText = await deps.chat(buildStage2Messages(stage1, [...pastNewestFirst].reverse()))
  }
  finalText = enforceCharCap(finalText)

  const generatedAt = deps.now ? deps.now() : Date.now()
  const id = deps.insertProfile({
    profileText: finalText,
    dataSourcesUsed,
    generatedAt,
    backendSynced: false
  })
  console.log(`[ai-profile] stored profile #${id} (${finalText.length} chars)`)

  // Fire-and-forget backend sync — a sync failure must NOT lose the local row.
  // `total` is the exact item count Mac reports (data_sources_used).
  void deps
    .syncProfile(id, finalText, generatedAt, total)
    .catch((e) => warnDegraded('backend_sync_failed', { op: 'generate', error: describeError(e) }))

  return { id, profileText: finalText, dataSourcesUsed, generatedAt, backendSynced: false }
}
