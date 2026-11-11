// Exercises the real preload projection: only main's bounded observation can complete telemetry.
// Optional callbacks/listener faults must preserve the legacy product outcome and listener cleanup.
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { OmiBridgeApi } from '../shared/types'

// The preload/node tsconfig intentionally has no renderer Window augmentation.
// The real preload still writes this bridge onto the stubbed global below.
const bridge = (): OmiBridgeApi => (window as unknown as { omi: OmiBridgeApi }).omi
const h = vi.hoisted(() => ({
  listener: undefined as undefined | (() => void),
  invoke: vi.fn(),
  once: vi.fn(),
  remove: vi.fn()
}))
vi.mock('@electron-toolkit/preload', () => ({ electronAPI: {} }))
vi.mock('electron', () => ({
  contextBridge: { exposeInMainWorld: vi.fn() },
  ipcRenderer: {
    invoke: h.invoke,
    once: h.once,
    removeListener: h.remove,
    on: vi.fn(),
    send: vi.fn()
  }
}))
beforeEach(async () => {
  vi.resetModules()
  vi.clearAllMocks()
  vi.stubGlobal('window', {})
  h.listener = undefined
  h.once.mockImplementation((_channel, listener) => {
    h.listener = listener
  })
  h.remove.mockImplementation(() => {
    h.listener = undefined
  })
  await import('./index')
})
afterEach(() => vi.unstubAllGlobals())
it('projects legacy outcome and orders opened before verified completion, without returning observation data', async () => {
  const order: string[] = []
  h.invoke.mockImplementation(async () => {
    h.listener?.()
    return { outcome: 'success', observedCompletion: true }
  })
  expect(
    await bridge().openCheckout(
      'fixture',
      () => order.push('opened'),
      () => order.push('completed')
    )
  ).toBe('success')
  expect(order).toEqual(['opened', 'completed'])
  expect(h.invoke).toHaveBeenCalledWith('billing:openCheckout', 'fixture')
  expect(h.remove).toHaveBeenCalledOnce()
  expect(h.listener).toBeUndefined()
})
it.each([
  ['success', false],
  ['cancel', true],
  ['closed', true],
  ['success', 'true']
])(
  'only exact success plus true can invoke completed (%s / %s)',
  async (outcome, observedCompletion) => {
    h.invoke.mockResolvedValue({ outcome, observedCompletion })
    const completed = vi.fn()
    expect(await bridge().openCheckout('fixture', undefined, completed)).toBe(outcome)
    expect(completed).not.toHaveBeenCalled()
  }
)
it('callback faults and visibility-listener transport faults never replace product outcome', async () => {
  h.invoke.mockImplementation(async () => {
    h.listener?.()
    return { outcome: 'success', observedCompletion: true }
  })
  const fault = () => {
    throw new Error('optional observer')
  }
  expect(await bridge().openCheckout('fixture', fault, fault)).toBe('success')
  h.once.mockImplementationOnce(fault)
  expect(await bridge().openCheckout('fixture', fault, fault)).toBe('success')
  h.remove.mockImplementationOnce(fault)
  expect(await bridge().openCheckout('fixture', fault, fault)).toBe('success')
})
it('IPC failure cleans its listener, preserves rejection and cannot complete', async () => {
  h.invoke.mockRejectedValueOnce(new Error('unavailable'))
  const completed = vi.fn()
  await expect(bridge().openCheckout('fixture', undefined, completed)).rejects.toThrow(
    'unavailable'
  )
  expect(completed).not.toHaveBeenCalled()
  expect(h.listener).toBeUndefined()
})

it('a cleanup transport fault cannot deliver a late opened callback after resolution', async () => {
  h.invoke.mockResolvedValue({ outcome: 'closed', observedCompletion: false })
  h.remove.mockImplementationOnce(() => {
    throw new Error('cleanup transport')
  })
  const opened = vi.fn()
  expect(await bridge().openCheckout('fixture', opened)).toBe('closed')
  h.listener?.()
  expect(opened).not.toHaveBeenCalled()
})
