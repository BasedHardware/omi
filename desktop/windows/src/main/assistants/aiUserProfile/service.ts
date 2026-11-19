// AI User Profile — cloud reader (main process).
//
// The backend owns the profile: it picks the sources, runs the synthesis, keeps
// the daily cadence and stores one current profile on the user doc. This client
// only reads it and proxies the user's explicit actions:
//
//   GET    /v1/users/ai-profile          read (also lets the backend schedule a
//                                        background refresh when its copy is stale)
//   POST   /v1/users/ai-profile/refresh  "Generate now / Regenerate" (synchronous)
//   PATCH  /v1/users/ai-profile          a user edit, sent with source=user_edit
//   DELETE /v1/users/ai-profile          clear it; the backend regenerates later
//
// No local generation, history table, synthesize call or mirror PATCH. The one
// exception is a one-time upgrade step: older builds kept the profile in a local
// table and mirrored it with a fire-and-forget PATCH, so after the first
// authenticated read this module uploads that table's newest text if the backend
// never got it, then drops the table (see salvageLegacyProfile below).
//
// Prompt consumers (focus, screen-task extraction, chat personalization) read the
// profile synchronously, so this module keeps the last fetched profile in memory
// and refetches in the background once it is older than CACHE_TTL_MS. The cache
// is keyed by the signed-in uid and dropped on sign-out, so one account's profile
// never grounds another account's prompts.
//
// TOKEN MODEL (Windows-specific): the Firebase token lives in the RENDERER, which
// relays a session on sign-in and on every id-token refresh (see
// renderer/src/lib/aiProfileHost.ts). The shared `core/session.ts` holds it.
import { net } from 'electron'
import { dropLegacyProfileTable, readLegacyProfileRow } from '../../ipc/db'
import type { LegacyProfileRow } from '../../ipc/legacyProfileTable'
import type {
  AiProfileErrorCode,
  AiProfileResult,
  AiUserProfile,
  AiUserProfileSource
} from '../../../shared/types'
import {
  fetchWithFreshToken,
  getAbortSignal,
  getBackendSession,
  getSessionEpoch,
  onSessionReset,
  setBackendSession,
  tokenUid,
  type BackendSession
} from '../core/session'

/** Credentials the renderer hands the main process to reach the backend. */
export type AiProfileSession = BackendSession

const PROFILE_PATH = '/v1/users/ai-profile'
const REFRESH_PATH = '/v1/users/ai-profile/refresh'
/** Matches the backend's stored-profile cap; an edit longer than this is refused
 *  locally instead of round-tripping to a 422. */
export const MAX_PROFILE_CHARS = 10_000
const READ_TIMEOUT_MS = 30_000
/** The refresh call is synchronous on the backend (~10-40 s of synthesis). */
const REFRESH_TIMEOUT_MS = 90_000
/** Re-GET at most this often for prompt consumers. The backend decides whether
 *  its copy is stale; this only bounds how old our view of it can get. */
export const CACHE_TTL_MS = 60 * 60 * 1000

type CacheEntry = {
  /** Uid of the session the profile was fetched for (null if undecodable). */
  uid: string | null
  profile: AiUserProfile | null
  fetchedAt: number
}

let cache: CacheEntry | null = null
let readInFlight: Promise<AiProfileResult<AiUserProfile | null>> | null = null
// Session epoch the in-flight read started under. A session change aborts that
// request, so a caller under the new session starts its own instead of joining it.
let readEpoch = -1
let refreshInFlight: Promise<AiProfileResult<AiUserProfile>> | null = null
// Bumped whenever a mutation (refresh, edit, delete, legacy upload) commits. A read
// pins it when it starts and drops its result if it moved: the GET may have been
// served before the mutation, and storing it would undo the mutation in the cache
// (and mark that older copy fresh for CACHE_TTL_MS).
let mutationRevision = 0

// Legacy-table upload state (one attempt per launch, see salvageLegacyProfile).
// The local database belongs to the account signed in when this process first
// read the profile: sign-out always wipes before it clears the session (and
// dbWipe.ts clears the legacy rows), so a later account never sees them. Any other
// uid in this process is never allowed to upload them.
let legacyOwnerUid: string | null = null
let legacySettled = false
let legacyRunning = false

// Sign-out: forget the departed account's profile before anyone else signs in.
onSessionReset(() => {
  cache = null
})

// --- Wire shape -------------------------------------------------------------

/** Error raised by a non-OK response. Carries only the status, never a body. */
class ProfileHttpError extends Error {
  constructor(readonly status: number) {
    super(`HTTP ${status}`)
    this.name = 'ProfileHttpError'
  }
}

