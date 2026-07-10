const WINDOWS_INSTALL_ID_KEY = 'omi-windows-install-id'

type InstallIdStorage = Pick<Storage, 'getItem' | 'setItem'>

function defaultStorage(): Storage {
  return window.localStorage
}

/** Return the stable, per-install identifier that backs Windows provenance. */
export function getWindowsInstallId(
  storage: InstallIdStorage = defaultStorage(),
  generateId: () => string = () => crypto.randomUUID()
): string {
  const existing = storage.getItem(WINDOWS_INSTALL_ID_KEY)
  if (existing) return existing

  const installId = generateId()
  storage.setItem(WINDOWS_INSTALL_ID_KEY, installId)
  return installId
}

/**
 * Return the backend contract hash: first eight hex chars of SHA-256 over the
 * stable Windows install id. The raw identifier never leaves the renderer.
 */
export async function getWindowsDeviceIdHash(
  storage: InstallIdStorage = defaultStorage()
): Promise<string> {
  const bytes = new TextEncoder().encode(getWindowsInstallId(storage))
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('')
    .slice(0, 8)
}
