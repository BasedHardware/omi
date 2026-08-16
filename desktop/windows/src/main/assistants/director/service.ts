/**
 * Director composition root — wires the pure/injected modules (engine, visit
 * coordinator, TCRS, subject binding, lane client) to the real substrate:
 * the shared SQLite handle, the backend session, the notification throttle,
 * and the renderer projection channel.
 *
 * Flag surface (mirrors mac's ContextBucketsFeature, Windows-shaped):
 * - Pipeline: `AppSettings.contextDirectorEnabled` (default OFF — ships dark;
 *   the Settings toggle and `OMI_FORCE_CONTEXT_BUCKETS=1` are the levers).
 * - Destination routing: on with the pipeline; `OMI_FORCE_BUCKET_DESTINATIONS=0` disables.
 * - Retrieval hop: on with the pipeline; `OMI_FORCE_BUCKET_RETRIEVAL=0` disables.
 * - Departure evaluation / workstream pooling / armed candidates: OFF unless
 *   env-forced (`OMI_FORCE_DEPARTURE_EVALUATION=1` / `OMI_FORCE_BUCKET_WORKSTREAMS=1`
 *   / `OMI_FORCE_BUCKET_CANDIDATES=1`) — mac holds these hard-off in production.
 */

import { net, BrowserWindow } from 'electron'
import { getAppSettings, onAppSettingsChanged } from '../../appSettings'
import {
  contextDirectorDb,
  getRecentActiveActionItems,
  reconcileAbandonedProactiveDeliveries,
  runContextBucketGC
} from '../../ipc/db'
import {
  finalizeVisitOn,
  reconcileInterruptedVisitsOn,
  startVisitOn,
  writeExtractionOn,
  type BucketExtraction,
  type ContextVisitFence
} from '../../ipc/contextBucketStore'
import {
  getAbortSignal,
  getBackendSession,
  getSessionEpoch,
  fetchWithFreshToken,
  isSessionExpired,
  onSessionReset,
  pullFreshSession
} from '../core/session'
import {
  notificationsActive,
  notifyProactive,
  lastGlobalProactiveNotificationAt
} from '../core/notify'
import { readFrameImageBase64 } from '../core/frameImage'
import type { RewindFrame } from '../../../shared/types'
import { createLaneClient, LaneError } from './laneClient'
import { cooldownMsForLevel, dailyLimitForLevel, type DeliveryGateInput } from './deliveryPolicy'
import {
  ContextProactivityEngine,
  DEPARTURE_WORTHINESS_THRESHOLD,
  type DirectorFrame,
  type PresentationOutcome
} from './engine'
import { ContextVisitCoordinator } from './visitCoordinator'
import { EXTRACTION_MAX_COMPLETION_TOKENS, EXTRACTION_SCHEMA, extractionPrompt } from './prompts'
import { sanitizeDestination, isBrowser } from './destinationKey'
import { applyDestinationOn } from '../../ipc/contextBucketStore'
import { retrieveForQuery, type RetrievalSource } from './retrieval'
import {
  liveTag,
  selectPooledFacts,
  selectRecentContextFacts,
  workstreamPromptSection,
  recentContextPromptSection,
  POOL_WORTHINESS_FLOOR,
  RECENT_CONTEXT_WORTHINESS_FLOOR
} from './workstreamPooling'
import {
  recentContextPoolOn,
  workstreamPoolOn,
  workstreamTagCountsOn
} from '../../ipc/proactivityLedger'
import { TaskContextualResurfacingService, sha256Hex, type TaskContextSubject } from './tcrs'
import { ContextSubjectBindingService } from './subjectBinding'

function envForced(name: string, defaultOn: boolean): boolean {
  const value = process.env[name]
  if (value === undefined) return defaultOn
  return value !== '0'
}

export function directorPipelineEnabled(): boolean {
  if (process.env.OMI_FORCE_CONTEXT_BUCKETS !== undefined) {
    return process.env.OMI_FORCE_CONTEXT_BUCKETS !== '0'
  }
  return getAppSettings().contextDirectorEnabled === true
}