/** The session changed before a fenced request was dispatched. */
class StaleSessionError extends Error {
  constructor() {
    super('AI profile: session changed')
    this.name = 'StaleSessionError'
  }
}

class NotSignedInError extends Error {
  constructor() {
    super('AI profile: no backend session')
    this.name = 'NotSignedInError'
  }
}

/** HTTP status → the failure class the renderer explains. */
export function codeForStatus(status: number): AiProfileErrorCode {
  switch (status) {
    case 401:
    case 403:
      return 'auth_expired'
    case 402:
      return 'usage_exhausted'
    case 409:
      return 'in_progress'
    case 422:
      return 'insufficient_data'
    case 429:
      return 'rate_limited'
    case 502:
      return 'synthesis_failed'
    default:
      return 'unknown'
  }
}

function codeForError(e: unknown): AiProfileErrorCode {
  if (e instanceof ProfileHttpError) return codeForStatus(e.status)
  if (e instanceof NotSignedInError) return 'not_signed_in'
  // Abort, timeout, DNS/TLS failure, malformed JSON.
  return 'network'
}

/** PII-free log label: status or error NAME, never a message (a JSON parse error
 *  message can echo a fragment of the profile text). */
function describeError(e: unknown): string {
  if (e instanceof ProfileHttpError) return `HTTP ${e.status}`
  return e instanceof Error ? e.name : 'Error'
}

function toMs(v: unknown): number | null {
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string' && v) {
    const t = Date.parse(v)
    return Number.isNaN(t) ? null : t
  }
  return null
}

const SOURCES: readonly AiUserProfileSource[] = ['backend', 'user_edit', 'exploration', 'client']

/** Parse an AIUserProfileResponse (or null). An absent or blank profile_text is
 *  "no profile", matching how the backend treats a cleared field. */
export function parseProfile(json: unknown): AiUserProfile | null {
  if (!json || typeof json !== 'object') return null
  const r = json as Record<string, unknown>
  const text = typeof r.profile_text === 'string' ? r.profile_text : ''
  if (!text.trim()) return null
  const source = SOURCES.find((s) => s === r.source) ?? null
  return {
    profileText: text,
    generatedAt: toMs(r.generated_at),
    dataSourcesUsed: typeof r.data_sources_used === 'number' ? r.data_sources_used : 0,
    source,
    refreshedAt: toMs(r.refreshed_at)
  }
}

// --- HTTP -------------------------------------------------------------------

/** One authed request against the Python backend. Resolves with the parsed JSON
 *  body (null for an empty body); throws ProfileHttpError on a non-OK status.
 *  The timeout covers reading the body too, and a session change aborts it.
 *  With `epoch`, the request is never dispatched unless the session is still that
 *  one (a token pull inside fetchWithFreshToken can switch accounts). */
async function send(
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
  path: string,
  body: unknown,
  timeoutMs: number,
  epoch?: number
): Promise<unknown> {
  if (!getBackendSession()) throw new NotSignedInError()
  const external = getAbortSignal()
  const ctrl = new AbortController()
  const onExternalAbort = (): void => ctrl.abort()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  if (external?.aborted) ctrl.abort()
  else external?.addEventListener('abort', onExternalAbort, { once: true })
  try {
    const res = await fetchWithFreshToken(async (session) => {
      if (epoch !== undefined && getSessionEpoch() !== epoch) throw new StaleSessionError()
      return net.fetch(`${session.apiBase}${path}`, {
        method,
        headers: {
          Authorization: `Bearer ${session.token}`,
          ...(body !== undefined ? { 'Content-Type': 'application/json' } : {})
        },
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal: ctrl.signal
      })
    }, `${method} ${path}`)
    if (!res.ok) throw new ProfileHttpError(res.status)
    const raw = await res.text()
    return raw ? (JSON.parse(raw) as unknown) : null
  } finally {
    clearTimeout(timer)
    external?.removeEventListener('abort', onExternalAbort)
  }
}

function currentUid(): string | null {
  const s = getBackendSession()
  return s ? tokenUid(s.token) : null
}

/** Store a result only if the account that asked is still the one signed in. */
function storeIfCurrent(uid: string | null, profile: AiUserProfile | null): void {
  if (!getBackendSession() || currentUid() !== uid) return
  cache = { uid, profile, fetchedAt: Date.now() }
}

/** Record a committed mutation's result. Bumping the revision makes any read
 *  that started before it discard its (possibly older) response. */
