import {
  linuxAvailable,
  getLinuxForegroundExePath,
  getLinuxForegroundInfo,
  getLinuxForegroundTitle
} from './linuxForeground'

// PROCESS_QUERY_LIMITED_INFORMATION — enough to read the image path, and works
// for processes at higher integrity than ours (unlike QUERY_INFORMATION).
const PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

// Foreground-window-changed accessibility event + flags for an out-of-context
// (callback-on-our-thread) hook. OBJID_WINDOW filters out caret/menu/child noise.
const EVENT_SYSTEM_FOREGROUND = 0x0003
const WINEVENT_OUTOFCONTEXT = 0x0000
const OBJID_WINDOW = 0

// DWMWA_EXTENDED_FRAME_BOUNDS. GetWindowRect returns the frame INCLUDING the
// invisible resize border Win10/11 keeps around every window (~8px/side), and for
// a MAXIMIZED window that frame deliberately hangs off-screen. EFB returns the
// visually correct frame — the rect a human sees. Anything that draws relative to
// a window's edges must use this, never GetWindowRect. Size of a RECT = 16 bytes.
const DWMWA_EXTENDED_FRAME_BOUNDS = 9
// DWMWA_CLOAKED. A cloaked window is composited-away by DWM while still enumerable
// with a valid frame: a suspended UWP app's ApplicationFrameWindow, a window on
// another virtual desktop, or one mid-animation. IsWindowVisible() (the WS_VISIBLE
// style bit) reports TRUE for such a window even though NOTHING is painted where
// its bounds say it is — so anything drawing around a window's edges must also
// reject cloaked windows or it rings empty desktop. Returns a non-zero DWORD when
// cloaked (the specific bit says by whom; any non-zero value means invisible).
const DWMWA_CLOAKED = 14
const SIZEOF_RECT = 16
const SIZEOF_DWORD = 4
const S_OK = 0

export type ForegroundWindowInfo = {
  handle: string | null
  exePath: string | null
  // Win32 window class — lets callers distinguish a real app window from a bare
  // shell surface (desktop/taskbar/Start), which share explorer.exe.
  className: string | null
}

/** Screen rect in PHYSICAL pixels (Win32 coordinates, not DIPs). */
export type ForegroundRect = { x: number; y: number; width: number; height: number }

/**
 * The foreground window sampled atomically in ONE GetForegroundWindow() call:
 * its DWM extended frame bounds (the visually correct frame, physical px) plus
 * the state flags a drawing consumer needs to decide whether to draw at all.
 * `rect` is null when the window has no readable frame (EFB failed AND
 * GetWindowRect failed).
 */
export type ForegroundFrame = {
  handle: string | null
  rect: ForegroundRect | null
  className: string | null
  exePath: string | null
  maximized: boolean
  minimized: boolean
  visible: boolean
  // DWM-cloaked (composited away though WS_VISIBLE) — see DWMWA_CLOAKED. A drawing
  // consumer must treat this as "do not frame": the window paints nothing on screen.
  cloaked: boolean
  // Owning process id, so a caller can recognise its OWN windows (an Electron app's
  // BrowserWindows are all owned by the main/browser process) and never frame them.
  pid: number | null
}

const NO_FRAME: ForegroundFrame = {
  handle: null,
  rect: null,
  className: null,
  exePath: null,
  maximized: false,
  minimized: false,
  visible: false,
  cloaked: false,
  pid: null
}

type Win32 = {
  getForegroundExePath: () => string | null
  // Foreground window's HWND (as a decimal string the C# helper can parse) plus
  // its owning exe path, read from a single GetForegroundWindow() call.
  getForegroundWindowInfo: () => ForegroundWindowInfo
  // Foreground window's title text (GetWindowTextW). Lets Rewind detect
  // login/private-browsing screens without the C# helper running.
  getForegroundWindowTitle: () => string | null
  // Foreground window's screen rect (physical px) + class + exe, read in one
  // GetForegroundWindow() call — the bar's fullscreen-suppression signal.
  getForegroundWindowRect: () => {
    rect: ForegroundRect | null
    className: string | null
    exePath: string | null
  }
  // Foreground window's DWM extended frame bounds + state flags — the geometry
  // source for anything drawn around a window (the focus halo).
  getForegroundWindowFrame: () => ForegroundFrame
  // Fire `cb` whenever the foreground window changes. Returns an unsubscribe.
  subscribeForegroundChange: (cb: () => void) => () => void
}

