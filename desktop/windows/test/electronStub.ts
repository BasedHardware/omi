// Test-only stub for the `electron` module.
//
// Node-side Vitest suites import main-process modules (e.g. overlay/shortcut,
// automation/bridge) whose module graph pulls in `electron`. The real package's
// entry resolves a native binary path and throws under a headless
// `npm install --ignore-scripts`. This stub is aliased in for `electron` in
// vitest.config.ts so those suites can exercise pure logic without the binary.
//
// It is intentionally minimal and inert: methods are no-ops with sensible
// return shapes. If a test needs specific Electron behaviour, mock it locally
// with `vi.mock('electron', ...)` in that suite instead of expanding this stub.

const noop = (): void => {}

export const app = {
  getPath: (): string => '/tmp',
  getAppPath: (): string => '/tmp/app',
  getName: (): string => 'omi-windows',
  getVersion: (): string => '0.0.0-test',
  isPackaged: false,
  on: noop,
  once: noop,
  whenReady: (): Promise<void> => Promise.resolve(),
  quit: noop,
  setLoginItemSettings: noop,
  requestSingleInstanceLock: (): boolean => true
}

export const globalShortcut = {
  register: (): boolean => true,
  unregister: noop,
  unregisterAll: noop,
  isRegistered: (): boolean => false
}

export const ipcMain = { on: noop, once: noop, handle: noop, removeHandler: noop, removeAllListeners: noop }
export const ipcRenderer = { on: noop, once: noop, invoke: (): Promise<undefined> => Promise.resolve(undefined), send: noop }
export const contextBridge = { exposeInMainWorld: noop }
export const shell = { openExternal: (): Promise<void> => Promise.resolve(), openPath: (): Promise<string> => Promise.resolve('') }
export const dialog = {
  showMessageBox: (): Promise<{ response: number }> => Promise.resolve({ response: 0 }),
  showOpenDialog: (): Promise<{ canceled: boolean; filePaths: string[] }> =>
    Promise.resolve({ canceled: true, filePaths: [] })
}
export const screen = {
  getPrimaryDisplay: (): { bounds: { x: number; y: number; width: number; height: number }; workAreaSize: { width: number; height: number }; scaleFactor: number } => ({
    bounds: { x: 0, y: 0, width: 1920, height: 1080 },
    workAreaSize: { width: 1920, height: 1040 },
    scaleFactor: 1
  }),
  getAllDisplays: (): unknown[] => [],
  on: noop
}
export const powerMonitor = { on: noop, getSystemIdleTime: (): number => 0 }
export const safeStorage = {
  isEncryptionAvailable: (): boolean => false,
  encryptString: (s: string): Buffer => Buffer.from(s),
  decryptString: (b: Buffer): string => b.toString()
}
export const session = { defaultSession: { webRequest: { onBeforeSendHeaders: noop } } }
export const net = { request: noop, isOnline: (): boolean => true }
export const desktopCapturer = { getSources: (): Promise<unknown[]> => Promise.resolve([]) }
export const nativeImage = { createEmpty: (): Record<string, never> => ({}), createFromPath: (): Record<string, never> => ({}) }

export class BrowserWindow {
  static getAllWindows(): BrowserWindow[] {
    return []
  }
  webContents = { send: noop, on: noop, executeJavaScript: (): Promise<undefined> => Promise.resolve(undefined) }
  on = noop
  loadURL = (): Promise<void> => Promise.resolve()
  show = noop
  hide = noop
  close = noop
  destroy = noop
  isDestroyed = (): boolean => false
  setBounds = noop
  getBounds = (): { x: number; y: number; width: number; height: number } => ({ x: 0, y: 0, width: 0, height: 0 })
}

export class Notification {
  static isSupported(): boolean {
    return false
  }
  on = noop
  show = noop
}

// Type-only exports referenced by main code; runtime values are never used.
export type WebContents = unknown
export type IpcMainInvokeEvent = unknown
export const webContents = { getAllWebContents: (): unknown[] => [] }

export default {
  app,
  globalShortcut,
  ipcMain,
  ipcRenderer,
  contextBridge,
  shell,
  dialog,
  screen,
  powerMonitor,
  safeStorage,
  session,
  net,
  desktopCapturer,
  nativeImage,
  BrowserWindow,
  Notification,
  webContents
}
