import { useSyncExternalStore } from 'react'

export type ListenWebSocketState = 'idle' | 'connecting' | 'open' | 'closed' | 'error'
export type RecordingDiagnosticsScope = 'live-mic' | 'recorder' | 'push-to-talk'

export type ContinuousRecordingStatusSnapshot = {
  signedIn: boolean
  authEmail: string | null
  recordingEnabled: boolean
  sessionActive: boolean
  websocketState: ListenWebSocketState
  websocketSessionId: string | null
  websocketUpdatedAt: number | null
  lastTranscriptAt: number | null
  lastConversationSyncAt: number | null
  lastConversationBoundaryAt: number | null
  lastEventType: string | null
  lastError: string | null
}

const initialStatus: ContinuousRecordingStatusSnapshot = {
  signedIn: false,
  authEmail: null,
  recordingEnabled: false,
  sessionActive: false,
  websocketState: 'idle',
  websocketSessionId: null,
  websocketUpdatedAt: null,
  lastTranscriptAt: null,
  lastConversationSyncAt: null,
  lastConversationBoundaryAt: null,
  lastEventType: null,
  lastError: null
}

let status: ContinuousRecordingStatusSnapshot = { ...initialStatus }
const subscribers = new Set<() => void>()

function publish(patch: Partial<ContinuousRecordingStatusSnapshot>): void {
  status = { ...status, ...patch }
  subscribers.forEach((cb) => cb())
}

export function getContinuousRecordingStatus(): ContinuousRecordingStatusSnapshot {
  return status
}

export function subscribeContinuousRecordingStatus(cb: () => void): () => void {
  subscribers.add(cb)
  return () => {
    subscribers.delete(cb)
  }
}

export function useContinuousRecordingStatus(): ContinuousRecordingStatusSnapshot {
  return useSyncExternalStore(
    subscribeContinuousRecordingStatus,
    getContinuousRecordingStatus,
    getContinuousRecordingStatus
  )
}

export function setContinuousRecordingAuth(user: {
  signedIn: boolean
  email?: string | null
}): void {
  publish({
    signedIn: user.signedIn,
    authEmail: user.email ?? null
  })
}

export function setContinuousRecordingPreference(enabled: boolean): void {
  publish({ recordingEnabled: enabled })
}

export function setContinuousRecordingSession(active: boolean): void {
  if (active) {
    publish({ sessionActive: true })
    return
  }
  const changed = status.sessionActive || status.websocketState !== 'idle'
  publish({
    sessionActive: false,
    websocketState: 'idle',
    websocketSessionId: null,
    websocketUpdatedAt: changed ? Date.now() : status.websocketUpdatedAt,
    lastError: null
  })
}

export function noteListenWebSocketConnecting(sessionId: string, now = Date.now()): void {
  publish({
    sessionActive: true,
    websocketState: 'connecting',
    websocketSessionId: sessionId,
    websocketUpdatedAt: now,
    lastError: null
  })
}

export function noteListenWebSocketOpen(sessionId: string, now = Date.now()): void {
  publish({
    sessionActive: true,
    websocketState: 'open',
    websocketSessionId: sessionId,
    websocketUpdatedAt: now,
    lastError: null
  })
}

export function noteListenWebSocketClosed(
  sessionId: string,
  code: number,
  reason: string,
  now = Date.now()
): void {
  publish({
    websocketState: 'closed',
    websocketSessionId: sessionId,
    websocketUpdatedAt: now,
    lastError: `Closed ${code}${reason ? `: ${reason}` : ''}`
  })
}

export function noteListenWebSocketError(
  sessionId: string,
  message: string,
  now = Date.now()
): void {
  publish({
    websocketState: 'error',
    websocketSessionId: sessionId,
    websocketUpdatedAt: now,
    lastError: message
  })
}

export function noteContinuousRecordingTranscript(now = Date.now()): void {
  publish({ lastTranscriptAt: now })
}

export function noteContinuousRecordingEvent(type: string, now = Date.now()): void {
  publish({
    lastEventType: type,
    lastConversationBoundaryAt: type === 'memory_creating' ? now : status.lastConversationBoundaryAt
  })
}

export function noteContinuousRecordingConversationSync(now = Date.now()): void {
  publish({ lastConversationSyncAt: now })
}

export function resetContinuousRecordingStatusForTests(): void {
  status = { ...initialStatus }
  subscribers.forEach((cb) => cb())
}

export function formatRecordingStatusTime(ts: number | null, now = Date.now()): string {
  if (ts == null) return 'Never'
  const elapsed = Math.max(0, now - ts)
  if (elapsed < 5000) return 'Just now'
  if (elapsed < 60000) return `${Math.floor(elapsed / 1000)}s ago`
  if (elapsed < 3600000) return `${Math.floor(elapsed / 60000)}m ago`
  if (elapsed < 86400000) return `${Math.floor(elapsed / 3600000)}h ago`
  return new Date(ts).toLocaleString()
}

export function websocketStateLabel(state: ListenWebSocketState): string {
  if (state === 'open') return 'Open'
  if (state === 'connecting') return 'Connecting'
  if (state === 'closed') return 'Closed'
  if (state === 'error') return 'Error'
  return 'Idle'
}

export function websocketStateTone(state: ListenWebSocketState): 'good' | 'warn' | 'neutral' {
  if (state === 'open') return 'good'
  if (state === 'closed' || state === 'error') return 'warn'
  return 'neutral'
}