function commitMutation(uid: string | null, profile: AiUserProfile | null): void {
  mutationRevision += 1
  storeIfCurrent(uid, profile)
}

function cachedForCurrentUser(): CacheEntry | null {
  if (!cache || !getBackendSession() || cache.uid !== currentUid()) return null
  return cache
}

async function run<T>(label: string, fn: () => Promise<T>): Promise<AiProfileResult<T>> {
  try {
    return { ok: true, value: await fn() }
  } catch (e) {
    console.warn(`[ai-profile] ${label} failed:`, describeError(e))
    return { ok: false, code: codeForError(e) }
  }
}

// --- Public API -------------------------------------------------------------

/** Relay a session from the renderer (sign-in, hourly id-token refresh, sign-out
 *  → null). A non-null session warms the cache in the background so the first
 *  prompt after sign-in already has the profile. */
export function configureAiProfileSession(session: AiProfileSession | null): void {
  setBackendSession(session)
  if (session && !isFresh()) void loadProfile()
}

function isFresh(now: number = Date.now()): boolean {
  const c = cachedForCurrentUser()
  return c !== null && now - c.fetchedAt < CACHE_TTL_MS
}

/** GET the profile and update the cache. Concurrent callers share one request.
 *  On failure the last fetched profile for this account (if any) is returned, so
 *  a flaky network doesn't blank the Settings card. */
export function loadProfile(): Promise<AiProfileResult<AiUserProfile | null>> {
  if (readInFlight && readEpoch === getSessionEpoch()) return readInFlight
  const uid = currentUid()
  const epoch = getSessionEpoch()
  const revision = mutationRevision
  readEpoch = epoch
  if (legacyOwnerUid === null && uid !== null && getBackendSession()) legacyOwnerUid = uid
  const p: Promise<AiProfileResult<AiUserProfile | null>> = run('read', async () => {
    const profile = parseProfile(await send('GET', PROFILE_PATH, undefined, READ_TIMEOUT_MS))
    if (revision !== mutationRevision) {
      // An edit/delete/refresh committed while this GET was out; its result is
      // newer than (or at least as new as) what this read saw.
      const c = cachedForCurrentUser()
      return c && c.uid === uid ? c.profile : profile
    }
    storeIfCurrent(uid, profile)
    if (epoch !== getSessionEpoch()) return profile
    return (await salvageLegacyProfile(uid, epoch, profile)) ?? profile
  })
    .then((r) => {
      if (r.ok) return r
      const c = cachedForCurrentUser()
      return c ? { ok: true as const, value: c.profile } : r
    })
    .finally(() => {
      if (readInFlight === p) readInFlight = null
    })
  readInFlight = p
  return p
}

/** Ask the backend to regenerate now (POST refresh). Synchronous on the backend;
 *  a second click while one is running joins it instead of drawing a 409. */
export function refreshProfile(): Promise<AiProfileResult<AiUserProfile>> {
  if (refreshInFlight) return refreshInFlight
  const uid = currentUid()
  refreshInFlight = run('refresh', async () => {
    const profile = parseProfile(await send('POST', REFRESH_PATH, undefined, REFRESH_TIMEOUT_MS))
    // A 200 with no text would be a backend bug; report it as a failed synthesis
    // rather than showing an empty profile as success.
    if (!profile) throw new ProfileHttpError(502)
    commitMutation(uid, profile)
    return profile
  }).finally(() => {
    refreshInFlight = null
  })
  return refreshInFlight
}

/** Save the user's edit. The backend keeps it as a correction the next synthesis
 *  builds on. */
export async function editProfile(text: string): Promise<AiProfileResult<AiUserProfile>> {
  const uid = currentUid()
  return run('edit', async () => {
    const json = await send(
      'PATCH',
      PROFILE_PATH,
      { profile_text: text, source: 'user_edit' },
      READ_TIMEOUT_MS
    )
    const profile = parseProfile(json) ?? {
      profileText: text,
      generatedAt: Date.now(),
      dataSourcesUsed: cachedForCurrentUser()?.profile?.dataSourcesUsed ?? 0,
      source: 'user_edit' as const,
      refreshedAt: cachedForCurrentUser()?.profile?.refreshedAt ?? null
    }
    commitMutation(uid, profile)
    return profile
  })
}

/** Clear the profile on the backend (it regenerates on its next trigger). */
export async function deleteProfile(): Promise<AiProfileResult<null>> {
  const uid = currentUid()
  return run('delete', async () => {
    await send('DELETE', PROFILE_PATH, undefined, READ_TIMEOUT_MS)
    commitMutation(uid, null)
    return null
  })
}

