// Guard against a stray file drop navigating a window away from the app.
//
// Electron's default behavior for a file dropped ANYWHERE outside a designated
// HTML5 drop zone is to NAVIGATE the window to that local `file://` URL, which
// blanks the app until a manual reload. The `will-navigate` event fires for such
// renderer-initiated navigations (a stray drop, or `window.location = …`). It
// does NOT fire for the app's own HashRouter route changes (same-document
// `#hash` nav) or for programmatic `loadURL`/`loadFile`/`reload`, so cancelling
// here cannot break in-app routing or the initial window load.
//
// We cancel ONLY a navigation to a `file:` URL that is not the app's own
// document. Every window loads its renderer once (dev `http://localhost:PORT`,
// prod loopback `http://127.0.0.1:PORT`, or the `file://` index.html fallback)
// and then only changes its `#hash`, so the sole `file:` URL a window ever shows
// is its own index.html — a dropped file is always a different path. http/https/
// mailto and `window.open()`ed links keep their existing behavior (the window's
// `setWindowOpenHandler` → `shell.openExternal`; the checkout window's own
// `will-navigate` completion handling — both target http(s), never `file:`).
//
// Extracted as a pure predicate so it is unit-testable without an Electron app,
// mirroring `windowShortcuts.ts` / `externalUrl.ts`.

/**
 * True iff a `will-navigate` to `targetUrl` should be cancelled. Blocks a
 * navigation to a local `file:` URL unless it targets the same document the
 * window already shows (the `loadFile` fallback runs on a `file://` origin).
 * Everything else — http/https/mailto/custom schemes, unparseable URLs — is
 * allowed through unchanged.
 *
 * @param targetUrl  the navigation target (the `url` arg of `will-navigate`)
 * @param currentUrl the URL the window currently shows (`webContents.getURL()`)
 */
export function shouldBlockNavigation(targetUrl: string, currentUrl: string): boolean {
  let target: URL
  try {
    target = new URL(targetUrl)
  } catch {
    return false // unparseable → not our stray-file case; leave behavior unchanged
  }
  if (target.protocol !== 'file:') return false // only local-file navigations are cancelled here
  // Allow the app's own document — the loadFile fallback serves the renderer from
  // a file:// origin, so a navigation back to that exact path is legitimate.
  try {
    const current = new URL(currentUrl)
    if (current.protocol === 'file:' && current.pathname === target.pathname) return false
  } catch {
    // No / unparseable current URL → treat the file target as foreign (block).
  }
  return true
}
