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

export function boundedDeviceRetentionSeconds(retentionDays: number): number | undefined {
  if (!Number.isFinite(retentionDays) || retentionDays < 1) return undefined
  const days = Math.min(6, Math.max(1, Math.floor(retentionDays)))
  return days * 24 * 60 * 60
}

export function buildScreenActivitySyncPayload(
  candidates: ScreenActivitySyncCandidate[],
  options: {
    clientDeviceId: string
    deviceName: string
  }
): { rows: Record<string, unknown>[] } {
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
  return { rows }
}
