import { EventEmitter } from 'node:events'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
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
import { openCheckoutWindow, registerBillingIpc } from './checkoutWindow'
beforeEach(() => {
  mocks.windows.length = 0
  vi.stubEnv('VITE_OMI_API_BASE', 'https://api.test')
})
afterEach(() => vi.unstubAllEnvs())
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

it.each([
  ['exact query', 'https://api.test/v1/payments/success?session_id=fixture', true],
  ['default port', 'https://api.test:443/v1/payments/success', true],
  ['wrong host', 'https://other.test/v1/payments/success', false],
  ['host suffix', 'https://api.test.evil.test/v1/payments/success', false],
  ['scheme', 'http://api.test/v1/payments/success', false],
  ['port', 'https://api.test:444/v1/payments/success', false],
  ['prefix', 'https://api.test/v1/payments/success-extra', false],
  ['extra path', 'https://api.test/v1/payments/success/extra', false],
  ['trailing slash', 'https://api.test/v1/payments/success/', false],
  ['userinfo', 'https://user@api.test/v1/payments/success', false],
  ['empty userinfo', 'https://@api.test/v1/payments/success', false]
])(
  'legacy success remains unchanged for %s; new completion requires configured exact origin/path',
  async (_label, url, trusted) => {
    const verified = vi.fn()
    const result = openCheckoutWindow('https://checkout.stripe.test/private', vi.fn(), verified)
    const window = mocks.windows[0]
    window.emit('ready-to-show')
    window.webContents.emit('will-redirect', {}, url)
    window.webContents.emit('did-navigate', {}, 'https://api.test/v1/payments/success')
    expect(await result).toBe('success')
    expect(verified).toHaveBeenCalledTimes(trusted ? 1 : 0)
  }
)
it.each(['cancel', 'closed', 'failure'])(
  'late trusted navigation after %s never verifies',
  async (outcome) => {
    const verified = vi.fn()
    const result = openCheckoutWindow('https://checkout.stripe.test/private', vi.fn(), verified)
    const window = mocks.windows[0]
    window.emit('ready-to-show')
    if (outcome === 'cancel')
      window.webContents.emit('will-navigate', {}, 'https://api.test/v1/payments/cancel')
    if (outcome === 'closed') window.emit('closed')
    if (outcome === 'failure')
      window.webContents.emit('did-fail-load', {}, -2, 'fixture', 'fixture', true)
    window.webContents.emit('will-redirect', {}, 'https://api.test/v1/payments/success')
    await result
    expect(verified).not.toHaveBeenCalled()
  }
)
it('main IPC returns only a closed outcome/verification pair and observation faults preserve outcome', async () => {
  const { ipcMain } = await import('electron')
  registerBillingIpc()
  const handler = vi
    .mocked(ipcMain.handle)
    .mock.calls.find(([channel]) => channel === 'billing:openCheckout')![1]
  const result = handler(
    {
      sender: {
        isDestroyed: () => false,
        send() {
          throw new Error('transport')
        }
      }
    } as any,
    'https://checkout.stripe.test/private'
  )
  const window = mocks.windows[0]
  window.emit('ready-to-show')
  window.webContents.emit('will-navigate', {}, 'https://api.test/v1/payments/success')
  expect(await result).toEqual({ outcome: 'success', observedCompletion: true })
  const fault = openCheckoutWindow(
    'https://checkout.stripe.test/private',
    () => {},
    () => {
      throw new Error('observer')
    }
  )
  mocks.windows[1].webContents.emit('will-navigate', {}, 'https://api.test/v1/payments/success')
  expect(await fault).toBe('success')
})

it('verification follows main-owned configured API origin, including a nondefault configured port', async () => {
  vi.stubEnv('VITE_OMI_API_BASE', 'https://configured.test:8443')
  for (const [index, url] of [
    'https://api.test/v1/payments/success',
    'https://configured.test:8443/v1/payments/success?session_id=fixture'
  ].entries()) {
    const verified = vi.fn()
    const result = openCheckoutWindow('https://checkout.stripe.test/private', vi.fn(), verified)
    mocks.windows[index].webContents.emit('will-redirect', {}, url)
    expect(await result).toBe('success')
    expect(verified).toHaveBeenCalledTimes(index)
  }
})
