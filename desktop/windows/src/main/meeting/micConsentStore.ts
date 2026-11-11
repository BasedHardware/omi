// Tier 2 — "which apps are capturing the microphone RIGHT NOW", read from the
// Windows CapabilityAccessManager ConsentStore:
//   HKCU\Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\
//     ConsentStore\microphone            → packaged (Store) apps as subkeys
//     ConsentStore\microphone\NonPackaged → win32 apps, key = path with '\'→'#'
// An app whose REG_QWORD LastUsedTimeStop == 0 (with a nonzero
// LastUsedTimeStart) is capturing at this moment.
//
// Pure advapi32/kernel32 via koffi, same lazy-load + never-throw pattern as
// usage/nativeForeground.ts. Change detection is EVENT-DRIVEN, not polled:
// RegNotifyChangeKeyValue(REG_NOTIFY_CHANGE_LAST_SET|NAME, watch-subtree) with
// an auto-reset event, awaited via koffi's async FFI (worker thread) — the
// notification is one-shot, so it is re-armed after every signal. stop() sets a
// flag and SetEvent()s the same event to unblock the waiter.
//
// (The WASAPI IAudioSessionManager2 C# helper is the documented fallback if the
// registry signal ever proves imprecise — deliberately not built.)
import koffi from 'koffi'

const HKEY_CURRENT_USER = 0x80000001
const KEY_READ = 0x20019
const KEY_NOTIFY = 0x0010
const ERROR_SUCCESS = 0
const ERROR_NO_MORE_ITEMS = 259
const REG_NOTIFY_CHANGE_NAME = 0x1
const REG_NOTIFY_CHANGE_LAST_SET = 0x4
const INFINITE = 0xffffffff
const WAIT_OBJECT_0 = 0

const MIC_KEY =
  'Software\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\microphone'

export type MicCaptureEntry = {
  /** Correlation id for Tier 1 agreement: lowercase exe basename for win32
   *  apps, lowercase package key for Store apps. */
  id: string
  /** Decoded full exe path (win32 apps only). */
  path: string | null
  packaged: boolean
}

export type MicConsentWatcher = {
  stop: () => void
}

type Native = {
  readEntries: (excludeExePath: string | null) => MicCaptureEntry[]
  watch: (onChange: () => void) => MicConsentWatcher | null
}

let cached: Native | null = null
let loadFailed = false

