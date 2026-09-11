import { describe, expect, it } from 'vitest'
import {
  classifyCloseReason,
  classifyTranscriptionStop,
  DAILY_LIMIT_MESSAGE,
  QUOTA_MESSAGE
} from './transcriptionStop'

// Close reasons are the literal strings the backend sends with WS 1008
// (backend/routers/chat.py transcribe_voice_message_stream, listen/runtime.py).
describe('classifyCloseReason', () => {
  it('separates the backend 1008 reasons by meaning, not by code', () => {
    expect(classifyCloseReason('trial_expired')).toBe('quota')
    expect(classifyCloseReason('quota_exceeded')).toBe('quota')
    expect(classifyCloseReason('Daily transcription budget exhausted')).toBe('daily_limit')
    expect(classifyCloseReason('Idle timeout: no audio for 60s')).toBe('idle')
    expect(classifyCloseReason('Rate limit exceeded. Retry in 30s.')).toBe('generic')
    expect(classifyCloseReason('')).toBe('generic')
  })
})

describe('classifyTranscriptionStop', () => {
  it('recognizes the surfaced messages, including when wrapped', () => {
    expect(classifyTranscriptionStop(`Omi transcription stopped: ${QUOTA_MESSAGE}`)).toBe('quota')
    expect(
      classifyTranscriptionStop(`system: Omi transcription stopped: ${DAILY_LIMIT_MESSAGE}`)
    ).toBe('daily_limit')
    expect(
      classifyTranscriptionStop(
        'Omi transcription stopped: Omi transcribe-stream closed (1008) Idle timeout: no audio for 60s'
      )
    ).toBe('idle')
    expect(classifyTranscriptionStop('Omi /v4/listen closed (1006)')).toBe('generic')
  })
})
