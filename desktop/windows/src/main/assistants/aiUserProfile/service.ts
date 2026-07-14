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

// Floor between generation ATTEMPTS, successful or not. `generatedAt` is only
// written on success, so without this a failing generation (429/500, empty LLM
// content, timeout, or simply a user with no data) stays permanently "due" — and
// since the renderer relays a session on every id-token refresh (~hourly), it
// would retry ~24x/day forever with no backoff. 6h preserves the ≤4-attempts/day
// ceiling the 6h timer alone used to give.
const MIN_ATTEMPT_INTERVAL_MS = 6 * 60 * 60 * 1000

let cachedSession: AiProfileSession | null = null
let isGenerating = false
let timer: ReturnType<typeof setInterval> | null = null

// Monotonic id for the current session. Bumped on EVERY configureAiProfileSession
// call (including null/sign-out). A generation captures it at entry and discards
// its result if it has moved — see OrchestratorDeps.isStale. A same-user token
// refresh also bumps it, so a refresh landing inside a 10–90s generation discards
// that run (it retries on the next due check). That is the deliberate trade: main
// receives only {bases, token} and cannot tell "same user, new token" from "new
// user", so it fails safe toward never writing a departed session's data.
let sessionEpoch = 0
// Aborts the in-flight generation's HTTP/LLM work on sign-out, so it dies
// promptly instead of running to completion against a signed-out session.
let abortController: AbortController | null = null
// Start time of the last generation ATTEMPT (any outcome). null = never tried.
let lastAttemptAt: number | null = null

/** Set/refresh (or clear, on null) the cached backend session. Called by the
 *  IPC layer whenever the renderer provides fresh credentials.
 *
 *  A NON-null session also kicks a `runIfDue()` — this closes the startup race:
 *  `maybeGenerateOnStartup` runs at app-ready, finds no session yet (the token
 *  lives in the renderer, which signs in later) and defers, after which nothing
 *  would re-check for up to 6h. Re-checking the moment credentials arrive means
 *  a >24h-old profile regenerates right after sign-in instead of hours later.
 *
 *  This is NOT a "generate on every push": the renderer relays a session on
 *  every Firebase id-token refresh (~hourly), but `runIfDue` gates on
 *  `shouldGenerate(latest.generatedAt, now)`, so the cadence stays ≤1/day. It is
 *  fire-and-forget by construction (runIfDue kicks generation without awaiting),
 *  so the setSession IPC returns immediately rather than blocking the renderer
 *  on a multi-second generation. */
/** Cache a session and invalidate anything in flight for the previous one.
 *  Deliberately does NOT kick a due-check — generateNow(session) reuses this and
 *  must not re-enter itself through runIfDue. */
function setSession(session: AiProfileSession | null): void {
  // Bump FIRST: any generation already in flight belongs to the previous session
  // and must now be treated as stale (it re-reads this at each write).
  sessionEpoch += 1
  cachedSession = session

  // Kill the in-flight generation's network/LLM work. Critical on sign-out (it
  // would otherwise keep fetching and synthesizing for 10–90s against a session
  // the user just ended, with requests still carrying their token). Also correct
  // on a plain token refresh: the epoch bump above has already doomed that run's
  // result, so letting it finish would burn an LLM call for output nobody can use.
  abortController?.abort()
  abortController = session ? new AbortController() : null
}

export function configureAiProfileSession(session: AiProfileSession | null): void {
  setSession(session)
  if (!session) return
  // Caching the session must never fail because a due-check threw — the IPC
  // handler's whole job is to store credentials.
  try {
    runIfDue()
  } catch (e) {
    console.warn('[ai-profile] due-check on session push failed:', describeError(e))
  }
}

// --- HTTP helpers -----------------------------------------------------------

// Shared abort-on-timeout wrapper — every net.fetch call below (authedGet,
// runChat, syncToBackend) needs the same AbortController + timer dance to cap
// a hung request; this is the one place that owns it.
// `external` is the current session's abort signal: a sign-out (or any session
// change) aborts every request still in flight for the old session, on top of
// the per-request timeout.
async function withTimeout<T>(
  ms: number,
  fn: (signal: AbortSignal) => Promise<T>,
  external?: AbortSignal
): Promise<T> {
  const ctrl = new AbortController()
  const onExternalAbort = (): void => ctrl.abort()
  const timer = setTimeout(() => ctrl.abort(), ms)
  if (external?.aborted) ctrl.abort()
  else external?.addEventListener('abort', onExternalAbort, { once: true })
  try {
    return await fn(ctrl.signal)
  } finally {
    clearTimeout(timer)
    external?.removeEventListener('abort', onExternalAbort)
  }
}

