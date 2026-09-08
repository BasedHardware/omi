import { describe, it, expect, vi } from 'vitest'
import { requestSettingsTab, onSettingsTabRequest, consumeSettingsTabRequest } from './settingsNav'

describe('settingsNav deep-link channel', () => {
  it('does not deliver anything to a subscriber when nothing was requested', () => {
    const cb = vi.fn()
    const off = onSettingsTabRequest(cb)
    off()
    expect(cb).not.toHaveBeenCalled()
  })

  it('replays a request made before the consumer subscribed (navigate-then-mount race)', () => {
    requestSettingsTab('plan-usage')
    const cb = vi.fn()
    const off = onSettingsTabRequest(cb)
    expect(cb).toHaveBeenCalledWith('plan-usage')
    off()
    consumeSettingsTabRequest()
  })

  it('delivers a request made after the consumer already subscribed', () => {
    const cb = vi.fn()
    const off = onSettingsTabRequest(cb)
    cb.mockClear() // drop the initial (empty) replay call
    requestSettingsTab('shortcuts')
    expect(cb).toHaveBeenCalledWith('shortcuts')
    off()
    consumeSettingsTabRequest()
  })

  it('consuming clears the buffer so the next subscriber gets nothing', () => {
    requestSettingsTab('about')
    const first = vi.fn()
    const offFirst = onSettingsTabRequest(first)
    expect(first).toHaveBeenCalledWith('about')
    consumeSettingsTabRequest()
    offFirst()

    const second = vi.fn()
    const offSecond = onSettingsTabRequest(second)
    expect(second).not.toHaveBeenCalled()
    offSecond()
  })
})
