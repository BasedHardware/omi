import { registerAssistant } from '../assistants/core/coordinator'
import { getBackendSession, onSessionReset } from '../assistants/core/session'
import { getJitDatabase, isJitMirrorAvailable } from '../ipc/db'
import {
  WindowsJitAssistant,
  createWindowsJitAgentTurnExecutor,
  createWindowsJitNanoTriageExecutor,
  setWindowsJitAgentTurnExecutor,
  setWindowsJitNanoTriageExecutor
} from './jitAssistant'
import { WindowsJitRuntime } from './jitRuntime'
import type { JitMirrorDb } from './jitTriggerMirror'
import { createJitFeedbackTransport, startJitFeedbackRetryLoop } from './jitFeedback'
import { setJitLegacyAmbientGate } from '../assistants/core/notify'
import { startPendingJitKeyframeCleanupWorker } from '../ipc/db'

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
let runtime: WindowsJitRuntime | null = null

/** Register the JIT peer with the existing coordinator. The executor is the
 * shipped Windows agent-kernel/pi-mono path; backend authority still gates every
 * paid/display boundary and flag-off keeps the legacy lane available. */
export function registerJitAssistant(): void {
  if (registered) return
  const mirrorDb = getJitDatabase() as unknown as JitMirrorDb
  // The mirror bootstrap is guarded so a failure cannot block opening the shared
  // database. When it did fail no `jit_*` table exists, so the lane stays
  // unregistered rather than throwing on the first analyzed frame; the legacy
  // assistants remain the delivery path exactly as with the flag off.
  if (!isJitMirrorAvailable()) {
    console.warn('[jit] trigger mirror unavailable; JIT assistant not registered')
    return
  }
  registered = true
  runtime = WindowsJitRuntime.withDefaultDb(
    mirrorDb,
    tokenOwnerId,
    () => null,
    () => getBackendSession() !== null
  )
  setWindowsJitAgentTurnExecutor(createWindowsJitAgentTurnExecutor())
  setWindowsJitNanoTriageExecutor(createWindowsJitNanoTriageExecutor())
  setJitLegacyAmbientGate(() => runtime?.shouldSuppressLegacyInsight() === true)
  registerAssistant(new WindowsJitAssistant(runtime))
  // Keyframe pins outlive renderer/session processes. Retry file/reference
  // cleanup independently on launch and on a bounded interval.
  startPendingJitKeyframeCleanupWorker()
  // Startup plus bounded scheduled drains cover launch/auth/network recovery;
  // completion still requires the strict server receipt.
  startJitFeedbackRetryLoop(
    getJitDatabase() as unknown as JitMirrorDb,
    createJitFeedbackTransport()
  )
  onSessionReset(() => {
    runtime?.clearForSignOut()
  })
}
