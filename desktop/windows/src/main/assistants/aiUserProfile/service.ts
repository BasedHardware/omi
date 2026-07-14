// AI User Profile — orchestrator (main process). Fetches the five data sources
// in parallel, runs the two-stage LLM synthesis (synthesis.ts), stores the
// profile locally (full history), and fire-and-forget syncs the current profile
// to the backend. Faithful port of macOS AIUserProfileService.generateProfile.
//
// TOKEN MODEL (Windows-specific): unlike macOS, the Firebase auth token lives in
// the RENDERER, not the main process. So this service can't mint its own token —
// the renderer supplies a session ({apiBase, desktopApiBase, token}) via IPC
// (same pattern as memories:bulkDelete / memoryExport:notion). We cache the last
// session so the daily background timer can reuse it; a missing/expired session
// makes background generation a soft no-op that defers to the next
// renderer-driven trigger. See docs note in index.ts wiring.
import { net } from 'electron'
import {
  deleteAiUserProfile,
  deleteAllAiUserProfiles,
  insertAiUserProfile,
  latestAiUserProfile,
  listAiUserProfiles,
  markAiUserProfileSynced,
  updateAiUserProfileText
} from '../../ipc/db'
import { getAppSettings } from '../../appSettings'
import type { AiUserProfileRecord } from '../../../shared/types'
import { shouldGenerate, type ChatMessage } from './synthesis'
import {
  AuthExpiredError,
  HttpError,
  describeError,
  generateProfile,
  warnDegraded,
  type SourceFetchers
} from './orchestrate'

/** Credentials the renderer hands the main process to reach the backend. */
export type AiProfileSession = {
  /** Python backend base (VITE_OMI_API_BASE) — data sources + ai-profile sync. */
  apiBase: string
  /** Rust desktop backend base (VITE_OMI_DESKTOP_API_BASE) — chat/completions. */
  desktopApiBase: string
  /** Fresh Firebase ID token. */
  token: string
}

// ModelQoS.Claude.synthesis on desktop — the cheap synthesis tier Windows
// already uses for memory-log/calendar/gmail import (src/renderer/.../memoryExtract.ts).
const SYNTHESIS_MODEL = 'claude-haiku-4-5-20251001'

const CONVERSATIONS_LOOKBACK_MS = 7 * 86_400_000
// Re-check every 6h (not exactly 24h) so a session that arrives after startup
// triggers a due generation on the next tick; shouldGenerate() still gates the
// actual >24h cadence, so this never over-generates.
const CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000
const REQUEST_TIMEOUT_MS = 30_000
const LLM_TIMEOUT_MS = 60_000

let cachedSession: AiProfileSession | null = null
let isGenerating = false
let timer: ReturnType<typeof setInterval> | null = null

/** Set/refresh (or clear, on null) the cached backend session. Called by the
 *  IPC layer whenever the renderer provides fresh credentials. */
export function configureAiProfileSession(session: AiProfileSession | null): void {
  cachedSession = session
}

// --- HTTP helpers -----------------------------------------------------------

// Shared abort-on-timeout wrapper — every net.fetch call below (authedGet,
// runChat, syncToBackend) needs the same AbortController + timer dance to cap
// a hung request; this is the one place that owns it.
async function withTimeout<T>(ms: number, fn: (signal: AbortSignal) => Promise<T>): Promise<T> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), ms)
  try {
    return await fn(ctrl.signal)
  } finally {
    clearTimeout(timer)
  }
}

// Electron's net.fetch uses Chromium's network stack (proxy/TLS aware) — the
// same path the renderer's axios uses.
async function authedGet(session: AiProfileSession, path: string): Promise<unknown> {
  return withTimeout(REQUEST_TIMEOUT_MS, async (signal) => {
    const res = await net.fetch(`${session.apiBase}${path}`, {
      method: 'GET',
      headers: { Authorization: `Bearer ${session.token}` },
      signal
    })
    // Distinguish an expired/invalid session from genuine no-data so generation
    // can abort with a clear signal instead of the misleading "not enough data".
    if (res.status === 401 || res.status === 403) throw new AuthExpiredError()
    if (!res.ok) throw new HttpError(res.status)
    return await res.json()
  })
}

// --- Data sources -----------------------------------------------------------
//
// Each fetcher throws on failure; the orchestrator's collectSources() owns the
// resilience policy (auth expiry aborts; any other failure degrades that one
// source to []). Keeping the try/catch out of here means the per-source logging
// (status/name only — never a response body) lives in exactly one place.

