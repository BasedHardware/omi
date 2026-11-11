import { release } from 'os'

// Windows 11 22H2 — the first build where Electron's `backgroundMaterial:
// 'mica'` is reliable (Mica itself shipped in 22000, but the DWM attribute
// Electron uses, DWMWA_SYSTEMBACKDROP_TYPE, exists from 22621).
export const MICA_MIN_BUILD = 22621

/** OS build number from `os.release()` ("10.0.26100" → 26100). 0 if unparseable. */
export function windowsBuildNumber(rel: string = release()): number {
  const build = Number(rel.split('.')[2])
  return Number.isFinite(build) ? build : 0
}

/** Whether the main window may use the Mica background material. */
export function supportsMica(
  platform: NodeJS.Platform = process.platform,
  build: number = windowsBuildNumber()
): boolean {
  return platform === 'win32' && build >= MICA_MIN_BUILD
}
