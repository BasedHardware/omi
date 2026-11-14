import { createHash, randomUUID } from 'node:crypto'
import type { ScreenActivitySyncCandidate } from '../ipc/db'

/** Stable `{platform}_{hash}` id, matching macOS ClientDeviceService. */
export function clientDeviceIdFromInstallId(installId: string): string {
  const digest = createHash('sha256').update(installId, 'utf8').digest('hex')
  return `windows_${digest.slice(0, 8)}`
}

export function resolveWindowsClientDeviceId(
  readMeta: (key: string) => string | null,
  writeMeta: (key: string, value: string) => void,
  generateId: () => string = randomUUID,
  installIdMetaKey = 'windows-install-id'
): string {
  let installId = readMeta(installIdMetaKey)
  if (!installId) {
    installId = generateId()
    writeMeta(installIdMetaKey, installId)
  }
  return clientDeviceIdFromInstallId(installId)
}

/** Backend stores lexicographically sortable UTC timestamps. */
export function formatScreenActivityTimestamp(unixMs: number): string {
  const d = new Date(unixMs)
  const ms = d.getUTCMilliseconds()
  return `${d.toISOString().slice(0, 19).replace('T', ' ')}.${String(ms).padStart(3, '0')}`
}

/** macOS `ScreenActivitySyncService.boundedDeviceRetentionSeconds`: omit when
 *  unlimited/invalid; otherwise cap at the backend's 6-day TTL. */
export function boundedDeviceRetentionSeconds(retentionDays: number): number | undefined {
  if (!Number.isFinite(retentionDays) || retentionDays < 1) return undefined
  const days = Math.min(6, Math.max(1, Math.floor(retentionDays)))
  return days * 24 * 60 * 60
}

/** Server-authoritative cutover generation from GET /v1/account/cutover/control. */
export function parseAccountGeneration(value: unknown): number | null {
  const record =
    value && typeof value === 'object' && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : null
  const generation = record?.account_generation
  if (typeof generation !== 'number' || !Number.isInteger(generation) || generation < 0) {
    return null
  }
  return generation
}

export type ScreenActivitySyncPayload = {
  account_generation: number
  deviceRetentionSeconds?: number
  rows: Record<string, unknown>[]
}

export function buildScreenActivitySyncPayload(
  candidates: ScreenActivitySyncCandidate[],
  options: {
    clientDeviceId: string
    deviceName: string
    accountGeneration: number
    retentionDays: number
  }
): ScreenActivitySyncPayload {
  const rows = candidates.map((c) => {
    const row: Record<string, unknown> = {
      id: c.id,
      timestamp: formatScreenActivityTimestamp(c.ts),
      appName: c.app,
      windowTitle: c.windowTitle,
      ocrText: c.ocrText,
      clientDeviceId: options.clientDeviceId,
      deviceName: options.deviceName
    }
    if (c.embedding) row.embedding = c.embedding
    return row
  })
  const payload: ScreenActivitySyncPayload = {
    // Same fence macOS sends from AccountCutoverControlManager. Backend skips
    // frame-request delivery when this does not match the control-plane generation.
    account_generation: options.accountGeneration,
    rows
  }
  const retention = boundedDeviceRetentionSeconds(options.retentionDays)
  if (retention !== undefined) payload.deviceRetentionSeconds = retention
  return payload
}