function asArray<T>(data: unknown, key: string): T[] {
  if (Array.isArray(data)) return data as T[]
  const nested = (data as Record<string, unknown> | null)?.[key]
  return Array.isArray(nested) ? (nested as T[]) : []
}

async function fetchMemories(session: AiProfileSession): Promise<string[]> {
  const data = await authedGet(session, '/v3/memories?limit=100&offset=0')
  const items = asArray<{ content?: string; category?: string }>(data, 'memories')
  return items
    .slice(0, 100)
    .map((m) => `[${m.category ?? 'other'}] ${m.content ?? ''}`.trim())
    .filter((s) => s.length > 3)
}

async function fetchTasks(session: AiProfileSession): Promise<string[]> {
  const data = await authedGet(session, '/v1/action-items?limit=50&offset=0')
  // Windows ActionItemResponse has no `priority` field (Mac does) — omit it.
  const items = asArray<{ description?: string; completed?: boolean }>(data, 'action_items')
  return items
    .slice(0, 50)
    .map((t) => `[${t.completed ? 'done' : 'todo'}] ${t.description ?? ''}`.trim())
    .filter((s) => s.length > 7)
}

async function fetchGoals(session: AiProfileSession): Promise<string[]> {
  // /v1/goals/all returns active + completed; we keep active only (Mac parity).
  const data = await authedGet(session, '/v1/goals/all')
  const goals = asArray<{
    title?: string
    target_value?: number
    current_value?: number
    is_active?: boolean
  }>(data, 'goals')
  return goals
    .filter((g) => g.is_active !== false && g.title)
    .map((g) => {
      const target = g.target_value ?? 0
      const progress = target > 0 ? Math.round(((g.current_value ?? 0) / target) * 100) : 0
      return `${g.title} (${progress}% complete)`
    })
}

async function fetchConversations(session: AiProfileSession): Promise<string[]> {
  const data = await authedGet(
    session,
    '/v1/conversations?limit=20&offset=0&statuses=completed,processing'
  )
  const convos = asArray<{
    created_at?: string
    structured?: { title?: string; overview?: string }
  }>(data, 'conversations')
  const cutoff = Date.now() - CONVERSATIONS_LOOKBACK_MS
  return convos
    .filter((c) => {
      // Keep past-7-days only (Mac passes startDate); tolerate a missing date.
      const t = c.created_at ? new Date(c.created_at).getTime() : NaN
      return Number.isNaN(t) || t >= cutoff
    })
    .map((c) => {
      const title = c.structured?.title ?? ''
      const summary = c.structured?.overview ?? ''
      return title ? `${title}: ${summary}` : ''
    })
    .filter((s) => s.length > 0)
}

async function fetchMessages(session: AiProfileSession): Promise<string[]> {
  const data = await authedGet(session, '/v2/messages')
  const messages = asArray<{ sender?: string; text?: string }>(data, 'messages')
  return messages
    .slice(0, 30)
    .map((m) => `[${m.sender ?? 'ai'}] ${m.text ?? ''}`.trim())
    .filter((s) => s.length > 5)
}

function makeFetchers(session: AiProfileSession): SourceFetchers {
  return {
    memories: () => fetchMemories(session),
    tasks: () => fetchTasks(session),
    goals: () => fetchGoals(session),
    conversations: () => fetchConversations(session),
    messages: () => fetchMessages(session)
  }
}

// --- LLM + backend sync -----------------------------------------------------

async function runChat(session: AiProfileSession, messages: ChatMessage[]): Promise<string> {
  return withTimeout(LLM_TIMEOUT_MS, async (signal) => {
    const res = await net.fetch(`${session.desktopApiBase}/v2/chat/completions`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${session.token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ model: SYNTHESIS_MODEL, stream: false, messages }),
      signal
    })
    if (!res.ok) throw new Error(`chat/completions HTTP ${res.status}`)
    const json = (await res.json()) as {
      choices?: { message?: { content?: string } }[]
    }
    const content = json?.choices?.[0]?.message?.content ?? ''
    if (!content.trim()) throw new Error('chat/completions returned empty content')
    return content.trim()
  })
}