/** The cached profile text for prompt grounding, or null. Never blocks: when the
 *  cache is missing or older than CACHE_TTL_MS it kicks a background GET and
 *  answers from what it has. */
export function getLatestProfileText(): string | null {
  if (!getBackendSession()) return null
  if (!isFresh()) void loadProfile()
  return cachedForCurrentUser()?.profile?.profileText || null
}

// --- Legacy local table: one-time upload --------------------------------------

/** Whether the newest pre-cloud local row holds text the backend lacks. The old
 *  `backendSynced` marker is set when a generation's mirror PATCH succeeded, but an
 *  edit never cleared it, so a failed edit sync still reads as synced. Hence: an
 *  unsynced row, or a row whose text differs from the cloud's and is not older
 *  than it (an edit PATCHed with its generation's timestamp), is uploaded. A cloud
 *  profile without a timestamp is trusted unless the row is marked unsynced. */
export function legacyRowNeedsUpload(row: LegacyProfileRow, cloud: AiUserProfile | null): boolean {
  const text = row.profileText.trim()
  if (!text) return false
  if (!cloud) return true
  if (text === cloud.profileText.trim()) return false
  if (cloud.generatedAt === null || !Number.isFinite(row.generatedAt)) return !row.backendSynced
  return row.generatedAt >= cloud.generatedAt
}

/** After an authenticated GET for the account that owns the local database: if
 *  the old local table holds newer text the backend never got, PATCH it (as a
 *  legacy client write: no source, the row's generated_at), and drop the table only
 *  once the backend has the text. A failed PATCH keeps the table for the next
 *  launch. Every step is fenced on the session epoch the GET ran under, and the
 *  PATCH is never dispatched under another session. Resolves with the profile the
 *  upload produced, or undefined when nothing was uploaded. */
async function salvageLegacyProfile(
  uid: string | null,
  epoch: number,
  cloud: AiUserProfile | null
): Promise<AiUserProfile | undefined> {
  if (legacySettled || legacyRunning || uid === null || uid !== legacyOwnerUid) return undefined
  legacyRunning = true
  try {
    let row: LegacyProfileRow | null
    try {
      row = readLegacyProfileRow()
    } catch (e) {
      legacySettled = true
      console.warn('[ai-profile] legacy table read failed:', describeError(e))
      return undefined
    }
    if (getSessionEpoch() !== epoch) return undefined
    if (!row || !legacyRowNeedsUpload(row, cloud)) {
      dropLegacy()
      return undefined
    }
    const revision = mutationRevision
    let json: unknown
    try {
      json = await send(
        'PATCH',
        PROFILE_PATH,
        {
          profile_text: row.profileText.slice(0, MAX_PROFILE_CHARS),
          generated_at: new Date(row.generatedAt).toISOString()
        },
        READ_TIMEOUT_MS,
        epoch
      )
    } catch (e) {
      // A session change (sign-out wipes the rows; a same-user token push may
      // retry later under the same owner) leaves the attempt open; any other
      // failure keeps the table for the next launch.
      if (getSessionEpoch() === epoch) legacySettled = true
      console.warn('[ai-profile] legacy profile upload failed:', describeError(e))
      return undefined
    }
    dropLegacy()
    const profile = parseProfile(json) ?? {
      profileText: row.profileText.slice(0, MAX_PROFILE_CHARS),
      generatedAt: row.generatedAt,
      dataSourcesUsed: cloud?.dataSourcesUsed ?? 0,
      source: 'client' as const,
      refreshedAt: cloud?.refreshedAt ?? null
    }
    if (revision === mutationRevision) {
      commitMutation(uid, profile)
    } else {
      // A user action committed while the upload was out; the server's final
      // state depends on arrival order, so let the next consumer re-read it.
      mutationRevision += 1
      if (cache) cache.fetchedAt = 0
    }
    console.log('[ai-profile] uploaded the pre-cloud local profile')
    return profile
  } finally {
    legacyRunning = false
  }
}

function dropLegacy(): void {
  legacySettled = true
  try {
    dropLegacyProfileTable()
  } catch (e) {
    console.warn('[ai-profile] legacy table drop failed:', describeError(e))
  }
}

/** Test seam: drop the cache and any in-flight bookkeeping. */
export function _resetAiProfileCache(): void {
  cache = null
  readInFlight = null
  refreshInFlight = null
  mutationRevision = 0
  legacyOwnerUid = null
  legacySettled = false
  legacyRunning = false
}