export const directorFlags = {
  destinationRouting: (): boolean =>
    directorPipelineEnabled() && envForced('OMI_FORCE_BUCKET_DESTINATIONS', true),
  retrievalHop: (): boolean =>
    directorPipelineEnabled() && envForced('OMI_FORCE_BUCKET_RETRIEVAL', true),
  departureEvaluation: (): boolean =>
    directorPipelineEnabled() && envForced('OMI_FORCE_DEPARTURE_EVALUATION', false),
  workstreamPooling: (): boolean =>
    directorPipelineEnabled() && envForced('OMI_FORCE_BUCKET_WORKSTREAMS', false),
  candidates: (): boolean =>
    directorPipelineEnabled() && envForced('OMI_FORCE_BUCKET_CANDIDATES', false)
}

// --- device identity (relayed from the renderer; see clientDevice.ts) --------

let deviceIdHash: string | null = null

/** The renderer computes sha256(install-id)[:8] and relays it so main-side
 *  calls share the SAME device scope as the renderer's HTTP client — mixed
 *  scopes would 403 the snapshot flow. */
export function setDirectorDeviceIdHash(hash: string): void {
  if (/^[0-9a-f]{8}$/.test(hash)) deviceIdHash = hash
}

export function directorDeviceId(): string | null {
  return deviceIdHash === null ? null : `windows_${deviceIdHash}`
}

function deviceHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'X-App-Platform': 'windows' }
  if (deviceIdHash !== null) headers['X-Device-Id-Hash'] = deviceIdHash
  return headers
}

function ownerUid(): string | null {
  const session = getBackendSession()
  if (!session) return null
  try {
    const payload = JSON.parse(
      Buffer.from(session.token.split('.')[1] ?? '', 'base64').toString('utf8')
    ) as Record<string, unknown>
    const uid = payload.user_id ?? payload.sub
    return typeof uid === 'string' && uid.length > 0 ? uid : null
  } catch {
    return null
  }
}

// --- backend adapters --------------------------------------------------------

async function apiFetch(path: string, init: RequestInit): Promise<Response> {
  return fetchWithFreshToken(async (session) => {
    return net.fetch(`${session.apiBase}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${session.token}`,
        ...deviceHeaders(),
        ...(init.headers as Record<string, string> | undefined)
      },
      signal: getAbortSignal()
    })
  }, 'director')
}

function toolSearch(path: string, body: Record<string, unknown>): Promise<RetrievalSource[]> {
  return apiFetch(path, { method: 'POST', body: JSON.stringify(body) }).then(async (res) => {
    if (!res.ok) return []
    const parsed = (await res.json()) as {
      is_error?: boolean
      sources?: Array<{
        kind?: string
        source_id?: string
        title?: string
        preview?: string
        created_at?: string | null
      }>
    }
    if (parsed.is_error === true || !Array.isArray(parsed.sources)) return []
    return parsed.sources.map((s) => ({
      kind: s.kind === 'memory' ? ('memory' as const) : ('conversation' as const),
      id: s.source_id ?? '',
      title: s.title ?? '',
      preview: s.preview ?? '',
      createdAt: s.created_at ?? ''
    }))
  })
}

/** The settings-sync HTTP pair (GET/PATCH /v1/users/notification-settings). */
export const notificationSettingsSyncHttp = {
  get: async (): Promise<{ enabled: boolean; frequency: number }> => {
    const res = await apiFetch('/v1/users/notification-settings', { method: 'GET' })
    if (!res.ok) throw new Error(`notification settings GET failed: ${res.status}`)
    return (await res.json()) as { enabled: boolean; frequency: number }
  },
  patch: async (body: {
    enabled?: boolean
    frequency: number
  }): Promise<{ enabled: boolean; frequency: number }> => {
    const res = await apiFetch('/v1/users/notification-settings', {
      method: 'PATCH',
      body: JSON.stringify(body)
    })
    if (!res.ok) throw new Error(`notification settings PATCH failed: ${res.status}`)
    return (await res.json()) as { enabled: boolean; frequency: number }
  }
}