let cached: Win32 | null = null
let loadFailed = false

function load(): Win32 | null {
  if (cached) return cached
  if (loadFailed) return null
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const koffi = require('koffi') as typeof import('koffi')
    const user32 = koffi.load('user32.dll')
    const kernel32 = koffi.load('kernel32.dll')

    const GetForegroundWindow = user32.func('void* GetForegroundWindow()')
    const GetWindowThreadProcessId = user32.func(
      'uint32 GetWindowThreadProcessId(void* hWnd, _Out_ uint32* lpdwProcessId)'
    )
    const OpenProcess = kernel32.func(
      'void* OpenProcess(uint32 dwDesiredAccess, bool bInheritHandle, uint32 dwProcessId)'
    )
    const QueryFullProcessImageNameW = kernel32.func(
      'bool QueryFullProcessImageNameW(void* hProcess, uint32 dwFlags, _Out_ uint16* lpExeName, _Inout_ uint32* lpdwSize)'
    )
    const CloseHandle = kernel32.func('bool CloseHandle(void* hObject)')
    const GetClassNameW = user32.func(
      'int32 GetClassNameW(void* hWnd, _Out_ uint16* lpClassName, int32 nMaxCount)'
    )
    const GetWindowTextW = user32.func(
      'int32 GetWindowTextW(void* hWnd, _Out_ uint16* lpString, int32 nMaxCount)'
    )
    const RECT = koffi.struct('OMI_RECT', {
      left: 'int32',
      top: 'int32',
      right: 'int32',
      bottom: 'int32'
    })
    const GetWindowRect = user32.func('bool GetWindowRect(void* hWnd, _Out_ OMI_RECT* lpRect)')
    const IsZoomed = user32.func('bool IsZoomed(void* hWnd)')
    const IsIconic = user32.func('bool IsIconic(void* hWnd)')
    const IsWindowVisible = user32.func('bool IsWindowVisible(void* hWnd)')
    void RECT

    // dwmapi is loaded lazily-but-eagerly here alongside user32; if it is
    // unavailable the frame reader falls back to GetWindowRect (and the halo's
    // maximized gate then rejects, which is the safe direction).
    let DwmGetWindowAttribute: ((...args: unknown[]) => number) | null = null
    // Same export, DWORD-out overload — koffi types a func by its C signature, so
    // the RECT and DWORD attribute reads need distinct declarations.
    let DwmGetWindowAttributeDword: ((...args: unknown[]) => number) | null = null
    try {
      const dwmapi = koffi.load('dwmapi.dll')
      DwmGetWindowAttribute = dwmapi.func(
        'int32 DwmGetWindowAttribute(void* hwnd, uint32 dwAttribute, _Out_ OMI_RECT* pvAttribute, uint32 cbAttribute)'
      ) as (...args: unknown[]) => number
      // Same symbol, DWORD-out overload. koffi binds a signature, not just a
      // symbol, so the RECT-out and DWORD-out reads are two distinct declarations;
      // the variadic (symbol, result, params) form gives the second one without
      // re-parsing a C prototype.
      DwmGetWindowAttributeDword = dwmapi.func('DwmGetWindowAttribute', 'int32', [
        'void*',
        'uint32',
        koffi.out(koffi.pointer('uint32')),
        'uint32'
      ]) as (...args: unknown[]) => number
    } catch (e) {
      console.warn('[usage] dwmapi unavailable; falling back to GetWindowRect:', e)
    }

    const rectFrom = (out: {
      left?: number
      top?: number
      right?: number
      bottom?: number
    }): ForegroundRect | null => {
      if (typeof out.left !== 'number' || typeof out.top !== 'number') return null
      if (typeof out.right !== 'number' || typeof out.bottom !== 'number') return null
      return {
        x: out.left,
        y: out.top,
        width: out.right - out.left,
        height: out.bottom - out.top
      }
    }

    // The window's VISUALLY correct frame (physical px). EFB first; GetWindowRect
    // only as a last resort (it includes the invisible resize border — callers
    // that need exact edges must treat that fallback as untrustworthy).
    const frameRectFromHwnd = (hwnd: unknown): ForegroundRect | null => {
      if (DwmGetWindowAttribute) {
        try {
          const out: { left?: number; top?: number; right?: number; bottom?: number } = {}
          const hr = DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, out, SIZEOF_RECT)
          if (hr === S_OK) {
            const r = rectFrom(out)
            if (r) return r
          }
        } catch {
          // fall through to GetWindowRect
        }
      }
      try {
        const out: { left?: number; top?: number; right?: number; bottom?: number } = {}
        if (GetWindowRect(hwnd, out)) return rectFrom(out)
      } catch {
        return null
      }
      return null
    }

    // Is the window composited-away by DWM (DWMWA_CLOAKED != 0)? A cloaked window
    // has WS_VISIBLE set yet paints nothing on screen (suspended UWP host, another
    // virtual desktop, mid-animation). Unreadable (no dwmapi) ⇒ false: absent the
    // signal, fall back to the other visibility gates rather than over-suppress.
    const cloakedFromHwnd = (hwnd: unknown): boolean => {
      if (!DwmGetWindowAttributeDword) return false
      try {
        const box: [number] = [0]
        const hr = DwmGetWindowAttributeDword(hwnd, DWMWA_CLOAKED, box, SIZEOF_DWORD)
        return hr === S_OK && box[0] !== 0
      } catch {
        return false
      }
    }

    // The window's owning process id, or null on any permission edge. A throw
    // degrades to pid=null (halo still allowed) rather than suppressing the halo —
    // symmetric with cloakedFromHwnd's fail-open.
    const pidFromHwnd = (hwnd: unknown): number | null => {
      try {
        const pidBox: [number] = [0]
        GetWindowThreadProcessId(hwnd, pidBox)
        return pidBox[0] || null
      } catch {
        return null
      }
    }

    // Read an HWND's title text. Returns null on any edge. Titles can be long
    // (browser tabs include the page name), so allow 512 UTF-16 chars.
    const titleFromHwnd = (hwnd: unknown): string | null => {
      const buf = Buffer.alloc(1024)
      const n = GetWindowTextW(hwnd, buf, 512)
      if (!n || n <= 0) return null
      return buf.toString('utf16le', 0, n * 2)
    }

    // Read an HWND's Win32 window class (e.g. "Shell_TrayWnd", "CabinetWClass").
    // Returns null on any edge. Class names are capped at 256 chars by Windows.
    const classNameFromHwnd = (hwnd: unknown): string | null => {
      const buf = Buffer.alloc(512) // 256 UTF-16 chars
      const n = GetClassNameW(hwnd, buf, 256)
      if (!n || n <= 0) return null
      return buf.toString('utf16le', 0, n * 2)
    }

    // Resolve an HWND to its owning process's image path. Shared by the
    // exe-path and window-info readers. Returns null on any permission edge.
    const exePathFromHwnd = (hwnd: unknown): string | null => {
      const pidBox: [number] = [0]
      GetWindowThreadProcessId(hwnd, pidBox)
      const pid = pidBox[0]
      if (!pid) return null
      const handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, pid)
      if (!handle) return null
      try {
        const buf = Buffer.alloc(520) // 260 UTF-16 chars
        const sizeBox: [number] = [260]
        const ok = QueryFullProcessImageNameW(handle, 0, buf, sizeBox)
        if (!ok || sizeBox[0] <= 0) return null
        return buf.toString('utf16le', 0, sizeBox[0] * 2)
      } finally {
        CloseHandle(handle)
      }
    }

    // WINEVENTPROC callback prototype (CALLBACK == __stdcall; ignored on x64 but
    // correct on x86). Registered per-subscription via koffi.register.
    const WinEventProc = koffi.proto(
      'void __stdcall WinEventProc(void* hHook, uint32 event, void* hwnd, int32 idObject, int32 idChild, uint32 idThread, uint32 dwmsEventTime)'
    )
    const SetWinEventHook = user32.func(
      'void* SetWinEventHook(uint32 eventMin, uint32 eventMax, void* hmodWinEventProc, void* lpfnWinEventProc, uint32 idProcess, uint32 idThread, uint32 dwFlags)'
    )
    const UnhookWinEvent = user32.func('bool UnhookWinEvent(void* hWinEventHook)')

    cached = {
      subscribeForegroundChange(cb: () => void): () => void {
        let hook: unknown = null
        let registered: bigint | null = null
        try {
          const onEvent = (
            _hHook: unknown,
            _event: number,
            _hwnd: unknown,
            idObject: number,
            idChild: number
          ): void => {
            // Only top-level window foreground changes — skip caret/menu/child objects.
            if (idObject !== OBJID_WINDOW || idChild !== 0) return
            try {
              cb()
            } catch {
              // Never let a JS callback throw back into the native dispatcher.
            }
          }
          registered = koffi.register(onEvent, koffi.pointer(WinEventProc))
          hook = SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND,
            EVENT_SYSTEM_FOREGROUND,
            null,
            registered,
            0,
            0,
            WINEVENT_OUTOFCONTEXT
          )
        } catch (e) {
          console.warn('[usage] SetWinEventHook failed; relying on poll only:', e)
        }
        return () => {
          try {
            if (hook) UnhookWinEvent(hook)
          } catch {
            // ignore
          }
          try {
            if (registered) koffi.unregister(registered)
          } catch {
            // ignore
          }
          hook = null
          registered = null
        }
      },
      getForegroundExePath(): string | null {
        const hwnd = GetForegroundWindow()
        if (!hwnd) return null
        return exePathFromHwnd(hwnd)
      },
      getForegroundWindowInfo(): ForegroundWindowInfo {
        const hwnd = GetForegroundWindow()
        if (!hwnd) return { handle: null, exePath: null, className: null }
        let handle: string | null = null
        try {
          // koffi.address gives the pointer's numeric address; the C# helper
          // parses windowHandle as a decimal long.
          handle = koffi.address(hwnd).toString()
        } catch {
          handle = null
        }
        return { handle, exePath: exePathFromHwnd(hwnd), className: classNameFromHwnd(hwnd) }
      },
      getForegroundWindowTitle(): string | null {
        const hwnd = GetForegroundWindow()
        if (!hwnd) return null
        return titleFromHwnd(hwnd)
      },
      getForegroundWindowRect() {
        const hwnd = GetForegroundWindow()
        if (!hwnd) return { rect: null, className: null, exePath: null }
        let rect: ForegroundRect | null = null
        try {
          const out: { left?: number; top?: number; right?: number; bottom?: number } = {}
          if (GetWindowRect(hwnd, out) && typeof out.left === 'number') {
            rect = {
              x: out.left,
              y: out.top!,
              width: out.right! - out.left,
              height: out.bottom! - out.top!
            }
          }
        } catch {
          rect = null
        }
        return { rect, className: classNameFromHwnd(hwnd), exePath: exePathFromHwnd(hwnd) }
      },
      getForegroundWindowFrame(): ForegroundFrame {
        const hwnd = GetForegroundWindow()
        if (!hwnd) return NO_FRAME
        let handle: string | null = null
        try {
          handle = koffi.address(hwnd).toString()
        } catch {
          handle = null
        }
        return {
          handle,
          rect: frameRectFromHwnd(hwnd),
          className: classNameFromHwnd(hwnd),
          exePath: exePathFromHwnd(hwnd),
          maximized: !!IsZoomed(hwnd),
          minimized: !!IsIconic(hwnd),
          visible: !!IsWindowVisible(hwnd),
          cloaked: cloakedFromHwnd(hwnd),
          pid: pidFromHwnd(hwnd)
        }
      }
    }
    return cached
  } catch (e) {
    console.warn('[usage] koffi/user32 unavailable, foreground monitor disabled:', e)
    loadFailed = true
    return null
  }
}

