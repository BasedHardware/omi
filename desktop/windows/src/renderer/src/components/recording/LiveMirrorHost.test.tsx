// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, cleanup } from '@testing-library/react'
import type { CaptureEvent } from '../../../../shared/types'

// LiveMirrorHost mirrors the capture window's live ops into this window and runs
// the on-save UI side effects. Mock the store + side-effect modules and assert it
// wires them correctly.

vi.mock('../../lib/liveConversation', () => ({ liveConversation: { applyRemoteOp: vi.fn() } }))
vi.mock('../../lib/pendingConversations', () => ({ createPendingConversation: vi.fn() }))
vi.mock('../../lib/pageCache', () => ({ refreshCloudConversations: vi.fn() }))
vi.mock('../../lib/kgSynthesis', () => ({ buildLocalGraph: vi.fn() }))

import { LiveMirrorHost } from './LiveMirrorHost'
import { liveConversation } from '../../lib/liveConversation'
import { createPendingConversation } from '../../lib/pendingConversations'
import { refreshCloudConversations } from '../../lib/pageCache'

let evHandlers: Array<(e: CaptureEvent) => void>
function emit(e: CaptureEvent): void {
  for (const fn of [...evHandlers]) fn(e)
}

beforeEach(() => {
  vi.clearAllMocks()
  evHandlers = []
  ;(window as unknown as { omi: unknown }).omi = {
    onCaptureEvent: (fn: (e: CaptureEvent) => void) => {
      evHandlers.push(fn)
      return () => (evHandlers = evHandlers.filter((x) => x !== fn))
    }
  }
})
afterEach(() => cleanup())

describe('LiveMirrorHost', () => {
  it('replays every live op into the store mirror', () => {
    render(<LiveMirrorHost />)
    emit({ type: 'live', op: { op: 'reset' } })
    expect(liveConversation.applyRemoteOp).toHaveBeenCalledWith({ op: 'reset' })
  })

  it('runs the save side effects on a saved op', () => {
    render(<LiveMirrorHost />)
    const segments = [{ id: 'a', text: 'hi' }]
    emit({ type: 'live', op: { op: 'saved', segments } })
    expect(liveConversation.applyRemoteOp).toHaveBeenCalledWith({ op: 'saved', segments })
    expect(createPendingConversation).toHaveBeenCalledWith(segments)
    expect(refreshCloudConversations).toHaveBeenCalled()
  })

  it('ignores non-live capture events', () => {
    render(<LiveMirrorHost />)
    emit({ type: 'vad-status', mode: 'gated' })
    expect(liveConversation.applyRemoteOp).not.toHaveBeenCalled()
  })
})