async function getWorkflowControl(): Promise<{
  workflowMode: string
  accountGeneration: number | null
}> {
  const res = await apiFetch('/v1/candidates/control', { method: 'GET' })
  if (!res.ok) return { workflowMode: 'off', accountGeneration: null }
  const parsed = (await res.json()) as { workflow_mode?: string; account_generation?: number }
  return {
    workflowMode: parsed.workflow_mode ?? 'off',
    accountGeneration:
      typeof parsed.account_generation === 'number' ? parsed.account_generation : null
  }
}

/** task_candidate graduation: canonical TaskCreateCandidate per cited fact
 *  (idempotency `context-bucket:<factID>`), then the local disposition flip
 *  none -> candidate_pending, exactly mac's CandidateSink order. */
async function graduateFacts(
  factIDs: string[],
  bucketID: string
): Promise<{ ok: true } | { ok: false; reason: string }> {
  if (factIDs.length === 0) return { ok: false, reason: 'no_fact_ids' }
  // Pin the session epoch: the facts and bucket were read under this owner,
  // and no candidate may be created or disposition flipped under another.
  const epoch = getSessionEpoch()
  const db = contextDirectorDb()
  const now = Date.now()
  const facts: Array<{
    id: string
    statement: string
    evidenceText: string
    confidence: number
    dispositionState: string
  }> = []
  for (const id of factIDs) {
    const row = db
      .prepare(
        `SELECT id, statement, evidenceText, confidence, dispositionState FROM bucket_facts
         WHERE id = ? AND bucketID = ? AND validityState = 'validated' AND (expiresAt IS NULL OR expiresAt > ?)`
      )
      .get(id, bucketID, now) as (typeof facts)[number] | undefined
    if (!row) return { ok: false, reason: 'stale' }
    if (row.dispositionState !== 'none' && row.dispositionState !== 'candidate_pending') {
      return { ok: false, reason: 'ineligible_disposition' }
    }
    facts.push(row)
  }

  const needsCreate = facts.some((f) => f.dispositionState === 'none')
  let generation: number | null = null
  if (needsCreate) {
    const control = await getWorkflowControl()
    if (getSessionEpoch() !== epoch) return { ok: false, reason: 'owner_changed' }
    if (control.workflowMode !== 'read' || control.accountGeneration === null) {
      return { ok: false, reason: 'workflow_not_readable' }
    }
    generation = control.accountGeneration
  }

  const deviceId = directorDeviceId()
  for (const fact of facts) {
    if (fact.dispositionState !== 'none') continue
    if (generation === null) return { ok: false, reason: 'workflow_not_readable' }
    if (getSessionEpoch() !== epoch) return { ok: false, reason: 'owner_changed' }
    const body = {
      subject_kind: 'task',
      proposed_action: 'create',
      capture_confidence: fact.confidence,
      ownership_confidence: fact.confidence,
      source_surface: 'context_bucket',
      evidence_refs: [
        {
          kind: 'local_screen',
          id: `bucket-fact:${fact.id}`,
          scope: 'device_local',
          version: 'context_bucket.v1',
          excerpt_hash: sha256Hex(fact.evidenceText),
          ...(deviceId !== null ? { device_id: deviceId } : {})
        }
      ],
      task_change: { description: fact.statement }
    }
    const res = await apiFetch('/v1/candidates', {
      method: 'POST',
      headers: {
        'Idempotency-Key': `context-bucket:${fact.id}`,
        'X-Account-Generation': String(generation)
      },
      body: JSON.stringify(body)
    })
    if (!res.ok) return { ok: false, reason: `create_failed_${res.status}` }
    if (getSessionEpoch() !== epoch) return { ok: false, reason: 'owner_changed' }
    const flipped = db
      .prepare(
        `UPDATE bucket_facts SET dispositionState = 'candidate_pending', updatedAt = ?
         WHERE id = ? AND validityState = 'validated' AND dispositionState = 'none' AND (expiresAt IS NULL OR expiresAt > ?)`
      )
      .run(Date.now(), fact.id, Date.now()) as { changes: number | bigint }
    if (Number(flipped.changes) !== 1) return { ok: false, reason: 'stale' }
  }
  return { ok: true }
}