function load(): Native | null {
  if (cached) return cached
  if (loadFailed) return null
  try {
    const advapi32 = koffi.load('advapi32.dll')
    const kernel32 = koffi.load('kernel32.dll')

    const RegOpenKeyExW = advapi32.func(
      'long RegOpenKeyExW(intptr hKey, const char16_t* lpSubKey, uint32 ulOptions, uint32 samDesired, _Out_ intptr* phkResult)'
    )
    const RegEnumKeyExW = advapi32.func(
      'long RegEnumKeyExW(intptr hKey, uint32 dwIndex, _Out_ uint16* lpName, _Inout_ uint32* lpcchName, void* lpReserved, void* lpClass, void* lpcchClass, void* lpftLastWriteTime)'
    )
    const RegQueryValueExW = advapi32.func(
      'long RegQueryValueExW(intptr hKey, const char16_t* lpValueName, void* lpReserved, _Out_ uint32* lpType, _Out_ uint8* lpData, _Inout_ uint32* lpcbData)'
    )
    const RegCloseKey = advapi32.func('long RegCloseKey(intptr hKey)')
    const RegNotifyChangeKeyValue = advapi32.func(
      'long RegNotifyChangeKeyValue(intptr hKey, bool bWatchSubtree, uint32 dwNotifyFilter, intptr hEvent, bool fAsynchronous)'
    )
    const CreateEventW = kernel32.func(
      'intptr CreateEventW(void* lpEventAttributes, bool bManualReset, bool bInitialState, void* lpName)'
    )
    const WaitForSingleObject = kernel32.func(
      'uint32 WaitForSingleObject(intptr hHandle, uint32 dwMilliseconds)'
    )
    const SetEvent = kernel32.func('bool SetEvent(intptr hEvent)')
    const CloseHandle = kernel32.func('bool CloseHandle(intptr hObject)')

    const openKey = (parent: number, subKey: string | null, sam: number): number | null => {
      const box: [number] = [0]
      const rc = RegOpenKeyExW(parent, subKey, 0, sam, box)
      return rc === ERROR_SUCCESS && box[0] ? box[0] : null
    }

    const enumSubkeys = (hKey: number): string[] => {
      const names: string[] = []
      const buf = Buffer.alloc(1024) // 512 UTF-16 chars — registry key names max 255
      for (let i = 0; ; i++) {
        const cch: [number] = [512]
        const rc = RegEnumKeyExW(hKey, i, buf, cch, null, null, null, null)
        if (rc === ERROR_NO_MORE_ITEMS) break
        if (rc !== ERROR_SUCCESS) break
        names.push(buf.toString('utf16le', 0, cch[0] * 2))
      }
      return names
    }

    /** Read a REG_QWORD value; null when absent or not 8 bytes. */
    const queryQword = (hKey: number, name: string): bigint | null => {
      const data = Buffer.alloc(8)
      const type: [number] = [0]
      const cb: [number] = [8]
      const rc = RegQueryValueExW(hKey, name, null, type, data, cb)
      if (rc !== ERROR_SUCCESS || cb[0] !== 8) return null
      return data.readBigUInt64LE(0)
    }

    /** True when this leaf key says "capturing right now". */
    const isActiveLeaf = (hLeaf: number): boolean => {
      const stop = queryQword(hLeaf, 'LastUsedTimeStop')
      if (stop === null || stop !== 0n) return false
      const start = queryQword(hLeaf, 'LastUsedTimeStart')
      return start !== null && start !== 0n
    }

    const readEntries = (excludeExePath: string | null): MicCaptureEntry[] => {
      const out: MicCaptureEntry[] = []
      const root = openKey(HKEY_CURRENT_USER, MIC_KEY, KEY_READ)
      if (!root) return out
      try {
        const excluded = excludeExePath?.toLowerCase() ?? null
        for (const name of enumSubkeys(root)) {
          if (name === 'NonPackaged') {
            const np = openKey(root, name, KEY_READ)
            if (!np) continue
            try {
              for (const appKey of enumSubkeys(np)) {
                const leaf = openKey(np, appKey, KEY_READ)
                if (!leaf) continue
                try {
                  if (!isActiveLeaf(leaf)) continue
                  const path = appKey.replace(/#/g, '\\')
                  if (excluded && path.toLowerCase() === excluded) continue // Omi itself
                  const base = path.slice(path.lastIndexOf('\\') + 1).toLowerCase()
                  out.push({ id: base, path, packaged: false })
                } finally {
                  RegCloseKey(leaf)
                }
              }
            } finally {
              RegCloseKey(np)
            }
          } else {
            const leaf = openKey(root, name, KEY_READ)
            if (!leaf) continue
            try {
              if (isActiveLeaf(leaf)) out.push({ id: name.toLowerCase(), path: null, packaged: true })
            } finally {
              RegCloseKey(leaf)
            }
          }
        }
      } finally {
        RegCloseKey(root)
      }
      return out
    }

    const watch = (onChange: () => void): MicConsentWatcher | null => {
      const hKey = openKey(HKEY_CURRENT_USER, MIC_KEY, KEY_READ | KEY_NOTIFY)
      if (!hKey) return null
      const hEvent = CreateEventW(null, false, false, null) // auto-reset
      if (!hEvent) {
        RegCloseKey(hKey)
        return null
      }
      let stopped = false

      const cleanup = (): void => {
        try {
          RegCloseKey(hKey)
        } catch {
          /* ignore */
        }
        try {
          CloseHandle(hEvent)
        } catch {
          /* ignore */
        }
      }

      // One-shot notification: must be re-armed after every signal.
      const arm = (): boolean => {
        const rc = RegNotifyChangeKeyValue(
          hKey,
          true, // watch the whole subtree (NonPackaged + packaged leaves)
          REG_NOTIFY_CHANGE_NAME | REG_NOTIFY_CHANGE_LAST_SET,
          hEvent,
          true // asynchronous — signal the event, don't block
        )
        return rc === ERROR_SUCCESS
      }

      const waitLoop = (): void => {
        // koffi .async runs the blocking wait on a worker thread; the JS
        // callback fires on the main loop when the event signals. Zero CPU
        // while idle — this is the no-polling requirement.
        WaitForSingleObject.async(hEvent, INFINITE, (err: unknown, res: number) => {
          if (stopped) {
            cleanup()
            return
          }
          if (err || res !== WAIT_OBJECT_0) {
            console.warn('[meeting] ConsentStore wait failed; watcher stopped:', err ?? res)
            cleanup()
            return
          }
          try {
            onChange()
          } catch (e) {
            console.warn('[meeting] ConsentStore onChange threw:', e)
          }
          if (!arm()) {
            console.warn('[meeting] ConsentStore re-arm failed; watcher stopped')
            cleanup()
            return
          }
          waitLoop()
        })
      }

      if (!arm()) {
        cleanup()
        return null
      }
      waitLoop()

      return {
        stop: (): void => {
          if (stopped) return
          stopped = true
          try {
            SetEvent(hEvent) // wake the waiter; it sees `stopped` and cleans up
          } catch {
            /* ignore */
          }
        }
      }
    }

    cached = { readEntries, watch }
    return cached
  } catch (e) {
    console.warn('[meeting] koffi/advapi32 ConsentStore unavailable:', e)
    loadFailed = true
    return null
  }
}

/** Apps capturing the microphone right now (Omi's own exe excluded). Never
 *  throws; [] when unavailable. */
export function readMicCaptureEntries(): MicCaptureEntry[] {
  if (process.platform !== 'win32') return []
  try {
    return load()?.readEntries(process.execPath) ?? []
  } catch (e) {
    console.warn('[meeting] ConsentStore read failed:', e)
    return []
  }
}

/** Watch the ConsentStore for changes (event-driven; no polling). Returns null
 *  when unavailable — the caller then relies on its other triggers. Never throws. */
export function watchMicConsentStore(onChange: () => void): MicConsentWatcher | null {
  if (process.platform !== 'win32') return null
  try {
    return load()?.watch(onChange) ?? null
  } catch (e) {
    console.warn('[meeting] ConsentStore watch failed:', e)
    return null
  }
}
