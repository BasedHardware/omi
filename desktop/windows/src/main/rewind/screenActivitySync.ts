// Sync Rewind OCR metadata (and optional embeddings) to the Python backend so
// mobile chat and cross-device retrieval can answer screen-activity questions.
// Windows previously kept screen history local-only (#10728).
import { hostname } from 'node:os'
import { net } from 'electron'
import {
  fetchWithFreshToken,
  getAbortSignal,
  getBackendSession,
  getSessionEpoch,
  onSessionReset,
  type BackendSession
} from '../assistants/core/session'
import {
  fetchScreenActivitySyncCandidates,
  getAppMeta,
  markScreenActivitySyncCandidates,
  setAppMeta
} from '../ipc/db'
import { getRewindSettings } from './captureService'
import {
  buildScreenActivitySyncPayload,
  parseAccountGeneration,
  resolveWindowsClientDeviceId
} from './screenActivitySyncLogic'

export {
  boundedDeviceRetentionSeconds,
  buildScreenActivitySyncPayload,
  clientDeviceIdFromInstallId,
  formatScreenActivityTimestamp,
  parseAccountGeneration,
  resolveWindowsClientDeviceId
} from './screenActivitySyncLogic'

const SYNC_INTERVAL_MS = 60_000
const BATCH_SIZE = 100
const REQUEST_TIMEOUT_MS = 60_000

let timer: ReturnType<typeof setInterval> | null = null
let tickInFlight: Promise<void> | null = null
let consecutiveFailures = 0
let cachedAccountGeneration: { epoch: number; value: number } | null = null

onSessionReset(() => {
  stopScreenActivitySync()
})

function resolveClientDeviceId(): string {
  return resolveWindowsClientDeviceId(getAppMeta, setAppMeta)
}

function syncIntervalMs(): number {
  if (consecutiveFailures <= 0) return SYNC_INTERVAL_MS
  const backoff = SYNC_INTERVAL_MS * Math.min(16, 2 ** consecutiveFailures)
  return Math.min(backoff, 5 * SYNC_INTERVAL_MS)
}

export function onBackendSessionChanged(session: BackendSession | null): void {
  if (session) startScreenActivitySync()
  else stopScreenActivitySync()
}

export function startScreenActivitySync(): void {
  if (timer) return
  void runSyncTick()
  timer = setInterval(() => void runSyncTick(), SYNC_INTERVAL_MS)
}

export function stopScreenActivitySync(): void {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
  consecutiveFailures = 0
  cachedAccountGeneration = null
}

async function runSyncTick(): Promise<void> {
  if (tickInFlight) return tickInFlight
  tickInFlight = syncTick().finally(() => {
    tickInFlight = null
  })
  return tickInFlight
}

async function syncTick(): Promise<void> {
  try {
    const session = getBackendSession()
    if (!session?.apiBase || !session.token) return

    const epoch = getSessionEpoch()
    const candidates = fetchScreenActivitySyncCandidates(BATCH_SIZE)
    if (candidates.length === 0) return

    // Generation is the server-authoritative cutover projection (macOS
    // AccountCutoverControlManager), never inferred from local queue state.
    const accountGeneration = await resolveAccountGeneration(session, epoch)
    if (getSessionEpoch() !== epoch) return

    const payload = buildScreenActivitySyncPayload(candidates, {
      clientDeviceId: resolveClientDeviceId(),
      deviceName: hostname(),
      accountGeneration,
      retentionDays: getRewindSettings().retentionDays
    })

    const ok = await pushScreenActivityRows(session, payload, epoch)
    if (!ok) {
      consecutiveFailures += 1
      if (timer) {
        clearInterval(timer)
        timer = setInterval(() => void runSyncTick(), syncIntervalMs())
      }
      return
    }
    if (getSessionEpoch() !== epoch) return
    markScreenActivitySyncCandidates(candidates)
    consecutiveFailures = 0
  } catch (e) {
    console.warn('[screen-activity-sync] tick error:', (e as Error).message)
  }
}

async function resolveAccountGeneration(session: BackendSession, epoch: number): Promise<number> {
  if (cachedAccountGeneration?.epoch === epoch) return cachedAccountGeneration.value
  const url = `${session.apiBase.replace(/\/$/, '')}/v1/account/cutover/control`
  try {
    const res = await fetchWithFreshToken(
      (s) =>
        withTimeout(
          REQUEST_TIMEOUT_MS,
          (signal) =>
            net.fetch(url, {
              method: 'GET',
              headers: {
                Authorization: `Bearer ${s.token}`,
                'X-App-Platform': 'windows'
              },
              signal
            }),
          getAbortSignal()
        ),
      'screen-activity-cutover'
    )
    if (getSessionEpoch() !== epoch) return 0
    if (!res.ok) return 0
    const parsed = parseAccountGeneration(await res.json())
    if (parsed === null) return 0
    cachedAccountGeneration = { epoch, value: parsed }
    return parsed
  } catch {
    // Legacy default matches the backend Field(default=0) and macOS
    // AccountCutoverControl.legacyDefault. Retry next tick; do not cache failures.
    return 0
  }
}

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

async function pushScreenActivityRows(
  session: BackendSession,
  payload: ReturnType<typeof buildScreenActivitySyncPayload>,
  epoch: number
): Promise<boolean> {
  const url = `${session.apiBase.replace(/\/$/, '')}/v1/screen-activity/sync`
  const body = JSON.stringify(payload)
  try {
    const res = await fetchWithFreshToken(
      (s) =>
        withTimeout(
          REQUEST_TIMEOUT_MS,
          (signal) =>
            net.fetch(url, {
              method: 'POST',
              headers: {
                Authorization: `Bearer ${s.token}`,
                'Content-Type': 'application/json',
                'X-App-Platform': 'windows'
              },
              body,
              signal
            }),
          getAbortSignal()
        ),
      'screen-activity-sync'
    )
    if (getSessionEpoch() !== epoch) return false
    if (res.status === 402) return false
    if (!res.ok) {
      console.warn(`[screen-activity-sync] HTTP ${res.status}`)
      return false
    }
    return true
  } catch (e) {
    console.warn('[screen-activity-sync] request failed:', (e as Error).message)
    return false
  }
}