// --- renderer projection channel --------------------------------------------

function publishProjectionToRenderer(raw: unknown): void {
  for (const win of BrowserWindow.getAllWindows()) {
    if (!win.isDestroyed()) win.webContents.send('intelligence:contextProjection', raw)
  }
}

// --- instances ---------------------------------------------------------------

export const directorLane = createLaneClient({
  fetchImpl: (url, init) => net.fetch(url, init),
  getSession: () => {
    const session = getBackendSession()
    return session ? { desktopApiBase: session.desktopApiBase, token: session.token } : null
  },
  ensureFreshSession: async () => {
    if (isSessionExpired()) await pullFreshSession()
  },
  getAbortSignal: () => getAbortSignal()
})

function gateInput(): DeliveryGateInput {
  const settings = getAppSettings()
  return {
    masterEnabled: settings.notificationsEnabled,
    frequencyLevel: settings.notificationFrequency,
    // No desktop paywall state exists in main today; plan multiplier 1.
    paywalled: false,
    cooldownMs: cooldownMsForLevel(settings.notificationFrequency),
    dailyLimit: dailyLimitForLevel(settings.notificationFrequency, 1),
    lastGlobalPresentationAt: lastGlobalProactiveNotificationAt()
  }
}

// The latest coordinator-approved frame, kept by the assistant peer for
// director grounding (mac trackedFrameForDirector).
let trackedFrame: (DirectorFrame & { imagePath: string | null }) | null = null

export function recordTrackedFrame(frame: RewindFrame): void {
  trackedFrame = {
    frameId: frame.id ?? null,
    appName: frame.app,
    windowTitle: frame.windowTitle.length > 0 ? frame.windowTitle : null,
    captureTime: frame.ts,
    storedAt: Date.now(),
    imagePath: frame.imagePath.length > 0 ? frame.imagePath : null
  }
}

export function clearTrackedFrame(): void {
  trackedFrame = null
}

export const directorEngine = new ContextProactivityEngine({
  db: () => contextDirectorDb(),
  lane: directorLane,
  now: () => Date.now(),
  sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  sessionEpoch: () => getSessionEpoch(),
  gateInput,
  presentationPreflight: (): PresentationOutcome =>
    notificationsActive('director') ? 'queued' : 'suppressed',
  present: (args) => {
    const shown = notifyProactive('director', {
      headline: args.title,
      advice: args.message,
      reasoning: '',
      category: 'other',
      sourceApp: '',
      confidence: 1
    })
    if (shown) {
      args.onPresented()
      return 'presented'
    }
    args.onDropped()
    return 'suppressed'
  },
  trackedFrame: (sinceStartedAt) => {
    if (trackedFrame === null || trackedFrame.captureTime < sinceStartedAt) return null
    return trackedFrame
  },
  readFrameImage: async (frameId) => {
    // The requested frame must still be the tracked one: a later window's
    // screenshot must never ground an earlier visit's decision.
    const frame = trackedFrame
    if (frame === null || frame.imagePath === null || frame.frameId !== frameId) return null
    return readFrameImageBase64({ imagePath: frame.imagePath } as RewindFrame)
  },
  incompleteTasks: () =>
    getRecentActiveActionItems(200).map((t) => ({
      description: t.description,
      dueAt: t.dueAt,
      createdAt: t.createdAt
    })),
  retrievalHopEnabled: () => directorFlags.retrievalHop(),
  candidatesEnabled: () => directorFlags.candidates(),
  runRetrieval: (query) =>
    retrieveForQuery(query, {
      conversations: (q, limit) =>
        toolSearch('/v1/tools/conversations/search', {
          query: q,
          limit,
          include_transcript: false
        }),
      conversationChunks: (q, limit) =>
        toolSearch('/v1/tools/conversations/search-chunks', { query: q, limit }),
      memories: (q, limit) => toolSearch('/v1/tools/memories/search', { query: q, limit })
    }),
  graduate: graduateFacts,
  poolPromptSections: (bucketID, visitID) => {
    const sections: string[] = []
    const now = Date.now()
    const db = contextDirectorDb()
    const pooledIds = new Set<string>()
    if (directorFlags.workstreamPooling()) {
      const counts = workstreamTagCountsOn(db, bucketID, visitID, now)
      const tag = liveTag(counts.own, counts.bucket)
      if (tag !== null) {
        const pool = selectPooledFacts(
          workstreamPoolOn(db, tag, bucketID, now, POOL_WORTHINESS_FLOOR),
          now
        )
        for (const fact of pool) pooledIds.add(fact.factID)
        const section = workstreamPromptSection(tag, pool, now)
        if (section !== null) sections.push(section)
      }
    }
    if (directorFlags.candidates()) {
      const recent = selectRecentContextFacts(
        recentContextPoolOn(db, bucketID, now, RECENT_CONTEXT_WORTHINESS_FLOOR).filter(
          (fact) => !pooledIds.has(fact.factID)
        ),
        now
      )
      const section = recentContextPromptSection(recent, now)
      if (section !== null) sections.push(section)
    }
    return sections
  }
})

