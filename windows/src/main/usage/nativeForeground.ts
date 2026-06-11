import koffi from 'koffi'

// PROCESS_QUERY_LIMITED_INFORMATION — enough to read the image path, and works
// for processes at higher integrity than ours (unlike QUERY_INFORMATION).
const PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

// Foreground-window-changed accessibility event + flags for an out-of-context
// (callback-on-our-thread) hook. OBJID_WINDOW filters out caret/menu/child noise.
const EVENT_SYSTEM_FOREGROUND = 0x0003
const WINEVENT_OUTOFCONTEXT = 0x0000
const OBJID_WINDOW = 0

export type ForegroundWindowInfo = {
  handle: string | null
  exePath: string | null
  // Win32 window class — lets callers distinguish a real app window from a bare
  // shell surface (desktop/taskbar/Start), which share explorer.exe.
  className: string | null
}

type Win32 = {
  getForegroundExePath: () => string | null
  // Foreground window's HWND (as a decimal string the C# helper can parse) plus
  // its owning exe path, read from a single GetForegroundWindow() call.
  getForegroundWindowInfo: () => ForegroundWindowInfo
  // Foreground window's title text (GetWindowTextW). Lets Rewind detect
  // login/private-browsing screens without the C# helper running.
  getForegroundWindowTitle: () => string | null
  // Fire `cb` whenever the foreground window changes. Returns an unsubscribe.
  subscribeForegroundChange: (cb: () => void) => () => void
}

let cached: Win32 | null = null
let loadFailed = false

function load(): Win32 | null {
  if (cached) return cached
  if (loadFailed) return null
  try {
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
  if (process.platform !== 'win32') return null
  try {
    return load()?.getForegroundWindowTitle() ?? null
  } catch (e) {
    console.warn('[usage] getForegroundWindowTitle failed:', e)
    return null
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
