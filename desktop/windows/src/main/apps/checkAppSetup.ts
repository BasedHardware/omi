import { ipcMain, net } from 'electron'

import { isAllowedExternalScheme } from '../externalUrl'

// The renderer can't poll an external-integration developer's arbitrary domain for
// setup completion — a cross-origin GET is CORS-blocked with webSecurity on. This
// main-process IPC does it instead, using Electron's net.fetch (Chromium network
// stack, proxy/TLS aware). It is the faithful, side-effect-free equivalent of
// macOS's URLSession poll: a single GET + JSON parse, no repeated enable calls.
//
// Hardened: https-only (the URL comes from developer-authored app config; a
// file://, UNC, or custom-protocol URL handed to the network stack is an abuse
// vector), a ~6s timeout so one slow webhook can't wedge the poll, and false on
// ANY failure (fails closed — same as macOS's isAppSetupCompleted).

const SETUP_CHECK_TIMEOUT_MS = 6000

export async function checkAppSetup(args: { url?: unknown; uid?: unknown }): Promise<boolean> {
  const rawUrl = typeof args?.url === 'string' ? args.url : ''
  const uid = typeof args?.uid === 'string' ? args.uid : ''
  if (!isAllowedExternalScheme(rawUrl, ['https'])) return false

  let target: string
  try {
    const u = new URL(rawUrl)
    u.searchParams.set('uid', uid)
    target = u.toString()
  } catch {
    return false
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), SETUP_CHECK_TIMEOUT_MS)
  try {
    const res = await net.fetch(target, { method: 'GET', signal: controller.signal })
    if (!res.ok) return false
    const json = (await res.json()) as { is_setup_completed?: unknown }
    return json?.is_setup_completed === true
  } catch {
    // Never log the raw URL — its query string may carry the uid or a token.
    return false
  } finally {
    clearTimeout(timer)
  }
}

/** Register the Apps IPC surface. Call once during main setup. */
export function registerAppsIpc(): void {
  ipcMain.handle('apps:checkSetup', (_e, args: { url: string; uid: string }) => checkAppSetup(args))
}
