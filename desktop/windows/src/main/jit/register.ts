import { registerAssistant } from '../assistants/core/coordinator'
import { getBackendSession, onSessionReset } from '../assistants/core/session'
import { getJitDatabase, isJitMirrorAvailable, startPendingJitKeyframeCleanupWorker } from '../ipc/db'
import type { JitMirrorDb } from './jitTriggerMirror'
import { KnowledgeLedgerMirrorSync } from './knowledgeLedgerMirrorSync'

function tokenOwnerId(): string | null {
  const token = getBackendSession()?.token
  if (!token) return null
  try {
    const segment = token.split('.')[1]
    const payload = JSON.parse(Buffer.from(segment, 'base64').toString('utf8')) as {
      sub?: unknown
      user_id?: unknown
    }
    const owner = payload.user_id ?? payload.sub
    return typeof owner === 'string' && owner.trim() ? owner.trim() : null
  } catch {
    return null
  }
}

let registered = false

export function registerKnowledgeLedgerMirrorSync(): void {
  if (registered) return
  // Retention cleanup remains independent of the canonical mirror's availability.
  startPendingJitKeyframeCleanupWorker()
  if (!isJitMirrorAvailable()) return
  registered = true
  const sync = new KnowledgeLedgerMirrorSync(getJitDatabase() as unknown as JitMirrorDb, tokenOwnerId)
  registerAssistant(sync)
  onSessionReset(() => sync.stop())
}