export const directorVisits = new ContextVisitCoordinator({
  startVisit: (input) => startVisitOn(contextDirectorDb(), input),
  finalizeVisit: (fence, opts) => finalizeVisitOn(contextDirectorDb(), fence, opts),
  reconcileInterruptedVisits: (now) => reconcileInterruptedVisitsOn(contextDirectorDb(), now),
  reconcileAbandonedDeliveries: (now) => reconcileAbandonedProactiveDeliveries(now),
  runDeterministicGC: (now) => runContextBucketGC(now),
  // better-sqlite3 is one process-lifetime handle; the epoch only moves on a
  // user switch, which wipes the tables anyway. Constant 1 keeps fence rows
  // comparable without inventing pool churn Windows does not have.
  poolEpoch: () => 1,
  now: () => Date.now()
})

export const directorSubjectBinding = new ContextSubjectBindingService({
  db: () => contextDirectorDb(),
  sessionEpoch: () => getSessionEpoch(),
  now: () => Date.now(),
  hasOwner: () => ownerUid() !== null
})

export const directorTcrs = new TaskContextualResurfacingService({
  bucketsEnabled: () => directorPipelineEnabled(),
  ownerId: () => ownerUid(),
  sessionEpoch: () => getSessionEpoch(),
  deviceId: () => directorDeviceId(),
  client: {
    getControl: getWorkflowControl,
    putContextSnapshot: async (snapshot, headers) => {
      const res = await apiFetch('/v1/task-intelligence/context-snapshot', {
        method: 'PUT',
        headers: {
          'Idempotency-Key': headers.idempotencyKey,
          'X-Account-Generation': String(headers.accountGeneration)
        },
        body: JSON.stringify(snapshot)
      })
      if (!res.ok) throw new Error(`context snapshot rejected: ${res.status}`)
    },
    evaluate: async (body) => {
      const res = await apiFetch('/v1/what-matters-now/evaluate', {
        method: 'POST',
        body: JSON.stringify(body)
      })
      // 404 = out-of-product: a calm no-op, matching the renderer's silent clear.
      if (res.status === 404) return null
      if (!res.ok) throw new Error(`evaluate rejected: ${res.status}`)
      return res.json()
    }
  },
  publishProjection: (raw, _urgentSubjects: TaskContextSubject[]) => {
    // Interruptions stay dark: the gate's safe default is not-enrolled and no
    // Windows opt-in surface exists yet, so only the dashboard lane is wired.
    if (raw !== null) publishProjectionToRenderer(raw)
  },
  now: () => Date.now(),
  setDebounce: (fn, ms) => setTimeout(fn, ms),
  clearDebounce: (handle) => clearTimeout(handle as NodeJS.Timeout),
  log: (message) => console.warn(`[director] ${message}`)
})