// Returns the absolute exe path of the current foreground window, or null when
// unavailable (no foreground window, permission edge, or koffi failed to load).
// Never throws.
export function getForegroundExePath(): string | null {
  if (process.platform === 'linux') {
    return linuxAvailable() ? getLinuxForegroundExePath() : null
  }
  if (process.platform !== 'win32') return null
  try {
    return load()?.getForegroundExePath() ?? null
  } catch (e) {
    console.warn('[usage] getForegroundExePath failed:', e)
    return null
  }
}

// Returns the current foreground window's HWND (decimal string) + owning exe
// path, or nulls when unavailable. Never throws.
export function getForegroundWindowInfo(): ForegroundWindowInfo {
  if (process.platform === 'linux') {
    return linuxAvailable()
      ? getLinuxForegroundInfo()
      : { handle: null, exePath: null, className: null }
  }
  if (process.platform !== 'win32') return { handle: null, exePath: null, className: null }
  try {
    return load()?.getForegroundWindowInfo() ?? { handle: null, exePath: null, className: null }
  } catch (e) {
    console.warn('[usage] getForegroundWindowInfo failed:', e)
    return { handle: null, exePath: null, className: null }
  }
}

// Returns the current foreground window's title text, or null when unavailable.
// Never throws.
export function getForegroundWindowTitle(): string | null {
  if (process.platform === 'linux') {
    return linuxAvailable() ? getLinuxForegroundTitle() : null
  }
  if (process.platform !== 'win32') return null
  try {
    return load()?.getForegroundWindowTitle() ?? null
  } catch (e) {
    console.warn('[usage] getForegroundWindowTitle failed:', e)
    return null
  }
}

