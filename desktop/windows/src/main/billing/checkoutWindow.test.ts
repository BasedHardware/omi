import { EventEmitter } from 'node:events'
import { beforeEach, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ windows: [] as any[] }))
vi.mock('electron', () => ({
  ipcMain: { handle: vi.fn() },
  shell: { openExternal: vi.fn() },
  BrowserWindow: class extends EventEmitter {
    static getFocusedWindow() {
      return undefined
    }
    static getAllWindows() {
      return []
    }
    webContents = new EventEmitter()
    destroyed = false
    show = vi.fn()
    constructor() {
      super()
      mocks.windows.push(this)
    }
    isDestroyed() {
      return this.destroyed
    }
    destroy() {
      this.destroyed = true
    }
    loadURL() {
      return Promise.resolve()
    }
  }
}))
vi.mock('../contextMenu', () => ({ installContextMenu: vi.fn() }))
import { openCheckoutWindow } from './checkoutWindow'
beforeEach(() => {
  mocks.windows.length = 0
})
it('window opened is emitted only after show, never URL acquisition or instantiation', async () => {
  const opened = vi.fn()
  const result = openCheckoutWindow('https://checkout.stripe.test/private', opened)
  const window = mocks.windows[0]
  expect(opened).not.toHaveBeenCalled()
  window.emit('ready-to-show')
  expect(window.show).toHaveBeenCalledOnce()
  expect(opened).toHaveBeenCalledOnce()
  window.webContents.emit('will-redirect', {}, 'https://api.test/v1/payments/success')
  expect(await result).toBe('success')
  expect(window.destroyed).toBe(true)
})
it.each(['cancel', 'closed'])('%s never resolves as successful navigation', async (outcome) => {
  const result = openCheckoutWindow('https://checkout.stripe.test/private')
  const window = mocks.windows[0]
  if (outcome === 'cancel')
    window.webContents.emit('will-navigate', {}, 'https://api.test/v1/payments/cancel')
  else window.emit('closed')
  expect(await result).toBe(outcome)
})
it('refused URL never opens a checkout window', async () => {
  const opened = vi.fn()
  await expect(openCheckoutWindow('file:///private', opened)).rejects.toThrow()
  expect(opened).not.toHaveBeenCalled()
  expect(mocks.windows).toHaveLength(0)
})
it('closing before ready does not report opened on a late callback', async () => {
  const opened = vi.fn()
  const result = openCheckoutWindow('https://checkout.stripe.test/private', opened)
  mocks.windows[0].emit('closed')
  mocks.windows[0].emit('ready-to-show')
  expect(await result).toBe('closed')
  expect(opened).not.toHaveBeenCalled()
})
