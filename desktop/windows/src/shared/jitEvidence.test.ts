import { describe, expect, it } from 'vitest'
import {
  buildJitKeyframeReference,
  buildJitRequestedFrameReference,
  rewindDeepLink,
  selectSingleConversationKeyframe
} from './jitEvidence'

describe('Windows JIT evidence contract', () => {
  it('provides one safe Rewind deep link and no media payload', () => {
    const reference = buildJitKeyframeReference({
      frameId: 42,
      conversationId: 'conversation-1',
      capturedAtMs: 100
    })
    expect(reference.kind).toBe('keyframe')
    expect(reference.metadata.deepLink).toBe('/#/rewind?frame_id=42')
    expect(rewindDeepLink('frame:1')).toBe('/#/rewind?frame_id=frame%3A1')
  })

  it('represents terminal requested-frame states without blocking text answers', () => {
    const reference = buildJitRequestedFrameReference({
      requestId: 'request-1',
      state: 'offline',
      errorCode: 'offline'
    })
    expect(reference.state).toBe('offline')
    expect(reference.metadata).not.toHaveProperty('image')
  })

  it('selects at most one deterministic conversation keyframe', () => {
    expect(selectSingleConversationKeyframe(['frame-2', 'frame-1', 'bad id'])).toBe('frame-1')
    expect(selectSingleConversationKeyframe([])).toBeNull()
  })
})