// Returns the current foreground window's rect (physical px) + class + exe, or
// nulls when unavailable. Never throws.
export function getForegroundWindowRect(): {
  rect: ForegroundRect | null
  className: string | null
  exePath: string | null
} {
  if (process.platform !== 'win32') return { rect: null, className: null, exePath: null }
  try {
    return load()?.getForegroundWindowRect() ?? { rect: null, className: null, exePath: null }
  } catch (e) {
    console.warn('[usage] getForegroundWindowRect failed:', e)
    return { rect: null, className: null, exePath: null }
  }
}

// Returns the current foreground window's DWM extended frame bounds (physical px)
// + class/exe + maximized/minimized/visible flags, sampled in one
// GetForegroundWindow() call. All-null/false when unavailable. Never throws.
//
// Use this — NOT getForegroundWindowRect — for anything drawn around the window's
// edges: GetWindowRect's rect includes the invisible resize border and hangs
// off-screen when maximized (that bug shipped once already: three of four glow
// bands landed off-screen and the fourth read as a stray bar).
export function getForegroundWindowFrame(): ForegroundFrame {
  if (process.platform !== 'win32') return NO_FRAME
  try {
    return load()?.getForegroundWindowFrame() ?? NO_FRAME
  } catch (e) {
    console.warn('[usage] getForegroundWindowFrame failed:', e)
    return NO_FRAME
  }
}

// Subscribe to foreground-window changes (event-driven, like macOS's NSWorkspace
// activation notification). Returns an unsubscribe. A no-op unsubscribe when
// unavailable (off-Windows, koffi failed, or the hook couldn't be installed) —
// in that case the caller's poll loop remains the sole signal. Never throws.
export function subscribeForegroundChange(cb: () => void): () => void {
  if (process.platform !== 'win32') return () => {}
  try {
    return load()?.subscribeForegroundChange(cb) ?? (() => {})
  } catch (e) {
    console.warn('[usage] subscribeForegroundChange failed:', e)
    return () => {}
  }
}
