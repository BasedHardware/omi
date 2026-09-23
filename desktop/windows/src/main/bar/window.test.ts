import { describe, it, expect, vi, beforeEach } from 'vitest'

// ----------- Module mocks (hoisted before all imports) -----------

// vi.mock factories run before module imports, so refs that must be accessible
// in both the factory and the test body need vi.hoisted().
const { mockSend, mockFire } = vi.hoisted(() => ({
  mockSend: vi.fn(),
  mockFire: vi.fn()
}))

// Override the electron alias (set in vitest.config.ts) with a stub that
// covers all the BrowserWindow methods createBarWindow() calls. The shared
// stub only stubs the subset needed by pure-logic tests.
vi.mock('electron', () => {
  const win = {
    setAlwaysOnTop: vi.fn(),
    setIgnoreMouseEvents: vi.fn(),
    setContentProtection: vi.fn(),
    setOpacity: vi.fn(),
    setBounds: vi.fn(),
    getBounds: vi.fn(() => ({ x: -9999, y: -9999, width: 560, height: 400 })),
    on: vi.fn(),
    showInactive: vi.fn(),
    loadURL: vi.fn(),
    loadFile: vi.fn(),
    isFocused: vi.fn(() => false),
    isDestroyed: vi.fn(() => false),
    webContents: { send: mockSend, on: vi.fn(), executeJavaScript: vi.fn() }
  }
  const BrowserWindow = vi.fn(() => win)
  ;(BrowserWindow as unknown as Record<string, unknown>).getAllWindows = vi.fn(() => [])
  return {
    BrowserWindow,
    ipcMain: { on: vi.fn(), handle: vi.fn(), removeAllListeners: vi.fn(), removeHandler: vi.fn() },
    screen: {
      getCursorScreenPoint: vi.fn(() => ({ x: 0, y: 0 })),
      getDisplayNearestPoint: vi.fn(() => ({
        id: 1,
        bounds: { x: 0, y: 0, width: 1920, height: 1080 },
        workArea: { x: 0, y: 0, width: 1920, height: 1040 },
        scaleFactor: 1
      }))
    },
    powerMonitor: { on: vi.fn() },
    nativeImage: { createEmpty: () => ({}), createFromPath: () => ({}) },
    app: { quit: vi.fn(), getPath: vi.fn(() => '/'), on: vi.fn(), getVersion: vi.fn(() => '0.0.0') },
    globalShortcut: { register: vi.fn(), unregister: vi.fn(), isRegistered: vi.fn(() => false) },
    shell: { openExternal: vi.fn() },
    Menu: { buildFromTemplate: vi.fn(() => ({ popup: vi.fn() })) },
    clipboard: { writeText: vi.fn() },
    Notification: vi.fn()
  }
})

vi.mock('@electron-toolkit/utils', () => ({ is: { dev: false } }))

// Spy on the gesture machine so we can assert it is never entered by summonFromTray.
vi.mock('./gesture', () => ({
  SummonGesture: vi.fn().mockImplementation(() => ({
    fire: mockFire,
    dispose: vi.fn(),
    endIfActive: vi.fn(),
    get isActive() {
      return false
    }
  }))
}))

// installBarContextMenu has a deep import chain (notify, voicePlaneIpc, insight,
// notifications, Firebase, …). Stub the whole module so window.ts stays importable
// without pulling in live network/auth dependencies.
vi.mock('./barContextMenu', () => ({ installBarContextMenu: vi.fn() }))

// ----------- Module under test -----------

import { summonFromTray, setBarEnabled } from './window'

describe('summonFromTray — PTT regression (PR #12074)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('never enters the gesture machine or emits bar:ptt when invoked as the tray callback', () => {
    // Arm the bar — the tray item is only reachable when barEnabled is true.
    setBarEnabled(true)

    summonFromTray()

    // Regression guard: the old code wired the tray item to handleSummonPress(),
    // which routes through gesture.fire() → onGestureStart() → sendPtt('down').
    // With no Space key physically held, the 1200ms gap timer fires onGestureEnd()
    // with kind='hold' → sendPtt('up'), producing ~1s of unintended microphone
    // capture. summonFromTray() bypasses the gesture machine entirely — it calls
    // showBar()/hideBar() directly — so neither fire() nor bar:ptt must be touched.
    expect(mockFire).not.toHaveBeenCalled()
    expect(mockSend).not.toHaveBeenCalledWith('bar:ptt', expect.anything())
  })
})
