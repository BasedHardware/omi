import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => {
  const ipcHandlers = new Map<string, (...args: unknown[]) => unknown>()
  return {
    ipcHandlers,
    defaultSignOpts: vi.fn(() => ({ baseUrl: null, posesDir: undefined })),
    translateToGlosses: vi.fn()
  }
})

vi.mock('electron', () => ({
  ipcMain: {
    handle: (channel: string, handler: (...args: unknown[]) => unknown) => h.ipcHandlers.set(channel, handler)
  }
}))

vi.mock('../integrations/signLanguage', () => ({
  defaultSignOpts: h.defaultSignOpts,
  translateToGlosses: h.translateToGlosses
}))
vi.mock('../integrations/stickyNotes', () => ({ readStickyNotes: vi.fn() }))
vi.mock('../integrations/oauth', () => ({
  connect: vi.fn(),
  disconnect: vi.fn(),
  isConnected: vi.fn(() => false),
  connectedEmail: vi.fn()
}))
vi.mock('../integrations/google', () => ({ fetchGmail: vi.fn(), fetchCalendar: vi.fn() }))
vi.mock('../integrations/xConnector', () => ({
  xConnect: vi.fn(),
  xStatus: vi.fn(),
  xSync: vi.fn(),
  xDisconnect: vi.fn(),
  xRunStateSnapshot: vi.fn()
}))
vi.mock('../integrations/syncState', () => ({
  getSourceState: vi.fn(),
  markProcessed: vi.fn(),
  lastSyncAt: vi.fn(),
  clearSyncState: vi.fn()
}))
vi.mock('../integrations/syncStateLogic', () => ({ filterNew: vi.fn() }))
vi.mock('../integrations/gmailSession', () => ({
  gmailSessionConnect: vi.fn(),
  gmailSessionStatus: vi.fn(),
  gmailSessionVerify: vi.fn(),
  gmailSessionFetch: vi.fn(),
  gmailSessionDisconnect: vi.fn()
}))

import { isSignLanguageEnabled, registerIntegrationsHandlers, setSignLanguageEnabled } from './integrations'

describe('integrations:signLanguage:translate IPC', () => {
  beforeEach(() => {
    h.ipcHandlers.clear()
    h.defaultSignOpts.mockClear()
    h.translateToGlosses.mockReset()
    setSignLanguageEnabled(false)
    registerIntegrationsHandlers()
  })

  it('does not translate while sign language is disabled', async () => {
    const handler = h.ipcHandlers.get('integrations:signLanguage:translate')!

    const result = await handler({}, { text: 'private transcript' })

    expect(result).toEqual({
      originalText: 'private transcript',
      poseUrl: '',
      assetType: 'pose',
      swrFull: 'TRANSLATION_UNAVAILABLE',
      glosses: []
    })
    expect(h.translateToGlosses).not.toHaveBeenCalled()
    expect(isSignLanguageEnabled()).toBe(false)
  })

  it('translates through the handler only after opt-in', async () => {
    const expected = { originalText: 'hello', poseUrl: 'data:', glosses: [] }
    h.translateToGlosses.mockResolvedValue(expected)
    setSignLanguageEnabled(true)

    const handler = h.ipcHandlers.get('integrations:signLanguage:translate')!
    const result = await handler({}, { text: 'hello' })

    expect(result).toBe(expected)
    expect(h.translateToGlosses).toHaveBeenCalledWith('hello', 'en', 'ase', { baseUrl: null, posesDir: undefined })
  })
})
