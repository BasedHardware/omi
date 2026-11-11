// Full process snapshot via CreateToolhelp32Snapshot (koffi/kernel32), following
// the lazy-load + never-throw pattern of usage/nativeForeground.ts. Returns
// lowercase image names ('zoom.exe') for Tier 1 matching.
import koffi from 'koffi'

const TH32CS_SNAPPROCESS = 0x00000002
const INVALID_HANDLE_VALUE = -1

type Native = {
  listProcessNames: () => string[]
}

let cached: Native | null = null
let loadFailed = false

function load(): Native | null {
  if (cached) return cached
  if (loadFailed) return null
  try {
    const kernel32 = koffi.load('kernel32.dll')

    // szExeFile is the image NAME only (not a path) — exactly what Tier 1 wants.
    const PROCESSENTRY32W = koffi.struct('OMI_PROCESSENTRY32W', {
      dwSize: 'uint32',
      cntUsage: 'uint32',
      th32ProcessID: 'uint32',
      th32DefaultHeapID: 'size_t',
      th32ModuleID: 'uint32',
      cntThreads: 'uint32',
      th32ParentProcessID: 'uint32',
      pcPriClassBase: 'int32',
      dwFlags: 'uint32',
      szExeFile: koffi.array('char16', 260, 'String')
    })

    const CreateToolhelp32Snapshot = kernel32.func(
      'intptr CreateToolhelp32Snapshot(uint32 dwFlags, uint32 th32ProcessID)'
    )
    const Process32FirstW = kernel32.func(
      'bool Process32FirstW(intptr hSnapshot, _Inout_ OMI_PROCESSENTRY32W* lppe)'
    )
    const Process32NextW = kernel32.func(
      'bool Process32NextW(intptr hSnapshot, _Inout_ OMI_PROCESSENTRY32W* lppe)'
    )
    const CloseHandle = kernel32.func('bool CloseHandle(intptr hObject)')

    const entrySize = koffi.sizeof(PROCESSENTRY32W)

    cached = {
      listProcessNames(): string[] {
        const snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if (!snap || snap === INVALID_HANDLE_VALUE) return []
        const names: string[] = []
        try {
          const entry: Record<string, unknown> = { dwSize: entrySize }
          if (!Process32FirstW(snap, entry)) return names
          do {
            const exe = entry.szExeFile
            if (typeof exe === 'string' && exe) names.push(exe.toLowerCase())
          } while (Process32NextW(snap, entry))
        } finally {
          CloseHandle(snap)
        }
        return names
      }
    }
    return cached
  } catch (e) {
    console.warn('[meeting] koffi/kernel32 snapshot unavailable:', e)
    loadFailed = true
    return null
  }
}

/** Lowercase image names of every running process, or [] when unavailable.
 *  Never throws. */
export function listProcessNames(): string[] {
  if (process.platform !== 'win32') return []
  try {
    return load()?.listProcessNames() ?? []
  } catch (e) {
    console.warn('[meeting] process snapshot failed:', e)
    return []
  }
}
