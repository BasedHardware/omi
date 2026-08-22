// Guard against any top-level navigation away from the app renderer.
//
// Electron's default behavior for a file dropped ANYWHERE outside a designated
// HTML5 drop zone is to NAVIGATE the window to that local `file://` URL, which
// blanks the app until a manual reload. The `will-navigate` event fires for such
// renderer-initiated navigations (a stray drop, or `window.location = …`). It
// does NOT fire for the app's own HashRouter route changes (same-document
// `#hash` nav) or for programmatic `loadURL`/`loadFile`/`reload`, so cancelling
// here cannot break in-app routing or the initial window load.
//
// Every privileged renderer carries the preload bridge, so allowing an in-place
// navigation to an attacker origin would hand that bridge to remote content.
// Windows load their renderer once (dev `http://localhost:PORT`, prod loopback
// `http://127.0.0.1:PORT`, or the `file://` index fallback) and then route with
// same-document hashes. Any other origin/document is therefore rejected.
//
// Extracted as a pure predicate so it is unit-testable without an Electron app,
// mirroring `windowShortcuts.ts` / `externalUrl.ts`.

/**
 * True iff a `will-navigate` to `targetUrl` should be cancelled. HTTP renderers
 * may stay on their exact origin. File renderers may stay on their exact file.
 * Unparseable URLs and every cross-origin/custom-scheme target fail closed.
 *
 * @param targetUrl  the navigation target (the `url` arg of `will-navigate`)
 * @param currentUrl the URL the window currently shows (`webContents.getURL()`)
 */
export function shouldBlockNavigation(targetUrl: string, currentUrl: string): boolean {
  let target: URL
  let current: URL
  try {
    target = new URL(targetUrl)
    current = new URL(currentUrl)
  } catch {
    return true
  }
  if (current.protocol === 'file:') {
    return target.protocol !== 'file:' || target.pathname !== current.pathname
  }
  return target.origin !== current.origin
}
