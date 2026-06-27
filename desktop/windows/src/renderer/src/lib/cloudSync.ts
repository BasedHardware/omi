// Cloud sync — Pro feature, currently a stub.
//
// The real implementation will push an encrypted snapshot of conversations,
// memories and settings to cortex.apym.io and pull on other devices. For now
// this records intent + a local "last synced" marker and exposes the same API
// surface the UI will use, so the Pro tab is wired end-to-end without a backend.
import { featureEnabled } from './license'

const KEY = 'cortex-cloud-sync-v1'

export type SyncState = {
  enabled: boolean
  lastSyncedAt?: number
  /** Endpoint the snapshot will be pushed to once implemented. */
  endpoint: string
}

const defaults: SyncState = { enabled: false, endpoint: 'https://cortex.apym.io/api/sync' }

function load(): SyncState {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? { ...defaults, ...(JSON.parse(raw) as Partial<SyncState>) } : { ...defaults }
  } catch {
    return { ...defaults }
  }
}

let current: SyncState = load()

function persist(): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(current))
  } catch {
    /* ignore */
  }
}

export function getSyncState(): SyncState {
  return current
}

export function setSyncEnabled(enabled: boolean): void {
  current = { ...current, enabled }
  persist()
}

export type SyncResult = { ok: boolean; reason?: string; at?: number }

/**
 * Stub sync. Gated behind the Pro `cloud-sync` feature. Returns a
 * not-implemented result for now but performs the gating + bookkeeping so the
 * UI behaves correctly today.
 */
export async function runSync(): Promise<SyncResult> {
  if (!featureEnabled('cloud-sync')) {
    return { ok: false, reason: 'Cloud sync is a Cortex Pro feature.' }
  }
  if (!current.enabled) {
    return { ok: false, reason: 'Cloud sync is turned off.' }
  }
  // TODO: encrypt + POST snapshot to `current.endpoint`. Stubbed for now.
  current = { ...current, lastSyncedAt: Date.now() }
  persist()
  return {
    ok: true,
    reason: 'Sync stub: snapshot recorded locally (server upload not yet implemented).',
    at: current.lastSyncedAt
  }
}