// Electron's net.fetch uses Chromium's network stack (proxy/TLS aware) — the
// same path the renderer's axios uses.
async function authedGet(
  session: AiProfileSession,
  path: string,
  external?: AbortSignal
): Promise<unknown> {
  return withTimeout(
    REQUEST_TIMEOUT_MS,
    async (signal) => {
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
    },
    external
  )
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

async function fetchMemories(session: AiProfileSession, signal?: AbortSignal): Promise<string[]> {
  const data = await authedGet(session, '/v3/memories?limit=100&offset=0', signal)
  const items = asArray<{ content?: string; category?: string }>(data, 'memories')
  return items
    .slice(0, 100)
    .map((m) => `[${m.category ?? 'other'}] ${m.content ?? ''}`.trim())
    .filter((s) => s.length > 3)
}

async function fetchTasks(session: AiProfileSession, signal?: AbortSignal): Promise<string[]> {
  const data = await authedGet(session, '/v1/action-items?limit=50&offset=0', signal)
  // Windows ActionItemResponse has no `priority` field (Mac does) — omit it.
  const items = asArray<{ description?: string; completed?: boolean }>(data, 'action_items')
  return items
    .slice(0, 50)
    .map((t) => `[${t.completed ? 'done' : 'todo'}] ${t.description ?? ''}`.trim())
    .filter((s) => s.length > 7)
}

async function fetchGoals(session: AiProfileSession, signal?: AbortSignal): Promise<string[]> {
  // /v1/goals/all returns active + completed; we keep active only (Mac parity).
  const data = await authedGet(session, '/v1/goals/all', signal)
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

async function fetchConversations(
  session: AiProfileSession,
  signal?: AbortSignal
): Promise<string[]> {
  const data = await authedGet(
    session,
    '/v1/conversations?limit=20&offset=0&statuses=completed,processing',
    signal
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

async function fetchMessages(session: AiProfileSession, signal?: AbortSignal): Promise<string[]> {
  const data = await authedGet(session, '/v2/messages', signal)
  const messages = asArray<{ sender?: string; text?: string }>(data, 'messages')
  return messages
    .slice(0, 30)
    .map((m) => `[${m.sender ?? 'ai'}] ${m.text ?? ''}`.trim())
    .filter((s) => s.length > 5)
}

function makeFetchers(session: AiProfileSession, signal?: AbortSignal): SourceFetchers {
  return {
    memories: () => fetchMemories(session, signal),
    tasks: () => fetchTasks(session, signal),
    goals: () => fetchGoals(session, signal),
    conversations: () => fetchConversations(session, signal),
    messages: () => fetchMessages(session, signal)
  }
}

// --- LLM + backend sync -----------------------------------------------------

async function runChat(
  session: AiProfileSession,
  messages: ChatMessage[],
  external?: AbortSignal
): Promise<string> {
  return withTimeout(
    LLM_TIMEOUT_MS,
    async (signal) => {
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
    },
    external
  )
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
  dataSourceItemCount?: number,
  external?: AbortSignal
): Promise<void> {
  return withTimeout(
    REQUEST_TIMEOUT_MS,
    async (signal) => {
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
    },
    external
  )
}

// --- Public API -------------------------------------------------------------

/** Generate a new profile now. Uses the provided session, else the cached one.
 *  Throws if no session is available or if there is no data to synthesize. */
export async function generateNow(session?: AiProfileSession): Promise<AiUserProfileRecord> {
  // setSession (not configureAiProfileSession) — a due-check here would re-enter
  // generateNow via runIfDue.
  if (session) setSession(session)
  const active = cachedSession
  if (!active) throw new Error('AI profile: no backend session available')
  if (isGenerating) throw new Error('AI profile: generation already in progress')

  // Pin the session this run belongs to. Every write is gated on the epoch still
  // matching, so a sign-out (or user switch) mid-generation discards the result
  // instead of writing the departed user's dossier back into the wiped DB.
  const startEpoch = sessionEpoch
  const signal = abortController?.signal
  const isStale = (): boolean => sessionEpoch !== startEpoch

  isGenerating = true
  try {
    console.log('[ai-profile] starting profile generation')
    // Wire the electron/better-sqlite3 impls to the pure orchestrator core
    // (orchestrate.ts) — the only place that touches the event loop / DB.
    return await generateProfile({
      fetchers: makeFetchers(active, signal),
      chat: (messages) => runChat(active, messages, signal),
      listPastProfiles: (n) => listAiUserProfiles(n).map((r) => r.profileText),
      insertProfile: insertAiUserProfile,
      syncProfile: (id, text, generatedAtMs, itemCount) =>
        syncToBackend(active, id, text, generatedAtMs, itemCount, signal),
      isStale
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
  // Non-reentrancy: runIfDue now has THREE triggers (startup, the 6h timer, and
  // every session push). A generation is multi-second, so a timer tick landing
  // on top of an in-flight run — or two rapid token refreshes — must not start a
  // second one. generateNow() also guards internally (it throws if re-entered);
  // bailing here keeps that from surfacing as a spurious warn log.
  if (isGenerating) return

  const now = Date.now()
  // Attempt floor. `generatedAt` only advances on SUCCESS, so a persistently
  // failing generation (or a user with no data) stays "due" forever — and this
  // is now reached on every hourly session push, not just the 6h timer. Without
  // this, one broken account would retry ~24x/day indefinitely.
  if (lastAttemptAt !== null && now - lastAttemptAt < MIN_ATTEMPT_INTERVAL_MS) return

  const latest = latestAiUserProfile()
  if (!shouldGenerate(latest?.generatedAt ?? null, now)) return
  if (!cachedSession) {
    // Soft no-op: no throw, no lost local row, just defer to the next tick
    // (or the next session push, whichever comes first). Deliberately does NOT
    // consume an attempt — nothing was tried.
    console.log('[ai-profile] generation due but no backend session yet — deferring')
    return
  }

  // Consume the attempt BEFORE starting: the floor must hold regardless of how
  // this run ends (success, HTTP error, timeout, abort, no-data).
  lastAttemptAt = now
  // m7/logging-security: name/status only — never e.message. A malformed-JSON
  // SyntaxError can echo a fragment of the user-data response body.
  void generateNow().catch((e) =>
    console.warn('[ai-profile] scheduled generation failed:', describeError(e))
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
