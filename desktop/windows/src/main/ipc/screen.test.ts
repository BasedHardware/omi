import { beforeEach, describe, expect, it, vi } from 'vitest'

const state = vi.hoisted(() => ({
  handlers: new Map<string, () => Promise<string>>(),
  latestFrame: vi.fn(),
  readRewindFrame: vi.fn(),
  ocr: vi.fn()
}))

vi.mock('electron', () => ({
  ipcMain: {
    handle: (channel: string, handler: () => Promise<string>) =>
      state.handlers.set(channel, handler)
  },
  desktopCapturer: { getSources: vi.fn().mockResolvedValue([]) }
}))
vi.mock('./db', () => ({ latestRewindFrame: () => state.latestFrame() }))
vi.mock('../ocr/helperProcess', () => ({
  helperProcess: { ocr: (jpeg: Buffer) => state.ocr(jpeg) }
}))
vi.mock('../rewind/currentScreen', () => ({
  getCurrentScreen: () => ({ text: '', ts: 0 }),
  screenCacheFresh: () => false
}))
vi.mock('../rewind/sourceId', () => ({ getPrimarySourceId: () => null }))
vi.mock('../rewind/paths', () => ({ rewindRoot: () => '/rewind' }))
vi.mock('../rewind/frameFile', () => ({
  readRewindFrame: (...args: unknown[]) => state.readRewindFrame(...args)
}))

import { registerScreenHandlers } from './screen'

describe('screen:readNow', () => {
  beforeEach(() => {
    state.handlers.clear()
    state.latestFrame.mockReturnValue({ imagePath: '/rewind/frame.jpg', ocrText: '' })
    state.readRewindFrame.mockResolvedValue(Buffer.from('jpeg'))
    state.ocr.mockResolvedValue({ ok: true, fullText: 'screen text' })
    registerScreenHandlers()
  })

  it('reads an unindexed frame through the guarded Rewind reader', async () => {
    const handler = state.handlers.get('screen:readNow')
    expect(handler).toBeDefined()
    await expect(handler!()).resolves.toBe('screen text')
    expect(state.readRewindFrame).toHaveBeenCalledWith('/rewind', '/rewind/frame.jpg')
    expect(state.ocr).toHaveBeenCalledWith(Buffer.from('jpeg'))
  })
})
