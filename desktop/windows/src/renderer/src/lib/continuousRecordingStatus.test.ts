import { beforeEach, expect, it } from 'vitest'
import {
  formatRecordingStatusTime,
  getContinuousRecordingStatus,
  noteContinuousRecordingConversationSync,
  noteContinuousRecordingEvent,
  noteContinuousRecordingTranscript,
  noteListenWebSocketConnecting,
  noteListenWebSocketOpen,
  resetContinuousRecordingStatusForTests,
  setContinuousRecordingAuth,
  setContinuousRecordingPreference,
  subscribeContinuousRecordingStatus,
  websocketStateLabel,
  websocketStateTone
} from './continuousRecordingStatus'

beforeEach(() => {
  resetContinuousRecordingStatusForTests()
})

it('tracks auth, preference, websocket, transcript, and conversation sync state', () => {
  let calls = 0
  const unsubscribe = subscribeContinuousRecordingStatus(() => {
    calls++
  })

  setContinuousRecordingAuth({ signedIn: true, email: 'ada@example.com' })
  setContinuousRecordingPreference(true)
  noteListenWebSocketConnecting('listen-1', 1000)
  noteListenWebSocketOpen('listen-1', 1500)
  noteContinuousRecordingTranscript(2000)
  noteContinuousRecordingEvent('memory_creating', 2500)
  noteContinuousRecordingConversationSync(3000)

  const status = getContinuousRecordingStatus()
  expect(status.signedIn).toBe(true)
  expect(status.authEmail).toBe('ada@example.com')
  expect(status.recordingEnabled).toBe(true)
  expect(status.sessionActive).toBe(true)
  expect(status.websocketState).toBe('open')
  expect(status.websocketSessionId).toBe('listen-1')
  expect(status.websocketUpdatedAt).toBe(1500)
  expect(status.lastTranscriptAt).toBe(2000)
  expect(status.lastConversationBoundaryAt).toBe(2500)
  expect(status.lastConversationSyncAt).toBe(3000)
  expect(calls).toBe(7)

  unsubscribe()
})

it('formats recent status timestamps for diagnostic tiles', () => {
  const now = 10 * 60 * 1000

  expect(formatRecordingStatusTime(null, now)).toBe('Never')
  expect(formatRecordingStatusTime(now - 2000, now)).toBe('Just now')
  expect(formatRecordingStatusTime(now - 12000, now)).toBe('12s ago')
  expect(formatRecordingStatusTime(now - 3 * 60 * 1000, now)).toBe('3m ago')
  expect(formatRecordingStatusTime(now - 2 * 60 * 60 * 1000, now)).toBe('2h ago')
})

it('labels websocket states with useful tones', () => {
  expect(websocketStateLabel('idle')).toBe('Idle')
  expect(websocketStateLabel('connecting')).toBe('Connecting')
  expect(websocketStateLabel('open')).toBe('Open')
  expect(websocketStateLabel('closed')).toBe('Closed')
  expect(websocketStateLabel('error')).toBe('Error')

  expect(websocketStateTone('open')).toBe('good')
  expect(websocketStateTone('connecting')).toBe('neutral')
  expect(websocketStateTone('idle')).toBe('neutral')
  expect(websocketStateTone('closed')).toBe('warn')
  expect(websocketStateTone('error')).toBe('warn')
})
