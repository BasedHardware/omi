/** Where the local omi bridge lives, and the display geometry everything else
 *  is laid out against. */

/**
 * Default bridge endpoint. The glasses render through the phone's WebView, so
 * on real hardware this has to be the LAN IP of the machine running the bridge
 * — `127.0.0.1` only resolves for the desktop simulator. Override without
 * rebuilding by appending `?bridge=ws://192.168.1.20:8765/app` to the app URL,
 * or at build time with `VITE_OMI_BRIDGE_URL`.
 */
const DEFAULT_BRIDGE_URL = 'ws://127.0.0.1:8788/app'

/** Resolve the bridge URL: query param > build-time env > default. */
export function bridgeUrl(): string {
  try {
    const fromQuery = new URLSearchParams(window.location.search).get('bridge')
    if (fromQuery) return fromQuery
  } catch {
    /* no window.location in a non-browser host; fall through */
  }
  const fromEnv = import.meta.env?.VITE_OMI_BRIDGE_URL
  return typeof fromEnv === 'string' && fromEnv.length > 0 ? fromEnv : DEFAULT_BRIDGE_URL
}

/** Full G2 canvas. Nothing may be positioned outside this box. */
export const CANVAS_WIDTH = 576
export const CANVAS_HEIGHT = 288

/** The bottom strip is reserved for connection state and push banners, so the
 *  body gets the rest. */
export const STATUS_HEIGHT = 48
export const BODY_HEIGHT = CANVAS_HEIGHT - STATUS_HEIGHT

/** Container IDs are stable across rebuilds so `textContainerUpgrade` keeps
 *  targeting the same box. ID *and* name must match or the update is dropped
 *  silently, so both live here. */
export const HOME_LIST_ID = 1
export const HOME_LIST_NAME = 'home' // containerName is capped at 16 chars
export const BODY_ID = 2
export const BODY_NAME = 'body'
export const STATUS_ID = 3
export const STATUS_NAME = 'status'

/**
 * Characters per body page. The full 576x288 canvas holds roughly 400-500
 * characters; the body is 240 of those 288 rows, so ~380 leaves a little slack
 * for a long final word rather than clipping it.
 */
export const PAGE_CHARS = 380

/** One line of the status strip, so it never wraps into a second row. */
export const STATUS_CHARS = 56

/** A flaky BLE hop can leave a bridge call hanging for ~30s. Fail it early so
 *  the serialized queue keeps moving instead of wedging the whole app. */
export const BRIDGE_CALL_TIMEOUT_MS = 5_000

/** How long a bridge request may go unanswered before the view shows an error
 *  instead of an endless spinner. */
export const REQUEST_TIMEOUT_MS = 20_000

/** How long a push banner stays on screen before the status line reverts. */
export const BANNER_TTL_MS = 15_000
