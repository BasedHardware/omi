import { describe, it, expect, vi } from 'vitest'

vi.mock('electron', () => ({
  ipcMain: { on: vi.fn(), handle: vi.fn() },
  BrowserWindow: { getAllWindows: () => [] }
}))

const { canForwardRendererDeviceCommand, sendDeviceCommandFromMain, setDeviceHostReady } =
  await import('./deviceBridge')

const MAIN_WINDOW_ID = 7
const OTHER_WINDOW_ID = 9

describe('canForwardRendererDeviceCommand', () => {
  it('allows pairing and lifecycle commands from the main window only', () => {
    for (const type of [
      'device-pair',
      'device-pair-cancel',
      'device-connect',
      'device-disconnect',
      'device-forget'
    ] as const) {
      const cmd = { type, deviceId: 'd' } as never
      expect(canForwardRendererDeviceCommand(cmd, MAIN_WINDOW_ID, MAIN_WINDOW_ID)).toBe(true)
      // An auxiliary renderer (toast, glow, overlay) must never be able to
      // unpair someone's device or start a Bluetooth scan.
      expect(canForwardRendererDeviceCommand(cmd, OTHER_WINDOW_ID, MAIN_WINDOW_ID)).toBe(false)
    }
  })

  it('allows settings and auth pushes from the main window only', () => {
    const settings = {
      type: 'device-settings',
      settings: { pairedDevice: null, autoReconnect: true, deviceListenEnabled: false }
    } as never
    expect(canForwardRendererDeviceCommand(settings, MAIN_WINDOW_ID, MAIN_WINDOW_ID)).toBe(true)
    expect(canForwardRendererDeviceCommand(settings, OTHER_WINDOW_ID, MAIN_WINDOW_ID)).toBe(false)
  })

  it('rejects everything when there is no main window to compare against', () => {
    const cmd = { type: 'device-pair' } as never
    expect(canForwardRendererDeviceCommand(cmd, MAIN_WINDOW_ID, undefined)).toBe(false)
  })

  it('rejects unknown command types', () => {
    expect(
      canForwardRendererDeviceCommand(
        { type: 'device-explode' } as never,
        MAIN_WINDOW_ID,
        MAIN_WINDOW_ID
      )
    ).toBe(false)
  })
})

describe('command queueing before the host is ready', () => {
  const makeWc = (): {
    sent: unknown[]
    wc: { isDestroyed: () => boolean; send: (c: string, p: unknown) => void }
  } => {
    const sent: unknown[] = []
    return {
      sent,
      wc: {
        isDestroyed: () => false,
        send: (_channel, payload) => sent.push(payload)
      }
    }
  }

  it('holds commands until the host announces itself, then flushes in order', () => {
    setDeviceHostReady(false, () => null)
    const { sent, wc } = makeWc()
    const getWc = (): never => wc as never

    sendDeviceCommandFromMain(getWc, { type: 'device-pair' })
    sendDeviceCommandFromMain(getWc, { type: 'device-disconnect' })
    // A window still loading would drop these silently without the queue.
    expect(sent.length).toBe(0)

    setDeviceHostReady(true, getWc)
    expect(sent).toEqual([{ cmd: { type: 'device-pair' } }, { cmd: { type: 'device-disconnect' } }])

    sendDeviceCommandFromMain(getWc, { type: 'device-forget' })
    expect(sent.length).toBe(3)
  })

  it('bounds the queue so a host that never comes up cannot grow it forever', () => {
    setDeviceHostReady(false, () => null)
    const { sent, wc } = makeWc()
    const getWc = (): never => wc as never
    for (let i = 0; i < 40; i += 1) {
      sendDeviceCommandFromMain(getWc, { type: 'device-connect', deviceId: `d${i}` })
    }
    setDeviceHostReady(true, getWc)
    expect(sent.length).toBe(16)
    // The most recent commands are the ones that survive.
    expect(sent[sent.length - 1]).toEqual({
      cmd: { type: 'device-connect', deviceId: 'd39' }
    })
  })
})
