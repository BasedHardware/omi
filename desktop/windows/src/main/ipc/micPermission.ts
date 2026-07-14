import { ipcMain } from 'electron'
import { execFile } from 'child_process'
import type { MicPermissionState } from '../../shared/types'

// The REAL Windows microphone permission, read from the Capability Access Manager
// consent store.
//
// Why this exists: Chromium's permission layer knows nothing about the Windows
// per-app microphone privacy toggle. `navigator.permissions.query({name:'microphone'})`
// returns 'granted' unconditionally in Electron (no `setPermissionCheckHandler` is
// registered, so the default `GetPermissionStatus` answers yes) — even on a brand-new
// profile with the mic actively blocked by Windows. Onboarding used that as truth and
// therefore FALSE-GRANTED the mic step on every run. The registry is the only honest
// source, so the mic step reads it over IPC instead.
//
// Two keys matter, and BOTH gate a desktop app:
//   …\ConsentStore\microphone              `Value` — the user's master mic toggle
//   …\ConsentStore\microphone\NonPackaged  `Value` — "let desktop apps access your mic"
// A missing key/value means the user has never been asked. We report that as 'unknown'
// and the UI treats it as NOT granted: never claim a grant we cannot see.
const CONSENT_ROOT =
  'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\microphone'

/** Pull the `Value` string out of `reg.exe query … /v Value` output. Null when the
 *  key or the value is absent (reg.exe exits non-zero, or prints no matching row). */
export function parseConsentValue(regOutput: string): string | null {
  const m = /^\s*Value\s+REG_SZ\s+(\S+)\s*$/m.exec(regOutput)
  return m ? m[1] : null
}

/** Fold the two consent values into a permission state. Granted requires an explicit
 *  Allow on the master toggle; an explicit Deny on EITHER key is a denial; anything
 *  else (never set, unreadable) is 'unknown' — which the UI treats as not granted. */
export function resolveMicState(
  root: string | null,
  nonPackaged: string | null
): MicPermissionState {
  if (root === 'Deny' || nonPackaged === 'Deny') return 'denied'
  // NonPackaged is absent on machines where the desktop-app toggle was never touched;
  // the master Allow still governs, so absent-but-not-Deny does not block a grant.
  if (root === 'Allow') return 'granted'
  return 'unknown'
}

function regQueryValue(key: string): Promise<string | null> {
  return new Promise((resolve) => {
    execFile('reg.exe', ['query', key, '/v', 'Value'], { windowsHide: true }, (err, stdout) => {
      // A missing key exits non-zero — that is "never set", not a crash.
      resolve(err ? null : parseConsentValue(stdout))
    })
  })
}

export async function readMicPermissionState(): Promise<MicPermissionState> {
  if (process.platform !== 'win32') return 'unknown'
  try {
    const [root, nonPackaged] = await Promise.all([
      regQueryValue(CONSENT_ROOT),
      regQueryValue(`${CONSENT_ROOT}\\NonPackaged`)
    ])
    return resolveMicState(root, nonPackaged)
  } catch {
    return 'unknown'
  }
}

export function registerMicPermissionHandlers(): void {
  ipcMain.handle('permissions:micState', async () => readMicPermissionState())
}
