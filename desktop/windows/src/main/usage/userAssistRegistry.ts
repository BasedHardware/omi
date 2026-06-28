import koffi from 'koffi'

// Native read of the UserAssist Count values from HKCU. Thin and untested by
// design — all decoding/parsing lives in the pure userAssist.ts. Returns the raw
// (still ROT13-encoded) value names plus their binary blobs; never throws, and
// yields [] off-Windows or if advapi32 can't be reached.

const HKEY_CURRENT_USER = 0x80000001
const KEY_READ = 0x20019
const ERROR_SUCCESS = 0
const ERROR_MORE_DATA = 234
const ERROR_NO_MORE_ITEMS = 259

// The "executable" UserAssist key: the only one carrying real focus time (the
// sibling shortcut key {F4E57C4B...} records launches with zero focus time).
const COUNT_SUBKEY =
  'Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\UserAssist\\' +
  '{CEBFF5CD-ACE2-4F4F-9178-9926F41749EA}\\Count'

// Generous caps: value names (ROT13 paths/AUMIDs) and blobs are small; the
// largest known entry (UEME_CTLSESSION) is ~1.6 KB.
const MAX_NAME_CHARS = 16384
const INITIAL_DATA_BYTES = 8192

type RawEntry = { name: string; data: Buffer }

type Advapi = {
  RegOpenKeyExW: (h: number, sub: string, o: number, sam: number, out: [unknown]) => number
  RegEnumValueW: (
    h: unknown,
    i: number,
    name: Buffer,
    nameLen: [number],
    reserved: unknown,
    type: [number],
    data: Buffer,
    dataLen: [number]
  ) => number
  RegCloseKey: (h: unknown) => number
}
let advapi: Advapi | null = null
let loadFailed = false

function load(): Advapi | null {
  if (advapi) return advapi
  if (loadFailed) return null
  try {
    const lib = koffi.load('advapi32.dll')
    advapi = {
      // HKEY passed as an integer (predefined HKEY_CURRENT_USER); result HKEY is a
      // real pointer we thread into RegEnumValueW / RegCloseKey.
      RegOpenKeyExW: lib.func(
        'long __stdcall RegOpenKeyExW(size_t hKey, str16 lpSubKey, uint32 ulOptions, uint32 samDesired, _Out_ void **phkResult)'
      ),
      RegEnumValueW: lib.func(
        'long __stdcall RegEnumValueW(void *hKey, uint32 dwIndex, _Out_ uint16 *lpValueName, _Inout_ uint32 *lpcchValueName, void *lpReserved, _Out_ uint32 *lpType, _Out_ uint8 *lpData, _Inout_ uint32 *lpcbData)'
      ),
      RegCloseKey: lib.func('long __stdcall RegCloseKey(void *hKey)')
    }
    return advapi
  } catch (e) {
    console.warn('[usage] advapi32 unavailable; UserAssist seed skipped:', e)
    loadFailed = true
    return null
  }
}

// Read every Count value. Returns raw ROT13 names + blobs. Never throws.
export function readUserAssistRaw(): RawEntry[] {
  if (process.platform !== 'win32') return []
  const api = load()
  if (!api) return []
  const hkeyBox: [unknown] = [null]
  if (api.RegOpenKeyExW(HKEY_CURRENT_USER, COUNT_SUBKEY, 0, KEY_READ, hkeyBox) !== ERROR_SUCCESS) {
    return []
  }
  const hkey = hkeyBox[0]
  const out: RawEntry[] = []
  try {
    const nameBuf = Buffer.alloc(MAX_NAME_CHARS * 2)
    let dataBuf = Buffer.alloc(INITIAL_DATA_BYTES)
    for (let i = 0; i < 100000; i++) {
      // Reset the in/out sizes to the current buffer capacities each iteration.
      const nameLen: [number] = [MAX_NAME_CHARS]
      const dataLen: [number] = [dataBuf.length]
      const type: [number] = [0]
      let rc = api.RegEnumValueW(hkey, i, nameBuf, nameLen, null, type, dataBuf, dataLen)
      if (rc === ERROR_MORE_DATA) {
        // Blob bigger than our buffer — grow and retry this same index.
        dataBuf = Buffer.alloc(Math.max(dataBuf.length * 2, dataLen[0] || dataBuf.length * 2))
        nameLen[0] = MAX_NAME_CHARS
        dataLen[0] = dataBuf.length
        type[0] = 0
        rc = api.RegEnumValueW(hkey, i, nameBuf, nameLen, null, type, dataBuf, dataLen)
      }
      if (rc === ERROR_NO_MORE_ITEMS) break
      if (rc !== ERROR_SUCCESS) break
      const name = nameBuf.toString('utf16le', 0, nameLen[0] * 2)
      out.push({ name, data: Buffer.from(dataBuf.subarray(0, dataLen[0])) })
    }
  } catch (e) {
    console.warn('[usage] RegEnumValue loop failed:', e)
  } finally {
    try {
      api.RegCloseKey(hkey)
    } catch {
      // ignore
    }
  }
  return out
}
