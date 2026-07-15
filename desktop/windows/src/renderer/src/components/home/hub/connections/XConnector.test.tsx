// @vitest-environment jsdom
import { describe, it, expect } from 'vitest'
import { deriveView } from './XConnector'
import type { XStatus, XRunState } from '../../../../../../shared/types'

const idle: XRunState = { phase: 'idle', postCount: 0, memoryCount: 0 }
const status = (o: Partial<XStatus> = {}): XStatus => ({
  connected: false,
  postCount: 0,
  memoryCount: 0,
  syncing: false,
  ...o
})

describe('deriveView — X connector row state', () => {
  it('shows the resting prompt when idle and not connected', () => {
    const v = deriveView(null, idle)
    expect(v.state).toBe('idle')
    expect(String(v.description)).toMatch(/Connect your X account/)
  })

  it('shows a busy wait while connecting, with the close-and-keep-importing hint', () => {
    const v = deriveView(null, { ...idle, phase: 'connecting' })
    expect(v.state).toBe('busy')
    expect(String(v.description)).toMatch(/keeps importing/)
  })

  it('shows live counts while syncing', () => {
    const v = deriveView(null, { phase: 'syncing', postCount: 7, memoryCount: 3 })
    expect(v.state).toBe('busy')
    expect(String(v.description)).toMatch(/Saved 7 posts · 3 memories/)
  })

  it('shows the connected summary once connected', () => {
    const v = deriveView(
      status({ connected: true, handle: 'ada', postCount: 12, memoryCount: 5 }),
      idle
    )
    expect(v.state).toBe('connected')
    expect(String(v.description)).toMatch(/@ada/)
    expect(String(v.description)).toMatch(/12 posts, 5 memories/)
  })

  it('surfaces a friendly message when the connector is not configured', () => {
    const v = deriveView(null, { ...idle, phase: 'failed', error: 'x_oauth_not_configured' })
    expect(v.state).toBe('idle')
    expect(String(v.description)).toMatch(/isn't configured on the server yet/)
  })
})