// --- extraction on qualified departures --------------------------------------

function decodeExtraction(content: string): BucketExtraction | null {
  try {
    const parsed = JSON.parse(content) as Record<string, unknown>
    if (typeof parsed.narrative !== 'string' || !Array.isArray(parsed.facts)) return null
    return parsed as unknown as BucketExtraction
  } catch {
    return null
  }
}

/** One extraction per qualified departure (mac ContextBucketRollupWriter.extract):
 *  prompt + screenshot through the extraction lane, strict schema, quota-silent;
 *  then the write, destination apply, and the flag-gated departure evaluation. */
export async function runDepartureExtraction(
  fence: ContextVisitFence,
  departingFrame: RewindFrame
): Promise<void> {
  if (fence.bucketID === null) return
  const epoch = getSessionEpoch()
  const evidenceRef =
    departingFrame.id != null ? `screenshot:${departingFrame.id}` : `visit:${fence.visitID}`
  const image = departingFrame.imagePath ? await readFrameImageBase64(departingFrame) : null
  let content: string
  try {
    const result = await directorLane.complete({
      operation: 'proactive_extraction',
      prompt: extractionPrompt({
        appName: departingFrame.app,
        windowTitle: departingFrame.windowTitle || null,
        evidenceRef
      }),
      imageBase64Jpeg: image ?? undefined,
      jsonSchema: EXTRACTION_SCHEMA as unknown as Record<string, unknown>,
      maxCompletionTokens: EXTRACTION_MAX_COMPLETION_TOKENS
    })
    content = result.content
  } catch (err) {
    // Quota cooldowns and lane failures are silent skips (mac quotaSkip).
    if (!(err instanceof LaneError)) console.warn('[director] extraction failed:', err)
    return
  }
  if (getSessionEpoch() !== epoch) return

  const extraction = decodeExtraction(content)
  if (extraction === null) return
  const db = contextDirectorDb()
  const write = writeExtractionOn(
    db,
    fence,
    extraction,
    {
      appName: departingFrame.app,
      windowTitle: departingFrame.windowTitle || null
    },
    Date.now()
  )
  if (write === null) return

  if (
    directorFlags.destinationRouting() &&
    typeof extraction.destination === 'string' &&
    isBrowser(departingFrame.app) &&
    (departingFrame.windowTitle ?? '').length > 0
  ) {
    const sanitized = sanitizeDestination(extraction.destination, departingFrame.windowTitle)
    if (sanitized !== null) applyDestinationOn(db, fence, sanitized, Date.now())
  }

  if (
    directorFlags.departureEvaluation() &&
    write.maximumValidatedWorthiness >= DEPARTURE_WORTHINESS_THRESHOLD
  ) {
    await directorEngine.evaluateAfterDeparture(fence, {
      frameId: departingFrame.id ?? null,
      appName: departingFrame.app,
      windowTitle: departingFrame.windowTitle || null,
      captureTime: departingFrame.ts,
      storedAt: Date.now()
    })
  }
}

// --- session hygiene ---------------------------------------------------------

export function currentTrackedFrame(): DirectorFrame | null {
  return trackedFrame
}

let resetWired = false

export function wireDirectorSessionReset(): void {
  if (resetWired) return
  resetWired = true
  onSessionReset(() => {
    directorLane.reset()
    directorTcrs.resetOwnerState()
    directorSubjectBinding.reset()
    clearTrackedFrame()
    void directorVisits.reset()
  })
  // Turning the pipeline OFF closes the active visit (as leaving to an
  // excluded context) so it cannot absorb contexts observed while TCRS owns
  // the world. Tracks the effective pipeline state, so an env force that keeps
  // the pipeline on regardless of the setting never triggers a close.
  let pipelineWasEnabled = directorPipelineEnabled()
  onAppSettingsChanged(() => {
    const enabled = directorPipelineEnabled()
    if (pipelineWasEnabled && !enabled) void directorVisits.leaveForExcludedContext(null)
    pipelineWasEnabled = enabled
  })
}