// `dataSourceItemCount` is the backend's `data_sources_used` INT — Mac sends
// the total item count across all sources (see totalSourceItems), not the
// count of source *types* that contributed. It is OMITTED entirely on a
// text-only edit: the backend's PATCH applies each field only when non-null
// (backend/database/users.py update_ai_user_profile), so omitting the key
// preserves the stored count instead of clobbering it with a wrong value.
// Only the generate path knows the true count and passes it.
async function syncToBackend(
  session: AiProfileSession,
  id: number,
  profileText: string,
  generatedAtMs: number,
  dataSourceItemCount?: number
): Promise<void> {
  return withTimeout(REQUEST_TIMEOUT_MS, async (signal) => {
    const body: Record<string, unknown> = {
      profile_text: profileText,
      generated_at: new Date(generatedAtMs).toISOString()
    }
    if (dataSourceItemCount !== undefined) body.data_sources_used = dataSourceItemCount
    const res = await net.fetch(`${session.apiBase}/v1/users/ai-profile`, {
      method: 'PATCH',
      headers: {
        Authorization: `Bearer ${session.token}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(body),
      signal
    })
    if (!res.ok) throw new HttpError(res.status)
    markAiUserProfileSynced(id)
    console.log('[ai-profile] synced profile to backend')
  })
}

// --- Public API -------------------------------------------------------------

/** Generate a new profile now. Uses the provided session, else the cached one.
 *  Throws if no session is available or if there is no data to synthesize. */
export async function generateNow(session?: AiProfileSession): Promise<AiUserProfileRecord> {
  const active = session ?? cachedSession
  if (!active) throw new Error('AI profile: no backend session available')
  if (session) cachedSession = session
  if (isGenerating) throw new Error('AI profile: generation already in progress')
  isGenerating = true
  try {
    console.log('[ai-profile] starting profile generation')
    // Wire the electron/better-sqlite3 impls to the pure orchestrator core
    // (orchestrate.ts) — the only place that touches the event loop / DB.
    return await generateProfile({
      fetchers: makeFetchers(active),
      chat: (messages) => runChat(active, messages),
      listPastProfiles: (n) => listAiUserProfiles(n).map((r) => r.profileText),
      insertProfile: insertAiUserProfile,
      syncProfile: (id, text, generatedAtMs, itemCount) =>
        syncToBackend(active, id, text, generatedAtMs, itemCount)
    })
  } finally {
    isGenerating = false
  }
}

/** The latest stored profile text (for downstream pipeline grounding). */
export function getLatestProfileText(): string | null {
  return latestAiUserProfile()?.profileText ?? null
}

/** Edit a stored profile's text, then fire-and-forget re-sync to the backend
 *  (using the cached session, if any). */
export async function editProfileText(id: number, text: string): Promise<void> {
  updateAiUserProfileText(id, text)
  if (!cachedSession) return
  // Look the record up (no getById in db.ts) to preserve its original
  // generatedAt on the backend.
  const record = listAiUserProfiles(50).find((r) => r.id === id)
  if (!record) return
  // Text-only edit: pass NO data_sources_used so the backend preserves its
  // stored item count (see syncToBackend / update_ai_user_profile). Sending an
  // approximation here would clobber the true count with a smaller wrong value.
  // A sync failure keeps the already-applied local edit (fail-open, degraded).
  void syncToBackend(cachedSession, id, text, record.generatedAt).catch((e) =>
    warnDegraded('backend_sync_failed', { op: 'edit', error: describeError(e) })
  )
}

/** Delete a single stored profile (local history only — Mac keeps the backend's
 *  single current profile untouched on delete). */
export function deleteProfile(id: number): void {
  deleteAiUserProfile(id)
}

/** Delete all stored profiles (local history only). */
export function deleteAll(): void {
  deleteAllAiUserProfiles()
}

// --- Background scheduling --------------------------------------------------

function runIfDue(): void {
  if (!getAppSettings().aiProfileEnabled) return
  const latest = latestAiUserProfile()
  if (!shouldGenerate(latest?.generatedAt ?? null, Date.now())) return
  if (!cachedSession) {
    // Soft no-op: no throw, no lost local row, just defer to the next tick
    // (or the next session push, whichever comes first).
    console.log('[ai-profile] generation due but no backend session yet — deferring')
    return
  }
  void generateNow().catch((e) =>
    console.warn('[ai-profile] scheduled generation:', (e as Error).message)
  )
}

/** Wire the startup check + daily timer. Idempotent (safe to call once at app
 *  startup). Generation is gated on the aiProfileEnabled setting and the >24h
 *  cadence; until the renderer has pushed a session this is a clean soft
 *  no-op (never throws, never loses a local row) — the renderer proactive
 *  framework (a later PR) owns actually deciding *when* to push a session and
 *  drive generation. This hook only covers the daily-cadence check once a
 *  session exists. */
export function maybeGenerateOnStartup(): void {
  runIfDue()
  if (!timer) timer = setInterval(runIfDue, CHECK_INTERVAL_MS)
}

/** Test/teardown: stop the background timer. */
export function stopAiProfileScheduler(): void {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}
